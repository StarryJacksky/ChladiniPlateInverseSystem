from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import csv  # 导入 CSV 检查工具 / Import CSV checking utilities
import os  # 导入系统权限检查 / Import OS permission checks
import re  # 导入版本解析工具 / Import version parsing tools
import tempfile  # 导入临时目录工具 / Import temporary directory utilities
from pathlib import Path  # 导入路径工具 / Import path utilities

import numpy as np  # 导入数值计算库 / Import numerical library

from src.comsol.discovery import discover_runtime_environment  # 导入运行环境发现 / Import runtime environment discovery
from src.comsol.discovery import config_with_runtime_discovery  # 导入运行时配置补全 / Import runtime config completion
from src.comsol.design_contract import expected_design_parameter_names  # 导入扩展设计参数名 / Import expanded design parameter names
from src.comsol.export_parameters import export_candidate_for_comsol  # 导入参数导出函数 / Import parameter export helper
from src.comsol.run_livelink import build_forced_matlab_batch  # 导入强迫响应 batch 构造函数 / Import forced-response batch builder
from src.comsol.run_livelink import build_matlab_batch  # 导入 MATLAB batch 构造函数 / Import MATLAB batch builder
from src.comsol.server import is_server_reachable  # 导入 server 端口检查 / Import server port check


MATERIAL_RANGES = {  # 定义材料参数合理范围 / Define reasonable material parameter ranges
    "density_kg_m3": (100.0, 25000.0),  # 密度范围 / Density range
    "poisson_ratio": (0.0, 0.49),  # 泊松比范围 / Poisson-ratio range
    "youngs_modulus_pa": (1.0e6, 5.0e12),  # 杨氏模量范围 / Young's modulus range
    "thermal_conductivity_w_mk": (1.0e-4, 5000.0),  # 导热范围 / Thermal-conductivity range
    "heat_capacity_j_kgk": (1.0, 10000.0),  # 热容范围 / Heat-capacity range
    "thermal_expansion_1_k": (0.0, 1.0e-3),  # 热膨胀范围 / Thermal-expansion range
}  # 结束材料范围 / End material ranges


def resolve_project_path(value: str | Path) -> Path:  # 解析项目相对路径 / Resolve project-relative path
    path = Path(value).expanduser()  # 展开用户目录 / Expand user directory
    return path if path.is_absolute() else Path.cwd() / path  # 返回绝对路径 / Return absolute path


def check_path(label: str, value: str | Path, required: bool = True, executable: bool = False) -> dict:  # 检查文件或目录路径 / Check a file or directory path
    path = resolve_project_path(value)  # 解析路径 / Resolve path
    exists = path.exists()  # 检查是否存在 / Check existence
    is_executable = os.access(path, os.X_OK) if exists else False  # 检查是否可执行 / Check executable permission
    ok = exists and (is_executable if executable else True)  # 计算检查结果 / Compute check result
    if not required and not exists:  # 检查可选路径缺失 / Check missing optional path
        status = "warn"  # 标记警告 / Mark warning
    elif ok:  # 检查通过 / Check passed
        status = "ok"  # 标记正常 / Mark ok
    else:  # 检查失败 / Check failed
        status = "fail" if required else "warn"  # 标记失败或警告 / Mark fail or warning
    message = "OK" if ok else ("Missing optional path" if not required and not exists else "Path check failed")  # 生成消息 / Build message
    return {"label": label, "path": str(path), "required": required, "exists": exists, "executable": is_executable, "status": status, "message": message}  # 返回检查详情 / Return check detail


def check_output_directory(label: str, value: str | Path) -> dict:  # 检查输出目录 / Check output directory
    path = resolve_project_path(value)  # 解析路径 / Resolve path
    path.mkdir(parents=True, exist_ok=True)  # 确保目录存在 / Ensure directory exists
    writable = os.access(path, os.W_OK)  # 检查是否可写 / Check writable permission
    status = "ok" if writable else "fail"  # 计算状态 / Compute status
    message = "OK" if writable else "Directory is not writable"  # 生成消息 / Build message
    return {"label": label, "path": str(path), "required": True, "exists": path.exists(), "writable": writable, "status": status, "message": message}  # 返回检查详情 / Return check detail


def self_test_item(label: str, ok: bool, message: str, path: str = "", required: bool = True) -> dict:  # 构造自检条目 / Build self-test item
    status = "ok" if ok else ("fail" if required else "warn")  # 计算条目状态 / Compute item status
    return {"label": label, "status": status, "message": message, "path": path, "required": required}  # 返回自检条目 / Return self-test item


def section_value(config: dict, section: str, key: str, default=None):  # 读取配置分区值 / Read config section value
    return config.get(section, {}).get(key, default)  # 返回分区键值 / Return section key value


def coerce_float(value, default: float = 0.0) -> float:  # 容错转换浮点数 / Convert to float tolerantly
    try:  # 捕获转换错误 / Catch conversion errors
        return float(value)  # 返回浮点数 / Return float value
    except (TypeError, ValueError):  # 处理无效数值 / Handle invalid value
        return default  # 返回默认值 / Return default value


