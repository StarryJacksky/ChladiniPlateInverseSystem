# Chladni Baseline COMSOL Model Audit

Source model:

```text
/Users/apple/Documents/Chladni.mph
```

Audit date:

```text
2026-05-21
```

## Current Model Facts

The model was exported with COMSOL 6.4.0.293 and inspected through its internal `dmodel.xml`.

Global parameters currently defined:

```text
wide      = 150[mm]
length    = 150[mm]
thickness = 2[mm]
radius    = 1.77[mm]
```

Physics interface:

```text
Shell physics tag: shell
Study tag: std1
Study feature: eig
Result surface expression shown in GUI: shell.disp
Out-of-plane displacement expression for export: shell.w
```

Current shell thickness features:

```text
to1: overall thickness, d = 0.002[m]
to2: d = 0.001[m]
to3: d = 0.0013[m]
to4: d = 0.0008[m]
to5: d = 0.0018[m]
to6: d = 0.0009[m]
to7: d = 0.0006[m]
to8: d = 0.0014
```

Fixed constraint:

```text
fix1 on shell boundary entities: 124, 125, 141, 149
```

## Main Mismatch With The Early Python Code

The early Python optimiser assumed this design contract:

```text
6 x 6 thickness matrix
h_1_1 ... h_6_6
thickness levels: 2.0, 2.5, 3.0, 3.5 mm
plate size: 100 mm x 100 mm
center clamp radius: 8 mm
```

The baseline COMSOL model currently uses:

```text
No h_1_1 ... h_6_6 parameters
Only four global parameters: wide, length, thickness, radius
Seven hard-coded local ThicknessOffset groups, to2 ... to8
plate size parameters: 150 mm x 150 mm
radius parameter: 1.77 mm
```

So the model can run as a shell eigenfrequency baseline, but it is not yet ready for the Python inverse-design loop.

Additional geometry inspection found that the received model can be rebuilt through its workplane split lines. After team discussion, the current calibrated software contract is now `15 x 15`, giving 10 mm cells on the real 150 mm plate.

## Required Model Changes Before LiveLink Bridge

Make the COMSOL model expose the same variables that Python will set:

```text
h0101, h0102, ..., h1515
```

Recommended COMSOL contract:

```text
1. Define 225 global parameters h0101 ... h1515, each with units [mm].
2. Divide the design plate into exactly 225 controllable 15 x 15 cell selections.
3. Create one shell ThicknessOffset feature per cell, or an equivalent selection-controlled thickness expression.
4. Set each cell thickness expression to the corresponding row/column parameter.
5. Keep the central clamp geometry and Python center mask consistent.
6. Keep the true plate size at 150 mm x 150 mm.
7. Use shell.w for nodal-line export, not shell.disp.
```

## Bridge Direction

The next development step should use MATLAB LiveLink as the bridge:

```text
Python writes candidates/candidate_xxx/comsol_parameters.csv
MATLAB LiveLink loads Chladni.mph
MATLAB sets model.param row/column thickness values
MATLAB runs model.study('std1').run
MATLAB exports frequencies.csv
MATLAB exports mode_01.csv ... mode_20.csv with x,y,shell.w
Python validates and scores the export
```

The initial LiveLink runner template is:

```text
comsol_templates/run_chladni_candidate.m
```

## Calibrated Decision

The current route is:

```text
Modify COMSOL and Python to meet at a 15 x 15 / h0101-style contract.
```

This preserves the inverse-design plan and avoids being trapped by the current seven grouped `ThicknessOffset` regions. The earlier 7 x 7 and 9 x 9 parameter tables were useful probes, but they are now superseded by the 15 x 15 calibration target.

## Update After First Parameterisation Probe

A first 7 x 7 parameterised copy has been created:

```text
comsol_templates/Chladni_7x7_parameterized.mph
```

The copy contains:

```text
grid_size = 7
cell_size = wide/grid_size
h_1_1 ... h_7_7 = 2[mm]
h_center = 2[mm]
```

This was a parameter-table alignment probe only. It should not be used as the production bridge model because the project has now moved to the `15 x 15` calibration contract.

The next parameterised copy should be:

```text
comsol_templates/Chladni_15x15_parameterized.mph
```

The important remaining COMSOL-side task is unchanged: bind each physical `15 x 15` plate cell's shell thickness expression to the corresponding row/column parameter.

## Update After 15 x 15 Binding

A bound 15 x 15 bridge model should be created:

```text
comsol_templates/Chladni_15x15_bound.mph
```

Confirmed by audit:

```text
225 h0101 ... h1515 global parameters
1 shell ThicknessOffset feature with a 15 x 15 piecewise row/column expression
fixed washer edges: 277, 278, 281, 284
```

The workplane split uses 14 arrayed internal lines at 10 mm spacing. The centre hole and washer radii are preserved.

The first 15 x 15 LiveLink smoke test succeeded with `candidate_011_0000`, exporting three modes to:

```text
data/comsol_exports/candidate_011_0000
```

The three exported eigenfrequencies were 30.1453376058 Hz, 33.3752698145 Hz, and 43.2866986567 Hz. Python validation marked the folder `needs_review` only because the smoke test exported 3 modes rather than the configured 20.
