"""Visual comparison: Phase 2 iter 1 (best broad) vs iter 3 (best recall)."""
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
        g /= g.max()
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


def build_composite(record, image_size, plate_length_mm):
    bc = record["best_composite"]
    subset = bc["subset"]
    method = bc["method"]
    cand = record["candidate_id"]
    prefix = f"p2it{record['iter']}"
    amps = []
    for f_label in subset:
        nearest = None
        for df in record["drive_freqs"]:
            if f"{int(round(df))}" == f_label:
                nearest = df
                break
        if nearest is None:
            nearest = float(f_label)
        vid = f"{prefix}_{cand}_comsol_f{nearest:.1f}Hz".replace(".", "p")
        csv = Path("data/comsol_exports") / vid / "forced_response" / "forced_response.csv"
        amps.append(load_amp_csv(csv, image_size, plate_length_mm))
    return composite(amps, method)


summary = json.load(open("reports/sprint2_section4_phase2/phase2_summary.json"))
plate_length_mm = 150.0
image_size = 256

target_bin = np.load("data/processed_targets/target_binary.npy").astype(bool)
target = np.array(Image.fromarray(target_bin.astype(np.uint8) * 255).resize((image_size, image_size), Image.NEAREST)) > 127

history = summary["history"]
recs = {h["iter"]: h for h in history}

amp0 = build_composite(recs[0], image_size, plate_length_mm)
amp1 = build_composite(recs[1], image_size, plate_length_mm)
amp3 = build_composite(recs[3], image_size, plate_length_mm)

# Use BOTH broad sigma (0.05) and a sharper sigma (0.02) for visualisation
sigmas = [("broad σ=0.05", 0.05), ("medium σ=0.025", 0.025), ("sharp σ=0.012", 0.012)]

fig, axes = plt.subplots(len(sigmas) + 1, 4, figsize=(20, 5 * (len(sigmas) + 1)))

# Row 0: just raw amplitude fields (no powder smoothing)
axes[0, 0].imshow(target, cmap="Greys", origin="lower")
axes[0, 0].set_title("Target IC", fontsize=12)
axes[0, 0].axis("off")

for col, (label, amp_arr, rec_iter) in enumerate([("baseline iter 0", amp0, 0), ("Phase 2 iter 1\n(best broad)", amp1, 1), ("Phase 2 iter 3\n(best recall)", amp3, 3)], start=1):
    axes[0, col].imshow(amp_arr, cmap="hot", origin="lower")
    bc = recs[rec_iter]["best_composite"]
    sub = "+".join(bc["subset"])
    axes[0, col].set_title(
        f"{label}\nraw composite amplitude\n"
        f"{bc['method']}({sub})",
        fontsize=10,
    )
    axes[0, col].axis("off")

# Rows 1-3: powder density at different sigmas
for ri, (slabel, sig) in enumerate(sigmas, start=1):
    axes[ri, 0].imshow(target, cmap="Greys", origin="lower")
    axes[ri, 0].set_title(f"Target IC\n({slabel})", fontsize=12)
    axes[ri, 0].axis("off")

    for col, (cap, amp_arr, rec_iter) in enumerate([("iter 0", amp0, 0), ("iter 1", amp1, 1), ("iter 3", amp3, 3)], start=1):
        d = chladni_powder_density(amp_arr, sigma_rel=sig)
        axes[ri, col].imshow(d, cmap="hot", origin="lower")
        bc = recs[rec_iter]["best_composite"]
        axes[ri, col].set_title(
            f"{cap} ({slabel})\nbroad enr={bc['broad']['enrich']:.2f}×ec={bc['broad']['recall']:.2f}\n"
            f"tight enr={bc['tight']['enrich']:.2f}× rec={bc['tight']['recall']:.2f}".replace("ec=", "  rec="),
            fontsize=10,
        )
        axes[ri, col].axis("off")

plt.suptitle("Phase 2 iter 1 (best broad) vs iter 3 (best recall) — tier1 CF-PETG, sr=3", fontsize=14, fontweight="bold")
plt.tight_layout()
out = Path("reports/sprint2_section4_phase2/iter1_vs_iter3_compare.png")
fig.savefig(out, dpi=140, bbox_inches="tight")
plt.close(fig)
print(f"Saved: {out}")

# Also generate a focused single-row comparison (the headline)
fig2, axes2 = plt.subplots(1, 4, figsize=(20, 5))
axes2[0].imshow(target, cmap="Greys", origin="lower")
axes2[0].set_title("Target IC", fontsize=13)
axes2[0].axis("off")

for col, (cap, amp_arr, rec_iter) in enumerate([
    ("Phase 1 baseline (iter 0)", amp0, 0),
    ("Phase 2 iter 1 (best broad)", amp1, 1),
    ("Phase 2 iter 3 (best recall)", amp3, 3),
], start=1):
    d = chladni_powder_density(amp_arr, sigma_rel=0.025)
    axes2[col].imshow(d, cmap="hot", origin="lower")
    bc = recs[rec_iter]["best_composite"]
    sub = "+".join(bc["subset"])
    axes2[col].set_title(
        f"{cap}\n{bc['method']}({sub})\n"
        f"broad enr={bc['broad']['enrich']:.2f}×  rec={bc['broad']['recall']:.2f}\n"
        f"tight enr={bc['tight']['enrich']:.2f}×  rec={bc['tight']['recall']:.2f}",
        fontsize=11,
    )
    axes2[col].axis("off")

plt.suptitle("Headline: which Phase 2 iter looks more like IC?", fontsize=14, fontweight="bold")
plt.tight_layout()
out2 = Path("reports/sprint2_section4_phase2/headline_compare.png")
fig2.savefig(out2, dpi=150, bbox_inches="tight")
plt.close(fig2)
print(f"Saved: {out2}")