def coerce_float_list(values) -> list[float]:  # 容错转换浮点列表 / Convert to float list tolerantly
    if not isinstance(values, list):  # 检查是否不是列表 / Check non-list value
        return []  # 返回空列表 / Return empty list
    output = []  # 创建输出列表 / Create output list
    for value in values:  # 遍历输入值 / Iterate input values
        try:  # 捕获单项转换错误 / Catch item conversion error
            output.append(float(value))  # 添加浮点值 / Add float value
        except (TypeError, ValueError):  # 跳过无效项 / Skip invalid item
            return []  # 返回空列表表示失败 / Return empty list as failure
    return output  # 返回转换结果 / Return converted result


def check_number_config(label: str, value, minimum: float, maximum: float, integer: bool = False, required: bool = True) -> dict:  # 检查数值配置 / Check numeric config
    try:  # 捕获转换错误 / Catch conversion errors
        number = float(value)  # 转换为浮点数 / Convert to float
    except (TypeError, ValueError):  # 处理非数值 / Handle non-numeric value
        return self_test_item(label, False, f"Value is not numeric: {value}. / 数值配置不是数字：{value}。", "", required)  # 返回失败 / Return failure
    integer_ok = (not integer) or number.is_integer()  # 检查整数要求 / Check integer requirement
    range_ok = minimum <= number <= maximum  # 检查范围 / Check range
    ok = integer_ok and range_ok  # 汇总结果 / Combine result
    message = f"value={number:g}, allowed={minimum:g}..{maximum:g}. / 当前值={number:g}，允许范围={minimum:g}..{maximum:g}。"  # 构造消息 / Build message
    if integer and not integer_ok:  # 检查整数失败 / Check integer failure
        message = f"value={number:g} must be an integer. / 当前值={number:g} 必须是整数。"  # 构造整数错误 / Build integer error
    return self_test_item(label, ok, message, "", required)  # 返回检查结果 / Return check result


def check_project_contract(config: dict) -> list[dict]:  # 检查项目几何合同 / Check project geometry contract
    grid_size = int(coerce_float(section_value(config, "project", "grid_size", 0)))  # 读取网格尺寸 / Read grid size
    plate_length = coerce_float(section_value(config, "project", "plate_length_mm", 0.0))  # 读取板长 / Read plate length
    plate_width = coerce_float(section_value(config, "project", "plate_width_mm", 0.0))  # 读取板宽 / Read plate width
    center_radius = coerce_float(section_value(config, "project", "center_clamp_radius_mm", 0.0))  # 读取中心夹持半径 / Read centre clamp radius
    grid_ok = grid_size == 15 and grid_size % 2 == 1  # 检查项目网格合同 / Check project grid contract
    plate_ok = plate_length == 150.0 and plate_width == 150.0  # 检查板尺寸合同 / Check plate size contract
    center_ok = 0.0 < center_radius < min(plate_length, plate_width) / 2.0  # 检查中心半径 / Check centre radius
    return [  # 返回项目检查 / Return project checks
        self_test_item("Project grid contract", grid_ok, f"grid_size={grid_size}; expected odd 15 for current bound model. / grid_size={grid_size}；当前绑定模型要求奇数 15。"),  # 添加网格检查 / Add grid check
        self_test_item("Plate size contract", plate_ok, f"plate={plate_length:g}x{plate_width:g} mm; expected 150x150 mm. / 板尺寸={plate_length:g}x{plate_width:g} mm；期望 150x150 mm。"),  # 添加板尺寸检查 / Add plate size check
        self_test_item("Center clamp radius", center_ok, f"center_clamp_radius_mm={center_radius:g}. / 中心夹持半径={center_radius:g}。"),  # 添加中心半径检查 / Add centre radius check
    ]  # 结束项目检查 / End project checks


def check_thickness_contract(config: dict) -> list[dict]:  # 检查厚度合同 / Check thickness contract
    levels_raw = section_value(config, "thickness", "levels_mm", [])  # 读取厚度等级 / Read thickness levels
    levels = coerce_float_list(levels_raw)  # 转换厚度等级 / Convert thickness levels
    default = coerce_float(section_value(config, "thickness", "default_mm", 0.0))  # 读取默认厚度 / Read default thickness
    neighbor = coerce_float(section_value(config, "thickness", "max_neighbor_difference_mm", 0.0))  # 读取邻居差值 / Read neighbour difference
    levels_ok = bool(levels) and levels == sorted(levels) and all(0.05 <= value <= 20.0 for value in levels)  # 检查厚度等级 / Check thickness levels
    default_ok = default in levels  # 检查默认厚度 / Check default thickness
    neighbor_ok = neighbor >= 0.0 and neighbor <= max(levels or [0.0])  # 检查邻居差值 / Check neighbour difference
    return [  # 返回厚度检查 / Return thickness checks
        self_test_item("Thickness levels", levels_ok, f"{len(levels)} level(s), range={min(levels or [0]):g}..{max(levels or [0]):g} mm. / {len(levels)} 个厚度等级，范围={min(levels or [0]):g}..{max(levels or [0]):g} mm。"),  # 添加厚度等级检查 / Add thickness level check
        self_test_item("Default thickness", default_ok, f"default_mm={default:g}; must be one of levels_mm. / default_mm={default:g}；必须属于 levels_mm。"),  # 添加默认厚度检查 / Add default thickness check
        self_test_item("Neighbour thickness limit", neighbor_ok, f"max_neighbor_difference_mm={neighbor:g}. / 相邻厚度限制={neighbor:g}。"),  # 添加邻居限制检查 / Add neighbour limit check
    ]  # 结束厚度检查 / End thickness checks


