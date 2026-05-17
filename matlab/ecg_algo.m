%% Configuration & Tunable Knobs
fs = 125;
filename = '..\matlab\mitbih_test.csv';

% --- THE RELATIVE KNOBS ---
tolerance = 1;           % 10% Peak-to-Peak Magnitude Tolerance
rs_window_knob = 255;       % Max drop allowed between peaks (R to S + Wander)
slope_thresh_knob = 15;    
refractory_delay = 10;     
max_window_knob = -100;      % Min gap (R-peak minus inter-peak rolling max) required; smaller gap = hump
max_window_arm_samples = 5; % Start max-window checks only after N samples from peak1
slope_backoff_samples = 0;
window_floor_offset = 5;  % ADC units subtracted from pre-slope min to set the normalization floor % Ignore slope retriggers for N samples after a slope event

% --- NSTDB NOISE KNOBS (real-world noise stress test) ---
enable_noise_profile = true;
noise_profile = 'mixed';   % 'none' | 'bw' | 'ma' | 'em' | 'mixed'
target_snr_db = 10;        % Common evaluation points: 24/18/12/6/0 dB

nstdb_dir = '..\matlab\nstdb';
nstdb_dir_resolved = nstdb_dir;

% ADC Parameters (8-bit)
ADC_RES = 255;    
DC_OFFSET = 64;  
SIGNAL_GAIN = ADC_RES * 0.5; 

%% 1. Load and Prep Data
raw_data = csvread(filename);
target_row = floor(rand() * 18118) + 1;
target_row = 20105;
fprintf('Reading CSV row index: %d\n', target_row);
beat_template = raw_data(target_row, 1:187);
ignore_prefix_samples = length(beat_template);

% Build stream as contiguous repeats of the selected beat (no zero padding).
num_repeats = 12;
clean_stream = repmat(beat_template, 1, num_repeats);

L = length(clean_stream);
t = (0:L-1)/fs;
base_adc_stream = (clean_stream * SIGNAL_GAIN) + DC_OFFSET;

% Load NSTDB artifacts from local CSV exports (bw/ma/em)
bw_path = fullfile(nstdb_dir_resolved, 'bw.csv');
ma_path = fullfile(nstdb_dir_resolved, 'ma.csv');
em_path = fullfile(nstdb_dir_resolved, 'em.csv');
if ~exist(bw_path, 'file') || ~exist(ma_path, 'file') || ~exist(em_path, 'file')
    error(['NSTDB files not found. Expected: ', bw_path, ', ', ma_path, ', ', em_path, ...
           '. Export NSTDB noise records to CSV and place them under ', nstdb_dir_resolved, '.']);
end

bw_raw = csvread(bw_path);
ma_raw = csvread(ma_path);
em_raw = csvread(em_path);

if size(bw_raw, 2) > 1, bw_raw = bw_raw(:,1); end
if size(ma_raw, 2) > 1, ma_raw = ma_raw(:,1); end
if size(em_raw, 2) > 1, em_raw = em_raw(:,1); end

src_idx_bw = linspace(1, length(bw_raw), L);
src_idx_ma = linspace(1, length(ma_raw), L);
src_idx_em = linspace(1, length(em_raw), L);

noise_bw = interp1(1:length(bw_raw), bw_raw(:), src_idx_bw, 'linear');
noise_ma = interp1(1:length(ma_raw), ma_raw(:), src_idx_ma, 'linear');
noise_em = interp1(1:length(em_raw), em_raw(:), src_idx_em, 'linear');

noise_bw = noise_bw - mean(noise_bw);
noise_ma = noise_ma - mean(noise_ma);
noise_em = noise_em - mean(noise_em);

switch lower(noise_profile)
    case 'none'
        selected_noise = zeros(1, L);
    case 'bw'
        selected_noise = noise_bw;
    case 'ma'
        selected_noise = noise_ma;
    case 'em'
        selected_noise = noise_em;
    case 'mixed'
        selected_noise = noise_bw + noise_ma + noise_em;
    otherwise
        error('Unknown noise_profile: %s', noise_profile);
end

% SNR-calibrated injection makes conditions reproducible and comparable.
if ~strcmpi(noise_profile, 'none')
    sig_power = mean((base_adc_stream - mean(base_adc_stream)).^2);
    noise_power = mean((selected_noise - mean(selected_noise)).^2);
    if noise_power > 0
        desired_noise_power = sig_power / (10^(target_snr_db / 10));
        selected_noise = selected_noise * sqrt(desired_noise_power / noise_power);
    end
end

if enable_noise_profile
    adc_stream = base_adc_stream + selected_noise;
else
    adc_stream = base_adc_stream;
