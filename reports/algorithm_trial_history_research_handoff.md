# Chladni Plate Inverse Design Algorithm Trial Report

Date: 2026-05-26

Current branch: `codex/chladni-inverse-design-scaffold`

Latest referenced commit: `aa2eee8 Add response-calibrated latent scheduling`

Intended reader: a research-oriented AI or human researcher who needs to understand why the current inverse-design algorithm has stalled, what has already been tried, and where the next academic breakthrough is likely to be.

## 0. 中文导读与使用说明

这份报告是给“下一位研究者或更高级 AI”接手用的，不是普通项目日报。它的核心目的有三个：

```text
1. 交代我们已经试过哪些算法路线，避免对方重复兜圈子。
2. 用真实 COMSOL 结果说明哪些路线有效、哪些路线只是看起来高级。
3. 把问题上升到物理设计空间和学术建模层面，让下一步研究不再只调超参数。
```

当前最重要的结论是：

```text
我们的自动化软件链路已经能跑通。
我们的评分和 COMSOL 闭环也已经能稳定反馈。
但当前变量合同下，算法还没有能力把 IC 这种目标图案逆向生成成像样的 Chladni 节点线。
```

截至本报告生成时，项目已经跑过 `293` 个真实 COMSOL 候选。历史最佳仍是：

```text
candidate_174_0002
final_score = 0.0339140677054821
precision   = 0.1076563022400535
recall      = 0.21488154821488153
```

这不是一个“再多跑几代就自然好起来”的状态。更合理的判断是：

```text
当前厚度 + 密度 + 损耗因子这组设计变量，还不足以稳定控制任意 logo 式节点线图案。
```

因此，下一步更像学术问题，而不是普通工程调参问题。建议另一个 AI 优先研究：

```text
1. 拓扑孔洞或开槽变量。
2. 支撑点、夹持条件、激励点、激励相位、驱动频率。
3. 强迫响应图案控制，而不是只匹配自然特征模态。
4. 可微有限元或伴随灵敏度优化。
5. 近简并模态子空间内的线性组合优化。
6. 给任意用户图案做物理可实现性判定。
```

如果要把本报告发给另一个 AI，建议直接给它全文，并额外强调：

```text
不要只建议“加大遗传算法”“加大贝叶斯优化”“多跑几代”。
我们已经试过这些方向，真实 COMSOL 反馈显示瓶颈更像物理变量表达能力不足。
```

## 1. Executive Summary

This project tries to solve an inverse Chladni-plate design problem:

Given a user-specified target drawing, currently an `IC` logo-like pattern, generate a manufacturable plate design so that one simulated Chladni nodal pattern from COMSOL resembles the target.

The current automated loop works technically:

```text
user target image
-> Python preprocessing
-> 15 x 15 candidate design variables
-> COMSOL/MATLAB LiveLink simulation
-> exported eigenmodes
-> nodal-line extraction
-> strict scoring
-> ranked candidates and frontend review
```

However, the inverse-design algorithm has not produced a visually convincing `IC` pattern. After 293 real COMSOL-scored candidates, the best candidate is still:

```text
candidate_174_0002
final_score = 0.0339140677054821
precision   = 0.1076563022400535
recall      = 0.21488154821488153
IoU         = 0.07726454709058188
Dice        = 0.14344581801982403
best_mode   = 18
frequency   = 486.209364226 Hz
```

The current diagnostic status is:

```text
physics_limited_current_contract
```

This means the present COMSOL design contract appears under-expressive for the requested custom pattern. The current variables are:

```text
thickness_mm
global_material
per_cell_density_or_mass
per_cell_loss_factor
```

The next recommended variables are:

```text
hole_or_slot_topology
support_position
actuator_position_phase
```

The most important conclusion is:

The current problem is probably not solvable by merely making the optimizer more aggressive. The next leap likely requires changing the physical design space and the mathematical formulation, not only tuning genetic algorithms, Bayesian search, or surrogate weights.

## 2. Current Physical and Numerical Contract

The real plate and model are calibrated as follows:

