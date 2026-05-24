# User Manual

[Language](./user_manual.md): [Bilingual](./user_manual.md) | [中文](./user_manual.zh-CN.md) | English

This manual explains the current Chladni Studio workflow.

## 1. What the Software Does

Chladni Studio helps users turn a desired visual pattern into candidate stepped-thickness plate designs.

```text
target image -> preprocessing -> thickness candidates -> COMSOL/MATLAB simulation -> scoring -> ranked results
```

## 2. Main Screen

The main screen has a drawing canvas on the left and control tabs on the right.

Top controls:

- `Brush`: draw dark target strokes.
- `Erase`: erase strokes.
- `Width`: change brush width.
- `Stroke`: use strokes as nodal-line targets.
- `Edge`: extract edges from filled logos or photos.
- `Filled`: use the filled region itself as the target.
- `Import`: load a PNG/JPEG/WebP image.
- `Save`: save and preprocess the target.

## 3. Target Tab

Use this tab to prepare the user-defined pattern.

Recommended target images:

- High contrast.
- Simple enough for a first search.
- Not too tiny or too filled.
- Avoid many isolated small pieces in the first loop.

`Target Quality` shows:

- Processed preview.
- Foreground area percentage.
- Connected component count.
- First-loop suitability recommendation.
- Warnings for fine detail, complexity, and area balance.

If the recommendation is `Late-stage target`, use it later after the optimization loop is stable, or simplify the image first.

## 4. Tune Tab

Use this tab to edit material and scoring parameters.

Material parameters:

- Density.
- Young's modulus.
- Poisson ratio.
- Thermal conductivity.
- Heat capacity.
- Thermal expansion.

Scoring parameters:

- Roughness weight.
- Mass weight.
- Frequency weight.
- Frequency range.

Press `Apply` after changing material or scoring values.

## 5. Run Tab

Use this tab to run the automatic pipeline.

Run presets:

- `Smoke`: 1 candidate, 3 modes. Use for quick checks.
- `Review`: 3 candidates, 10 modes. Use for short comparison runs.
- `Full`: 12 candidates, 20 modes. Use for a fuller local search.

`Run COMSOL`:

- On: run the COMSOL/MATLAB bridge.
- Off: run the Python-side workflow without COMSOL simulation.

Preflight checks:

- Candidate count must be from 1 to 100.
- Mode count must be from 1 to 60.
- The target should be saved once so preprocessing metrics exist.
- If `Run COMSOL` is enabled, diagnostics should be ready.

Diagnostics:

- `Refresh`: checks paths, model, runner, timeout settings, and mphserver reachability.
- `Self-test`: runs a safer Python-only deployment check.

Timeline and Logs:

- Timeline shows queued, target preparation, candidate generation, simulation, scoring, done, and error stages.
- Logs show recent COMSOL/MATLAB output tails.

Artifacts:

- Shows generated file sizes.
- Previews cleanup candidates.
- Cleans only regenerable or temporary files covered by the retention policy.

## 6. Results Tab

Use this tab to inspect scored candidates.

You can:

- Search candidates by ID.
- Sort by rank, score, IoU, Dice, or frequency.
- Filter by minimum IoU.
- Open target/simulated/overlay images in a larger viewer.
- Switch between scored modes.
- Open a readable candidate report.
- Download a candidate result package.

The best candidate is not always the highest IoU candidate, because the final score can include roughness, mass, and frequency penalties.

## 7. Typical Beginner Workflow

1. Launch Chladni Studio.
2. Draw or import a simple target.
3. Choose `Edge` for filled logos/photos, or `Stroke` for hand-drawn lines.
4. Click `Save`.
5. Check `Target Quality`.
6. Open `Tune` and confirm material/scoring settings.
7. Open `Run`, choose `Smoke`, and click `Run`.
8. If the smoke run works, try `Review` or `Full`.
9. Open `Results` and inspect the best candidates.

## 8. Reading Results

Important metrics:

- IoU: overlap between simulated nodal region and target.
- Dice: another similarity measure, often easier to compare visually.
- Frequency: exported modal frequency from COMSOL.
- Final score: similarity minus penalties.

Use the overlay image first for quick visual judgment, then compare metrics.

## 9. Current Limitations

These items depend on future real project data:

- Final material presets.
- Physical frequency validation.
- Final COMSOL model acceptance.
- Official release screenshots.

The current manual is therefore a development-version manual.