def check_material_contract(config: dict) -> list[dict]:  # 检查材料合同 / Check material contract
    material = config.get("material", {})  # 读取材料配置 / Read material config
    return [check_number_config(f"Material {key}", material.get(key), minimum, maximum) for key, (minimum, maximum) in MATERIAL_RANGES.items()]  # 返回材料检查 / Return material checks


def check_simulation_contract(config: dict) -> list[dict]:  # 检查仿真合同 / Check simulation contract
    minimum_frequency = coerce_float(section_value(config, "simulation", "frequency_min_hz", 0.0))  # 读取最小频率 / Read minimum frequency
    maximum_frequency = coerce_float(section_value(config, "simulation", "frequency_max_hz", 0.0))  # 读取最大频率 / Read maximum frequency
    frequency_ok = 0.0 <= minimum_frequency <= maximum_frequency <= 100000.0  # 检查频率范围 / Check frequency range
    return [  # 返回仿真检查 / Return simulation checks
        check_number_config("Simulation mode count", section_value(config, "simulation", "num_modes", 0), 1.0, 200.0, True),  # 添加模态数量检查 / Add mode count check
        self_test_item("Simulation frequency range", frequency_ok, f"{minimum_frequency:g}..{maximum_frequency:g} Hz. / 频率范围={minimum_frequency:g}..{maximum_frequency:g} Hz。"),  # 添加频率范围检查 / Add frequency range check
    ]  # 结束仿真检查 / End simulation checks


def check_optimisation_contract(config: dict) -> list[dict]:  # 检查优化合同 / Check optimisation contract
    optimisation = config.get("optimisation", {})  # 读取优化配置 / Read optimisation config
    return [  # 返回优化检查 / Return optimisation checks
        check_number_config("Optimisation population size", optimisation.get("population_size"), 1.0, 1000.0, True),  # 添加候选数量检查 / Add population size check
        check_number_config("Optimisation iteration count", optimisation.get("num_iterations"), 1.0, 1000.0, True),  # 添加迭代数量检查 / Add iteration count check
        check_number_config("Roughness weight", optimisation.get("roughness_weight"), 0.0, 10.0),  # 添加粗糙度权重检查 / Add roughness weight check
        check_number_config("Mass weight", optimisation.get("mass_weight"), 0.0, 10.0),  # 添加质量权重检查 / Add mass weight check
        check_number_config("Frequency weight", optimisation.get("frequency_weight"), 0.0, 10.0),  # 添加频率权重检查 / Add frequency weight check
    ]  # 结束优化检查 / End optimisation checks


def check_runtime_config_contract(config: dict) -> list[dict]:  # 检查运行时配置合同 / Check runtime config contract
    comsol_config = config.get("comsol", {})  # 读取 COMSOL 配置 / Read COMSOL config
    paths_config = config.get("paths", {})  # 读取路径配置 / Read paths config
    target_mode = str(section_value(config, "nodal_extraction", "target_mode", ""))  # 读取目标模式 / Read target mode
    target_mode_ok = target_mode in {"chladni", "stroke", "edge", "filled"}  # 检查目标模式 / Check target mode
    path_keys_ok = all(paths_config.get(key) for key in ["target_pattern", "processed_targets_dir", "candidates_dir", "comsol_exports_dir"])  # 检查路径键 / Check path keys
    return [  # 返回运行时检查 / Return runtime checks
        self_test_item("Target mode contract", target_mode_ok, f"target_mode={target_mode}. / 目标模式={target_mode}。"),  # 添加目标模式检查 / Add target mode check
        self_test_item("Required path keys", path_keys_ok, "Target, processed, candidate, and export paths are configured. / 目标、处理、候选和导出路径已配置。"),  # 添加路径键检查 / Add path key check
        check_number_config("COMSOL server port", comsol_config.get("server_port", 0), 1.0, 65535.0, True),  # 添加端口检查 / Add port check
    ]  # 结束运行时检查 / End runtime checks


def check_config_contract(config: dict) -> list[dict]:  # 检查完整配置合同 / Check complete config contract
    checks = []  # 创建检查列表 / Create check list
    checks.extend(check_project_contract(config))  # 添加项目检查 / Add project checks
    checks.extend(check_thickness_contract(config))  # 添加厚度检查 / Add thickness checks
    checks.extend(check_material_contract(config))  # 添加材料检查 / Add material checks
    checks.extend(check_simulation_contract(config))  # 添加仿真检查 / Add simulation checks
    checks.extend(check_optimisation_contract(config))  # 添加优化检查 / Add optimisation checks
    checks.extend(check_runtime_config_contract(config))  # 添加运行时检查 / Add runtime checks
    return checks  # 返回所有配置检查 / Return all config checks


