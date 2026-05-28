function probe_orthotropic_emm1(model_path, output_log) % 探针 shell.emm1 上的 Orthotropic 设置流程 / Probe Orthotropic setup on shell.emm1

if nargin < 2 || isempty(output_log)
    output_log = 'data/comsol_logs/orthotropic_emm1_probe.log';
end

[log_dir, ~, ~] = fileparts(output_log);
if ~isempty(log_dir) && ~exist(log_dir, 'dir'); mkdir(log_dir); end
fid = fopen(output_log, 'w');
fprintf(fid, 'probe_orthotropic_emm1 start\n');

comsol_mli_path = getenv('COMSOL_MLI_PATH');
if ~isempty(comsol_mli_path) && exist(comsol_mli_path, 'dir')
    addpath(comsol_mli_path);
elseif exist('/Applications/COMSOL64/Multiphysics/mli', 'dir')
    addpath('/Applications/COMSOL64/Multiphysics/mli');
end

import com.comsol.model.*
import com.comsol.model.util.*

try
    server_host = getenv('COMSOL_SERVER_HOST'); if isempty(server_host); server_host = '127.0.0.1'; end
    server_port = str2double(getenv('COMSOL_SERVER_PORT')); if isnan(server_port) || server_port <= 0; server_port = 2036; end
    server_user = getenv('COMSOL_SERVER_USER'); server_password = getenv('COMSOL_SERVER_PASSWORD');
    if ~isempty(server_user)
        mphstart(char(server_host), server_port, server_user, server_password);
    else
        mphstart(server_port);
    end
    fprintf(fid, 'mphstart_ok\n');
catch err_ms
    if isempty(strfind(err_ms.message, 'already connected'))
        fprintf(fid, 'mphstart_warn=%s\n', err_ms.message);
    end
end

try
    model = mphload(model_path);
    fprintf(fid, 'model_loaded=%s\n', model_path);
catch err
    fprintf(fid, 'model_load_error=%s\n', err.message);
    fclose(fid); return;
end

em = model.physics('shell').feature('emm1');

% --- Phase A: enumerate valid values for *_mat options ---
fprintf(fid, '\n=== Phase A: probe Evector_mat / nuvector_mat / Gvector_mat / D_mat ---\n');
candidate_mat_values = {'userdef', 'from_mat', 'fromMaterial', 'from_material'};
test_props = {'Evector_mat', 'nuvector_mat', 'Gvector_mat', 'D_mat', 'E_mat', 'nu_mat'};
for pi = 1:length(test_props)
    prop = test_props{pi};
    try
        v = em.getString(prop);
        fprintf(fid, '%s_current=%s\n', prop, char(v));
    catch err
        fprintf(fid, '%s_getString_FAILED=%s\n', prop, err.message);
    end
    for vi = 1:length(candidate_mat_values)
        val = candidate_mat_values{vi};
        try
            em.set(prop, val);
            fprintf(fid, 'set_%s_%s=ok\n', prop, val);
        catch err
            % Just record allowed-values hint from message
            msg = err.message;
            % Truncate long stack traces
            if length(msg) > 250; msg = msg(1:250); end
            fprintf(fid, 'set_%s_%s_FAILED=%s\n', prop, val, msg);
        end
    end
end

% --- Phase B: set SolidModel=Orthotropic and try to populate Evector ---
fprintf(fid, '\n=== Phase B: SolidModel=Orthotropic + Evector population ---\n');
try
    em.set('SolidModel', 'Orthotropic');
    fprintf(fid, 'SolidModel=Orthotropic_ok\n');
catch err; fprintf(fid, 'SolidModel_FAILED=%s\n', err.message); end

% Now try Evector_mat = 'userdef' followed by setting Evector
try; em.set('Evector_mat', 'userdef'); fprintf(fid, 'Evector_mat=userdef_ok\n'); catch err; fprintf(fid, 'Evector_mat_userdef_FAILED=%s\n', err.message); end
% try cell array
try
    em.set('Evector', {'2.5e9', '1e9', '1e9'});
    fprintf(fid, 'set_Evector_cell_ok\n');
    val = em.getString('Evector');
    fprintf(fid, 'Evector_readback=%s\n', char(val));
