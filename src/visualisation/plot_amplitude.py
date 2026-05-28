"""Lightweight 2D-field PNG renderer used by the Results tab.

Bridges raw ``.npy`` arrays saved by the production pipeline
(``phase1_best_powder_broad.npy`` etc.) into grayscale PNGs the
frontend can display under ``/assets/production/...``. Kept tiny on
purpose — no matplotlib import on this hot path.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image


def render_grayscale_field(arr: np.ndarray, output_path: str | Path, invert: bool = False, target_size: int = 256) -> Path:
    """Render a 2D float array as a grayscale PNG.

    Parameters
    ----------
    arr:
        2D ``np.ndarray`` (any dtype, any shape ≥ 2×2).
    output_path:
        Destination ``.png`` path; parent dirs are created.
    invert:
        If ``True`` brighter pixels = LOWER input values. Use this for raw
        amplitude grids so dark spots highlight nodal lines (where powder
        gathers in the physical experiment).
        If ``False`` brighter pixels = HIGHER input values — natural for
        powder-density maps and binary targets.
    target_size:
        Output side length in pixels (nearest-neighbour resampled).
    """
    out = Path(output_path)
    data = np.asarray(arr, dtype=np.float64)
    if data.ndim != 2:
        raise ValueError(f"render_grayscale_field expects a 2D array, got shape={data.shape}")

    if np.issubdtype(arr.dtype, np.bool_):
        norm = data.astype(np.float64)
    else:
        peak = float(np.max(np.abs(data)))
        if peak > 1.0e-30:
            norm = data / peak
        else:
            norm = data
    norm = np.clip(norm, 0.0, 1.0)
    if invert:
        norm = 1.0 - norm

    img = Image.fromarray((norm * 255.0).astype(np.uint8), mode="L")
    if img.size != (int(target_size), int(target_size)):
        img = img.resize((int(target_size), int(target_size)), Image.NEAREST)

    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    return out


def render_production_pngs(production_dir: str | Path) -> dict[str, Path]:
    """Ensure all renderable ``.npy`` files in a production-run dir have
    an up-to-date PNG twin under ``<production_dir>/previews/``.

    Returns a ``{png_name: full_path}`` map. Cached by mtime — only
    regenerates when the ``.npy`` is newer than its PNG.
    """
    base = Path(production_dir)
    out_dir = base / "previews"
    out_dir.mkdir(parents=True, exist_ok=True)

    # (npy_filename, png_filename, invert)
    catalogue = [
        ("target_resized.npy", "target.png", False),
        ("phase1_best_composite_amp.npy", "phase1_amp.png", True),
        ("phase1_best_powder_broad.npy", "phase1_powder_broad.png", False),
        ("phase1_best_powder_sharp.npy", "phase1_powder_sharp.png", False),
        ("phase2_best_composite_amp.npy", "phase2_amp.png", True),
        ("phase2_best_powder_broad.npy", "phase2_powder_broad.png", False),
        ("phase2_best_powder_sharp.npy", "phase2_powder_sharp.png", False),
    ]
    rendered: dict[str, Path] = {}
    for npy_name, png_name, invert in catalogue:
        npy_path = base / npy_name
        png_path = out_dir / png_name
        if not npy_path.exists():
            continue
        try:
            if png_path.exists() and png_path.stat().st_mtime >= npy_path.stat().st_mtime:
                rendered[png_name] = png_path
                continue
            arr = np.load(npy_path)
            render_grayscale_field(arr, png_path, invert=invert)
            rendered[png_name] = png_path
        except Exception:
            continue
    return rendered