def check_runner_contract(runner_path: Path) -> dict:  # 检查 LiveLink runner 合同 / Check LiveLink runner contract
    if not runner_path.exists():  # 检查 runner 是否存在 / Check whether runner exists
        return self_test_item("LiveLink runner contract", False, "Runner file is missing. / runner 文件不存在。", str(runner_path))  # 返回缺失结果 / Return missing result
    text = runner_path.read_text(encoding="utf-8", errors="ignore")  # 读取 runner 文本 / Read runner text
    required_tokens = ["function run_chladni_candidate", "mphload", "model.param.set", "frequencies.csv", "mode_%02d.csv"]  # 定义关键合同片段 / Define key contract tokens
    missing = [token for token in required_tokens if token not in text]  # 查找缺失片段 / Find missing tokens
    ok = not missing  # 判断是否通过 / Decide whether passed
    message = "Runner contract looks complete. / runner 合同看起来完整。" if ok else f"Missing tokens: {', '.join(missing)}"  # 生成检查消息 / Build check message
    return self_test_item("LiveLink runner contract", ok, message, str(runner_path))  # 返回检查结果 / Return check result


def check_forced_runner_contract(runner_path: Path) -> dict:  # 检查强迫响应 runner 合同 / Check forced-response runner contract
    if not runner_path.exists():  # 检查 runner 是否存在 / Check whether runner exists
        return self_test_item("Forced-response runner contract", False, "Forced-response runner file is missing. / 强迫响应 runner 文件不存在。", str(runner_path))  # 返回缺失结果 / Return missing result
    text = runner_path.read_text(encoding="utf-8", errors="ignore")  # 读取 runner 文本 / Read runner text
    required_tokens = ["function run_chladni_forced_response", "frequency_parameters.csv", "actuator_parameters.csv", "forced_response.csv", "std_mosaic_forced"]  # 定义强迫响应合同片段 / Define forced-response contract tokens
    missing = [token for token in required_tokens if token not in text]  # 查找缺失片段 / Find missing tokens
    ok = not missing  # 判断是否通过 / Decide whether passed
    message = "Forced-response runner contract looks complete. / 强迫响应 runner 合同看起来完整。" if ok else f"Missing tokens: {', '.join(missing)}"  # 生成检查消息 / Build check message
    return self_test_item("Forced-response runner contract", ok, message, str(runner_path))  # 返回检查结果 / Return check result


def check_design_contract_runner(script_path: Path) -> dict:  # 检查设计变量合同脚本 / Check design-variable contract script
    if not script_path.exists():  # 检查脚本是否存在 / Check whether script exists
        return self_test_item("Design contract runner", False, "Design contract script is missing. / 设计变量合同脚本不存在。", str(script_path))  # 返回缺失结果 / Return missing result
    text = script_path.read_text(encoding="utf-8", errors="ignore")  # 读取脚本文本 / Read script text
    required_tokens = ["function apply_design_variable_contract", "rho_scale_field", "eta_loss_field", "rhoS%02d%02d", "etaL%02d%02d", "mphsave"]  # 定义关键片段 / Define key tokens
    missing = [token for token in required_tokens if token not in text]  # 查找缺失片段 / Find missing tokens
    ok = not missing  # 判断合同是否完整 / Decide whether contract is complete
    message = "Design contract script looks complete. / 设计变量合同脚本看起来完整。" if ok else f"Missing tokens: {', '.join(missing)}"  # 生成消息 / Build message
    return self_test_item("Design contract runner", ok, message, str(script_path))  # 返回检查结果 / Return check result


def check_export_directory_write(path: Path) -> dict:  # 检查导出目录写入 / Check export directory writing
    try:  # 捕获写入错误 / Catch write errors
        path.mkdir(parents=True, exist_ok=True)  # 确保目录存在 / Ensure directory exists
        probe = path / "self_test_write.tmp"  # 构造测试文件 / Build probe file
        probe.write_text("ok\n", encoding="utf-8")  # 写入测试内容 / Write probe content
        probe.unlink()  # 删除测试文件 / Remove probe file
        return self_test_item("Export directory write", True, "Write probe succeeded. / 写入探针成功。", str(path))  # 返回成功结果 / Return success result
    except OSError as exc:  # 处理系统写入错误 / Handle OS write error
        return self_test_item("Export directory write", False, str(exc), str(path))  # 返回失败结果 / Return failure result


