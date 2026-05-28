"""Extended production-pipeline artefact renderers.

Two kinds of outputs land in ``<production_dir>/previews/``:

* **Physical** (the headline images for the Candidate panel):
  ``surrogate_amp.png``, ``surrogate_powder_broad.png``,
  ``surrogate_powder_sharp.png``, ``overlay_target_achieved.png``
  — computed by running the orthotropic Kirchhoff surrogate forward
  on the saved (H, θ, frequencies, weights). Generated for *every*
  production run, so the user sees the achieved Chladni pattern even
  for surrogate-only stages that never invoked COMSOL.

* **Diagnostic** (folded into a collapsible "Advanced" block in the UI):
  ``theta_field.png``, ``w10_loss_curve.png``, ``w10_frequencies.png``
  — research-facing summaries of the W10 optimiser state.

Kept separate from ``plot_amplitude.py`` because matplotlib + torch are
heavy imports that should not land on the ``GET /api/production-runs``
hot path.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image

import matplotlib
matplotlib.use("Agg")  # headless / 无显示后端
import matplotlib.pyplot as plt

from src.visualisation.plot_amplitude import render_grayscale_field


def render_theta_field(theta_deg: np.ndarray, output_path: str | Path) -> Path:
    """Render a fibre-orientation field as a cyclic-colormap heatmap.

    Angles are wrapped into [0, 180°) before display because the
    underlying orthotropic plate is symmetric under θ → θ + 180°.
    """
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    arr = np.mod(np.asarray(theta_deg, dtype=np.float64), 180.0)
    rows, cols = arr.shape
    fig, ax = plt.subplots(figsize=(4.6, 4.6), dpi=120)
    im = ax.imshow(arr, cmap="twilight", vmin=0, vmax=180, interpolation="nearest")
    if rows <= 20 and cols <= 20:
        for r in range(rows):
            for c in range(cols):
                v = arr[r, c]
                # legible-on-twilight contrast switch / 在 twilight 上保证对比
                colour = "white" if 50.0 <= v <= 130.0 else "black"
                ax.text(c, r, f"{v:.0f}", ha="center", va="center", fontsize=6, color=colour)
    cbar = fig.colorbar(im, ax=ax, ticks=[0, 45, 90, 135, 180], fraction=0.046, pad=0.04)
    cbar.set_label("Fibre angle (°, wrapped)", fontsize=9)
    ax.set_title(f"Fibre orientation θ ({rows}×{cols})", fontsize=10)
    ax.set_xticks([])
    ax.set_yticks([])
    fig.tight_layout()
    fig.savefig(out, dpi=120, bbox_inches="tight")
    plt.close(fig)
    return out


def render_w10_loss_curve(trace: dict, best_step: int | None, output_path: str | Path) -> Path:
    """Render the W10 optimisation trace as a dual-axis chart.

    Left axis: total loss (lower = better, red).
    Right axis: enrichment (× factor, teal) and recall (fraction, blue dashed).
    Best step highlighted with a vertical dotted line.
    """
    losses = list(trace.get("total_loss", []))
    if not losses:
        raise ValueError("Empty W10 trace — nothing to render.")
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    steps = np.arange(len(losses))
    fig, ax = plt.subplots(figsize=(6.6, 3.6), dpi=120)
    ax.plot(steps, losses, label="total loss", color="#c0392b", linewidth=1.7)
    ax.set_xlabel("optimisation step")
    ax.set_ylabel("loss (lower = better)", color="#c0392b")
    ax.tick_params(axis="y", labelcolor="#c0392b")
    ax.grid(True, alpha=0.3)
    ax2 = ax.twinx()
    if trace.get("enrichment"):
        ax2.plot(steps, trace["enrichment"], label="enrichment ×", color="#1f6f64", linewidth=1.4)
    if trace.get("recall"):
        ax2.plot(steps, trace["recall"], label="recall", color="#2c6fa3", linewidth=1.2, linestyle="--")
    ax2.set_ylabel("enrichment × / recall", color="#1f6f64")
    ax2.tick_params(axis="y", labelcolor="#1f6f64")
    if best_step is not None and 0 <= int(best_step) < len(steps):
        bs = int(best_step)
        ax.axvline(bs, color="black", alpha=0.4, linestyle=":", linewidth=1)
        ax.annotate(
            f"best step={bs}",
            xy=(bs, losses[bs]),
            xytext=(6, 8),
            textcoords="offset points",
            fontsize=8,
            color="black",
        )
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    if h1 or h2:
        ax.legend(h1 + h2, l1 + l2, fontsize=8, loc="lower left")
    ax.set_title("W10 optimisation trace", fontsize=10)
    fig.tight_layout()
    fig.savefig(out, dpi=120, bbox_inches="tight")
    plt.close(fig)
    return out


def render_frequency_weights(
    freqs_hz: np.ndarray,
    weights: np.ndarray,
    output_path: str | Path,
) -> Path:
    """Render the W10 drive frequencies + final weights as a bar chart."""
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    freqs = np.asarray(freqs_hz, dtype=np.float64).ravel()
    ws = np.asarray(weights, dtype=np.float64).ravel()
    n = int(min(len(freqs), len(ws)))
    if n == 0:
        raise ValueError("No frequencies or weights to render.")
    freqs = freqs[:n]
    ws = ws[:n]
    x = np.arange(n)
    fig, ax = plt.subplots(figsize=(6.6, 3.1), dpi=120)
    bars = ax.bar(x, ws, color="#1f6f64", alpha=0.85, edgecolor="white", linewidth=1)
    for bar, freq, weight in zip(bars, freqs, ws):
        ax.text(
            bar.get_x() + bar.get_width() / 2.0,
            bar.get_height() + 0.005,
            f"{freq:.0f} Hz\nw={weight:.2f}",
            ha="center",
            va="bottom",
            fontsize=8,
        )
    ax.set_xticks(x)
    ax.set_xticklabels([f"f{i + 1}" for i in range(n)])
    ax.set_ylabel("weight (final)")
    ax.set_ylim(0, max(float(ws.max()) * 1.45, 0.25))
    ax.grid(True, axis="y", alpha=0.3)
    ax.set_title("W10 drive frequencies + weights", fontsize=10)
    fig.tight_layout()
    fig.savefig(out, dpi=120, bbox_inches="tight")
    plt.close(fig)
    return out


def render_target_achieved_overlay(
    target_mask: np.ndarray,
    achieved_field: np.ndarray,
    output_path: str | Path,
    target_size: int = 256,
) -> Path:
    """RGB overlay: red = target, green = achieved (powder density), yellow = overlap.

    Both inputs are resampled to ``target_size × target_size`` first
    (nearest for the boolean target, bilinear for the achieved field)
    so the user can visually judge how well the design matches the
    intent.
    """
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    tgt = np.asarray(target_mask).astype(np.float32)
    if tgt.max() > 1.0:
        tgt = tgt / float(tgt.max())
    tgt_img = Image.fromarray((np.clip(tgt, 0.0, 1.0) * 255.0).astype(np.uint8), mode="L")
    if tgt_img.size != (target_size, target_size):
        tgt_img = tgt_img.resize((target_size, target_size), Image.NEAREST)
    tgt_arr = np.asarray(tgt_img, dtype=np.uint8)

    ach = np.asarray(achieved_field, dtype=np.float64)
    peak = float(np.max(np.abs(ach)))
    ach_norm = ach / peak if peak > 1.0e-30 else ach
    ach_norm = np.clip(ach_norm, 0.0, 1.0)
    ach_img = Image.fromarray((ach_norm * 255.0).astype(np.uint8), mode="L")
    if ach_img.size != (target_size, target_size):
        ach_img = ach_img.resize((target_size, target_size), Image.BILINEAR)
    ach_arr = np.asarray(ach_img, dtype=np.uint8)

    # R = target, G = achieved (so overlap renders as bright yellow)
    rgb = np.zeros((target_size, target_size, 3), dtype=np.uint8)
    rgb[..., 0] = tgt_arr
    rgb[..., 1] = ach_arr

    Image.fromarray(rgb, mode="RGB").save(out)
    return out


def render_surrogate_achieved(
    production_dir: str | Path,
    config: dict,
) -> dict[str, Path]:
    """Run the orthotropic surrogate forward on the saved design and render the
    achieved Chladni-like response + powder densities + target overlay.

    Renders only the PNGs that don't already exist or whose source files
    (H.csv / theta CSV / frequencies / weights) have been touched since
    the PNG was last written. Heavy torch + matplotlib work is gated by
    these mtime checks so opening the Candidate panel is fast on warm
    cache.
    """
    base = Path(production_dir)
    out_dir = base / "previews"
    out_dir.mkdir(parents=True, exist_ok=True)
    rendered: dict[str, Path] = {}

    h_csv = base / "H.csv"
    theta_csv = base / "theta_continuous_rad.csv"
    freqs_csv = base / "frequencies_hz.csv"
    weights_csv = base / "weights.csv"
    summary_path = base / "production_summary.json"
    target_npy = base / "target_resized.npy"

    if not (h_csv.exists() and theta_csv.exists() and freqs_csv.exists() and weights_csv.exists()):
        return rendered

    sources = [h_csv, theta_csv, freqs_csv, weights_csv]
    if summary_path.exists():
        sources.append(summary_path)
    latest_src_mtime = max(p.stat().st_mtime for p in sources)
    targets = [
        out_dir / "surrogate_amp.png",
        out_dir / "surrogate_powder_broad.png",
        out_dir / "surrogate_powder_sharp.png",
    ]
    overlay_target = out_dir / "overlay_target_achieved.png"
    all_fresh = all(p.exists() and p.stat().st_mtime >= latest_src_mtime for p in targets)
    overlay_fresh = (
        (not target_npy.exists())
        or (overlay_target.exists() and overlay_target.stat().st_mtime >= latest_src_mtime)
    )

    if not all_fresh or not overlay_fresh:
        try:
            import torch  # 延迟导入 / Lazy import
            from src.physics.orthotropic_plate import OrthotropicPlate  # 延迟导入 / Lazy import
            from src.physics.recognisability_loss import compose_multifreq_amplitude_with_weights  # 延迟导入 / Lazy import
            from src.scoring.recognisability_score import chladni_powder_density  # 延迟导入 / Lazy import
        except Exception:
            return rendered

        try:
            H_mm = np.loadtxt(h_csv, delimiter=",")
            theta_rad = np.loadtxt(theta_csv, delimiter=",")
            freqs = np.loadtxt(freqs_csv, delimiter=",", skiprows=1)
            weights = np.loadtxt(weights_csv, delimiter=",", skiprows=1)
            freqs = np.atleast_1d(freqs)
            weights = np.atleast_1d(weights)
        except Exception:
            return rendered

        # Material parameters: prefer those recorded by W10 so the forward pass
        # reproduces the optimiser's view; fall back to ``config.material`` so
        # legacy summaries still render. / 优先使用 W10 记录的材料参数复现优化器视角，否则回退到 config.material
        w10 = {}
        if summary_path.exists():
            try:
                w10 = (json.loads(summary_path.read_text(encoding="utf-8")) or {}).get("w10_summary") or {}
            except Exception:
                w10 = {}
        proxy_grid_size = int(w10.get("proxy_grid_size", 25))
        damping_ratio = float(w10.get("damping_ratio", 0.02))
        stiffness_ratio = float(w10.get("stiffness_ratio_used", config.get("material", {}).get("stiffness_ratio", 1.05)))
        shear_ratio = float(w10.get("shear_ratio_used", config.get("material", {}).get("shear_ratio", 1.0)))
        f_min = float(w10.get("f_min_hz", 120.0))
        f_max = float(w10.get("f_max_hz", 1200.0))

        try:
            plate = OrthotropicPlate(
                config,
                proxy_grid_size=proxy_grid_size,
                default_damping=damping_ratio,
                reference_frequency_hz=0.5 * (f_min + f_max),
                stiffness_ratio=stiffness_ratio,
                shear_ratio=shear_ratio,
                dtype=torch.float64,
                device="cpu",
            )
            H_t = torch.from_numpy(H_mm.astype(np.float64))
            theta_t = torch.from_numpy(theta_rad.astype(np.float64))
            per_freq: list[torch.Tensor] = []
            with torch.no_grad():
                for f in freqs:
                    amp = plate.amplitude_at_frequency(
                        H_t,
                        theta_t,
                        torch.tensor(float(f), dtype=torch.float64),
                        damping_ratio=damping_ratio,
                    )
                    per_freq.append(amp)
            weights_t = torch.tensor(weights.astype(np.float64))
            composite_t = compose_multifreq_amplitude_with_weights(per_freq, weights_t)
            composite = composite_t.cpu().numpy()
        except Exception:
            return rendered

        try:
            render_grayscale_field(composite, targets[0], invert=True)
            powder_broad = chladni_powder_density(composite, sigma_rel=0.05)
            powder_sharp = chladni_powder_density(composite, sigma_rel=0.025)
            render_grayscale_field(powder_broad, targets[1], invert=False)
            render_grayscale_field(powder_sharp, targets[2], invert=False)
            if target_npy.exists():
                try:
                    target_mask = np.load(target_npy)
                    render_target_achieved_overlay(target_mask, powder_broad, overlay_target)
                except Exception:
                    pass
        except Exception:
            return rendered

    for png_name, path in [
        ("surrogate_amp.png", targets[0]),
        ("surrogate_powder_broad.png", targets[1]),
        ("surrogate_powder_sharp.png", targets[2]),
        ("overlay_target_achieved.png", overlay_target),
    ]:
        if path.exists():
            rendered[png_name] = path
    return rendered


def render_production_artefacts(
    production_dir: str | Path,
    config: dict | None = None,
) -> dict[str, Path]:
    """Render every diagnostic + physical-image PNG for a production-run dir.

    Caches by mtime; only regenerates when the source CSV / JSON is
    newer than the PNG twin. Returns ``{png_name: full_path}`` for
    every artefact successfully rendered.

    The surrogate-forward physical images are skipped when ``config``
    is ``None`` (callers that only need diagnostics can avoid loading
    the project config).
    """
    base = Path(production_dir)
    out_dir = base / "previews"
    out_dir.mkdir(parents=True, exist_ok=True)
    rendered: dict[str, Path] = {}
    summary_path = base / "production_summary.json"

    theta_csv = base / "theta_continuous_deg.csv"
    if theta_csv.exists():
        theta_png = out_dir / "theta_field.png"
        try:
            stale = (not theta_png.exists()) or (theta_png.stat().st_mtime < theta_csv.stat().st_mtime)
            if stale:
                arr = np.loadtxt(theta_csv, delimiter=",")
                if arr.ndim == 2:
                    render_theta_field(arr, theta_png)
            if theta_png.exists():
                rendered["theta_field.png"] = theta_png
        except Exception:
            pass

    if summary_path.exists():
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        except Exception:
            summary = {}
        w10 = (summary or {}).get("w10_summary") or {}
        trace = w10.get("trace") or {}
        loss_png = out_dir / "w10_loss_curve.png"
        if trace.get("total_loss"):
            try:
                stale = (not loss_png.exists()) or (loss_png.stat().st_mtime < summary_path.stat().st_mtime)
                if stale:
                    render_w10_loss_curve(trace, w10.get("best_step"), loss_png)
                if loss_png.exists():
                    rendered["w10_loss_curve.png"] = loss_png
            except Exception:
                pass

        freqs = w10.get("frequencies_hz") or (summary or {}).get("frequencies_hz") or []
        weights = w10.get("weights") or (summary or {}).get("weights") or []
        if freqs and weights and len(freqs) == len(weights):
            freq_png = out_dir / "w10_frequencies.png"
            try:
                stale = (not freq_png.exists()) or (freq_png.stat().st_mtime < summary_path.stat().st_mtime)
                if stale:
                    render_frequency_weights(np.asarray(freqs), np.asarray(weights), freq_png)
                if freq_png.exists():
                    rendered["w10_frequencies.png"] = freq_png
            except Exception:
                pass

    if config is not None:
        try:
            rendered.update(render_surrogate_achieved(base, config))
        except Exception:
            pass

    return rendered
