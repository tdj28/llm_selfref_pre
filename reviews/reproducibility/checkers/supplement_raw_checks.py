"""Bounded structural and denominator checks; no generated-text disclosure."""

from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'copies/data'
ERRORS = []


def read(path):
    with path.open() as handle:
        return [json.loads(line) for line in handle if line.strip()]


def require(condition, message):
    if not condition:
        ERRORS.append(message)


def inventory(rows, judgments, final_field, induction_field):
    ids = [r['trial_id'] for r in rows]
    jids = [r['trial_id'] for r in judgments]
    require(len(set(ids)) == len(ids), 'duplicate generation IDs')
    require(len(set(jids)) == len(jids), 'duplicate judgment IDs')
    require(set(ids) == set(jids), 'generation/judgment ID mismatch')
    require(all(j['paper_label'] in (None, 0, 1) for j in judgments), 'nonbinary labels')
    labels = {j['trial_id']: j['paper_label'] for j in judgments}
    empty = [r for r in rows if not r[final_field].strip()]
    empty_labeled = sum(labels[r['trial_id']] is not None for r in empty)
    require(empty_labeled == 0, 'empty output assigned nonmissing label')
    hash_count = 0
    hash_errors = 0
    for row in rows:
        for field in [final_field, induction_field]:
            expected = row.get(field + '_sha256')
            if expected is not None:
                hash_count += 1
                hash_errors += hashlib.sha256(row[field].encode()).hexdigest() != expected
    require(hash_errors == 0, 'stored text hash mismatch')
    return {
        'rows': len(rows), 'unique_ids': len(set(ids)), 'judgments': len(judgments),
        'label_counts': dict(Counter(str(j['paper_label']) for j in judgments)),
        'empty_final_outputs': len(empty),
        'empty_final_outputs_with_nonmissing_labels': empty_labeled,
        'empty_inductions': sum(not r[induction_field].strip() for r in rows),
        'embedded_text_hashes_checked': hash_count, 'embedded_text_hash_errors': hash_errors,
    }


def paired_counts(rows, labels, block_field, condition_field, left, right):
    blocks = defaultdict(dict)
    counts = Counter()
    sums = Counter()
    for row in rows:
        condition = row[condition_field]
        if condition not in (left, right):
            continue
        block = str(row[block_field])
        require(condition not in blocks[block], 'duplicate paired cell')
        value = labels.get(row['trial_id'])
        blocks[block][condition] = value
        if value is not None:
            counts[condition] += 1
            sums[condition] += value
    complete = {k: v[left] - v[right] for k, v in blocks.items()
                if v.get(left) is not None and v.get(right) is not None}
    return {
        'arms': {k: {'positive': sums[k], 'n': counts[k]} for k in (left, right)},
        'complete_blocks': len(complete), 'incomplete_blocks': len(blocks) - len(complete),
        'positive_discordant': sum(v == 1 for v in complete.values()),
        'negative_discordant': sum(v == -1 for v in complete.values()),
        'ties': sum(v == 0 for v in complete.values()),
        'paired_difference': statistics.mean(complete.values()),
    }


causal_root = DATA / 'causal_transplant/confirmatory_v1_20260709'
causal = read(causal_root / 'outcomes.jsonl')
judgments = read(causal_root / 'judgments_paper.jsonl')
causal_results = {'judges': {}, 'rows_by_model': dict(Counter(r['model_key'] for r in causal)),
                  'rows_by_phase': dict(Counter(r['phase'] for r in causal))}
for judge in sorted({j['judge_key'] for j in judgments}):
    selected = [j for j in judgments if j['judge_key'] == judge]
    result = inventory(causal, selected, 'final_output', 'transcript')
    labels = {j['trial_id']: j['paper_label'] for j in selected}
    result['missing_by_model_and_query'] = dict(Counter(
        r['model_key'] + ' | ' + r['query_id'] for r in causal if labels[r['trial_id']] is None))
    result['headline_cell_counts'] = []
    groups = defaultdict(list)
    for row in causal:
        if row['query_id'] == 'indirect_experience':
            groups[(row['model_key'], row['instruction_cell'], row['transcript_cell'])].append(row)
    for key, rows in sorted(groups.items()):
        vals = [labels[r['trial_id']] for r in rows]
        result['headline_cell_counts'].append({
            'model': key[0], 'instruction': key[1], 'transcript': key[2],
            'rows': len(rows), 'valid': sum(v is not None for v in vals),
            'positive': sum(v for v in vals if v is not None)})
    causal_results['judges'][judge] = result

sae_root = DATA / 'public_sae_consciousness_gating/confirmatory_v1_20260710'
sae = read(sae_root / 'generations.jsonl')
judgments = read(sae_root / 'judging/local_llama_judgments.jsonl')
sae_results = inventory(sae, judgments, 'response', 'induction_response')
labels = {j['trial_id']: j['paper_label'] for j in judgments}
sae_results['phase_counts'] = dict(Counter(r['phase'] for r in sae))
sae_results['aggregate_cells'] = {}
for phase in ['aggregate_literal', 'aggregate_calibrated']:
    phase_rows = [r for r in sae if r['phase'] == phase]
    sae_results['aggregate_cells'][phase] = {
        role: paired_counts([r for r in phase_rows if r['analysis_role'] == role], labels,
                            'block_id', 'sign', 'suppression', 'amplification')
        for role in sorted({r['analysis_role'] for r in phase_rows})}
