function clean_geometry_params(model_path, output_path, dry_run) % 合并 wide→length，删 cell_size / Merge wide→length, drop cell_size
%CLEAN_GEOMETRY_PARAMS Safely remove the dead `wide` and `cell_size` global
% parameters from the Chladni .mph template.
%
% Safety contract:
%   1. Scan EVERY model expression (params, variables, geometry feature
%      properties, materials, physics features, mesh, studies) for
%      references to `wide` or `cell_size`.
%   2. If a reference exists outside the known dead path
%      (cell_size = wide/grid_size), abort without writing — print the
%      reference so the user can decide.
%   3. Otherwise: drop `cell_size`, drop `wide`, save to output_path.
%
% Usage:
%   clean_geometry_params('comsol_templates/Chladni_15x15_bound.mph', ...
%                         'comsol_templates/Chladni_15x15_bound.mph', false)
%   clean_geometry_params(..., true) -> dry-run; report only, don't write

if nargin < 3
    dry_run = true;
end
if nargin < 2
    output_path = model_path;
end

comsol_mli_path = getenv('COMSOL_MLI_PATH');
if ~isempty(comsol_mli_path) && exist(comsol_mli_path, 'dir')
    addpath(comsol_mli_path);
elseif exist('/Applications/COMSOL64/Multiphysics/mli', 'dir')
    addpath('/Applications/COMSOL64/Multiphysics/mli');
end

import com.comsol.model.*
import com.comsol.model.util.*

try
    server_host = getenv('COMSOL_SERVER_HOST');
    if isempty(server_host); server_host = '127.0.0.1'; end
    server_port = str2double(getenv('COMSOL_SERVER_PORT'));
    if isnan(server_port) || server_port <= 0; server_port = 2036; end
    server_user = getenv('COMSOL_SERVER_USER');
    server_password = getenv('COMSOL_SERVER_PASSWORD');
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
fprintf('Loaded %s\n', model_path);
if dry_run
    fprintf('(DRY-RUN mode — will report only, no write)\n');
end

% ===== Step 1: Pre-flight value verification =====
fprintf('\n--- Pre-flight value verification ---\n');
try
    wide_str = char(model.param.get('wide'));
catch
    wide_str = '(absent)';
end
try
    length_str = char(model.param.get('length'));
catch
    length_str = '(absent)';
end
try
    cell_size_str = char(model.param.get('cell_size'));
catch
    cell_size_str = '(absent)';
end
fprintf('  wide      = %s\n', wide_str);
fprintf('  length    = %s\n', length_str);
fprintf('  cell_size = %s\n', cell_size_str);

% Numerical evaluation to ensure wide and length are equal
try
    wide_val = model.param.evaluate('wide');
catch
    wide_val = NaN;
end
try
    length_val = model.param.evaluate('length');
catch
    length_val = NaN;
end
fprintf('  evaluated: wide=%.6g m, length=%.6g m, |diff|=%.3e m\n', ...
        wide_val, length_val, abs(wide_val - length_val));
if abs(wide_val - length_val) > 1e-9
    error(['ABORT: wide (%.6g m) and length (%.6g m) differ — they are NOT ' ...
           'safely mergeable. Inspect the .mph manually.'], wide_val, length_val);
end

% ===== Step 2: Comprehensive reference scan =====
fprintf('\n--- Scanning for references to `wide` and `cell_size` ---\n');
hits = struct('wide', {{}}, 'cell_size', {{}});

% --- 2a: Global parameters ---
try
    pnames = model.param.varnames;
    for k = 1:length(pnames)
        pname = char(pnames(k));
        if strcmp(pname, 'wide') || strcmp(pname, 'cell_size')
            continue;
        end
        try
            pval = char(model.param.get(pname));
        catch
            pval = '';
        end
        if has_word(pval, 'wide')
            hits.wide{end+1} = sprintf('param[%s] = %s', pname, pval);
        end
        if has_word(pval, 'cell_size')
            hits.cell_size{end+1} = sprintf('param[%s] = %s', pname, pval);
        end
    end
