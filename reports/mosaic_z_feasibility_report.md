# MOSAIC-Z Feasibility Report / MOSAIC-Z 可行性报告

Date: 2026-05-26

## Summary / 摘要

MOSAIC-Z was implemented as a first research-grade probe for the Chladni inverse-design problem. The key change is that the system no longer asks whether one exported COMSOL eigenmode looks like the user target. Instead, it treats exported modes as a modal basis and optimises a continuous modal combination whose zero contour should match the target.

本轮已经把 MOSAIC-Z 作为第一版研究级探针落地。关键变化是：系统不再只判断某一个 COMSOL 本征模态是否像目标图案，而是把导出的多个模态视为模态基底，并优化一个连续模态组合，使其零等值线贴合目标图案。

## Implemented / 已实现

- Added `src/subspace/mosaic_z.py` for modal-basis loading, target skeleton preparation, zero-contour optimisation, alpha export, and preview generation.
- Added `src/scoring/signed_distance_loss.py` for differentiable signed-distance zero-contour loss.
- Added `scripts/run_mosaic_z_subspace.py` for batch subspace feasibility experiments.
- Added `src/forced_response/` and `scripts/run_mosaic_z_projection.py` for physical projection from ideal modal coefficients to actuator position, phase, amplitude, and drive frequency.
- Added `scripts/run_mosaic_z_direct_actuator.py` for direct amplitude-valley optimisation of actuator position, phase, amplitude, and drive frequency.
- Added `src/topology_grammar/generator.py` and `scripts/generate_mosaic_z_topology_primitives.py` to convert an arbitrary target pattern into groove, slot, rib, and mass-pad primitive CSV seeds.
- Added `scikit-image` to the local environment and `requirements.txt`; target skeletonisation now prefers `skimage.morphology.skeletonize` and falls back to the in-repo Zhang-Suen implementation.
- Added the first operator-sculpting CSV contract layer: `topology_primitives.csv`, `support_parameters.csv`, `actuator_parameters.csv`, and `frequency_parameters.csv`.
- Updated the LiveLink runner to read support, frequency, actuator, and topology contract files and write `operator_contract_summary.txt` into each COMSOL export directory.
- Added `comsol_templates/run_chladni_forced_response.m`, `simulate-forced-response`, and `scripts/score_comsol_forced_response.py` for real COMSOL frequency-domain validation and scoring.
- Fixed the COMSOL Shell load bridge from a failing `BoundaryLoad` guess to `FaceLoad` with `forceReferenceArea`, unit-aware Gaussian pressure, frequency-study binding, and all-zero response protection.
- Added `force_sigma_mm` to `frequency_parameters.csv` so actuator footprint width can be swept without editing MATLAB.
- Added `src/forced_response/calibrate_modal_response.py` and `scripts/calibrate_mosaic_z_forced_response.py` to estimate COMSOL-calibrated modal participation scale factors from real forced-response exports.
- Added optional `modal_scale_csv` support to direct actuator optimisation so new actuator layouts can be generated from a real-COMSOL-calibrated predictor.

## Best Subspace Results / 最佳子空间结果

Baseline best single-mode result from the previous COMSOL search was approximately:

- `final_score ≈ 0.0339`
- `IoU ≈ 0.077`
- `Dice ≈ 0.143`

The best MOSAIC-Z result found so far is:

- Candidate: `candidate_151_0005`
- Modes: `8..60`
- Grid: `160 x 160`
- Steps/restarts: `1000 x 7`
- Loss weights: target `1.4`, extra-zero `7.5`, cross `0.9`, sharp `0.25`
- `IoU ≈ 0.176`
- `Dice ≈ 0.299`
- `layout ≈ 0.734`
- Preview: `reports/mosaic_z/top_full_refine/candidate_151_0005/best_subspace_response.png`

This is a clear improvement over single-mode matching, but it is still not an acceptable custom-logo result. The target strokes can be partially pulled into the zero contour, while large extra zero contours remain.

这说明子空间方法确实比单模态匹配更强，但还没有达到可交付的客制化图案效果。目标笔画已经能被部分吸入零线，但仍然存在大量额外零线。

## Physical Projection Results / 物理投影结果

The best free modal alpha from `candidate_151_0005` was projected into actuator parameters:

| Actuator Count | Projection Loss | Drive Frequency |
|---:|---:|---:|
| 1 | `0.878` | `520.60 Hz` |
| 2 | `0.583` | `458.99 Hz` |
| 4 | `0.343` | `363.05 Hz` |