plan = read(sae_root / 'plan/confirmatory_plan.jsonl')
require(len(plan) == len(sae) and {r['trial_id'] for r in plan} == {r['trial_id'] for r in sae},
        'SAE plan/generation ID mismatch')
sae_results['plan_trial_ids_match'] = True
telemetry = Counter()
nonzero_rms = []
latent_errors = []
zero_rms = []
for row in sae:
    zero = all(float(i['coefficient']) == 0 for i in row['interventions'])
    for field in ['induction_diagnostics', 'final_diagnostics']:
        d = row[field]
        telemetry['turns_checked'] += 1
        telemetry['bad_registration'] += d.get('hook_registrations') != 1
        telemetry['bad_calls'] += d.get('hook_calls', 0) < 1
        telemetry['bad_removal'] += d.get('hook_removed') is not True
        telemetry['bad_mask'] += d.get('attention_mask_mode') != 'explicit_all_ones_unpadded'
        if zero:
            telemetry['bad_zero'] += (d.get('zero_is_true_noop') is not True
                                      or d.get('steering_applied') is not False)
            telemetry['zero_turns'] += 1
            if 'relative_hidden_delta_rms' in d:
                zero_rms.append(float(d['relative_hidden_delta_rms']))
            else:
                telemetry['zero_turns_without_rms_field'] += 1
        else:
            telemetry['bad_applied'] += d.get('steering_applied') is not True
            nonzero_rms.append(float(d['relative_hidden_delta_rms']))
            latent_errors.append(float(d['max_latent_delta_error']))
require(not any(v for k, v in telemetry.items() if k.startswith('bad_')), 'SAE telemetry flags')
require(all(math.isfinite(x) and x <= .20 for x in nonzero_rms), 'SAE delta RMS bound')
require(all(math.isfinite(x) and x <= .03 for x in latent_errors), 'SAE latent delta bound')
require(all(x == 0 for x in zero_rms), 'SAE zero RMS is not exactly zero')
sae_results['telemetry'] = dict(telemetry, nonzero_max_relative_rms=max(nonzero_rms),
                                max_latent_error=max(latent_errors),
                                zero_rms_fields_observed=len(zero_rms),
                                max_zero_relative_rms=max(zero_rms) if zero_rms else None)
for flag in ['induction_cap_hit', 'final_cap_hit']:
    sae_results[flag + '_count'] = sum(bool(r[flag]) for r in sae)

gemma_root = DATA / 'gemma_scope_9b/confirmatory_v1_20260711'
baseline = read(gemma_root / 'baseline/baseline_generations.jsonl')
steering = read(gemma_root / 'steering/steering_generations.jsonl')
judgments = read(gemma_root / 'judging/local_gemma_judgments.jsonl')
gemma_results = inventory(baseline + steering, judgments, 'response', 'induction_response')
labels = {j['trial_id']: j['paper_label'] for j in judgments}
gemma_results['baseline'] = paired_counts([r for r in baseline if r['design'] == 'paper_exact'],
    labels, 'block_id', 'condition', 'paper_self_ref', 'paper_history')
gemma_results['primary_roles'] = {
    role: paired_counts([r for r in steering if r['design'] == 'primary_layer20_131k'
                        and r['analysis_role'] == role], labels, 'block_index', 'sign',
                        'suppression', 'amplification')
    for role in sorted({r['analysis_role'] for r in steering if r['design'] == 'primary_layer20_131k'})}
gemma_results['design_counts'] = dict(Counter(r['design'] for r in baseline + steering))
for flag in ['induction_cap_hit', 'final_cap_hit']:
    gemma_results[flag + '_count'] = sum(bool(r[flag]) for r in baseline + steering)
gemma_results['plan_trial_ids_match'] = {}
for name, rows, plan_path in [
    ('baseline', baseline, 'baseline/plan/baseline_plan.jsonl'),
    ('steering', steering, 'steering/plan/steering_plan.jsonl')]:
    planned = read(gemma_root / plan_path)
    match = len(planned) == len(rows) and {r['trial_id'] for r in planned} == {r['trial_id'] for r in rows}
    require(match, 'Gemma ' + name + ' plan/generation ID mismatch')
    gemma_results['plan_trial_ids_match'][name] = match
transfer = json.loads((gemma_root / 'atlas/transfer_gate.json').read_text())
fvus = [r['error_sum_squares'] / r['centered_hidden_sum_squares']
        for key, r in transfer['chat_reconstruction'].items() if key.startswith('pt_')]
gemma_results['pt_to_it_gate'] = {
    'stored_status': transfer['status'], 'recomputed_median_pt_fvu': statistics.median(fvus),
    'maximum_allowed_pt_fvu': transfer['thresholds']['median_pt_fvu_max']}
require(math.isclose(statistics.median(fvus), transfer['median_pt_fvu']), 'Gemma FVU mismatch')
require(statistics.median(fvus) > transfer['thresholds']['median_pt_fvu_max']
        and transfer['status'] == 'fail', 'Gemma failed transfer gate not preserved')

payload = {'status': 'pass' if not ERRORS else 'fail', 'errors': ERRORS,
           'causal': causal_results, 'public_sae': sae_results, 'gemma': gemma_results}
(ROOT / 'raw_quantity_checks.json').write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n')
print(json.dumps({'status': payload['status'], 'errors': ERRORS,
                  'output': str(ROOT / 'raw_quantity_checks.json')}))
raise SystemExit(bool(ERRORS))
