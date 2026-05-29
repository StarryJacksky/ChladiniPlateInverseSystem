"""Render the final battery comparison grid.

Reads all production_summary.json + COMSOL forced_response CSVs from
reports/_battery/<material>/<target>/<candidate_id>/ and the existing
reports/production/production_design (CF-PETG on target_binary) +
reports/production_pla/production_design (PLA on target_binary).

Produces:
  reports/_battery/battery_comsol_native_grid.png   (target × material grid, COMSOL-style)
  reports/_battery/battery_summary_table.txt        (metric table)
  reports/_battery/battery_summary.json             (raw data)
"""
from __future__ import annotations
import json
import os
import sys
from pathlib import Path

Path("data/.matplotlib_cache").mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(Path("data/.matplotlib_cache").resolve()))
os.environ.setdefault("MPLBACKEND", "Agg")

import re

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.tri as mtri

ROOT = Path(__file__).resolve().parents[1]


# Target ordering and metadata
TARGETS = [
    # (display_name, .npy path for showing target image)
    ("binary (8-elem)", "data/processed_targets/target_binary.npy"),
    ("cross",           "data/processed_targets/target_cross.npy"),
    ("diagonal",        "data/processed_targets/target_diagonal.npy"),
    ("xform",           "data/processed_targets/target_xform.npy"),
    ("star_outline",    "data/_d_verify_targets/star_outline.npy"),
    ("ic",              "data/processed_targets/target_ic.npy"),
]


def locate_run(material: str, target_label: str) -> tuple[Path, str] | None:
    """Return (summary_path, candidate_id) for a battery run; None if missing.

    Handles both the original baseline runs (production/, production_pla/) and
    the unique-id battery runs (_battery/<mat>/<target>/bat_<mat>_<target>/).
    """
    base = ROOT / "reports" / "_battery" / material / target_label
    if base.exists():
        # Look for bat_<material>_<target>/ subdir
        cand = base / f"bat_{material}_{target_label}"
        sp = cand / "production_summary.json"
        if sp.exists():
            return sp, f"bat_{material}_{target_label}"
    # Fallback: pre-existing target_binary runs
    if target_label == "binary":
        if material == "cfpetg":
            sp = ROOT / "reports/production/production_design/production_summary.json"
            if sp.exists():
                return sp, "production_design"
        elif material == "pla":
            sp = ROOT / "reports/production_pla/production_design/production_summary.json"
            if sp.exists():
                return sp, "production_design"
    return None


