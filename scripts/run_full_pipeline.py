from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import argparse  # 导入命令行解析 / Import argument parsing
import json  # 导入 JSON 工具 / Import JSON utilities
import subprocess  # 导入子进程工具 / Import subprocess utilities
import sys  # 导入系统工具 / Import system utilities
import time  # 导入计时工具 / Import timing utilities
from pathlib import Path  # 导入路径工具 / Import path utilities

PROJECT_ROOT = Path(__file__).resolve().parents[1]  # 计算项目根目录 / Compute project root
if str(PROJECT_ROOT) not in sys.path:  # 检查搜索路径 / Check search path
    sys.path.insert(0, str(PROJECT_ROOT))  # 添加项目根 / Add project root

from src.comsol.credentials import ensure_comsol_credentials  # 复用 COMSOL 凭据 / Reuse COMSOL credentials
from src.config import load_config  # 复用配置加载 / Reuse config loader


PYTHON_EXE = sys.executable  # 解析当前 Python 可执行 / Resolve current Python executable


def _frequency_token(frequency_hz: float) -> str:  # 与 run_comsol_frequency_sweep 一致的频率 token / Frequency token compatible with run_comsol_frequency_sweep
    rounded = f"{float(frequency_hz):.3f}".rstrip("0").rstrip(".")  # 格式化 / Format
    return rounded.replace("-", "m").replace(".", "p")  # 替换不友好字符 / Replace unfriendly characters


def echo(prefix: str, message: str) -> None:  # 统一格式化输出 / Unified formatted print
    print(f"[{prefix}] {message}", flush=True)  # 写到 stdout / Write to stdout


def run_stage(name: str, command: list[str], log_path: Path | None = None, allow_fail: bool = False) -> dict:  # 运行一个流水线阶段 / Run a pipeline stage
    echo(name, "$ " + " ".join(command))  # 显示命令 / Show command
    start = time.time()  # 计时开始 / Start timer
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=str(PROJECT_ROOT), text=True)  # 启动子进程 / Spawn child
    captured_lines: list[str] = []  # 缓存输出 / Capture output
    assert process.stdout is not None  # 断言 stdout 存在 / Assert stdout exists
    for line in process.stdout:  # 流式读取 / Stream lines
        sys.stdout.write(line)  # 转发到 stdout / Forward to stdout
        sys.stdout.flush()  # 立即刷新 / Flush immediately
        captured_lines.append(line)  # 缓存 / Capture
    returncode = process.wait()  # 等待结束 / Wait for end
    elapsed = float(time.time() - start)  # 耗时 / Elapsed
    if log_path is not None:  # 若有日志路径 / If log path provided
        log_path.parent.mkdir(parents=True, exist_ok=True)  # 创建日志父目录 / Create log parent
        log_path.write_text("".join(captured_lines), encoding="utf-8")  # 写日志 / Write log
    status = "ok" if returncode == 0 else "fail"  # 状态 / Status
    if returncode != 0 and not allow_fail:  # 严格失败 / Strict failure
        raise SystemExit(f"[{name}] stage failed with exit code {returncode}. See log: {log_path}. / 阶段失败，退出码 {returncode}。日志：{log_path}。")  # 抛出退出 / Raise exit
    echo(name, f"done in {elapsed:.1f}s ({status}) / 完成 {elapsed:.1f}s（{status}）")  # 打印完成 / Print done
    return {"name": name, "command": command, "returncode": int(returncode), "elapsed_s": float(elapsed), "log_path": str(log_path) if log_path is not None else None, "status": status}  # 返回阶段记录 / Return stage record


