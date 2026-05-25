from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints

from pathlib import Path  # 导入路径工具 / Import path utilities

import numpy as np  # 导入数值计算库 / Import numerical library


MATERIAL_PARAMETER_SPECS = {  # 定义材料参数导出合同 / Define material parameter export contract
    "density_kg_m3": ("mat_density", "kg/m^3"),  # 密度参数 / Density parameter
    "poisson_ratio": ("mat_poisson_ratio", "1"),  # 泊松比参数 / Poisson-ratio parameter
    "youngs_modulus_pa": ("mat_youngs_modulus", "Pa"),  # 杨氏模量参数 / Young's modulus parameter
    "thermal_conductivity_w_mk": ("mat_thermal_conductivity", "W/(m*K)"),  # 导热系数参数 / Thermal-conductivity parameter
    "heat_capacity_j_kgk": ("mat_heat_capacity", "J/(kg*K)"),  # 热容参数 / Heat-capacity parameter
    "thermal_expansion_1_k": ("mat_thermal_expansion", "1/K"),  # 热膨胀参数 / Thermal-expansion parameter
}  # 结束材料参数合同 / End material parameter contract


def H_to_parameter_rows(H: np.ndarray) -> list[dict[str, float | str]]:  # 转换厚度矩阵为参数行 / Convert thickness matrix to parameter rows
    rows = []  # 创建行列表 / Create row list
    for row in range(H.shape[0]):  # 遍历矩阵行 / Iterate matrix rows
        for col in range(H.shape[1]):  # 遍历矩阵列 / Iterate matrix columns
            rows.append({"name": f"h{row + 1:02d}{col + 1:02d}", "value_mm": float(H[row, col])})  # 添加参数行 / Add parameter row
    return rows  # 返回参数行 / Return parameter rows


def field_to_parameter_rows(field: np.ndarray, prefix: str, unit: str) -> list[dict[str, float | str]]:  # 转换单元场为参数行 / Convert a per-cell field to parameter rows
    rows = []  # 创建参数行列表 / Create parameter row list
    for row in range(field.shape[0]):  # 遍历场行 / Iterate field rows
        for col in range(field.shape[1]):  # 遍历场列 / Iterate field columns
            rows.append({"name": f"{prefix}{row + 1:02d}{col + 1:02d}", "value": float(field[row, col]), "unit": unit})  # 添加场参数 / Add field parameter
    return rows  # 返回参数行 / Return parameter rows


def material_to_parameter_rows(material: dict | None) -> list[dict[str, float | str]]:  # 转换材料配置为参数行 / Convert material config to parameter rows
    source = material or {}  # 处理空材料配置 / Handle empty material config
    rows = []  # 创建材料参数行 / Create material parameter rows
    for key, (name, unit) in MATERIAL_PARAMETER_SPECS.items():  # 遍历材料合同 / Iterate material contract
        if key in source:  # 检查参数是否存在 / Check whether parameter exists
            rows.append({"name": name, "value": float(source[key]), "unit": unit})  # 添加参数行 / Add parameter row
    return rows  # 返回材料参数行 / Return material parameter rows


def load_optional_matrix(path: Path) -> np.ndarray | None:  # 读取可选矩阵 / Load optional matrix
    if not path.exists():  # 检查文件是否存在 / Check file existence
        return None  # 缺失时返回空 / Return none when missing
    return np.loadtxt(path, delimiter=",")  # 读取矩阵 / Load matrix


def export_parameter_csv(H: np.ndarray, path: str | Path) -> None:  # 导出 COMSOL 参数 CSV / Export COMSOL parameter CSV
    output_path = Path(path)  # 转换为路径对象 / Convert to path object
    output_path.parent.mkdir(parents=True, exist_ok=True)  # 创建父目录 / Create parent directory
    rows = H_to_parameter_rows(H)  # 生成参数行 / Build parameter rows
    with output_path.open("w", encoding="utf-8") as file_obj:  # 打开输出文件 / Open output file
        file_obj.write("name,value_mm\n")  # 写入表头 / Write header
        for item in rows:  # 遍历参数行 / Iterate parameter rows
            file_obj.write(f"{item['name']},{item['value_mm']:.3f}\n")  # 写入参数值 / Write parameter value


def export_material_parameter_csv(material: dict | None, path: str | Path) -> Path:  # 导出 COMSOL 材料参数 CSV / Export COMSOL material parameter CSV
    output_path = Path(path)  # 转换为路径对象 / Convert to path object
    output_path.parent.mkdir(parents=True, exist_ok=True)  # 创建父目录 / Create parent directory
    rows = material_to_parameter_rows(material)  # 生成材料参数行 / Build material parameter rows
    with output_path.open("w", encoding="utf-8") as file_obj:  # 打开输出文件 / Open output file
        file_obj.write("name,value,unit\n")  # 写入表头 / Write header
        for item in rows:  # 遍历材料参数行 / Iterate material parameter rows
            file_obj.write(f"{item['name']},{item['value']:.12g},{item['unit']}\n")  # 写入参数值和单位 / Write parameter value and unit
    return output_path  # 返回输出路径 / Return output path


def export_design_variable_parameter_csv(candidate_path: Path, path: str | Path) -> Path:  # 导出扩展设计变量参数 CSV / Export expanded design-variable parameter CSV
    output_path = Path(path)  # 转换输出路径 / Convert output path
    output_path.parent.mkdir(parents=True, exist_ok=True)  # 创建父目录 / Create parent directory
    density_scale = load_optional_matrix(candidate_path / "density_scale.csv")  # 读取密度倍率场 / Load density-scale field
    loss_factor = load_optional_matrix(candidate_path / "loss_factor.csv")  # 读取损耗因子场 / Load loss-factor field
    rows = []  # 创建参数行列表 / Create parameter row list
    if density_scale is not None:  # 检查密度倍率是否存在 / Check density-scale existence
        rows.extend(field_to_parameter_rows(density_scale, "rhoS", "1"))  # 添加密度倍率参数 / Add density-scale parameters
    if loss_factor is not None:  # 检查损耗因子是否存在 / Check loss-factor existence
        rows.extend(field_to_parameter_rows(loss_factor, "etaL", "1"))  # 添加损耗因子参数 / Add loss-factor parameters
    with output_path.open("w", encoding="utf-8") as file_obj:  # 打开输出文件 / Open output file
        file_obj.write("name,value,unit\n")  # 写入表头 / Write header
        for item in rows:  # 遍历设计变量参数 / Iterate design-variable parameters
            file_obj.write(f"{item['name']},{item['value']:.12g},{item['unit']}\n")  # 写入参数行 / Write parameter row
    return output_path  # 返回输出路径 / Return output path


def export_candidate_for_comsol(candidate_dir: str | Path, material: dict | None = None) -> Path:  # 导出候选 COMSOL 参数 / Export candidate COMSOL parameters
    path = Path(candidate_dir)  # 转换为路径对象 / Convert to path object
    H = np.loadtxt(path / "H.csv", delimiter=",")  # 读取厚度矩阵 / Load thickness matrix
    output_path = path / "comsol_parameters.csv"  # 设置输出路径 / Set output path
    export_parameter_csv(H, output_path)  # 导出参数表 / Export parameter table
    export_material_parameter_csv(material, path / "material_parameters.csv")  # 导出材料参数表 / Export material parameter table
    export_design_variable_parameter_csv(path, path / "design_variable_parameters.csv")  # 导出扩展设计变量表 / Export expanded design-variable table
    return output_path  # 返回输出路径 / Return output path
