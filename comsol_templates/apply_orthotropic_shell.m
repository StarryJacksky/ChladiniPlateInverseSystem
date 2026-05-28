function status = apply_orthotropic_shell(model, theta_field_csv, forced_log) % COMSOL 6.4 Shell orthotropic 注入 / COMSOL 6.4 Shell orthotropic injection
%APPLY_ORTHOTROPIC_SHELL Configure shell.emm1 as Orthotropic with per-cell theta(x,y) rotation.
%   Uses the COMSOL 6.4 API discovered via probe_orthotropic_emm1.m + probe_rotated_cs.m:
%     - shell.emm1 directly accepts SolidModel='Orthotropic' + Evector_mat='userdef' + Evector={...}
%     - Rotated coord system uses rotationSequence (ZXZ default) + 3-element angle vector
%
%   Returns 'ok' on full success; 'fallback:isotropic_equivalent' if orthotropic
%   path fails (legacy safety net).

status = 'not_attempted';

if nargin < 3 || forced_log < 0; forced_log = 1; end

if ~exist(theta_field_csv, 'file')
    status = ['failed:theta_field_csv_not_found:' theta_field_csv];
    fprintf(forced_log, 'orthotropic_status=%s\n', status);
    return;
end

problems = strings(0);

% --- Step 1: create / update theta_interp interpolation ---
try
    if has_func(model, 'theta_interp'); model.func.remove('theta_interp'); end
    f_interp = model.func.create('theta_interp', 'Interpolation');
    f_interp.set('source', 'file');
    f_interp.set('filename', char(theta_field_csv));
    f_interp.set('struct', 'spreadsheet');
    f_interp.setIndex('funcs', 'theta_interp', 0, 0); % 可调用名 = tag 名 / Callable name = tag
    f_interp.setIndex('funcs', '1', 0, 1);
    try; f_interp.set('extrap', 'nearest'); catch; end
    try; f_interp.set('defvars', 'on'); catch; end
    try; f_interp.setIndex('argunit', 'm', 0); catch; end
    try; f_interp.setIndex('argunit', 'm', 1); catch; end
    try; f_interp.setIndex('fununit', 'rad', 0); catch; end
    fprintf(forced_log, 'theta_interp_created=%s\n', theta_field_csv);
catch err_t
    status = ['failed:theta_interp:' err_t.message];
    fprintf(forced_log, 'orthotropic_status=%s\n', status);
    return;
end

% --- Step 2: create / update Rotated coord system sys_ortho ---
sys_ortho_tag = 'sys_ortho';
try
    cs_tags = model.component('comp1').coordSystem.tags();
    for k = 1:length(cs_tags)
        if strcmp(char(cs_tags(k)), sys_ortho_tag)
            model.component('comp1').coordSystem.remove(sys_ortho_tag); break;
        end
    end
    cs = model.component('comp1').coordSystem.create(sys_ortho_tag, 'Rotated');
    % Set rotation sequence to ZXZ (default) and angle = {theta_interp, 0, 0}
    cs.set('rotationSequence', 'ZXZ');
    cs.set('angle', {'theta_interp(x,y)', '0', '0'});
    fprintf(forced_log, 'sys_ortho_created=Rotated angle_first=theta_interp(x,y)\n');
catch err_cs
    problems(end+1) = "sys_ortho:" + err_cs.message;
    sys_ortho_tag = ''; % mark failed
end

% --- Step 3: set shell.emm1 to Orthotropic with Evector/nuvector/Gvector ---
ortho_set_ok = false;
try
    em = model.physics('shell').feature('emm1');
    em.set('SolidModel', 'Orthotropic');
    fprintf(forced_log, 'emm1_SolidModel=Orthotropic\n');
    
    em.set('Evector_mat', 'userdef');
    em.set('Evector', {'mat_E1', 'mat_E2', 'mat_E_perp_z'});
    
    em.set('nuvector_mat', 'userdef');
    em.set('nuvector', {'mat_nu12', 'mat_nu23', 'mat_nu13'});
    
    em.set('Gvector_mat', 'userdef');
    em.set('Gvector', {'mat_G12', 'mat_G23', 'mat_G13'});
    
    % Bind to rotated coord system
    if ~isempty(sys_ortho_tag)
        % try multiple property names for coord system selector
        cs_bound = false;
        cand_cs_props = {'coordinateSystem', 'CoordinateSystem', 'coordsys', 'csys'};
        for ci = 1:length(cand_cs_props)
            try
                em.set(cand_cs_props{ci}, sys_ortho_tag);
                fprintf(forced_log, 'emm1_%s=%s\n', cand_cs_props{ci}, sys_ortho_tag);
                cs_bound = true; break;
            catch
            end
        end
        if ~cs_bound; problems(end+1) = "emm1_coord_bind:none_of_4_names_worked"; end
    end
    
    % Read back to confirm
    try
        rb = char(em.getString('Evector'));
        fprintf(forced_log, 'Evector_readback=%s\n', rb);
        ortho_set_ok = ~isempty(rb);
    catch
    end
catch err_em
    problems(end+1) = "emm1_orthotropic:" + err_em.message;
end

% --- Step 4: fall back to isotropic-equivalent if anything critical broke ---
if ~ortho_set_ok
    try
        % restore to Isotropic + use (E1+E2)/2 as equivalent
        em = model.physics('shell').feature('emm1');
        em.set('SolidModel', 'Isotropic');
        em.set('E_mat', 'from_mat');
        em.set('nu_mat', 'from_mat');
        model.param.set('mat_youngs_modulus_iso_equiv', '(mat_E1+mat_E2)/2');
        mat = model.component('comp1').material('mat1');
        try
            mat.propertyGroup('def').set('youngsmodulus', 'mat_youngs_modulus_iso_equiv*(1+i*eta_loss_field)');
        catch
            mat.propertyGroup('def').set('youngsmodulus', '(mat_E1+mat_E2)/2');
        end
        status = 'fallback:isotropic_equivalent';
        fprintf(forced_log, 'orthotropic_status=%s\n', status);
        return;
    catch err_fb
        problems(end+1) = "isotropic_fallback:" + err_fb.message;
        status = ['failed:' char(strjoin(problems, '|'))];
        fprintf(forced_log, 'orthotropic_status=%s\n', status);
        return;
    end
end

if isempty(problems)
    status = 'ok';
else
    status = ['partial:' char(strjoin(problems, '|'))];
end
fprintf(forced_log, 'orthotropic_status=%s\n', status);
end

function flag = has_func(model, tag)
flag = false;
try; model.func(tag); flag = true; catch; flag = false; end
end