end

fprintf('Noise profile: %s | enabled: %d\n', noise_profile, enable_noise_profile);
fprintf('Noise source: NSTDB (%s) | target SNR: %.1f dB\n', nstdb_dir_resolved, target_snr_db);
fprintf('Noise stats => mean: %.2f, std: %.2f, p2p: %.2f\n', mean(selected_noise), std(selected_noise), max(selected_noise)-min(selected_noise));

%% 2. Execution Loop
i = ignore_prefix_samples + 1;
peak1_mag = 0;
peak1_idx = 0; 
rolling_min = 255; 
rolling_max = 0;
rolling_max_idx = 0;
rolling_max_valid = false;
strong_slope_seen = false;
max_window_broken = false;
trans_idx = 0;
slope_backoff_ctr = 0;
all_preprocessed_samples = []; % NaN-separated accepted windows for offline visualization
pair_counter = 0;
pair_palette = lines(32);
peak1_pair_id = 0;
peak1_color = [1, 0, 0];

% Open input vector file
fid = fopen('input_vectors.txt', 'w');
fid_raw_unscaled = fopen('input_vectors_raw_unscaled.txt', 'w');
fid_raw_scaled = fopen('input_vectors_raw_scaled.txt', 'w');
fprintf(fid, '[[[runtime]]]\n');
fprintf(fid_raw_unscaled, '[[[runtime]]]\n');
fprintf(fid_raw_scaled, '[[[runtime]]]\n');

figure('Color', 'w');
subplot(2,1,1);
plot(adc_stream, 'Color', [0.35, 0.35, 0.35]);
title('Detected Peak Pairs on Input Stream');
xlabel('Sample Index');
ylabel('ADC');
grid on;
hold on;

