# COMSOL Export Specification

## Python To COMSOL

Each candidate folder contains:

```text
H.csv
comsol_parameters.csv
material_parameters.csv
```

`H.csv` is the direct matrix form:

```csv
2.500,3.000,2.500,...
```

`comsol_parameters.csv` is the named parameter form:

```csv
name,value_mm
h0101,2.5
h0102,3.0
...
```

COMSOL should map each parameter `hrrcc` to the corresponding plate cell thickness, where `rr` is the two-digit row and `cc` is the two-digit column.

The current orientation contract is:

```text
h0101 = top-left cell
h0115 = top-right cell
h1501 = bottom-left cell
h1515 = bottom-right cell
```

The current naming contract is:

```text
h0101 ... h0115
h0201 ... h0215
...
h1501 ... h1515
```

Before running optimisation batches, confirm that the baseline `.mph` model uses the same 225 parameter names and that `value_mm` is interpreted as millimetres.

`material_parameters.csv` is the named material parameter form:

```csv
name,value,unit
mat_density,1200,kg/m^3
mat_poisson_ratio,0.35,1
mat_youngs_modulus,2e9,Pa
mat_thermal_conductivity,0.18,W/(m*K)
mat_heat_capacity,1200,J/(kg*K)
mat_thermal_expansion,8e-05,1/K
```

The bound COMSOL material should reference these global parameters for density, Young's modulus, Poisson ratio, thermal conductivity, heat capacity, and thermal expansion.

## COMSOL To Python

For each candidate, COMSOL should export:

```text
data/comsol_exports/candidate_xxx_xxxx/
  frequencies.csv
  mode_01.csv
  mode_02.csv
  ...
  mode_20.csv
```

`frequencies.csv` format:

```csv
mode,frequency_hz
1,123.4
2,175.8
```

`mode_XX.csv` format:

```csv
x,y,w
-50.0,-50.0,0.0012
-49.5,-50.0,0.0011
```

The `w` column must be the out-of-plane displacement field.

## Validation Before Scoring

After COMSOL exports at least one candidate folder, run:

```powershell
python -m src.main validate-comsol-exports
```

The validation report is saved as:

```text
data/comsol_exports/validation_report.json
```

Only run candidate scoring after the export folder passes this basic format check.
