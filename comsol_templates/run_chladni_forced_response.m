function run_chladni_forced_response(model_path, candidate_dir, export_dir) % 运行 MOSAIC-Z 强迫响应验证 / Run MOSAIC-Z forced-response validation
%RUN_CHLADNI_FORCED_RESPONSE Run one candidate through COMSOL frequency-domain validation. / 通过 COMSOL 频域验证运行一个候选。

comsol_mli_path = getenv('COMSOL_MLI_PATH'); % 读取 COMSOL MATLAB 接口路径 / Read COMSOL MATLAB-interface path
if ~isempty(comsol_mli_path) && exist(comsol_mli_path, 'dir') % 检查环境变量路径是否可用 / Check whether environment path is available
    addpath(comsol_mli_path); % 添加 COMSOL MATLAB 接口路径 / Add COMSOL MATLAB-interface path
elseif exist('/Applications/COMSOL64/Multiphysics/mli', 'dir') % 检查 macOS 默认路径 / Check macOS default path
    addpath('/Applications/COMSOL64/Multiphysics/mli'); % 添加 macOS 默认接口路径 / Add macOS default interface path
elseif exist('/usr/local/comsol64/multiphysics/mli', 'dir') % 检查 Linux 常见路径 / Check common Linux path
    addpath('/usr/local/comsol64/multiphysics/mli'); % 添加 Linux 接口路径 / Add Linux interface path
elseif exist('/opt/comsol64/multiphysics/mli', 'dir') % 检查 Linux 可选路径 / Check optional Linux path
    addpath('/opt/comsol64/multiphysics/mli'); % 添加可选 Linux 接口路径 / Add optional Linux interface path
end % 结束接口路径配置 / End interface path setup

import com.comsol.model.* % 导入 COMSOL 模型 API / Import COMSOL model API
import com.comsol.model.util.* % 导入 COMSOL 工具 API / Import COMSOL utility API

try % 尝试连接 COMSOL server / Try connecting to COMSOL server
    server_user = getenv('COMSOL_SERVER_USER'); % 读取 server 用户名 / Read server username
    server_password = getenv('COMSOL_SERVER_PASSWORD'); % 读取 server 密码 / Read server password
    server_host = getenv('COMSOL_SERVER_HOST'); % 读取 server 主机 / Read server host
    if isempty(server_host) % 检查主机是否缺失 / Check whether host is missing
        server_host = '127.0.0.1'; % 使用本机默认主机 / Use localhost default
    end % 结束主机默认值 / End host default
    server_port = str2double(getenv('COMSOL_SERVER_PORT')); % 读取 server 端口 / Read server port
    if isnan(server_port) || server_port <= 0 % 检查端口是否有效 / Check whether port is valid
        server_port = 2036; % 使用默认端口 / Use default port
    end % 结束端口默认值 / End port default
    if ~isempty(server_user) % 检查是否有用户名 / Check whether username exists
        mphstart(char(server_host), server_port, server_user, server_password); % 带凭据连接 server / Connect to server with credentials
    else % 处理无用户名情况 / Handle missing username
        mphstart(server_port); % 使用本机端口连接 / Connect by local port
    end % 结束连接分支 / End connection branch
catch err % 捕获连接异常 / Catch connection exception
    if ~contains(err.message, 'already') && ~contains(err.message, '已') % 忽略已连接提示 / Ignore already-connected messages
        rethrow(err); % 重新抛出真实错误 / Rethrow real error
    end % 结束错误过滤 / End error filtering
end % 结束 server 连接 / End server connection

model = mphload(model_path); % 加载 COMSOL 模型 / Load COMSOL model
if ~exist(export_dir, 'dir') % 检查导出目录是否存在 / Check whether export directory exists
    mkdir(export_dir); % 创建导出目录 / Create export directory
end % 结束目录创建 / End directory creation

forced_log_path = fullfile(export_dir, 'forced_response_contract_summary.txt'); % 构造合同摘要路径 / Build contract summary path
forced_log = fopen(forced_log_path, 'w'); % 打开合同摘要文件 / Open contract summary file
fprintf(forced_log, 'MOSAIC-Z forced-response contract summary\n'); % 写入摘要标题 / Write summary title