def build_argument_parser() -> argparse.ArgumentParser:  # 构造参数解析器 / Build argument parser
    parser = argparse.ArgumentParser(description="One-shot pipeline: W1 → W2/W4 manifold → W3 → W4 → W5 → W6 (v1+v2) → COMSOL forced-response → W2 unified ranker. / 一键流水线。")  # 创建解析器 / Create parser
    parser.add_argument("--config", type=str, default="config.yaml", help="Project config path. / 项目配置路径。")  # 配置 / Config
    parser.add_argument("--target", type=str, default=None, help="Target binary NPY override (defaults to data/processed_targets/target_binary.npy). / 目标 NPY 覆盖。")  # 目标 / Target
    parser.add_argument("--target-tag", type=str, default="run", help="Tag used in candidate ids and report dirs (e.g. ic, client_logo_v3). / 候选与报告标签。")  # 标签 / Tag
    parser.add_argument("--drive-frequency-hz", type=float, default=None, help="Optional drive-frequency override; otherwise derived from W1 verdict. / 可选驱动频率覆盖。")  # 频率 / Frequency
    parser.add_argument("--manifold", type=str, default="reports/design_manifold_pca.npz", help="PCA manifold NPZ; rebuilt if missing. / PCA 流形 NPZ；缺失则重建。")  # 流形 / Manifold
    parser.add_argument("--rebuild-manifold", action="store_true", help="Force rebuild manifold from current candidate pool. / 强制重建流形。")  # 重建流形 / Rebuild
    parser.add_argument("--num-steps-w3", type=int, default=250, help="Adam steps for W3. / W3 Adam 步数。")  # W3 步 / W3 steps
    parser.add_argument("--num-steps-w4", type=int, default=250, help="Adam steps for W4. / W4 Adam 步数。")  # W4 步 / W4 steps
    parser.add_argument("--num-steps-w6", type=int, default=250, help="Adam steps for W6. / W6 Adam 步数。")  # W6 步 / W6 steps
    parser.add_argument("--num-modes-w6", type=int, default=20, help="Modes monitored in W6. / W6 监测模态数。")  # W6 模态 / W6 modes
    parser.add_argument("--skip-w3", action="store_true", help="Skip W3 stage. / 跳过 W3。")  # 跳过 W3 / Skip W3
    parser.add_argument("--skip-w4", action="store_true", help="Skip W4 stage. / 跳过 W4。")  # 跳过 W4 / Skip W4
    parser.add_argument("--skip-w5", action="store_true", help="Skip W5 stage. / 跳过 W5。")  # 跳过 W5 / Skip W5
    parser.add_argument("--skip-w6", action="store_true", help="Skip W6 stage. / 跳过 W6。")  # 跳过 W6 / Skip W6
    parser.add_argument("--skip-comsol", action="store_true", help="Skip COMSOL forced-response stage. / 跳过 COMSOL 强迫响应阶段。")  # 跳过 COMSOL / Skip COMSOL
    parser.add_argument("--skip-rank", action="store_true", help="Skip the final W2 unified-ranking stage. / 跳过 W2 统一排序阶段。")  # 跳过排名 / Skip rank
    parser.add_argument("--comsol-frequencies", type=str, default=None, help="Comma-separated frequencies (Hz) for COMSOL sweep; defaults to derived drive frequency. / COMSOL 扫频频率，默认仅在驱动频率上跑。")  # COMSOL 频率 / COMSOL freqs
    parser.add_argument("--comsol-skip-legacy", action="store_true", help="Skip legacy epsilon-threshold scoring in COMSOL sweep. / 跳过 COMSOL 旧阈值评分。")  # 旧评分 / Skip legacy
    parser.add_argument("--rank-mode", type=str, choices=["auto", "amplitude", "nodal"], default="auto", help="Ranking primary metric. / 排序主指标。")  # 排序模式 / Rank mode
    parser.add_argument("--output-dir", type=str, default=None, help="Pipeline summary directory; defaults to reports/pipeline/<target-tag>/. / 流水线摘要目录。")  # 输出 / Output
    parser.add_argument("--include-candidate", action="append", default=[], help="Include an existing candidate id in COMSOL + ranking stages (repeatable). / 将已有候选编号也纳入 COMSOL 与排名（可重复）。")  # 复用已有候选 / Include existing
    return parser  # 返回 / Return


