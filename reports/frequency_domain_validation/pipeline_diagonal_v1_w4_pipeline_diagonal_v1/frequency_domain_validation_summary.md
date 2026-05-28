# Frequency Domain Validation Summary / 频域验证总结

## Purpose / 研究目的

验证 A / target thick 是否能在单中心激励 frequency-domain 下形成 IC-like low-amplitude valley。

## Input / 输入信息

- Case: `pipeline_diagonal_v1_w4_pipeline_diagonal_v1`
- Target: `data/processed_targets/target_binary.npy`
- COMSOL export path: `data/comsol_frequency_exports/pipeline_diagonal_v1_w4_pipeline_diagonal_v1`
- Frequency samples: `9`
- Frequency range: `200.000-950.000 Hz`
- Detected export format: `combined_csv`

## Method / 方法

后处理使用振幅图 `A(x,y)=|u_z(x,y,ω)|`。目标线扩展为 target band，目标两侧构造 side band。评分奖励 target band 上低振幅、side band 上相对高振幅，并惩罚远离目标的大量低振幅谷线。

这里不用 signed zero crossing 作为主指标，因为 frequency-domain 响应和真实沙粒实验看到的是振动幅值低谷，而不是本征模态符号零线。

## Valley Schematics / 波谷示意图

- `best_valley_schematic.png`: 最佳频率的 Target / Valley / Overlay 三联图。
- `all_frequency_valley_schematics.png`: 每个频率对应低振幅波谷的总览图。
- `valley_schematics/freq_*_valley_schematic.png`: 每个频率独立的波谷示意图。
这些示意图显示的是最低振幅核心区，便于观察每个频率的波谷形状；数值判定仍使用完整 amplitude-valley score。

## Top 10 Frequencies / 前 10 个频率

| Rank | Frequency Hz | Target Mean | Side Mean | Contrast | Extra Penalty | Final Score |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 640.000 | 0.0415 | 0.0673 | 1.620 | 0.104 | 0.200 |
| 2 | 400.000 | 0.0708 | 0.0907 | 1.281 | 0.104 | 0.152 |
| 3 | 950.000 | 0.0443 | 0.0481 | 1.086 | 0.102 | 0.139 |
| 4 | 300.000 | 0.0477 | 0.0541 | 1.134 | 0.113 | 0.132 |
| 5 | 750.000 | 0.0608 | 0.0669 | 1.100 | 0.110 | 0.124 |
| 6 | 540.000 | 0.0806 | 0.0873 | 1.083 | 0.110 | 0.119 |
| 7 | 200.000 | 0.1288 | 0.1307 | 1.015 | 0.097 | 0.097 |
| 8 | 474.000 | 0.1600 | 0.1565 | 0.978 | 0.111 | 0.093 |
| 9 | 860.000 | 0.1764 | 0.1412 | 0.800 | 0.099 | 0.078 |

## Decision / 判据与结论

- Best frequency: `640.000 Hz`
- Best valley contrast: `1.620`
- Best final score: `0.200`
- Target lower than side band: `True`
- Recommendation state: `weak_frequency_domain_candidate`
结论：当前只是弱可行。建议围绕最佳频率继续局部精扫并复核波谷示意图，暂不直接进入打印实验。

## TAGS-A+ Next Step / TAGS-A+ 下一步

如果 A 频域验证不达标，下一步不是回到 B/C，也不是 225-cell 独立优化，而是以 A 为主族做低维目标对齐几何重设计。目标是提高 narrowband score、降低 frequency spread、提高 center-drive reachability，同时仍不添加外部实验设施。

建议几何族：A1 target thick mild；A2 target thick medium；A3 target thick strong；A4 target thick + side soft mild；A5 target thick + side soft strong；A6 segmented target thick；A7 segmented target thick + side soft；A8 target thick + edge tuning；A9 segmented target thick + edge tuning；A10 segmented target thick + side soft + edge tuning。
