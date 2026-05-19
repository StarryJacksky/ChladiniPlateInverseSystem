from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

from pathlib import Path  # 导入路径工具 / Import path utilities

import numpy as np  # 导入数值计算库 / Import numerical library


def H_to_parameter_rows(H: np.ndarray) -> list[dict[str, float | str]]:  # 转换厚度矩阵为参数行 / Convert thickness matrix to parameter rows
    rows = []  # 创建行列表 / Create row list
    for row in range(H.shape[0]):  # 遍历矩阵行 / Iterate matrix rows
        for col in range(H.shape[1]):  # 遍历矩阵列 / Iterate matrix columns
            rows.append({"name": f"h_{row + 1}_{col + 1}", "value_mm": float(H[row, col])})  # 添加参数行 / Add parameter row
    return rows  # 返回参数行 / Return parameter rows


def export_parameter_csv(H: np.ndarray, path: str | Path) -> None:  # 导出 COMSOL 参数 CSV / Export COMSOL parameter CSV
    output_path = Path(path)  # 转换为路径对象 / Convert to path object
    output_path.parent.mkdir(parents=True, exist_ok=True)  # 创建父目录 / Create parent directory
    rows = H_to_parameter_rows(H)  # 生成参数行 / Build parameter rows
    with output_path.open("w", encoding="utf-8") as file_obj:  # 打开输出文件 / Open output file
        file_obj.write("name,value_mm\n")  # 写入表头 / Write header
        for item in rows:  # 遍历参数行 / Iterate parameter rows
            file_obj.write(f"{item['name']},{item['value_mm']:.3f}\n")  # 写入参数值 / Write parameter value


def export_candidate_for_comsol(candidate_dir: str | Path) -> Path:  # 导出候选 COMSOL 参数 / Export candidate COMSOL parameters
    path = Path(candidate_dir)  # 转换为路径对象 / Convert to path object
    H = np.loadtxt(path / "H.csv", delimiter=",")  # 读取厚度矩阵 / Load thickness matrix
    output_path = path / "comsol_parameters.csv"  # 设置输出路径 / Set output path
    export_parameter_csv(H, output_path)  # 导出参数表 / Export parameter table
    return output_path  # 返回输出路径 / Return output path