apply_parameter_file(model, fullfile(candidate_dir, 'comsol_parameters.csv'), true, forced_log); % 应用厚度参数 / Apply thickness parameters
apply_parameter_file(model, fullfile(candidate_dir, 'material_parameters.csv'), false, forced_log); % 应用材料参数 / Apply material parameters
apply_parameter_file(model, fullfile(candidate_dir, 'design_variable_parameters.csv'), false, forced_log); % 应用扩展设计变量 / Apply expanded design variables
support = read_optional_table(fullfile(candidate_dir, 'support_parameters.csv')); % 读取支撑合同 / Read support contract
frequency = read_optional_table(fullfile(candidate_dir, 'frequency_parameters.csv')); % 读取频率合同 / Read frequency contract
actuators = read_optional_table(fullfile(candidate_dir, 'actuator_parameters.csv')); % 读取激振器合同 / Read actuator contract
topology = read_optional_table(fullfile(candidate_dir, 'topology_primitives.csv')); % 读取拓扑合同 / Read topology contract

if ~isempty(support) && height(support) >= 1 % 检查支撑参数是否存在 / Check whether support parameters exist
    model.param.set('support_center_x', sprintf('%.12g[mm]', support.center_x_mm(1))); % 设置支撑 x 坐标 / Set support x coordinate
    model.param.set('support_center_y', sprintf('%.12g[mm]', support.center_y_mm(1))); % 设置支撑 y 坐标 / Set support y coordinate
    model.param.set('support_clamp_radius', sprintf('%.12g[mm]', support.clamp_radius_mm(1))); % 设置支撑半径 / Set support radius
    fprintf(forced_log, 'support=%.12g,%.12g,%.12g\n', support.center_x_mm(1), support.center_y_mm(1), support.clamp_radius_mm(1)); % 记录支撑参数 / Log support parameters
end % 结束支撑处理 / End support handling

if isempty(frequency) || height(frequency) < 1 % 检查频率参数是否缺失 / Check whether frequency parameters are missing
    error('frequency_parameters.csv is required. / 需要 frequency_parameters.csv。'); % 抛出缺失频率错误 / Raise missing frequency error
end % 结束频率检查 / End frequency check
drive_frequency_hz = frequency.drive_frequency_hz(1); % 读取驱动频率 / Read drive frequency
damping_ratio = frequency.damping_ratio(1); % 读取阻尼比 / Read damping ratio
force_sigma_mm = 2.5; % 设置默认激励宽度 / Set default excitation width
if any(strcmp(frequency.Properties.VariableNames, 'force_sigma_mm')) && ~isnan(frequency.force_sigma_mm(1)) % 检查可选激励宽度列 / Check optional excitation-width column
    force_sigma_mm = frequency.force_sigma_mm(1); % 读取激励宽度 / Read excitation width
end % 结束激励宽度读取 / End excitation-width loading
model.param.set('drive_frequency_hz', sprintf('%.12g[Hz]', drive_frequency_hz)); % 设置驱动频率参数 / Set drive-frequency parameter
model.param.set('modal_damping_ratio', sprintf('%.12g', damping_ratio)); % 设置阻尼比参数 / Set damping-ratio parameter
model.param.set('mosaic_force_sigma', sprintf('%.12g[mm]', force_sigma_mm)); % 设置激励空间宽度 / Set excitation spatial width
fprintf(forced_log, 'drive_frequency_hz=%.12g\n', drive_frequency_hz); % 记录驱动频率 / Log drive frequency
fprintf(forced_log, 'damping_ratio=%.12g\n', damping_ratio); % 记录阻尼比 / Log damping ratio
fprintf(forced_log, 'force_sigma_mm=%.12g\n', force_sigma_mm); % 记录激励宽度 / Log excitation width

