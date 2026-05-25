function apply_design_variable_contract(model_path, output_path, grid_size, plate_length_mm, server_port) % 将扩展设计变量绑定到 COMSOL 模型 / Bind expanded design variables into a COMSOL model
if nargin < 5 % 检查 server 端口参数 / Check server-port argument
    server_port = 2036; % 使用默认 COMSOL server 端口 / Use default COMSOL server port
end % 结束参数检查 / End argument check
if nargin < 4 % 检查板长参数 / Check plate-length argument
    plate_length_mm = 150; % 使用默认 150 mm 板长 / Use default 150 mm plate length
end % 结束参数检查 / End argument check
if nargin < 3 % 检查网格参数 / Check grid-size argument
    grid_size = 15; % 使用默认 15x15 网格 / Use default 15x15 grid
end % 结束参数检查 / End argument check
addpath('/Applications/COMSOL64/Multiphysics/mli'); % 添加 COMSOL LiveLink 路径 / Add COMSOL LiveLink path
import com.comsol.model.* % 导入 COMSOL 模型类 / Import COMSOL model classes
import com.comsol.model.util.* % 导入 COMSOL 工具类 / Import COMSOL utility classes
try % 尝试连接 COMSOL server / Try connecting to COMSOL server
    mphstart(server_port); % 连接指定端口的 COMSOL server / Connect to COMSOL server on the requested port
catch err % 捕获连接异常 / Catch connection exception
    if ~contains(err.message, 'already') && ~contains(err.message, '已') % 判断是否不是已连接提示 / Check whether error is not already-connected notice
        rethrow(err); % 重新抛出真实连接错误 / Rethrow real connection error
    end % 结束错误判断 / End error check
end % 结束连接尝试 / End connection attempt
model = mphload(model_path); % 读取源 MPH 模型 / Load source MPH model
comp_tag = 'comp1'; % 设置组件标签 / Set component tag
material_tag = 'mat1'; % 设置材料标签 / Set material tag
variable_tag = 'var_design_contract'; % 设置变量节点标签 / Set variable-node tag
rho_expression = build_cell_expression('rhoS', grid_size, plate_length_mm); % 构建密度倍率分段表达式 / Build density-scale piecewise expression
eta_expression = build_cell_expression('etaL', grid_size, plate_length_mm); % 构建损耗因子分段表达式 / Build loss-factor piecewise expression
ensure_design_parameters(model, grid_size); % 确保全部扩展参数存在 / Ensure all expanded parameters exist
ensure_variable_node(model, comp_tag, variable_tag); % 确保变量节点存在 / Ensure variable node exists
model.component(comp_tag).variable(variable_tag).set('rho_scale_field', rho_expression); % 写入密度倍率场变量 / Write density-scale field variable
model.component(comp_tag).variable(variable_tag).descr('rho_scale_field', 'Per-cell density scale from rhoSrrcc / 单元级密度倍率'); % 写入密度变量说明 / Write density variable description
model.component(comp_tag).variable(variable_tag).set('eta_loss_field', eta_expression); % 写入损耗因子场变量 / Write loss-factor field variable
model.component(comp_tag).variable(variable_tag).descr('eta_loss_field', 'Per-cell material loss factor from etaLrrcc / 单元级材料损耗因子'); % 写入损耗变量说明 / Write loss variable description
set_material_property(model, comp_tag, material_tag, 'density', 'mat_density*rho_scale_field'); % 绑定局部密度 / Bind local density
set_material_property(model, comp_tag, material_tag, 'youngsmodulus', 'mat_youngs_modulus*(1+i*eta_loss_field)'); % 绑定带损耗的复杨氏模量 / Bind lossy complex Young modulus
set_material_property(model, comp_tag, material_tag, 'poissonsratio', 'mat_poisson_ratio'); % 保持泊松比参数绑定 / Keep Poisson-ratio parameter binding
set_material_property(model, comp_tag, material_tag, 'thermalconductivity', {'mat_thermal_conductivity','0','0','0','mat_thermal_conductivity','0','0','0','mat_thermal_conductivity'}); % 保持导热参数绑定 / Keep thermal-conductivity parameter binding
set_material_property(model, comp_tag, material_tag, 'heatcapacity', 'mat_heat_capacity'); % 保持热容参数绑定 / Keep heat-capacity parameter binding
set_material_property(model, comp_tag, material_tag, 'thermalexpansioncoefficient', {'mat_thermal_expansion','0','0','0','mat_thermal_expansion','0','0','0','mat_thermal_expansion'}); % 保持热膨胀参数绑定 / Keep thermal-expansion parameter binding
mphsave(model, output_path, 'copy', 'on'); % 保存升级后的 MPH 模型副本 / Save upgraded MPH model copy
fprintf('Saved design-variable contract model: %s\n', output_path); % 打印输出模型路径 / Print output model path
end % 结束主函数 / End main function

