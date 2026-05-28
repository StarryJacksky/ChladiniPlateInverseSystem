function probe_rotated_cs(model_path, output_log)

if nargin < 2 || isempty(output_log); output_log = 'data/comsol_logs/rotated_cs_probe.log'; end
[log_dir, ~, ~] = fileparts(output_log);
if ~isempty(log_dir) && ~exist(log_dir, 'dir'); mkdir(log_dir); end
fid = fopen(output_log, 'w');

comsol_mli_path = getenv('COMSOL_MLI_PATH');
if ~isempty(comsol_mli_path) && exist(comsol_mli_path, 'dir'); addpath(comsol_mli_path);
elseif exist('/Applications/COMSOL64/Multiphysics/mli', 'dir'); addpath('/Applications/COMSOL64/Multiphysics/mli'); end
import com.comsol.model.*
import com.comsol.model.util.*

try
    server_host = getenv('COMSOL_SERVER_HOST'); if isempty(server_host); server_host = '127.0.0.1'; end
    server_port = str2double(getenv('COMSOL_SERVER_PORT')); if isnan(server_port) || server_port <= 0; server_port = 2036; end
    server_user = getenv('COMSOL_SERVER_USER'); server_password = getenv('COMSOL_SERVER_PASSWORD');
    if ~isempty(server_user); mphstart(char(server_host), server_port, server_user, server_password);
    else; mphstart(server_port); end
    fprintf(fid, 'mphstart_ok\n');
catch err_ms
    if isempty(strfind(err_ms.message, 'already connected')); fprintf(fid, 'mphstart_warn=%s\n', err_ms.message); end
end

try; model = mphload(model_path); catch err; fprintf(fid, 'model_load_error=%s\n', err.message); fclose(fid); return; end
fprintf(fid, 'model_loaded\n');

% List all existing coord systems
fprintf(fid, '\n=== existing coordSystem tags ===\n');
try
    cs_tags = model.component('comp1').coordSystem.tags();
    for k = 1:length(cs_tags); fprintf(fid, '  %s\n', char(cs_tags(k))); end
catch err; fprintf(fid, 'enumerate_cs_failed=%s\n', err.message); end

% Try creating different coord system types
types_to_try = {'Rotated', 'BaseVectorSystem', 'CartesianSystem', 'Cylindrical', 'Spherical'};
for ti = 1:length(types_to_try)
    typ = types_to_try{ti};
    tag = sprintf('probe_cs_%d', ti);
    fprintf(fid, '\n--- type=%s tag=%s ---\n', typ, tag);
    try
        % Remove if exists
        cs_tags = model.component('comp1').coordSystem.tags();
        for k = 1:length(cs_tags)
            if strcmp(char(cs_tags(k)), tag); model.component('comp1').coordSystem.remove(tag); break; end
        end
        cs = model.component('comp1').coordSystem.create(tag, typ);
        fprintf(fid, 'create=ok\n');
        % List properties
        try
            props = cs.properties();
            fprintf(fid, 'props_count=%d\n', length(props));
            for pi = 1:length(props)
                pname = char(props(pi));
                try; pval = char(cs.getString(pname)); catch; pval = '<unreadable>'; end
                fprintf(fid, '  %s=%s\n', pname, pval);
            end
        catch err; fprintf(fid, 'props_err=%s\n', err.message); end
        try; model.component('comp1').coordSystem.remove(tag); catch; end
    catch err; fprintf(fid, 'create_failed=%s\n', err.message); end
end

% Specifically attempt full Rotated CS setup with sample θ
fprintf(fid, '\n=== full Rotated CS workflow ===\n');
try
    cs_tags = model.component('comp1').coordSystem.tags();
    for k = 1:length(cs_tags); if strcmp(char(cs_tags(k)), 'rot_test'); model.component('comp1').coordSystem.remove('rot_test'); break; end; end
    cs = model.component('comp1').coordSystem.create('rot_test', 'Rotated');
    % Try all known property names for rotation angles
    cands_angle = {'theta', 'thetaXY', 'rot1', 'rot2', 'rot3', 'phi', 'psi', 'eulerXYZ', 'eulerAngles'};
    for ci = 1:length(cands_angle)
        try
            cs.set(cands_angle{ci}, '0.5');
            fprintf(fid, 'rot_set_%s=ok\n', cands_angle{ci});
            try; rb = char(cs.getString(cands_angle{ci})); fprintf(fid, '  readback=%s\n', rb); catch; end
        catch err; msg = err.message; if length(msg)>200; msg=msg(1:200); end; fprintf(fid, 'rot_set_%s_FAILED=%s\n', cands_angle{ci}, msg); end
    end
catch err; fprintf(fid, 'rot_workflow_FAILED=%s\n', err.message); end

% Cleanup
try; model.component('comp1').coordSystem.remove('rot_test'); catch; end

fprintf(fid, '\nprobe_done\n');
fclose(fid);
end
