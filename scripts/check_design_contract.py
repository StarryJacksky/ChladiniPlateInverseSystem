from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

import csv  # 导入 CSV 工具 / Import CSV utilities
from pathlib import Path  # 导入路径工具 / Import path utilities
from tempfile import TemporaryDirectory  # 导入临时目录工具 / Import temporary directory helper

import numpy as np  # 导入数值计算库 / Import numerical library

from src.comsol.design_contract import build_design_contract_summary  # 导入合同摘要构造器 / Import contract summary builder
from src.comsol.design_contract import expected_design_parameter_names  # 导入预期参数名构造器 / Import expected parameter-name builder
from src.comsol.export_parameters import export_candidate_for_comsol  # 导入候选导出函数 / Import candidate export helper
from src.config import load_config  # 导入配置读取函数 / Import config loader


def read_design_rows(path: Path) -> list[dict]:  # 读取设计变量行 / Read design-variable rows
    with path.open("r", encoding="utf-8", newline="") as file_obj:  # 打开 CSV 文件 / Open CSV file
        return list(csv.DictReader(file_obj))  # 返回字典行 / Return dictionary rows


def main() -> None:  # 主入口 / Main entry point
    config = load_config("config.yaml")  # 读取项目配置 / Load project config
    grid_size = int(config["project"]["grid_size"])  # 读取网格尺寸 / Read grid size
    summary = build_design_contract_summary(config)  # 构建合同摘要 / Build contract summary
    expected_names = expected_design_parameter_names(grid_size)  # 构造预期参数名 / Build expected parameter names
    assert summary["parameter_count"] == 2 * grid_size * grid_size  # 检查参数数量 / Check parameter count
    assert summary["first_parameter"] == "rhoS0101"  # 检查首个密度参数 / Check first density parameter
    assert summary["last_parameter"] == f"etaL{grid_size:02d}{grid_size:02d}"  # 检查最后损耗参数 / Check final loss parameter
    assert "if(y>=0.065" in summary["rho_expression"]  # 检查顶部行阈值 / Check top-row threshold
    assert "if(x<=-0.065" in summary["rho_expression"]  # 检查左侧列阈值 / Check left-column threshold
    with TemporaryDirectory(prefix="chladni_design_contract_") as temporary_dir:  # 创建临时目录 / Create temporary directory
        candidate_dir = Path(temporary_dir) / "candidate_000_0000"  # 构造临时候选目录 / Build temporary candidate directory
        candidate_dir.mkdir(parents=True, exist_ok=True)  # 创建候选目录 / Create candidate directory
        np.savetxt(candidate_dir / "H.csv", np.full((grid_size, grid_size), 2.0), delimiter=",", fmt="%.3f")  # 写入厚度矩阵 / Write thickness matrix
        np.savetxt(candidate_dir / "density_scale.csv", np.ones((grid_size, grid_size)), delimiter=",", fmt="%.4f")  # 写入密度倍率矩阵 / Write density-scale matrix
        np.savetxt(candidate_dir / "loss_factor.csv", np.zeros((grid_size, grid_size)), delimiter=",", fmt="%.5f")  # 写入损耗因子矩阵 / Write loss-factor matrix
        export_candidate_for_comsol(candidate_dir, config.get("material"))  # 导出 COMSOL 参数 / Export COMSOL parameters
        rows = read_design_rows(candidate_dir / "design_variable_parameters.csv")  # 读取导出参数 / Read exported parameters
    names = [row["name"] for row in rows]  # 提取参数名 / Extract parameter names
    assert names == expected_names  # 检查导出顺序 / Check export order
    assert rows[0]["value"] == "1" and rows[-1]["value"] == "0"  # 检查默认值 / Check default values
    print("Design variable contract checks passed. / 设计变量合同检查通过。")  # 打印成功 / Print success


if __name__ == "__main__":  # 检查直接运行 / Check direct execution
    main()  # 执行主入口 / Run main entry point