if isempty(actuators) || height(actuators) < 1 % 检查激振器参数是否缺失 / Check whether actuator parameters are missing
    error('actuator_parameters.csv is required. / 需要 actuator_parameters.csv。'); % 抛出缺失激振器错误 / Raise missing actuator error
end % 结束激振器检查 / End actuator check
for row = 1:height(actuators) % 遍历激振器 / Iterate actuators
    actuator_id = actuators.id(row); % 读取激振器编号 / Read actuator id
    model.param.set(sprintf('act%d_x', actuator_id), sprintf('%.12g[mm]', actuators.x_mm(row))); % 设置激振器 x 坐标 / Set actuator x coordinate
    model.param.set(sprintf('act%d_y', actuator_id), sprintf('%.12g[mm]', actuators.y_mm(row))); % 设置激振器 y 坐标 / Set actuator y coordinate
    model.param.set(sprintf('act%d_amplitude', actuator_id), sprintf('%.12g', actuators.amplitude(row))); % 设置激振器幅值 / Set actuator amplitude
    model.param.set(sprintf('act%d_phase_deg', actuator_id), sprintf('%.12g[deg]', actuators.phase_deg(row))); % 设置激振器相位 / Set actuator phase
    fprintf(forced_log, 'actuator_%d=%.12g,%.12g,%.12g,%.12g\n', actuator_id, actuators.x_mm(row), actuators.y_mm(row), actuators.amplitude(row), actuators.phase_deg(row)); % 记录激振器参数 / Log actuator parameters
end % 结束激振器循环 / End actuator loop

if ~isempty(topology) % 检查拓扑合同是否存在 / Check whether topology contract exists
    model.param.set('topology_primitive_count', sprintf('%d', height(topology))); % 设置拓扑基元数量 / Set topology primitive count
    fprintf(forced_log, 'topology_primitive_count=%d\n', height(topology)); % 记录拓扑基元数量 / Log topology primitive count
end % 结束拓扑记录 / End topology logging

force_expression = build_gaussian_force_expression(actuators); % 构造高斯激励表达式 / Build Gaussian excitation expression
fprintf(forced_log, 'force_expression=%s\n', force_expression); % 记录激励表达式 / Log excitation expression
load_status = try_apply_shell_force(model, force_expression); % 尝试应用 shell 载荷 / Try applying shell load
fprintf(forced_log, 'load_status=%s\n', load_status); % 记录载荷状态 / Log load status
if ~startsWith(load_status, 'ok') % 检查载荷是否真实成功 / Check whether load really succeeded
    fclose(forced_log); % 关闭摘要文件 / Close summary file
    error('COMSOL forced-response load failed: %s / COMSOL 强迫响应载荷失败：%s', load_status, load_status); % 抛出载荷失败 / Raise load failure
end % 结束载荷状态检查 / End load-status check
study_status = try_run_frequency_study(model, drive_frequency_hz); % 尝试运行频域研究 / Try running frequency-domain study
fprintf(forced_log, 'study_status=%s\n', study_status); % 记录研究状态 / Log study status
fclose(forced_log); % 关闭摘要文件 / Close summary file

if ~strcmp(study_status, 'ok') % 检查频域研究是否成功 / Check whether frequency study succeeded
    error('COMSOL frequency-domain study failed: %s / COMSOL 频域研究失败：%s', study_status, study_status); % 抛出频域失败 / Raise frequency-domain failure
end % 结束研究状态检查 / End study status check

mphsave(model, fullfile(export_dir, 'debug_before_export_forced_response_model.mph'), 'copy', 'on'); % 保存导出前调试模型 / Save pre-export debug model
export_forced_response(model, export_dir); % 导出强迫响应结果 / Export forced response results
prepare_forced_response_view(model, drive_frequency_hz, export_dir); % 保存前创建默认查看图 / Create default viewer plot before save
mphsave(model, fullfile(export_dir, 'last_forced_response_model.mph'), 'copy', 'on'); % 保存验证模型副本 / Save validation model copy
end % 结束主函数 / End main function

