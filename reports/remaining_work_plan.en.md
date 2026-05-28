# Remaining Work Plan

[Language](./remaining_work_plan.md): [Bilingual](./remaining_work_plan.md) | [中文](./remaining_work_plan.zh-CN.md) | English

> Algorithm-breakthrough roadmap lives in [`algorithm_breakthrough_plan.en.md`](./algorithm_breakthrough_plan.en.md). This document covers only maintenance work and tasks waiting for external inputs.

This document separates tasks Codex can continue now from tasks blocked by real material, COMSOL, or physical-test data.

## A. Can Continue Independently

The independent development queue is now mostly quality maintenance rather than new feature construction.

### 1. Quality Gate Maintenance

Tasks:

1. Run `python scripts/check_local_quality.py` after every meaningful code or documentation change.
2. Keep the bilingual comment checker passing for hand-written `.py`, `.m`, and `.html` files.
3. Extend the local quality bundle only when a new repeatable local check appears.

Completed foundation:

- The quality bundle now covers documentation links, bilingual comments, config contracts, discovery fixtures, artifact cleanup, Python-only smoke tests, Python compilation, and optional frontend syntax checks.

### 2. Documentation Maintenance

Tasks:

1. Keep the root README as the short bilingual entry page that links into user-facing guides.
2. Keep the deployment guide, user manual, code-structure guide, and planning reports synchronized with any later implementation changes.
3. Add final screenshots and lab-specific notes only after the UI and COMSOL workflow are stable.

Completed foundation:

- Beginner-facing bilingual docs now exist for setup, software use, project structure, local checks, run reports, and remaining work.

### 3. Visual Verification When Available

Tasks:

1. Re-open the local app in a browser once local server approval or another usable preview route is available.
2. Check desktop and narrow layouts for Target, Tune, Results, and Run.
3. Capture final screenshots for README and user manual only after the interface is no longer changing quickly.

Current note:

- The recent local preview attempt was blocked by local server/file preview permissions, so this item is waiting on a usable preview path rather than more implementation code.

## B. Needs Real Project Data Later

### 1. Material Calibration

Needs measured or trusted values for density, Young's modulus, Poisson ratio, and thermal parameters.

### 2. COMSOL Baseline Freeze

Needs the final MPH model, final hole/spacer assumptions, final boundary naming, and final fixed constraints.

### 3. Physical Validation

Needs measured plate frequencies, excitation setup, and photographed or extracted physical nodal patterns.

### 4. Optimization Tuning

Needs enough COMSOL results to tune scoring weights, random search settings, and genetic algorithm operators.

### 5. Clean Machine Validation

Needs real Windows, macOS, and Linux machines, or equivalent clean virtual machines, with actual COMSOL/MATLAB installations to confirm discovery behavior.

### 6. Final Release Guide

Needs stable UI screenshots, final install paths, final lab-specific COMSOL/MATLAB notes, and confirmed troubleshooting cases.

## C. Current Waiting Boundary

Codex is now close to the planned waiting boundary.

Most meaningful new work now needs one of these inputs: the accepted final MPH model, real material values, real COMSOL output images/CSV data, physical validation measurements, clean OS validation machines, or a working local browser preview route.

Until then, the safe independent work is maintenance: keep docs synchronized, keep checks passing, and avoid inventing model-specific assumptions that could fight the real COMSOL baseline.
