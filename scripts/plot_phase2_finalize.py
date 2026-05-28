"""Plot Phase 2 final result: target + baseline + best iter (iter1), and trajectory."""
import json
import os
from pathlib import Path

Path("data/.matplotlib_cache").mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(Path("data/.matplotlib_cache").resolve()))
os.environ.setdefault("MPLBACKEND", "Agg")

import numpy as np
import matplotlib.pyplot as plt
from PIL import Image

from src.scoring.recognisability_score import chladni_powder_density
from scripts.run_sprint2_section4_phase1 import downsample_comsol_xy_to_grid


def load_amp_csv(csv_path, image_size, plate_length_mm):
    arr = np.loadtxt(csv_path, delimiter=",", skiprows=1)
    if arr.shape[1] >= 4:
        amp = np.sqrt(arr[:, 2] ** 2 + arr[:, 3] ** 2)
    else:
        amp = np.abs(arr[:, 2])
    g = downsample_comsol_xy_to_grid(arr[:, 0], arr[:, 1], amp, image_size, plate_length_mm)
    if g.max() > 1e-30:
        g = g / g.max()
    return g


def composite(amps, method):
    s = np.stack(amps, axis=0)
    if method == "RMS":
        c = np.sqrt(np.mean(s ** 2, axis=0))
    elif method == "MAX":
        c = np.max(s, axis=0)
    else:
        c = np.sum(s, axis=0)
    if c.max() > 1e-30:
        c /= c.max()
    return c


summary = json.load(open("reports/sprint2_section4_phase2/phase2_summary.json"))
plate_length_mm = 150.0
image_size = 256

target_bin = np.load("data/processed_targets/target_binary.npy").astype(bool)
timg = Image.fromarray(target_bin.astype(np.uint8) * 255).resize((image_size, image_size), Image.NEAREST)
target = (np.array(timg) > 127).astype(bool)


def build_composite_for_iter(record):
    bc = record["best_composite"]
    subset = bc["subset"]
    method = bc["method"]
    candidate = record["candidate_id"]
    iter_n = record["iter"]
    # Forced response export prefix
    prefix = f"p2it{iter_n}"
    amps = []
    for f_label in subset:
        # Re-derive 1-dp drive freq from the per_freq dict using nearest drive_freq
        nearest = None
        for df in record["drive_freqs"]:
            if f"{int(round(df))}" == f_label:
                nearest = df
                break
        if nearest is None:
            nearest = float(f_label)
        vid = f"{prefix}_{candidate}_comsol_f{nearest:.1f}Hz".replace(".", "p")
        csv = Path("data/comsol_exports") / vid / "forced_response" / "forced_response.csv"
        amps.append(load_amp_csv(csv, image_size, plate_length_mm))
    return composite(amps, method)


history = summary["history"]
baseline_record = history[0]
best_record = next(h for h in history if h["iter"] == summary["best_iter"])

baseline_amp = build_composite_for_iter(baseline_record)
best_amp = build_composite_for_iter(best_record)

dens_b = chladni_powder_density(baseline_amp, sigma_rel=0.05)
dens_p2 = chladni_powder_density(best_amp, sigma_rel=0.05)

# 4-panel: target | baseline | phase2 best | trajectory bar
fig = plt.figure(figsize=(20, 6))
gs = fig.add_gridspec(1, 4, width_ratios=[1, 1, 1, 1.1])

ax_t = fig.add_subplot(gs[0])
ax_t.imshow(target, cmap="Greys", origin="lower")
ax_t.set_title("Target IC", fontsize=12)
ax_t.axis("off")

ax_b = fig.add_subplot(gs[1])
ax_b.imshow(dens_b, cmap="hot", origin="lower")
bc_b = baseline_record["best_composite"]
sub_b = "+".join(bc_b["subset"])
ax_b.set_title(
    f"Phase 1 best (iter 0)\n"
    f"{bc_b['method']}({sub_b})\n"
    f"broad enr={bc_b['broad']['enrich']:.2f}×  rec={bc_b['broad']['recall']:.2f}\n"
    f"tight enr={bc_b['tight']['enrich']:.2f}×  rec={bc_b['tight']['recall']:.2f}",
    fontsize=10,
)
ax_b.axis("off")

ax_p = fig.add_subplot(gs[2])
ax_p.imshow(dens_p2, cmap="hot", origin="lower")
bc_p = best_record["best_composite"]
sub_p = "+".join(bc_p["subset"])
ax_p.set_title(
    f"Phase 2 BEST (iter {best_record['iter']})\n"
    f"{bc_p['method']}({sub_p})\n"
    f"broad enr={bc_p['broad']['enrich']:.2f}×  rec={bc_p['broad']['recall']:.2f}\n"
    f"tight enr={bc_p['tight']['enrich']:.2f}×  rec={bc_p['tight']['recall']:.2f}",
    fontsize=10,
)
ax_p.axis("off")

ax_tr = fig.add_subplot(gs[3])
iters = [h["iter"] for h in history]
enrs = [h["best_composite"]["broad"]["enrich"] for h in history]
recs = [h["best_composite"]["broad"]["recall"] for h in history]
accepts = [h.get("accepted", True) for h in history]
colors = ["green" if a else "red" for a in accepts]
ax_tr.bar([str(i) for i in iters], enrs, color=colors, alpha=0.7, edgecolor="black")
for i, (e, r, a) in enumerate(zip(enrs, recs, accepts)):
    ax_tr.text(i, e + 0.05, f"{e:.2f}×\nrec={r:.2f}\n{'✓' if a else '✗'}", ha="center", fontsize=10)
ax_tr.axhline(enrs[0], ls="--", color="gray", alpha=0.5, label=f"baseline {enrs[0]:.2f}×")
ax_tr.axhline(summary["best_enrichment"], ls="-", color="darkgreen", alpha=0.8, label=f"best {summary['best_enrichment']:.2f}× ({summary['improvement_pct']:+.1f}%)")
ax_tr.set_xlabel("Phase 2 iteration")
ax_tr.set_ylabel("broad enrichment factor")
ax_tr.set_ylim(0, max(enrs) * 1.25)
ax_tr.set_title("Phase 2 trust-region trajectory", fontsize=11)
ax_tr.legend(loc="lower right", fontsize=9)
ax_tr.grid(axis="y", alpha=0.3)

fig.suptitle("Sprint 2 §4 Phase 2 — Trust-region COMSOL refinement on tier1 (CF-PETG, sr=3)", fontsize=13)
plt.tight_layout()
out = Path("reports/sprint2_section4_phase2/phase2_final.png")
fig.savefig(out, dpi=150, bbox_inches="tight")
plt.close(fig)
print(f"Saved: {out}")

np.save("reports/sprint2_section4_phase2/phase2_best_amp.npy", best_amp)
np.save("reports/sprint2_section4_phase2/phase2_best_density.npy", dens_p2)
print(f"Saved npys")
