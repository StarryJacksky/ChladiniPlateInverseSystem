# Remaining Work Plan

[Language](./remaining_work_plan.md): [Bilingual](./remaining_work_plan.md) | [中文](./remaining_work_plan.zh-CN.md) | English

This document separates tasks Codex can continue now from tasks blocked by real material, COMSOL, or physical-test data.

## A. Can Continue Now

### 1. Frontend Design Polish

Goal: make the app feel like a serious engineering design console, not a temporary debug page.

Tasks:

1. Unify visual hierarchy across Target, Tune, Results, and Run tabs.
2. Keep the first screen as the usable workspace, not a marketing page.
3. Verify desktop and narrow layouts in the browser after local server approval is available.

Recently completed:

- Run Overview now includes a clear next-action strip so users know whether to run Smoke, Discover paths, check model files, or run Self-test.

### 2. Frontend Function Completion

Goal: let users draw/import, run, inspect, and compare without opening files manually.

Tasks:

1. Add deeper multi-candidate visual comparison once more real COMSOL images are available.
2. Add final screenshot-driven walkthroughs after the UI stops moving.

Recently completed:

- Result overview now explains ranking, shows a top-candidate comparison strip, and links to a full run report.
- Target Quality now gives practical guidance for imported photos, logos, and dense hand drawings.

### 3. Automation Robustness

Goal: make the Run tab predictable before asking users to trust one-click automation.

Tasks:

1. Validate COMSOL/MATLAB running-process detection and install-path discovery on clean Windows, macOS, and Linux machines.
2. Add deeper model-specific preflight checks after the final COMSOL model is frozen.
3. Keep Python-only self-test independent from COMSOL/MATLAB execution.

Recently completed:

- Frontend setup assistant for COMSOL/MATLAB discovery, path confirmation, and diagnostics verification.
- Safe local Stop pathway with persisted cancelling/cancelled workflow state.
- Backend recovery hints that combine workflow state, diagnostics, and recent COMSOL/MATLAB logs.

### 4. Backend Checks and Contracts

Goal: catch configuration problems before expensive COMSOL/MATLAB runs.

Tasks:

1. Prefer already-running processes, then known install folders, then manual override in the setup flow.
2. Add manual override fields to the setup wizard when discovery fails.
3. Keep cleanup behavior covered by automated tests as artifact policy evolves.

Recently completed:

- Config contract diagnostics for geometry, thickness, material, simulation, optimisation, paths, and COMSOL port values.
- Discovery tests for install-path fixtures, missing configured paths, and running-process priority.
- Non-invasive COMSOL/MATLAB version hints now recognise macOS, Windows, and Linux install-path formats.
- License diagnostics now tell users to open COMSOL/MATLAB once after install to confirm login or license state.
- Artifact cleanup checks now verify that old regenerable files and temporary workflow files are cleanable while newest generations and mode CSV data stay protected.

### 5. Documentation Drafts

Goal: make GitHub understandable before final screenshots and lab-specific values exist.

Tasks:

1. Keep README as a short entry page.
2. Maintain the Windows/macOS/Linux deployment guide in `docs/deployment_guide.md`.
3. Maintain the software user manual in `docs/user_manual.md`.
4. Add final screenshots later after UI stops moving.

Recently completed:

- Added a documentation link checker so README and guide entry links can be validated automatically.

### 6. Python-Only Smoke Test Path

Goal: let new users verify the app without COMSOL first.

Tasks:

1. Confirm clone/install/self-test/launch workflow on a clean environment.
2. Confirm UI target import and refresh manually after final screenshots are ready.

Recently completed:

- Added `scripts/check_python_smoke.py` to verify target preprocessing and candidate generation in a temporary directory without COMSOL.
- Documented expected smoke-test files in the deployment guide.

## B. Needs Real Project Data Later

### 1. Material Calibration

Needs measured or trusted values for density, Young's modulus, Poisson ratio, and thermal parameters.

### 2. COMSOL Baseline Freeze

Needs the final MPH model, final hole/spacer assumptions, final boundary naming, and final fixed constraints.

### 3. Physical Validation

Needs measured plate frequencies, excitation setup, and photographed or extracted physical nodal patterns.

### 4. Optimization Tuning

Needs enough COMSOL results to tune scoring weights, random search settings, and genetic algorithm operators.

### 5. Final Release Guide

Needs stable UI screenshots, final install paths, final lab-specific COMSOL/MATLAB notes, and confirmed troubleshooting cases.

## C. Current Waiting Boundary

Codex is not yet blocked.

Continue with: frontend polish, Python-only smoke validation, non-invasive version inference, backend config hardening, and documentation refinement.

Only after those are complete should the project wait mainly for real material data, final COMSOL model acceptance, and physical validation data.
