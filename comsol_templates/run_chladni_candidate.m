function run_chladni_candidate(model_path, candidate_dir, export_dir, num_modes)
%RUN_CHLADNI_CANDIDATE Run one Chladni candidate through COMSOL LiveLink.

if nargin < 4
    num_modes = 20;
end

comsol_mli_path = getenv('COMSOL_MLI_PATH');
if ~isempty(comsol_mli_path) && exist(comsol_mli_path, 'dir')
    addpath(comsol_mli_path);
elseif exist('/Applications/COMSOL64/Multiphysics/mli', 'dir')
    addpath('/Applications/COMSOL64/Multiphysics/mli');
elseif exist('/usr/local/comsol64/multiphysics/mli', 'dir')
    addpath('/usr/local/comsol64/multiphysics/mli');
elseif exist('/opt/comsol64/multiphysics/mli', 'dir')
    addpath('/opt/comsol64/multiphysics/mli');
end

import com.comsol.model.*
import com.comsol.model.util.*

try
    server_user = getenv('COMSOL_SERVER_USER');
    server_password = getenv('COMSOL_SERVER_PASSWORD');
    server_host = getenv('COMSOL_SERVER_HOST');
    if isempty(server_host)
        server_host = '127.0.0.1';
    end
    server_port = str2double(getenv('COMSOL_SERVER_PORT'));
    if isnan(server_port) || server_port <= 0
        server_port = 2036;
    end
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

if ~exist(export_dir, 'dir')
    mkdir(export_dir);
end

parameter_file = fullfile(candidate_dir, 'comsol_parameters.csv');
parameters = readtable(parameter_file, 'TextType', 'string', 'VariableNamingRule', 'preserve');
parameter_names = string(parameters{:, 1});
parameter_values_mm = parameters{:, 2};

for row = 1:height(parameters)
    name = char(parameter_names(row));
    value_mm = parameter_values_mm(row);
    model.param.set(name, sprintf('%.12g[mm]', value_mm));
end

material_file = fullfile(candidate_dir, 'material_parameters.csv');
if exist(material_file, 'file')
    material_parameters = readtable(material_file, 'TextType', 'string', 'VariableNamingRule', 'preserve');
    material_names = string(material_parameters{:, 1});
    material_values = material_parameters{:, 2};
    material_units = string(material_parameters{:, 3});
    for row = 1:height(material_parameters)
        name = char(material_names(row));
        value = material_values(row);
        unit = char(material_units(row));
        if strcmp(unit, '1')
            model.param.set(name, sprintf('%.12g', value));
        else
            model.param.set(name, sprintf('%.12g[%s]', value, unit));
        end
    end
end

design_variable_file = fullfile(candidate_dir, 'design_variable_parameters.csv');
if exist(design_variable_file, 'file')
    design_parameters = readtable(design_variable_file, 'TextType', 'string', 'VariableNamingRule', 'preserve');
    design_names = string(design_parameters{:, 1});
    design_values = design_parameters{:, 2};
    design_units = string(design_parameters{:, 3});
    for row = 1:height(design_parameters)
        name = char(design_names(row));
        value = design_values(row);
        unit = char(design_units(row));
        if strcmp(unit, '1')
            model.param.set(name, sprintf('%.12g', value));
        else
            model.param.set(name, sprintf('%.12g[%s]', value, unit));
        end
    end
end

operator_log_path = fullfile(export_dir, 'operator_contract_summary.txt');
operator_log = fopen(operator_log_path, 'w');
fprintf(operator_log, 'MOSAIC-Z operator contract summary\n');

support_file = fullfile(candidate_dir, 'support_parameters.csv');
if exist(support_file, 'file')
    support_parameters = readtable(support_file, 'TextType', 'string', 'VariableNamingRule', 'preserve');
    if height(support_parameters) >= 1
        model.param.set('support_center_x', sprintf('%.12g[mm]', support_parameters.center_x_mm(1)));
        model.param.set('support_center_y', sprintf('%.12g[mm]', support_parameters.center_y_mm(1)));
        model.param.set('support_clamp_radius', sprintf('%.12g[mm]', support_parameters.clamp_radius_mm(1)));
        fprintf(operator_log, 'support_center_x_mm=%.12g\n', support_parameters.center_x_mm(1));
        fprintf(operator_log, 'support_center_y_mm=%.12g\n', support_parameters.center_y_mm(1));
        fprintf(operator_log, 'support_clamp_radius_mm=%.12g\n', support_parameters.clamp_radius_mm(1));
    end
