"""Production pipeline — full inverse design from target → final COMSOL composite.

Pipeline stages:
  S1. Prepare target (from PNG/NPY)
  S2. W10 surrogate optimisation (joint H + θ on tier1 CF-PETG sr≈3)
  S3. COMSOL eigenfrequency analysis (30 modes)
  S4. Phase 1: select top-K IC-likeness modes + user magic off-resonance freqs
  S5. COMSOL forced response at selected freqs
  S6. Exhaustive composite subset search → best (RMS/MAX/SUM up to k=3)
  S7. Optional Phase 2 trust-region (refine H+θ from S2, re-run S3-S6)
  S8. Package final deliverables (H.csv, θ.csv, summary.json, composite npy, density npy, visualisation)

This is the customer-facing path. Returns a dict with all key metrics + artefact paths.
"""
from __future__ import annotations

import itertools
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# Cooperative cancellation hook. The UI server installs a callable returning
# True once the user clicks Stop; _run_subprocess polls it every
# _CANCEL_POLL_INTERVAL_S so a long COMSOL/MATLAB child can be killed promptly
# instead of forcing the user to wait for it to finish. Single-flight pipeline
# (the server runs one job at a time) makes a module global safe here. /
# 协作式取消钩子：UI 点 Stop 后服务器注入返回 True 的回调；_run_subprocess 每
# _CANCEL_POLL_INTERVAL_S 轮询一次，从而能及时杀掉正在跑的 COMSOL/MATLAB 子进程，
# 不必干等它跑完。pipeline 单飞（服务器一次只跑一个任务），用模块全局是安全的。
_CANCEL_CHECK: Callable[[], bool] | None = None
_CANCEL_POLL_INTERVAL_S = 0.3


def _terminate_process_tree(proc: subprocess.Popen) -> None:
    """Best-effort kill of a child process and everything it spawned.

    The child is launched in its own process group/session (see
    _run_subprocess), so signalling the group also reaches the MATLAB/COMSOL
    grandchild. The independently-started mphserver daemon lives in a
    different group and is intentionally left running. /
    尽力杀掉子进程及其派生的整棵进程树。子进程以独立进程组启动，故对进程组
    发信号能波及 MATLAB/COMSOL 孙进程；独立启动的常驻 mphserver 在另一个进程组，
    刻意保留不杀。
    """
    if proc.poll() is not None:
        return
    try:
        if os.name == "nt":
            proc.send_signal(getattr(signal, "CTRL_BREAK_EVENT", signal.SIGTERM))
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError):
        pass
    try:
        proc.wait(timeout=5.0)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        if os.name == "nt":
            proc.kill()
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        pass


def _config_get(cfg: dict, key: str, default: Any) -> Any:
    """Read a key from the `production:` section of config.yaml; fall back to default."""
    return cfg.get("production", {}).get(key, default)


def build_default_pipeline_config(config_yaml_path: str | Path = "config.yaml",
                                     overrides: dict | None = None) -> "ProductionPipelineConfig":
    """Construct a ProductionPipelineConfig from config.yaml production: section, allowing per-call overrides."""
    from src.config import load_config

    config = load_config(str(config_yaml_path))
    overrides = overrides or {}

    def take(key: str, default: Any) -> Any:
        if key in overrides:
            return overrides[key]
        return _config_get(config, key, default)

    magic_raw = take("magic_off_resonance_hz", [165.0])
    if isinstance(magic_raw, str):
        magic = tuple(float(x.strip()) for x in magic_raw.split(",") if x.strip())
    else:
        magic = tuple(float(x) for x in magic_raw)

    return ProductionPipelineConfig(
        candidate_id=str(take("default_candidate_id", "production_design")),
        stiffness_ratio=float(take("stiffness_ratio", 3.0)),
        shear_ratio=float(take("shear_ratio", 1.0)),
        w10_num_steps=int(take("w10_num_steps", 300)),
        w10_lr_h=float(take("w10_lr_h", 0.05)),
        w10_num_frequencies=int(take("w10_num_frequencies", 6)),
        w10_f_min_hz=float(take("w10_f_min_hz", 120.0)),
        w10_f_max_hz=float(take("w10_f_max_hz", 1200.0)),
        w10_sigma_anneal_start=float(take("w10_sigma_anneal_start", 0.20)),
        w10_sigma_anneal_steps=int(take("w10_sigma_anneal_steps", 100)),
        w10_target_dilation_px=int(take("w10_target_dilation_px", 2)),
        w10_min_surrogate_enrichment=float(take("w10_min_surrogate_enrichment", 0.5)),
        multistart_n=int(take("multistart_n", 1)),
        multistart_uplift_threshold=float(take("multistart_uplift_threshold", 0.05)),
        phase2_score_mode=str(take("phase2_score_mode", "composite")),
        phase1_top_k_modes=int(take("phase1_top_k_modes", 6)),
        phase1_off_resonance_hz=float(take("phase1_off_resonance_hz", 1.5)),
        magic_off_resonance_hz=magic,
        enable_magic_freqs=bool(take("enable_magic_freqs", True)),
        phase1_w10_topn=int(take("phase1_w10_topn", 3)),
        eig_n_modes=int(take("eig_n_modes", 30)),
        phase1_band_slack_hz=float(take("phase1_band_slack_hz", 20.0)),
        phase1_offband_min_enrichment=float(take("phase1_offband_min_enrichment", 2.0)),
        phase2_max_iters=int(take("phase2_max_iters", 3)),
        phase2_inner_steps=int(take("phase2_inner_steps", 200)),
        phase2_lr_h_init=float(take("phase2_lr_h_init", 0.025)),
        phase2_freeze_freq_first_steps=int(take("phase2_freeze_freq_first_steps", 20)),
        skip_phase2=bool(overrides.get("skip_phase2", False)),
        skip_comsol=bool(overrides.get("skip_comsol", False)),
    )


