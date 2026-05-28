function probe_model_structure(model_path, output_log) % 探测 .mph 模型物理 / 材料结构 / Probe .mph model physics / material structure
%PROBE_MODEL_STRUCTURE Inspect tags, material model, propertyGroups, coordinate systems.
%   写入诊断信息到 output_log 文本文件 / Write diagnostics to output_log text file.

if nargin < 2 % 检查默认日志 / Default log
    output_log = fullfile(pwd, 'probe_model_log.txt'); % 默认 / Default
end % 结束默认日志 / End default

comsol_mli_path = getenv('COMSOL_MLI_PATH'); % MLI / MLI
if ~isempty(comsol_mli_path) && exist(comsol_mli_path, 'dir')
    addpath(comsol_mli_path);
elseif exist('/Applications/COMSOL64/Multiphysics/mli', 'dir')
    addpath('/Applications/COMSOL64/Multiphysics/mli');
end

import com.comsol.model.*
import com.comsol.model.util.*

try
    server_user = getenv('COMSOL_SERVER_USER');
    server_password = getenv('COMSOL_SERVER_PASSWORD');
    server_host = getenv('COMSOL_SERVER_HOST');
    if isempty(server_host); server_host = '127.0.0.1'; end
    server_port = str2double(getenv('COMSOL_SERVER_PORT'));
    if isnan(server_port) || server_port <= 0; server_port = 2036; end
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
fprintf(log_fid, '=== MOSAIC-Z COMSOL model probe ===\n');
fprintf(log_fid, 'model_path=%s\n', model_path);
fprintf(log_fid, 'comsol_version=%s\n', char(mphversion));

% --- Components ---
fprintf(log_fid, '\n--- Components ---\n');
try
    comp_tags = model.component.tags;
    for k = 1:length(comp_tags)
        fprintf(log_fid, 'component[%d]=%s\n', k, char(comp_tags(k)));
    end
catch err_c
    fprintf(log_fid, 'ERROR reading components: %s\n', err_c.message);
end

% --- Physics ---
fprintf(log_fid, '\n--- Physics interfaces ---\n');
try
    for k = 1:length(comp_tags)
        comp_tag = char(comp_tags(k));
        phys_tags = model.component(comp_tag).physics.tags;
        for j = 1:length(phys_tags)
            phys_tag = char(phys_tags(j));
            try
                ptype = char(model.component(comp_tag).physics(phys_tag).getType);
            catch
                ptype = '?';
            end
            fprintf(log_fid, 'physics[%s.%s] type=%s\n', comp_tag, phys_tag, ptype);
            try
                feat_tags = model.component(comp_tag).physics(phys_tag).feature.tags;
                for f = 1:length(feat_tags)
                    ftag = char(feat_tags(f));
                    try
                        ftype = char(model.component(comp_tag).physics(phys_tag).feature(ftag).getType);
                    catch
                        ftype = '?';
                    end
                    fprintf(log_fid, '  feature[%s] type=%s\n', ftag, ftype);
                end
            catch err_f
                fprintf(log_fid, '  ERROR feature scan: %s\n', err_f.message);
            end
        end
    end
catch err_p
    fprintf(log_fid, 'ERROR reading physics: %s\n', err_p.message);
end

% --- Materials ---
fprintf(log_fid, '\n--- Materials ---\n');
try
    for k = 1:length(comp_tags)
        comp_tag = char(comp_tags(k));
        mat_tags = model.component(comp_tag).material.tags;
        for j = 1:length(mat_tags)
            mat_tag = char(mat_tags(j));
            fprintf(log_fid, 'material[%s.%s]\n', comp_tag, mat_tag);
            try
                pg_tags = model.component(comp_tag).material(mat_tag).propertyGroup.tags;
                for p = 1:length(pg_tags)
                    pg_tag = char(pg_tags(p));
                    fprintf(log_fid, '  propertyGroup[%s]\n', pg_tag);
                    try
                        prop_names = model.component(comp_tag).material(mat_tag).propertyGroup(pg_tag).propertyNames;
                        for n = 1:length(prop_names)
                            pname = char(prop_names(n));
                            try
                                pval = char(model.component(comp_tag).material(mat_tag).propertyGroup(pg_tag).getString(pname));
                            catch
                                pval = '?';
                            end
                            if length(pval) > 80; pval = [pval(1:80) '...']; end
                            fprintf(log_fid, '    %s = %s\n', pname, pval);
                        end
                    catch err_pn
                        fprintf(log_fid, '    ERROR propNames: %s\n', err_pn.message);
                    end
                end
            catch err_pg
                fprintf(log_fid, '  ERROR pg scan: %s\n', err_pg.message);
            end
        end
    end
catch err_m
    fprintf(log_fid, 'ERROR reading materials: %s\n', err_m.message);
end

% --- Coordinate systems ---
fprintf(log_fid, '\n--- Coordinate systems ---\n');
try
    for k = 1:length(comp_tags)
        comp_tag = char(comp_tags(k));
        try
            cs_tags = model.component(comp_tag).coordSystem.tags;
            for j = 1:length(cs_tags)
                cs_tag = char(cs_tags(j));
                try
                    cs_type = char(model.component(comp_tag).coordSystem(cs_tag).getType);
                catch
                    cs_type = '?';
                end
                fprintf(log_fid, 'coordSystem[%s.%s] type=%s\n', comp_tag, cs_tag, cs_type);
            end
        catch
            fprintf(log_fid, '  (no coordSystem on %s)\n', comp_tag);
        end
    end
catch err_cs
    fprintf(log_fid, 'ERROR reading coord systems: %s\n', err_cs.message);
end

% --- Functions ---
fprintf(log_fid, '\n--- Global functions ---\n');
try
    func_tags = model.func.tags;
    for k = 1:length(func_tags)
        ftag = char(func_tags(k));
        try
            ftype = char(model.func(ftag).getType);
        catch
            ftype = '?';
        end
        fprintf(log_fid, 'func[%s] type=%s\n', ftag, ftype);
    end
catch
    fprintf(log_fid, '  (no global functions)\n');
end

% --- Parameters (mat_* and stiffness/shear) ---
fprintf(log_fid, '\n--- Material-related parameters ---\n');
try
    param_names = model.param.varnames;
    for k = 1:length(param_names)
        pname = char(param_names(k));
        if startsWith(pname, 'mat_') || contains(lower(pname), 'stiff') || contains(lower(pname), 'shear') || contains(lower(pname), 'orthotropic')
            try
                pval = char(model.param.get(pname));
            catch
                pval = '?';
            end
            fprintf(log_fid, '  %s = %s\n', pname, pval);
        end
    end
catch err_pr
    fprintf(log_fid, 'ERROR param: %s\n', err_pr.message);
end

fprintf(log_fid, '\n=== probe complete ===\n');
fclose(log_fid);
fprintf('Probe log written: %s\n', output_log);
end