function table_data = read_optional_table(path) % 读取可选 CSV 表 / Read optional CSV table
if exist(path, 'file') % 检查文件是否存在 / Check whether file exists
    table_data = readtable(path, 'TextType', 'string', 'VariableNamingRule', 'preserve'); % 读取 CSV 表 / Read CSV table
else % 处理缺失文件 / Handle missing file
    table_data = []; % 返回空值 / Return empty value
end % 结束文件检查 / End file check
end % 结束读取函数 / End reader function

function apply_parameter_file(model, path, values_are_mm, forced_log) % 应用参数 CSV / Apply parameter CSV
if ~exist(path, 'file') % 检查参数文件是否存在 / Check whether parameter file exists
    fprintf(forced_log, 'missing_parameter_file=%s\n', path); % 记录缺失文件 / Log missing file
    return; % 返回调用方 / Return to caller
end % 结束文件检查 / End file check
parameters = readtable(path, 'TextType', 'string', 'VariableNamingRule', 'preserve'); % 读取参数表 / Read parameter table
for row = 1:height(parameters) % 遍历参数行 / Iterate parameter rows
    name = char(string(parameters{row, 1})); % 读取参数名 / Read parameter name
    value = parameters{row, 2}; % 读取参数值 / Read parameter value
    if values_are_mm % 检查是否毫米厚度表 / Check whether values are millimetres
        model.param.set(name, sprintf('%.12g[mm]', value)); % 设置毫米参数 / Set millimetre parameter
    else % 处理带单位参数表 / Handle unit-aware parameter table
        unit = char(string(parameters{row, 3})); % 读取单位 / Read unit
        if strcmp(unit, '1') % 检查是否无量纲 / Check whether dimensionless
            model.param.set(name, sprintf('%.12g', value)); % 设置无量纲参数 / Set dimensionless parameter
        else % 处理有量纲参数 / Handle dimensional parameter
            model.param.set(name, sprintf('%.12g[%s]', value, unit)); % 设置带单位参数 / Set parameter with unit
        end % 结束单位分支 / End unit branch
    end % 结束参数类型分支 / End parameter-type branch
end % 结束参数循环 / End parameter loop
fprintf(forced_log, 'applied_parameter_file=%s rows=%d\n', path, height(parameters)); % 记录应用结果 / Log application result
end % 结束参数应用函数 / End parameter application function

function force_expression = build_gaussian_force_expression(actuators) % 构造高斯激励表达式 / Build Gaussian excitation expression
terms = strings(height(actuators), 1); % 创建表达式项数组 / Create expression-term array
for row = 1:height(actuators) % 遍历激振器 / Iterate actuators
    amp = actuators.amplitude(row); % 读取幅值 / Read amplitude
    phase = actuators.phase_deg(row); % 读取相位 / Read phase
    x_mm = actuators.x_mm(row); % 读取 x 坐标 / Read x coordinate
    y_mm = actuators.y_mm(row); % 读取 y 坐标 / Read y coordinate
    terms(row) = sprintf('(%.12g*1[N/m^2]*exp(i*%.12g[deg])*exp(-((x-(%.12g[mm]))^2+(y-(%.12g[mm]))^2)/(mosaic_force_sigma^2)))', amp, phase, x_mm, y_mm); % 构造带单位的单点高斯激励项 / Build one unit-aware Gaussian actuator term
end % 结束激振器循环 / End actuator loop
force_expression = char(strjoin(terms, '+')); % 合并全部激励项 / Join all excitation terms
end % 结束表达式构造函数 / End expression builder