Interpretation:

- A single actuator is not enough to reproduce the ideal modal combination.
- Two actuators help, but still leave a large gap.
- Four actuators reduce the gap substantially, which indicates that the ideal subspace response is not purely mathematical fantasy; it needs richer excitation or equivalent structural scattering/support freedom.

解释：

- 单激振器不足以复现理想模态组合。
- 双激振器明显改善，但仍然差距较大。
- 四激振器显著降低投影误差，说明理想子空间响应不是纯数学幻象，而是需要更丰富的激励自由度，或通过支撑/局部拓扑扰动获得等效自由度。

## Direct Forced-Response Optimisation / 直接强迫响应优化

The alpha-projection path still lost too much structure, so actuator parameters were also optimised directly against an amplitude-valley loss. This bypasses the free-alpha target and asks the physically predicted forced response itself to place low-amplitude valleys on the target.

由于 alpha 投影链路仍然损失较大，本轮进一步直接用 amplitude-valley loss 优化激振参数。也就是说，不再先拟合理想 alpha，而是直接要求物理预测的强迫响应在目标图案上形成低振幅谷线。

| Candidate | Actuators | Drive Frequency | IoU | Dice | Layout | Valley Area |
|---|---:|---:|---:|---:|---:|---:|
| `candidate_151_quad_160` | 4 | `794.19 Hz` | `0.207` | `0.343` | `0.610` | `0.092` |
| `candidate_151_six_160` | 6 | `500.15 Hz` | `0.252` | `0.402` | `0.690` | `0.108` |
| `candidate_151_eight_160_center_safe` | 8 | `1113.16 Hz` | `0.297` | `0.458` | `0.738` | `0.086` |

Key generated validation candidates:

- `candidates/mosaic_z_candidate_151_direct_six`
- `candidates/mosaic_z_candidate_151_direct_eight_safe`
- Topology grammar seeds: `reports/mosaic_z/topology_seed_groove.csv`, `reports/mosaic_z/topology_seed_rib.csv`, and `reports/mosaic_z/topology_seed_mass_pad.csv`

This is the strongest evidence so far that the next breakthrough is not more thickness-only search. The same modal export becomes much more target-like when the response is optimised as a controllable forced response.

这是目前最强证据：下一步突破不应继续依赖厚度单变量搜索。同一组 COMSOL 模态导出，在改成可控强迫响应优化后，已经显著更接近目标图案。

## Real COMSOL Forced-Response Validation / 真实 COMSOL 强迫响应验证

The new LiveLink forced-response runner now reaches COMSOL and produces nonzero shell displacement for MOSAIC-Z candidates. The runner uses:

- `FaceLoad` on the Shell interface.
- `forceReferenceArea = [0, 0, gaussian actuator pressure]`.
- Complex phase in the load expression.
- A dedicated `std_mosaic_forced/freq` Frequency study.
- A guard that fails the run if the response is all zero.

新的 LiveLink 强迫响应 runner 已经能进入 COMSOL 并为 MOSAIC-Z 候选产生非零壳位移。runner 使用 Shell 的 `FaceLoad`、参考面积力、复数相位激励、独立 `std_mosaic_forced/freq` 频域研究，并加入全零响应保护。

Best threshold sweep so far:

| Candidate | Actuators | COMSOL Drive Frequency | Best Epsilon | Real COMSOL IoU | Real COMSOL Dice | Real COMSOL Layout | Preview |
|---|---:|---:|---:|---:|---:|---:|---|
| `mosaic_z_candidate_151_direct_six` | 6 | `500.15 Hz` | `0.040` | `0.121` | `0.216` | `0.423` | `reports/mosaic_z/comsol_forced_response/candidate_151_direct_six_eps004/comsol_forced_response_preview.png` |
| `mosaic_z_candidate_151_direct_eight_safe` | 8 | `1113.16 Hz` | `0.040` | `0.116` | `0.208` | `0.390` | `reports/mosaic_z/comsol_forced_response/candidate_151_direct_eight_safe_eps004/comsol_forced_response_preview.png` |

Small real-COMSOL force-width sweep on the six-actuator candidate:

| Candidate | `force_sigma_mm` | Best Epsilon | Real COMSOL IoU | Real COMSOL Dice | Real COMSOL Layout |
|---|---:|---:|---:|---:|---:|
| `mosaic_z_candidate_151_direct_six` | `2.5` | `0.040` | `0.121` | `0.216` | `0.423` |
| `mosaic_z_candidate_151_direct_six_sigma5` | `5.0` | `0.040` | `0.117` | `0.209` | `0.402` |
| `mosaic_z_candidate_151_direct_six_sigma8` | `8.0` | `0.050` | `0.103` | `0.187` | `0.368` |

