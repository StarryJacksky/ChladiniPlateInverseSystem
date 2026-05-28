function probe_orthotropic_api(model_path, output_log) % 探针 COMSOL Orthotropic API / Probe COMSOL Orthotropic API
%PROBE_ORTHOTROPIC_API Create an Orthotropic propertyGroup and dump its variable names / expressions.
%   Also probes Shell physics emm1 feature for elastic-material-related properties.

if nargin < 2 || isempty(output_log)
    output_log = 'data/comsol_logs/orthotropic_api_probe.log';
end

[log_dir, ~, ~] = fileparts(output_log);
if ~isempty(log_dir) && ~exist(log_dir, 'dir'); mkdir(log_dir); end
fid = fopen(output_log, 'w');
fprintf(fid, 'probe_orthotropic_api start\n');

comsol_mli_path = getenv('COMSOL_MLI_PATH'); % MLI
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
    fclose(fid);
    return;
end

% Try to enumerate all material propertyGroups for mat1
mat = [];
try
    mat = model.component('comp1').material('mat1');
    pg_tags = mat.propertyGroup.tags();
    fprintf(fid, 'existing_pg_tags=');
    for i = 1:length(pg_tags); fprintf(fid, '%s,', char(pg_tags(i))); end
    fprintf(fid, '\n');
catch err
    fprintf(fid, 'enumerate_pg_failed=%s\n', err.message);
end

% Try each candidate orthotropic type
candidate_types = {'Orthotropic', 'OrthotropicEnu_alpha', 'OrthotropicEnu', ...
                   'LinearElasticOrthotropic', 'Orthotropic_Eortho', 'OrthotropicElastic'};

for ti = 1:length(candidate_types)
    type_name = candidate_types{ti};
    pg_tag = sprintf('probe_ortho_%d', ti);
    fprintf(fid, '\n--- type=%s tag=%s ---\n', type_name, pg_tag);
    try
        % remove if exists
        existing_tags = mat.propertyGroup.tags();
        for k = 1:length(existing_tags)
            if strcmp(char(existing_tags(k)), pg_tag); mat.propertyGroup.remove(pg_tag); break; end
        end
        mat.propertyGroup.create(pg_tag, type_name);
        fprintf(fid, 'create=ok\n');
        pg = mat.propertyGroup(pg_tag);

        % Dump varName / expr / descr / param names
        try
            vn = pg.varName();
            fprintf(fid, 'varName=');
            for j = 1:length(vn); fprintf(fid, '"%s",', char(vn(j))); end
            fprintf(fid, '\n');
        catch err; fprintf(fid, 'varName_error=%s\n', err.message); end

        try
            ex = pg.expr();
            fprintf(fid, 'expr=');
            for j = 1:length(ex); fprintf(fid, '"%s",', char(ex(j))); end
            fprintf(fid, '\n');
        catch err; fprintf(fid, 'expr_error=%s\n', err.message); end

        try
            ds = pg.descr();
            fprintf(fid, 'descr=');
            for j = 1:length(ds); fprintf(fid, '"%s",', char(ds(j))); end
            fprintf(fid, '\n');
        catch err; fprintf(fid, 'descr_error=%s\n', err.message); end

        try
            ids = pg.identifier();
            fprintf(fid, 'identifier=');
            for j = 1:length(ids); fprintf(fid, '"%s",', char(ids(j))); end
            fprintf(fid, '\n');
        catch err; fprintf(fid, 'identifier_error=%s\n', err.message); end

        % Cleanup
        try; mat.propertyGroup.remove(pg_tag); catch; end
    catch err
        fprintf(fid, 'create_error=%s\n', err.message);
    end
end

% Now probe Shell physics emm1: list valid SolidModel options
fprintf(fid, '\n=== shell.emm1 probe ===\n');
try
    em = model.physics('shell').feature('emm1');
    try
        sm_cur = em.getString('SolidModel');
        fprintf(fid, 'current_SolidModel=%s\n', char(sm_cur));
    catch err; fprintf(fid, 'getString_SolidModel_failed=%s\n', err.message); end
    try
        mm_cur = em.getString('MaterialModel');
        fprintf(fid, 'current_MaterialModel=%s\n', char(mm_cur));
    catch err; fprintf(fid, 'getString_MaterialModel_failed=%s\n', err.message); end

    % Try setting various model names and see which succeed
    candidates_sm = {'Isotropic', 'Orthotropic', 'Anisotropic', 'UserDefined', 'LinearElastic'};
    for k = 1:length(candidates_sm)
        sm = candidates_sm{k};
        try
            em.set('SolidModel', sm);
            fprintf(fid, 'set_SolidModel_%s=ok\n', sm);
            % After successful set, list properties
            try
                props = em.properties();
                fprintf(fid, '  properties_count=%d\n', length(props));
                for pi = 1:length(props); fprintf(fid, '  prop_%d=%s\n', pi, char(props(pi))); end
            catch err; fprintf(fid, '  properties_error=%s\n', err.message); end
        catch err
            fprintf(fid, 'set_SolidModel_%s_FAILED=%s\n', sm, err.message);
        end
    end

    % Reset SolidModel
    try; em.set('SolidModel', 'Isotropic'); catch; end
catch err
    fprintf(fid, 'shell_emm1_error=%s\n', err.message);
end

% Probe what propertyGroup types are available in Material Library
fprintf(fid, '\n=== material library probe (best-effort) ===\n');
try
    % Try to list all propertyGroup type registrations via Java reflection
    % This is a best-effort attempt
    cls = mat.propertyGroup.getClass();
    fprintf(fid, 'propertyGroup_class=%s\n', char(cls.getName()));
catch err
    fprintf(fid, 'pg_reflection_failed=%s\n', err.message);
end

fprintf(fid, '\nprobe_done\n');
fclose(fid);
fprintf('orthotropic probe complete, log=%s\n', output_log);
end