function status = try_apply_shell_force(model, force_expression) % 尝试应用 shell 载荷 / Try applying shell force
status = 'not_attempted'; % 初始化状态 / Initialise status
shell = model.physics('shell'); % 读取 shell 物理场 / Read shell physics
feature_types = ["FaceLoad", "BoundaryLoad"]; % 定义候选载荷 feature 类型 / Define candidate load feature types
last_error = ''; % 保存最后一个错误 / Store last error
for type_index = 1:numel(feature_types) % 遍历候选 feature 类型 / Iterate candidate feature types
    feature_type = char(feature_types(type_index)); % 读取当前 feature 类型 / Read current feature type
    try % 尝试创建载荷 / Try creating load
        if has_feature(shell, 'mosaic_force') % 检查旧载荷是否存在 / Check whether old load exists
            shell.feature.remove('mosaic_force'); % 删除旧载荷 / Remove old load
        end % 结束旧载荷清理 / End old-load cleanup
        shell.create('mosaic_force', feature_type, 2); % 创建候选载荷 / Create candidate load
        shell.feature('mosaic_force').selection.all; % 选择全部 shell 面 / Select all shell boundaries
        try_set_load_expression(shell.feature('mosaic_force'), force_expression); % 设置载荷表达式 / Set load expression
        status = ['ok:' feature_type]; % 标记成功类型 / Mark successful type
        return; % 返回调用方 / Return to caller
    catch err % 捕获该类型失败 / Catch this type failure
        last_error = [feature_type ':' err.message]; % 记录失败原因 / Record failure reason
    end % 结束当前类型尝试 / End current type attempt
end % 结束 feature 类型循环 / End feature-type loop
status = ['failed:' last_error]; % 返回最终失败原因 / Return final failure reason
end % 结束载荷函数 / End load function

function exists_flag = has_feature(owner, tag) % 检查 feature 是否存在 / Check whether feature exists
exists_flag = false; % 默认不存在 / Default to not existing
try % 尝试读取 feature / Try reading feature
    owner.feature(tag); % 访问 feature / Access feature
    exists_flag = true; % 标记存在 / Mark existing
catch % 捕获缺失错误 / Catch missing-feature error
    exists_flag = false; % 保持不存在 / Keep not existing
end % 结束检查 / End check
end % 结束 feature 检查 / End feature check

function try_set_load_expression(feature, force_expression) % 设置载荷表达式 / Set load expression
try % 尝试 shell 常见 Fz 字段 / Try common shell Fz field
    feature.set('forceType', 'ForceArea'); % 设置为参考面积力 / Set force-per-reference-area mode
    feature.set('forceReferenceArea_src', 'userdef'); % 设置参考面积力来源 / Set reference-area force source
    feature.set('forceReferenceArea', {'0', '0', force_expression}); % 设置参考面积力向量 / Set reference-area force vector
    feature.set('F', {'0', '0', force_expression}); % 同步通用力向量以兼容导出 / Mirror generic force vector for compatibility
    feature.set('harmonicPerturbation', '0'); % 使用普通频域载荷 / Use normal frequency-domain load
catch % 捕获字段不匹配 / Catch field mismatch
    try % 尝试三分量载荷字段 / Try vector load field
        feature.set('FperArea', {'0', '0', force_expression}); % 设置单位面积力 / Set force per area
    catch % 捕获第二种字段失败 / Catch second field failure
        feature.set('F', {'0', '0', force_expression}); % 设置通用力字段 / Set generic force field
    end % 结束备选字段 / End fallback field
end % 结束载荷字段设置 / End load-field setting
end % 结束载荷表达式函数 / End load expression function

function status = try_run_frequency_study(model, drive_frequency_hz) % 尝试运行频域研究 / Try running frequency-domain study
status = 'not_attempted'; % 初始化状态 / Initialise status
try % 尝试创建或更新研究 / Try creating or updating study
    if has_feature(model.study, 'std_mosaic_forced') % 检查旧研究是否存在 / Check whether old study exists
        model.study.remove('std_mosaic_forced'); % 删除旧研究 / Remove old study
    end % 结束旧研究清理 / End old-study cleanup
    model.study.create('std_mosaic_forced'); % 创建新研究 / Create new study
    model.study('std_mosaic_forced').create('freq', 'Frequency'); % 创建频域步骤 / Create frequency-domain step
    model.study('std_mosaic_forced').feature('freq').set('plist', sprintf('%.12g[Hz]', drive_frequency_hz)); % 设置频率列表 / Set frequency list
    try % 尝试把激励绑定到频域研究 / Try binding excitation to frequency study
        force_feature = model.physics('shell').feature('mosaic_force'); % 读取激励 feature / Read excitation feature
        force_feature.set('StudyStep', 'std_mosaic_forced/freq'); % 绑定到强迫响应研究步 / Bind to forced-response study step
        force_feature.set('harmonicPerturbation', '0'); % 保持普通频域载荷 / Keep normal frequency-domain load
    catch bind_err % 捕获绑定失败但继续运行 / Catch binding failure while continuing
        fprintf('Could not bind mosaic_force to frequency study: %s\n', bind_err.message); % 打印绑定警告 / Print binding warning
    end % 结束绑定尝试 / End binding attempt
    model.study('std_mosaic_forced').run; % 运行频域研究 / Run frequency-domain study
    status = 'ok'; % 标记成功 / Mark success