Interpretation:

- The COMSOL bridge now works mechanically; this is no longer a fake zero-response success.
- The real COMSOL response is significantly weaker than the Python modal-response prediction (`Dice 0.216` vs predicted `0.402` for six actuators, and `Dice 0.208` vs predicted `0.458` for eight actuators).
- The gap likely comes from simplified modal forcing assumptions: point-sampled modal participation, no modal mass normalisation, Gaussian distributed load mismatch, missing damping calibration, and mode truncation.
- The first force-width sweep suggests wider Gaussian loading does not solve the gap by itself; the next calibration target should be modal participation/mass normalisation and COMSOL-in-the-loop actuator search.

解释：

- COMSOL 桥接已经机械跑通；它不再是假成功的全零响应。
- 真实 COMSOL 响应明显弱于 Python 模态响应预测。
- 差距很可能来自模态强迫模型的简化：点采样参与因子、缺少模态质量归一化、高斯分布载荷不匹配、阻尼未校准、以及模态截断。
- 第一轮激励宽度 sweep 表明，仅仅加宽高斯载荷不能解决差距；下一步应优先校准模态参与因子/模态质量归一化，并进入 COMSOL 闭环激振搜索。

### Modal-Participation Calibration Loop / 模态参与因子校准闭环

A first calibration loop was added after the initial real-COMSOL validation. The calibration uses real `forced_response.csv` exports to fit per-mode complex participation scale factors, then reruns direct actuator optimisation with the calibrated predictor.

第一轮真实 COMSOL 验证之后，系统加入了模态参与因子校准闭环。该闭环使用真实 `forced_response.csv` 导出拟合每个模态的复数参与因子修正，然后用校准后的预测器重新优化激振参数。

Calibration v1 used four real COMSOL cases:

| Calibration Set | Cases | Mean Scale Abs | Min Scale Abs | Max Scale Abs |
|---|---:|---:|---:|---:|
| `real_comsol_v1` | `4` | `1.000` | `0.797` | `1.529` |

The calibrated six-actuator candidate improved real COMSOL matching:

| Candidate | Drive Frequency | Best Epsilon | Real COMSOL IoU | Real COMSOL Dice | Real COMSOL Layout | Preview |
|---|---:|---:|---:|---:|---:|---|
| `mosaic_z_candidate_151_calibrated_six_v1` | `796.96 Hz` | `0.050` | `0.179` | `0.303` | `0.492` | `reports/mosaic_z/comsol_forced_response/candidate_151_calibrated_six_v1_eps005/comsol_forced_response_preview.png` |

This is a real-COMSOL improvement over the previous best (`Dice 0.216 -> 0.303`). It does not solve the custom-logo problem yet, but it proves that the predictor can be corrected with COMSOL observations instead of only running open-loop Python optimisation.

这是一次真实 COMSOL 层面的提升（`Dice 0.216 -> 0.303`）。它还没有解决客制化 logo 问题，但证明了预测器可以用 COMSOL 观测反校正，而不是只做开环 Python 优化。

Calibration v2 added the new calibrated case, but its coherence was lower (`0.438` on the new case), and the next Python prediction became weaker (`predicted Dice 0.355` vs v1 `0.397`). This suggests that one global modal-scale correction is still too crude; the next surrogate should be frequency/local-load aware.

第二轮校准加入了新的校准候选，但新样本 coherence 较低（`0.438`），下一轮 Python 预测也变弱（`predicted Dice 0.355`，低于 v1 的 `0.397`）。这说明单一全局模态修正仍然太粗，下一版代理模型应加入频率和局部载荷感知。

### Real Frequency Scan Around the Calibrated Candidate / 校准候选真实频率扫描

The calibrated six-actuator layout was scanned in real COMSOL while keeping actuator positions and phases fixed:

| Candidate | Drive Frequency | Real COMSOL Dice at Epsilon 0.05 | Real COMSOL IoU | Real COMSOL Layout |
|---|---:|---:|---:|---:|
| `mosaic_z_candidate_151_calibrated_six_f750` | `750 Hz` | `0.110` | `0.058` | `0.277` |
| `mosaic_z_candidate_151_calibrated_six_f780` | `780 Hz` | `0.161` | `0.088` | `0.336` |
| `mosaic_z_candidate_151_calibrated_six_v1` | `796.96 Hz` | `0.303` | `0.179` | `0.492` |
| `mosaic_z_candidate_151_calibrated_six_f790` | `790 Hz` | `0.311` | `0.184` | `0.499` |
| `mosaic_z_candidate_151_calibrated_six_f805` | `805 Hz` | `0.318` | `0.189` | `0.529` |
| `mosaic_z_candidate_151_calibrated_six_f810` | `810 Hz` | `0.321` | `0.191` | `0.551` |
| `mosaic_z_candidate_151_calibrated_six_f812` | `812 Hz` | `0.320` | `0.191` | `0.539` |
| `mosaic_z_candidate_151_calibrated_six_f815` | `815 Hz` | `0.312` | `0.185` | `0.538` |
| `mosaic_z_candidate_151_calibrated_six_f820` | `820 Hz` | `0.295` | `0.173` | `0.521` |
| `mosaic_z_candidate_151_calibrated_six_f860` | `860 Hz` | `0.055` | `0.028` | `0.075` |

Current real-COMSOL best:

- Candidate: `mosaic_z_candidate_151_calibrated_six_f810`
- Drive frequency: `810 Hz`
- Epsilon: `0.050`
- Real COMSOL IoU: `0.191`
- Real COMSOL Dice: `0.321`
- Real COMSOL layout: `0.551`
- Preview: `reports/mosaic_z/comsol_forced_response/candidate_151_calibrated_six_f810_eps005/comsol_forced_response_preview.png`

当前真实 COMSOL 最优候选为 `mosaic_z_candidate_151_calibrated_six_f810`。它仍不是可交付图案，但已经形成了可复现实验进步：从原始单模态 `Dice ≈ 0.143`，到真实强迫响应 `0.216`，再到校准闭环与频率扫描后的 `0.321`。

A follow-up actuator re-optimisation with the frequency fixed at `810 Hz` was also tested:

| Candidate | Python Predicted Dice | Real COMSOL Dice | Real COMSOL IoU | Interpretation |
|---|---:|---:|---:|---|
| `mosaic_z_candidate_151_fixed810_six_v1` | `0.382` | `0.238` | `0.135` | Worse than the scanned v1 layout; current surrogate still misranks actuator layouts. |

固定 `810 Hz` 后重新优化激励点的候选也已经测试。真实结果低于扫频得到的 v1 布局，说明当前代理模型对激励点/相位的排序仍不可靠；下一步应优先让代理模型吸收真实 COMSOL 观测，而不是继续扩大开环 Python 搜索。

## Research Decision / 研究判断

### Critical Correction: Layer 3 Was Not Actually Active / 关键修正：Layer 3 此前并未真正生效

After re-reading the MOSAIC-Z plan against the implementation, one important mistake was found: the project had contract files for `topology_primitives.csv` and `support_parameters.csv`, but they were not yet changing the COMSOL operator in the intended way.

重新对照 MOSAIC-Z 方案和代码实现后，发现一个重要问题：项目虽然已经有 `topology_primitives.csv` 和 `support_parameters.csv` 合同文件，但它们此前并没有按预期真正改变 COMSOL 算子。

Findings:

- `topology_primitives.csv` was read by the LiveLink runners, but only `topology_primitive_count` was logged/set. No slot, groove, rib, or mass-pad geometry was created in COMSOL.
- `support_parameters.csv` set `support_center_x`, `support_center_y`, and `support_clamp_radius`, but the audited MPH fixed constraint is still an explicit entity selection. The support parameters are not currently bound to the fixed constraint.
- Therefore, the recent frequency/actuator sweeps mostly stayed inside the same physical operator. They improved the response locally, but they did not execute the Layer 3 operator-sculpting step described in MOSAIC-Z.

发现：

- `topology_primitives.csv` 此前只被读取并记录 `topology_primitive_count`，没有在 COMSOL 中真正创建槽、沟、肋或质量块。
- `support_parameters.csv` 虽然设置了 `support_center_x`、`support_center_y`、`support_clamp_radius`，但审计到的 MPH 固定约束仍然是显式实体选择；这些支撑参数目前没有绑定到固定约束。
- 因此，最近的频率/激振扫描基本仍停留在同一个物理算子里。它们带来了局部提升，但没有真正执行 MOSAIC-Z 的 Layer 3 operator sculpting。

Immediate correction implemented:

- Added `src/topology_grammar/rasterize.py`.
- Added `scripts/materialize_topology_candidate.py`.
- This materialises slot/groove/rib/mass-pad primitives into the fields that are already bound to COMSOL: `H.csv`, `density_scale.csv`, and `loss_factor.csv`.
- This is not yet full CAD-level slot/rib geometry, but it makes topology primitives physically affect stiffness/mass/damping instead of only existing as logs.

已做即时修正：

- 新增 `src/topology_grammar/rasterize.py`。
- 新增 `scripts/materialize_topology_candidate.py`。
- 该工具会把 slot/groove/rib/mass-pad 基元物化到已经绑定 COMSOL 的 `H.csv`、`density_scale.csv`、`loss_factor.csv`。
- 这还不是完整 CAD 几何级别的槽/肋建模，但它已经让拓扑基元真实影响刚度/质量/阻尼，而不是只存在于日志里。

First real-COMSOL test of rasterised Layer 3 seeds:

| Candidate | Operator Primitive Family | Real COMSOL Dice at Epsilon 0.05 | Real COMSOL IoU | Real COMSOL Layout | Interpretation |
|---|---|---:|---:|---:|---|
| `mosaic_z_candidate_151_calibrated_six_f810` | none / baseline | `0.321` | `0.191` | `0.551` | Current best same-operator baseline |
| `mosaic_z_operator_groove_seed_v1` | groove | `0.308` | `0.182` | `0.505` | Operator changed, but seed did not improve |
| `mosaic_z_operator_rib_seed_v1` | rib | `0.299` | `0.176` | `0.545` | Operator changed, but seed did not improve |
| `mosaic_z_operator_mass_pad_seed_v1` | mass_pad | `0.311` | `0.184` | `0.535` | Operator changed, close but below baseline |

Interpretation:

- Rasterised topology is now active enough to change the real COMSOL response.
- The current hand-generated target-aligned primitive seeds are too weak/coarse to produce a breakthrough.
- The next true MOSAIC-Z step is not more frequency sweeps. It is either COMSOL-side geometry creation for slots/ribs/mass pads, or an optimisation loop that searches these topology primitives directly and judges them by subspace feasibility plus real forced response.

解释：

- 栅格化拓扑现在已经能真实改变 COMSOL 响应。
- 但当前手工目标对齐的 primitive seed 太弱、太粗，还没有形成突破。
- 下一步真正的 MOSAIC-Z 不应继续扫频，而应做 COMSOL 侧真实槽/肋/质量块几何，或直接优化这些拓扑基元，并用子空间可行性和真实强迫响应共同评判。

The current contract `thickness + density + loss -> eigenmode matching` should not remain the main algorithmic path. The new evidence supports:

1. Keep MOSAIC-Z as the main scoring and diagnosis layer.
2. Treat single-mode IoU/Dice as evaluation metrics only, not the primary optimiser.
3. Add operator-sculpting variables next: support offset, actuator parameters, slot/rib/mass-pad grammar.
4. Use COMSOL frequency-domain/harmonic-response validation after actuator/support contracts exist.

当前 `厚度 + 密度 + 损耗 -> 单本征模态匹配` 不应继续作为主算法路径。新的证据支持：

1. 将 MOSAIC-Z 作为主要评分与诊断层。
2. 单模态 IoU/Dice 只作为评价指标，不再作为主优化对象。
3. 下一步加入算子塑形变量：支撑偏移、激振参数、槽/肋/质量块结构语法。
4. 等激振/支撑合同建立后，再进入 COMSOL 频域/谐响应验证。

## Next Implementation Tasks / 下一步实现任务

- Replace the current global modal-scale calibration with a frequency-aware and load-footprint-aware surrogate, because v2 calibration exposed case-dependent modal participation errors.
- Add a COMSOL-response feedback loop that can choose the next frequency/actuator candidate automatically from observed real scores instead of manually cloning candidate folders.
- Promote topology primitives from rasterised field approximations to real COMSOL geometry or shell-field modifier features, because current CSV-only topology logging was a no-op and rasterised 15x15 seeds are too coarse.
- Rebuild support offset as an actual COMSOL selection/constraint change; setting `support_center_x/y` alone is not enough unless the fixed constraint uses those parameters.
- Implement COMSOL-side geometry creation for `topology_primitives.csv` slot/rib/mass-pad rows.
- Add support-offset and force-width sweeps because the current centre clamp and `2.5 mm` Gaussian force width may be suppressing controllability.
- Add family-level active learning so COMSOL budget is assigned by observed improvement and failure rate.
