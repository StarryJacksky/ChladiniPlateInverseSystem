function run_chladni_forced_response_orthotropic(model_path, candidate_dir, export_dir) % orthotropic shell 强迫响应 / Orthotropic shell forced-response runner
%RUN_CHLADNI_FORCED_RESPONSE_ORTHOTROPIC Run one orthotropic candidate through COMSOL.
%   等价于 run_chladni_forced_response，但若 candidate_dir/theta_field.csv 存在则启用 orthotropic shell.

comsol_mli_path = getenv('COMSOL_MLI_PATH');
if ~isempty(comsol_mli_path) && exist(comsol_mli_path, 'dir')
    addpath(comsol_mli_path);
elseif exist('/Applications/COMSOL64/Multiphysics/mli', 'dir')
    addpath('/Applications/COMSOL64/Multiphysics/mli');
end

import com.comsol.model.*
import com.comsol.model.util.*

try
    server_user = getenv('COMSOL_SERVER_USER');
    server_password = getenv('COMSOL_SERVER_PASSWORD');
    server_host = getenv('COMSOL_SERVER_HOST');
    if isempty(server_host); server_host = '127.0.0.1'; end
    server_port = str2double(getenv('COMSOL_SERVER_PORT'));
    if isnan(server_port) || server_port <= 0; server_port = 2036; end
    if ~isempty(server_user)
        mphstart(char(server_host), server_port, server_user, server_password);
    else
        mphstart(server_port);
    end
catch err
    if ~contains(err.message, 'already') && ~contains(err.message, '已')
        rethrow(err);
    end
end

model = mphload(model_path);
if ~exist(export_dir, 'dir'); mkdir(export_dir); end

forced_log_path = fullfile(export_dir, 'forced_response_contract_summary.txt');
forced_log = fopen(forced_log_path, 'w');
fprintf(forced_log, 'MOSAIC-Z forced-response contract summary (orthotropic-capable)\n');
fprintf(forced_log, 'candidate_dir=%s\n', candidate_dir);

apply_parameter_file(model, fullfile(candidate_dir, 'comsol_parameters.csv'), true, forced_log);
apply_parameter_file(model, fullfile(candidate_dir, 'material_parameters.csv'), false, forced_log);
apply_parameter_file(model, fullfile(candidate_dir, 'design_variable_parameters.csv'), false, forced_log);

support = read_optional_table(fullfile(candidate_dir, 'support_parameters.csv'));
frequency = read_optional_table(fullfile(candidate_dir, 'frequency_parameters.csv'));
actuators = read_optional_table(fullfile(candidate_dir, 'actuator_parameters.csv'));

if ~isempty(support) && height(support) >= 1
    model.param.set('support_center_x', sprintf('%.12g[mm]', support.center_x_mm(1)));
    model.param.set('support_center_y', sprintf('%.12g[mm]', support.center_y_mm(1)));
    model.param.set('support_clamp_radius', sprintf('%.12g[mm]', support.clamp_radius_mm(1)));
    fprintf(forced_log, 'support=%.12g,%.12g,%.12g\n', support.center_x_mm(1), support.center_y_mm(1), support.clamp_radius_mm(1));
end

if isempty(frequency) || height(frequency) < 1
    error('frequency_parameters.csv is required.');
end
drive_frequency_hz = frequency.drive_frequency_hz(1);
damping_ratio = frequency.damping_ratio(1);
force_sigma_mm = 2.5;
if any(strcmp(frequency.Properties.VariableNames, 'force_sigma_mm')) && ~isnan(frequency.force_sigma_mm(1))
    force_sigma_mm = frequency.force_sigma_mm(1);
end
model.param.set('drive_frequency_hz', sprintf('%.12g[Hz]', drive_frequency_hz));
model.param.set('modal_damping_ratio', sprintf('%.12g', damping_ratio));
model.param.set('mosaic_force_sigma', sprintf('%.12g[mm]', force_sigma_mm));
fprintf(forced_log, 'drive_frequency_hz=%.12g\n', drive_frequency_hz);
fprintf(forced_log, 'damping_ratio=%.12g\n', damping_ratio);
fprintf(forced_log, 'force_sigma_mm=%.12g\n', force_sigma_mm);

if isempty(actuators) || height(actuators) < 1
    error('actuator_parameters.csv is required.');