@dataclass
class ProductionPipelineConfig:
    """Configuration for the end-to-end inverse-design pipeline."""

    target_path: str = "data/processed_targets/target_binary.npy"
    candidate_id: str = "production_design"
    output_dir: str = "reports/production"

    # Material (defaults to tier1 CF-PETG — best generalising material per generalisation_check_v2)
    stiffness_ratio: float = 3.0
    shear_ratio: float = 1.0

    # W10 surrogate hyper-params (theta optimisation removed; see
    # `recognisability_placement_w10.py` and BATTERY_FINDINGS.md for rationale)
    w10_num_steps: int = 300
    w10_lr_h: float = 0.05
    w10_num_frequencies: int = 6
    w10_f_min_hz: float = 120.0
    w10_f_max_hz: float = 1200.0
    # P0 fix (2026-05): sigma annealing + target dilation guard the surrogate
    # against gradient-cliff collapse on thin / sparse targets. Without these,
    # the recognisability loss (-log(enrichment + 1e-9)) saturates at the
    # epsilon floor for any target whose initial random forced-response
    # produces enrichment < 1e-9, killing the gradient signal and leaving the
    # design essentially random (observed: 4-pointed star outline yielded
    # surrogate enrichment = 4e-36 after 300 steps). /
    # P0 修复：sigma 退火 + 目标膨胀，防止细线/稀疏目标在初始 H 下
    # enrichment 起步即 1e-40、梯度被 -log(x+1e-9) 的 epsilon 削平
    w10_sigma_anneal_start: float = 0.20
    w10_sigma_anneal_steps: int = 100
    w10_target_dilation_px: int = 2
    # Health-check threshold: abort the pipeline before sinking 5+ minutes
    # of COMSOL on a W10 design whose surrogate self-report says it never
    # learned anything. /
    # 健康度阈值：W10 自评 enrichment 低于此值就拒绝下推到 COMSOL
    w10_min_surrogate_enrichment: float = 0.5
    # Multi-start used to differentiate runs via θ_seed when θ was an
    # optimisation variable. After θ optimisation was removed in 2026-05
    # (see BATTERY_FINDINGS.md) the W10 surrogate is deterministic for a
    # given target + config, so N > 1 is a no-op. These fields are kept on
    # the config for backwards compatibility only. /
    # 多启动 N>1 在 θ 撤掉后无效；保留字段仅做兼容
    multistart_n: int = 1
    multistart_uplift_threshold: float = 0.05  # 兼容字段 / Compat only
    # Phase 2 acceptance scoring. "composite" (default, new) uses
    # enrich · √recall to reject the "collapse-to-a-bright-dot" failure
    # mode where enrichment shoots up but the target shape is destroyed.
    # "enrich_only" reproduces the pre-2026-05 behaviour that selected a
    # visually-worse Phase 2 iter because its raw enrich beat Phase 1's. /
    # Phase 2 决策分；composite 防"塌陷成单点"伪赢家
    phase2_score_mode: str = "composite"  # "composite" | "enrich_only"

    # Phase 1 selection
    phase1_top_k_modes: int = 6
    phase1_off_resonance_hz: float = 1.5
    magic_off_resonance_hz: tuple[float, ...] = (165.0,)
    # Magic freqs are tier1 (sr=3.0) empirical values; off by default for
    # other materials. When True, also adds them to the drive list. /
    # magic 是 tier1 经验值；可关闭，避免污染其他材料的设计
    enable_magic_freqs: bool = True
    # Number of W10-trained frequencies (sorted by their learned weight) to
    # inject into the Phase 1 drive list. P1 bridge fix 2026-05: pre-fix the
    # surrogate's K=6 trained frequencies were silently discarded; Phase 1
    # only drove COMSOL at top-K eigfreqs + magic. Now top-N W10 freqs are
    # also offered to the composite search. /
    # 把 W10 训练频率（按权重排序）的 top-N 接入 Phase 1 drive 列表
    phase1_w10_topn: int = 3
    eig_n_modes: int = 30
    # In-band gate for Phase 1 drive-freq selection. W10 only designs H+θ in
    # [w10_f_min_hz, w10_f_max_hz]; the plate's fundamental modes (~70 Hz for
    # a thin plate) are "central blob" patterns whose amplitude covers the
    # whole plate, which trivially passes the IC-likeness score
    # (enrichment×recall) even though they have nothing to do with the target.
    # Reject any eigenmode outside [w10_f_min_hz - slack, w10_f_max_hz + slack]
    # so out-of-band modes can never become drive candidates. /
    # W10 设计带宽以外的 eigenmode（尤其低频"中心一坨"基频）会因 recall≈1
    # 在 IC-likeness 评分里轻易胜出，但根本和目标无关；此 slack 内才允许入选
    phase1_band_slack_hz: float = 20.0
    # Quality escape hatch for the band gate above. A pure frequency cut also
    # throws away genuinely good *low-order* eigenmodes — e.g. a ~64 Hz cross
    # mode with enrichment≈6 — which is exactly what low-symmetry targets
    # (cross / X / plus) need. Enrichment is the real discriminator: a
    # central-blob fundamental has enrichment≈1 (no better than uniform) while
    # a structured low mode has enrichment≫1. So an out-of-band eigenmode is
    # still admitted *iff* its enrichment ≥ this threshold; blobs stay
    # rejected, useful low modes get through. Set very high to restore the old
    # hard-floor behaviour. /
    # 频率硬门的质量旁路：纯按频率切会误杀优质低阶模态（如 ~64Hz 十字模态
    # enr≈6），而这正是十字/叉/加号等低对称目标需要的。enrichment 才是判据：
    # 中心一坨基频 enr≈1，结构化低频模态 enr≫1。带外模态仅当 enr≥此阈值才放行；
    # 调到很大即恢复旧的硬下限行为
    phase1_offband_min_enrichment: float = 2.0

    # Phase 2 trust-region (set max_iters=0 to skip).
    # Defaults bumped (2026-05): old (1 iter / 80 steps / freeze=60 from W10
    # default) routinely produced delta=0 because P2 effectively only got
    # ~20 steps of freq/weight optimisation from a near-optimal P1 starting
    # point. New defaults give P2 a real chance to escape the P1 basin while
    # keeping wall-clock at ~3x the old single-iter cost. /
    # Phase 2 信任域：旧默认（1 轮 / 80 步 / freeze=60）让 P2 实质只跑 ~20 步
    # freq/weight 优化，绝大多数情况下 delta=0；新默认给 P2 真正的优化空间
    phase2_max_iters: int = 3
    phase2_inner_steps: int = 200
    phase2_lr_h_init: float = 0.025
    phase2_freeze_freq_first_steps: int = 20

    # Scoring
    image_size: int = 256

    # Run-control
    skip_phase2: bool = False
    skip_comsol: bool = False  # if True, surrogate-only (for fast preview)


def _emit(progress: Callable[[dict], None] | None, stage: str, message: str, **extra) -> None:
    if progress is not None:
        try:
            progress({"stage": stage, "message": message, **extra})
        except Exception:
            pass


def _run_subprocess(cmd: list[str], cwd: Path, label: str) -> subprocess.CompletedProcess:
    from src.optimisation.workflow import WorkflowCancelled  # lazy import / 延迟导入，避免循环依赖

    env = os.environ.copy()
    existing_pythonpath = env.get("PYTHONPATH", "")
    project_path = str(cwd)
    env["PYTHONPATH"] = project_path if not existing_pythonpath else project_path + os.pathsep + existing_pythonpath

    # Launch in its own process group/session so a cancel can signal the whole
    # tree (this python child AND the MATLAB/COMSOL grandchild it spawns). /
    # 用独立进程组/会话启动，便于取消时一次性杀掉 python 子进程及其 MATLAB/COMSOL 孙进程
    popen_kwargs: dict[str, Any] = dict(
        cwd=str(cwd), env=env,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    if os.name == "nt":
        popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        popen_kwargs["start_new_session"] = True

    try:
        proc = subprocess.Popen(cmd, **popen_kwargs)
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"{label} could not start because the executable was not found: {cmd[0]!r}. "
            f"Full command: {' '.join(cmd)}"
        ) from exc

    cancel_check = _CANCEL_CHECK
    # Poll so a Stop click kills the child within ~_CANCEL_POLL_INTERVAL_S
    # rather than waiting for the (minutes-long) COMSOL/MATLAB call to return. /
    # 轮询：点 Stop 能在 ~_CANCEL_POLL_INTERVAL_S 内杀掉子进程，而不必等
    # 长达数分钟的 COMSOL/MATLAB 调用自己返回
    while True:
        try:
            stdout, stderr = proc.communicate(timeout=_CANCEL_POLL_INTERVAL_S)
            break
        except subprocess.TimeoutExpired:
            if cancel_check is not None and cancel_check():
                _terminate_process_tree(proc)
                try:
                    proc.communicate(timeout=5.0)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.communicate()
                raise WorkflowCancelled(f"{label} cancelled by user. / 用户已取消（{label}）。")

    res = subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr)
    if res.returncode != 0:
        tail = ("\n".join((res.stdout or "").splitlines()[-25:]) + "\n" + "\n".join((res.stderr or "").splitlines()[-25:]))[-4000:]
        raise RuntimeError(f"{label} failed (rc={res.returncode}):\n{tail}")
    return res


