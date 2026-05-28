# Frequency Domain Validation Summary / 频域验证总结

## Purpose / 研究目的

验证 A / target thick 是否能在单中心激励 frequency-domain 下形成 IC-like low-amplitude valley。

## Input / 输入信息

- Case: `pipeline_diagonal_v1_w6_pipeline_diagonal_v1_v2_strong`
- Target: `data/processed_targets/target_binary.npy`
- COMSOL export path: `data/comsol_frequency_exports/pipeline_diagonal_v1_w6_pipeline_diagonal_v1_v2_strong`
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
| 1 | 860.000 | 0.0801 | 0.0962 | 1.201 | 0.111 | 0.139 |
| 2 | 950.000 | 0.0715 | 0.0822 | 1.149 | 0.116 | 0.129 |
| 3 | 200.000 | 0.0777 | 0.0813 | 1.047 | 0.099 | 0.128 |
| 4 | 750.000 | 0.0461 | 0.0495 | 1.074 | 0.114 | 0.123 |
| 5 | 474.000 | 0.1015 | 0.1028 | 1.013 | 0.095 | 0.119 |
| 6 | 300.000 | 0.0868 | 0.0863 | 0.994 | 0.106 | 0.107 |
| 7 | 640.000 | 0.1013 | 0.0970 | 0.957 | 0.106 | 0.104 |
| 8 | 540.000 | 0.0695 | 0.0597 | 0.860 | 0.100 | 0.103 |
| 9 | 400.000 | 0.1213 | 0.1191 | 0.982 | 0.111 | 0.097 |

## Decision / 判据与结论

- Best frequency: `860.000 Hz`
- Best valley contrast: `1.201`
- Best final score: `0.139`
- Target lower than side band: `True`
- Recommendation state: `not_ready_for_printing_redesign_tags_a_plus`
结论：暂不建议进入打印实验。A 的窄频 eigenmode 可行性尚未转化为真实中心激励频响，需要 TAGS-A+ 几何重设计。

## TAGS-A+ Next Step / TAGS-A+ 下一步

如果 A 频域验证不达标，下一步不是回到 B/C，也不是 225-cell 独立优化，而是以 A 为主族做低维目标对齐几何重设计。目标是提高 narrowband score、降低 frequency spread、提高 center-drive reachability，同时仍不添加外部实验设施。

建议几何族：A1 target thick mild；A2 target thick medium；A3 target thick strong；A4 target thick + side soft mild；A5 target thick + side soft strong；A6 segmented target thick；A7 segmented target thick + side soft；A8 target thick + edge tuning；A9 segmented target thick + edge tuning；A10 segmented target thick + side soft + edge tuning。
