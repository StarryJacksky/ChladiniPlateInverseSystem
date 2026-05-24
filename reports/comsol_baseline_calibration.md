# COMSOL Baseline Model Calibration

This document is the checklist for aligning the baseline COMSOL `.mph` model with the Python inverse-design code before further optimisation development.

## 1. Purpose

The current task is calibration and planning, not LiveLink automation. The baseline model should first prove that one candidate can travel through this manual loop:

```text
Python candidate H.csv
-> COMSOL parameter update
-> eigenfrequency study
-> exported mode CSV files
-> Python validation
-> Python scoring
```

## 2. Geometry Checks

Confirm these items in the `.mph` model:

```text
1. The plate is 150 mm x 150 mm, matching config.yaml.
2. The design area is divided into a 15 x 15 thickness grid.
3. Each cell maps to exactly one thickness parameter.
4. The central clamped region is represented consistently with an 8 mm radius assumption.
5. The central clamp does not accidentally become a tunable optimisation region.
6. The thickness field is stepwise, not smoothly interpolated between cells.
7. Boundary/support settings match the intended Chladni plate experiment.
```

## 3. Parameter Naming Contract

Python currently exports `comsol_parameters.csv` with names like:

```text
h0101, h0102, ..., h1515
```

The COMSOL model should use the same names. The earlier `h_1_1` style is intentionally avoided because COMSOL can interpret repeated underscore-style parameter names as duplicate global `h` variables during equation compilation.

## 4. Python To COMSOL Import Check

For a generated candidate folder:

```text
candidates/candidate_000_0000/H.csv
candidates/candidate_000_0000/comsol_parameters.csv
```

Check in COMSOL:

```text
1. All 225 parameter rows import successfully.
2. Values keep millimetre meaning, not metre meaning.
3. A value of 2.500 means 2.500 mm in the model.
4. Cell row/column orientation is known and documented.
5. The top-left Python matrix cell maps to the intended physical top-left model cell.
6. The single centre cell remains fixed at the default thickness.
```

## 5. COMSOL To Python Export Contract

For each simulated candidate, COMSOL should export:

```text
data/comsol_exports/candidate_000_0000/
  frequencies.csv
  mode_01.csv
  mode_02.csv
  ...
  mode_20.csv
```

`frequencies.csv` must contain:

```csv
mode,frequency_hz
1,123.4
2,175.8
```

Each `mode_XX.csv` must contain:

```csv
x,y,w
-50.0,-50.0,0.0012
-49.5,-50.0,0.0011
```

`w` must be the out-of-plane displacement component. If COMSOL names it differently, export it as column `w` anyway.

## 6. Baseline Model Red Flags

Watch for these before trusting optimisation results:

```text
1. Parameter names do not match Python exports.
2. Thickness values are interpreted in metres instead of millimetres.
3. Only one global thickness changes instead of 225 independent cell thicknesses.
4. The row/column orientation is flipped without being documented.
5. The central clamp is modelled differently from Python's centre mask.
6. The exported mode files omit x or y coordinates.
7. The exported displacement is not the out-of-plane component.
8. Frequencies are exported without explicit mode numbers.
9. The exported grid is too sparse for 256 x 256 comparison.
10. Some modes have all-zero or constant displacement fields.
```

## 7. Immediate Calibration Procedure

Use this order for the next model-code alignment pass:

```text
1. Run python -m src.main generate-candidates.
2. Import candidates/candidate_000_0000/comsol_parameters.csv into COMSOL.
3. Confirm all 225 model parameters changed as expected.
4. Run one eigenfrequency study.
5. Export frequencies.csv and at least mode_01.csv to data/comsol_exports/candidate_000_0000/.
6. Run python -m src.main validate-comsol-exports.
7. If validation passes, export all requested modes.
8. Run python -m src.main score-candidates.
```

## 8. What To Send Back From COMSOL

To review the baseline model without parsing the binary `.mph`, send any of:

```text
1. Screenshot of the parameter table.
2. Screenshot of the 15 x 15 thickness selections.
3. Screenshot of the eigenfrequency study settings.
4. Screenshot of the result export settings.
5. One exported frequencies.csv.
6. One exported mode_01.csv.
7. A COMSOL-generated model report or Java export if available.
```

The most useful first artifact is a single `data/comsol_exports/candidate_000_0000/` folder containing `frequencies.csv` and one or more `mode_XX.csv` files.

## 9. Current Bound Model

The current bridge model is:

```text
comsol_templates/Chladni_15x15_bound.mph
```

It contains 225 `h0101 ... h1515` parameters. The shell thickness is bound through one default `ThicknessOffset` feature using a 15 x 15 piecewise `x,y` expression, which avoids overlapping local shell-thickness variables. The exported boundary mapping is:

```text
reports/chladni_15x15_boundary_mapping.csv
```

Python row/column orientation is documented as:

```text
h0101 = top-left cell
h0115 = top-right cell
h1501 = bottom-left cell
h1515 = bottom-right cell
```

## 10. LiveLink Smoke Test

The first successful bridge smoke test used:

```text
model: comsol_templates/Chladni_15x15_bound.mph
candidate: candidates/candidate_011_0000
export: data/comsol_exports/candidate_011_0000
modes exported: 3
```

Exported frequencies:

```text
mode 1: 30.1453376058 Hz
mode 2: 33.3752698145 Hz
mode 3: 43.2866986567 Hz
```

The 20-mode rerun now validates as `ok` for `candidate_011_0000`.

## 11. First Scoring Result

The first end-to-end scoring pass used `candidate_011_0000`, 20 exported modes, and the current `data/target_patterns/target.png`.

```text
best mode: 3
best IoU: 0.32011696912359167
best Dice: 0.48498273503159817
frequency: 43.2866986584 Hz
final score: -4.5089468360106455
```

The earlier identical-mode scoring issue was caused by sparse COMSOL sample points being inserted into a 256 x 256 grid with unsampled pixels left as zero. The interpolation step now uses inverse-distance interpolation, and the 20 modes produce distinct similarity values.

Mode preview images can be generated with:

```text
python -m src.main render-mode-previews --candidate-id candidate_011_0000 --limit 6
```