def _run_w10_surrogate(cfg: ProductionPipelineConfig, project_root: Path, progress=None,
                         initial_H_csv: Path | None = None,
                         candidate_id: str | None = None, num_steps: int | None = None,
                         lr_h: float | None = None,
                         freeze_freq_first_steps: int | None = None,
                         skip_health_check: bool = False) -> dict:
    """Run W10 surrogate optimisation. Returns its summary dict.

    ``freeze_freq_first_steps`` (when not None) overrides the W10 default of
    60. Useful for short Phase 2 inner iterations where 60 steps of frozen
    freqs/weights would consume almost the entire budget and leave Adam
    barely any time to update them. /
    Phase 2 短 inner-iter 用：W10 默认前 60 步冻结 freq/weight，对 P2 80~200 步
    几乎没法真正调 freq；传低值让 freq/weight 有充分优化时间
    """
    cand_id = candidate_id or cfg.candidate_id
    cmd = [
        sys.executable, "scripts/run_w10_anisotropy.py",
        "--candidate-id", cand_id,
        "--num-steps", str(int(num_steps if num_steps is not None else cfg.w10_num_steps)),
        "--learning-rate-h", f"{float(lr_h if lr_h is not None else cfg.w10_lr_h)}",
        "--num-frequencies", str(int(cfg.w10_num_frequencies)),
        "--f-min-hz", f"{float(cfg.w10_f_min_hz)}",
        "--f-max-hz", f"{float(cfg.w10_f_max_hz)}",
        "--stiffness-ratio", f"{float(cfg.stiffness_ratio)}",
        "--shear-ratio", f"{float(cfg.shear_ratio)}",
        "--target", cfg.target_path,
        "--snapshot-every", "999999",
        "--sigma-anneal-start", f"{float(cfg.w10_sigma_anneal_start)}",
        "--sigma-anneal-steps", str(int(cfg.w10_sigma_anneal_steps)),
        "--target-dilation-px", str(int(cfg.w10_target_dilation_px)),
    ]
    if initial_H_csv is not None:
        cmd.extend(["--initial-H", str(initial_H_csv)])
    if freeze_freq_first_steps is not None:
        cmd.extend(["--freeze-freq-first-steps", str(int(freeze_freq_first_steps))])
    _emit(progress, "surrogate", f"Running W10 surrogate ({int(num_steps or cfg.w10_num_steps)} steps)", candidate_id=cand_id)
    _run_subprocess(cmd, project_root, label=f"W10 surrogate ({cand_id})")
    summary_path = project_root / "candidates" / cand_id / "w10_optimization_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    # Health check: refuse to send a clearly-failed surrogate run downstream
    # to COMSOL. A surrogate enrichment < ~0.5 means the loss collapsed to
    # the epsilon floor (gradient cliff) and the design is essentially
    # random — sinking 5+ min of COMSOL on it is wasted compute. /
    # 健康度检查：W10 自评 enrichment 太低就直接拒绝下推 COMSOL
    surr = float(summary.get("best_surrogate_metrics", {}).get("enrichment", 0.0))
    threshold = float(cfg.w10_min_surrogate_enrichment)
    if (not skip_health_check) and surr < threshold:  # 失败 / Failed
        msg = (f"W10 surrogate convergence failure: best enrichment={surr:.3e} < threshold={threshold:.2f}. "
               f"Likely causes: thin/sparse target hitting the loss gradient cliff (enrichment underflowed "
               f"below 1e-9 → -log(x+eps) saturated → no gradient). Try raising --target-dilation-px or "
               f"--sigma-anneal-start. See {summary_path} for trace details. / "
               f"W10 收敛失败：surrogate enrichment 远低于阈值，多半是细线/稀疏目标触发梯度悬崖；"
               f"加大 --target-dilation-px / --sigma-anneal-start 再试")
        raise RuntimeError(msg)  # 抛错 / Raise
    return summary


def _phase2_score(best_composite: dict, mode: str = "composite") -> dict:
    """Compute the Phase 2 acceptance / "best" score from a best_composite dict.

    The default ``mode="composite"`` returns ``broad.enrich · √(max(broad.recall, 0))``.
    This rejects the dominant Phase 2 failure mode: gradient-step collapses
    the COMSOL composite to a single bright spot in the middle of the plate,
    which boosts enrichment (peak / median ratio shoots up) but kills recall
    (the target's full shape is no longer covered). With raw enrich-only
    acceptance, that collapse looks like a +50% "improvement" and beats
    Phase 1's faithful 4-pointed star; with the composite, it loses.

    Backward-compatibility: pass ``mode="enrich_only"`` to reproduce the
    pre-2026-05 behaviour. /
    Phase 2 决策分；composite 防"塌陷成中心亮点"伪赢家
    """
    broad = best_composite.get("broad", {}) or {}
    tight = best_composite.get("tight", {}) or {}
    be = float(broad.get("enrich", 0.0))
    br = float(broad.get("recall", 0.0))
    te = float(tight.get("enrich", 0.0))
    tr = float(tight.get("recall", 0.0))
    if mode == "enrich_only":
        score = be
    else:  # "composite" (default)
        score = be * (max(br, 0.0) ** 0.5)
    return {
        "score": float(score),
        "broad_enrich": be, "broad_recall": br,
        "tight_enrich": te, "tight_recall": tr,
    }


def _run_w10_multistart(cfg: ProductionPipelineConfig, project_root: Path, progress=None) -> dict:
    """Run W10 surrogate.

    Historical note: this was a multi-start wrapper that ran N seeds and
    picked a winner by composite score, with anti-regression guards. The
    seeds differed only in θ_seed — which made sense while θ was an
    optimisation variable. After θ optimisation was removed (2026-05; see
    BATTERY_FINDINGS.md), the W10 surrogate is fully deterministic for a
    given target + config, so N > 1 would just repeat the same computation.
    This now always single-starts. ``multistart_n`` / ``multistart_uplift_threshold``
    in config / CLI are still accepted for backwards compatibility but
    ignored with a one-line warning when N > 1. /
    多启动机制因 θ 移除后 surrogate 完全确定而失效；保留 API 但 N>1 时只警告
    """
    N = max(1, int(cfg.multistart_n))
    if N > 1:
        _emit(progress, "multistart_noop",
              f"multistart_n={N} requested but W10 surrogate is deterministic since "
              "θ optimisation was removed; falling back to single-start. / 多启动已无意义")
    return _run_w10_surrogate(cfg, project_root, progress=progress)


