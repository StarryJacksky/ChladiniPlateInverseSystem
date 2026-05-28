"""Verify Phase 2 anti-collapse fix: composite (enr·√rec) rejects the
"collapsed-to-bright-dot" pseudo-improvement that legacy enrich-only accepts.

Simulates 5 representative best_composite payloads:
  P1 baseline   (faithful 4-pointed star)
  Collapse      (single bright spot, high enr / low rec) -- THE BUG
  Genuine win   (better enr AND recall)
  Recall trade  (slightly lower enr, much better recall)
  Drift         (slightly lower both -- should always reject)

Expected: composite REJECTS the collapse, enrich_only ACCEPTS it (bug).
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.optimisation.production_pipeline import _phase2_score


def mk(be, br, te=None, tr=None):
    if te is None: te = be * 0.8
    if tr is None: tr = br * 0.7
    return {"broad": {"enrich": be, "recall": br},
            "tight": {"enrich": te, "tight": tr}}


CASES = [
    ("P1 baseline",       mk(3.00, 0.60)),
    ("Collapse (bug)",    mk(4.50, 0.20)),
    ("Genuine win",       mk(3.50, 0.65)),
    ("Recall trade",      mk(2.80, 0.75)),
    ("Drift down",        mk(2.80, 0.55)),
]


def run(score_mode: str) -> dict:
    baseline_bc = CASES[0][1]
    baseline_score = _phase2_score(baseline_bc, score_mode)["score"]
    rows = []
    for name, bc in CASES:
        s = _phase2_score(bc, score_mode)
        delta = s["score"] - baseline_score
        accepted = delta > 0
        rows.append({"name": name, "score": s["score"], "enr": s["broad_enrich"],
                     "rec": s["broad_recall"], "delta": delta, "accepted": accepted})
    return {"baseline_score": baseline_score, "rows": rows}


def main() -> int:
    print("=" * 92)
    print(f"{'case':<24} | {'broad enr':>9} {'rec':>5} | "
          f"{'enr-only score':>15} {'accept':>7} | "
          f"{'composite score':>16} {'accept':>7}")
    print("=" * 92)

    enr_only = run("enrich_only")
    comp = run("composite")

    fail = False
    for r_e, r_c in zip(enr_only["rows"], comp["rows"]):
        name = r_e["name"]
        enr = r_e["enr"]
        rec = r_e["rec"]
        e_score = r_e["score"]
        c_score = r_c["score"]
        e_ok = "ACCEPT" if r_e["accepted"] else "reject"
        c_ok = "ACCEPT" if r_c["accepted"] else "reject"
        print(f"{name:<24} | {enr:>9.2f} {rec:>5.2f} | "
              f"{e_score:>15.3f} {e_ok:>7} | "
              f"{c_score:>16.3f} {c_ok:>7}")
    print("=" * 92)

    print("\n--- Expected behaviour ---")
    expected = [
        ("P1 baseline",  "reject", "reject"),
        ("Collapse (bug)", "ACCEPT", "reject"),
        ("Genuine win", "ACCEPT", "ACCEPT"),
        ("Recall trade", "reject", "ACCEPT"),
        ("Drift down",  "reject", "reject"),
    ]
    for (name, exp_e, exp_c), r_e, r_c in zip(expected, enr_only["rows"], comp["rows"]):
        got_e = "ACCEPT" if r_e["accepted"] else "reject"
        got_c = "ACCEPT" if r_c["accepted"] else "reject"
        ok_e = got_e == exp_e
        ok_c = got_c == exp_c
        marker_e = "OK" if ok_e else "FAIL"
        marker_c = "OK" if ok_c else "FAIL"
        if not ok_e or not ok_c: fail = True
        print(f"  {name:<22} enr_only: expect {exp_e:>6} got {got_e:>6} [{marker_e:>4}]  "
              f"composite: expect {exp_c:>6} got {got_c:>6} [{marker_c:>4}]")

    print()
    if fail:
        print("RESULT: FAIL — at least one acceptance disagrees with expectation.")
        return 1
    print("RESULT: PASS — composite rejects collapse, enrich-only would accept it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
