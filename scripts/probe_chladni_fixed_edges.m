function probe_chladni_fixed_edges() % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
%PROBE_CHLADNI_FIXED_EDGES Print coordinates for the current fixed edges. / 中文说明：本注释解释脚本意图 / Chinese note: this comment explains the script intent

addpath('/Applications/COMSOL64/Multiphysics/mli'); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation

model_path = '/Users/apple/Documents/ChladiniPlateProject/comsol_templates/Chladni_9x9_parameterized.mph'; % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
fixed_edges = [124, 125, 141, 149]; % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation

mphstart(2036); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
model = mphload(model_path); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation

for edge_index = 1:numel(fixed_edges) % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    edge_id = fixed_edges(edge_index); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    coords = mphgetcoords(model, 'geom1', 'edge', edge_id); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    radii = sqrt(coords(1, :).^2 + coords(2, :).^2); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    fprintf('edge %d coords size %dx%d radius min %.8g max %.8g\n', edge_id, size(coords, 1), size(coords, 2), min(radii), max(radii)); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    disp(coords); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
end % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
end % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
