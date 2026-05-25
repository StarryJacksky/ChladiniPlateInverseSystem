function run_chladni_candidate(model_path, candidate_dir, export_dir, num_modes) % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
%RUN_CHLADNI_CANDIDATE Run one Chladni candidate through COMSOL LiveLink. / 中文说明：本注释解释脚本意图 / Chinese note: this comment explains the script intent
% This script is intended for MATLAB with COMSOL LiveLink available. / 中文说明：本注释解释脚本意图 / Chinese note: this comment explains the script intent
% / 中文说明：本注释解释脚本意图 / Chinese note: this comment explains the script intent
% Required model contract: / 中文说明：本注释解释脚本意图 / Chinese note: this comment explains the script intent
%   1. The model contains study tag std1 with eigenfrequency feature eig. / 中文说明：本注释解释脚本意图 / Chinese note: this comment explains the script intent
%   2. The model contains global parameters matching comsol_parameters.csv. / 中文说明：本注释解释脚本意图 / Chinese note: this comment explains the script intent
%   3. Each thickness region uses those parameters in its shell thickness d. / 中文说明：本注释解释脚本意图 / Chinese note: this comment explains the script intent
%   4. Out-of-plane displacement is available as shell.w. / 中文说明：本注释解释脚本意图 / Chinese note: this comment explains the script intent

if nargin < 4 % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    num_modes = 20; % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
end % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation

addpath('/Applications/COMSOL64/Multiphysics/mli'); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation

import com.comsol.model.* % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
import com.comsol.model.util.* % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation

try % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    mphstart(2036); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
catch err % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    if ~contains(err.message, 'already') && ~contains(err.message, '已') % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
        rethrow(err); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    end % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
end % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation

model = mphload(model_path); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation

parameter_file = fullfile(candidate_dir, 'comsol_parameters.csv'); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
parameters = readtable(parameter_file, 'TextType', 'string', 'VariableNamingRule', 'preserve'); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
parameter_names = string(parameters{:, 1}); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
parameter_values_mm = parameters{:, 2}; % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation

for row = 1:height(parameters) % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    name = char(parameter_names(row)); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    value_mm = parameter_values_mm(row); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    model.param.set(name, sprintf('%.12g[mm]', value_mm)); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
end % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation

material_file = fullfile(candidate_dir, 'material_parameters.csv'); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
if exist(material_file, 'file') % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    material_parameters = readtable(material_file, 'TextType', 'string', 'VariableNamingRule', 'preserve'); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    material_names = string(material_parameters{:, 1}); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    material_values = material_parameters{:, 2}; % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    material_units = string(material_parameters{:, 3}); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    for row = 1:height(material_parameters) % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
        name = char(material_names(row)); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
        value = material_values(row); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
        unit = char(material_units(row)); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
        if strcmp(unit, '1') % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
            model.param.set(name, sprintf('%.12g', value)); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
        else % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
            model.param.set(name, sprintf('%.12g[%s]', value, unit)); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
        end % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    end % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
end % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation

design_variable_file = fullfile(candidate_dir, 'design_variable_parameters.csv'); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
if exist(design_variable_file, 'file') % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    design_parameters = readtable(design_variable_file, 'TextType', 'string', 'VariableNamingRule', 'preserve'); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    design_names = string(design_parameters{:, 1}); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    design_values = design_parameters{:, 2}; % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    design_units = string(design_parameters{:, 3}); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    for row = 1:height(design_parameters) % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
        name = char(design_names(row)); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
        value = design_values(row); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
        unit = char(design_units(row)); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
        if strcmp(unit, '1') % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
            model.param.set(name, sprintf('%.12g', value)); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
        else % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
            model.param.set(name, sprintf('%.12g[%s]', value, unit)); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
        end % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    end % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
end % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation

try % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    model.study('std1').feature('eig').set('neigs', num2str(num_modes)); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
catch err % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    fprintf('Could not set eigenmode count automatically: %s\n', err.message); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
end % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation

model.study('std1').run; % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation

if ~exist(export_dir, 'dir') % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    mkdir(export_dir); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
end % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation

dataset_tag = 'dset1'; % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation

try % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    frequencies = mphglobal(model, 'freq', 'dataset', dataset_tag, 'solnum', 'all'); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
catch % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    frequencies = mphglobal(model, 'freq', 'solnum', 'all'); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
end % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation

frequency_path = fullfile(export_dir, 'frequencies.csv'); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
frequency_file = fopen(frequency_path, 'w'); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
fprintf(frequency_file, 'mode,frequency_hz\n'); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
for mode_index = 1:min(num_modes, numel(frequencies)) % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    fprintf(frequency_file, '%d,%.12g\n', mode_index, real(frequencies(mode_index))); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
end % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
fclose(frequency_file); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation

for mode_index = 1:min(num_modes, numel(frequencies)) % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    mode_data = mpheval(model, {'x', 'y', 'shell.w'}, 'dataset', dataset_tag, 'edim', 2, 'solnum', mode_index); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    x = mode_data.d1(:); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    y = mode_data.d2(:); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    w = mode_data.d3(:); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    mode_path = fullfile(export_dir, sprintf('mode_%02d.csv', mode_index)); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    mode_file = fopen(mode_path, 'w'); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    fprintf(mode_file, 'x,y,w\n'); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    for point_index = 1:numel(w) % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
        fprintf(mode_file, '%.12g,%.12g,%.12g\n', x(point_index), y(point_index), w(point_index)); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    end % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    fclose(mode_file); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
end % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation

mphsave(model, fullfile(export_dir, 'last_run_model.mph'), 'copy', 'on'); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
end % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