```text
plate size: 150 mm x 150 mm
design grid: 15 x 15
cell size: about 10 mm
center clamp radius: 8 mm
target/scoring image size: 256 x 256
COMSOL exported modes: usually 20 to 80 modes depending on run
target-matching minimum mode: 8
```

Current thickness variables:

```text
design mode: continuous
thickness lower bound: 0.6 mm
thickness upper bound: 2.0 mm
default thickness: 2.0 mm
max neighbor difference: 1.0 mm
```

Current material parameters:

```text
density: 1200 kg/m^3
Poisson ratio: 0.35
Young's modulus: 2.0e9 Pa
thermal conductivity: 0.18 W/(m*K)
heat capacity: 1200 J/(kg*K)
thermal expansion: 8e-5 1/K
```

Current auxiliary design variables:

```text
density_scale range: 0.65 to 1.55
loss_factor range: 0.0 to 0.16
```

The COMSOL parameter export contract currently writes:

```text
H.csv
comsol_parameters.csv
material_parameters.csv
design_variable_parameters.csv
density_scale.csv
loss_factor.csv
```

The COMSOL-to-Python result contract is:

```text
data/comsol_exports/<candidate_id>/frequencies.csv
data/comsol_exports/<candidate_id>/mode_01.csv
data/comsol_exports/<candidate_id>/mode_02.csv
...
```

## 3. Current Scoring Rule

The current scoring version is:

```text
strict_precision_topology_v5
```

A candidate is scored by:

1. Importing COMSOL mode CSV files.
2. Interpolating displacement onto a 256 x 256 grid.
3. Extracting nodal regions from near-zero displacement.
4. Removing the center clamp region.
5. Comparing each eligible mode to the target pattern.
6. Selecting the best mode.
7. Applying roughness, mass, and frequency penalties.

The scoring components include:

```text
IoU
Dice
Chamfer/distance similarity
Overlap balance
Layout similarity
Area similarity
Precision
Recall
Projection similarity
Extent similarity
Complexity similarity
Connected-component similarity
Centerline overreach penalty
```

The current final score is approximately:

```text
final_score =
  best_pattern_similarity
  - roughness_weight * roughness_penalty
  - mass_weight * mass_penalty
  - frequency_weight * frequency_penalty
```

Current relevant weights:

```text
roughness_weight = 0.15
mass_weight      = 0.01
frequency_weight = 0.01
```

The feasibility thresholds are intentionally strict:

```text
score floor     = 0.08
precision floor = 0.20
```

The best real candidate is far below both:

```text
best score     = 0.033914
best precision = 0.107656
```

So the current search is not merely slightly underperforming; it is still far from the engineering acceptance target.

## 4. Chronological Algorithm Trial History

### Phase A: Random, Evolutionary, and Target-Guided Thickness Search

Early candidate generation started with:

```text
random thickness matrices
evolutionary crossover and mutation
target-guided thickness maps
neighbor-thickness constraint repair
center-clamp constraint enforcement
```

Goal:

```text
Find a 15 x 15 thickness field that naturally creates a nodal pattern resembling the target.
```

What happened:

Early candidates could produce valid COMSOL runs and nonempty nodal patterns, but the generated nodal lines were mostly generic plate eigenmodes: broad curves, star-like structures, rings, or center-dominated patterns. They did not form the letter-like `IC` structure.

Lesson:

Thickness-only search has a strong tendency to fall into low-dimensional modal families controlled by symmetry, center clamping, and global stiffness distribution. Direct target drawing information does not translate cleanly into a desired eigenmode zero contour.

### Phase B: Response-Guided Closed Loop

The next step used real COMSOL feedback:

```text
target_grid
simulated_grid
missing = target - simulated
extra = simulated - target
avoid = weighted extra-response map
```

Candidate generation then tried to:

```text
increase response in missing target regions
suppress extra star/ring arms
blend high-scoring parents with error maps
inject asymmetric perturbations
```

Goal:

```text
Stop generating the same visually wrong patterns by learning from real COMSOL failure maps.
```

What happened:

This improved the search loop and helped avoid some repeated traps, but it did not create a qualitatively new `IC`-like mode. The physical response still often remained global, smooth, and center-coupled.

Lesson:

Real-response feedback is necessary, but error maps over thickness alone are not enough. The missing/extra map tells us where the nodal pattern is wrong, but it does not provide a reliable local control knob for moving eigenmode zero contours.

### Phase C: Kirchhoff-Love Plate Proxy

A simplified Kirchhoff-Love plate proxy was introduced.

The proxy uses a discrete approximation roughly equivalent to:

```text
K u = lambda M u
K ~= L^T D L
D = E h^3 / [12(1 - nu^2)]
M ~= rho h
```

The code removes center-clamp degrees of freedom and solves eigenmodes on either the design grid or an upsampled sparse grid.

Goal:

```text
Use a fast physics-inspired surrogate before expensive COMSOL simulation.
```

Variants tried:

```text
continuous KL-guided search
direct KL proxy optimization
high-resolution sparse KL proxy
KL-calibrated Bayesian candidate ranking
```

What happened:

The KL proxy could produce plausible nodal maps in its own simplified world, but KL-only high scores did not reliably transfer to COMSOL. Candidates that looked promising in the proxy often collapsed into rings, star spokes, or compact center structures in real COMSOL.

Lesson:

The KL proxy is useful as a weak physics prior, but it is not a proof of real COMSOL success. Important mismatches likely include:

```text
real shell physics versus simplified scalar plate proxy
boundary/support modeling differences
center clamp implementation differences
modal ordering and mode-shape degeneracy
COMSOL meshing and material details
loss/density modeling not fully represented in the proxy
nodal extraction threshold differences
```

Practical conclusion:

Do not trust KL-only scores. They can guide exploration, but every promising candidate must be validated by real COMSOL.

### Phase D: Strict Scoring Upgrade

The scoring system was made more strict because early metrics could reward visually wrong candidates.

Problems seen:

```text
large star-like patterns got partial overlap credit
center rings could receive misleading area/layout scores
overly broad nodal regions improved recall while destroying precision
low-order generic modes sometimes beat visually more relevant modes
```

Changes:

```text
precision and overlap balance became more important
layout, projection, topology, and complexity metrics were added
centerline overreach penalties were added
minimum target mode was raised
strict_precision_topology_v5 became the active scoring version
```

Lesson:

The scoring upgrade made the numerical result better aligned with what the human sees, but it also made the hard truth clearer: the current search is far from producing a usable custom pattern.

### Phase E: COMSOL Design Contract Expansion

The COMSOL contract was expanded beyond thickness:

```text
per-cell density scale
per-cell loss factor
global material parameters
```

This made the candidate design vector:

```text
H.csv                 -> local thickness
density_scale.csv     -> local mass/density scaling
loss_factor.csv       -> local damping/loss scaling
material_parameters   -> global material controls
```

Goal:

```text
Give the optimizer mass and damping control, not just stiffness control.
```

What happened:

This was the first step that produced relatively stable improvements. The best candidate so far came from this family:

```text
candidate_174_0002
created_by = auxiliary_physics_inverse_search
variant    = aux_loss_outer_suppress_from_candidate_173_0011_aux_local_g174_02
score      = 0.033914
```

Lesson:

Independent mass/damping fields are more useful than pure thickness changes. However, even these variables still cannot reliably sculpt letter-like nodal contours.

### Phase F: Auxiliary Physics Local Search

A family of hand-designed auxiliary physical strategies was introduced.

Examples:

```text
aux_mass_target_heavy
aux_mass_target_light
aux_loss_outer_suppress
aux_inertia_edge_heavy
aux_inertia_ring_break
aux_low_loss_target_channel
aux_heavy_loss_balanced
aux_target_edge_bridge
aux_recall_outer_trim
aux_precision_channel_guard
```

The most effective strategy was to take a high-scoring real candidate and test different density/loss fields on or near the same thickness matrix.

Goal:

```text
Separate "geometry/stiffness" from "mass/damping" and locally test physical response shaping.
```

What happened:

This became the most reliable family. Many top candidates after generation 174 are auxiliary-physics local variants:

```text
candidate_174_0002: score 0.033914, aux_loss_outer_suppress
candidate_179_0011: score 0.033129, aux_low_loss_target_channel
candidate_181_0003: score 0.032797, aux_mass_target_heavy
candidate_178_0006: score 0.032433, aux_mass_target_heavy
candidate_181_0005: score 0.032407, aux_loss_outer_suppress
```

Lesson:

Auxiliary mass/loss fields give useful control, but the improvements are incremental. They have not changed the qualitative modal family enough to create a recognizable `IC`.

### Phase G: Latent Joint Physics Search

A low-dimensional latent physics representation was added.

The latent basis maps include:

```text
target
target edge
inverse target
radial
inverse radial
current thickness field
inverse thickness field
horizontal coordinate basis
vertical coordinate basis
diagonal basis
angular symmetry-breaking basis
```

Two latent fields are composed from coefficients:

```text
density source field
loss source field
```

These are scaled into:

```text
density_scale
loss_factor
```

Goal:

```text
Stop using only hand-named auxiliary strategies and search a smoother low-dimensional physics manifold.
```

What happened:

Initial randomized latent search produced one near-best result:

```text
candidate_177_0001
created_by = latent_physics_inverse_search
score      = 0.033721
precision  = 0.105616
recall     = 0.199533
frequency  = 462.204 Hz
```

This was close to the best score but still not visually convincing.

Lesson:

The latent representation can find near-frontier candidates, but the frontier itself is still poor. This suggests the issue is not only optimizer quality; it is likely the expressiveness of the current physics contract.

### Phase H: CMA-Style Latent Coefficient Optimization

A CMA-like latent optimizer was added.

It samples latent coefficient vectors around high-scoring real anchors, selects elites by an acquisition score, updates the coefficient mean and sigma, and emits traceable metadata:

```text
latent_optimizer
latent_anchor_candidate
latent_coefficients
latent_predicted_score
latent_trusted_prediction
latent_uncertainty
latent_expected_improvement
latent_auxiliary_alignment
latent_response_correction
latent_surrogate_optimism
latent_novelty
```

Goal:

```text
Replace random latent sampling with a directed optimizer in low-dimensional coefficient space.
```

What happened:

Generation 178:

```text
best overall: candidate_178_0006, score 0.032433, auxiliary family
best CMA latent observed in that run: candidate_178_0005, score about 0.030011
```

Generation 179:

```text
best overall: candidate_179_0011, score 0.033129, auxiliary family
CMA latent candidates mostly underperformed
```

Generation 180:

```text
best overall: candidate_180_0008, score 0.032274, auxiliary family
CMA latent still underperformed
```

Generation 181:

```text
best overall: candidate_181_0003, score 0.032797, auxiliary family
latent exploration slots were reduced by adaptive scheduling
```

Lesson:

The latent optimizer was technically successful as an optimization mechanism, but it exposed surrogate optimism. The learned surrogate predicted some latent candidates would be strong, but real COMSOL scores did not confirm it.

### Phase I: Response-Calibrated Latent Scheduling

To counter surrogate optimism, the latent acquisition was changed:

```text
trusted_prediction = predicted - optimism_penalty * max(0, predicted - anchor_real_score)
```

It also added a response correction score based on real COMSOL error maps:

```text
missing target regions
extra simulated regions
avoidance regions
target channel
target edge
density field
loss field
```

Finally, adaptive family scheduling was added:

```text
If auxiliary physics outperforms latent physics in recent real COMSOL scores,
reduce latent front-loaded slots and give more slots to auxiliary physics.
```

Observed behavior:

```text
Before scheduling: 6 latent + 8 auxiliary in the first 14 candidates.
After scheduling: 3 latent + 11 auxiliary in generation 181.
```

Lesson:

The scheduler correctly recognized that auxiliary physics was more reliable than CMA latent search. This protects future runs from wasting too many expensive COMSOL calls on a currently weak family.

## 5. Best Real Candidate Table

The current top candidates under real COMSOL scoring are:

| Rank | Candidate | Family | Variant | Score | Precision | Recall | Mode | Frequency |
|---:|---|---|---|---:|---:|---:|---:|---:|
| 1 | `candidate_174_0002` | auxiliary physics | `aux_loss_outer_suppress_from_candidate_173_0011` | 0.033914 | 0.107656 | 0.214882 | 18 | 486.209 Hz |
| 2 | `candidate_177_0001` | latent physics | randomized latent from `candidate_173_0002` | 0.033721 | 0.105616 | 0.199533 | 18 | 462.204 Hz |
| 3 | `candidate_173_0011` | previous search frontier | high-scoring anchor | 0.033228 | 0.105272 | 0.204538 | 18 | 520.026 Hz |
| 4 | `candidate_176_0011` | auxiliary/search frontier | later local variant | 0.033169 | 0.105612 | 0.207207 | 18 | 504.999 Hz |
| 5 | `candidate_179_0011` | auxiliary physics | `aux_low_loss_target_channel_from_candidate_174_0002` | 0.033129 | 0.105380 | 0.206540 | 18 | 502.592 Hz |
| 6 | `candidate_181_0003` | auxiliary physics | `aux_mass_target_heavy_from_candidate_174_0002` | 0.032797 | 0.104149 | 0.200200 | 18 | 522.124 Hz |

The table shows a strong pattern:

```text
Most robust top candidates are auxiliary mass/loss variants around a few real anchors.
Latent search can approach the frontier but has not surpassed it.
KL-only and purely target-guided strategies are not reliable enough.
```

## 6. Main Failure Modes Observed

### 6.1 Center-Dominated or Ring-Like Modes

Many candidates produce nodal structures near the center clamp, compact rings, or central patches. These may have some overlap with target strokes but visually fail.

Likely causes:

```text
central clamp dominates modal topology
low-order mode families are globally constrained
local thickness changes cannot freely place zero contours
scoring can partially reward overlap even when topology is wrong
```

### 6.2 Star/Spoke Modes

Many candidates produce radial spoke patterns. These can accidentally overlap parts of letters but are visually unrelated to `IC`.

Likely causes:

```text
square plate symmetry
central clamp symmetry breaking
eigenmode degeneracy or near-degeneracy
global stiffness distribution
target-independent modal basis preferences
```

### 6.3 Proxy-to-COMSOL Mismatch

KL proxy success does not transfer reliably to COMSOL.

Likely causes:

```text
simplified scalar KL model versus COMSOL shell model
different boundary treatment
different center clamp treatment
mesh and interpolation effects
modal index switching
threshold-sensitive nodal extraction
missing density/loss implementation in proxy
```

### 6.4 Surrogate Optimism

The Bayesian/latent surrogate can predict high scores for candidates that fail in real COMSOL.

Likely causes:

```text
real dataset is still small for a high-dimensional nonlinear inverse problem
candidate families are not independent samples
many candidates are local variants around a few anchors
score range is narrow
surrogate cannot infer actual eigenmode topology from weak features alone
```

### 6.5 Current Design Space May Be Under-Expressive

Even the best candidates remain around:

```text
precision around 0.10
recall around 0.20
IoU around 0.07
Dice around 0.14
```

This is not an optimizer convergence story alone. It suggests the current design variables may not have enough control authority over arbitrary letter-like nodal sets.

## 7. Scientific Interpretation

The inverse problem should be framed as:

Find physical design variables `p` such that for some eigenmode `k`, the zero level set of the eigenfunction resembles the target set `T`:

```text
Z(w_k(p)) ~= T
```

where:

```text
K(p) w_k = lambda_k M(p) w_k
```

This is difficult because:

```text
the target is a zero-level set, not an amplitude image
eigenmode sign is arbitrary
mode index can switch under small parameter changes
near-degenerate modes can rotate within eigenspaces
zero contours are global objects controlled by the whole operator
not every drawing is physically realizable as a nodal set under fixed boundary conditions
```

The current algorithm mostly searches design variables and checks output similarity. A more academic approach should optimize the operator and eigenfunction structure directly.

