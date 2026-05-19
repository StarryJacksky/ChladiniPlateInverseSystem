# COMSOL Export Specification

## Python To COMSOL

Each candidate folder contains:

```text
H.csv
comsol_parameters.csv
```

`H.csv` is the direct matrix form:

```csv
2.500,3.000,2.500,...
```

`comsol_parameters.csv` is the named parameter form:

```csv
name,value_mm
h_1_1,2.5
h_1_2,3.0
...
```

COMSOL should map each parameter `h_i_j` to the corresponding plate cell thickness.

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
