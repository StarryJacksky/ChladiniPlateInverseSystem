"""Quick visualisation of an orthotropic smoke test output."""
from __future__ import annotations
import os, sys
from pathlib import Path
Path("data/.matplotlib_cache").mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(Path("data/.matplotlib_cache").resolve()))
os.environ.setdefault("MPLBACKEND", "Agg")

import numpy as np
import matplotlib.pyplot as plt
from src.scoring.recognisability_score import chladni_powder_density

amp_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("reports/w10_comsol_validation/orthotropic_smoke/w10_ic_tier2_sr12/composite_amplitude.npy")
amp = np.load(amp_path)
print(f"amp shape={amp.shape} dtype={amp.dtype} max={np.abs(amp).max():.3e} mean={np.abs(amp).mean():.3e}")

target = np.load("data/processed_targets/target_binary.npy")
from PIL import Image
tgt_img = Image.fromarray((target.astype(np.uint8) * 255))
tgt_img = tgt_img.resize(amp.shape[::-1], resample=Image.NEAREST)
target_amp = (np.array(tgt_img) > 127).astype(bool)

powder = chladni_powder_density(amp, sigma_rel=0.05)

fig, axes = plt.subplots(1, 3, figsize=(15, 5))
im0 = axes[0].imshow(np.abs(amp), cmap="viridis", origin="upper")
axes[0].set_title(f"COMSOL amplitude (orthotropic)\n shape={amp.shape}")
plt.colorbar(im0, ax=axes[0])
axes[0].axis("off")

im1 = axes[1].imshow(powder, cmap="hot", origin="upper")
axes[1].set_title("Chladni powder density")
axes[1].axis("off")

overlay = np.zeros((*amp.shape, 3))
overlay[..., 0] = powder / max(powder.max(), 1e-9)
overlay[..., 2] = target_amp.astype(float)
axes[2].imshow(overlay, origin="upper")
axes[2].set_title("powder (red) vs target (blue)")
axes[2].axis("off")

output = amp_path.parent / "smoke_viz.png"
plt.tight_layout()
plt.savefig(output, dpi=120, bbox_inches="tight")
print(f"saved {output}")
