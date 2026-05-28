function probe_geometry_extents(model_path, output_log) % 探测 .mph 几何原语 / 工作平面尺寸 / Probe geometry primitives and workplane extents in .mph
%PROBE_GEOMETRY_EXTENTS Dump every geometry feature's size / sketch extent
%   to diagnose discrepancies between "10x10" displayed in COMSOL GUI vs the
%   actual 150x150 mm physical domain seen in exported mode_xy.csv.
%
% Usage from MATLAB:
%   probe_geometry_extents('comsol_templates/Chladni_15x15_bound.mph', ...
%                          'reports/geom_probe.log')

if nargin < 2 % 默认日志位置 / Default log location
    output_log = fullfile(pwd, 'reports', 'geom_probe.log');
end
[log_dir, ~, ~] = fileparts(output_log);
if ~isempty(log_dir) && ~exist(log_dir, 'dir')
    mkdir(log_dir);
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
log_fid = fopen(output_log, 'w');
cleanup = onCleanup(@() fclose(log_fid));

fprintf(log_fid, '=== Geometry-extent probe ===\n');
fprintf(log_fid, 'model_path=%s\n', model_path);
fprintf(log_fid, 'comsol_version=%s\n\n', char(mphversion));

% --- Walk every component / geometry / feature ---
comp_tags = model.component.tags;
for k = 1:length(comp_tags)
    comp_tag = char(comp_tags(k));
    fprintf(log_fid, 'component[%s]\n', comp_tag);

    try
        geom_tags = model.component(comp_tag).geom.tags;
    catch
        fprintf(log_fid, '  (no geom on %s)\n', comp_tag);
        continue;
    end

    for g = 1:length(geom_tags)
        geom_tag = char(geom_tags(g));
        fprintf(log_fid, '  geom[%s]\n', geom_tag);

        % Bounding box of the resolved geometry
        try
            bb = mphgetbbox(model, geom_tag);
            % bb is [xmin xmax ymin ymax zmin zmax] for 3D, [xmin xmax ymin ymax] for 2D
            if numel(bb) >= 6
                fprintf(log_fid, '    bbox: x=[%.6g, %.6g]  y=[%.6g, %.6g]  z=[%.6g, %.6g]  (m)\n', ...
                        bb(1), bb(2), bb(3), bb(4), bb(5), bb(6));
                fprintf(log_fid, '    bbox: x=[%.2f, %.2f]  y=[%.2f, %.2f]  z=[%.2f, %.2f]  (mm)\n', ...
                        bb(1)*1000, bb(2)*1000, bb(3)*1000, bb(4)*1000, bb(5)*1000, bb(6)*1000);
            elseif numel(bb) >= 4
                fprintf(log_fid, '    bbox: x=[%.6g, %.6g]  y=[%.6g, %.6g]  (m)\n', ...
                        bb(1), bb(2), bb(3), bb(4));
                fprintf(log_fid, '    bbox: x=[%.2f, %.2f]  y=[%.2f, %.2f]  (mm)\n', ...
                        bb(1)*1000, bb(2)*1000, bb(3)*1000, bb(4)*1000);
            end
        catch err_bb
            fprintf(log_fid, '    ERROR bbox: %s\n', err_bb.message);
        end

        % Length unit
        try
            lu = char(model.component(comp_tag).geom(geom_tag).lengthUnit);
            fprintf(log_fid, '    lengthUnit=%s\n', lu);
        catch
        end

        % Walk geometry features (sq, r, blk, wp, ext, etc.)
        try
            feat_tags = model.component(comp_tag).geom(geom_tag).feature.tags;
        catch
            feat_tags = [];
        end
        for f = 1:length(feat_tags)
            ftag = char(feat_tags(f));
            try
                ftype = char(model.component(comp_tag).geom(geom_tag).feature(ftag).getType);
            catch
                ftype = '?';
            end
            fprintf(log_fid, '    feature[%s] type=%s\n', ftag, ftype);

            % Dump every property of this feature (size, pos, dist, etc.)
            try
                prop_names = model.component(comp_tag).geom(geom_tag).feature(ftag).properties;
                for p = 1:length(prop_names)
                    pname = char(prop_names(p));
                    try
                        pval = model.component(comp_tag).geom(geom_tag).feature(ftag).getString(pname);
                        if ischar(pval) || isa(pval, 'java.lang.String')
                            pval_str = char(pval);
                        else
                            pval_str = mat2str(pval);
                        end
                    catch
                        try
                            pval = model.component(comp_tag).geom(geom_tag).feature(ftag).getDouble(pname);
                            pval_str = num2str(pval);
                        catch
                            pval_str = '?';
                        end
                    end
                    if length(pval_str) > 120; pval_str = [pval_str(1:120) '...']; end
                    fprintf(log_fid, '      .%s = %s\n', pname, pval_str);
                end
            catch err_p
                fprintf(log_fid, '      ERROR properties: %s\n', err_p.message);
            end

            % If this is a work plane (type=='WorkPlane'), recurse into its sketch
            if strcmpi(ftype, 'WorkPlane')
                try
                    wp_geom = model.component(comp_tag).geom(geom_tag).feature(ftag).geom;
                    wp_feat_tags = wp_geom.feature.tags;
                    fprintf(log_fid, '      [WorkPlane sketch features]\n');
                    for wf = 1:length(wp_feat_tags)
                        wftag = char(wp_feat_tags(wf));
                        try
                            wftype = char(wp_geom.feature(wftag).getType);
                        catch
                            wftype = '?';
                        end
                        fprintf(log_fid, '      wp.feature[%s] type=%s\n', wftag, wftype);
                        try
                            wp_props = wp_geom.feature(wftag).properties;
                            for wp_p = 1:length(wp_props)
                                wp_pname = char(wp_props(wp_p));
                                try
                                    wp_pval = char(wp_geom.feature(wftag).getString(wp_pname));
                                catch
                                    wp_pval = '?';
                                end
                                if length(wp_pval) > 120; wp_pval = [wp_pval(1:120) '...']; end
                                fprintf(log_fid, '        .%s = %s\n', wp_pname, wp_pval);
                            end
                        catch
                        end
                    end
                catch err_wp
                    fprintf(log_fid, '      ERROR walking workplane sketch: %s\n', err_wp.message);
                end
            end
        end
    end