function ensure_design_parameters(model, grid_size) % 确保扩展变量参数存在 / Ensure expanded-variable parameters exist
for row = 1:grid_size % 遍历参数行 / Iterate parameter rows
    for col = 1:grid_size % 遍历参数列 / Iterate parameter columns
        model.param.set(sprintf('rhoS%02d%02d', row, col), '1'); % 设置默认密度倍率 / Set default density scale
        model.param.descr(sprintf('rhoS%02d%02d', row, col), sprintf('Density scale cell (%d,%d) / 密度倍率单元 (%d,%d)', row, col, row, col)); % 设置密度参数说明 / Set density parameter description
        model.param.set(sprintf('etaL%02d%02d', row, col), '0'); % 设置默认损耗因子 / Set default loss factor
        model.param.descr(sprintf('etaL%02d%02d', row, col), sprintf('Loss factor cell (%d,%d) / 损耗因子单元 (%d,%d)', row, col, row, col)); % 设置损耗参数说明 / Set loss parameter description
    end % 结束列循环 / End column loop
end % 结束行循环 / End row loop
end % 结束参数函数 / End parameter function

function ensure_variable_node(model, comp_tag, variable_tag) % 确保变量节点存在 / Ensure variable node exists
try % 尝试读取变量节点 / Try reading variable node
    model.component(comp_tag).variable(variable_tag); % 访问现有变量节点 / Access existing variable node
catch % 捕获缺失变量节点 / Catch missing variable node
    model.component(comp_tag).variable.create(variable_tag); % 创建变量节点 / Create variable node
end % 结束变量节点检查 / End variable-node check
end % 结束变量节点函数 / End variable-node function

function set_material_property(model, comp_tag, material_tag, property_name, expression) % 设置材料属性 / Set material property
try % 优先使用普通属性组 API / Prefer regular property-group API
    model.component(comp_tag).material(material_tag).propertyGroup('def').set(property_name, expression); % 写入材料属性 / Write material property
catch % 捕获旧接口差异 / Catch older API differences
    model.component(comp_tag).material(material_tag).propertyGroup('def').set(property_name, char(expression)); % 退回字符表达式写入 / Fall back to char expression write
end % 结束材料属性设置 / End material property setting
end % 结束材料函数 / End material function

function expression = build_cell_expression(prefix, grid_size, plate_length_mm) % 构建二维分段场表达式 / Build two-dimensional piecewise field expression
expression = build_x_expression(prefix, grid_size, grid_size, plate_length_mm); % 设置最后一行为兜底 / Use last row as fallback
for row = grid_size - 1:-1:1 % 从下向上包裹行条件 / Wrap row conditions from bottom to top
    row_expression = build_x_expression(prefix, row, grid_size, plate_length_mm); % 构建当前行表达式 / Build current row expression
    expression = sprintf('if(y>=%s,%s,%s)', threshold_text(y_threshold(row, grid_size, plate_length_mm)), row_expression, expression); % 包裹行条件 / Wrap row condition
end % 结束行包裹 / End row wrapping
end % 结束二维表达式函数 / End two-dimensional expression function

function expression = build_x_expression(prefix, row, grid_size, plate_length_mm) % 构建单行 x 分段表达式 / Build one-row x piecewise expression
expression = sprintf('%s%02d%02d', prefix, row, grid_size); % 设置最后一列为兜底 / Use last column as fallback
for col = grid_size - 1:-1:1 % 从右向左包裹列条件 / Wrap column conditions from right to left
    expression = sprintf('if(x<=%s,%s%02d%02d,%s)', threshold_text(x_threshold(col, grid_size, plate_length_mm)), prefix, row, col, expression); % 包裹列条件 / Wrap column condition
end % 结束列包裹 / End column wrapping
end % 结束单行表达式函数 / End one-row expression function

function value = x_threshold(col, grid_size, plate_length_mm) % 计算 x 阈值 / Compute x threshold
cell_size_m = plate_length_mm / 1000 / grid_size; % 计算单元尺寸米值 / Compute cell size in metres
half_length_m = plate_length_mm / 2000; % 计算半板长米值 / Compute half plate length in metres
value = -half_length_m + cell_size_m * col; % 返回列右边界阈值 / Return column right-boundary threshold
end % 结束 x 阈值函数 / End x-threshold function

function value = y_threshold(row, grid_size, plate_length_mm) % 计算 y 阈值 / Compute y threshold
cell_size_m = plate_length_mm / 1000 / grid_size; % 计算单元尺寸米值 / Compute cell size in metres
half_length_m = plate_length_mm / 2000; % 计算半板长米值 / Compute half plate length in metres
value = half_length_m - cell_size_m * row; % 返回行下边界阈值 / Return row lower-boundary threshold
end % 结束 y 阈值函数 / End y-threshold function

function text = threshold_text(value) % 格式化阈值文本 / Format threshold text
if abs(value) < 1e-15 % 检查近似零 / Check nearly zero
    value = 0; % 清理负零 / Clean negative zero
end % 结束近零检查 / End near-zero check
text = sprintf('%.12g', value); % 返回紧凑数值文本 / Return compact numeric text
end % 结束格式化函数 / End formatting function
