"""W10 CLI — joint H + θ optimisation on orthotropic plate.
W10 命令行入口：H + θ 在正交各向异性 Kirchhoff 板上的联合优化。
"""
from __future__ import annotations  # 类型注解 / Type hints

import argparse  # / Argparse
import os  # / OS for thread env-vars
import sys  # / System
from pathlib import Path  # / Paths


# === Cross-platform determinism: pin BLAS / OMP threads to 1 BEFORE numpy /
# torch are imported. PyTorch on Windows (Intel MKL) and macOS (Accelerate /
# Apple-built MKL) reorder float accumulation differently across threads, so
# the *same* seed on two machines diverges to different local minima after a
# few hundred Adam steps. Forcing single-thread BLAS keeps Adam state
# (numerically) close enough across platforms that the COMSOL forced-response
# downstream lands on the same composite. Users who want max throughput can
# override with --torch-num-threads. /
# 跨平台确定性：在 numpy/torch 导入前钉死单线程 BLAS。Win MKL 和 Mac Accelerate
# 在多线程下浮点累加顺序不同，同 seed 跑出来 Adam 状态会逐步分叉到不同局部极小；
# 锁死单线程后跨平台数值收敛趋同。要回多线程加速可加 --torch-num-threads。
_DEFAULT_TORCH_THREADS = int(os.environ.get("W10_TORCH_NUM_THREADS", "1"))
for _env_name in ("OMP_NUM_THREADS", "MKL_NUM_THREADS",
                   "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS",
                   "VECLIB_MAXIMUM_THREADS"):
    os.environ.setdefault(_env_name, str(_DEFAULT_TORCH_THREADS))

PROJECT_ROOT = Path(__file__).resolve().parents[1]  # 项目根 / Project root
if str(PROJECT_ROOT) not in sys.path:  # / Check
    sys.path.insert(0, str(PROJECT_ROOT))  # / Add

from scripts.run_w3_optimization import derive_candidate_dir  # 候选目录 / Candidate dir
from scripts.run_w3_optimization import load_initial_H  # H 初值 / H init
from scripts.run_w3_optimization import load_verdict  # 判定 / Verdict
from src.config import load_config  # 配置 / Config
from src.optimisation.recognisability_placement_w10 import W10AnisotropyConfig  # 配置 / Config
from src.optimisation.recognisability_placement_w10 import run_w10_anisotropy_placement  # 入口 / Entry
from src.physics.plate_loss_adapter import load_target_binary  # 目标 / Target


def parse_floats(text: str) -> list[float]:  # / Parse floats
    return [float(x.strip()) for x in text.split(",") if x.strip()]  # / Parse


