from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

"""D4 不可约表示（irrep）分解工具。/ D4 irreducible-representation decomposition toolkit.

正方形板有 D4 对称（4 重旋转 + 4 条镜面反射）。任何标量场 P : ℝ²→ℝ 可以唯一分解为
P = P_{A1} ⊕ P_{A2} ⊕ P_{B1} ⊕ P_{B2} ⊕ P_E，其中
- A1: 全对称（中心鼓包、(2,2)、(3,3) 等偶-偶模态）
- A2: 旋转偶、镜面奇（手性陀螺）
- B1: 90° 旋转奇、沿轴镜面 +、沿对角镜面 -（沿 x/y 轴节线模式）
- B2: 90° 旋转奇、沿轴镜面 -、沿对角镜面 +（沿对角线节线模式）
- E:  二维表示（手性对子，左右不等价）

中心点 + D∞ 等效激振只耦合到 A1 子空间。因此目标在 A1 上的能量占比给出物理可达上限。
The square plate has D4 symmetry. Center-point excitation (D∞-equivalent) only couples
to A1; the A1 energy ratio of the target gives an upper bound for achievable patterns.
"""

import numpy as np  # 数值库 / Numerical library


D4_OPERATIONS: list[str] = ["e", "r1", "r2", "r3", "s_x", "s_y", "s_d", "s_ad"]  # 8 个 D4 元素 / 8 D4 elements


D4_CHARACTERS: dict[str, dict[str, int]] = {
    "A1": {"e": 1, "r1": 1, "r2": 1, "r3": 1, "s_x": 1, "s_y": 1, "s_d": 1, "s_ad": 1},  # 全对称 / Trivial
    "A2": {"e": 1, "r1": 1, "r2": 1, "r3": 1, "s_x": -1, "s_y": -1, "s_d": -1, "s_ad": -1},  # 手性陀螺 / Pseudoscalar
    "B1": {"e": 1, "r1": -1, "r2": 1, "r3": -1, "s_x": 1, "s_y": 1, "s_d": -1, "s_ad": -1},  # 沿轴镜面 + / Axis-symmetric
    "B2": {"e": 1, "r1": -1, "r2": 1, "r3": -1, "s_x": -1, "s_y": -1, "s_d": 1, "s_ad": 1},  # 对角镜面 + / Diagonal-symmetric
    "E":  {"e": 2, "r1": 0, "r2": -2, "r3": 0, "s_x": 0, "s_y": 0, "s_d": 0, "s_ad": 0},  # 二维表示 / 2-D representation
}  # 特标表 / Character table


def apply_d4_operation(image: np.ndarray, op: str) -> np.ndarray:  # 把一个 D4 操作作用到图像 / Apply a D4 operation to an image
    if op == "e":  # 恒等 / Identity
        return image.copy()  # 复制 / Copy
    if op == "r1":  # 逆时针旋转 90° / CCW 90 rotation
        return np.rot90(image, k=1)  # numpy rot90 / numpy rot90
    if op == "r2":  # 旋转 180° / 180 rotation
        return np.rot90(image, k=2)  # rot90 k=2 / rot90 k=2
    if op == "r3":  # 顺时针旋转 90° / CW 90 rotation
        return np.rot90(image, k=3)  # rot90 k=3 / rot90 k=3
    if op == "s_x":  # 沿 x 轴（水平）镜面，y → -y（垂直翻转） / x-axis mirror, flip vertical
        return np.flipud(image)  # 上下翻转 / Flip up-down
    if op == "s_y":  # 沿 y 轴（垂直）镜面，x → -x（水平翻转） / y-axis mirror, flip horizontal
        return np.fliplr(image)  # 左右翻转 / Flip left-right
    if op == "s_d":  # 沿主对角线镜面 → 转置 / Main-diagonal mirror = transpose
        return image.T  # 转置 / Transpose
    if op == "s_ad":  # 沿反对角线镜面 = 旋转 90° 后转置 / Anti-diagonal mirror = transpose-after-180
        return np.rot90(image, k=2).T  # 反对角 / Anti-diagonal
    raise ValueError(f"Unknown D4 operation: {op} / 未知 D4 操作：{op}")  # 抛错 / Raise


