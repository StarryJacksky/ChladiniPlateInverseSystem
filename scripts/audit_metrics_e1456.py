"""Read-only audit of pipeline metric/algorithm choices (E1/E4/E5/E6).

This script does NOT touch any core pipeline code. It only reads the archived
artifacts of a completed run (production_summary.json + saved powder/amp .npy +
target_resized.npy) and quantifies four "algorithmic thinking" concerns raised
during the audit:

  E1  composite ranking is concentration-biased (favours blobs over the cross)
  E4  W10-injected drive frequencies vs COMSOL eigenmodes — who actually helps
  E5  modal excitability (does shape-based mode selection pick inexcitable modes)
  E6  fixed-percentile powder threshold sensitivity

Run:
    .venv/bin/python scripts/audit_metrics_e1456.py \
        --run-dir reports/_bambu_final/bambu_cross \
        --out reports/audit_metrics_2026-05.png
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


def _load(run_dir: Path):
    summ = json.load(open(run_dir / "production_summary.json"))
    target = np.load(run_dir / "target_resized.npy")
    out = {"summ": summ, "target": target}
    for name in (
        "phase1_best_single_amp",
        "phase1_best_single_powder_broad",
        "phase1_best_composite_amp",
        "phase1_best_powder_broad",
    ):
        p = run_dir / f"{name}.npy"
        if p.exists():
            out[name] = np.load(p)
    return out


def _binarise(field: np.ndarray, target: np.ndarray) -> np.ndarray:
    """Binarise a powder/amplitude field at the coverage of the target.

    Use a quantile threshold so that the number of 'on' pixels roughly matches
    the target's, making IoU a fair shape comparison independent of overall
    brightness."""
    f = np.abs(field).astype(float)
    f = f / (f.max() + 1e-12)
    cov = float((target > 0.5).mean())
    if cov <= 0:
        return f > f.max()
    thr = np.quantile(f, 1.0 - cov)
    return f >= thr


def _iou(a: np.ndarray, b: np.ndarray) -> float:
    a = a > 0.5
    b = b > 0.5
    inter = np.logical_and(a, b).sum()
    union = np.logical_or(a, b).sum()
    return float(inter / union) if union else 0.0


def _corr(field: np.ndarray, target: np.ndarray) -> float:
    f = np.abs(field).astype(float).ravel()
    t = (target > 0.5).astype(float).ravel()
    if f.std() < 1e-12 or t.std() < 1e-12:
        return 0.0
    return float(np.corrcoef(f, t)[0, 1])


def audit_e1(data) -> dict:
    """Composite (blob) vs single (cross): show enrich-ranking anti-correlates
    with shape fidelity (IoU / correlation with target)."""
    summ, target = data["summ"], data["target"]
    p1 = summ["phase1"]
    res = {"single": {}, "composite": {}}
    res["single"]["enrich"] = p1["best_single"]["broad"]["enrich"]
    res["single"]["recall"] = p1["best_single"]["broad"]["recall"]
    res["composite"]["enrich"] = p1["best_composite"]["broad"]["enrich"]
    res["composite"]["recall"] = p1["best_composite"]["broad"]["recall"]
    if "phase1_best_single_powder_broad" in data:
        s = data["phase1_best_single_powder_broad"]
        res["single"]["iou"] = _iou(_binarise(s, target), target > 0.5)
        res["single"]["corr"] = _corr(s, target)
    if "phase1_best_powder_broad" in data:
        c = data["phase1_best_powder_broad"]
        res["composite"]["iou"] = _iou(_binarise(c, target), target > 0.5)
        res["composite"]["corr"] = _corr(c, target)
    return res


def audit_e4(data) -> dict:
    """W10-injected drive freqs vs COMSOL eigenmode freqs — mean quality."""
    p1 = data["summ"]["phase1"]
    # Only the W10 freqs actually injected into the drive list are the top-N by
    # weight; classify a per-freq tone as W10 if it sits within 1.5 Hz of ANY
    # learned W10 frequency (drive freqs are rounded when keyed). /
    w10_freqs = [float(x) for x in p1["w10_freqs_weights"]["frequencies_hz"]]
    per = p1["per_freq"]
    eig_e, eig_r, w_e, w_r = [], [], [], []
    rows = []
    for f, v in per.items():
        b = v["broad"]
        ff = float(f)
        is_w10 = any(abs(ff - wf) <= 1.5 for wf in w10_freqs)
        rows.append((float(f), b["enrich"], b["recall"], "W10" if is_w10 else "eig"))
        (w_e if is_w10 else eig_e).append(b["enrich"])
        (w_r if is_w10 else eig_r).append(b["recall"])
    return {
        "rows": sorted(rows),
        "eig_mean_enrich": float(np.mean(eig_e)) if eig_e else 0.0,
        "eig_mean_recall": float(np.mean(eig_r)) if eig_r else 0.0,
        "w10_mean_enrich": float(np.mean(w_e)) if w_e else 0.0,
        "w10_mean_recall": float(np.mean(w_r)) if w_r else 0.0,
    }


def audit_e5(data) -> dict:
    """Excitability check (indirect): per selected eigenmode, the forced-response
    recall is the empirical 'did this mode actually appear under the real load'.
    A mode chosen by shape but inexcitable would show recall≈0."""
    p1 = data["summ"]["phase1"]
    per = p1["per_freq"]
    per_keys = {float(k): k for k in per}
    rows = []
    for m in p1["top_modes"]:
        f = float(m["freq_hz"])
        # match to nearest per_freq key within 1.5 Hz (drive freqs are rounded)
        forced = None
        if per_keys:
            nearest = min(per_keys, key=lambda kf: abs(kf - f))
            if abs(nearest - f) <= 1.5:
                forced = per[per_keys[nearest]]
        rows.append({
            "mode": m["mode"],
            "freq": m["freq_hz"],
            "eig_shape_enrich": m["enrichment"],
            "forced_recall": forced["broad"]["recall"] if forced else None,
            "forced_enrich": forced["broad"]["enrich"] if forced else None,
        })
    return {"rows": rows}


def audit_e6(data) -> dict:
    """Powder threshold sensitivity. Chladni powder accumulates at NODES, i.e.
    where the displacement |amplitude| is SMALLEST. So 'powder on' = the lowest
    p-percentile of |amp|. Sweep p and report recall / enrich-proxy / IoU to see
    how sensitive the figure is to the (fixed) percentile cut."""
    target = data["target"]
    amp = data.get("phase1_best_single_amp")
    if amp is None:
        return {}
    f = np.abs(amp).astype(float)
    f = f / (f.max() + 1e-12)
    tmask = target > 0.5
    cov = float(tmask.mean())
    out = []
    # low-side percentiles: smallest p% of |amp| = nodal lines = powder
    for pct in (2, 4, 6, 7, 8, 10, 12, 15, 20):
        thr = np.percentile(f, pct)
        on = f <= thr
        on_frac = float(on.mean())
        recall = float(np.logical_and(on, tmask).sum() / max(tmask.sum(), 1))
        # enrichment proxy = P(target | powder) / P(target) = precision / coverage
        on_sum = max(int(on.sum()), 1)
        precision = float(np.logical_and(on, tmask).sum() / on_sum)
        enrich = float(precision / (cov + 1e-12))
        iou = _iou(on, tmask)
        out.append({"pct": pct, "on_frac": on_frac, "recall": recall,
                     "enrich_proxy": enrich, "iou": iou})
    return {"sweep": out, "target_cov": cov}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", default="reports/_bambu_final/bambu_cross")
    ap.add_argument("--out", default="reports/audit_metrics_2026-05.png")
    args = ap.parse_args()

    run_dir = Path(args.run_dir)
    data = _load(run_dir)

    e1 = audit_e1(data)
    e4 = audit_e4(data)
    e5 = audit_e5(data)
    e6 = audit_e6(data)

    print("=" * 70)
    print("E1  composite (blob) vs single (cross) — shape fidelity")
    print("-" * 70)
    for k in ("single", "composite"):
        r = e1[k]
        print(f"  {k:9s} enrich={r.get('enrich',0):6.2f} recall={r.get('recall',0):.2f} "
              f"IoU={r.get('iou',float('nan')):.3f} corr={r.get('corr',float('nan')):.3f}")
    print("  -> ranking by enrich picks the LOW-IoU blob over the HIGH-IoU cross")

    print("=" * 70)
    print("E4  W10-injected freqs vs COMSOL eigenmodes")
    print("-" * 70)
    for f, e, r, kind in e4["rows"]:
        print(f"  {f:7.1f} Hz  enr={e:5.2f} rec={r:.2f}  [{kind}]")
    print(f"  eig  mean: enr={e4['eig_mean_enrich']:.2f} rec={e4['eig_mean_recall']:.2f}")
    print(f"  W10  mean: enr={e4['w10_mean_enrich']:.2f} rec={e4['w10_mean_recall']:.2f}")

    print("=" * 70)
    print("E5  selected-mode excitability (forced-response recall)")
    print("-" * 70)
    for r in e5["rows"]:
        fr = r["forced_recall"]
        print(f"  mode {r['mode']:>2} @ {r['freq']:6.1f} Hz  shape_enr={r['eig_shape_enrich']:.2f}  "
              f"forced_recall={fr if fr is None else round(fr,2)}")

    print("=" * 70)
    print("E6  powder threshold (percentile) sensitivity — best single tone")
    print("-" * 70)
    print(f"  target coverage = {e6.get('target_cov',0):.3f}")
    for s in e6.get("sweep", []):
        print(f"  pct={s['pct']:>2}  on_frac={s['on_frac']:.3f}  recall={s['recall']:.2f}  "
              f"enrich_proxy={s['enrich_proxy']:.2f}  IoU={s['iou']:.3f}")

    _make_figure(data, e1, e4, e6, Path(args.out))
    print(f"\nFigure saved -> {args.out}")
    json.dump({"e1": e1, "e4": e4, "e5": e5, "e6": e6},
              open(Path(args.out).with_suffix(".json"), "w"), indent=2)
    return 0


def _make_figure(data, e1, e4, e6, out_path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    target = data["target"]
    fig, ax = plt.subplots(2, 3, figsize=(13, 8))

    ax[0, 0].imshow(target, cmap="gray_r"); ax[0, 0].set_title("TARGET (cross)")
    if "phase1_best_single_powder_broad" in data:
        ax[0, 1].imshow(np.abs(data["phase1_best_single_powder_broad"]), cmap="gray_r")
    ax[0, 1].set_title(f"BEST SINGLE\nenr={e1['single'].get('enrich',0):.1f} "
                        f"IoU={e1['single'].get('iou',0):.2f}")
    if "phase1_best_powder_broad" in data:
        ax[0, 2].imshow(np.abs(data["phase1_best_powder_broad"]), cmap="gray_r")
    ax[0, 2].set_title(f"BEST COMPOSITE (MAX)\nenr={e1['composite'].get('enrich',0):.1f} "
                        f"IoU={e1['composite'].get('iou',0):.2f}")
    for a in ax[0]:
        a.set_xticks([]); a.set_yticks([])

    # E4 bar
    rows = e4["rows"]
    freqs = [f"{int(f)}" for f, _, _, _ in rows]
    enr = [e for _, e, _, _ in rows]
    colors = ["#d62728" if k == "W10" else "#1f77b4" for _, _, _, k in rows]
    ax[1, 0].bar(freqs, enr, color=colors)
    ax[1, 0].set_title("E4: per-freq enrich\n(blue=eigenmode, red=W10-injected)")
    ax[1, 0].set_ylabel("broad enrich"); ax[1, 0].tick_params(axis="x", rotation=45)

    # E4 recall
    rec = [r for _, _, r, _ in rows]
    ax[1, 1].bar(freqs, rec, color=colors)
    ax[1, 1].set_title("E4: per-freq recall")
    ax[1, 1].set_ylabel("broad recall"); ax[1, 1].tick_params(axis="x", rotation=45)

    # E6 sweep
    sw = e6.get("sweep", [])
    if sw:
        pcts = [s["pct"] for s in sw]
        enr_max = max((s["enrich_proxy"] for s in sw), default=0.0) or 1.0
        ax[1, 2].plot(pcts, [s["recall"] for s in sw], "o-", label="recall")
        ax[1, 2].plot(pcts, [s["iou"] for s in sw], "s-", label="IoU")
        ax[1, 2].plot(pcts, [s["enrich_proxy"] / enr_max for s in sw], "^-",
                       label="enrich (norm)")
        cov = e6.get("target_cov", 0)
        ax[1, 2].axvline(100 * cov, color="gray", ls="--", lw=1,
                          label=f"target cov {100*cov:.1f}%")
        ax[1, 2].set_title("E6: powder threshold sweep\n(lowest p% |amp| = nodes)")
        ax[1, 2].set_xlabel("low-side percentile"); ax[1, 2].legend(fontsize=8)

    fig.tight_layout()
    fig.savefig(out_path, dpi=110)
    plt.close(fig)


if __name__ == "__main__":
    raise SystemExit(main())
