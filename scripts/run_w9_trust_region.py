from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

"""W9 — Trust-region surrogate-COMSOL calibration loop CLI.
W9 命令行入口：信赖域 surrogate-COMSOL 校正回路。

每个 outer iteration：
  1. 调 W8 surrogate 优化（80 inner steps，初值 = 当前 H_k，注入上一轮的校正锚点）
  2. 调 COMSOL frequency sweep 在 W8 选出的 freqs/weights 上
  3. 计算 COMSOL RMS 合成场 + 真 enrichment
  4. 记录残差 (COMSOL - surrogate) 为新锚点
  5. 根据预测/实际改善比率更新信赖半径
  6. 维护 best-by-COMSOL bookkeeping，下一轮从 best H 重启

Each outer iteration alternates surrogate (W8) descent and COMSOL ground-truth eval.
"""

import argparse  # 命令行 / Argparse
import json  # JSON / JSON
import subprocess  # 子进程 / Subprocess
import sys  # 系统 / System
import time  # 时间 / Time
from pathlib import Path  # 路径 / Paths

PROJECT_ROOT = Path(__file__).resolve().parents[1]  # 根 / Root
if str(PROJECT_ROOT) not in sys.path:  # 检查 / Check
    sys.path.insert(0, str(PROJECT_ROOT))  # 添加 / Add

import numpy as np  # NumPy / NumPy

from src.comsol.credentials import ensure_comsol_credentials  # 在父进程预先生成凭据让子进程继承 / Pre-generate creds so children inherit
from src.comsol.import_results import interpolate_to_grid  # 插值 / Interpolate
from src.forced_response.score_comsol_response import load_forced_response_csv  # CSV / CSV
from src.optimisation.trust_region_w9 import TrustRegionAnchor  # 锚点 / Anchor
from src.optimisation.trust_region_w9 import TrustRegionConfig  # 配置 / Config
from src.optimisation.trust_region_w9 import make_calibration_npz  # 序列化 / Serialise
from src.optimisation.trust_region_w9 import summarise_iteration  # 摘要 / Summary
from src.optimisation.trust_region_w9 import trust_region_ratio  # 比率 / Ratio
from src.optimisation.trust_region_w9 import update_trust_radius  # 更新半径 / Update radius
from src.scoring.recognisability_score import recognisability_score_grid  # 评分 / Score


def rms_compose(amps: list[np.ndarray], weights: list[float]) -> np.ndarray:  # 加权 RMS / Weighted RMS
    w = np.asarray(weights, dtype=np.float64) / max(sum(weights), 1.0e-12)  # 归一 / Normalise
    stack = np.stack([a ** 2 for a in amps], axis=0)  # 平方 / Squares
    return np.sqrt(np.clip((w[:, None, None] * stack).sum(axis=0), 0.0, None))  # sqrt / sqrt


def run_w8_inner(target_path: str, candidate_id: str, num_steps: int, lr_H: float, lr_freq: float, lr_weight: float, num_frequencies: int, f_min: float, f_max: float, smoothness_weight: float, sbs_seed: str | None, calibration_npz: str | None, freeze_freq_first_steps: int, freeze_freq_and_weight: bool, initial_H: str | None) -> dict:  # 调用 W8 inner / Call W8 inner
    cmd = ["python", "scripts/run_w8_recognisability.py", "--target", target_path, "--candidate-id", candidate_id, "--num-frequencies", str(int(num_frequencies)), "--num-steps", str(int(num_steps)), "--snapshot-every", "999999", "--learning-rate-h", f"{float(lr_H)}", "--learning-rate-freq", f"{float(lr_freq) if not freeze_freq_and_weight else 0.0}", "--learning-rate-weight", f"{float(lr_weight) if not freeze_freq_and_weight else 0.0}", "--freeze-freq-first-steps", str(int(freeze_freq_first_steps if not freeze_freq_and_weight else num_steps + 1)), "--f-min-hz", f"{float(f_min)}", "--f-max-hz", f"{float(f_max)}", "--smoothness-weight", f"{float(smoothness_weight)}"]  # CLI / CLI
    if sbs_seed:  # SBS / SBS
        cmd.extend(["--sbs-seed", str(sbs_seed)])  # 加 / Add
    if initial_H:  # 初值 / Initial H
        cmd.extend(["--initial-H", str(initial_H)])  # 加 / Add
    if calibration_npz:  # 校正 / Calibration
        cmd.extend(["--calibration-npz", str(calibration_npz)])  # 加 / Add
    print("  $ " + " ".join(cmd[1:]))  # 打印 / Print
    result = subprocess.run([".venv/bin/" + cmd[0]] + cmd[1:], cwd=str(PROJECT_ROOT), capture_output=True, text=True, check=False)  # 跑 / Run
    if result.returncode != 0:  # 失败 / Failed
        print(result.stdout[-2000:])  # 标准输出 / Stdout
        print(result.stderr[-2000:])  # 标准错误 / Stderr
        raise RuntimeError(f"W8 inner failed with exit code {result.returncode}")  # 抛错 / Raise
    summary_path = PROJECT_ROOT / "candidates" / candidate_id / "w8_optimization_summary.json"  # 摘要 / Summary
    return json.loads(summary_path.read_text(encoding="utf-8"))  # 加载 / Load


