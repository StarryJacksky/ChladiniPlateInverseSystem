# COMSOL Frequency Domain Validation Guide / COMSOL 频域验证指南

## 1. Validation Object / 验证对象

主验证对象是 `tags_ic_case_a_target_thick`。

- 推荐中心频率：`301.1 Hz`
- 推荐第一轮扫频范围：`301.1 Hz ±15%`
- 对应范围约为：`255.9 Hz` 到 `346.3 Hz`
- 第一轮建议步长：`2 Hz` 或 `5 Hz`
- 如果发现 IC 目标线附近出现连续低振幅谷线，再围绕局部峰值用 `0.5 Hz` 或 `1 Hz` 精扫

This validation is meant to test whether the TAGS-A target-thick geometry can create an IC-like low-amplitude valley under a physically driven frequency-domain response.

## 2. COMSOL Study Type / COMSOL Study 类型

请使用：

- `Frequency Domain`
- 或同等的 `Harmonic Response`

不要只做 `Eigenfrequency`。Eigenfrequency 只用于提供模态、窄频候选和物理过滤依据，不能替代真实频域验证。

## 3. Boundary Condition Warning / 边界条件警告

如果 eigenfrequency study 里中心区域被设为 `Fixed Constraint`，这对自然模态分析是可以接受的。

但在 frequency-domain study 中，不要把同一个中心区域同时：

- fixed 到零位移；
- 又施加 harmonic excitation。

这会导致模型过约束，或导致激励无法有效进入结构。

推荐选择以下二选一：

1. 在中心驱动区域施加 harmonic prescribed z-displacement；
2. 在中心驱动区域施加 harmonic force。

团队需要明确实际实验更接近位移驱动还是力驱动。当前后处理代码两种导出都可以评分，因为它只读取上表面的 `|u_z|` 振幅响应。

## 4. Recommended Frequency-Domain Output / 推荐频域输出

输出 top observation surface 上的 out-of-plane response。

如果 COMSOL 输出复数响应，请导出：

```text
real(uz), imag(uz)
```

或者直接导出：

```text
abs(uz)
```

Python 后处理使用：

```text
A(x, y, omega) = |u_z(x, y, omega)|
```

它不会把 signed zero-crossing 当作主评分。

## 5. Target Pattern Definition / 目标图案定义

目标是 IC 的 skeleton / centerline / line-like pattern，不是填充面积。

评分关心的是：

- 目标线附近是否成为低振幅谷线；
- 目标线两侧是否有更高振幅形成对比；
- 远离目标处是否出现大量错误低谷。

上表面应尽量保持平整，避免沙粒被几何台阶直接卡住。TAGS 几何应尽量隐藏在下表面或被动厚度场中。

## 6. COMSOL Export Format / COMSOL 导出格式

两种格式都支持。

### Format A: One CSV Per Frequency / 每个频率一个 CSV

推荐路径：

```text
data/comsol_frequency_exports/tags_ic_case_a_target_thick/freq_301p1.csv
```

CSV columns 可选：

```text
x,y,abs_uz
```

或：

```text
x,y,real_uz,imag_uz
```

文件名里的 `301p1` 会被解析为 `301.1 Hz`。

### Format B: Combined CSV / 统一 CSV

推荐路径：

```text
data/comsol_frequency_exports/tags_ic_case_a_target_thick/frequency_response.csv
```

CSV columns 可选：

```text
frequency_hz,x,y,abs_uz
```

或：

```text
frequency_hz,x,y,real_uz,imag_uz
```

## 7. Python Postprocessing Entry / Python 后处理入口

COMSOL 导出完成后运行：

```bash
python -m src.analysis.run_frequency_domain_validation \
  --case tags_ic_case_a_target_thick \
  --export-path data/comsol_frequency_exports/tags_ic_case_a_target_thick \
  --target data/processed_targets/target_binary.npy \
  --output-dir reports/frequency_domain_validation/tags_ic_case_a_target_thick
```

如果目标文件路径不同，可以把 `--target` 改成实际目标图片或 `.npy` 文件。

输出会生成：

- `frequency_domain_scores.csv`
- `frequency_domain_validation_summary.md`
- `best_frequency_response.png`
- `target_band_overlay.png`
- `score_vs_frequency.png`
- `top_5_frequency_previews.png`

## 8. Decision Rule / 判定规则

建议使用简单判据：

- `valley_contrast > 1.5`：弱可行；
- `valley_contrast > 2.0`：较好；
- `valley_contrast > 3.0`：强；
- 同时 `extra_valley_penalty` 不能太高；
- 目标线附近应视觉上形成连续低振幅路径。

如果 A 案例通过，建议在最佳频率附近做局部精扫并进入 CAD/打印验证。

如果 A 案例不通过，说明窄频 eigenmode 可行性没有转化为真实中心激励频响，下一步应做 TAGS-A+ 几何重设计，而不是回到自由线性组合或盲搜 225 个 cell。