def _run_comsol_eigfreq(cfg: ProductionPipelineConfig, project_root: Path, candidate_id: str, progress=None) -> Path:
    """Run COMSOL eigenfrequency analysis. Returns eigfreq export dir."""
    eig_name = f"prod_eig_{candidate_id}"
    cmd = [
        sys.executable, "scripts/run_modal_calibration_w10design.py",
        "--source-candidate", candidate_id,
        "--candidate-name", eig_name,
        "--stiffness-ratio", f"{float(cfg.stiffness_ratio)}",
        "--shear-ratio", f"{float(cfg.shear_ratio)}",
        "--n-modes", str(int(cfg.eig_n_modes)),
    ]
    _emit(progress, "comsol_eigfreq", f"Running COMSOL eigenfrequency ({cfg.eig_n_modes} modes)")
    _run_subprocess(cmd, project_root, label=f"COMSOL eigfreq ({candidate_id})")
    return project_root / "data" / "comsol_exports" / eig_name / "eigenfrequency"


def _compute_ic_likeness_per_mode(eig_dir: Path, target: np.ndarray, image_size: int, plate_length_mm: float, n_modes: int) -> list[dict]:
    from src.scoring.recognisability_score import (
        coverage_recall,
        recognisability_score_grid,
    )
    from scripts.run_sprint2_section4_phase1 import downsample_comsol_xy_to_grid

    arr = np.loadtxt(eig_dir / "eigenfrequencies.csv", delimiter=",", skiprows=1)
    if arr.ndim == 1:
        arr = arr.reshape(-1, 2)
    n_modes = min(n_modes, len(arr))
    freqs = arr[:n_modes, 1].astype(float)
    xy = np.loadtxt(eig_dir / "mode_xy.csv", delimiter=",", skiprows=1)
    rows = []
    for k in range(1, n_modes + 1):
        try:
            m = np.loadtxt(eig_dir / f"mode_{k:03d}.csv", delimiter=",", skiprows=1)
            if m.ndim == 1:
                m = m.reshape(-1, 2)
            amp = np.sqrt(m[:, 0] ** 2 + m[:, 1] ** 2)
            grid = downsample_comsol_xy_to_grid(xy[:, 0], xy[:, 1], amp, image_size, plate_length_mm)
            if grid.max() > 1e-30:
                grid = grid / grid.max()
            s = recognisability_score_grid(grid, target.astype(bool), sigma_rel=0.05, percentile=20.0)
            r = float(coverage_recall(grid, target.astype(bool), percentile=20.0))
            rows.append({"mode": int(k), "freq_hz": float(freqs[k - 1]),
                         "enrichment": float(s["enrichment_factor"]), "recall": r,
                         "ic_score": float(s["enrichment_factor"]) * r})
        except Exception:
            rows.append({"mode": int(k), "freq_hz": float(freqs[k - 1]),
                         "enrichment": float("nan"), "recall": float("nan"), "ic_score": float("nan")})
    return rows


def _load_w10_freqs_weights(candidate_dir: Path) -> tuple[list[float], list[float]] | None:
    """Load W10-trained frequencies + weights from a candidate's summary.

    Returns (frequencies_hz, weights) or None if not available. Reads from
    w10_optimization_summary.json (preferred — has weights for ranking) and
    falls back to frequencies_hz.csv if that's missing. /
    读取候选目录里 W10 训练出来的频率+权重；优先用 summary（有权重做排序）
    """
    summary_path = candidate_dir / "w10_optimization_summary.json"
    if summary_path.exists():
        try:
            data = json.loads(summary_path.read_text(encoding="utf-8"))
            freqs = data.get("frequencies_hz") or []
            weights = data.get("weights") or [1.0 / max(len(freqs), 1)] * len(freqs)
            if freqs:
                return [float(f) for f in freqs], [float(w) for w in weights]
        except Exception:
            pass
    csv_path = candidate_dir / "frequencies_hz.csv"
    if csv_path.exists():
        try:
            arr = np.loadtxt(csv_path, delimiter=",")
            freqs = arr.flatten().tolist()
            return freqs, [1.0 / max(len(freqs), 1)] * len(freqs)
        except Exception:
            pass
    return None