def run_comsol_sweep_inner(candidate_id: str, freqs_hz: list[float], output_prefix: str) -> dict:  # 调用 COMSOL sweep / Call COMSOL sweep
    freq_str = ",".join(f"{f:.1f}" for f in freqs_hz)  # 频率串 / Freq string
    validation_dir = f"data/comsol_frequency_exports/{output_prefix}_validation"  # 验证目录 / Validation dir
    cmd = [".venv/bin/python", "scripts/run_comsol_frequency_sweep.py", "--base-candidate-id", candidate_id, "--run-name", f"{output_prefix}_comsol", "--frequencies", freq_str, "--candidate-prefix", output_prefix, "--validation-output-dir", validation_dir]  # CLI / CLI
    print("  $ " + " ".join(cmd[1:]))  # 打印 / Print
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True, check=False)  # 跑 / Run
    if result.returncode != 0:  # 失败 / Failed
        print(result.stdout[-3000:])  # 输出 / Stdout
        print(result.stderr[-3000:])  # 错误 / Stderr
        raise RuntimeError(f"COMSOL sweep failed with exit code {result.returncode}")  # 抛错 / Raise
    return {"validation_dir": validation_dir, "output_prefix": output_prefix}  # 返回 / Return


def load_comsol_amps(output_prefix: str, freqs_hz: list[float], grid_size: int = 256) -> list[np.ndarray]:  # 加载所有频率的 COMSOL 场 / Load all COMSOL fields
    amps: list[np.ndarray] = []  # 振幅 / Amplitudes
    for f in freqs_hz:  # 遍历 / Iterate
        found = None  # 占位 / Placeholder
        for fmt in [f"{f:.1f}", f"{f:.2f}"]:  # 两种精度 / Two precisions
            label = f"f{fmt}".replace(".", "p")  # 标签 / Label
            csv_path = PROJECT_ROOT / "data" / "comsol_exports" / f"{output_prefix}_sweep_{label}" / "forced_response" / "forced_response.csv"  # 路径 / Path
            if csv_path.exists():  # 找到 / Found
                x, y, _, _, w_abs = load_forced_response_csv(csv_path)  # CSV / Load
                field = interpolate_to_grid(x, y, w_abs, grid_size=int(grid_size))  # 插值 / Interp
                found = field  # 找到 / Found
                break  # 退出 / Break
        if found is None:  # 没找到 / Missing
            raise FileNotFoundError(f"COMSOL forced response for {f} Hz not found under prefix {output_prefix}")  # 抛错 / Raise
        amps.append(found)  # 追加 / Append
    return amps  # 返回 / Return


def compute_surrogate_composite_from_summary(candidate_id: str) -> np.ndarray:  # 从 W8 candidate 加载 surrogate composite / Load surrogate composite
    npy_path = PROJECT_ROOT / "candidates" / candidate_id / "composite_amplitude.npy"  # 路径 / Path
    if not npy_path.exists():  # 不存在 / Missing
        raise FileNotFoundError(f"surrogate composite not found: {npy_path}")  # 抛错 / Raise
    return np.load(npy_path).astype(np.float64)  # 加载 / Load


