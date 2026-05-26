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

try
    model.study('std1').feature('eig').set('neigs', num2str(num_modes));
catch err
    fprintf('Could not set eigenmode count automatically: %s\n', err.message);
end

model.study('std1').run;

if ~exist(export_dir, 'dir')
    mkdir(export_dir);
end

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