def _select_phase1_drive_freqs(rows: list[dict], cfg: ProductionPipelineConfig,
                                 w10_freqs_weights: tuple[list[float], list[float]] | None = None) -> list[float]:
    """Pick COMSOL forced-response drive frequencies for Phase 1.

    Sources (in order of inclusion):
    1. Top-K in-band COMSOL eigfreqs ranked by IC-likeness (existing).
    2. Top-``cfg.phase1_w10_topn`` W10-trained frequencies ranked by their
       optimised weights (P1 fix 2026-05). W10 trained H+θ to give the target
       pattern *at these exact frequencies*; previously Phase 1 ignored them
       entirely, throwing away the surrogate's main optimisation signal.
    3. Optional magic frequencies (tier1-empirical; gated by
       ``cfg.enable_magic_freqs``).

    Dedup with 5 Hz tolerance — if a W10 freq is within 5 Hz of an already-
    selected COMSOL eigfreq, drop the W10 freq (the COMSOL one is the true
    resonance and gives stronger response). /
    Phase 1 \u9009\u9891\u6c47\u6c47\u603b\uff1aCOMSOL top-K eigfreq + W10 \u8bad\u51fa\u6765\u7684 top-N \u9891\u7387
    \uff08\u6309 W10 \u6743\u91cd\u6392\u5e8f\uff09+ \u53ef\u5173 magic\uff1b5 Hz \u5bb9\u5dee\u53bb\u91cd
    """
    rows_valid = [r for r in rows if not np.isnan(r["ic_score"])]
    slack = float(cfg.phase1_band_slack_hz)
    f_lo = float(cfg.w10_f_min_hz) - slack
    f_hi = float(cfg.w10_f_max_hz) + slack
    offband_min_enr = float(getattr(cfg, "phase1_offband_min_enrichment", 2.0))

    def _in_band(r: dict) -> bool:
        return f_lo <= float(r["freq_hz"]) <= f_hi

    # Eigenmodes eligible to become drive candidates: in-band always; an
    # out-of-band mode only if its pattern quality (enrichment) clears
    # ``offband_min_enr``. This keeps the band gate's intent (block low-freq
    # central-blob fundamentals, enr≈1) while no longer discarding genuinely
    # good low-order modes (e.g. a ~64 Hz cross mode, enr≈6) that low-symmetry
    # targets depend on. /
    # 可成为驱动候选的本征模态：带内全收；带外仅当 enrichment ≥ offband_min_enr
    # 才收。既保留挡掉低频"中心一坨"基频（enr≈1）的本意，又不再误杀十字/叉这类
    # 低对称目标依赖的优质低阶模态（如 ~64Hz 十字模态 enr≈6）
    eligible: list[dict] = []
    admitted_offband: list[dict] = []
    for r in rows_valid:
        if _in_band(r):
            eligible.append(r)
        elif float(r.get("enrichment", 0.0)) >= offband_min_enr:
            eligible.append(r)
            admitted_offband.append(r)

    if not eligible and rows_valid:
        # Defensive fallback: should not happen with eig_n_modes >= 30 covering
        # the W10 band, but if it does, fall through to the legacy behaviour
        # with a loud warning so the user can investigate. /
        # 防御：30 阶 eigfreq 几乎不可能完全错过 W10 带宽；若发生则回退到全集并告警
        seen = sorted({round(float(r["freq_hz"]), 1) for r in rows_valid})
        print(f"[Phase 1] WARNING: no eligible eigenmodes (band [{f_lo:.0f},{f_hi:.0f}] Hz, "
              f"off-band enr≥{offband_min_enr}); falling back to full mode list. Eigenfreqs seen: {seen}")
        eligible = rows_valid
    else:
        if admitted_offband:
            adm = sorted({round(float(r["freq_hz"]), 1) for r in admitted_offband})
            print(f"[Phase 1] admitting {len(adm)} high-enrichment out-of-band eigenmode(s) "
                  f"(enr≥{offband_min_enr}): {adm}")
        rejected = sorted({round(float(r["freq_hz"]), 1) for r in rows_valid if r not in eligible})
        if rejected:
            print(f"[Phase 1] rejecting {len(rejected)} low-quality out-of-band eigenmode(s): "
                  f"{rejected[:6]}{'…' if len(rejected) > 6 else ''}")

    eligible.sort(key=lambda r: -r["ic_score"])
    top_rows = eligible[:cfg.phase1_top_k_modes]
    drive = [r["freq_hz"] + cfg.phase1_off_resonance_hz for r in top_rows]

    # P1 bridge: add W10-trained frequencies (top-N by weight). /
    # P1 桥接：把 W10 训练频率（按权重排）的 top-N 加进来
    if w10_freqs_weights is not None and int(cfg.phase1_w10_topn) > 0:
        w10_freqs, w10_weights = w10_freqs_weights
        if w10_freqs:
            ranked = sorted(zip(w10_freqs, w10_weights), key=lambda fw: -fw[1])
            top_n = ranked[:int(cfg.phase1_w10_topn)]
            added = []
            for f_w10, w_w10 in top_n:
                if not (f_lo <= float(f_w10) <= f_hi):
                    continue
                # Dedup vs already-selected drive freqs with 5 Hz tolerance
                f_drive = float(f_w10) + float(cfg.phase1_off_resonance_hz)
                if any(abs(f_drive - existing) < 5.0 for existing in drive):
                    continue
                drive.append(f_drive)
                added.append((float(f_w10), float(w_w10)))
            if added:
                summary_str = ", ".join(f"{f:.1f}Hz(w={w:.2f})" for f, w in added)
                print(f"[Phase 1] adding {len(added)} W10-trained drive freqs: {summary_str}")
            else:
                print(f"[Phase 1] no W10 freqs added (all out-of-band or within 5 Hz of selected eigfreqs)")

    # Magic frequencies (tier1-empirical). Gated by enable_magic_freqs. /
    # Magic 频率（tier1 经验值）；可关
    if bool(cfg.enable_magic_freqs) and cfg.magic_off_resonance_hz:
        if abs(float(cfg.stiffness_ratio) - 3.0) > 0.5:
            # tier1 magic was calibrated at sr=3.0; warn if user is using
            # a different anisotropy ratio so they can disable. /
            # magic 是 tier1 sr=3.0 经验值；其他 sr 提示用户考虑关闭
            print(f"[Phase 1] WARNING: enable_magic_freqs=True but stiffness_ratio={cfg.stiffness_ratio:.2f} "
                  f"differs from tier1 (sr=3.0); magic freqs {list(cfg.magic_off_resonance_hz)} may not apply. "
                  f"Consider config production.enable_magic_freqs: false")
        drive.extend(cfg.magic_off_resonance_hz)

    drive = list(dict.fromkeys(round(f, 1) for f in drive))
    return drive


def _run_comsol_forced_response(cfg: ProductionPipelineConfig, project_root: Path, candidate_id: str,
                                  freqs_hz: list[float], variant_prefix: str, progress=None) -> list[Path]:
    fstr = ",".join(f"{f:.1f}" for f in freqs_hz)
    output_dir = f"reports/production/_comsol_{variant_prefix}"
    cmd = [
        sys.executable, "scripts/run_w10_comsol_validation.py",
        "--candidate", candidate_id,
        "--stiffness-ratio", f"{float(cfg.stiffness_ratio)}",
        "--shear-ratio", f"{float(cfg.shear_ratio)}",
        "--frequencies", fstr,
        "--top-n", str(len(freqs_hz)),
        "--variant-prefix", variant_prefix,
        "--material-mode", "orthotropic_shell",
        "--output-dir", output_dir,
    ]
    _emit(progress, "comsol_forced", f"Running COMSOL forced response at {len(freqs_hz)} freqs", freqs=freqs_hz)
    _run_subprocess(cmd, project_root, label=f"COMSOL forced response ({candidate_id})")
    csv_paths = []
    for f in freqs_hz:
        vid = f"{variant_prefix}_{candidate_id}_comsol_f{f:.1f}Hz".replace(".", "p")
        csv_paths.append(project_root / "data" / "comsol_exports" / vid / "forced_response" / "forced_response.csv")
    return csv_paths


def _load_amp_csv(csv_path: Path, image_size: int, plate_length_mm: float) -> np.ndarray:
    from scripts.run_sprint2_section4_phase1 import downsample_comsol_xy_to_grid

    arr = np.loadtxt(csv_path, delimiter=",", skiprows=1)
    if arr.shape[1] >= 4:
        amp = np.sqrt(arr[:, 2] ** 2 + arr[:, 3] ** 2)
    else:
        amp = np.abs(arr[:, 2])
    grid = downsample_comsol_xy_to_grid(arr[:, 0], arr[:, 1], amp, image_size, plate_length_mm)
    if grid.max() > 1e-30:
        grid = grid / grid.max()
    return grid


def _composite(amps: list[np.ndarray], method: str) -> np.ndarray:
    stack = np.stack(amps, axis=0)
    if method == "RMS":
        c = np.sqrt(np.mean(stack ** 2, axis=0))
    elif method == "MAX":
        c = np.max(stack, axis=0)
    else:
        c = np.sum(stack, axis=0)
    if c.max() > 1e-30:
        c = c / c.max()
    return c


def _score_amp(amp: np.ndarray, target: np.ndarray) -> dict:
    """Score a forced-response amplitude grid against the target binary.

    NOTE on metric alignment (P1 fix 2026-05): broad sigma_rel=0.05 and
    percentile=20 MUST match W10's final training values
    (recognisability_placement_w10.W10AnisotropyConfig.sigma_rel = 0.05 and
    recall_percentile_frac = 0.20) so that W10's self-reported surrogate
    enrichment is on the same scale as the Phase 1 broad enrich reported
    here. If the W10 defaults move, update these too. /
    broad 分数与 W10 训练 metric 必须对齐（sigma_rel=0.05, percentile=20）
    才能让 W10 surrogate enrichment 和 Phase 1 broad enrich 可比
    """
    from src.scoring.recognisability_score import coverage_recall, recognisability_score_grid

    sb = recognisability_score_grid(amp, target.astype(bool), sigma_rel=0.05, percentile=20.0)
    rb = float(coverage_recall(amp, target.astype(bool), percentile=20.0))
    st = recognisability_score_grid(amp, target.astype(bool), sigma_rel=0.012, percentile=92.0)
    rt = float(coverage_recall(amp, target.astype(bool), percentile=92.0))
    return {
        "broad": {"enrich": float(sb["enrichment_factor"]), "recall": rb,
                  "contrast": float(sb["gaussian_contrast"])},
        "tight": {"enrich": float(st["enrichment_factor"]), "recall": rt,
                  "contrast": float(st["gaussian_contrast"])},
    }