def check_timeout_config(config: dict) -> dict:  # 检查超时配置 / Check timeout configuration
    comsol_config = config.get("comsol", {})  # 读取 COMSOL 配置 / Read COMSOL config
    server_timeout = float(comsol_config.get("server_start_timeout_s", 30.0))  # 读取 server 超时 / Read server timeout
    livelink_timeout = float(comsol_config.get("livelink_timeout_s", 7200.0))  # 读取 LiveLink 超时 / Read LiveLink timeout
    ok = server_timeout > 0 and livelink_timeout > server_timeout  # 判断超时是否合理 / Decide whether timeouts are reasonable
    message = f"server_start_timeout_s={server_timeout:g}, livelink_timeout_s={livelink_timeout:g}. / server 启动超时={server_timeout:g}，LiveLink 超时={livelink_timeout:g}。"  # 生成超时消息 / Build timeout message
    return self_test_item("Timeout configuration", ok, message)  # 返回超时检查 / Return timeout check


def infer_comsol_version(command_path: str | Path) -> dict:  # 从路径推断 COMSOL 版本 / Infer COMSOL version from path
    path_text = str(command_path).replace("\\", "/")  # 转换并归一化路径文本 / Convert and normalize path text
    match = re.search(r"(?:COMSOL|comsol)[/_ -]*(\d)(\d)(?:\b|/)", path_text, re.IGNORECASE)  # 匹配跨平台 COMSOL 目录 / Match cross-platform COMSOL folder
    version = f"{match.group(1)}.{match.group(2)}" if match else ""  # 构造版本字符串 / Build version string
    ok = bool(version)  # 判断是否识别版本 / Decide whether version was found
    message = f"Detected COMSOL {version} from path. / 从路径识别到 COMSOL {version}。" if ok else "COMSOL version was not inferred from the command path. / 未能从命令路径推断 COMSOL 版本。"  # 生成版本消息 / Build version message
    return self_test_item("COMSOL version hint", ok, message, path_text, False)  # 返回可选版本检查 / Return optional version check


def infer_matlab_version(command_path: str | Path) -> dict:  # 从路径推断 MATLAB 版本 / Infer MATLAB version from path
    path_text = str(command_path).replace("\\", "/")  # 转换并归一化路径文本 / Convert and normalize path text
    match = re.search(r"MATLAB[_/ -]*(R\d{4}[ab])", path_text, re.IGNORECASE)  # 匹配跨平台 MATLAB 目录 / Match cross-platform MATLAB folder
    version = match.group(1).upper() if match else ""  # 读取版本字符串 / Read version string
    ok = bool(version)  # 判断是否识别版本 / Decide whether version was found
    message = f"Detected MATLAB {version} from path. / 从路径识别到 MATLAB {version}。" if ok else "MATLAB version was not inferred from the command path. / 未能从命令路径推断 MATLAB 版本。"  # 生成版本消息 / Build version message
    return self_test_item("MATLAB version hint", ok, message, path_text, False)  # 返回可选版本检查 / Return optional version check


def check_license_environment() -> dict:  # 检查常见 license 环境变量 / Check common license environment variables
    keys = ["LM_LICENSE_FILE", "MLM_LICENSE_FILE", "COMSOL_LICENSE_FILE"]  # 定义常见 license 变量 / Define common license variables
    present = [key for key in keys if os.environ.get(key)]  # 查找已设置变量 / Find configured variables
    ok = bool(present)  # 判断是否有变量 / Decide whether any variable exists
    message = f"License variables set: {', '.join(present)}; still open COMSOL/MATLAB once after install to confirm login. / 已设置 license 变量：{', '.join(present)}；安装后仍建议先打开 COMSOL/MATLAB 确认登录。" if ok else "No common license environment variable detected; named-user login or local license files may still work, but open COMSOL/MATLAB once before full automation. / 未检测到常见 license 环境变量；命名用户登录或本机 license 文件仍可能可用，但完整自动化前请先打开 COMSOL/MATLAB 一次。"  # 生成 license 消息 / Build license message
    return self_test_item("License environment hint", ok, message, "", False)  # 返回可选 license 检查 / Return optional license check