def load_csv(p: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    arr = np.loadtxt(p, delimiter=",", skiprows=1)
    x, y = arr[:, 0], arr[:, 1]
    amp = arr[:, 4] if arr.shape[1] >= 5 else np.sqrt(arr[:, 2] ** 2 + arr[:, 3] ** 2)
    return x, y, amp


_DIR_RE = re.compile(r"_comsol_f(?P<num>[\dp]+)Hz$")


def freq_csv(stage_prefix: str, cand: str, freq_str: str, drive_freqs: list[float]) -> Path:
    """Find the forced_response.csv whose freq tag is nearest to freq_str.

    Robust to floating-point drift: instead of computing the filename, we scan
    existing folders matching <stage_prefix>_<cand>_comsol_f*Hz/ and pick the
    one with closest numeric frequency. /
    扫描已存在文件夹按数值最近匹配，避免 ".0" vs ".5" 失配。
    """
    target = float(freq_str)
    base = ROOT / "data" / "comsol_exports"
    prefix = f"{stage_prefix}_{cand}_comsol_f"
    best: tuple[float, Path] | None = None
    for d in base.glob(f"{stage_prefix}_{cand}_comsol_f*Hz"):
        m = _DIR_RE.search(d.name)
        if not m:
            continue
        f_val = float(m.group("num").replace("p", "."))
        diff = abs(f_val - target)
        if best is None or diff < best[0]:
            best = (diff, d)
    if best is None:
        # Fallback to old behaviour for legacy paths
        nearest = min(drive_freqs, key=lambda f: abs(float(f) - target)) if drive_freqs else target
        tag = f"f{nearest:.1f}Hz".replace(".", "p")
        return base / f"{stage_prefix}_{cand}_comsol_{tag}" / "forced_response" / "forced_response.csv"
    return best[1] / "forced_response" / "forced_response.csv"


def build_composite_from_summary(summary: dict, cand: str) -> tuple[np.ndarray | None, np.ndarray | None, np.ndarray | None, str, list[float], str]:
    """Pick Phase 1 best_composite OR Phase 2 winner iter's best_composite —
    crucial because Phase 2 retrains at NEW freqs, so we must use the right
    subset + matching candidate_id + matching drive_freqs from history.
    """
    p2 = summary.get("phase2") or {}
    history = p2.get("history") or []
    best_iter = p2.get("best_iter", 0)
    use_p1 = (best_iter == 0) or not history

    if use_p1:
        bc = summary["phase1"]["best_composite"]
        prefix = "prodp1"
        drive_freqs = list(summary["phase1"]["drive_freqs"])
        stage_tag = "Phase 1"
        cand_for_csv = cand
    else:
        winner = next((h for h in history if h["iter"] == best_iter), None)
        if winner is None:
            print(f"  [warn] phase2 best_iter={best_iter} not in history; falling back to Phase 1")
            bc = summary["phase1"]["best_composite"]
            prefix = "prodp1"
            drive_freqs = list(summary["phase1"]["drive_freqs"])
            stage_tag = "Phase 1 (P2 winner not found)"
            cand_for_csv = cand
        else:
            bc = winner["best_composite"]
            prefix = f"prodp2it{best_iter}"
            stage_tag = f"Phase 2 iter {best_iter}"
            cand_for_csv = winner["candidate_id"]
            # Phase 2 retrains at NEW freqs which match its subset values.
            # The history record's drive_freqs may be empty / phase-1 leftovers,
            # so use the subset values themselves as the lookup keys. /
            # Phase 2 在新频率上重训，其 subset 即为查找键
            drive_freqs = [float(s) for s in bc["subset"]]

    subset, method = bc["subset"], bc["method"]
    amps = []
    x0 = y0 = None
    used_freqs = []
    for fl in subset:
        csv = freq_csv(prefix, cand_for_csv, fl, drive_freqs)
        if not csv.exists():
            print(f"  [missing] {csv}")
            continue
        x, y, a = load_csv(csv)
        if x0 is None:
            x0, y0 = x, y
        peak = float(np.max(np.abs(a)))
        if peak > 0:
            a = a / peak
        amps.append(a)
        nearest = min(drive_freqs, key=lambda f: abs(int(round(f)) - int(fl)))
        used_freqs.append(nearest)
    if not amps:
        return None, None, None, "+".join(subset), [], stage_tag
    stack = np.stack(amps, axis=0)
    if method == "RMS":
        comp = np.sqrt(np.mean(stack ** 2, axis=0))
    elif method == "MAX":
        comp = np.max(stack, axis=0)
    else:
        comp = np.sum(stack, axis=0)
    if comp.max() > 1e-30:
        comp = comp / comp.max()
    return x0, y0, comp, "+".join(subset), used_freqs, stage_tag


def powder_from_amp(amp: np.ndarray, sigma_rel: float = 0.08) -> np.ndarray:
    """Sand accumulation = where amplitude is LOW (nodes).

    σ_rel controls visual width of nodal "bands". Composite (multi-freq RMS)
    needs wider σ (~0.08) than single-freq (~0.025) because RMS of three
    normalized modes rarely dips below 2.5% — most physical nodes show up
    in 5–15% relative-amplitude band. /
    σ_rel 控制节点带宽。复合频率 RMS 后节点很少 <2.5%，用 0.08 才能看清沙带。
    """
    peak = float(np.max(np.abs(amp)))
    if peak <= 0:
        return np.ones_like(amp)
    return np.exp(-((np.abs(amp) / peak / sigma_rel) ** 2))


def add_target(ax, target_path: str, title: str):
    arr = np.load(ROOT / target_path)
    ax.imshow(arr, cmap="gray_r")
    ax.set_title(title, fontsize=10)
    ax.set_xticks([])
    ax.set_yticks([])


def add_powder_jet(ax, x_m, y_m, powder, title: str, plate_mm: float = 150.0):
    triang = mtri.Triangulation(x_m, y_m)
    ax.tricontourf(triang, powder, levels=200, cmap="jet", vmin=0, vmax=1)
    ax.set_aspect("equal")
    ax.set_xlim(-plate_mm/2/1000, plate_mm/2/1000)
    ax.set_ylim(-plate_mm/2/1000, plate_mm/2/1000)
    ax.set_title(title, fontsize=10)
    ax.set_xticks([])
    ax.set_yticks([])


def main() -> int:
    # 1) Gather metadata + composites
    rows = []
    for tgt_label, tgt_path in TARGETS:
        battery_label = "binary" if tgt_label.startswith("binary") else tgt_label
        row = {"target_label": tgt_label, "target_path": tgt_path, "runs": {}}
        for mat in ("cfpetg", "pla"):
            loc = locate_run(mat, battery_label)
            if loc is None:
                row["runs"][mat] = None
                continue
            sp, cand = loc
            s = json.loads(sp.read_text())
            bc = s["phase1"]["best_composite"]
            p2 = s.get("phase2") or {}
            sr = s.get("stiffness_ratio")
            entry = {
                "summary_path": str(sp),
                "candidate_id": cand,
                "stiffness_ratio": sr,
                "p1_broad_enr": bc["broad"]["enrich"],
                "p1_broad_rec": bc["broad"]["recall"],
                "p1_tight_enr": bc["tight"]["enrich"],
                "p1_tight_rec": bc["tight"]["recall"],
                "p1_subset":    bc["subset"],
                "p2_best_iter": p2.get("best_iter"),
                "p2_enr":       p2.get("best_enrichment"),
                "p2_rec":       p2.get("best_recall"),
            }
            try:
                x, y, comp, subset_s, used_f, stage_tag = build_composite_from_summary(s, cand)
                if comp is not None:
                    entry["powder"] = powder_from_amp(comp)
                    entry["x_m"] = x
                    entry["y_m"] = y
                    entry["subset_str"] = subset_s
                    entry["used_freqs"] = used_f
                    entry["stage_tag"] = stage_tag
            except Exception as e:
                entry["render_error"] = str(e)
            row["runs"][mat] = entry
        rows.append(row)

    # 2) Write text metric table
    out_dir = ROOT / "reports" / "_battery"
    out_dir.mkdir(parents=True, exist_ok=True)
    lines = []
    lines.append("=" * 100)
    lines.append(f"{'target':<20} {'material':<10} {'enr':<8} {'recall':<8} {'tight_enr':<10} {'tight_rec':<10} {'subset':<10} {'p2_imp%':<8}")
    lines.append("-" * 100)
    for r in rows:
        for mat in ("cfpetg", "pla"):
            e = r["runs"].get(mat)
            if e is None:
                lines.append(f"{r['target_label']:<20} {mat:<10} {'-':<8} {'-':<8} {'-':<10} {'-':<10} {'-':<10}")
                continue
            p2_imp = "0"  # both runs so far end Phase 2 with best_iter=0
            if e.get("p2_best_iter") not in (0, None):
                base_score = e["p1_broad_enr"] * (e["p1_broad_rec"] ** 0.5)
                # not exact, but approx
                p2_imp = "+"
            subset_s = "+".join(e["p1_subset"])[:10]
            lines.append(f"{r['target_label']:<20} {mat:<10} {e['p1_broad_enr']:<8.3f} {e['p1_broad_rec']:<8.3f} {e['p1_tight_enr']:<10.3f} {e['p1_tight_rec']:<10.3f} {subset_s:<10} {p2_imp:<8}")
    lines.append("=" * 100)
    text = "\n".join(lines)
    (out_dir / "battery_summary_table.txt").write_text(text)
    print(text)

    # 3) Render grid
    n_targets = len(rows)
    fig, axes = plt.subplots(n_targets, 3, figsize=(13, 3.8 * n_targets),
                              gridspec_kw=dict(wspace=0.05, hspace=0.45))
    if n_targets == 1:
        axes = axes.reshape(1, 3)
    for ri, r in enumerate(rows):
        add_target(axes[ri, 0], r["target_path"], f"Target: {r['target_label']}")
        for ci, mat in enumerate(("cfpetg", "pla"), start=1):
            e = r["runs"].get(mat)
            ax = axes[ri, ci]
            mat_disp = "CF-PETG (sr=3, θ)" if mat == "cfpetg" else "PLA iso (sr=1, no θ)"
            if e is None or "powder" not in e:
                ax.text(0.5, 0.5, "(no run yet)", ha="center", va="center", transform=ax.transAxes,
                        fontsize=11, color="gray")
                ax.set_title(f"{mat_disp}\n(missing)", fontsize=10)
                ax.set_xticks([]); ax.set_yticks([])
                continue
            f_str = ", ".join(f"{f:.0f}" for f in e["used_freqs"])
            title = (f"{mat_disp}\n"
                     f"COMSOL @ {f_str} Hz\n"
                     f"enr={e['p1_broad_enr']:.2f}× rec={e['p1_broad_rec']:.2f}  "
                     f"(tight {e['p1_tight_enr']:.2f}×)")
            add_powder_jet(ax, e["x_m"], e["y_m"], e["powder"], title)

    fig.suptitle("Battery: CF-PETG (θ active) vs school FDM PLA (no θ) across 6 targets\n"
                  "COMSOL-native rendering (jet, powder σ=0.08: bright = nodal lines = sand)",
                  fontsize=14, fontweight="bold", y=0.995)
    # winner annotation per row (between PLA panel and right edge)
    for ri, r in enumerate(rows):
        cf = r["runs"].get("cfpetg") or {}
        pla = r["runs"].get("pla") or {}
        cenr = (cf.get("p2_enr") or cf.get("p1_broad_enr")) or 0
        penr = (pla.get("p2_enr") or pla.get("p1_broad_enr")) or 0
        if cenr <= 0 or penr <= 0:
            continue
        delta = (penr - cenr) / cenr * 100
        if delta > 5:
            verdict = f"PLA wins\n{delta:+.0f}%"
            color = "darkgreen"
        elif delta < -5:
            verdict = f"CF-PETG wins\n{delta:+.0f}%"
            color = "darkred"
        else:
            verdict = "tie"
            color = "gray"
        axes[ri, 2].annotate(
            verdict, xy=(1.02, 0.5), xycoords="axes fraction",
            fontsize=11, fontweight="bold", color=color, va="center", ha="left",
        )
    out_png = out_dir / "battery_comsol_native_grid.png"
    fig.savefig(out_png, dpi=130, bbox_inches="tight")
    print(f"[wrote] {out_png}")

    # 4) Save raw json (strip numpy)
    def _clean(d):
        if isinstance(d, dict):
            return {k: _clean(v) for k, v in d.items() if k not in ("powder", "x_m", "y_m")}
        if isinstance(d, list):
            return [_clean(x) for x in d]
        if isinstance(d, np.ndarray):
            return d.tolist()
        return d
    (out_dir / "battery_summary.json").write_text(json.dumps([_clean(r) for r in rows], indent=2, ensure_ascii=False))
    print(f"[wrote] {out_dir / 'battery_summary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