def _exhaustive_composite_search(amps: dict[str, np.ndarray], target: np.ndarray, max_k: int = 3) -> list[dict]:
    labels = list(amps.keys())
    records = []
    for k in range(1, max_k + 1):
        for sub in itertools.combinations(labels, k):
            for method in ["RMS", "MAX", "SUM"]:
                c = _composite([amps[l] for l in sub], method)
                s = _score_amp(c, target)
                records.append({"subset": list(sub), "method": method, **s})
    records.sort(key=lambda r: -r["broad"]["enrich"])
    return records


def _evaluate_design(cfg: ProductionPipelineConfig, project_root: Path, candidate_id: str,
                       variant_prefix: str, target: np.ndarray, plate_length_mm: float, progress=None) -> dict:
    """Run COMSOL eigfreq + Phase 1 + forced response + composite search for a candidate."""
    eig_dir = _run_comsol_eigfreq(cfg, project_root, candidate_id, progress=progress)
    rows = _compute_ic_likeness_per_mode(eig_dir, target, cfg.image_size, plate_length_mm, cfg.eig_n_modes)
    w10_fw = _load_w10_freqs_weights(project_root / "candidates" / candidate_id)  # P1 bridge / P1 桥接
    drive_freqs = _select_phase1_drive_freqs(rows, cfg, w10_freqs_weights=w10_fw)
    csvs = _run_comsol_forced_response(cfg, project_root, candidate_id, drive_freqs, variant_prefix, progress=progress)
    amps = {}
    for f, p in zip(drive_freqs, csvs):
        if p.exists():
            amps[f"{f:.0f}"] = _load_amp_csv(p, cfg.image_size, plate_length_mm)

    if not amps:
        raise RuntimeError(f"No forced-response CSVs found for {candidate_id}")

    per_freq = {}
    for label, amp in amps.items():
        per_freq[label] = _score_amp(amp, target)

    records = _exhaustive_composite_search(amps, target, max_k=3)
    best = records[0]
    best_amp = _composite([amps[l] for l in best["subset"]], best["method"])

    # Best SINGLE drive frequency. The MAX/SUM/RMS composite maximises broad
    # enrichment, which rewards a compact high-contrast central blob and tends
    # to smear distinct single-frequency figures (e.g. a clean cross at one
    # eigenfrequency) into that blob. A single pure tone usually preserves the
    # recognisable nodal figure, so we surface it alongside the composite.
    # Ranked by IC-likeness (broad enrich × broad recall) rather than pure
    # enrichment so a full-coverage cross beats a tiny over-concentrated dot. /
    # 最佳"单频"驱动：MAX/SUM/RMS 合成最大化 broad 富集，会偏向中心一坨、把单频
    # 本来干净的图案（如某个本征频率上的十字）糊掉。单一纯音通常能保住可辨认的
    # 节线图案，故与合成图并列展示。按 IC-likeness(broad 富集×召回)排序而非纯富集，
    # 让覆盖完整的十字胜过过度集中的小亮点
    singles = [r for r in records if len(r["subset"]) == 1]
    best_single = None
    best_single_amp = None
    if singles:
        best_single = max(singles, key=lambda r: r["broad"]["enrich"] * r["broad"]["recall"])
        best_single_amp = amps[best_single["subset"][0]]

    return {
        "candidate_id": candidate_id,
        "eig_dir": str(eig_dir),
        "top_modes": sorted([r for r in rows if not np.isnan(r["ic_score"])], key=lambda r: -r["ic_score"])[:cfg.phase1_top_k_modes],
        "drive_freqs": drive_freqs,
        "w10_freqs_weights": ({"frequencies_hz": list(w10_fw[0]), "weights": list(w10_fw[1])} if w10_fw is not None else None),
        "per_freq": per_freq,
        "best_composite": best,
        "best_composite_amp": best_amp,
        "best_single": best_single,
        "best_single_amp": best_single_amp,
        "single_freq_amps": amps,
        "top10_composites": [{k: v for k, v in r.items() if k != "best_composite_amp"} for r in records[:10]],
    }


def _save_single_freq_gallery(amps: dict[str, np.ndarray], target: np.ndarray,
                                per_freq: dict, composite_amp: np.ndarray, out_png: Path) -> None:
    """Save a browsable gallery of every single-frequency powder figure plus the
    composite, next to the target.

    Rationale: no scalar score (enrichment / recall / IoU) reliably picks the
    *most recognisable* figure — a compact central blob always out-scores a
    spread-out cross. So instead of trusting a metric, we lay out all single
    frequencies for the human eye to pick the recognisable one. /
    存一张可浏览的图廊：所有单频 powder + 合成 + 目标。没有任何标量分数能可靠选出
    "最像目标"的图（中心一坨总比铺开的十字分高），故全摆出来让人眼挑
    """
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return
    items = sorted(amps.items(), key=lambda kv: float(kv[0]))
    n = len(items) + 2  # + target + composite
    cols = 4
    rows = (n + cols - 1) // cols
    fig, ax = plt.subplots(rows, cols, figsize=(cols * 3.0, rows * 3.0))
    ax = np.atleast_1d(ax).ravel()
    ax[0].imshow(target.astype(float), cmap="gray_r"); ax[0].set_title("TARGET"); ax[0].axis("off")
    cpw = (composite_amp <= np.percentile(composite_amp, 12)).astype(float)
    ax[1].imshow(cpw, cmap="gray_r"); ax[1].set_title("MAX composite"); ax[1].axis("off")
    for i, (label, amp) in enumerate(items):
        pw = (amp <= np.percentile(amp, 12)).astype(float)
        b = per_freq.get(label, {}).get("broad", {})
        title = f"{label}Hz"
        if b:
            title += f"\nenr={b.get('enrich', 0):.1f} rec={b.get('recall', 0):.2f}"
        ax[i + 2].imshow(pw, cmap="gray_r"); ax[i + 2].set_title(title, fontsize=8); ax[i + 2].axis("off")
    for j in range(n, len(ax)):
        ax[j].axis("off")
    fig.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=85)
    plt.close(fig)


def _to_native(o: Any) -> Any:
    if isinstance(o, dict):
        return {k: _to_native(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_to_native(v) for v in o]
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.floating):
        return float(o)
    return o