def discovery_check_items(discovery: dict) -> list[dict]:  # 构造自动发现诊断条目 / Build auto-discovery diagnostic items
    summary = discovery.get("summary", {})  # 读取发现摘要 / Read discovery summary
    suggestions = discovery.get("suggestions", {})  # 读取路径建议 / Read path suggestions
    process_count = int(summary.get("process_count", 0))  # 读取进程数量 / Read process count
    process_status = str(summary.get("process_probe_status", ""))  # 读取进程探测状态 / Read process probe status
    process_error = str(summary.get("process_probe_error", ""))  # 读取进程探测错误 / Read process probe error
    comsol_count = int(summary.get("comsol_install_count", 0))  # 读取 COMSOL 候选数 / Read COMSOL candidate count
    matlab_count = int(summary.get("matlab_install_count", 0))  # 读取 MATLAB 候选数 / Read MATLAB candidate count
    process_message = f"{process_count} matching process(es) found. / 找到 {process_count} 个相关运行进程。" if process_count else ("Process list unavailable: " + process_error + " / 进程列表不可用：" + process_error if process_status == "unavailable" else "No running COMSOL/MATLAB process detected. / 未检测到正在运行的 COMSOL/MATLAB 进程。")  # 构造进程消息 / Build process message
    install_message = f"COMSOL candidates={comsol_count}, MATLAB candidates={matlab_count}. / COMSOL 候选={comsol_count}，MATLAB 候选={matlab_count}。"  # 构造安装候选消息 / Build install-candidate message
    comsol_path = str(suggestions.get("comsol_command_path", ""))  # 读取 COMSOL 建议 / Read COMSOL suggestion
    matlab_path = str(suggestions.get("matlab_path", ""))  # 读取 MATLAB 建议 / Read MATLAB suggestion
    suggestion_ok = bool(comsol_path and matlab_path)  # 判断建议是否完整 / Decide whether suggestions are complete
    suggestion_message = "Suggested COMSOL and MATLAB paths are available. / 已找到 COMSOL 与 MATLAB 路径建议。" if suggestion_ok else "Path suggestions are incomplete; manual config may still be needed. / 路径建议不完整，可能仍需手动配置。"  # 构造建议消息 / Build suggestion message
    suggestion_path = f"COMSOL={comsol_path or '-'}; MATLAB={matlab_path or '-'}"  # 构造建议路径文本 / Build suggestion path text
    return [  # 返回诊断条目 / Return diagnostic items
        self_test_item("Running process discovery", process_count > 0 and process_status != "unavailable", process_message, "", False),  # 添加运行进程发现 / Add running-process discovery
        self_test_item("Install path discovery", bool(comsol_count or matlab_count), install_message, "", False),  # 添加安装路径发现 / Add install-path discovery
        self_test_item("Runtime path suggestion", suggestion_ok, suggestion_message, suggestion_path, False),  # 添加路径建议 / Add path suggestion
    ]  # 结束诊断条目 / End diagnostic items


def check_parameter_export(config: dict) -> dict:  # 检查候选参数导出 / Check candidate parameter export
    grid_size = int(config["project"]["grid_size"])  # 读取网格尺寸 / Read grid size
    default_mm = float(config["thickness"]["default_mm"])  # 读取默认厚度 / Read default thickness
    with tempfile.TemporaryDirectory(prefix="chladni_self_test_") as temporary_dir:  # 创建临时目录 / Create temporary directory
        candidate_dir = Path(temporary_dir) / "candidate_000_0000"  # 构造临时候选目录 / Build temporary candidate directory
        candidate_dir.mkdir(parents=True, exist_ok=True)  # 创建候选目录 / Create candidate directory
        np.savetxt(candidate_dir / "H.csv", np.full((grid_size, grid_size), default_mm), delimiter=",", fmt="%.3f")  # 写入临时厚度矩阵 / Write temporary thickness matrix
        np.savetxt(candidate_dir / "density_scale.csv", np.ones((grid_size, grid_size)), delimiter=",", fmt="%.4f")  # 写入临时密度倍率 / Write temporary density scale
        np.savetxt(candidate_dir / "loss_factor.csv", np.zeros((grid_size, grid_size)), delimiter=",", fmt="%.5f")  # 写入临时损耗因子 / Write temporary loss factor
        export_candidate_for_comsol(candidate_dir, config.get("material"))  # 导出参数文件 / Export parameter files
        with (candidate_dir / "comsol_parameters.csv").open("r", encoding="utf-8", newline="") as file_obj:  # 打开厚度参数表 / Open thickness parameter table
            parameter_rows = list(csv.DictReader(file_obj))  # 读取厚度参数行 / Read thickness parameter rows
        with (candidate_dir / "material_parameters.csv").open("r", encoding="utf-8", newline="") as file_obj:  # 打开材料参数表 / Open material parameter table
            material_rows = list(csv.DictReader(file_obj))  # 读取材料参数行 / Read material parameter rows
        with (candidate_dir / "design_variable_parameters.csv").open("r", encoding="utf-8", newline="") as file_obj:  # 打开设计变量参数表 / Open design-variable parameter table
            design_rows = list(csv.DictReader(file_obj))  # 读取设计变量参数行 / Read design-variable parameter rows
    expected_count = grid_size * grid_size  # 计算预期参数数量 / Compute expected parameter count
    names_ok = parameter_rows[0]["name"] == "h0101" and parameter_rows[-1]["name"] == f"h{grid_size:02d}{grid_size:02d}" if parameter_rows else False  # 检查首尾参数名 / Check first and last parameter names
    material_ok = len(material_rows) >= 6  # 检查材料参数数量 / Check material parameter count
    design_names = [row.get("name", "") for row in design_rows]  # 读取设计变量参数名 / Read design-variable parameter names
    expected_design_names = expected_design_parameter_names(grid_size)  # 构造预期设计变量参数名 / Build expected design-variable names
    design_ok = design_names == expected_design_names  # 检查设计变量合同 / Check design-variable contract
    ok = len(parameter_rows) == expected_count and names_ok and material_ok and design_ok  # 汇总导出结果 / Combine export result
    message = f"{len(parameter_rows)}/{expected_count} thickness rows, {len(material_rows)} material rows, {len(design_rows)}/{len(expected_design_names)} design rows. / 厚度行 {len(parameter_rows)}/{expected_count}，材料行 {len(material_rows)}，设计变量行 {len(design_rows)}/{len(expected_design_names)}。"  # 生成导出消息 / Build export message
    return self_test_item("Parameter export dry run", ok, message)  # 返回检查结果 / Return check result


