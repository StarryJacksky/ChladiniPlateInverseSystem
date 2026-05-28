"""Plot tier1 finalize results: target vs P1_uniform vs best_composite, plus full leaderboard."""
import json
import os
from pathlib import Path

Path("data/.matplotlib_cache").mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(Path("data/.matplotlib_cache").resolve()))
os.environ.setdefault("MPLBACKEND", "Agg")

import numpy as np
import matplotlib.pyplot as plt

base = Path("reports/sprint2_section4_phase1_tier1/w10_ic_tier1_sr3_v2")
dens_uni = np.load(base / "tier1_density_uniform.npy")
dens_best = np.load(base / "tier1_density_best.npy")
summary = json.load(open(base / "tier1_finalize.json"))

target_bin = np.load("data/processed_targets/target_binary.npy").astype(bool)
from PIL import Image
target_img = Image.fromarray(target_bin.astype(np.uint8) * 255).resize((256, 256), Image.NEAREST)
target = (np.array(target_img) > 127).astype(bool)

p1u = summary["p1_uniform_rms"]
bc = summary["best_composite"]

fig, axes = plt.subplots(1, 3, figsize=(15, 5.5))

axes[0].imshow(target, cmap="Greys", origin="lower")
axes[0].set_title("Target IC", fontsize=12)
axes[0].axis("off")

axes[1].imshow(dens_uni, cmap="hot", origin="lower")
axes[1].set_title(
    "Tier1 (sr=3) P1_uniform_RMS (6 freqs)\n"
    f"broad enr={p1u['broad']['enrich']:.2f}×  rec={p1u['broad']['recall']:.2f}\n"
    f"tight enr={p1u['tight']['enrich']:.2f}×  rec={p1u['tight']['recall']:.2f}",
    fontsize=11,
)
axes[1].axis("off")

axes[2].imshow(dens_best, cmap="hot", origin="lower")
sub_str = "+".join(bc["subset"])
axes[2].set_title(
    f"Tier1 BEST {bc['method']}: {sub_str}\n"
    f"broad enr={bc['broad']['enrich']:.2f}×  rec={bc['broad']['recall']:.2f}\n"
    f"tight enr={bc['tight']['enrich']:.2f}×  rec={bc['tight']['recall']:.2f}",
    fontsize=11,
)
axes[2].axis("off")

plt.suptitle("Tier1 (CF-PETG, sr=3) Phase 1 + Off-resonance Sweep (Final Result)", fontsize=13)
plt.tight_layout()
out = base / "tier1_final_panel.png"
fig.savefig(out, dpi=150, bbox_inches="tight")
plt.close(fig)
print(f"Saved: {out}")


# Comparison panel: tier1 vs tier2
fig2, axes2 = plt.subplots(1, 4, figsize=(20, 5.5))
axes2[0].imshow(target, cmap="Greys", origin="lower")
axes2[0].set_title("Target IC", fontsize=12)
axes2[0].axis("off")

tier2_dens = None
tier2_p = Path("reports/sprint2_section4_phase1/w10_ic_tier2_sr12/deliverable_best_composite_132+180_RMS.npy")
if tier2_p.exists():
    from src.scoring.recognisability_score import chladni_powder_density
    tier2_amp = np.load(tier2_p)
    tier2_dens = chladni_powder_density(tier2_amp, sigma_rel=0.05)
    axes2[1].imshow(tier2_dens, cmap="hot", origin="lower")
    axes2[1].set_title("Tier2 (sr=12) BEST\nRMS(132+180Hz)\nbroad enr=3.82×  rec=0.89", fontsize=11)
else:
    axes2[1].text(0.5, 0.5, "tier2 deliverable\nnot found", ha="center", va="center")
axes2[1].axis("off")

axes2[2].imshow(dens_uni, cmap="hot", origin="lower")
axes2[2].set_title(
    "Tier1 P1_uniform_RMS (6 freqs)\n"
    f"broad enr={p1u['broad']['enrich']:.2f}×  rec={p1u['broad']['recall']:.2f}",
    fontsize=11,
)
axes2[2].axis("off")

axes2[3].imshow(dens_best, cmap="hot", origin="lower")
axes2[3].set_title(
    f"Tier1 BEST {bc['method']}({sub_str})\n"
    f"broad enr={bc['broad']['enrich']:.2f}×  rec={bc['broad']['recall']:.2f}",
    fontsize=11,
)
axes2[3].axis("off")

plt.suptitle("Apples-to-apples: Tier2 (sr=12) vs Tier1 (sr=3) — Phase 1 best composites", fontsize=13)
plt.tight_layout()
out2 = base / "tier1_vs_tier2_compare.png"
fig2.savefig(out2, dpi=150, bbox_inches="tight")
plt.close(fig2)
print(f"Saved: {out2}")
