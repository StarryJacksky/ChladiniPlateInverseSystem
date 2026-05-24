function inspect_chladni_geometry_features() % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
%INSPECT_CHLADNI_GEOMETRY_FEATURES Print geometry feature tags and properties. / 中文说明：本注释解释脚本意图 / Chinese note: this comment explains the script intent
% This is a read-only LiveLink probe for locating the current 10x10 split. / 中文说明：本注释解释脚本意图 / Chinese note: this comment explains the script intent

addpath('/Applications/COMSOL64/Multiphysics/mli'); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation

model_path = '/Users/apple/Documents/ChladiniPlateProject/comsol_templates/Chladni_9x9_parameterized.mph'; % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation

mphstart(2036); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
model = mphload(model_path); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
geom = model.geom('geom1'); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
fprintf('\nTOP-LEVEL GEOMETRY\n'); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
print_feature_tree(geom); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation

fprintf('\nWORKPLANE GEOMETRY wp1\n'); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
wpgeom = geom.feature('wp1').geom; % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
print_feature_tree(wpgeom); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
end % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation

function print_feature_tree(geom) % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
tags = cell(geom.feature.tags); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
for tag_index = 1:numel(tags) % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    tag = tags{tag_index}; % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    feature = geom.feature(tag); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    fprintf('\nFEATURE %s\n', tag); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    try % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
        fprintf('label: %s\n', char(feature.label)); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    catch % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
        fprintf('label: <unavailable>\n'); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    end % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    try % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
        fprintf('type: %s\n', char(feature.getType)); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    catch % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
        fprintf('type: <unavailable>\n'); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    end % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    try % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
        properties = cell(feature.properties); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
        for property_index = 1:numel(properties) % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
            property_name = properties{property_index}; % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
            try % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
                value = feature.getString(property_name); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
                fprintf('  %s = %s\n', property_name, value); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
            catch % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
                try % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
                    value_array = feature.getStringArray(property_name); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
                    fprintf('  %s = [%s]\n', property_name, strjoin(cell(value_array), ', ')); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
                catch % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
                    fprintf('  %s = <non-string>\n', property_name); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
                end % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
            end % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
        end % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    catch err % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
        fprintf('properties failed: %s\n', err.message); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    end % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
end % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
end % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