## 8. Recommended Research Directions

### Direction 1: Add Topology Variables

The next COMSOL contract should allow:

```text
holes
slots
cutouts
ribs
local added masses
```

Why:

Topology can change modal families much more strongly than continuous thickness/density fields. Letter-like nodal patterns may require structural features that break symmetry and guide zero contours.

Suggested representation:

```text
coarse binary or level-set topology field
manufacturing constraints on minimum feature size
regularization for connected material
optional symmetry-breaking priors
```

### Direction 2: Optimize Boundary and Excitation

The current model is mainly eigenfrequency matching. Real Chladni figures in experiments are often forced responses, not arbitrary eigenmode selection.

Potential variables:

```text
support position
clamp radius
actuator position
actuator phase
drive frequency
multi-point excitation
```

Why:

If the user wants to see a pattern physically, forced-response control may be more practical than hoping one natural eigenmode exactly matches the drawing.

### Direction 3: Use an Adjoint or Differentiable Eigenmode Optimizer

A research-grade method should compute sensitivities:

```text
d lambda_k / d p
d w_k / d p
d loss(Z(w_k), T) / d p
```

Potential routes:

```text
COMSOL sensitivity / adjoint module if available
MATLAB finite-element eigen-sensitivity implementation
JAX/PyTorch differentiable plate solver
custom sparse FE solver with autograd
```

The loss should be based on a signed distance transform of the target:

```text
L_mode = mean over pixels near simulated zero contour of distance_to_target
       + mean over target pixels of distance_to_simulated_zero_contour
       + topology/coverage penalties
```

This is probably more meaningful than optimizing IoU after thresholding only.

### Direction 4: Treat Modal Degeneracy Explicitly

Instead of scoring only individual modes, handle mode subspaces.

If eigenvalues are close:

```text
span(w_i, w_j, ...)
```

may contain a linear combination whose nodal set is better than any exported basis vector. COMSOL may output an arbitrary basis inside a near-degenerate eigenspace.

Research question:

Can we optimize over linear combinations of near-degenerate modes before declaring a design failure?

### Direction 5: Active Learning with Family-Level Budgeting

Continue using real COMSOL feedback, but formulate the problem as active learning:

```text
candidate family
predicted score
uncertainty
family historical reliability
expected information gain
COMSOL cost
```

The adaptive scheduler added recently is a primitive version of this. A more formal version could use:

```text
multi-armed bandits
Bayesian optimization with trust regions
ensemble disagreement
Thompson sampling over candidate families
```

### Direction 6: Feasibility Analysis Before Optimization

Before spending more COMSOL time, analyze whether a requested image is likely realizable under a given contract.

Possible feasibility predictors:

```text
target topology complexity
stroke width and connectivity
distance from center clamp
required number of nodal branches
symmetry mismatch
estimated modal order
minimum feature size relative to 15 x 15 grid
```

This could tell users:

```text
easy target
possible but high cost
requires topology variables
likely impossible under current plate/support contract
```

## 9. What Not To Do Next

Avoid these tempting but likely unproductive moves:

```text
Do not simply increase random generations indefinitely.
Do not trust KL proxy winners without COMSOL validation.
Do not optimize scoring weights until bad visuals look good numerically.
Do not keep giving many front-loaded slots to a family after real scores show it underperforms.
Do not assume arbitrary logo drawings are realizable as eigenmode nodal sets under fixed support.
Do not treat the target as an amplitude pattern; it is a desired zero-contour pattern.
```

## 10. Recommended Immediate Next Step

The most useful next research step is:

```text
Add topology or boundary/excitation variables to the COMSOL contract,
then build an optimizer that works on a signed-distance zero-contour loss.
```

Practical staged plan:

1. Add one new high-impact COMSOL variable family, preferably `hole_or_slot_topology`.
2. Keep the 15 x 15 thickness/density/loss fields active.
3. Represent topology on a coarse grid with minimum feature constraints.
4. Run a small design-of-experiments batch to see if topology changes mode families more strongly.
5. Fit a surrogate only after collecting real COMSOL topology samples.
6. Use active family scheduling to allocate expensive COMSOL calls.
7. If topology helps, move toward differentiable or adjoint optimization.

