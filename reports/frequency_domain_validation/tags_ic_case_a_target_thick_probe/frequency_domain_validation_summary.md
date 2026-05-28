# Frequency Domain Validation Summary / 频域验证总结

## Purpose / 研究目的

验证 A / target thick 是否能在单中心激励 frequency-domain 下形成 IC-like low-amplitude valley。

## Input / 输入信息

- Case: `tags_ic_case_a_target_thick_probe`
- Target: `data/processed_targets/target_binary.npy`
- COMSOL export path: `data/comsol_frequency_exports/tags_ic_case_a_target_thick_probe`
- Frequency samples: `1`
- Frequency range: `301.100-301.100 Hz`
- Detected export format: `combined_csv`

## Method / 方法

后处理使用振幅图 `A(x,y)=|u_z(x,y,ω)|`。目标线扩展为 target band，目标两侧构造 side band。评分奖励 target band 上低振幅、side band 上相对高振幅，并惩罚远离目标的大量低振幅谷线。

这里不用 signed zero crossing 作为主指标，因为 frequency-domain 响应和真实沙粒实验看到的是振动幅值低谷，而不是本征模态符号零线。

## Top 10 Frequencies / 前 10 个频率

| Rank | Frequency Hz | Target Mean | Side Mean | Contrast | Extra Penalty | Final Score |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 301.100 | 0.1612 | 0.1676 | 1.040 | 0.109 | 0.099 |

## Decision / 判据与结论

- Best frequency: `301.100 Hz`
- Best valley contrast: `1.040`
- Best final score: `0.099`
- Target lower than side band: `True`
- Recommendation state: `not_ready_for_printing_redesign_tags_a_plus`
结论：暂不建议进入打印实验。A 的窄频 eigenmode 可行性尚未转化为真实中心激励频响，需要 TAGS-A+ 几何重设计。

## TAGS-A+ Next Step / TAGS-A+ 下一步

如果 A 频域验证不达标，下一步不是回到 B/C，也不是 225-cell 独立优化，而是以 A 为主族做低维目标对齐几何重设计。目标是提高 narrowband score、降低 frequency spread、提高 center-drive reachability，同时仍不添加外部实验设施。

建议几何族：A1 target thick mild；A2 target thick medium；A3 target thick strong；A4 target thick + side soft mild；A5 target thick + side soft strong；A6 segmented target thick；A7 segmented target thick + side soft；A8 target thick + edge tuning；A9 segmented target thick + edge tuning；A10 segmented target thick + side soft + edge tuning。