while i < L - 5
    dy = adc_stream(i) - adc_stream(i-1);
    slope_backoff_ctr = max(0, slope_backoff_ctr - 1);

    % --- ASIC ROLLING MIN LOGIC ---
    if peak1_mag > 0
        max_window_armed = (i - peak1_idx) >= max_window_arm_samples;

        % Update the rolling minimum with the current sample
        if adc_stream(i) < rolling_min
            rolling_min = adc_stream(i);
        end

        if max_window_armed && ((~rolling_max_valid) || (adc_stream(i) > rolling_max))
            rolling_max = adc_stream(i);
            rolling_max_idx = i;
            rolling_max_valid = true;
        end

        if (~strong_slope_seen) && (dy > slope_thresh_knob)
            strong_slope_seen = true;
        end

        if rolling_max_valid && (~max_window_broken) && ((peak1_mag - rolling_max) < max_window_knob) && (~strong_slope_seen)
            max_window_broken = true;
        end

        % Immediate max-window reset between peaks (hardware-style async supervision)
        if max_window_broken
            fprintf('  [MAX-WINDOW RESET] Async reset at Idx %d | R-to-Max Gap: %.1f | Max Idx: %d\n', ...
                i, (peak1_mag - rolling_max), rolling_max_idx);

            subplot(2,1,1); hold on;
            plot(rolling_max_idx, rolling_max, 'cx', 'MarkerSize', 10, 'LineWidth', 2);
            plot(i, adc_stream(i), 'cs', 'MarkerSize', 8, 'LineWidth', 2);
            hold off;

            peak1_mag = 0;
            rolling_min = 255;
            i = i + refractory_delay;
            rolling_max = 0;
            rolling_max_idx = 0;
            rolling_max_valid = false;
            strong_slope_seen = false;
            max_window_broken = false;
            continue;
        end
        
        % --- THE IMPROVED SAFETY CHECK ---
        % Instead of current sample, check if the deepest point found so far 
        % is too far from the R-peak (indicating heavy wander or garbage)
        if (peak1_mag - rolling_min) > rs_window_knob
            fprintf('  [REL-SAFETY] RESET at Idx %d | Current Min Drop: %.1f\n', i, (peak1_mag - rolling_min));
            
            subplot(2,1,1); hold on; 
            plot(i, adc_stream(i), 'mx', 'MarkerSize', 10, 'LineWidth', 2); 
            hold off;
            
            peak1_mag = 0;
            rolling_min = 255;
            i = i + refractory_delay;
            rolling_max = 0;
            rolling_max_idx = 0;
            rolling_max_valid = false;
            strong_slope_seen = false;
            max_window_broken = false;
            continue;
        end
    end

    % --- SLOPE TRIGGER ---
    if (dy > slope_thresh_knob) && (slope_backoff_ctr == 0)
        [max_val, max_rel_idx] = max(adc_stream(i:i+5));
        actual_peak_idx = i + max_rel_idx - 1; 
        slope_backoff_ctr = slope_backoff_samples;
        if peak1_mag == 0
            % MAX 1 FOUND
            peak1_mag = max_val;
            peak1_idx = actual_peak_idx;
            pair_counter = pair_counter + 1;
            peak1_pair_id = pair_counter;
            peak1_color = pair_palette(mod(peak1_pair_id-1, size(pair_palette,1)) + 1, :);
            rolling_min = min(adc_stream(max(1, i-3) : i-1)) - window_floor_offset; % Min of 3 pre-slope samples minus floor offset

            rolling_max = 0;
            rolling_max_idx = 0;
            rolling_max_valid = false;
            strong_slope_seen = false;
            max_window_broken = false;
            subplot(2,1,1);
            plot(actual_peak_idx, max_val, '^', 'Color', peak1_color, 'MarkerFaceColor', peak1_color, 'MarkerSize', 8, 'LineWidth', 1.4);
            text(actual_peak_idx, max_val + 2, sprintf('P%d-1', peak1_pair_id), 'Color', peak1_color, 'FontSize', 8, 'HorizontalAlignment', 'center');
            i = i + refractory_delay;
        else
            % PEAK 2 FOUND
            mag_err = abs(peak1_mag - max_val) / peak1_mag;

            if mag_err > tolerance
                subplot(2,1,1);
                plot(actual_peak_idx, max_val, 'x', 'Color', peak1_color, 'MarkerSize', 8, 'LineWidth', 1.6);
                plot([peak1_idx, actual_peak_idx], [peak1_mag, max_val], ':', 'Color', peak1_color, 'LineWidth', 1.0);
                text(actual_peak_idx, max_val - 3, sprintf('P%d-2R', peak1_pair_id), 'Color', peak1_color, 'FontSize', 8, 'HorizontalAlignment', 'center');

                fprintf('  [TOL RESET] Err: %.1f%% (Raw Mag Difference)\n', mag_err*100);
                peak1_mag = max_val;
                peak1_idx = actual_peak_idx;
                pair_counter = pair_counter + 1;
                peak1_pair_id = pair_counter;
                peak1_color = pair_palette(mod(peak1_pair_id-1, size(pair_palette,1)) + 1, :);
                rolling_min = min(adc_stream(max(1, i-3) : i-1)) - window_floor_offset; % Min of 3 pre-slope samples minus floor offset
                rolling_max = 0;
                rolling_max_idx = 0;
                rolling_max_valid = false;
                strong_slope_seen = false;
                max_window_broken = false;
                subplot(2,1,1);
                plot(actual_peak_idx, max_val, '^', 'Color', peak1_color, 'MarkerFaceColor', peak1_color, 'MarkerSize', 8, 'LineWidth', 1.4);
                text(actual_peak_idx, max_val + 2, sprintf('P%d-1', peak1_pair_id), 'Color', peak1_color, 'FontSize', 8, 'HorizontalAlignment', 'center');
                i = i + refractory_delay;
            else
                % --- VALID PAIR ---
                fprintf('  [VALID] Pushing window. Final Rolling Min: %.1f\n', rolling_min);

                win_len = length(beat_template);
                win_start = peak1_idx;
                win_end = win_start + win_len - 1;
                if win_end > L
                    fprintf('  [WINDOW SKIP] Incomplete peak1 window at Idx %d (need %d, have %d)\n', ...
                        peak1_idx, win_len, (L - peak1_idx + 1));
                    peak1_mag = 0;
                    rolling_min = 255;
                    rolling_max = 0;
                    rolling_max_idx = 0;
                    rolling_max_valid = false;
                    strong_slope_seen = false;
                    max_window_broken = false;
                    i = i + refractory_delay;
                    continue;
                end
                cnn_win = adc_stream(win_start : win_end);
                p_offset = cnn_win - rolling_min;
                
                % DEBUG: Compare initialized rolling_min vs actual window minimum
                actual_window_min = min(cnn_win);
                fprintf('  [DEBUG] Initial rolling_min: %.1f | Actual window min: %.1f | Difference: %.1f\n', rolling_min, actual_window_min, rolling_min - actual_window_min);
                fprintf('  [DEBUG] p_offset range: [%.1f, %.1f] | cnn_win range: [%.1f, %.1f]\n', min(p_offset), max(p_offset), min(cnn_win), max(cnn_win));
                % Normalize to full 5-bit dynamic range per accepted window (min->0, max->31)
