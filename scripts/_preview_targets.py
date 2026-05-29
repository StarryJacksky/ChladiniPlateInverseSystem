"""Preview all available targets for battery selection."""
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
TARGETS = [
    ("target_binary",   "data/processed_targets/target_binary.npy",   "8-elem复杂"),
    ("target_cross",    "data/processed_targets/target_cross.npy",    "十字 D4"),
    ("target_diagonal", "data/processed_targets/target_diagonal.npy", "对角线 D2"),
    ("target_xform",    "data/processed_targets/target_xform.npy",    "形变"),
    ("star_outline",    "data/_d_verify_targets/star_outline.npy",    "五角星轮廓"),
]
fig, axes = plt.subplots(1, 5, figsize=(20, 4.5))
for ax, (name, p, desc) in zip(axes, TARGETS):
    arr = np.load(ROOT / p)
    ax.imshow(arr, cmap="gray_r")
    ax.set_title(f"{name}\n{desc} — {100*arr.mean():.1f}% area", fontsize=11)
    ax.axis("off")
fig.suptitle("Available targets for material battery test", fontsize=13)
fig.tight_layout()
OUT = ROOT / "reports" / "_material_comparison" / "available_targets.png"
fig.savefig(OUT, dpi=130, bbox_inches="tight")
print(f"[wrote] {OUT}")