def derive_drive_frequency(config: dict, verdict_path: Path, override: float | None) -> float:  # 决定驱动频率 / Decide drive frequency
    if override is not None:  # 优先 CLI 覆盖 / Prefer CLI override
        return float(override)  # 返回 / Return
    if verdict_path.exists():  # 检查 verdict 存在 / Check verdict exists
        try:  # 尝试解析 / Try parse
            data = json.loads(verdict_path.read_text(encoding="utf-8"))  # 读取 / Read
            metrics = data.get("metrics", {}) or {}  # 取 metrics / Get metrics
            est = metrics.get("estimated_min_frequency_hz")  # 取估算频率 / Get estimated freq
            if est is not None:  # 命中 / Hit
                return float(est) * 3.0  # 略高于 Weyl 估计 / Slightly above Weyl
        except (OSError, json.JSONDecodeError):  # 容错 / Tolerate
            pass  # 忽略 / Ignore
    return 800.0  # 默认 / Default


def main(argv: list[str] | None = None) -> int:  # 主入口 / Main entry
    parser = build_argument_parser()  # 构造解析器 / Build parser
    args = parser.parse_args(argv)  # 解析 / Parse
    config = load_config(args.config)  # 读取配置 / Load config
    tag = str(args.target_tag).strip() or "run"  # 标签 / Tag
    output_dir = Path(args.output_dir) if args.output_dir else PROJECT_ROOT / "reports" / "pipeline" / tag  # 输出目录 / Output dir
    output_dir.mkdir(parents=True, exist_ok=True)  # 创建目录 / Create dir
    target_arg = ["--target", str(args.target)] if args.target else []  # 目标参数 / Target args
    target_path = Path(args.target) if args.target else Path(config["paths"]["processed_targets_dir"]) / "target_binary.npy"  # 目标路径 / Target path
    if not target_path.exists():  # 检查目标存在 / Check target exists
        raise SystemExit(f"Target binary not found: {target_path}. / 未找到目标二值图：{target_path}。")  # 抛出 / Raise
    verdict_path = PROJECT_ROOT / "reports" / f"target_realizability_{tag}.json"  # W1 报告路径 / W1 report path
    stages: list[dict] = []  # 阶段记录 / Stage records
    stages.append(run_stage("W1", [PYTHON_EXE, "scripts/analyze_target_realizability.py", "--config", args.config, "--output", str(verdict_path), *target_arg], log_path=output_dir / "w1.log"))  # 跑 W1 / Run W1
    drive_freq = derive_drive_frequency(config, verdict_path, args.drive_frequency_hz)  # 解析频率 / Resolve freq
    echo("FREQ", f"drive_frequency_hz = {drive_freq:.2f} (used by W3/W4/W5/W6/COMSOL) / 驱动频率 {drive_freq:.2f}")  # 打印频率 / Print freq
    manifold_path = Path(args.manifold) if args.manifold else Path("reports/design_manifold_pca.npz")  # 流形路径 / Manifold path
    if args.rebuild_manifold or not manifold_path.exists():  # 检查是否构建 / Check whether to build
        stages.append(run_stage("MANIFOLD", [PYTHON_EXE, "scripts/build_design_manifold.py", "--config", args.config, "--output", str(manifold_path)], log_path=output_dir / "manifold.log"))  # 拟合流形 / Fit manifold
    else:  # 跳过 / Skip
        echo("MANIFOLD", f"reused {manifold_path} / 复用 {manifold_path}")  # 复用提示 / Reuse notice
    candidate_ids: list[str] = list(dict.fromkeys(args.include_candidate or []))  # 候选列表（含 include） / Candidate list (with include)
    if not args.skip_w3:  # 跑 W3 / Run W3
        cid = f"w3_pipeline_{tag}"  # 候选 ID / Candidate id
        stages.append(run_stage("W3", [PYTHON_EXE, "scripts/run_w3_optimization.py", "--config", args.config, "--candidate-id", cid, "--drive-frequency-hz", f"{drive_freq:.6f}", "--verdict-report", str(verdict_path), "--num-steps", str(args.num_steps_w3), *target_arg], log_path=output_dir / "w3.log"))  # 跑 W3 / Run W3
        candidate_ids.append(cid)  # 加入候选 / Append
    if not args.skip_w4:  # 跑 W4 / Run W4
        cid = f"w4_pipeline_{tag}"  # 候选 ID / Candidate id
        stages.append(run_stage("W4", [PYTHON_EXE, "scripts/run_w4_optimization.py", "--config", args.config, "--candidate-id", cid, "--drive-frequency-hz", f"{drive_freq:.6f}", "--verdict-report", str(verdict_path), "--manifold", str(manifold_path), "--num-steps", str(args.num_steps_w4), *target_arg], log_path=output_dir / "w4.log"))  # 跑 W4 / Run W4
        candidate_ids.append(cid)  # 加入候选 / Append
    if not args.skip_w5:  # 跑 W5 / Run W5
        stages.append(run_stage("W5", [PYTHON_EXE, "scripts/run_w5_homotopy.py", "--config", args.config, "--target-tag", tag, "--drive-frequency-hz", f"{drive_freq:.6f}", "--verdict-report", str(verdict_path), "--manifold", str(manifold_path), *target_arg], log_path=output_dir / "w5.log"))  # 跑 W5 / Run W5
    if not args.skip_w6:  # 跑 W6 / Run W6
        cid_v1 = f"w6_pipeline_{tag}_v1"  # v1 ID / v1 id
        stages.append(run_stage("W6_v1", [PYTHON_EXE, "scripts/run_w6_spectral.py", "--config", args.config, "--candidate-id", cid_v1, "--drive-frequency-hz", f"{drive_freq:.6f}", "--verdict-report", str(verdict_path), "--manifold", str(manifold_path), "--num-steps", str(args.num_steps_w6), "--num-modes", str(args.num_modes_w6), "--cluster-weight", "0.5", "--amplitude-weight", "1.0", *target_arg], log_path=output_dir / "w6_v1.log"))  # 跑 W6 v1 / Run W6 v1
        candidate_ids.append(cid_v1)  # 加入 / Append
        cid_v2 = f"w6_pipeline_{tag}_v2_strong"  # v2 ID / v2 id
        stages.append(run_stage("W6_v2", [PYTHON_EXE, "scripts/run_w6_spectral.py", "--config", args.config, "--candidate-id", cid_v2, "--drive-frequency-hz", f"{drive_freq:.6f}", "--verdict-report", str(verdict_path), "--manifold", str(manifold_path), "--num-steps", str(args.num_steps_w6), "--num-modes", str(args.num_modes_w6), "--cluster-weight", "2.0", "--amplitude-weight", "1.0", *target_arg], log_path=output_dir / "w6_v2.log"))  # 跑 W6 v2 / Run W6 v2
        candidate_ids.append(cid_v2)  # 加入 / Append
    comsol_results: list[dict] = []  # COMSOL 记录 / COMSOL records
    sweep_candidate_ids: list[str] = []  # COMSOL 克隆出来的候选编号 / Cloned sweep candidate ids
    if not args.skip_comsol and candidate_ids:  # 跑 COMSOL / Run COMSOL
        creds = ensure_comsol_credentials(config)  # 在父进程统一生成 / Generate once in parent
        echo("COMSOL", f"credentials prepared (user={creds.username}, generated={creds.generated}); child subprocesses will inherit. / 凭据已在父进程准备好。")  # 打印凭据状态 / Print credential status
        freq_list = args.comsol_frequencies if args.comsol_frequencies else f"{drive_freq:.3f}"  # 频率列表 / Frequency list
        freq_tokens = [_frequency_token(float(f)) for f in (freq_list.split(",")) if f.strip()]  # 频率 token 列表 / Frequency token list
        for cid in candidate_ids:  # 遍历候选 / Iterate candidates
            run_name = f"pipeline_{tag}_{cid}"  # 运行名 / Run name
            cmd = [PYTHON_EXE, "scripts/run_comsol_frequency_sweep.py", "--config", args.config, "--base-candidate-id", cid, "--frequencies", freq_list, "--run-name", run_name, "--frequency-export-case", run_name]  # COMSOL 命令 / COMSOL command
            if args.comsol_skip_legacy:  # 跳过旧评分 / Skip legacy scoring
                cmd.append("--skip-legacy-epsilon-score")  # 加旗 / Add flag
            stage = run_stage(f"COMSOL_{cid}", cmd, log_path=output_dir / f"comsol_{cid}.log", allow_fail=True)  # 跑 COMSOL / Run COMSOL
            comsol_results.append({"candidate_id": cid, **stage})  # 加入记录 / Append record
            stages.append(stage)  # 加阶段 / Append stage
            if stage["returncode"] == 0:  # 成功则记录 sweep 候选 / On success, record sweep candidates
                for tok in freq_tokens:  # 遍历每个频率 / Iterate per frequency
                    sweep_candidate_ids.append(f"{cid}_sweep_f{tok}")  # 加入 sweep 候选 / Append sweep candidate
    rank_payload: dict | None = None  # 排名占位 / Rank placeholder
    if not args.skip_rank:  # 跑排名 / Run ranker
        candidates_root = Path(config["paths"]["candidates_dir"])  # 候选根目录 / Candidate root
        discovered_sweeps: list[str] = []  # 已存在 sweep 候选 / Discovered sweep candidates
        for cid in candidate_ids:  # 遍历主候选 / Iterate candidates
            for sweep_dir in sorted(candidates_root.glob(f"{cid}_sweep_f*")):  # 扫描 sweep / Scan sweeps
                if (sweep_dir / "H.csv").exists():  # 含 H.csv 才算 / Require H.csv
                    discovered_sweeps.append(sweep_dir.name)  # 加入 / Append
        ranked_ids = list(dict.fromkeys(candidate_ids + sweep_candidate_ids + discovered_sweeps))  # 合并候选去重 / Merge with dedup
        rank_args = [PYTHON_EXE, "scripts/rank_candidates.py", "--config", args.config, "--mode", args.rank_mode, "--top", "10", "--verdict-report", str(verdict_path)]  # 排名命令 / Rank cmd
        for cid in ranked_ids:  # 限定候选 / Restrict candidates
            rank_args.extend(["--candidate", cid])  # 加候选 / Add candidate
        stages.append(run_stage("RANK", rank_args, log_path=output_dir / "rank.log", allow_fail=True))  # 跑排名 / Run rank
        leaderboard_json = PROJECT_ROOT / "reports" / "leaderboard.json"  # 排行 JSON / Leaderboard JSON
        if leaderboard_json.exists():  # 命中 / Hit
            try:  # 尝试解析 / Try parse
                rank_payload = json.loads(leaderboard_json.read_text(encoding="utf-8"))  # 读取 / Read
            except (OSError, json.JSONDecodeError):  # 容错 / Tolerate
                rank_payload = None  # 置空 / Reset
    summary = {"target_tag": tag, "target_path": str(target_path), "verdict_path": str(verdict_path), "drive_frequency_hz": float(drive_freq), "manifold_path": str(manifold_path), "candidates": candidate_ids, "sweep_candidates": sweep_candidate_ids, "comsol_runs": comsol_results, "stages": stages, "rank_payload": rank_payload}  # 摘要 / Summary
    summary_path = output_dir / "pipeline_summary.json"  # 摘要路径 / Summary path
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")  # 写摘要 / Write summary
    echo("DONE", f"summary: {summary_path}, candidates: {candidate_ids}  / 摘要：{summary_path}，候选：{candidate_ids}")  # 总结 / Wrap up
    return 0  # 返回 / Return


if __name__ == "__main__":  # 判断直接运行 / Check direct execution
    raise SystemExit(main())  # 退出 / Exit
