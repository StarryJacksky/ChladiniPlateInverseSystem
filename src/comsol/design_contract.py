from __future__ import annotations  # 启用现代类型注解 / Enable modern type hints


DESIGN_VARIABLE_FIELDS = {"density_scale": ("rhoS", "1"), "loss_factor": ("etaL", "1")}  # 定义扩展变量导出前缀 / Define expanded-variable export prefixes


def cell_parameter_name(prefix: str, row: int, col: int) -> str:  # 构造单元参数名 / Build cell parameter name
    return f"{prefix}{row:02d}{col:02d}"  # 返回两位行列参数名 / Return two-digit row-column parameter name


def expected_field_parameter_names(prefix: str, grid_size: int) -> list[str]:  # 构造某个场的全部参数名 / Build all parameter names for one field
    return [cell_parameter_name(prefix, row, col) for row in range(1, grid_size + 1) for col in range(1, grid_size + 1)]  # 返回行优先参数名 / Return row-major parameter names


def expected_design_parameter_names(grid_size: int) -> list[str]:  # 构造全部扩展设计变量参数名 / Build all expanded design-variable names
    names = []  # 创建名称列表 / Create name list
    for _field_name, (prefix, _unit) in DESIGN_VARIABLE_FIELDS.items():  # 遍历扩展变量字段 / Iterate expanded-variable fields
        names.extend(expected_field_parameter_names(prefix, grid_size))  # 添加当前字段参数 / Add current field parameters
    return names  # 返回全部参数名 / Return all parameter names


def x_threshold_m(col: int, grid_size: int, plate_length_mm: float) -> float:  # 计算列右边界阈值 / Compute right-boundary threshold for a column
    cell_size_m = float(plate_length_mm) / 1000.0 / float(grid_size)  # 计算单元尺寸米值 / Compute cell size in metres
    half_length_m = float(plate_length_mm) / 2000.0  # 计算半板长米值 / Compute half plate length in metres
    return -half_length_m + cell_size_m * float(col)  # 返回 x 阈值 / Return x threshold


def y_threshold_m(row: int, grid_size: int, plate_length_mm: float) -> float:  # 计算行下边界阈值 / Compute lower-boundary threshold for a row
    cell_size_m = float(plate_length_mm) / 1000.0 / float(grid_size)  # 计算单元尺寸米值 / Compute cell size in metres
    half_length_m = float(plate_length_mm) / 2000.0  # 计算半板长米值 / Compute half plate length in metres
    return half_length_m - cell_size_m * float(row)  # 返回 y 阈值 / Return y threshold


def format_threshold(value: float) -> str:  # 格式化 COMSOL 阈值 / Format COMSOL threshold
    text = f"{value:.12g}"  # 生成紧凑浮点文本 / Build compact float text
    return "0" if text in {"-0", "-0.0"} else text  # 清理负零 / Clean negative zero


def build_x_piecewise_expression(prefix: str, row: int, grid_size: int, plate_length_mm: float) -> str:  # 构造单行 x 分段表达式 / Build one-row x piecewise expression
    expression = cell_parameter_name(prefix, row, grid_size)  # 设置最后一列为兜底 / Use last column as fallback
    for col in range(grid_size - 1, 0, -1):  # 从右向左包裹条件 / Wrap conditions from right to left
        threshold = format_threshold(x_threshold_m(col, grid_size, plate_length_mm))  # 计算当前列阈值 / Compute current column threshold
        expression = f"if(x<={threshold},{cell_parameter_name(prefix, row, col)},{expression})"  # 包裹当前列条件 / Wrap current column condition
    return expression  # 返回单行表达式 / Return row expression


def build_piecewise_cell_expression(prefix: str, grid_size: int, plate_length_mm: float) -> str:  # 构造二维单元分段表达式 / Build two-dimensional cell piecewise expression
    expression = build_x_piecewise_expression(prefix, grid_size, grid_size, plate_length_mm)  # 设置最后一行为兜底 / Use last row as fallback
    for row in range(grid_size - 1, 0, -1):  # 从下向上包裹行条件 / Wrap row conditions from bottom to top
        threshold = format_threshold(y_threshold_m(row, grid_size, plate_length_mm))  # 计算当前行阈值 / Compute current row threshold
        row_expression = build_x_piecewise_expression(prefix, row, grid_size, plate_length_mm)  # 构造当前行表达式 / Build current row expression
        expression = f"if(y>={threshold},{row_expression},{expression})"  # 包裹当前行条件 / Wrap current row condition
    return expression  # 返回二维分段表达式 / Return two-dimensional piecewise expression


def build_design_contract_summary(config: dict) -> dict:  # 构建设计变量合同摘要 / Build design-variable contract summary
    grid_size = int(config["project"]["grid_size"])  # 读取网格尺寸 / Read grid size
    plate_length_mm = float(config["project"]["plate_length_mm"])  # 读取板长 / Read plate length
    rho_expression = build_piecewise_cell_expression("rhoS", grid_size, plate_length_mm)  # 构造密度倍率表达式 / Build density-scale expression
    eta_expression = build_piecewise_cell_expression("etaL", grid_size, plate_length_mm)  # 构造损耗因子表达式 / Build loss-factor expression
    names = expected_design_parameter_names(grid_size)  # 构造预期参数名 / Build expected parameter names
    return {"grid_size": grid_size, "plate_length_mm": plate_length_mm, "parameter_count": len(names), "first_parameter": names[0], "last_parameter": names[-1], "rho_expression_length": len(rho_expression), "eta_expression_length": len(eta_expression), "rho_expression": rho_expression, "eta_expression": eta_expression}  # 返回摘要 / Return summary