end
for row = 1:height(actuators)
    actuator_id = actuators.id(row);
    model.param.set(sprintf('act%d_x', actuator_id), sprintf('%.12g[mm]', actuators.x_mm(row)));
    model.param.set(sprintf('act%d_y', actuator_id), sprintf('%.12g[mm]', actuators.y_mm(row)));
    model.param.set(sprintf('act%d_amplitude', actuator_id), sprintf('%.12g', actuators.amplitude(row)));
    model.param.set(sprintf('act%d_phase_deg', actuator_id), sprintf('%.12g[deg]', actuators.phase_deg(row)));
    fprintf(forced_log, 'actuator_%d=%.12g,%.12g,%.12g,%.12g\n', actuator_id, actuators.x_mm(row), actuators.y_mm(row), actuators.amplitude(row), actuators.phase_deg(row));
end

% === NEW: orthotropic shell injection if theta_field.csv is present ===
theta_field_path = fullfile(candidate_dir, 'theta_field.csv');
orthotropic_status = 'disabled';
if exist(theta_field_path, 'file')
    fprintf(forced_log, 'theta_field_csv=%s\n', theta_field_path);
    orthotropic_status = apply_orthotropic_shell(model, theta_field_path, forced_log);
end
fprintf(forced_log, 'orthotropic_final_status=%s\n', orthotropic_status);

force_expression = build_gaussian_force_expression(actuators);
fprintf(forced_log, 'force_expression=%s\n', force_expression);
load_status = try_apply_shell_force(model, force_expression);
fprintf(forced_log, 'load_status=%s\n', load_status);
if ~startsWith(load_status, 'ok')
    fclose(forced_log);
    error('COMSOL forced-response load failed: %s', load_status);
end
study_status = try_run_frequency_study(model, drive_frequency_hz);
fprintf(forced_log, 'study_status=%s\n', study_status);
fclose(forced_log);

if ~strcmp(study_status, 'ok')
    error('COMSOL frequency-domain study failed: %s', study_status);
end

mphsave(model, fullfile(export_dir, 'debug_before_export_forced_response_model.mph'), 'copy', 'on');
export_forced_response(model, export_dir);
prepare_forced_response_view(model, drive_frequency_hz, export_dir);
mphsave(model, fullfile(export_dir, 'last_forced_response_model.mph'), 'copy', 'on');
end

% ====== helpers below (mirrored from run_chladni_forced_response.m) ======
function table_data = read_optional_table(path)
if exist(path, 'file')
    table_data = readtable(path, 'TextType', 'string', 'VariableNamingRule', 'preserve');
else
    table_data = [];
end
end

function apply_parameter_file(model, path, values_are_mm, forced_log)
if ~exist(path, 'file')
    fprintf(forced_log, 'missing_parameter_file=%s\n', path);
    return;
end
parameters = readtable(path, 'TextType', 'string', 'VariableNamingRule', 'preserve');
for row = 1:height(parameters)
    name = char(string(parameters{row, 1}));
    value = parameters{row, 2};
    if values_are_mm
        model.param.set(name, sprintf('%.12g[mm]', value));
    else
        unit = char(string(parameters{row, 3}));
        if strcmp(unit, '1')
            model.param.set(name, sprintf('%.12g', value));
        else
            model.param.set(name, sprintf('%.12g[%s]', value, unit));
        end
    end
end
fprintf(forced_log, 'applied_parameter_file=%s rows=%d\n', path, height(parameters));
end

function force_expression = build_gaussian_force_expression(actuators)
terms = strings(height(actuators), 1);
for row = 1:height(actuators)
    amp = actuators.amplitude(row);
    phase = actuators.phase_deg(row);
    x_mm = actuators.x_mm(row);
    y_mm = actuators.y_mm(row);
    terms(row) = sprintf('(%.12g*1[N/m^2]*exp(i*%.12g[deg])*exp(-((x-(%.12g[mm]))^2+(y-(%.12g[mm]))^2)/(mosaic_force_sigma^2)))', amp, phase, x_mm, y_mm);
end
force_expression = char(strjoin(terms, '+'));
end

function status = try_apply_shell_force(model, force_expression)
status = 'not_attempted';
shell = model.physics('shell');
feature_types = ["FaceLoad", "BoundaryLoad"];
last_error = '';
for type_index = 1:numel(feature_types)
    feature_type = char(feature_types(type_index));
    try
        if has_feature(shell, 'mosaic_force')
            shell.feature.remove('mosaic_force');
        end
        shell.create('mosaic_force', feature_type, 2);
        shell.feature('mosaic_force').selection.all;
        try_set_load_expression(shell.feature('mosaic_force'), force_expression);
        status = ['ok:' feature_type];
        return;
    catch err
        last_error = [feature_type ':' err.message];
    end
end
status = ['failed:' last_error];
end

function exists_flag = has_feature(owner, tag)
exists_flag = false;
try
    owner.feature(tag);
    exists_flag = true;
catch
    exists_flag = false;
end
end