end

frequency_file = fullfile(candidate_dir, 'frequency_parameters.csv');
if exist(frequency_file, 'file')
    frequency_parameters = readtable(frequency_file, 'TextType', 'string', 'VariableNamingRule', 'preserve');
    if height(frequency_parameters) >= 1
        model.param.set('drive_frequency_hz', sprintf('%.12g[Hz]', frequency_parameters.drive_frequency_hz(1)));
        model.param.set('modal_damping_ratio', sprintf('%.12g', frequency_parameters.damping_ratio(1)));
        fprintf(operator_log, 'drive_frequency_hz=%.12g\n', frequency_parameters.drive_frequency_hz(1));
        fprintf(operator_log, 'modal_damping_ratio=%.12g\n', frequency_parameters.damping_ratio(1));
    end
end

actuator_file = fullfile(candidate_dir, 'actuator_parameters.csv');
if exist(actuator_file, 'file')
    actuator_parameters = readtable(actuator_file, 'TextType', 'string', 'VariableNamingRule', 'preserve');
    fprintf(operator_log, 'actuator_count=%d\n', height(actuator_parameters));
    for row = 1:height(actuator_parameters)
        actuator_id = actuator_parameters.id(row);
        model.param.set(sprintf('act%d_x', actuator_id), sprintf('%.12g[mm]', actuator_parameters.x_mm(row)));
        model.param.set(sprintf('act%d_y', actuator_id), sprintf('%.12g[mm]', actuator_parameters.y_mm(row)));
        model.param.set(sprintf('act%d_amplitude', actuator_id), sprintf('%.12g', actuator_parameters.amplitude(row)));
        model.param.set(sprintf('act%d_phase_deg', actuator_id), sprintf('%.12g[deg]', actuator_parameters.phase_deg(row)));
        fprintf(operator_log, 'actuator_%d=%.12g,%.12g,%.12g,%.12g\n', actuator_id, actuator_parameters.x_mm(row), actuator_parameters.y_mm(row), actuator_parameters.amplitude(row), actuator_parameters.phase_deg(row));
    end
end

topology_file = fullfile(candidate_dir, 'topology_primitives.csv');
if exist(topology_file, 'file')
    topology_primitives = readtable(topology_file, 'TextType', 'string', 'VariableNamingRule', 'preserve');
    model.param.set('topology_primitive_count', sprintf('%d', height(topology_primitives)));
    fprintf(operator_log, 'topology_primitive_count=%d\n', height(topology_primitives));
end

fclose(operator_log);

try
    model.study('std1').feature('eig').set('neigs', num2str(num_modes));
catch err
    fprintf('Could not set eigenmode count automatically: %s\n', err.message);
end

model.study('std1').run;

dataset_tag = 'dset1';

try
    frequencies = mphglobal(model, 'freq', 'dataset', dataset_tag, 'solnum', 'all');
catch
    frequencies = mphglobal(model, 'freq', 'solnum', 'all');
end

frequency_path = fullfile(export_dir, 'frequencies.csv');
frequency_file = fopen(frequency_path, 'w');
fprintf(frequency_file, 'mode,frequency_hz\n');
for mode_index = 1:min(num_modes, numel(frequencies))
    fprintf(frequency_file, '%d,%.12g\n', mode_index, real(frequencies(mode_index)));
end
fclose(frequency_file);

for mode_index = 1:min(num_modes, numel(frequencies))
    mode_data = mpheval(model, {'x', 'y', 'shell.w'}, 'dataset', dataset_tag, 'edim', 2, 'solnum', mode_index);
    x = mode_data.d1(:);
    y = mode_data.d2(:);
    w = mode_data.d3(:);
    mode_path = fullfile(export_dir, sprintf('mode_%02d.csv', mode_index));
    mode_file = fopen(mode_path, 'w');
    fprintf(mode_file, 'x,y,w\n');
    for point_index = 1:numel(w)
        fprintf(mode_file, '%.12g,%.12g,%.12g\n', x(point_index), y(point_index), w(point_index));
    end
    fclose(mode_file);
end

mphsave(model, fullfile(export_dir, 'last_run_model.mph'), 'copy', 'on');
end
