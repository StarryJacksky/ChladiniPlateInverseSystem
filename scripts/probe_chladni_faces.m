function probe_chladni_faces() % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
%PROBE_CHLADNI_FACES Print geometry entity information for the Chladni model. / 中文说明：本注释解释脚本意图 / Chinese note: this comment explains the script intent
% This is a read-only LiveLink probe used before binding thickness selections. / 中文说明：本注释解释脚本意图 / Chinese note: this comment explains the script intent

addpath('/Applications/COMSOL64/Multiphysics/mli'); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation

model_path = '/Users/apple/Documents/ChladiniPlateProject/comsol_templates/Chladni_9x9_parameterized.mph'; % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation

mphstart(2036); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
model = mphload(model_path); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation

info = mphgeominfo(model, 'geom1'); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
fprintf('Geometry info fields:\n'); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
disp(fieldnames(info)); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
fprintf('Ndomains=%d Nboundaries=%d Nedges=%d Nvertices=%d Nfaces=%d\n', info.Ndomains, info.Nboundaries, info.Nedges, info.Nvertices, info.Nfaces); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation

entity_names = {'face', 'boundary'}; % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
entity_ids = [1, 2, 3, 4, 5, 50, 81, 104]; % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation

for name_index = 1:numel(entity_names) % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    entity_name = entity_names{name_index}; % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    fprintf('\nEntity probe: %s\n', entity_name); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    for id_index = 1:numel(entity_ids) % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
        entity_id = entity_ids(id_index); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
        try % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
            coords = mphgetcoords(model, 'geom1', entity_name, entity_id); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
            fprintf('%s %d coords size %dx%d\n', entity_name, entity_id, size(coords, 1), size(coords, 2)); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
            disp(coords(:, 1:min(size(coords, 2), 6))); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
        catch err % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
            fprintf('%s %d failed: %s\n', entity_name, entity_id, err.message); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
        end % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    end % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
end % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
end % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
