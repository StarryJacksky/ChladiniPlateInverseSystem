function run_chladni_eigenfrequency_orthotropic(model_path, candidate_dir, export_dir, n_modes, freq_lower_hz) % COMSOL eigenfrequency + orthotropic / COMSOL eigenfrequency + orthotropic
%RUN_CHLADNI_EIGENFREQUENCY_ORTHOTROPIC Compute first n_modes eigenfrequencies and mode shapes,
%   honouring an orthotropic shell setup if theta_field.csv is present.
%
%   Inputs:
%     model_path      Path to bound .mph
%     candidate_dir   Directory with H.csv, theta_field.csv (optional), material_parameters.csv, support_parameters.csv, comsol_parameters.csv
%     export_dir      Output directory (eigenfrequencies.csv + eigenmode_<k>.csv + summary log)
%     n_modes         Number of modes to extract (default 30)
%     freq_lower_hz   Lower bound for search (default 10 Hz)

if nargin < 4 || isempty(n_modes); n_modes = 30; end
if nargin < 5 || isempty(freq_lower_hz); freq_lower_hz = 10.0; end

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
catch err
    if ~contains(err.message, 'already') && ~contains(err.message, '已')
        rethrow(err);
    end
end

model = mphload(model_path);
if ~exist(export_dir, 'dir'); mkdir(export_dir); end

eig_log_path = fullfile(export_dir, 'eigenfrequency_summary.txt');
eig_log = fopen(eig_log_path, 'w');
fprintf(eig_log, 'MOSAIC-Z eigenfrequency summary (orthotropic-capable)\n');
fprintf(eig_log, 'candidate_dir=%s\n', candidate_dir);
fprintf(eig_log, 'n_modes=%d freq_lower_hz=%.6g\n', n_modes, freq_lower_hz);

apply_parameter_file(model, fullfile(candidate_dir, 'comsol_parameters.csv'), true, eig_log);
apply_parameter_file(model, fullfile(candidate_dir, 'material_parameters.csv'), false, eig_log);
apply_parameter_file(model, fullfile(candidate_dir, 'design_variable_parameters.csv'), false, eig_log);

support = read_optional_table(fullfile(candidate_dir, 'support_parameters.csv'));
if ~isempty(support) && height(support) >= 1
    model.param.set('support_center_x', sprintf('%.12g[mm]', support.center_x_mm(1)));
    model.param.set('support_center_y', sprintf('%.12g[mm]', support.center_y_mm(1)));
    model.param.set('support_clamp_radius', sprintf('%.12g[mm]', support.clamp_radius_mm(1)));
    fprintf(eig_log, 'support=%.12g,%.12g,%.12g\n', support.center_x_mm(1), support.center_y_mm(1), support.clamp_radius_mm(1));
end

theta_field_path = fullfile(candidate_dir, 'theta_field.csv');
orthotropic_status = 'disabled';
if exist(theta_field_path, 'file')
    fprintf(eig_log, 'theta_field_csv=%s\n', theta_field_path);
    orthotropic_status = apply_orthotropic_shell(model, theta_field_path, eig_log);
end
fprintf(eig_log, 'orthotropic_final_status=%s\n', orthotropic_status);

% Eigenfrequency study
study_status = try_run_eigenfrequency_study(model, n_modes, freq_lower_hz);
fprintf(eig_log, 'study_status=%s\n', study_status);
if ~strcmp(study_status, 'ok')
    fclose(eig_log);
    error('COMSOL eigenfrequency study failed: %s', study_status);
end

% Extract eigenfrequencies via mphglobal
dataset_tag = 'dset1';
try
    datasets = model.result.dataset.tags;
    dataset_tag = char(datasets(end));
catch; end

try
    freqs = mphglobal(model, 'freq', 'dataset', dataset_tag);
    freqs = real(freqs);
    fprintf(eig_log, 'eigenfreqs_extracted=%d\n', length(freqs));
catch err
    fprintf(eig_log, 'eigenfreqs_extraction_failed=%s\n', err.message);
    fclose(eig_log);
    error('Failed to extract eigenfrequencies: %s', err.message);
end

% Save eigenfrequencies
freq_csv = fullfile(export_dir, 'eigenfrequencies.csv');
ff = fopen(freq_csv, 'w');
fprintf(ff, 'mode_index,frequency_hz\n');
for k = 1:length(freqs)
    fprintf(ff, '%d,%.12g\n', k, freqs(k));
end
fclose(ff);

% Extract mode shapes (shell.w) at each eigenfrequency on a uniform sampling grid
n_extract = min(length(freqs), n_modes);
fprintf(eig_log, 'extracting_mode_shapes=%d\n', n_extract);
% Get all mesh nodes once
try
    data0 = mpheval(model, {'x', 'y', 'real(shell.w)', 'imag(shell.w)'}, 'dataset', dataset_tag, 'edim', 2, 'solnum', 1);
catch err
    fprintf(eig_log, 'mpheval_failed=%s\n', err.message);
    fclose(eig_log);
    error('Failed to evaluate mode shapes: %s', err.message);
end
x = data0.d1(:);
y = data0.d2(:);
n_pts = numel(x);
xy_csv = fullfile(export_dir, 'mode_xy.csv');
fxy = fopen(xy_csv, 'w'); fprintf(fxy, 'x,y\n');
for p = 1:n_pts; fprintf(fxy, '%.12g,%.12g\n', x(p), y(p)); end
fclose(fxy);

