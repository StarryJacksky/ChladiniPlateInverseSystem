# TAGS Physical Filter Usage / TAGS 物理过滤器用法

## Purpose / 用途

This tool does not replace COMSOL frequency-domain validation. It ranks TAGS candidates by narrowband, center-drive-reachable modal-subspace feasibility, using COMSOL eigenmode exports as input.

这个工具不是替代 COMSOL 频域验证，而是用已经导出的 COMSOL 本征模态，对 TAGS 候选做“窄频带 + 中心激励可达性”的物理筛选。

## Required Input / 所需输入

Each case directory should contain:

- `mode_08.csv` through at least `mode_40.csv`
- `frequencies.csv`

每个案例目录需要包含：

- `mode_08.csv` 到至少 `mode_40.csv`
- `frequencies.csv`

The mode CSV loader accepts scattered `x,y,w` style exports. It also tries common displacement column names such as `uz`, `u_z`, `disp`, and `shell.disp`.

模态 CSV 读取器支持散点式 `x,y,w` 导出，也会尝试识别 `uz`、`u_z`、`disp`、`shell.disp` 等常见位移列名。

## Command / 命令

```bash
python -m src.analysis.run_tags_physical_filter \
  --cases tags_ic_case_a_target_thick tags_ic_case_b_target_thin tags_ic_case_c_target_thin_side_thick \
  --mode-start 8 \
  --mode-end 40
```

## Outputs / 输出

- `reports/tags_physical_filter_results.csv`
- `reports/tags_physical_reachability_summary.md`
- `reports/figures/free_response_case_*.png`
- `reports/figures/best_narrowband_response_case_*_beta_*.png`
- `reports/figures/alpha_frequency_barplot_case_*.png`
- `reports/figures/drive_participation_barplot_case_*.png`
- `reports/figures/summary_physical_score_barplot.png`

## Interpretation / 解读

`free_dice` and `free_layout` show mathematical expressiveness only. High free score can be misleading when the coefficient mix spans widely separated frequencies.

`free_dice` 和 `free_layout` 只表示数学表达能力。如果系数组合横跨很远的频率，高自由分数可能会误导。

`narrowband_dice`, `narrowband_layout`, and `narrowband_frequency_spread` show whether the target-like combination can be formed inside one frequency neighborhood.

`narrowband_dice`、`narrowband_layout` 和 `narrowband_frequency_spread` 表示目标相似组合能否在一个频率邻域内形成。

`center_drive_reachability` estimates whether the modes in that combination have enough participation near the center drive region.

`center_drive_reachability` 估计该组合里的模态在中心激励区域是否有足够参与度。

`physical_score` is the practical ranking score. It favors target-like, narrowband, center-drive-reachable combinations and penalizes overly broad or too-many-mode mixtures.

`physical_score` 是实用排序分数。它偏好像目标、窄频、中心可激励的组合，并惩罚过宽频或依赖太多模态的混合。

## Current A/B/C Result / 当前 A/B/C 结果

The current run ranks `tags_ic_case_a_target_thick` highest and recommends COMSOL frequency-domain validation around roughly `301 Hz ± 15%`. Case B has high center-drive reachability in a narrow window, but its narrowband visual match is weaker. Case C has reasonable visual narrowband structure, but weak center-drive reachability.

当前运行中 `tags_ic_case_a_target_thick` 排名最高，建议围绕约 `301 Hz ± 15%` 做 COMSOL 频域验证。B 案例在一个窄频窗里中心可激性很高，但窄频视觉相似性较弱。C 案例窄频视觉结构尚可，但中心驱动可达性偏弱。
