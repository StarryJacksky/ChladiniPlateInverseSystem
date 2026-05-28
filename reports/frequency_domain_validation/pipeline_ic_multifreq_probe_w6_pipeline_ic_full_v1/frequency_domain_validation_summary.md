# Frequency Domain Validation Summary / 频域验证总结

## Purpose / 研究目的

验证 A / target thick 是否能在单中心激励 frequency-domain 下形成 IC-like low-amplitude valley。

## Input / 输入信息

- Case: `pipeline_ic_multifreq_probe_w6_pipeline_ic_full_v1`
- Target: `data/processed_targets/target_binary.npy`
- COMSOL export path: `data/comsol_frequency_exports/pipeline_ic_multifreq_probe_w6_pipeline_ic_full_v1`
- Frequency samples: `9`
- Frequency range: `180.000-920.000 Hz`
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
| 1 | 636.547 | 0.0145 | 0.0318 | 2.191 | 0.106 | 0.245 |
| 2 | 720.000 | 0.0198 | 0.0327 | 1.652 | 0.114 | 0.185 |
| 3 | 420.000 | 0.0342 | 0.0450 | 1.316 | 0.095 | 0.168 |
| 4 | 250.000 | 0.0376 | 0.0449 | 1.193 | 0.103 | 0.149 |
| 5 | 820.000 | 0.1131 | 0.1321 | 1.168 | 0.090 | 0.145 |
| 6 | 180.000 | 0.0508 | 0.0591 | 1.162 | 0.110 | 0.140 |
| 7 | 320.000 | 0.0647 | 0.0705 | 1.089 | 0.116 | 0.121 |
| 8 | 540.000 | 0.0498 | 0.0489 | 0.983 | 0.110 | 0.113 |
| 9 | 920.000 | 0.1004 | 0.1071 | 1.067 | 0.118 | 0.107 |

## Decision / 判据与结论

- Best frequency: `636.547 Hz`
- Best valley contrast: `2.191`
- Best final score: `0.245`
- Target lower than side band: `True`
- Recommendation state: `good_frequency_domain_candidate`
结论：建议在最佳频率附近做局部精扫，并准备进入 CAD/打印验证。

## TAGS-A+ Next Step / TAGS-A+ 下一步

如果 A 频域验证不达标，下一步不是回到 B/C，也不是 225-cell 独立优化，而是以 A 为主族做低维目标对齐几何重设计。目标是提高 narrowband score、降低 frequency spread、提高 center-drive reachability，同时仍不添加外部实验设施。

建议几何族：A1 target thick mild；A2 target thick medium；A3 target thick strong；A4 target thick + side soft mild；A5 target thick + side soft strong；A6 segmented target thick；A7 segmented target thick + side soft；A8 target thick + edge tuning；A9 segmented target thick + edge tuning；A10 segmented target thick + side soft + edge tuning。