def build_argument_parser() -> argparse.ArgumentParser:  # 解析器 / Parser
    parser = argparse.ArgumentParser(description="Run W10 anisotropy joint optimisation (H + per-cell θ on orthotropic Kirchhoff plate). / 运行 W10 各向异性联合优化（H + per-cell θ）。")  # / Parser
    parser.add_argument("--config", type=str, default="config.yaml", help="Project config. / 项目配置。")  # / Config
    parser.add_argument("--target", type=str, default=None, help="Target NPY override. / 目标 NPY 覆盖。")  # / Target
    parser.add_argument("--verdict-report", type=str, default=None, help="Optional verdict report. / 可选判定报告。")  # / Verdict
    parser.add_argument("--candidate-id", type=str, default="w10_anisotropy_v1", help="Output candidate id. / 候选编号。")  # / Candidate
    parser.add_argument("--num-frequencies", type=int, default=6, help="Joint frequencies K. / 联合频率数 K。")  # / K
    parser.add_argument("--f-min-hz", type=float, default=120.0, help="Freq lower bound. / 频率下限。")  # / Lower
    parser.add_argument("--f-max-hz", type=float, default=1200.0, help="Freq upper bound. / 频率上限。")  # / Upper
    parser.add_argument("--initial-frequencies-hz", type=str, default=None, help="Comma-separated initial freqs. / 初始频率。")  # / Init
    parser.add_argument("--proxy-grid-size", type=int, default=25, help="Proxy grid. / 代理网格。")  # / Grid
    parser.add_argument("--damping-ratio", type=float, default=0.02, help="Damping. / 阻尼比。")  # / Damping
    parser.add_argument("--num-steps", type=int, default=300, help="Adam steps. / Adam 步数。")  # / Steps
    parser.add_argument("--learning-rate-h", type=float, default=0.05, help="H LR. / H 学习率。")  # / H LR
    parser.add_argument("--learning-rate-theta", type=float, default=0.10, help="θ LR (radians). / θ 学习率（弧度）。")  # / θ LR
    parser.add_argument("--learning-rate-freq", type=float, default=0.10, help="Freq logits LR. / 频率学习率。")  # / Freq LR
    parser.add_argument("--learning-rate-weight", type=float, default=0.10, help="Weight logits LR. / 权重学习率。")  # / Weight LR
    parser.add_argument("--enrichment-weight", type=float, default=1.0, help="Enrichment weight. / 富集权重。")  # / Enr
    parser.add_argument("--contrast-weight", type=float, default=1.0, help="Contrast weight. / 对比权重。")  # / Ct
    parser.add_argument("--recall-weight", type=float, default=0.5, help="Recall weight. / Recall 权重。")  # / Rc
    parser.add_argument("--sigma-rel", type=float, default=0.05, help="Gaussian sigma. / 高斯 σ。")  # / σ
    parser.add_argument("--recall-percentile-frac", type=float, default=0.20, help="Recall percentile. / Recall 分位。")  # / Pct
    parser.add_argument("--smoothness-weight", type=float, default=4.0, help="H smoothness weight. / H 平滑罚权重。")  # / Sm
    parser.add_argument("--theta-smoothness-weight", type=float, default=0.50, help="θ smoothness weight (via sin/cos 2θ). / θ 平滑罚权重。")  # / θ Sm
    parser.add_argument("--freq-separation-min-hz", type=float, default=30.0, help="Min freq gap. / 频率间隔下限。")  # / Sep
    parser.add_argument("--freq-separation-weight", type=float, default=0.5, help="Freq separation weight. / 间隔罚权重。")  # / SepW
    parser.add_argument("--freeze-freq-first-steps", type=int, default=60, help="Freeze freq/weight first N. / 冻结步数。")  # / Frz
    parser.add_argument("--plateau-patience", type=int, default=80, help="Plateau patience. / 平台容忍。")  # / Plat
    parser.add_argument("--snapshot-every", type=int, default=25, help="Snapshot interval. / 快照间隔。")  # / Snap
    parser.add_argument("--initial-H", type=str, default=None, help="Initial 15x15 H mm. / H 初值。")  # / H Init
    parser.add_argument("--initial-theta-rad", type=str, default=None, help="Initial 15x15 θ rad (CSV). / θ 初值（弧度 CSV）。")  # / θ Init
    parser.add_argument("--output-dir", type=str, default=None, help="Override output dir. / 覆盖输出目录。")  # / Out
    parser.add_argument("--sinkhorn-weight", type=float, default=0.0, help="Sinkhorn weight. / Sinkhorn 权重。")  # / Sinkhorn
    parser.add_argument("--sinkhorn-epsilon", type=float, default=0.01, help="Sinkhorn ε. / Sinkhorn ε。")  # / ε
    parser.add_argument("--sinkhorn-target-irreps", type=str, default=None, help="Comma-separated irreps. / irrep 列表。")  # / irrep
    parser.add_argument("--stiffness-ratio", type=float, default=None, help="Override stiffness ratio E_||/E_⊥ (else read config.material.stiffness_ratio). / 覆盖各向异性比。")  # / sr
    parser.add_argument("--shear-ratio", type=float, default=None, help="Override shear ratio G/G_iso. / 覆盖剪切比。")  # / Gr
    parser.add_argument("--theta-init-mode", type=str, default="random", choices=["random", "zeros", "diagonal"], help="θ initial mode. / θ 初始模式。")  # / mode
    parser.add_argument("--theta-seed", type=int, default=42, help="θ random seed. / θ 随机种子。")  # / seed
    parser.add_argument("--torch-num-threads", type=int, default=_DEFAULT_TORCH_THREADS, help="torch.set_num_threads value (default 1 for Win/Mac reproducibility; raise for speed). / torch 线程数，默认 1 以求跨平台一致。")  # / threads
    parser.add_argument("--sigma-anneal-start", type=float, default=None, help="Initial sigma_rel for powder loss; linearly shrinks to --sigma-rel over --sigma-anneal-steps. Larger value (e.g. 0.20) protects against gradient-cliff collapse on thin / sparse targets. None disables (uses sigma_rel throughout). / 损失中 powder σ 起步值，逐步收紧到 --sigma-rel；防止细线目标梯度悬崖；None 关闭")  # / sigma anneal
    parser.add_argument("--sigma-anneal-steps", type=int, default=100, help="Number of steps over which sigma anneals from start to end. / Sigma 退火步数")  # / anneal steps
    parser.add_argument("--target-dilation-px", type=int, default=0, help="Pixels of binary dilation applied to the proxy-grid target mask. >0 helps thin targets (e.g. 1-2px outlines). / 目标膨胀像素数；细线/稀疏 target 建议 2-3")  # / dilation
    return parser  # / Return