def main() -> int:  # 主 / Main
    parser = argparse.ArgumentParser(description="W9 trust-region surrogate-COMSOL calibration loop. / W9 信赖域代理-COMSOL 校正回路。")  # 解析器 / Parser
    parser.add_argument("--target", type=str, required=True, help="Path to target binary NPY. / 目标二值 NPY 路径。")  # Target / Target
    parser.add_argument("--run-name", type=str, default="w9_run", help="Name for this W9 run (used as candidate id prefix). / W9 运行名称。")  # Run / Run
    parser.add_argument("--outer-iterations", type=int, default=4, help="Number of outer (COMSOL) iterations. / 外层迭代次数。")  # Outer / Outer
    parser.add_argument("--inner-steps", type=int, default=80, help="W8 inner steps per outer iter. / 每外层 W8 内层步数。")  # Inner / Inner
    parser.add_argument("--num-frequencies", type=int, default=6, help="Frequency count K. / 频率数。")  # Freqs / Freqs
    parser.add_argument("--f-min-hz", type=float, default=120.0, help="Frequency lower bound. / 频率下限。")  # fmin / fmin
    parser.add_argument("--f-max-hz", type=float, default=1200.0, help="Frequency upper bound. / 频率上限。")  # fmax / fmax
    parser.add_argument("--initial-lr-H", type=float, default=0.05, help="Inner W8 initial H LR (modulated by trust radius). / 内层 H 学习率初值。")  # LR / LR
    parser.add_argument("--initial-trust-radius-mm", type=float, default=0.5, help="Initial trust radius in mm (H-space Euclidean). / 初始信赖半径 (mm)。")  # TR / TR
    parser.add_argument("--sbs-seed", type=str, default=None, help="Optional SBS seed NPY. / 可选 SBS 种子。")  # SBS / SBS
    parser.add_argument("--smoothness-weight", type=float, default=4.0, help="W8 smoothness weight. / 平滑罚。")  # Smooth / Smooth
    parser.add_argument("--freeze-after-iter", type=int, default=1, help="Freeze freq/weight after this many outer iters (anchor stability). / 第几轮后冻结 freq/weight。")  # Freeze / Freeze
    args = parser.parse_args()  # 解析 / Parse

    cfg = TrustRegionConfig(outer_iterations=int(args.outer_iterations), inner_w8_steps=int(args.inner_steps), inner_w8_lr_H=float(args.initial_lr_H), num_frequencies=int(args.num_frequencies), f_min_hz=float(args.f_min_hz), f_max_hz=float(args.f_max_hz), initial_trust_radius_mm=float(args.initial_trust_radius_mm), sbs_seed_path=args.sbs_seed, smoothness_weight=float(args.smoothness_weight), freeze_freqs_after_iter=int(args.freeze_after_iter))  # 配置 / Config

    creds = ensure_comsol_credentials({})  # 在父进程生成凭据，os.environ 设置后传给所有 subprocess / Generate creds in parent so children inherit
    print(f"COMSOL credentials prepared (will propagate to subprocess via os.environ): user={creds.username}, generated={creds.generated}")  # 提示 / Print
    target = np.load(args.target).astype(bool)  # 目标 / Target
    run_root = PROJECT_ROOT / "candidates" / "w9_runs" / args.run_name  # 根 / Root
    run_root.mkdir(parents=True, exist_ok=True)  # 建目录 / Mkdir
    anchors: list[TrustRegionAnchor] = []  # 锚点列表 / Anchor list
    trust_radius_mm = float(cfg.initial_trust_radius_mm)  # 当前信赖半径 / Current radius
    history: list[dict] = []  # 历史 / History
    best_iteration: int = -1  # 最佳轮 / Best iter
    best_comsol_E: float = float("-inf")  # 最佳 COMSOL / Best COMSOL
    best_H_path: str | None = None  # 最佳 H / Best H path
    locked_freqs: list[float] | None = None  # 冻结频率 / Locked freqs
    locked_weights: list[float] | None = None  # 冻结权重 / Locked weights

    print(f"=== W9 trust-region loop: {args.run_name} ===")  # 标题 / Header
    print(f"target: {args.target}, outer={cfg.outer_iterations}, inner={cfg.inner_w8_steps}, initial_radius={trust_radius_mm} mm")  # 信息 / Info

    t_start = time.time()  # 开始 / Start
    for k in range(cfg.outer_iterations):  # 外循环 / Outer loop
        iter_t = time.time()  # 计时 / Timer
        cand_id_k = f"w9_{args.run_name}_iter{k}"  # 候选 ID / Candidate ID
        calib_npz = run_root / f"calibration_iter{k}.npz"  # 校正 / Calibration
        meta = make_calibration_npz(anchors, trust_radius_mm, float(cfg.calibration_sigma_factor), calib_npz)  # 序列化 / Serialise
        print(f"\n--- Outer iter {k+1}/{cfg.outer_iterations} (trust radius={trust_radius_mm:.3f} mm, anchors={meta['num_anchors']}) ---")  # 头 / Header

        initial_H_arg: str | None = None  # 初值 / Init
        if best_H_path is not None:  # 用最佳 H / Use best
            initial_H_arg = best_H_path  # 路径 / Path

        freeze_fw = (locked_freqs is not None)  # 是否冻结 / Freeze?
        if freeze_fw:  # 冻结时手工指定频率初值需要额外参数；这里简化为完全冻结优化 / Simplified
            pass  # 占位 / Pass

        adapted_lr_H = float(cfg.inner_w8_lr_H) * (trust_radius_mm / cfg.initial_trust_radius_mm)  # LR 随信赖半径 / LR scaled by trust radius
        summary = run_w8_inner(target_path=args.target, candidate_id=cand_id_k, num_steps=cfg.inner_w8_steps, lr_H=adapted_lr_H, lr_freq=cfg.inner_w8_lr_freq, lr_weight=cfg.inner_w8_lr_weight, num_frequencies=cfg.num_frequencies, f_min=cfg.f_min_hz, f_max=cfg.f_max_hz, smoothness_weight=cfg.smoothness_weight, sbs_seed=cfg.sbs_seed_path, calibration_npz=str(calib_npz) if meta["num_anchors"] > 0 else None, freeze_freq_first_steps=20, freeze_freq_and_weight=freeze_fw, initial_H=initial_H_arg)  # 跑 W8 / Run W8

        freqs_k = [float(f) for f in summary["frequencies_hz"]]  # 频率 / Freqs
        weights_k = [float(w) for w in summary["weights"]]  # 权重 / Weights
        surrogate_amp = compute_surrogate_composite_from_summary(cand_id_k)  # 代理 / Surrogate
        H_k = np.loadtxt(PROJECT_ROOT / "candidates" / cand_id_k / "H.csv", delimiter=",")  # H / H
        H_save_path = run_root / f"H_iter{k}.npy"  # H 路径 / H path
        np.save(H_save_path, H_k)  # 保存 / Save

        # COMSOL eval — use first iter's freqs/weights to keep anchor structure stable
        if k == 0 and cfg.freeze_freqs_after_iter == 1:  # 锁定 / Lock
            locked_freqs, locked_weights = freqs_k, weights_k  # 锁定 / Lock
            print(f"  → locked freqs/weights for subsequent iters: freqs={[round(f,1) for f in freqs_k]}, top weight={max(weights_k):.2f}")  # 提示 / Hint
        eval_freqs = locked_freqs if locked_freqs is not None else freqs_k  # 评估频率 / Eval freqs
        eval_weights = locked_weights if locked_weights is not None else weights_k  # 评估权重 / Eval weights

        comsol_prefix = f"w9_{args.run_name}_iter{k}"  # 前缀 / Prefix
        run_comsol_sweep_inner(candidate_id=cand_id_k, freqs_hz=eval_freqs, output_prefix=comsol_prefix)  # 跑 COMSOL / Run COMSOL
        comsol_amps = load_comsol_amps(comsol_prefix, eval_freqs, grid_size=256)  # 加载 / Load
        comsol_composite = rms_compose(comsol_amps, eval_weights)  # 真 RMS / True RMS

        # Downsample COMSOL composite to surrogate grid for residual storage; resize target to 256 for COMSOL scoring
        from PIL import Image  # 延迟导入 / Lazy
        proxy_grid = int(surrogate_amp.shape[0])  # 代理网格 / Proxy size
        comsol_proxy = np.array(Image.fromarray(comsol_composite).resize((proxy_grid, proxy_grid), Image.BILINEAR), dtype=np.float64)  # 下采样到代理 / Downsample
        residual = comsol_proxy - surrogate_amp  # 残差 (proxy grid) / Residual at proxy grid

        # Scoring at native COMSOL resolution against target_256
        target_256 = target  # 目标 256 / Target 256
        if target.shape != comsol_composite.shape:  # 形状对齐 / Shape align
            target_256 = np.array(Image.fromarray(target.astype(np.uint8) * 255).resize(comsol_composite.shape[::-1], Image.NEAREST)) > 127  # NN 缩放 / NN resize
        comsol_metrics = recognisability_score_grid(comsol_composite, target_256, sigma_rel=0.05, percentile=20.0)  # 评分 / Score
        # Surrogate scoring against downscaled target at proxy grid
        target_proxy = np.array(Image.fromarray(target.astype(np.uint8) * 255).resize((proxy_grid, proxy_grid), Image.NEAREST)) > 127  # NN 缩放 / NN resize
        surrogate_metrics = recognisability_score_grid(surrogate_amp, target_proxy, sigma_rel=0.05, percentile=20.0)  # 代理评分 / Surrogate score

        anchor = TrustRegionAnchor(iteration=k, H_grid=H_k, residual_amp=residual, comsol_amp=comsol_composite, surrogate_amp=surrogate_amp, comsol_enrichment=float(comsol_metrics["enrichment_factor"]), surrogate_enrichment=float(surrogate_metrics["enrichment_factor"]), freqs_hz=eval_freqs, weights=eval_weights)  # 锚 / Anchor
        anchors.append(anchor)  # 加 / Append

        comsol_hist = [a.comsol_enrichment for a in anchors]  # 历史 / History
        surr_hist = [a.surrogate_enrichment for a in anchors]  # 历史 / History
        ratio = trust_region_ratio(comsol_hist, surr_hist)  # 比率 / Ratio
        new_radius, decision = update_trust_radius(ratio, trust_radius_mm, cfg)  # 更新 / Update

        if anchor.comsol_enrichment > best_comsol_E:  # 接受 / Accept
            best_comsol_E = anchor.comsol_enrichment  # 更新 / Update
            best_iteration = k  # 轮次 / Iteration
            best_H_path = str(H_save_path)  # 路径 / Path

        iter_summary = summarise_iteration(k, anchor, trust_radius_mm, decision)  # 摘要 / Summary
        iter_summary["iter_seconds"] = float(time.time() - iter_t)  # 时间 / Time
        iter_summary["target_path"] = str(args.target)  # 目标 / Target
        iter_summary["adapted_lr_H"] = float(adapted_lr_H)  # LR / LR
        history.append(iter_summary)  # 加 / Append
        print(f"  surrogate enrichment={anchor.surrogate_enrichment:.3f}, COMSOL enrichment={anchor.comsol_enrichment:.3f}, gap={anchor.comsol_enrichment - anchor.surrogate_enrichment:+.3f}")  # 打印 / Print
        print(f"  trust radius: {trust_radius_mm:.3f} → {new_radius:.3f} ({decision})")  # 打印 / Print
        print(f"  iter time: {time.time() - iter_t:.1f}s")  # 时间 / Time
        trust_radius_mm = new_radius  # 更新 / Update

    total_t = time.time() - t_start  # 总时 / Total
    print(f"\n=== W9 finished in {total_t:.1f}s ===")  # 完成 / Done
    print(f"Best COMSOL enrichment: {best_comsol_E:.3f}x at iter {best_iteration}")  # 最佳 / Best

    report = {"run_name": args.run_name, "target_path": str(args.target), "outer_iterations": cfg.outer_iterations, "inner_steps": cfg.inner_w8_steps, "total_seconds": float(total_t), "best_comsol_enrichment": float(best_comsol_E), "best_iteration": int(best_iteration), "best_H_path": str(best_H_path) if best_H_path else None, "history": history}  # 报告 / Report
    report_path = run_root / "w9_history.json"  # 路径 / Path
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")  # 写 / Write
    print(f"Report: {report_path}")  # 提示 / Print
    return 0  # 返回 / Return


if __name__ == "__main__":  # 直接 / Direct
    raise SystemExit(main())  # 退出 / Exit