catch err % 捕获研究错误 / Catch study error
    status = ['failed:' err.message]; % 记录失败原因 / Record failure reason
end % 结束研究尝试 / End study attempt
end % 结束频域研究函数 / End frequency-study function

function export_forced_response(model, export_dir) % 导出强迫响应 / Export forced response
dataset_tag = 'dset1'; % 设置默认数据集标签 / Set default dataset tag
try % 尝试读取最新数据集 / Try reading latest dataset
    datasets = model.result.dataset.tags; % 读取数据集标签 / Read dataset tags
    dataset_tag = char(datasets(end)); % 使用最后一个数据集 / Use last dataset
catch % 捕获数据集读取失败 / Catch dataset-read failure
    dataset_tag = 'dset1'; % 回退默认数据集 / Fall back to default dataset
end % 结束数据集选择 / End dataset selection
try % 尝试带数据集导出 / Try exporting with dataset
    data = mpheval(model, {'x', 'y', 'real(shell.w)', 'imag(shell.w)', 'abs(shell.w)'}, 'dataset', dataset_tag, 'edim', 2); % 计算响应字段 / Evaluate response fields
catch % 捕获数据集导出失败 / Catch dataset export failure
    data = mpheval(model, {'x', 'y', 'real(shell.w)', 'imag(shell.w)', 'abs(shell.w)'}, 'edim', 2); % 无数据集回退导出 / Fallback export without dataset
end % 结束导出尝试 / End export attempt
x = data.d1(:); % 读取 x 坐标 / Read x coordinates
y = data.d2(:); % 读取 y 坐标 / Read y coordinates
w_real = data.d3(:); % 读取实部位移 / Read real displacement
w_imag = data.d4(:); % 读取虚部位移 / Read imaginary displacement
w_abs = data.d5(:); % 读取振幅 / Read amplitude
if max(abs(w_abs)) <= 0 % 检查响应是否为全零 / Check whether response is all zero
    error('Forced response is all zero after solving. / 求解后的强迫响应全为零。'); % 抛出全零响应错误 / Raise all-zero response error
end % 结束全零检查 / End all-zero check
response_path = fullfile(export_dir, 'forced_response.csv'); % 构造响应输出路径 / Build response output path
response_file = fopen(response_path, 'w'); % 打开响应 CSV / Open response CSV
fprintf(response_file, 'x,y,w_real,w_imag,w_abs\n'); % 写入表头 / Write header
for point_index = 1:numel(w_abs) % 遍历采样点 / Iterate sample points
    fprintf(response_file, '%.12g,%.12g,%.12g,%.12g,%.12g\n', x(point_index), y(point_index), w_real(point_index), w_imag(point_index), w_abs(point_index)); % 写入响应行 / Write response row
end % 结束采样点循环 / End sample-point loop
fclose(response_file); % 关闭响应 CSV / Close response CSV
end % 结束响应导出函数 / End response export function

