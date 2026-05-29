"""Re-create the W8-era IC target ("IC" text in Times New Roman Bold, 1024x1024).

Mirrors scripts/create_ic_target.py (Windows-only font path) but uses macOS font.
Then preprocess into 256x256 binary npy under data/processed_targets/target_ic.npy.
"""
from __future__ import annotations
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
FONT = Path("/System/Library/Fonts/Supplemental/Times New Roman Bold.ttf")
OUT_PNG = ROOT / "data/target_patterns/target_ic.png"
OUT_NPY = ROOT / "data/processed_targets/target_ic.npy"


def main() -> int:
    OUT_PNG.parent.mkdir(parents=True, exist_ok=True)
    canvas = 1024
    img = Image.new("RGB", (canvas, canvas), "white")
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(str(FONT), 520)
    text = "IC"
    box = draw.textbbox((0, 0), text, font=font)
    tw, th = box[2] - box[0], box[3] - box[1]
    x = (canvas - tw) // 2 - box[0]
    y = (canvas - th) // 2 - box[1]
    draw.text((x, y), text, font=font, fill=(0, 37, 93))
    img.save(OUT_PNG)
    print(f"[wrote] {OUT_PNG}")

    # Downsample to 256x256 and binarize (mirror src/target/preprocess_target.py behaviour)
    small = img.convert("L").resize((256, 256), Image.LANCZOS)
    arr = np.asarray(small, dtype=np.uint8)
    binary = (arr < 200).astype(np.uint8)  # foreground = dark text
    OUT_NPY.parent.mkdir(parents=True, exist_ok=True)
    np.save(OUT_NPY, binary)
    print(f"[wrote] {OUT_NPY} (sum={int(binary.sum())}, area={100*binary.mean():.1f}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