def _load_theta_csv(path: Path) -> "np.ndarray":  # 读 θ CSV / Load θ CSV
    import numpy as np  # / NumPy
    arr = np.loadtxt(str(path), delimiter=",")  # / Load
    return arr  # / Return


def main(argv: list[str] | None = None) -> int:  # 主 / Main
    import numpy as np  # / NumPy
    import torch  # / Torch — env vars set above were honoured at import
    parser = build_argument_parser()  # / Parser
    args = parser.parse_args(argv)  # / Parse
    # Apply the requested torch thread count. ``set_num_threads`` is safe to
    # call repeatedly; the env vars above pinned BLAS at import time so this
    # mainly affects PyTorch's intra-op pool. /
    # 应用 torch 线程数；环境变量已在导入时锁定 BLAS，这里再锁 torch 自身线程池
    torch.set_num_threads(max(1, int(args.torch_num_threads)))
    config = load_config(args.config)  # / Config
    target = load_target_binary(config, args.target)  # / Target
    verdict = load_verdict(Path(args.verdict_report) if args.verdict_report else None)  # / Verdict
    candidate_dir = derive_candidate_dir(config, args.candidate_id)  # / Dir
    output_dir = Path(args.output_dir) if args.output_dir else candidate_dir  # / Out
    initial_H = load_initial_H(Path(args.initial_H)) if args.initial_H else None  # / H init
    initial_theta = _load_theta_csv(Path(args.initial_theta_rad)) if args.initial_theta_rad else None  # / θ init
    initial_freqs = parse_floats(args.initial_frequencies_hz) if args.initial_frequencies_hz else None  # / Freqs init
    sinkhorn_irreps = [s.strip() for s in args.sinkhorn_target_irreps.split(",")] if args.sinkhorn_target_irreps else None  # / irrep

    opt_config = W10AnisotropyConfig(
        proxy_grid_size=int(args.proxy_grid_size),
        num_frequencies=int(args.num_frequencies),
        f_min_hz=float(args.f_min_hz),
        f_max_hz=float(args.f_max_hz),
        damping_ratio=float(args.damping_ratio),
        num_steps=int(args.num_steps),
        learning_rate_H=float(args.learning_rate_h),
        learning_rate_theta=float(args.learning_rate_theta),
        learning_rate_freq=float(args.learning_rate_freq),
        learning_rate_weight=float(args.learning_rate_weight),
        plateau_patience=int(args.plateau_patience),
        snapshot_every=int(args.snapshot_every),
        smoothness_weight=float(args.smoothness_weight),
        theta_smoothness_weight=float(args.theta_smoothness_weight),
        freq_separation_min_hz=float(args.freq_separation_min_hz),
        freq_separation_weight=float(args.freq_separation_weight),
        freeze_freq_first_steps=int(args.freeze_freq_first_steps),
        initial_frequencies_hz=initial_freqs,
        enrichment_weight=float(args.enrichment_weight),
        contrast_weight=float(args.contrast_weight),
        recall_weight=float(args.recall_weight),
        sigma_rel=float(args.sigma_rel),
        recall_percentile_frac=float(args.recall_percentile_frac),
        sinkhorn_weight=float(args.sinkhorn_weight),
        sinkhorn_epsilon=float(args.sinkhorn_epsilon),
        sinkhorn_target_irreps=sinkhorn_irreps,
        stiffness_ratio=args.stiffness_ratio,
        shear_ratio=args.shear_ratio,
        theta_init_mode=str(args.theta_init_mode),
        theta_seed=int(args.theta_seed),
        sigma_anneal_start=(float(args.sigma_anneal_start) if args.sigma_anneal_start is not None else None),
        sigma_anneal_steps=int(args.sigma_anneal_steps),
        target_dilation_px=int(args.target_dilation_px),
    )  # 配置 / Config

    sr_print = args.stiffness_ratio if args.stiffness_ratio is not None else config.get("material", {}).get("stiffness_ratio", 1.05)  # 显示用 / Display
    print(f"W10 anisotropy start / 启动 W10: candidate={args.candidate_id}, K={opt_config.num_frequencies}, range=[{opt_config.f_min_hz:.0f},{opt_config.f_max_hz:.0f}]Hz, steps={opt_config.num_steps}, sr={sr_print:.3f}, θ_init={opt_config.theta_init_mode}")  # / Print
    summary = run_w10_anisotropy_placement(config, target, opt_config, output_dir, verdict=verdict, initial_H_mm=initial_H, initial_theta_rad=initial_theta)  # / Run

    losses = summary["trace"]["total_loss"]  # / Loss
    enr = summary["trace"]["enrichment"]  # / Enr
    ct = summary["trace"]["contrast"]  # / Ct
    rc = summary["trace"]["recall"]  # / Rc
    print(f"steps={len(losses)}  best_loss={summary['best_loss']:.4f}@step{summary['best_step']}  enrichment {enr[0]:.2f}->{enr[-1]:.2f}  contrast {ct[0]:.2f}->{ct[-1]:.2f}  recall {rc[0]:.2%}->{rc[-1]:.2%}")  # / Print
    print(f"θ RMS deviation: {summary['trace']['theta_rms_deg'][0]:.1f}° → {summary['trace']['theta_rms_deg'][-1]:.1f}°")  # / θ
    print(f"E_||={summary['E_parallel_pa']:.3e}  E_⊥={summary['E_perp_pa']:.3e}  G={summary['G_pp_pa']:.3e}  sr={summary['stiffness_ratio_used']:.3f}")  # / Print
    if summary.get("best_surrogate_metrics"):  # / Surrogate
        m = summary["best_surrogate_metrics"]  # / Take
        print(f"surrogate metrics @ best step: enrichment={m['enrichment']:.2f}x  contrast={m['contrast']:.2f}x  recall={m['recall']*100:.1f}%")  # / Print
    print(f"output dir: {output_dir}")  # / Path
    print(f"summary json: {output_dir / 'w10_optimization_summary.json'}")  # / Summary
    return 0  # / Return


if __name__ == "__main__":  # / Direct
    raise SystemExit(main())  # / Exit
