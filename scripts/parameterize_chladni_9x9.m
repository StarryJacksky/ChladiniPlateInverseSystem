function parameterize_chladni_9x9() % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
%PARAMETERIZE_CHLADNI_9X9 Add the calibrated 9x9 optimisation parameters. / 中文说明：本注释解释脚本意图 / Chinese note: this comment explains the script intent
% Run from MATLAB with COMSOL LiveLink connected to an mphserver. / 中文说明：本注释解释脚本意图 / Chinese note: this comment explains the script intent

addpath('/Applications/COMSOL64/Multiphysics/mli'); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation

model_path = '/Users/apple/Documents/Chladni.mph'; % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
output_path = '/Users/apple/Documents/ChladiniPlateProject/comsol_templates/Chladni_9x9_parameterized.mph'; % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
grid_size = 9; % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation

mphstart(2036); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
model = mphload(model_path); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation

model.param.set('grid_size', num2str(grid_size)); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
model.param.descr('grid_size', 'Optimisation grid size / 优化网格尺寸'); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
model.param.set('cell_size', 'wide/grid_size'); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
model.param.descr('cell_size', 'Nominal optimisation cell size / 名义优化单元尺寸'); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation

for row = 1:grid_size % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    for col = 1:grid_size % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
        name = sprintf('h%02d%02d', row, col); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
        model.param.set(name, '2[mm]'); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
        model.param.descr(name, sprintf('9x9 thickness cell (%d,%d) / 9x9 厚度单元 (%d,%d)', row, col, row, col));
    end % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
end % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation

model.param.set('hcenter', '2[mm]'); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
model.param.descr('hcenter', 'Fixed centre physical thickness / 中心物理约束厚度'); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation

mphsave(model, output_path, 'copy', 'on'); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
fprintf('Saved parameterized model to %s\n', output_path); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
end % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
