function bind_chladni_15x15_model() % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
%BIND_CHLADNI_15X15_MODEL Rebuild the baseline split and bind 15x15 shell thicknesses. / 中文说明：本注释解释脚本意图 / Chinese note: this comment explains the script intent
% This preserves the square, centre hole, and washer radius, then binds the / 中文说明：本注释解释脚本意图 / Chinese note: this comment explains the script intent
% default shell thickness to a 15x15 piecewise expression. / 中文说明：本注释解释脚本意图 / Chinese note: this comment explains the script intent

addpath('/Applications/COMSOL64/Multiphysics/mli'); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation

input_path = '/Users/apple/Documents/ChladiniPlateProject/comsol_templates/Chladni_15x15_parameterized.mph'; % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
output_path = '/Users/apple/Documents/ChladiniPlateProject/comsol_templates/Chladni_15x15_bound.mph'; % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
mapping_path = '/Users/apple/Documents/ChladiniPlateProject/reports/chladni_15x15_boundary_mapping.csv'; % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
grid_size = 15; % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
half_width = 0.075; % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
cell_size = 0.15 / grid_size; % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
first_split = -half_width + cell_size; % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
line_extent = 0.08; % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
washer_radius = 0.00433; % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
radius_tol = 1e-6; % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation

mphstart(2036); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
model = mphload(input_path); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
apply_material_contract(model); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation

wpgeom = model.geom('geom1').feature('wp1').geom; % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
wpgeom.feature('pol1').set('table', [first_split, line_extent; first_split, -line_extent]); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
wpgeom.feature('arr1').set('size', [grid_size - 1, 1]); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
wpgeom.feature('arr1').set('displ', [cell_size, 0]); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
wpgeom.feature('pol2').set('table', [-line_extent, first_split; line_extent, first_split]); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
wpgeom.feature('arr2').set('size', [1, grid_size - 1]); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
wpgeom.feature('arr2').set('displ', [0, cell_size]); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation

wpgeom.run; % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
model.geom('geom1').run; % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation

shell = model.physics('shell'); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
remove_cell_thickness_features(shell); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
shell.feature('to1').set('d', build_thickness_expression(grid_size, half_width, cell_size)); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation

info = mphgeominfo(model, 'geom1'); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
cell_boundaries = cell(grid_size, grid_size); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
mapping_rows = {}; % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation

for boundary_id = 1:info.Nboundaries % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    coords = mphgetcoords(model, 'geom1', 'boundary', boundary_id); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    centroid_x = mean(coords(1, :)); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    centroid_y = mean(coords(2, :)); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    col = clamp_index(floor((centroid_x + half_width) / cell_size) + 1, grid_size); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    row = clamp_index(floor((half_width - centroid_y) / cell_size) + 1, grid_size); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    cell_boundaries{row, col}(end + 1) = boundary_id; % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    mapping_rows(end + 1, :) = {boundary_id, row, col, centroid_x, centroid_y}; %#ok<AGROW> % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
end % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation

fixed_edges = find_washer_edges(model, washer_radius, radius_tol); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
shell.feature('fix1').selection.set(fixed_edges); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation

try % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    model.mesh('mesh1').run; % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
catch err % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    fprintf('Mesh rebuild warning: %s\n', err.message); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
end % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation

write_boundary_mapping(mapping_path, mapping_rows); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
mphsave(model, output_path, 'copy', 'on'); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
fprintf('Saved bound 15x15 model to %s\n', output_path); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
fprintf('Boundary mapping written to %s\n', mapping_path); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
fprintf('Boundary count: %d; fixed washer edges: %s\n', info.Nboundaries, mat2str(fixed_edges)); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
end % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation

function apply_material_contract(model) % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
model.param.set('mat_density', '1200[kg/m^3]'); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
model.param.set('mat_poisson_ratio', '0.35'); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
model.param.set('mat_youngs_modulus', '2.0e9[Pa]'); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
model.param.set('mat_thermal_conductivity', '0.18[W/(m*K)]'); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
model.param.set('mat_heat_capacity', '1200[J/(kg*K)]'); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
model.param.set('mat_thermal_expansion', '8.0e-5[1/K]'); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
try % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    material = model.material('mat1'); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    material.propertyGroup('def').set('density', {'mat_density'}); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    material.propertyGroup('def').set('youngsmodulus', {'mat_youngs_modulus'}); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    material.propertyGroup('def').set('poissonsratio', {'mat_poisson_ratio'}); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    material.propertyGroup('def').set('thermalconductivity', {'mat_thermal_conductivity'}); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    material.propertyGroup('def').set('heatcapacity', {'mat_heat_capacity'}); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    material.propertyGroup('def').set('thermalexpansioncoefficient', {'mat_thermal_expansion'}); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
catch err % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    fprintf('Material contract warning: %s\n', err.message); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
end % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
end % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation

function remove_cell_thickness_features(shell) % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
tags = cell(shell.feature.tags); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
for tag_index = 1:numel(tags) % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    tag = tags{tag_index}; % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    if ismember(tag, {'to2', 'to3', 'to4', 'to5', 'to6', 'to7', 'to8'}) || startsWith(tag, 'to_') % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
        shell.feature.remove(tag); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    end % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
end % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
end % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation

function expression = build_thickness_expression(grid_size, half_width, cell_size) % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
row_expressions = cell(1, grid_size); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
for row = 1:grid_size % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    x_expression = sprintf('h%02d%02d', row, grid_size); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    for col = grid_size - 1:-1:1 % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
        split_x = -half_width + col * cell_size; % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
        x_expression = sprintf('if(x<=%.12g,h%02d%02d,%s)', split_x, row, col, x_expression); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    end % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    row_expressions{row} = x_expression; % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
end % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation

expression = row_expressions{grid_size}; % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
for row = grid_size - 1:-1:1 % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    split_y = half_width - row * cell_size; % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    expression = sprintf('if(y>=%.12g,%s,%s)', split_y, row_expressions{row}, expression); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
end % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
end % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation

function index = clamp_index(index, grid_size) % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
index = max(1, min(grid_size, index)); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
end % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation

function fixed_edges = find_washer_edges(model, washer_radius, radius_tol) % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
info = mphgeominfo(model, 'geom1'); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
fixed_edges = []; % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
for edge_id = 1:info.Nedges % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    coords = mphgetcoords(model, 'geom1', 'edge', edge_id); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    radii = sqrt(coords(1, :).^2 + coords(2, :).^2); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    if max(abs(radii - washer_radius)) < radius_tol % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
        fixed_edges(end + 1) = edge_id; %#ok<AGROW> % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    end % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
end % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
end % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation

function write_boundary_mapping(mapping_path, mapping_rows) % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
file_id = fopen(mapping_path, 'w'); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
fprintf(file_id, 'boundary_id,row,col,centroid_x_m,centroid_y_m\n'); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
for row_index = 1:size(mapping_rows, 1) % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
    fprintf(file_id, '%d,%d,%d,%.12g,%.12g\n', mapping_rows{row_index, :}); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
end % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
fclose(file_id); % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
end % 执行本行 MATLAB/COMSOL 操作 / Execute this MATLAB/COMSOL operation