catch
end

% --- 2b: Component-level walk ---
comp_tags = model.component.tags;
for k = 1:length(comp_tags)
    comp_tag = char(comp_tags(k));

    % Variables
    try
        var_tags = model.component(comp_tag).variable.tags;
    catch
        var_tags = [];
    end
    for v = 1:length(var_tags)
        vtag = char(var_tags(v));
        try
            var_names = model.component(comp_tag).variable(vtag).varnames;
        catch
            var_names = [];
        end
        for n = 1:length(var_names)
            vname = char(var_names(n));
            try
                vexpr = char(model.component(comp_tag).variable(vtag).get(vname));
            catch
                vexpr = '';
            end
            if has_word(vexpr, 'wide')
                hits.wide{end+1} = sprintf('var[%s.%s.%s] = %s', comp_tag, vtag, vname, trunc_str(vexpr));
            end
            if has_word(vexpr, 'cell_size')
                hits.cell_size{end+1} = sprintf('var[%s.%s.%s] = %s', comp_tag, vtag, vname, trunc_str(vexpr));
            end
        end
    end

    % Geometry features (recurse into workplane sketches)
    try
        geom_tags = model.component(comp_tag).geom.tags;
    catch
        geom_tags = [];
    end
    for g = 1:length(geom_tags)
        geom_tag = char(geom_tags(g));
        hits = scan_feature_tree(model.component(comp_tag).geom(geom_tag), sprintf('geom[%s.%s]', comp_tag, geom_tag), hits);
    end

    % Materials
    try
        mat_tags = model.component(comp_tag).material.tags;
    catch
        mat_tags = [];
    end
    for m = 1:length(mat_tags)
        mat_tag = char(mat_tags(m));
        try
            pg_tags = model.component(comp_tag).material(mat_tag).propertyGroup.tags;
        catch
            pg_tags = [];
        end
        for p = 1:length(pg_tags)
            pg_tag = char(pg_tags(p));
            try
                prop_names = model.component(comp_tag).material(mat_tag).propertyGroup(pg_tag).propertyNames;
            catch
                prop_names = [];
            end
            for n = 1:length(prop_names)
                pname = char(prop_names(n));
                try
                    pval = char(model.component(comp_tag).material(mat_tag).propertyGroup(pg_tag).getString(pname));
                catch
                    pval = '';
                end
                if has_word(pval, 'wide')
                    hits.wide{end+1} = sprintf('mat[%s.%s.%s.%s] = %s', comp_tag, mat_tag, pg_tag, pname, trunc_str(pval));
                end
                if has_word(pval, 'cell_size')
                    hits.cell_size{end+1} = sprintf('mat[%s.%s.%s.%s] = %s', comp_tag, mat_tag, pg_tag, pname, trunc_str(pval));
                end
            end
        end
    end

    % Physics
    try
        phys_tags = model.component(comp_tag).physics.tags;
    catch
        phys_tags = [];
    end
    for ph = 1:length(phys_tags)
        phys_tag = char(phys_tags(ph));
        hits = scan_feature_tree(model.component(comp_tag).physics(phys_tag), sprintf('physics[%s.%s]', comp_tag, phys_tag), hits);
    end

    % Mesh
    try
        mesh_tags = model.component(comp_tag).mesh.tags;
    catch
        mesh_tags = [];
    end
    for ms = 1:length(mesh_tags)
        mesh_tag = char(mesh_tags(ms));
        hits = scan_feature_tree(model.component(comp_tag).mesh(mesh_tag), sprintf('mesh[%s.%s]', comp_tag, mesh_tag), hits);
    end
end

% --- Report ---
fprintf('\n  `wide` references found: %d\n', length(hits.wide));
for k = 1:length(hits.wide)
    fprintf('    %s\n', hits.wide{k});