def project_to_irrep(image: np.ndarray, irrep: str) -> np.ndarray:  # 把图像投影到指定 irrep 子空间 / Project image to a given irrep subspace
    if irrep not in D4_CHARACTERS:  # 检查 / Check
        raise ValueError(f"Unknown irrep: {irrep}. Expected one of {list(D4_CHARACTERS.keys())}. / 未知 irrep。")  # 抛错 / Raise
    characters = D4_CHARACTERS[irrep]  # 特标 / Characters
    image = np.asarray(image, dtype=np.float64)  # 转浮点 / Cast
    if image.ndim != 2 or image.shape[0] != image.shape[1]:  # 必须方阵 / Must be square
        raise ValueError(f"Image must be square 2-D, got shape {image.shape}. / 输入必须是方形二维数组。")  # 抛错 / Raise
    accumulator = np.zeros_like(image)  # 累加器 / Accumulator
    for op in D4_OPERATIONS:  # 遍历群操作 / Iterate group ops
        accumulator = accumulator + float(characters[op]) * apply_d4_operation(image, op)  # 加权累加 / Weighted sum
    dim_rho = float(characters["e"])  # 特标的 χ(e) 等于 irrep 维数 / χ(e) = dim ρ
    group_order = 8.0  # |D4| = 8 / Group order
    return (dim_rho / group_order) * accumulator  # 投影算子 / Projection operator


def decompose(image: np.ndarray) -> dict[str, np.ndarray]:  # 把图像分解到 5 个 irrep / Decompose image into 5 irreps
    image = np.asarray(image, dtype=np.float64)  # 浮点 / Float
    return {irrep: project_to_irrep(image, irrep) for irrep in D4_CHARACTERS.keys()}  # 字典 / Dict


def irrep_energy_ratios(image: np.ndarray) -> dict[str, float]:  # 5 个 irrep 的能量占比 / Energy ratios across 5 irreps
    parts = decompose(image)  # 分解 / Decompose
    total_energy = float(np.sum(image.astype(np.float64) ** 2))  # 原图能量 / Original energy
    if total_energy <= 1.0e-18:  # 空图 / Empty
        return {k: 0.0 for k in parts}  # 全零 / Zeros
    ratios: dict[str, float] = {}  # 结果 / Result
    for irrep, part in parts.items():  # 遍历 / Iterate
        ratios[irrep] = float(np.sum(part ** 2)) / total_energy  # 占比 / Ratio
    return ratios  # 返回 / Return


def coupling_accessibility(image: np.ndarray, accessible_irreps: tuple[str, ...] = ("A1",)) -> float:  # 可达 irrep 能量占总能量比例 / Accessible-irrep energy fraction
    ratios = irrep_energy_ratios(image)  # 占比 / Ratios
    return float(sum(ratios[k] for k in accessible_irreps if k in ratios))  # 累加 / Sum


def reconstruct_from_irreps(parts: dict[str, np.ndarray]) -> np.ndarray:  # 从 irrep 分量重建原图（用于校验完备性） / Reconstruct original from irrep parts (sanity)
    return sum(parts.values())  # 直接求和 / Plain sum


def check_orthogonality(image: np.ndarray) -> dict[str, float]:  # 检查 5 个 irrep 分量两两正交 / Check orthogonality
    parts = decompose(image)  # 分解 / Decompose
    pairs: dict[str, float] = {}  # 内积 / Inner products
    keys = list(parts.keys())  # 名字 / Names
    for i, a in enumerate(keys):  # 遍历 / Iterate
        for b in keys[i + 1:]:  # 配对 / Pair
            pairs[f"{a}·{b}"] = float(np.sum(parts[a] * parts[b]))  # 内积 / Inner product
    return pairs  # 返回 / Return