function prepare_forced_response_view(model, drive_frequency_hz, export_dir) % 创建打开 MPH 时更清楚的强迫响应图 / Create clear forced-response plot for opened MPH
viewer_log_path = fullfile(export_dir, 'forced_response_viewer_summary.txt'); % 查看图日志路径 / Viewer log path
viewer_log = fopen(viewer_log_path, 'w'); % 打开日志 / Open log
fprintf(viewer_log, 'drive_frequency_hz=%.12g\n', drive_frequency_hz); % 写入频率 / Write frequency
try % 尽量创建图，但不要让查看图失败影响仿真保存 / Best-effort viewer plot
    dataset_tag = latest_result_dataset(model); % 读取最新数据集 / Read latest dataset
    fprintf(viewer_log, 'dataset_tag=%s\n', dataset_tag); % 写入数据集 / Write dataset
    if has_feature(model.result, 'pg_mosaic_forced_response') % 删除旧图组 / Remove old plot group
        model.result.remove('pg_mosaic_forced_response'); % 删除 / Remove
    end % 结束旧图清理 / End old plot cleanup
    pg = model.result.create('pg_mosaic_forced_response', 'PlotGroup3D'); % 创建 3D 图组 / Create 3D plot group
    pg.label(sprintf('MOSAIC forced response |w| @ %.4g Hz', drive_frequency_hz)); % 设置标签 / Set label
    try % 设置数据集 / Set dataset
        pg.set('data', dataset_tag); % 绑定最新解 / Bind latest solution
    catch data_err % 记录但不中断 / Log but continue
        fprintf(viewer_log, 'plot_group_data_warning=%s\n', data_err.message); % 写入警告 / Write warning
    end % 结束数据集绑定 / End dataset binding
    try % 设置标题 / Set title
        pg.set('titletype', 'manual'); % 手动标题 / Manual title
        pg.set('title', sprintf('Forced response |w| at %.4g Hz', drive_frequency_hz)); % 标题 / Title
    catch title_err % 记录但不中断 / Log but continue
        fprintf(viewer_log, 'title_warning=%s\n', title_err.message); % 写入警告 / Write warning
    end % 结束标题设置 / End title setup
    surf = pg.create('surf_mosaic_forced_response', 'Surface'); % 创建表面图 / Create surface plot
    surf.label('Forced-response displacement amplitude |w|'); % 标签 / Label
    surf.set('expr', 'abs(shell.w)'); % 位移幅值表达式 / Displacement amplitude expression
    try % 设置单位 / Set unit
        surf.set('unit', 'm'); % 单位 / Unit
    catch unit_err % 记录但不中断 / Log but continue
        fprintf(viewer_log, 'unit_warning=%s\n', unit_err.message); % 写入警告 / Write warning
    end % 结束单位设置 / End unit setup
    try % 设置描述 / Set description
        surf.set('descr', 'Forced-response displacement amplitude'); % 描述 / Description
    catch descr_err % 记录但不中断 / Log but continue
        fprintf(viewer_log, 'descr_warning=%s\n', descr_err.message); % 写入警告 / Write warning
    end % 结束描述设置 / End description setup
    pg.run; % 运行图组 / Run plot group
    fprintf(viewer_log, 'forced_response_plot_status=ok\n'); % Log amplitude plot success
    [sand_threshold_abs, sand_peak_abs] = sampled_response_stats(model, dataset_tag, viewer_log); % Compute low-amplitude mask threshold
    prepare_sand_prediction_view(model, dataset_tag, drive_frequency_hz, sand_threshold_abs, sand_peak_abs, viewer_log); % Create sand prediction plot
    fprintf(viewer_log, 'viewer_status=ok\n'); % 记录成功 / Log success
catch err % 捕获查看图错误 / Catch viewer error
    fprintf(viewer_log, 'viewer_status=failed:%s\n', err.message); % 写入失败 / Write failure
end % 结束查看图创建 / End viewer plot creation
fclose(viewer_log); % 关闭日志 / Close log
end % 结束查看图函数 / End viewer function