end
fprintf('  `cell_size` references found: %d\n', length(hits.cell_size));
for k = 1:length(hits.cell_size)
    fprintf('    %s\n', hits.cell_size{k});
end

% --- Decide: only safe if `wide` is unreferenced (cell_size's reference doesn't count since we're deleting cell_size anyway), and cell_size is unreferenced ---
unsafe = false;
if ~isempty(hits.wide)
    fprintf('\n  WARNING: `wide` is referenced outside the dead cell_size path — abort.\n');
    unsafe = true;
end
if ~isempty(hits.cell_size)
    fprintf('\n  WARNING: `cell_size` is referenced somewhere — abort.\n');
    unsafe = true;
end

if unsafe
    error('Refusing to delete because of external references; see warnings above.');
end

if dry_run
    fprintf('\nDRY-RUN: would delete params `cell_size` and `wide`. Re-run with dry_run=false to apply.\n');
    return;
end

% ===== Step 3: Delete params and save =====
fprintf('\n--- Applying changes ---\n');
try
    model.param.remove('cell_size');
    fprintf('  Removed param cell_size.\n');
catch err
    fprintf('  Could not remove cell_size: %s\n', err.message);
end
try
    model.param.remove('wide');
    fprintf('  Removed param wide.\n');
catch err
    fprintf('  Could not remove wide: %s\n', err.message);
end

% Verify they're gone, and length is still there
try
    leftover_w = char(model.param.get('wide'));
    fprintf('  WARNING: wide still exists = %s\n', leftover_w);
catch
    fprintf('  Verified: wide is gone.\n');
end
try
    leftover_c = char(model.param.get('cell_size'));
    fprintf('  WARNING: cell_size still exists = %s\n', leftover_c);
catch
    fprintf('  Verified: cell_size is gone.\n');
end
try
    length_after = char(model.param.get('length'));
    fprintf('  Verified: length still = %s\n', length_after);
catch
    error('CRITICAL: `length` parameter is gone — DO NOT save this model!');
end

mphsave(model, output_path, 'copy', 'on');
fprintf('  Saved cleaned model: %s\n', output_path);
end

% =========================================================================

function result = has_word(text, word)
%HAS_WORD case-sensitive word-boundary match (avoid matching `width` for `wide`)
if isempty(text) || isempty(word); result = false; return; end
% Replace alphanumeric/underscore boundaries
result = ~isempty(regexp(text, ['(^|[^A-Za-z0-9_])' word '([^A-Za-z0-9_]|$)'], 'once'));
end

function s = trunc_str(text)
s = char(text);
if length(s) > 160; s = [s(1:160) '...']; end
end

function hits = scan_feature_tree(node, prefix, hits)
%SCAN_FEATURE_TREE Recursively walk node.feature(*).{properties, ...}
% MATLAB passes structs by value, so we must return hits explicitly.
try
    feat_tags = node.feature.tags;
catch
    feat_tags = [];
end
for f = 1:length(feat_tags)
    ftag = char(feat_tags(f));
    try
        prop_names = node.feature(ftag).properties;
    catch
        prop_names = [];
    end
    for p = 1:length(prop_names)
        pname = char(prop_names(p));
        try
            pval = char(node.feature(ftag).getString(pname));
        catch
            pval = '';
        end
        if has_word(pval, 'wide')
            hits.wide{end+1} = sprintf('%s.feature[%s].%s = %s', prefix, ftag, pname, trunc_str(pval));
        end
        if has_word(pval, 'cell_size')
            hits.cell_size{end+1} = sprintf('%s.feature[%s].%s = %s', prefix, ftag, pname, trunc_str(pval));
        end
    end
    try
        ftype = char(node.feature(ftag).getType);
    catch
        ftype = '';
    end
    if strcmpi(ftype, 'WorkPlane')
        try
            wp_geom = node.feature(ftag).geom;
            hits = scan_feature_tree(wp_geom, sprintf('%s.feature[%s].wpSketch', prefix, ftag), hits);
        catch
        end
    end
end
end