end

% --- Also dump all geometry-related global parameters ---
fprintf(log_fid, '\n--- Geometry-related global parameters ---\n');
try
    pnames = model.param.varnames;
    for k = 1:length(pnames)
        pname = char(pnames(k));
        plow = lower(pname);
        if contains(plow, 'len') || contains(plow, 'size') || contains(plow, 'width') || ...
           contains(plow, 'plate') || contains(plow, 'l_') || contains(plow, 'thickness') || ...
           contains(plow, 'edge') || contains(plow, 'side') || contains(plow, 'sq') || ...
           contains(plow, 'wide') || contains(plow, 'cell')
            try
                pval = char(model.param.get(pname));
            catch
                pval = '?';
            end
            fprintf(log_fid, '  %s = %s\n', pname, pval);
        end
    end
catch err_pr
    fprintf(log_fid, 'ERROR scanning params: %s\n', err_pr.message);
end

% --- Search ALL parameter expressions for references to cell_size / wide ---
fprintf(log_fid, '\n--- Parameters referencing cell_size / wide / length ---\n');
try
    pnames = model.param.varnames;
    for k = 1:length(pnames)
        pname = char(pnames(k));
        try
            pval = char(model.param.get(pname));
        catch
            pval = '?';
        end
        if contains(pval, 'cell_size') || contains(pval, 'wide') || contains(pval, 'length') || ...
           contains(pval, 'grid_size')
            fprintf(log_fid, '  %s = %s\n', pname, pval);
        end
    end
catch
end

% --- Dump ALL model variables (any component) referencing cell_size / wide ---
fprintf(log_fid, '\n--- Component variables referencing cell_size / wide ---\n');
try
    for k = 1:length(comp_tags)
        comp_tag = char(comp_tags(k));
        try
            var_tags = model.component(comp_tag).variable.tags;
        catch
            continue;
        end
        for v = 1:length(var_tags)
            vtag = char(var_tags(v));
            try
                var_names = model.component(comp_tag).variable(vtag).varnames;
            catch
                continue;
            end
            for n = 1:length(var_names)
                vname = char(var_names(n));
                try
                    vexpr = char(model.component(comp_tag).variable(vtag).get(vname));
                catch
                    vexpr = '?';
                end
                if contains(vexpr, 'cell_size') || contains(vexpr, 'wide')
                    short = vexpr;
                    if length(short) > 200; short = [short(1:200) '...']; end
                    fprintf(log_fid, '  [%s.%s] %s = %s\n', comp_tag, vtag, vname, short);
                end
            end
        end
    end
catch
end

fprintf(log_fid, '\n=== probe complete ===\n');
fprintf('Geometry probe log written: %s\n', output_log);
end
