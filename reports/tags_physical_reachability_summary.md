# TAGS Physical Reachability Summary / TAGS 物理可达性总结

Single-eigenmode scoring underestimates TAGS, but full free modal-subspace scoring overestimates physical reachability. Therefore, the relevant decision metric is narrowband, center-drive-reachable modal-subspace feasibility, followed by COMSOL frequency-domain validation using amplitude-valley scoring.

本报告把自由模态组合只当作数学表达能力参考，不把它当成真实单频中心激励实验预测。

## A/B/C Comparison / A/B/C 对比

| Case | Free Dice | Free Layout | Best beta | NB Dice | NB Layout | B_alpha | R_drive | PhysicalScore | Recommendation | Sweep |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| tags_ic_case_a_target_thick | 0.163 | 0.497 | 0.15 | 0.241 | 0.617 | 0.100 | 0.554 | 0.355 | validate | 255.9-346.3 Hz |
| tags_ic_case_b_target_thin | 0.171 | 0.501 | 0.05 | 0.084 | 0.210 | 0.014 | 0.955 | 0.211 | validate | 479.6-648.8 Hz |
| tags_ic_case_c_target_thin_side_thick | 0.173 | 0.514 | 0.15 | 0.224 | 0.578 | 0.029 | 0.182 | 0.097 | redesign first | 246.9-334.1 Hz |

## Interpretation / 解读

当前最适合进入 COMSOL 频域验证的是 `tags_ic_case_a_target_thick`，推荐围绕 `301.1 Hz` 做约 ±15% 扫频。

若某案例自由分数高但窄频分数、中心驱动参与度低，它只能说明该结构的 COMSOL 模态字典在数学上能拼出目标轮廓，不能说明单频中心激励能真实出现该图案。

## Boundary Condition Warning / 频域边界条件提醒

Eigenfrequency 里中心固定区可用于自然模态分析；但 Frequency Domain 里不要在同一个中心区域同时施加零位移固定和谐波激励，否则模型会过约束。建议选择：小中心区谐波 z 位移、小中心区谐波力，或简化 shaker/contact connector 三者之一。

## TAGS-A+ Recommendation / TAGS-A+ 建议

15×15 网格应继续作为输出分辨率，而不是 225 维独立优化变量。下一轮建议使用低维目标对齐参数：target band offset、side band offset、I stem/top/bottom offsets、C upper/left/lower arc offsets、edge tuning offsets、background thickness、smoothing radius。

建议几何族：A1 target thick mild，A2 target thick medium，A3 target thick strong，A4 target thick + side soft mild，A5 target thick + side soft strong，A6 segmented target thick，A7 segmented target thick + side soft，A8 target thick + edge tuning，A9 segmented target thick + edge tuning，A10 segmented target thick + side soft + edge tuning。

## Loader Warnings / 数据加载警告

- `tags_ic_case_a_target_thick`: no modal-loading warnings. / 无模态加载警告。
- `tags_ic_case_b_target_thin`: no modal-loading warnings. / 无模态加载警告。
- `tags_ic_case_c_target_thin_side_thick`: no modal-loading warnings. / 无模态加载警告。