def run_production_pipeline(cfg: ProductionPipelineConfig, project_root: Path | None = None,
                              progress: Callable[[dict], None] | None = None,
                              cancel_check: Callable[[], bool] | None = None) -> dict:
    """End-to-end inverse design pipeline. Returns deliverables dict.

    ``cancel_check`` (optional) is polled by the heavy COMSOL/MATLAB
    subprocess launcher so a UI Stop click can kill the running child
    promptly instead of waiting for the current stage to finish. /
    ``cancel_check`` 由重型 COMSOL/MATLAB 子进程启动器轮询，使 UI 点 Stop
    能及时杀掉正在跑的子进程，而非等当前阶段跑完。
    """
    project_root = project_root or PROJECT_ROOT
    global _CANCEL_CHECK
    _CANCEL_CHECK = cancel_check  # install for _run_subprocess; next run overwrites / 注入供 _run_subprocess 使用，下次运行会覆盖
    from src.config import load_config

    config = load_config(str(project_root / "config.yaml"))
    plate_length_mm = float(config["project"]["plate_length_mm"])

    output_dir = project_root / cfg.output_dir / cfg.candidate_id
    output_dir.mkdir(parents=True, exist_ok=True)

    _emit(progress, "start", f"Pipeline start (sr={cfg.stiffness_ratio}, candidate={cfg.candidate_id})")

    # === S1: Load target ===
    target_path = project_root / cfg.target_path
    if not target_path.exists():
        raise FileNotFoundError(f"Target not found at {target_path}; run prepare-target first.")
    target_bin = np.load(target_path).astype(bool)
    if target_bin.shape != (cfg.image_size, cfg.image_size):
        from PIL import Image
        timg = Image.fromarray(target_bin.astype(np.uint8) * 255).resize((cfg.image_size, cfg.image_size), Image.NEAREST)
        target = np.array(timg) > 127
    else:
        target = target_bin
    np.save(output_dir / "target_resized.npy", target)
    _emit(progress, "target", f"Target loaded ({int(target.sum())} pixels)")

    # === S2: W10 surrogate (single-start or multi-start with anti-regression decision) ===
    _emit(progress, "surrogate_start",
          f"Running W10 surrogate ({'multi-start ×%d' % cfg.multistart_n if cfg.multistart_n > 1 else 'single-start'})")
    t0 = time.time()
    w10_summary = _run_w10_multistart(cfg, project_root, progress=progress)
    elapsed_surr = time.time() - t0
    surr_metrics = w10_summary.get("best_surrogate_metrics", {})
    _emit(progress, "surrogate_done", f"W10 done in {elapsed_surr:.0f}s; surrogate enr={surr_metrics.get('enrichment', 0):.2f}×",
          surrogate_metrics=surr_metrics)

    # Copy initial H+θ into output dir
    cand_dir = project_root / "candidates" / cfg.candidate_id
    for fname in ["H.csv", "theta_continuous_rad.csv", "theta_continuous_deg.csv",
                  "frequencies_hz.csv", "weights.csv", "w10_optimization_summary.json"]:
        src_file = cand_dir / fname
        if src_file.exists():
            shutil.copy2(src_file, output_dir / fname)

    if cfg.skip_comsol:
        result = {
            "candidate_id": cfg.candidate_id,
            "output_dir": str(output_dir),
            "stage_reached": "surrogate_only",
            "stiffness_ratio": cfg.stiffness_ratio,
            "shear_ratio": cfg.shear_ratio,
            "surrogate_metrics": surr_metrics,
            "w10_summary": w10_summary,
        }
        summary_path = output_dir / "production_summary.json"
        summary_path.write_text(json.dumps(_to_native(result), indent=2, ensure_ascii=False), encoding="utf-8")
        result["summary_path"] = str(summary_path)
        _emit(progress, "done", "Surrogate-only mode (skip_comsol=True); done.", summary_path=str(summary_path))
        return result

    # === S3-S6: Phase 1 evaluation on initial design ===
    _emit(progress, "phase1_start", "Phase 1: COMSOL eigfreq + Phase 1 selection + forced response + composite search")
    t1 = time.time()
    p1_result = _evaluate_design(cfg, project_root, cfg.candidate_id,
                                    variant_prefix="prodp1", target=target,
                                    plate_length_mm=plate_length_mm, progress=progress)
    elapsed_p1 = time.time() - t1
    _emit(progress, "phase1_done",
          f"Phase 1 done in {elapsed_p1:.0f}s; best composite = {p1_result['best_composite']['broad']['enrich']:.2f}× broad",
          best_composite=p1_result["best_composite"])

    # Save Phase 1 deliverables
    np.save(output_dir / "phase1_best_composite_amp.npy", p1_result["best_composite_amp"])
    from src.scoring.recognisability_score import chladni_powder_density
    np.save(output_dir / "phase1_best_powder_broad.npy", chladni_powder_density(p1_result["best_composite_amp"], sigma_rel=0.05))
    np.save(output_dir / "phase1_best_powder_sharp.npy", chladni_powder_density(p1_result["best_composite_amp"], sigma_rel=0.025))
    # Best single-frequency figure (heuristic pick; see gallery for the full
    # set — a single scalar can't reliably identify the most recognisable one). /
    # 最佳单频图（启发式挑选；可靠判断请看图廊——单一标量分数选不准最可辨认的那张）
    if p1_result.get("best_single_amp") is not None:
        bs_amp = p1_result["best_single_amp"]
        np.save(output_dir / "phase1_best_single_amp.npy", bs_amp)
        np.save(output_dir / "phase1_best_single_powder_broad.npy", chladni_powder_density(bs_amp, sigma_rel=0.05))
        np.save(output_dir / "phase1_best_single_powder_sharp.npy", chladni_powder_density(bs_amp, sigma_rel=0.025))
        bs = p1_result["best_single"]
        _emit(progress, "phase1_best_single",
              f"Best single drive (heuristic) {bs['subset'][0]}Hz: broad enr={bs['broad']['enrich']:.2f}× rec={bs['broad']['recall']:.2f}; "
              f"see phase1_single_freq_gallery.png to eyeball all single tones",
              best_single=bs)

    # Browsable gallery of all single-frequency figures (metric-free; for eyes). /
    # 全部单频图廊（不靠指标，给人眼挑）
    try:
        _save_single_freq_gallery(
            p1_result.get("single_freq_amps", {}), target, p1_result.get("per_freq", {}),
            p1_result["best_composite_amp"], output_dir / "phase1_single_freq_gallery.png")
    except Exception as exc:
        print(f"[Phase 1] gallery render skipped: {exc}")

    final = {
        "candidate_id": cfg.candidate_id,
        "output_dir": str(output_dir),
        "stiffness_ratio": cfg.stiffness_ratio,
        "shear_ratio": cfg.shear_ratio,
        "stage_reached": "phase1",
        "surrogate_metrics": surr_metrics,
        "phase1": {k: v for k, v in p1_result.items()
                   if k not in ("best_composite_amp", "best_single_amp", "single_freq_amps")},
        "wallclock_seconds": {"surrogate": elapsed_surr, "phase1": elapsed_p1},
    }

    # === S7: Phase 2 trust-region (optional) ===
    # Acceptance / best-tracking uses the composite Phase-2 score
    # (enrich · √recall) by default — see ``_phase2_score`` docstring and
    # ``cfg.phase2_score_mode``. /
    # 接受 / best 追踪默认用复合分；防 "塌陷成中心亮点" 伪赢家
    if not cfg.skip_phase2 and cfg.phase2_max_iters > 0:
        _emit(progress, "phase2_start",
              f"Phase 2 trust-region ({cfg.phase2_max_iters} iters, score_mode={cfg.phase2_score_mode})")
        score_mode = str(cfg.phase2_score_mode)
        history = [{
            "iter": 0, "candidate_id": cfg.candidate_id,
            "best_composite": p1_result["best_composite"],
            "score": _phase2_score(p1_result["best_composite"], score_mode),
            "accepted": True,
        }]
        best_score_obj = history[0]["score"]
        best_score = float(best_score_obj["score"])
        best_iter = 0
        best_amp = p1_result["best_composite_amp"]

        lr_h = cfg.phase2_lr_h_init
        cur_H = cand_dir / "H.csv"

        for it in range(1, cfg.phase2_max_iters + 1):
            t2 = time.time()
            iter_cand = f"{cfg.candidate_id}_p2it{it}"
            old = project_root / "candidates" / iter_cand
            if old.exists():
                shutil.rmtree(old)
            _emit(progress, "phase2_iter_start", f"iter {it}/{cfg.phase2_max_iters}: surrogate continue (lr_H={lr_h:.4f}, freeze_freq={cfg.phase2_freeze_freq_first_steps})", iter=it)
            _run_w10_surrogate(cfg, project_root, progress=progress,
                                initial_H_csv=cur_H,
                                candidate_id=iter_cand, num_steps=cfg.phase2_inner_steps,
                                lr_h=lr_h,
                                freeze_freq_first_steps=cfg.phase2_freeze_freq_first_steps)
            res = _evaluate_design(cfg, project_root, iter_cand,
                                     variant_prefix=f"prodp2it{it}", target=target,
                                     plate_length_mm=plate_length_mm, progress=progress)
            new_score_obj = _phase2_score(res["best_composite"], score_mode)
            prev_score_obj = history[-1]["score"]
            new_score = float(new_score_obj["score"])
            prev_score = float(prev_score_obj["score"])
            delta = new_score - prev_score
            accepted = delta > 0
            if delta > 0.10:
                lr_h *= 1.3
            elif delta <= 0:
                lr_h *= 0.5
            history.append({"iter": it, "candidate_id": iter_cand,
                            "best_composite": res["best_composite"],
                            "score": new_score_obj,
                            "delta": float(delta),
                            "accepted": bool(accepted),
                            "wallclock_s": float(time.time() - t2)})
            if accepted:
                cur_H = project_root / "candidates" / iter_cand / "H.csv"
                if new_score > best_score:
                    best_score = new_score
                    best_score_obj = new_score_obj
                    best_iter = it
                    best_amp = res["best_composite_amp"]
            _emit(progress, "phase2_iter_done",
                  (f"iter {it}: score {prev_score:.3f}→{new_score:.3f}  "
                   f"(enr {prev_score_obj['broad_enrich']:.2f}→{new_score_obj['broad_enrich']:.2f}×, "
                   f"rec {prev_score_obj['broad_recall']:.2f}→{new_score_obj['broad_recall']:.2f})  "
                   f"[{'ACCEPT' if accepted else 'REJECT'}]"),
                  iter=it, delta=delta, accepted=accepted,
                  prev_score=prev_score, new_score=new_score,
                  prev_enrich=prev_score_obj['broad_enrich'], new_enrich=new_score_obj['broad_enrich'],
                  prev_recall=prev_score_obj['broad_recall'], new_recall=new_score_obj['broad_recall'])
            if lr_h < 0.005:
                break

        np.save(output_dir / "phase2_best_composite_amp.npy", best_amp)
        np.save(output_dir / "phase2_best_powder_broad.npy", chladni_powder_density(best_amp, sigma_rel=0.05))
        np.save(output_dir / "phase2_best_powder_sharp.npy", chladni_powder_density(best_amp, sigma_rel=0.025))

        baseline_score = float(history[0]["score"]["score"])
        improvement_pct = float((best_score - baseline_score) / max(baseline_score, 1e-9) * 100)
        final["stage_reached"] = "phase2"
        final["phase2"] = {
            "history": history,
            "score_mode": score_mode,
            "best_iter": int(best_iter),
            "best_score": float(best_score),
            "best_enrichment": float(best_score_obj["broad_enrich"]),
            "best_recall": float(best_score_obj["broad_recall"]),
            "baseline_score": baseline_score,
            "improvement_pct": improvement_pct,
        }

    # === S7.5: W10 → COMSOL gap monitor ===
    # Compare W10's self-reported surrogate enrichment vs what the COMSOL
    # forced response actually achieves on the same H+θ. A large gap means
    # the surrogate (orthotropic Kirchhoff plate, 25x25 proxy) is mis-
    # estimating the real plate physics, and W10 is optimising for an
    # imaginary objective. /
    # W10 自评 enrichment vs COMSOL Phase 1 实测 broad enrich 的差距监控
    surr_enr = float(surr_metrics.get("enrichment", 0.0))
    p1_enr = float(p1_result["best_composite"]["broad"]["enrich"])
    p2_enr = float(final.get("phase2", {}).get("best_enrichment", p1_enr))
    final_comsol_enr = max(p1_enr, p2_enr)
    gap_abs = float(surr_enr - final_comsol_enr)
    gap_rel = float(gap_abs / max(surr_enr, 1.0e-9))
    gap_status = "ok"
    if surr_enr >= 1.5 and gap_rel > 0.7:  # surrogate predicted >>1, COMSOL got <30% → big gap
        gap_status = "large_surrogate_overestimate"
    elif final_comsol_enr > surr_enr * 1.5 and surr_enr > 0.5:  # COMSOL beat surrogate by 1.5x (pleasant surprise; possibly target dilation effect)
        gap_status = "comsol_outperformed_surrogate"
    final["w10_comsol_gap"] = {
        "surrogate_enrichment": surr_enr,
        "comsol_final_enrichment": final_comsol_enr,
        "gap_absolute": gap_abs,
        "gap_relative": gap_rel,
        "status": gap_status,
    }
    if gap_status == "large_surrogate_overestimate":
        msg = (f"[gap monitor] W10 surrogate predicted {surr_enr:.2f}× but COMSOL achieved only "
               f"{final_comsol_enr:.2f}× (gap {gap_rel*100:.0f}%). Surrogate is over-promising; "
               f"consider lowering --target-dilation-px or tightening --sigma-anneal-end to make "
               f"the surrogate train against a harder objective. / "
               f"surrogate 与 COMSOL gap 过大，建议降低 dilation 或收紧 sigma-anneal-end")
        print(msg)
        _emit(progress, "gap_warning", msg)
    elif gap_status == "comsol_outperformed_surrogate":
        print(f"[gap monitor] COMSOL ({final_comsol_enr:.2f}×) outperformed surrogate ({surr_enr:.2f}×) — "
              f"unusual but harmless; usually means target dilation gave the surrogate a softer goal "
              f"than the real physics could deliver.")

    # === S8: Final summary JSON ===
    summary_path = output_dir / "production_summary.json"
    summary_path.write_text(json.dumps(_to_native(final), indent=2, ensure_ascii=False), encoding="utf-8")
    _emit(progress, "done", f"Pipeline complete. Best enrichment = {final.get('phase2', {}).get('best_enrichment', p1_result['best_composite']['broad']['enrich']):.2f}×",
          summary_path=str(summary_path))
    final["summary_path"] = str(summary_path)
    return final