Alternative staged plan:

1. Add actuator/support position variables first.
2. Switch objective from pure eigenmode matching to forced-response nodal pattern matching.
3. Treat drive frequency as a variable.
4. Score the steady-state response pattern instead of only natural eigenmodes.

The forced-response route may be more aligned with real Chladni-figure control.

## 11. Files and Code Areas To Inspect

Important configuration:

```text
config.yaml
```

Candidate generation:

```text
src/candidate/generate_candidate.py
```

KL proxy:

```text
src/physics/kirchhoff_love.py
```

Scoring:

```text
src/scoring/metrics.py
src/scoring/score_candidate.py
src/scoring/feasibility.py
```

COMSOL contract:

```text
src/comsol/export_parameters.py
comsol_templates/run_chladni_candidate.m
comsol_templates/apply_design_variable_contract.m
```

Current feasibility summary:

```text
reports/feasibility_report.json
```

Current best candidates:

```text
candidates/candidate_174_0002
candidates/candidate_177_0001
candidates/candidate_179_0011
candidates/candidate_181_0003
```

COMSOL exports:

```text
data/comsol_exports/<candidate_id>
```

Frontend result review:

```text
frontend/target_designer.html
src/frontend/target_ui_server.py
```

## 12. Suggested Prompt For Another Research AI

The following prompt can be given to another AI:

```text
We are working on inverse design for a Chladni plate. The goal is to generate a manufacturable plate whose simulated nodal pattern resembles a user-provided target drawing such as an IC logo.

Current system:
- Plate: 150 mm x 150 mm.
- Design grid: 15 x 15.
- Center clamp radius: 8 mm.
- Variables currently exposed to COMSOL: per-cell thickness, global material, per-cell density scale, per-cell loss factor.
- Simulation: COMSOL/MATLAB LiveLink eigenfrequency modes.
- Scoring: strict nodal-line pattern similarity at 256 x 256 resolution.
- Current best after 293 real COMSOL candidates: candidate_174_0002 with score 0.033914, precision 0.107656, recall 0.214882, IoU 0.077265.
- Diagnostic status: physics_limited_current_contract.

Already tried:
- Random and evolutionary thickness search.
- Target-guided thickness maps.
- Real-response feedback using missing/extra nodal maps.
- Kirchhoff-Love plate proxy with direct optimization and sparse high-resolution solve.
- Strict precision/topology scoring.
- Per-cell density and loss-factor auxiliary physics.
- Hand-designed auxiliary mass/damping local-search variants.
- Low-dimensional latent physics fields for density/loss.
- CMA-style latent coefficient optimization.
- Response-calibrated latent acquisition.
- Adaptive candidate-family scheduling.

Empirical finding:
- Auxiliary mass/loss local search is the most reliable family but only gives incremental gains.
- Latent search can approach the current frontier but has not exceeded it.
- KL proxy scores do not reliably transfer to COMSOL.
- Current outputs still look like generic plate modes, not the requested logo.

Please analyze this as a research problem. We need a fundamental next-step algorithmic and physical-design-space breakthrough, not just hyperparameter tuning. Consider inverse eigenvalue/eigenfunction optimization, topology optimization, forced-response rather than eigenmode matching, support/actuator variables, adjoint or differentiable FE methods, mode-subspace handling for near-degenerate eigenvalues, and feasibility limits for arbitrary target nodal sets.
```

## 13. Final Research Hypothesis

The present algorithm is not failing because it lacks enough search loops. It is failing because the target is an arbitrary symbolic drawing, while the current physical contract only weakly perturbs a constrained plate eigenproblem.

The next successful method will likely need at least one of:

```text
topological design freedom
support/excitation freedom
forced-response control
adjoint/differentiable eigenmode optimization
mode-subspace optimization
target feasibility prediction
```

In short:

The current system is a functioning automation and evaluation platform, but not yet a sufficiently expressive inverse-design engine for arbitrary custom Chladni logos.
