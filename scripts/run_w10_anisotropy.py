"""W10 CLI — joint H + ω optimisation on orthotropic plate.
W10 命令行入口：H + ω 在正交各向异性 Kirchhoff 板上的联合优化（θ 已撤）。

Per the 2026-05 battery (`reports/_battery/BATTERY_FINDINGS.md`), per-cell θ
optimisation was a parasitic dimension under this surrogate and has been
removed. The plate remains orthotropic (sr / gr from config) but the
principal axis is fixed to global x in every cell. /
θ 优化已从 W10 撤掉；板仍是正交各向异性（sr/gr 生效）但每格主轴对齐 x。
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


# === Cross-platform determinism: pin BLAS / OMP threads to 1 BEFORE numpy /
# torch are imported. PyTorch on Windows (Intel MKL) and macOS (Accelerate /
# Apple-built MKL) reorder float accumulation differently across threads, so
# the *same* seed on two machines diverges to different local minima after a
# few hundred Adam steps. Forcing single-thread BLAS keeps Adam state
# (numerically) close enough across platforms that the COMSOL forced-response
# downstream lands on the same composite. Users who want max throughput can
# override with --torch-num-threads. /
# 跨平台确定性：在 numpy/torch 导入前钉死单线程 BLAS。
_DEFAULT_TORCH_THREADS = int(os.environ.get("W10_TORCH_NUM_THREADS", "1"))
for _env_name in ("OMP_NUM_THREADS", "MKL_NUM_THREADS",
                   "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS",
                   "VECLIB_MAXIMUM_THREADS"):
    os.environ.setdefault(_env_name, str(_DEFAULT_TORCH_THREADS))

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.run_w3_optimization import derive_candidate_dir
from scripts.run_w3_optimization import load_initial_H
from scripts.run_w3_optimization import load_verdict
from src.config import load_config
from src.optimisation.recognisability_placement_w10 import W10AnisotropyConfig
from src.optimisation.recognisability_placement_w10 import run_w10_anisotropy_placement
from src.physics.plate_loss_adapter import load_target_binary


def parse_floats(text: str) -> list[float]:
    return [float(x.strip()) for x in text.split(",") if x.strip()]


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run W10 joint optimisation (H + omega on orthotropic Kirchhoff plate; theta optimisation removed in 2026-05). / 运行 W10 联合优化（H + omega）。")
    parser.add_argument("--config", type=str, default="config.yaml", help="Project config. / 项目配置。")
    parser.add_argument("--target", type=str, default=None, help="Target NPY override. / 目标 NPY 覆盖。")
    parser.add_argument("--verdict-report", type=str, default=None, help="Optional verdict report. / 可选判定报告。")
    parser.add_argument("--candidate-id", type=str, default="w10_anisotropy_v1", help="Output candidate id. / 候选编号。")
    parser.add_argument("--num-frequencies", type=int, default=6, help="Joint frequencies K. / 联合频率数 K。")
    parser.add_argument("--f-min-hz", type=float, default=120.0, help="Freq lower bound. / 频率下限。")
    parser.add_argument("--f-max-hz", type=float, default=1200.0, help="Freq upper bound. / 频率上限。")
    parser.add_argument("--initial-frequencies-hz", type=str, default=None, help="Comma-separated initial freqs. / 初始频率。")
    parser.add_argument("--proxy-grid-size", type=int, default=25, help="Proxy grid. / 代理网格。")
    parser.add_argument("--damping-ratio", type=float, default=0.02, help="Damping. / 阻尼比。")
    parser.add_argument("--num-steps", type=int, default=300, help="Adam steps. / Adam 步数。")
    parser.add_argument("--learning-rate-h", type=float, default=0.05, help="H LR. / H 学习率。")
    parser.add_argument("--learning-rate-freq", type=float, default=0.10, help="Freq logits LR. / 频率学习率。")
    parser.add_argument("--learning-rate-weight", type=float, default=0.10, help="Weight logits LR. / 权重学习率。")
    parser.add_argument("--enrichment-weight", type=float, default=1.0, help="Enrichment weight. / 富集权重。")
    parser.add_argument("--contrast-weight", type=float, default=1.0, help="Contrast weight. / 对比权重。")
    parser.add_argument("--recall-weight", type=float, default=1.5, help="Recall weight (default raised from 0.5 to 1.5 for thin/4-fold targets). / Recall 权重")
    parser.add_argument("--weight-entropy-weight", type=float, default=0.10, help="Coefficient for -lambda*H(softmax(weights)); prevents W10 weight collapse. / 权重熵正则")
    parser.add_argument("--sigma-rel", type=float, default=0.05, help="Gaussian sigma. / 高斯 sigma。")
    parser.add_argument("--recall-percentile-frac", type=float, default=0.20, help="Recall percentile. / Recall 分位。")
    parser.add_argument("--smoothness-weight", type=float, default=4.0, help="H smoothness weight. / H 平滑罚权重。")
    parser.add_argument("--freq-separation-min-hz", type=float, default=30.0, help="Min freq gap. / 频率间隔下限。")
    parser.add_argument("--freq-separation-weight", type=float, default=0.5, help="Freq separation weight. / 间隔罚权重。")
    parser.add_argument("--freeze-freq-first-steps", type=int, default=60, help="Freeze freq/weight first N. / 冻结步数。")
    parser.add_argument("--plateau-patience", type=int, default=80, help="Plateau patience. / 平台容忍。")
    parser.add_argument("--snapshot-every", type=int, default=25, help="Snapshot interval. / 快照间隔。")
    parser.add_argument("--initial-H", type=str, default=None, help="Initial 15x15 H mm. / H 初值。")
    parser.add_argument("--h-init-mm", type=float, default=None, help="W10 H init thickness (uniform). None = (h_min+h_max)/2 mid-range. / W10 H 初值厚度")
    parser.add_argument("--output-dir", type=str, default=None, help="Override output dir. / 覆盖输出目录。")
    parser.add_argument("--sinkhorn-weight", type=float, default=0.0, help="Sinkhorn weight. / Sinkhorn 权重。")
    parser.add_argument("--sinkhorn-epsilon", type=float, default=0.01, help="Sinkhorn epsilon. / Sinkhorn epsilon。")
    parser.add_argument("--sinkhorn-target-irreps", type=str, default=None, help="Comma-separated irreps. / irrep 列表。")
    parser.add_argument("--stiffness-ratio", type=float, default=None, help="Override stiffness ratio E_par/E_perp. / 覆盖各向异性比。")
    parser.add_argument("--shear-ratio", type=float, default=None, help="Override shear ratio G/G_iso. / 覆盖剪切比。")
    parser.add_argument("--torch-num-threads", type=int, default=_DEFAULT_TORCH_THREADS, help="torch.set_num_threads value (default 1 for Win/Mac reproducibility). / torch 线程数")
    parser.add_argument("--sigma-anneal-start", type=float, default=None, help="Initial sigma_rel for powder loss; linearly shrinks to --sigma-rel. None disables. / sigma 退火起点")
    parser.add_argument("--sigma-anneal-steps", type=int, default=100, help="Sigma anneal steps. / Sigma 退火步数")
    parser.add_argument("--target-dilation-px", type=int, default=0, help="Pixels of binary dilation applied to the proxy-grid target mask. / 目标膨胀像素数")
    return parser


def main(argv: list[str] | None = None) -> int:
    import torch
    parser = build_argument_parser()
    args = parser.parse_args(argv)
    torch.set_num_threads(max(1, int(args.torch_num_threads)))
    config = load_config(args.config)
    target = load_target_binary(config, args.target)
    verdict = load_verdict(Path(args.verdict_report) if args.verdict_report else None)
    candidate_dir = derive_candidate_dir(config, args.candidate_id)
    output_dir = Path(args.output_dir) if args.output_dir else candidate_dir
    initial_H = load_initial_H(Path(args.initial_H)) if args.initial_H else None
    initial_freqs = parse_floats(args.initial_frequencies_hz) if args.initial_frequencies_hz else None
    sinkhorn_irreps = [s.strip() for s in args.sinkhorn_target_irreps.split(",")] if args.sinkhorn_target_irreps else None

    opt_config = W10AnisotropyConfig(
        proxy_grid_size=int(args.proxy_grid_size),
        num_frequencies=int(args.num_frequencies),
        f_min_hz=float(args.f_min_hz),
        f_max_hz=float(args.f_max_hz),
        damping_ratio=float(args.damping_ratio),
        num_steps=int(args.num_steps),
        learning_rate_H=float(args.learning_rate_h),
        learning_rate_freq=float(args.learning_rate_freq),
        learning_rate_weight=float(args.learning_rate_weight),
        plateau_patience=int(args.plateau_patience),
        snapshot_every=int(args.snapshot_every),
        smoothness_weight=float(args.smoothness_weight),
        freq_separation_min_hz=float(args.freq_separation_min_hz),
        freq_separation_weight=float(args.freq_separation_weight),
        freeze_freq_first_steps=int(args.freeze_freq_first_steps),
        initial_frequencies_hz=initial_freqs,
        enrichment_weight=float(args.enrichment_weight),
        contrast_weight=float(args.contrast_weight),
        recall_weight=float(args.recall_weight),
        weight_entropy_weight=float(args.weight_entropy_weight),
        sigma_rel=float(args.sigma_rel),
        recall_percentile_frac=float(args.recall_percentile_frac),
        sinkhorn_weight=float(args.sinkhorn_weight),
        sinkhorn_epsilon=float(args.sinkhorn_epsilon),
        sinkhorn_target_irreps=sinkhorn_irreps,
        stiffness_ratio=args.stiffness_ratio,
        shear_ratio=args.shear_ratio,
        h_init_mm=(float(args.h_init_mm) if args.h_init_mm is not None else None),
        sigma_anneal_start=(float(args.sigma_anneal_start) if args.sigma_anneal_start is not None else None),
        sigma_anneal_steps=int(args.sigma_anneal_steps),
        target_dilation_px=int(args.target_dilation_px),
    )

    sr_print = args.stiffness_ratio if args.stiffness_ratio is not None else config.get("material", {}).get("stiffness_ratio", 1.05)
    print(f"W10 start / W10 启动: candidate={args.candidate_id}, K={opt_config.num_frequencies}, range=[{opt_config.f_min_hz:.0f},{opt_config.f_max_hz:.0f}]Hz, steps={opt_config.num_steps}, sr={sr_print:.3f}  (theta optimisation removed; per-cell rotation fixed at 0)")
    summary = run_w10_anisotropy_placement(config, target, opt_config, output_dir, verdict=verdict, initial_H_mm=initial_H)

    losses = summary["trace"]["total_loss"]
    enr = summary["trace"]["enrichment"]
    ct = summary["trace"]["contrast"]
    rc = summary["trace"]["recall"]
    print(f"steps={len(losses)}  best_loss={summary['best_loss']:.4f}@step{summary['best_step']}  enrichment {enr[0]:.2f}->{enr[-1]:.2f}  contrast {ct[0]:.2f}->{ct[-1]:.2f}  recall {rc[0]:.2%}->{rc[-1]:.2%}")
    print(f"E_par={summary['E_parallel_pa']:.3e}  E_perp={summary['E_perp_pa']:.3e}  G={summary['G_pp_pa']:.3e}  sr={summary['stiffness_ratio_used']:.3f}")
    if summary.get("best_surrogate_metrics"):
        m = summary["best_surrogate_metrics"]
        print(f"surrogate metrics @ best step: enrichment={m['enrichment']:.2f}x  contrast={m['contrast']:.2f}x  recall={m['recall']*100:.1f}%")
    print(f"output dir: {output_dir}")
    print(f"summary json: {output_dir / 'w10_optimization_summary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