catch err
    msg = err.message; if length(msg) > 250; msg = msg(1:250); end
    fprintf(fid, 'set_Evector_cell_FAILED=%s\n', msg);
end

try; em.set('nuvector_mat', 'userdef'); catch; end
try; em.set('nuvector', {'0.35', '0.35', '0.35'}); fprintf(fid, 'set_nuvector_ok\n');
catch err; msg = err.message; if length(msg) > 250; msg = msg(1:250); end; fprintf(fid, 'set_nuvector_FAILED=%s\n', msg); end

try; em.set('Gvector_mat', 'userdef'); catch; end
try; em.set('Gvector', {'9e8', '9e8', '9e8'}); fprintf(fid, 'set_Gvector_ok\n');
catch err; msg = err.message; if length(msg) > 250; msg = msg(1:250); end; fprintf(fid, 'set_Gvector_FAILED=%s\n', msg); end

% --- Phase C: probe shellsys coordinate system ---
fprintf(fid, '\n=== Phase C: shellsys coord system probe ---\n');
try
    cs = model.component('comp1').coordSystem('shellsys');
    fprintf(fid, 'shellsys_class=%s\n', char(cs.getClass().getName()));
    try
        props = cs.properties();
        fprintf(fid, 'shellsys_property_count=%d\n', length(props));
        for ki = 1:min(length(props), 50)
            try
                pname = char(props(ki));
                try
                    pval = char(cs.getString(pname));
                catch
                    pval = '<unreadable>';
                end
                fprintf(fid, '  %s=%s\n', pname, pval);
            catch; end
        end
    catch err; fprintf(fid, 'props_error=%s\n', err.message); end
catch err
    fprintf(fid, 'shellsys_error=%s\n', err.message);
end

% --- Phase D: try various ways to set shellsys rotation angle from theta_interp ---
fprintf(fid, '\n=== Phase D: shellsys rotation attempts ---\n');
% Make sure theta_interp exists first (create a dummy if needed)
try
    if ~has_func(model, 'theta_interp_test')
        f = model.func.create('theta_interp_test', 'Analytic');
        f.set('expr', '0.0');
        f.set('args', {'x', 'y'});
    end
catch err; fprintf(fid, 'create_dummy_theta_FAILED=%s\n', err.message); end

cs = model.component('comp1').coordSystem('shellsys');
% Try various 'base' options
candidate_base = {'rotation', 'manualvectors', 'simrot', 'rotated', 'plane'};
for bi = 1:length(candidate_base)
    b = candidate_base{bi};
    try
        cs.set('base', b);
        fprintf(fid, 'shellsys_base=%s_ok\n', b);
    catch err
        msg = err.message; if length(msg) > 250; msg = msg(1:250); end
        fprintf(fid, 'shellsys_base=%s_FAILED=%s\n', b, msg);
    end
end

% Try set rot or rotationAngle
rot_props = {'rot', 'rotationAngle', 'theta', 'angle'};
for ri = 1:length(rot_props)
    p = rot_props{ri};
    try
        cs.set(p, 'theta_interp_test(x,y)');
        fprintf(fid, 'shellsys_%s=ok\n', p);
        try; val = char(cs.getString(p)); fprintf(fid, '  readback=%s\n', val); catch; end
    catch err
        msg = err.message; if length(msg) > 250; msg = msg(1:250); end
        fprintf(fid, 'shellsys_%s_FAILED=%s\n', p, msg);
    end
end

fprintf(fid, '\nprobe_done\n');
fclose(fid);
fprintf('probe complete log=%s\n', output_log);
end

function flag = has_func(model, tag)
flag = false;
try; model.func(tag); flag = true; catch; flag = false; end
end
