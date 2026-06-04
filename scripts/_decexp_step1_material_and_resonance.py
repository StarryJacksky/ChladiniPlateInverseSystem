"""Step 1 (read-only): is the material mismatch systemic, and which freqs SHOULD be driven?

Part A: pair every COMSOL eigfreq JSON with its optimizer w10_optimization_summary;
        compare material (sr/shear) and compute the on-resonance fraction of drive energy.
Part B: for production_design, recommend on-resonance + well-isolated (calibration-robust)
        COMSOL eigenfrequencies, contrasted with the freqs the design actually drives.
"""
from __future__ import annotations
import json, csv
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
MODAL = ROOT / "reports" / "modal_calibration"
ZETA = 0.02  # damping; half-power bandwidth ~ ZETA*f


def jload(p):
    return json.loads(p.read_text(encoding="utf-8"))


def load_col(p):
    if not p.exists():
        return []
    out = []
    for row in csv.reader(p.open(encoding="utf-8")):
        try:
            out.append(float(row[0]))
        except (ValueError, IndexError):
            pass
    return out


# index optimizer summaries by candidate (parent dir name)
w10 = {}
for p in ROOT.rglob("w10_optimization_summary.json"):
    try:
        w10[p.parent.name] = (p, jload(p))
    except Exception:
        pass


def cand_key(eig_filename: str) -> str:
    s = eig_filename.replace("_comsol_eigfreqs.json", "")
    for pre in ("prod_eig_", "phase2_eig_", "modal_calibration_"):
        if s.startswith(pre):
            s = s[len(pre):]
    return s


def onres_fraction(drive, weights, eigs):
    if len(eigs) == 0 or not drive:
        return None
    wtot = sum(weights) or 1.0
    onw = 0.0
    for f, w in zip(drive, weights):
        nearest = float(eigs[int(np.argmin(np.abs(eigs - f)))])
        if abs(f - nearest) <= ZETA * nearest:   # within 1 half-power bandwidth
            onw += w
    return onw / wtot


print("=" * 96)
print("PART A — material consistency (optimizer vs COMSOL) + on-resonance drive fraction")
print("=" * 96)
print(f"{'candidate':<34}{'opt_sr':>8}{'eig_sr':>8}{'opt_shr':>9}{'eig_shr':>9}{'mat':>6}{'onRes%':>9}")
mism = 0; total = 0; offres_designs = []
for ep in sorted(MODAL.glob("*_comsol_eigfreqs.json")):
    e = jload(ep)
    key = e.get("source_candidate") or cand_key(ep.name)
    # strip trailing iteration suffix to find the optimizer dir
    candidates_to_try = [key, key.replace("_p2it1", ""), key.replace("_p2it1", "").replace("_v2", "")]
    w = None
    for k in candidates_to_try:
        if k in w10:
            w = w10[k]; break
    eig_sr = e.get("material_summary", {}).get("stiffness_ratio")
    eig_shr = e.get("material_summary", {}).get("shear_ratio")
    eigs = np.array(e.get("comsol_eigfreqs_hz", []), float)
    if w is None:
        print(f"{cand_key(ep.name):<34}{'?':>8}{eig_sr!s:>8}{'?':>9}{eig_shr!s:>9}{'no-opt':>6}{'-':>9}")
        continue
    wp, wd = w
    opt_sr = wd.get("stiffness_ratio_used"); opt_shr = wd.get("shear_ratio_used")
    drive = load_col(wp.parent / "frequencies_hz.csv")
    weights = load_col(wp.parent / "weights.csv")
    onres = onres_fraction(drive, weights, eigs)
    mat_ok = (opt_sr is not None and eig_sr is not None and abs(float(opt_sr) - float(eig_sr)) < 0.01)
    total += 1
    if not mat_ok:
        mism += 1
    if onres is not None and onres < 0.5:
        offres_designs.append((cand_key(ep.name), onres))
    print(f"{cand_key(ep.name):<34}{opt_sr!s:>8}{eig_sr!s:>8}{opt_shr!s:>9}{eig_shr!s:>9}"
          f"{('OK' if mat_ok else 'MISM'):>6}{(f'{100*onres:.0f}' if onres is not None else '-'):>9}")

print(f"\nmaterial mismatch: {mism}/{total} pairs")
print(f"designs driving <50% energy on-resonance: {len(offres_designs)}")
for k, o in sorted(offres_designs, key=lambda t: t[1]):
    print(f"    {k:<40} on-res {100*o:.0f}%")

print("\n" + "=" * 96)
print("PART B — production_design: recommended on-resonance, calibration-robust drive freqs")
print("=" * 96)
ep = MODAL / "prod_eig_production_design_comsol_eigfreqs.json"
e = jload(ep)
eigs = np.array(e["comsol_eigfreqs_hz"], float)
drive = load_col(ROOT / "reports/production_pla/production_design/frequencies_hz.csv")
weights = load_col(ROOT / "reports/production_pla/production_design/weights.csv")
# isolation of each eigenmode = gap to nearest OTHER eigenmode, in bandwidths
iso = []
for i, f in enumerate(eigs):
    others = np.delete(eigs, i)
    gap = float(np.min(np.abs(others - f)))
    iso.append((f, gap, gap / (ZETA * f)))
# robust = isolated (gap >> bandwidth). Prefer lower freq (sparser, easier to hit, less print-sensitive)
robust = [t for t in iso if t[2] >= 4.0 and t[0] <= 600.0]
robust.sort(key=lambda t: -t[2])
print("current design drive freqs (Hz, weight, on/off vs COMSOL):")
for f, w in zip(drive, weights):
    nearest = float(eigs[int(np.argmin(np.abs(eigs - f)))])
    gbw = abs(f - nearest) / (ZETA * nearest)
    print(f"    {f:8.1f}  w={w:5.3f}   nearest_eig={nearest:7.1f}  ({gbw:4.1f} bw -> {'ON' if gbw<=1 else 'OFF'})")
print("\nrecommended drive freqs = isolated COMSOL eigenmodes <=600Hz (gap>=4 bandwidths):")
print(f"    {'eig_Hz':>9}{'gap_Hz':>9}{'gap/bw':>9}   (higher gap/bw = more robust to material/print error)")
for f, gap, gbw in robust[:10]:
    print(f"    {f:>9.1f}{gap:>9.1f}{gbw:>9.1f}")
if not robust:
    print("    (none — modes too clustered; see modal density below)")
# modal density profile
print("\nmodal density (modes per 100 Hz band):")
for lo in range(0, 1000, 100):
    n = int(((eigs >= lo) & (eigs < lo + 100)).sum())
    print(f"    {lo:4d}-{lo+100:4d} Hz: {'#'*n} ({n})")