function try_set_load_expression(feature, force_expression)
try
    feature.set('forceType', 'ForceArea');
    feature.set('forceReferenceArea_src', 'userdef');
    feature.set('forceReferenceArea', {'0', '0', force_expression});
    feature.set('F', {'0', '0', force_expression});
    feature.set('harmonicPerturbation', '0');
catch
    try
        feature.set('FperArea', {'0', '0', force_expression});
    catch
        feature.set('F', {'0', '0', force_expression});
    end
end
end

function status = try_run_frequency_study(model, drive_frequency_hz)
status = 'not_attempted';
try
    if has_feature(model.study, 'std_mosaic_forced')
        model.study.remove('std_mosaic_forced');
    end
    model.study.create('std_mosaic_forced');
    model.study('std_mosaic_forced').create('freq', 'Frequency');
    model.study('std_mosaic_forced').feature('freq').set('plist', sprintf('%.12g[Hz]', drive_frequency_hz));
    try
        force_feature = model.physics('shell').feature('mosaic_force');
        force_feature.set('StudyStep', 'std_mosaic_forced/freq');
        force_feature.set('harmonicPerturbation', '0');
    catch bind_err
        fprintf('Could not bind mosaic_force to frequency study: %s\n', bind_err.message);
    end
    model.study('std_mosaic_forced').run;
    status = 'ok';
catch err
    status = ['failed:' err.message];
end
end

function export_forced_response(model, export_dir)
dataset_tag = 'dset1';
try
    datasets = model.result.dataset.tags;
    dataset_tag = char(datasets(end));
catch
    dataset_tag = 'dset1';
end
try
    data = mpheval(model, {'x', 'y', 'real(shell.w)', 'imag(shell.w)', 'abs(shell.w)'}, 'dataset', dataset_tag, 'edim', 2);
catch
    data = mpheval(model, {'x', 'y', 'real(shell.w)', 'imag(shell.w)', 'abs(shell.w)'}, 'edim', 2);
end
x = data.d1(:);
y = data.d2(:);
w_real = data.d3(:);
w_imag = data.d4(:);
w_abs = data.d5(:);
if max(abs(w_abs)) <= 0
    error('Forced response is all zero after solving.');
end
response_path = fullfile(export_dir, 'forced_response.csv');
response_file = fopen(response_path, 'w');
fprintf(response_file, 'x,y,w_real,w_imag,w_abs\n');
for point_index = 1:numel(w_abs)
    fprintf(response_file, '%.12g,%.12g,%.12g,%.12g,%.12g\n', x(point_index), y(point_index), w_real(point_index), w_imag(point_index), w_abs(point_index));
end
fclose(response_file);
end

function prepare_forced_response_view(model, drive_frequency_hz, export_dir)
viewer_log_path = fullfile(export_dir, 'forced_response_viewer_summary.txt');
viewer_log = fopen(viewer_log_path, 'w');
fprintf(viewer_log, 'drive_frequency_hz=%.12g\n', drive_frequency_hz);
try
    dataset_tag = latest_result_dataset(model);
    fprintf(viewer_log, 'dataset_tag=%s\n', dataset_tag);
    if has_feature(model.result, 'pg_mosaic_forced_response')
        model.result.remove('pg_mosaic_forced_response');
    end
    pg = model.result.create('pg_mosaic_forced_response', 'PlotGroup3D');
    pg.label(sprintf('MOSAIC forced response |w| @ %.4g Hz', drive_frequency_hz));
    try
        pg.set('data', dataset_tag);
    catch data_err
        fprintf(viewer_log, 'plot_group_data_warning=%s\n', data_err.message);
    end
    try
        pg.set('titletype', 'manual');
        pg.set('title', sprintf('Forced response |w| at %.4g Hz', drive_frequency_hz));
    catch title_err
        fprintf(viewer_log, 'title_warning=%s\n', title_err.message);
    end
    surf = pg.create('surf_mosaic_forced_response', 'Surface');
    surf.label('Forced-response displacement amplitude |w|');
    surf.set('expr', 'abs(shell.w)');
    try
        surf.set('unit', 'm');
    catch unit_err
        fprintf(viewer_log, 'unit_warning=%s\n', unit_err.message);
    end
    try
        surf.set('descr', 'Forced-response displacement amplitude');
    catch descr_err
        fprintf(viewer_log, 'descr_warning=%s\n', descr_err.message);
    end
    pg.run;
    fprintf(viewer_log, 'viewer_status=ok\n');
catch err
    fprintf(viewer_log, 'viewer_status=failed:%s\n', err.message);
end
fclose(viewer_log);
end

function dataset_tag = latest_result_dataset(model)
dataset_tag = 'dset1';
try
    datasets = model.result.dataset.tags;
    dataset_tag = char(datasets(end));
catch
    dataset_tag = 'dset1';
end
end