def check_matlab_batch(config: dict) -> dict:  # 检查 MATLAB batch 表达式 / Check MATLAB batch expression
    comsol_config = config.get("comsol", {})  # 读取 COMSOL 配置 / Read COMSOL config
    model = resolve_project_path(comsol_config.get("model_path", ""))  # 解析模型路径 / Resolve model path
    runner = resolve_project_path(comsol_config.get("runner_path", ""))  # 解析 runner 路径 / Resolve runner path
    batch = build_matlab_batch(model, Path("candidate_000_0000"), Path("data/comsol_exports/candidate_000_0000"), runner, 1)  # 构造测试 batch / Build test batch
    ok = "run_chladni_candidate" in batch and str(model.resolve()) in batch  # 检查表达式关键内容 / Check expression key content
    message = "MATLAB batch expression can be built. / MATLAB batch 表达式可构造。" if ok else "MATLAB batch expression is incomplete. / MATLAB batch 表达式不完整。"  # 生成检查消息 / Build check message
    return self_test_item("MATLAB batch dry run", ok, message)  # 返回检查结果 / Return check result


def check_forced_matlab_batch(config: dict) -> dict:  # 检查强迫响应 MATLAB batch 表达式 / Check forced-response MATLAB batch expression
    comsol_config = config.get("comsol", {})  # 读取 COMSOL 配置 / Read COMSOL config
    model = resolve_project_path(comsol_config.get("model_path", ""))  # 解析模型路径 / Resolve model path
    runner = resolve_project_path(comsol_config.get("forced_response_runner_path", "comsol_templates/run_chladni_forced_response.m"))  # 解析强迫响应 runner 路径 / Resolve forced-response runner path
    batch = build_forced_matlab_batch(model, Path("candidate_000_0000"), Path("data/comsol_exports/candidate_000_0000/forced_response"), runner)  # 构造测试 batch / Build test batch
    ok = "run_chladni_forced_response" in batch and str(model.resolve()) in batch  # 检查表达式关键内容 / Check expression key content
    message = "Forced-response MATLAB batch expression can be built. / 强迫响应 MATLAB batch 表达式可构造。" if ok else "Forced-response MATLAB batch expression is incomplete. / 强迫响应 MATLAB batch 表达式不完整。"  # 生成检查消息 / Build check message
    return self_test_item("Forced-response MATLAB batch dry run", ok, message)  # 返回检查结果 / Return check result


def run_deployment_self_test(config: dict) -> dict:  # 运行部署自检 / Run deployment self-test
    diagnostics = diagnose_comsol_environment(config)  # 运行基础诊断 / Run base diagnostics
    comsol_config = config.get("comsol", {})  # 读取 COMSOL 配置 / Read COMSOL config
    paths_config = config.get("paths", {})  # 读取路径配置 / Read path config
    runner_path = resolve_project_path(comsol_config.get("runner_path", ""))  # 解析 runner 路径 / Resolve runner path
    forced_runner_path = resolve_project_path(comsol_config.get("forced_response_runner_path", "comsol_templates/run_chladni_forced_response.m"))  # 解析强迫响应 runner 路径 / Resolve forced-response runner path
    design_runner_path = resolve_project_path(comsol_config.get("design_contract_runner_path", ""))  # 解析设计合同脚本路径 / Resolve design-contract script path
    export_dir = resolve_project_path(paths_config.get("comsol_exports_dir", "data/comsol_exports"))  # 解析导出目录 / Resolve export directory
    grid_size = int(config["project"]["grid_size"])  # 读取网格尺寸 / Read grid size
    checks = [  # 创建自检列表 / Create self-test list
        self_test_item("Diagnostics readiness", bool(diagnostics["ready_for_auto_run"]), "Base diagnostics are ready. / 基础诊断已就绪。" if diagnostics["ready_for_auto_run"] else "Base diagnostics are not ready. / 基础诊断尚未就绪。"),  # 添加基础诊断结果 / Add base diagnostics result
        self_test_item("Grid calibration", grid_size == 15 and grid_size % 2 == 1, f"grid_size={grid_size}. / 网格尺寸={grid_size}。"),  # 添加网格校准检查 / Add grid calibration check
        check_runner_contract(runner_path),  # 添加 runner 合同检查 / Add runner contract check
        check_forced_runner_contract(forced_runner_path),  # 添加强迫响应 runner 合同检查 / Add forced-response runner contract check
        check_design_contract_runner(design_runner_path),  # 添加设计变量合同脚本检查 / Add design-variable contract script check
        check_export_directory_write(export_dir),  # 添加导出目录写入检查 / Add export directory write check
        check_timeout_config(config),  # 添加超时配置检查 / Add timeout configuration check
        check_parameter_export(config),  # 添加参数导出检查 / Add parameter export check
        check_matlab_batch(config),  # 添加 MATLAB batch 检查 / Add MATLAB batch check
        check_forced_matlab_batch(config),  # 添加强迫响应 MATLAB batch 检查 / Add forced-response MATLAB batch check
    ]  # 结束自检列表 / End self-test list
    ready = all(item["status"] == "ok" for item in checks if item.get("required", True))  # 计算自检是否通过 / Compute self-test readiness
    return {"ready": ready, "checks": checks, "diagnostics": diagnostics}  # 返回自检结果 / Return self-test result


