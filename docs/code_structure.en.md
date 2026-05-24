# Project Code Structure and Logic

[Language](./code_structure.md): [Bilingual](./code_structure.md) | [中文](./code_structure.zh-CN.md) | English

This document explains the main folders and the logic of the project for beginners.

## 1. Big Picture

The software turns a user target pattern into candidate Chladni plate designs.

```text
user image or drawing
        |
        v
target preprocessing
        |
        v
15 x 15 thickness candidates
        |
        v
COMSOL/MATLAB simulation
        |
        v
nodal-line extraction and scoring
        |
        v
ranked results, reports, packages
```

The current physical contract is a real `150 mm x 150 mm` plate with a `15 x 15` thickness grid.

## 2. Root Files

- `README.md`: the GitHub front page and first entry point.
- `config.yaml`: the main project configuration, including geometry, material values, scoring weights, paths, and COMSOL/MATLAB settings.
- `requirements.txt`: Python package dependencies.
- `.gitignore`: files Git should ignore, such as generated cache or temporary outputs.

Beginners usually start with `README.md`, then read the deployment guide, user manual, and this code-structure guide.

## 3. `frontend/`

`frontend/target_designer.html` is the main local Studio interface.

It contains the drawing canvas, image import controls, Target/Tune/Results/Run tabs, JavaScript that calls local backend APIs, and visual styling for the engineering console.

The frontend does not run COMSOL directly. Instead, it sends requests to the local Python server in `src/frontend/target_ui_server.py`.

## 4. `src/main.py`

`src/main.py` is the command-line entry point.

Common commands include:

- `target-ui`: starts the local web interface.
- `prepare-target`: preprocesses the target image.
- `generate-candidates`: generates thickness matrices.
- `run-workflow`: runs the automated design workflow.
- `diagnose-comsol`: checks COMSOL/MATLAB readiness.
- `self-test`: runs deployment checks.

If a beginner wants to understand how commands enter the project, start here.

## 5. `src/config.py`

`src/config.py` loads `config.yaml` and creates required folders.

Most modules receive a `config` dictionary from this file. That dictionary tells the code where target images live, where candidates should be saved, what plate size and grid size are used, what material and scoring values should be used, and where COMSOL and MATLAB are located.

## 6. `src/target/`

This folder prepares user drawings or imported images for scoring.

- `preprocess_target.py`: converts the input image into a clean binary target.
- `analyse_target.py`: measures target quality, such as foreground area, connected parts, and complexity warnings.

Important outputs:

- `target_binary.npy`: the numerical target array used by scoring code.
- `target_preview.png`: preview image shown in the UI.
- `target_analysis.json`: target-quality data shown in the UI.

## 7. `src/candidate/`

This folder creates one stepped-thickness plate candidate.

- `generate_candidate.py`: creates a `15 x 15` thickness matrix.
- `constraints.py`: keeps generated values inside physical and design limits.

Important outputs:

- `H.csv`: the candidate thickness matrix.
- `metadata.json`: generation settings and candidate metadata.
- `comsol_parameters.csv`: parameter values that can be passed toward COMSOL.

## 8. `src/optimisation/`

This folder controls candidate batches and workflow order.

- `random_search.py`: generates many candidate thickness matrices and previews.
- `workflow.py`: connects target preprocessing, candidate generation, optional COMSOL simulation, and scoring.

The current search method is intentionally simple and robust. Later, after real COMSOL and physical validation data are stable, this folder can grow into stronger optimization methods.

## 9. `src/comsol/`

This folder handles the connection between Python and COMSOL/MATLAB.

- `discovery.py`: finds already-running COMSOL/MATLAB processes and common install paths.
- `diagnostics.py`: checks whether the local machine is ready for automated simulation.
- `server.py`: starts or connects to COMSOL `mphserver`.
- `run_livelink.py`: runs MATLAB LiveLink commands for one or more candidates.
- `export_parameters.py`: writes candidate parameters in a COMSOL-friendly format.
- `import_results.py`: reads COMSOL-exported frequencies and mode shapes.
- `validate_exports.py`: checks exported COMSOL result folders.
- `model_audit.py`: records basic information about the bound COMSOL model.