%                 p_span = max(p_offset);
%                 if p_span > 0
%                     scaled = round((double(p_offset) / double(p_span)) * 31);
%                 else
%                     scaled = zeros(size(p_offset));
%                 end
%                 scaled = min(max(scaled, 0), 31);
                output_shift = 2;
                scaled = min(max(bitshift(int32(p_offset), -output_shift), 0), 31);
                fprintf('  [DEBUG] scaled range: [%d, %d]\n', min(scaled), max(scaled));

                % Build a reference-scaled version of the original beat (0..31)
                orig_ref = beat_template;
                orig_ref = orig_ref - min(orig_ref);
                if max(orig_ref) > 0
                    orig_ref_scaled = (orig_ref / max(orig_ref)) * 31;
                else
                    orig_ref_scaled = zeros(size(orig_ref));
                end

                % Build scaled version of the actual input window that was processed
                input_pair_ref = cnn_win;
                input_pair_ref = input_pair_ref - min(input_pair_ref);
                if max(input_pair_ref) > 0
                    input_pair_scaled = (input_pair_ref / max(input_pair_ref)) * 31;
                else
                    input_pair_scaled = zeros(size(input_pair_ref));
                end

                subplot(2,1,1);
                plot(actual_peak_idx, max_val, 's', 'Color', peak1_color, 'MarkerFaceColor', peak1_color, 'MarkerSize', 7, 'LineWidth', 1.4);
                plot([peak1_idx, actual_peak_idx], [peak1_mag, max_val], '-', 'Color', peak1_color, 'LineWidth', 1.2);
                text(actual_peak_idx, max_val - 3, sprintf('P%d-2', peak1_pair_id), 'Color', peak1_color, 'FontSize', 8, 'HorizontalAlignment', 'center');
                subplot(2,1,2);
                plot(orig_ref_scaled, 'k--', 'LineWidth', 1.2); hold on;
                plot(input_pair_scaled, 'b-.', 'LineWidth', 1.2);
                plot(double(scaled), 'r', 'LineWidth', 1.5); hold off;
                title(['CNN Input | Rolling Min Subtracted: ', num2str(round(rolling_min))]);
                legend('Original Row (Scaled 0..31)', 'Input Peak Pair (Scaled 0..31)', 'Processed Window', 'Location', 'best');
                ylim([-2 35]); grid on;

                drawnow; pause(0.2);

                % Keep all accepted preprocessed windows for offline visualization
                all_preprocessed_samples = [all_preprocessed_samples, scaled(:).', NaN];

                % Write transaction to file
                fprintf(fid, '[[transaction]]           %d\n', trans_idx);
                fprintf(fid_raw_unscaled, '[[transaction]]           %d\n', trans_idx);
                fprintf(fid_raw_scaled, '[[transaction]]           %d\n', trans_idx);
                for k = 1:length(scaled)
                    fprintf(fid, '0x%04x\n', max(0, round(scaled(k))));
                    fprintf(fid_raw_unscaled, '0x%04x\n', max(0, round(cnn_win(k))));
                    fprintf(fid_raw_scaled, '0x%04x\n', max(0, round(orig_ref_scaled(k))));
                end
                fprintf(fid, '[[/transaction]]\n');
                fprintf(fid_raw_unscaled, '[[/transaction]]\n');
                fprintf(fid_raw_scaled, '[[/transaction]]\n');
                trans_idx = trans_idx + 1;

                peak1_mag = 0;
                rolling_min = 255;
                rolling_max = 0;
                rolling_max_idx = 0;
                rolling_max_valid = false;
                strong_slope_seen = false;
                max_window_broken = false;
                i = i + (refractory_delay * 2);
            end
        end
    end
    i = i + 1;
end

% Write closing empty transaction and footer
fprintf(fid, '[[transaction]]           %d\n', trans_idx);
fprintf(fid_raw_unscaled, '[[transaction]]           %d\n', trans_idx);
fprintf(fid_raw_scaled, '[[transaction]]           %d\n', trans_idx);
fprintf(fid, '[[[/runtime]]]\n');
fprintf(fid_raw_unscaled, '[[[/runtime]]]\n');
fprintf(fid_raw_scaled, '[[[/runtime]]]\n');
fclose(fid);
fclose(fid_raw_unscaled);
fclose(fid_raw_scaled);
fprintf('Saved %d transactions to input_vectors.txt\n', trans_idx);
fprintf('Saved %d transactions to input_vectors_raw_unscaled.txt\n', trans_idx);
fprintf('Saved %d transactions to input_vectors_raw_scaled.txt\n', trans_idx);

save('all_preprocessed_samples.mat', 'all_preprocessed_samples');
csvwrite('all_preprocessed_samples.csv', all_preprocessed_samples);
fprintf('Saved preprocessed sample log to all_preprocessed_samples.mat/csv\n');

