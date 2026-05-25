from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

from datetime import datetime  # 导入时间戳工具 / Import timestamp helper
from pathlib import Path  # 导入路径工具 / Import path utilities

from src.comsol.discovery import config_with_runtime_discovery  # 导入运行时路径发现 / Import runtime path discovery
from src.comsol.run_livelink import matlab_quote  # 导入 MATLAB 字符串转义 / Import MATLAB string quoting
from src.comsol.run_livelink import run_command_streamed  # 导入流式命令运行器 / Import streamed command runner
from src.comsol.server import ensure_comsol_server  # 导入 COMSOL server 确保函数 / Import COMSOL server helper


DEFAULT_CONTRACT_SCRIPT = "comsol_templates/apply_design_variable_contract.m"  # 默认合同脚本路径 / Default contract script path


def build_contract_matlab_batch(script_path: Path, model_path: Path, output_path: Path, grid_size: int, plate_length_mm: float, server_port: int) -> str:  # 构造合同升级 batch / Build contract-upgrade batch
    script_dir = script_path.parent.resolve()  # 获取脚本目录 / Get script directory
    parts = [  # 创建 MATLAB 命令片段 / Create MATLAB command parts
        f"addpath({matlab_quote(script_dir)})",  # 添加脚本目录 / Add script directory
        f"apply_design_variable_contract({matlab_quote(model_path.resolve())},{matlab_quote(output_path.resolve())},{grid_size},{plate_length_mm},{server_port})",  # 调用合同升级函数 / Call contract-upgrade function
    ]  # 结束命令片段 / End command parts
    return "; ".join(parts)  # 拼接 batch 字符串 / Join batch string


def default_design_bound_model_path(model_path: Path) -> Path:  # 构造默认升级模型路径 / Build default upgraded-model path
    return model_path.with_name(model_path.stem.replace("_bound", "") + "_design_bound.mph")  # 返回默认输出路径 / Return default output path


def apply_design_variable_contract(config: dict, model_path: str | Path | None = None, output_path: str | Path | None = None, progress=None) -> dict:  # 应用 COMSOL 扩展变量合同 / Apply COMSOL expanded-variable contract
    runtime_config, _applied, _discovery = config_with_runtime_discovery(config)  # 应用运行时路径发现 / Apply runtime path discovery
    comsol_config = runtime_config.get("comsol", {})  # 读取 COMSOL 配置 / Read COMSOL config
    if not ensure_comsol_server(runtime_config):  # 确保 COMSOL server 可用 / Ensure COMSOL server availability
        raise RuntimeError("COMSOL server is not reachable. / COMSOL server 无法连接。")  # 抛出 server 错误 / Raise server error
    source_model = Path(model_path or comsol_config.get("model_path", "comsol_templates/Chladni_15x15_bound.mph"))  # 解析源模型 / Resolve source model
    target_model = Path(output_path) if output_path else default_design_bound_model_path(source_model)  # 解析输出模型 / Resolve output model
    script_path = Path(comsol_config.get("design_contract_runner_path", DEFAULT_CONTRACT_SCRIPT))  # 解析合同脚本 / Resolve contract script
    matlab_path = str(comsol_config.get("matlab_path", "/Applications/MATLAB_R2024a.app/bin/matlab"))  # 解析 MATLAB 路径 / Resolve MATLAB path
    grid_size = int(runtime_config["project"]["grid_size"])  # 读取网格尺寸 / Read grid size
    plate_length_mm = float(runtime_config["project"]["plate_length_mm"])  # 读取板长 / Read plate length
    server_port = int(comsol_config.get("server_port", 2036))  # 读取 server 端口 / Read server port
    batch = build_contract_matlab_batch(script_path, source_model, target_model, grid_size, plate_length_mm, server_port)  # 构造 batch 命令 / Build batch command
    command = [matlab_path, "-batch", batch]  # 构造 MATLAB 命令 / Build MATLAB command
    log_dir = Path(runtime_config["paths"]["comsol_exports_dir"])  # 读取日志目录 / Read log directory
    log_path = log_dir / "design_contract_upgrade.log"  # 构造日志路径 / Build log path
    timeout_s = float(comsol_config.get("livelink_timeout_s", 7200))  # 读取超时 / Read timeout
    returncode, _output = run_command_streamed(command, log_path, progress, {"stage": "design-contract"}, timeout_s)  # 运行合同升级 / Run contract upgrade
    if returncode != 0:  # 检查返回码 / Check return code
        raise RuntimeError(f"Design contract upgrade failed. See {log_path}. / 设计变量合同升级失败，见 {log_path}。")  # 抛出失败 / Raise failure
    return {"source_model": str(source_model), "output_model": str(target_model), "log_path": str(log_path), "returncode": returncode, "finished_at": datetime.now().isoformat(timespec="seconds")}  # 返回运行结果 / Return run result