def diagnose_comsol_environment(config: dict) -> dict:  # 诊断 COMSOL/MATLAB 环境 / Diagnose COMSOL/MATLAB environment
    discovery = discover_runtime_environment()  # 发现运行进程和安装路径 / Discover running processes and install paths
    runtime_config, applied_paths, discovery = config_with_runtime_discovery(config, discovery)  # 应用运行时发现结果 / Apply runtime discovery result
    comsol_config = runtime_config.get("comsol", {})  # 读取 COMSOL 配置 / Read COMSOL config
    paths_config = runtime_config.get("paths", {})  # 读取路径配置 / Read paths config
    checks = check_config_contract(runtime_config)  # 先运行配置合同检查 / Run config contract checks first
    checks.extend([  # 追加路径检查列表 / Append path check list
        check_path("COMSOL command", comsol_config.get("comsol_command_path", ""), True, True),  # 检查 COMSOL 命令 / Check COMSOL command
        infer_comsol_version(comsol_config.get("comsol_command_path", "")),  # 添加 COMSOL 版本提示 / Add COMSOL version hint
        check_path("MATLAB command", comsol_config.get("matlab_path", ""), True, True),  # 检查 MATLAB 命令 / Check MATLAB command
        infer_matlab_version(comsol_config.get("matlab_path", "")),  # 添加 MATLAB 版本提示 / Add MATLAB version hint
        check_license_environment(),  # 添加 license 环境提示 / Add license environment hint
        check_path("Bound MPH model", comsol_config.get("model_path", ""), True, False),  # 检查绑定模型 / Check bound model
        check_path("LiveLink runner", comsol_config.get("runner_path", ""), True, False),  # 检查 LiveLink 脚本 / Check LiveLink runner
        check_path("Forced-response runner", comsol_config.get("forced_response_runner_path", "comsol_templates/run_chladni_forced_response.m"), True, False),  # 检查强迫响应脚本 / Check forced-response runner
        check_path("Design contract runner", comsol_config.get("design_contract_runner_path", ""), True, False),  # 检查设计合同脚本 / Check design contract runner
        check_path("Source MPH model", comsol_config.get("source_model_path", ""), False, False),  # 检查原始模型 / Check source model
        check_output_directory("COMSOL exports", paths_config.get("comsol_exports_dir", "data/comsol_exports")),  # 检查导出目录 / Check export directory
        check_timeout_config(config),  # 检查超时配置 / Check timeout configuration
    ])  # 结束路径检查列表 / End path check list
    checks.extend(discovery_check_items(discovery))  # 加入自动发现提示 / Add auto-discovery hints
    if applied_paths:  # 检查是否应用运行时补全 / Check whether runtime completion was applied
        applied_text = ", ".join(f"{key} from {source}" for key, source in applied_paths.items())  # 构造应用说明 / Build applied-path description
        checks.append(self_test_item("Runtime path auto-fill", True, f"Applied {applied_text}. / 已应用 {applied_text}。", "", False))  # 添加补全提示 / Add completion hint
    host = str(comsol_config.get("server_host", "127.0.0.1"))  # 读取 server 主机 / Read server host
    port = int(comsol_config.get("server_port", 2036))  # 读取 server 端口 / Read server port
    auto_start = bool(comsol_config.get("auto_start_server", True))  # 读取自动启动设置 / Read auto-start setting
    reachable = is_server_reachable(host, port)  # 检查 server 端口 / Check server port
    server_status = "ok" if reachable else ("warn" if auto_start else "fail")  # 计算 server 状态 / Compute server status
    server_message = "mphserver is already listening" if reachable else ("Will be started automatically when needed" if auto_start else "mphserver is not reachable and auto-start is disabled")  # 生成 server 消息 / Build server message
    server = {"host": host, "port": port, "auto_start": auto_start, "reachable": reachable, "status": server_status, "message": server_message}  # 构造 server 详情 / Build server detail
    required_ok = all(item["status"] == "ok" for item in checks if item.get("required"))  # 检查必需项 / Check required items
    ready_for_auto_run = required_ok and (reachable or auto_start)  # 判断是否可自动运行 / Decide automatic-run readiness
    return {"ready_for_auto_run": ready_for_auto_run, "checks": checks, "server": server, "discovery": discovery, "applied_runtime_paths": applied_paths}  # 返回诊断结果 / Return diagnostics
