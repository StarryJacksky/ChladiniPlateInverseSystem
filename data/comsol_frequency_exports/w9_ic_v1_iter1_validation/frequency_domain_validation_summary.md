# Frequency Domain Validation Summary / 频域验证总结

## Purpose / 研究目的

验证 A / target thick 是否能在单中心激励 frequency-domain 下形成 IC-like low-amplitude valley。

## Input / 输入信息

- Case: `w9_ic_v1_iter1`
- Target: `data/processed_targets/target_binary.npy`
- COMSOL export path: `data/comsol_frequency_exports/w9_ic_v1_iter1`
- Frequency samples: `6`
- Frequency range: `225.500-938.700 Hz`
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
| 1 | 594.500 | 0.0148 | 0.0288 | 1.947 | 0.115 | 0.214 |
| 2 | 225.500 | 0.0228 | 0.0319 | 1.399 | 0.103 | 0.167 |
| 3 | 775.800 | 0.0389 | 0.0488 | 1.254 | 0.118 | 0.142 |
| 4 | 706.800 | 0.0673 | 0.0732 | 1.088 | 0.112 | 0.122 |
| 5 | 381.800 | 0.0678 | 0.0703 | 1.037 | 0.119 | 0.107 |
| 6 | 938.700 | 0.1893 | 0.1511 | 0.798 | 0.105 | 0.093 |

## Decision / 判据与结论

- Best frequency: `594.500 Hz`
- Best valley contrast: `1.947`
- Best final score: `0.214`
- Target lower than side band: `True`
- Recommendation state: `weak_frequency_domain_candidate`
结论：当前只是弱可行。建议围绕最佳频率继续局部精扫并复核波谷示意图，暂不直接进入打印实验。

## TAGS-A+ Next Step / TAGS-A+ 下一步

如果 A 频域验证不达标，下一步不是回到 B/C，也不是 225-cell 独立优化，而是以 A 为主族做低维目标对齐几何重设计。目标是提高 narrowband score、降低 frequency spread、提高 center-drive reachability，同时仍不添加外部实验设施。

建议几何族：A1 target thick mild；A2 target thick medium；A3 target thick strong；A4 target thick + side soft mild；A5 target thick + side soft strong；A6 segmented target thick；A7 segmented target thick + side soft；A8 target thick + edge tuning；A9 segmented target thick + edge tuning；A10 segmented target thick + side soft + edge tuning。