function [threshold_abs, peak_abs] = sampled_response_stats(model, dataset_tag, viewer_log)
threshold_abs = NaN;
peak_abs = NaN;
try
    try
        data = mpheval(model, {'abs(shell.w)'}, 'dataset', dataset_tag, 'edim', 2);
    catch
        data = mpheval(model, {'abs(shell.w)'}, 'edim', 2);
    end
    amplitudes = abs(data.d1(:));
    amplitudes = amplitudes(isfinite(amplitudes));
    if isempty(amplitudes)
        fprintf(viewer_log, 'sand_prediction_status=skipped:no_amplitude_samples\n');
        return;
    end
    peak_abs = max(amplitudes);
    sorted_amplitudes = sort(amplitudes);
    threshold_index = max(1, min(numel(sorted_amplitudes), ceil(0.10 * numel(sorted_amplitudes))));
    threshold_abs = sorted_amplitudes(threshold_index);
    if peak_abs > 0
        threshold_abs = max(threshold_abs, peak_abs * 1e-6);
    end
    fprintf(viewer_log, 'sand_threshold_percentile=10\n');
    fprintf(viewer_log, 'sand_threshold_abs_m=%.12g\n', threshold_abs);
    fprintf(viewer_log, 'sand_peak_abs_m=%.12g\n', peak_abs);
catch stats_err
    fprintf(viewer_log, 'sand_prediction_status=skipped:stats_failed:%s\n', stats_err.message);
end
end

function prepare_sand_prediction_view(model, dataset_tag, drive_frequency_hz, threshold_abs, peak_abs, viewer_log)
try
    if ~isfinite(threshold_abs) || threshold_abs <= 0 || ~isfinite(peak_abs) || peak_abs <= 0
        fprintf(viewer_log, 'sand_prediction_status=skipped:invalid_threshold\n');
        return;
    end
    if has_feature(model.result, 'pg_mosaic_sand_prediction')
        model.result.remove('pg_mosaic_sand_prediction');
    end
    pg = model.result.create('pg_mosaic_sand_prediction', 'PlotGroup3D');
    pg.label(sprintf('MOSAIC sand prediction nodes @ %.4g Hz', drive_frequency_hz));
    try
        pg.set('data', dataset_tag);
    catch data_err
        fprintf(viewer_log, 'sand_plot_group_data_warning=%s\n', data_err.message);
    end
    try
        pg.set('titletype', 'manual');
        pg.set('title', sprintf('Sand prediction: lowest 10%% |w| at %.4g Hz', drive_frequency_hz));
    catch title_err
        fprintf(viewer_log, 'sand_title_warning=%s\n', title_err.message);
    end
    surf = pg.create('surf_mosaic_sand_prediction', 'Surface');
    surf.label('Sand prediction: low-vibration node mask');
    surf.set('expr', sprintf('if(abs(shell.w)<=%.12g[m],1-abs(shell.w)/(%.12g[m]),0)', threshold_abs, threshold_abs));
    try
        surf.set('unit', '1');
    catch unit_err
        fprintf(viewer_log, 'sand_unit_warning=%s\n', unit_err.message);
    end
    try
        surf.set('descr', 'Predicted sand retention from lowest 10% displacement amplitude');
    catch descr_err
        fprintf(viewer_log, 'sand_descr_warning=%s\n', descr_err.message);
    end
    try
        surf.set('rangecoloractive', 'on');
        surf.set('rangecolormin', '0');
        surf.set('rangecolormax', '1');
    catch range_err
        fprintf(viewer_log, 'sand_color_range_warning=%s\n', range_err.message);
    end
    pg.run;
    fprintf(viewer_log, 'sand_prediction_status=ok\n');
catch sand_err
    fprintf(viewer_log, 'sand_prediction_status=failed:%s\n', sand_err.message);
end
end

function dataset_tag = latest_result_dataset(model) % 获取最新结果数据集 / Get latest result dataset
dataset_tag = 'dset1'; % 默认数据集 / Default dataset
try % 尝试读取最后一个数据集 / Try reading last dataset
    datasets = model.result.dataset.tags; % 读取数据集标签 / Read dataset tags
    dataset_tag = char(datasets(end)); % 使用最后一个数据集 / Use latest dataset
catch % 读取失败时保持默认 / Keep default on failure
    dataset_tag = 'dset1'; % 回退 / Fallback
end % 结束数据集读取 / End dataset read
end % 结束数据集函数 / End dataset helper