This is the most deployment-sensitive part of the project because it depends on local COMSOL, local MATLAB, LiveLink, licenses, and the final `.mph` model.

## 10. `comsol_templates/`

This folder stores COMSOL model files and MATLAB scripts used by LiveLink.

- `Chladni_15x15_parameterized.mph`: parameterized baseline model for the `15 x 15` grid.
- `Chladni_15x15_bound.mph`: bound model variant used by the current bridge.
- `run_chladni_candidate.m`: MATLAB script that receives candidate parameters, runs COMSOL, and exports results.
- `export_specification.md`: explains expected COMSOL export files.

This folder becomes final only after the baseline COMSOL model is accepted.

## 11. `src/nodal/` and `src/scoring/`

`src/nodal/` converts simulated mode fields into nodal-line masks.

- `extract_nodal.py`: extracts nodal regions from simulation arrays.

`src/scoring/` compares simulated nodal masks with the user target.

- `metrics.py`: computes similarity metrics such as IoU and Dice.
- `score_candidate.py`: combines similarity with penalties and writes ranking data.

Important outputs:

- `score.json`: detailed score for one candidate.
- `ranked_candidates.csv`: sorted candidate ranking.

## 12. `src/visualisation/`

This folder creates images for humans to inspect.

- `plot_thickness.py`: draws thickness-field previews from `H.csv`.
- `plot_modes.py`: draws COMSOL mode previews and comparison images.

The UI uses these images in the Results tab.

## 13. `src/frontend/`

`src/frontend/target_ui_server.py` is the Python server behind the local Studio.

It provides APIs for loading and saving the target canvas, updating material and scoring settings, updating COMSOL settings, running workflow jobs, reading rankings and candidate details, generating reports, viewing logs and diagnostics, and safely cancelling a workflow.

Think of this file as the bridge between the HTML interface and the Python algorithm code.

## 14. `scripts/`

This folder contains scripts that help developers, deployers, and COMSOL model builders.

Important Python scripts:

- `launch_chladni_studio.py`: starts the UI and finds an available local port.
- `check_bilingual_comments.py`: checks bilingual source-code comments.
- `check_config_contract.py`: checks core configuration contracts.
- `check_discovery_fixtures.py`: checks COMSOL/MATLAB discovery examples.
- `check_python_smoke.py`: verifies Python-only target preprocessing and candidate generation.

Important MATLAB scripts:

- `parameterize_chladni_15x15.m`: helps create a parameterized `15 x 15` COMSOL model.
- `bind_chladni_15x15_model.m`: binds model parameters to the LiveLink workflow.
- `probe_chladni_faces.m` and related probe scripts: inspect COMSOL geometry selections.

The `.bat`, `.sh`, and `.command` launchers are convenience wrappers for Windows, Linux, and macOS users.

## 15. Data Folders

- `data/target_patterns/`: user target images.
- `data/processed_targets/`: processed target arrays, previews, and analysis.
- `candidates/`: generated thickness candidates.
- `data/comsol_exports/`: COMSOL output files, mode CSV files, logs, reports, and workflow state.
- `reports/`: planning notes, audits, calibration notes, and remaining-work plans.

Most generated data can be recreated, but large COMSOL outputs and useful validation records should be handled carefully.

## 16. Normal Developer Reading Order

For a beginner who wants to understand the code, read in this order:

1. `README.md`: project goal.
2. `docs/user_manual.md`: how the user operates the software.
3. `docs/code_structure.md`: code map.
4. `src/main.py`: how commands enter the system.
5. `src/optimisation/workflow.py`: how the automatic workflow is connected.
6. `src/frontend/target_ui_server.py`: how the frontend calls the backend.
7. `src/target/`, `src/candidate/`, `src/scoring/`: algorithm core.
8. `src/comsol/` and `comsol_templates/`: COMSOL/MATLAB bridge.

## 17. What Is Still Waiting for Real Data

Some parts should not be treated as final until lab data are frozen:

- final material values.
- final COMSOL boundary names and model selections.
- final physical validation frequencies and photographed nodal patterns.
- final optimization weights.
- final release screenshots.

Until then, this project is already usable for Python-side smoke testing, UI workflow testing, COMSOL/MATLAB discovery, and bridge planning.
