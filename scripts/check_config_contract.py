from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

from copy import deepcopy  # 导入深拷贝工具 / Import deepcopy helper

from src.config import load_config  # 导入配置加载函数 / Import config loader
from src.comsol.diagnostics import check_config_contract  # 导入配置合同检查 / Import config contract checks
from src.comsol.diagnostics import infer_comsol_version  # 导入 COMSOL 版本推断 / Import COMSOL version inference
from src.comsol.diagnostics import infer_matlab_version  # 导入 MATLAB 版本推断 / Import MATLAB version inference


def status_by_label(checks: list[dict]) -> dict[str, str]:  # 按标签索引状态 / Index statuses by label
    return {item["label"]: item["status"] for item in checks}  # 返回标签状态字典 / Return label-status dictionary


def test_version_inference() -> None:  # 测试路径版本推断 / Test path version inference
    comsol_paths = ["/Applications/COMSOL64/Multiphysics/bin/comsol", "/usr/local/comsol64/multiphysics/bin/comsol", "C:/Program Files/COMSOL/COMSOL64/Multiphysics/bin/win64/comsol.exe"]  # 定义 COMSOL 路径样例 / Define COMSOL path samples
    matlab_paths = ["/Applications/MATLAB_R2024a.app/bin/matlab", "/usr/local/MATLAB/R2024a/bin/matlab", "C:/Program Files/MATLAB/R2024a/bin/matlab.exe"]  # 定义 MATLAB 路径样例 / Define MATLAB path samples
    for path in comsol_paths:  # 遍历 COMSOL 样例 / Iterate COMSOL samples
        assert infer_comsol_version(path)["status"] == "ok"  # 确认 COMSOL 可识别 / Confirm COMSOL is recognized
    for path in matlab_paths:  # 遍历 MATLAB 样例 / Iterate MATLAB samples
        assert infer_matlab_version(path)["status"] == "ok"  # 确认 MATLAB 可识别 / Confirm MATLAB is recognized


def main() -> None:  # 主入口 / Main entry point
    config = load_config("config.yaml")  # 读取当前配置 / Load current config
    checks = check_config_contract(config)  # 运行当前配置合同检查 / Run current config contract checks
    required_failures = [item for item in checks if item.get("required", True) and item.get("status") != "ok"]  # 收集必需失败项 / Collect required failures
    if required_failures:  # 检查当前配置是否失败 / Check whether current config failed
        raise AssertionError(required_failures)  # 抛出失败项 / Raise failed items
    broken = deepcopy(config)  # 复制配置用于坏例子 / Copy config for bad sample
    broken["project"]["grid_size"] = 14  # 设置错误网格 / Set invalid grid
    broken["simulation"]["frequency_max_hz"] = -1  # 设置错误频率 / Set invalid frequency
    broken["material"]["poisson_ratio"] = 0.75  # 设置错误泊松比 / Set invalid Poisson ratio
    statuses = status_by_label(check_config_contract(broken))  # 运行坏配置检查 / Run bad config checks
    assert statuses["Project grid contract"] == "fail"  # 确认网格失败 / Confirm grid failure
    assert statuses["Simulation frequency range"] == "fail"  # 确认频率失败 / Confirm frequency failure
    assert statuses["Material poisson_ratio"] == "fail"  # 确认材料失败 / Confirm material failure
    test_version_inference()  # 运行版本推断样例 / Run version inference samples
    print("Config contract checks passed. / 配置合同检查通过。")  # 打印通过信息 / Print success message


if __name__ == "__main__":  # 检查直接运行 / Check direct execution
    main()  # 执行主入口 / Run main entry point
