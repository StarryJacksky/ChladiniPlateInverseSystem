from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import os  # 导入环境变量工具 / Import environment-variable utilities
from pathlib import Path  # 导入路径工具 / Import path utilities

import numpy as np  # 导入数值计算库 / Import numerical library

os.environ.setdefault("MPLCONFIGDIR", str((Path("reports") / ".matplotlib").resolve()))  # 设置可写 Matplotlib 缓存目录 / Set writable Matplotlib cache directory

from src.physics.drive_reachability import drive_reachability  # 导入中心驱动可达性 / Import centre-drive reachability
from src.scoring.amplitude_valley_score import score_amplitude_valley_grid  # 导入振幅谷线评分 / Import amplitude-valley scoring
from src.subspace.free_subspace_feasibility import optimise_modal_combination  # 导入模态组合优化 / Import modal-combination optimisation


def make_line_target(size: int = 48) -> np.ndarray:  # 构造简单竖线目标 / Build simple vertical-line target
    target = np.zeros((size, size), dtype=bool)  # 创建空目标图 / Create empty target map
    target[8:-8, size // 2] = True  # 写入竖线骨架 / Draw vertical line skeleton
    return target  # 返回目标图 / Return target map


def test_modal_combination_line() -> None:  # 测试模态组合能重建已知零线 / Test modal combination reconstructs known zero line
    size = 48  # 设置图像尺寸 / Set image size
    yy, xx = np.meshgrid(np.linspace(-1.0, 1.0, size), np.linspace(-1.0, 1.0, size), indexing="ij")  # 构造坐标网格 / Build coordinate grid
    fields = np.stack([xx, yy, xx + yy], axis=0).astype(np.float32)  # 构造合成模态 / Build synthetic modes
    result = optimise_modal_combination(fields, np.asarray([100.0, 110.0, 130.0]), [1, 2, 3], make_line_target(size), steps=80, restarts=1, epsilon=0.055, seed=3)  # 运行小优化 / Run small optimisation
    assert result.metrics["dice"] > 0.05  # 确认能产生非零匹配 / Ensure nonzero match appears


def test_drive_reachability() -> None:  # 测试中心驱动参与度 / Test centre-drive participation
    fields = np.zeros((2, 32, 32), dtype=np.float32)  # 创建两个合成模态 / Create two synthetic modes
    fields[0, 14:18, 14:18] = 1.0  # 第一个模态中心强 / First mode strong at centre
    fields[1, :4, :4] = 1.0  # 第二个模态远离中心 / Second mode away from centre
    result = drive_reachability(np.asarray([1.0, 0.0]), fields, [1, 2], np.asarray([100.0, 200.0]), radius_fraction=0.12)  # 计算可达性 / Compute reachability
    assert float(result["R_drive"]) > 0.9  # 确认中心模态可达性高 / Ensure centre mode is reachable


def test_amplitude_valley_score() -> None:  # 测试低振幅谷线评分 / Test low-amplitude valley scoring
    target = make_line_target(48)  # 构造目标线 / Build target line
    amplitude = np.ones((48, 48), dtype=np.float32)  # 创建高振幅背景 / Create high-amplitude background
    amplitude[:, 22:27] = 0.01  # 目标带设低振幅 / Set low amplitude on target band
    score = score_amplitude_valley_grid(amplitude, target, epsilon=0.08)  # 计算谷线评分 / Compute valley score
    assert float(score["valley_contrast"]) > 5.0  # 确认目标谷线对比明显 / Ensure target valley contrast is clear


def main() -> None:  # 主入口 / Main entry point
    test_modal_combination_line()  # 运行模态组合烟测 / Run modal-combination smoke test
    test_drive_reachability()  # 运行驱动可达性烟测 / Run drive-reachability smoke test
    test_amplitude_valley_score()  # 运行振幅谷线烟测 / Run amplitude-valley smoke test
    print("Physical filter smoke tests passed. / 物理过滤器烟测通过。")  # 打印通过信息 / Print success message


if __name__ == "__main__":  # 检查是否直接执行 / Check direct execution
    main()  # 执行主入口 / Run main entry point