% Each mode: extract via solnum (eigenfrequency uses solnum for mode selection)
for k = 1:n_extract
    try
        dk = mpheval(model, {'real(shell.w)', 'imag(shell.w)'}, 'dataset', dataset_tag, 'edim', 2, 'solnum', k);
        wr = dk.d1(:); wi = dk.d2(:);
        mode_csv = fullfile(export_dir, sprintf('mode_%03d.csv', k));
        fm = fopen(mode_csv, 'w');
        fprintf(fm, 'w_real,w_imag\n');
        for p = 1:n_pts
            fprintf(fm, '%.12g,%.12g\n', wr(p), wi(p));
        end
        fclose(fm);
    catch err
        fprintf(eig_log, 'mode_%d_extract_failed=%s\n', k, err.message);
    end
end

fprintf(eig_log, 'mode_extraction_done=%d\n', n_extract);

% Render native COMSOL PNG previews (Image2D export of an Amplitude surface plot).
% Frontend prefers these when present; Python fallback renders grayscale + nodal overlay
% from mode_XXX.csv when they are missing.
preview_dir = fullfile(export_dir, 'previews');
if ~exist(preview_dir, 'dir'); mkdir(preview_dir); end
try
    fprintf(eig_log, 'native_previews=start n=%d\n', n_extract);
    pg_tag = 'pg_mosaic_eig_native';
    surf_tag = 'surf_mosaic_eig_native';
    img_tag = 'img_mosaic_eig_native';
    try; model.result.remove(pg_tag); catch; end
    try; model.result.export.remove(img_tag); catch; end
    pg = model.result.create(pg_tag, 'PlotGroup2D');
    pg.set('data', dataset_tag);
    try; pg.set('titletype', 'none'); catch; end
    surf = pg.create(surf_tag, 'Surface');
    surf.set('expr', 'abs(shell.w)');
    try; surf.set('descr', 'Sand prediction |shell.w|'); catch; end
    try; surf.set('colortable', 'RainbowLight'); catch; end
    try; surf.set('resolution', 'normal'); catch; end
    try; surf.set('smooth', 'internal'); catch; end
    img = model.result.export.create(img_tag, 'Image2D');
    img.set('plotgroup', pg_tag);
    try; img.set('size', '600,600'); catch; end
    try; img.set('antialias', 'on'); catch; end
    try; img.set('background', 'current'); catch; end
    try; img.set('printlegend', 'on'); catch; end
    for k = 1:n_extract
        try
            % Eigenfrequency dataset: select mode via solnum / looplevel (both tolerated).
            try; pg.set('solnum', k); catch; end
            try; pg.set('looplevel', k); catch; end
            png_path = fullfile(preview_dir, sprintf('mode_%02d.png', k));
            img.set('filename', png_path);
            img.run;
        catch err
            fprintf(eig_log, 'native_preview_failed_mode=%d msg=%s\n', k, err.message);
        end
    end
    fprintf(eig_log, 'native_previews=done\n');
catch err
    fprintf(eig_log, 'native_preview_setup_failed=%s\n', err.message);
end

mphsave(model, fullfile(export_dir, 'last_eigenfrequency_model.mph'), 'copy', 'on');
fclose(eig_log);
end

% ====== helpers ======
function table_data = read_optional_table(path)
if exist(path, 'file')
    table_data = readtable(path, 'TextType', 'string', 'VariableNamingRule', 'preserve');
else
    table_data = [];
end
end

function apply_parameter_file(model, path, values_are_mm, log_fid)
if ~exist(path, 'file')
    fprintf(log_fid, 'missing_parameter_file=%s\n', path);
    return;
end
parameters = readtable(path, 'TextType', 'string', 'VariableNamingRule', 'preserve');
for row = 1:height(parameters)
    name = char(string(parameters{row, 1}));
    value = parameters{row, 2};
    if values_are_mm
        model.param.set(name, sprintf('%.12g[mm]', value));
    else
        unit = char(string(parameters{row, 3}));
        if strcmp(unit, '1')
            model.param.set(name, sprintf('%.12g', value));
        else
            model.param.set(name, sprintf('%.12g[%s]', value, unit));
        end
    end
end
fprintf(log_fid, 'applied_parameter_file=%s rows=%d\n', path, height(parameters));
end

function exists_flag = has_feature(owner, tag)
exists_flag = false;
try; owner.feature(tag); exists_flag = true; catch; exists_flag = false; end
end

function status = try_run_eigenfrequency_study(model, n_modes, freq_lower_hz)
status = 'not_attempted';
try
    if has_feature(model.study, 'std_mosaic_eig')
        model.study.remove('std_mosaic_eig');
    end
    model.study.create('std_mosaic_eig');
    model.study('std_mosaic_eig').create('eig', 'Eigenfrequency');
    eigf = model.study('std_mosaic_eig').feature('eig');
    eigf.set('neigs', n_modes);
    eigf.set('shift', sprintf('%.12g[Hz]', freq_lower_hz));
    try; eigf.set('shiftactive', 'on'); catch; end
    try; eigf.set('eigwhich', 'lr'); catch; end  % nearest real shift
    model.study('std_mosaic_eig').run;
    status = 'ok';
catch err
    status = ['failed:' err.message];
end
end
