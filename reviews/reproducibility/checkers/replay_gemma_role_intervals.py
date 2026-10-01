"""Replay only six stored Gemma intervals using the inspected production convention."""
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT.parents[2]
RELEASE = ROOT / 'copies/data/gemma_scope_9b/confirmatory_v1_20260711'
SOURCES = [SOURCE / 'experiments/exp2_sae/analyze_gemma_scope_9b.py',
           SOURCE / 'experiments/exp2_sae/gemma_scope_9b_protocol.py']
before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in SOURCES}
rows = [json.loads(s) for s in (RELEASE / 'steering/steering_generations.jsonl').read_text().splitlines()]
judgments = [json.loads(s) for s in (RELEASE / 'judging/local_gemma_judgments.jsonl').read_text().splitlines()]
labels = {r['trial_id']: r['paper_label'] for r in judgments}
primary = json.loads((RELEASE / 'analysis/primary_verdict.json').read_text())
results = {}
for role, reported in primary['primary_role_effects'].items():
    blocks = defaultdict(dict)
    for row in rows:
        if row['design'] == 'primary_layer20_131k' and row['analysis_role'] == role:
            blocks[row['block_index']][row['sign']] = labels[row['trial_id']]
    values = np.array([float(cells['suppression'] - cells['amplification'])
                       for _, cells in sorted(blocks.items(), key=lambda item: str(item[0]))])
    key = 'primary|gemma_local|' + role
    seed = int(hashlib.sha256(key.encode()).hexdigest()[:8], 16)
    rng = np.random.default_rng(seed)
    estimates = np.empty(100000, dtype=np.float64)
    for start in range(0, 100000, 10000):
        indices = rng.integers(0, len(values), size=(10000, len(values)))
        estimates[start:start + 10000] = values[indices].mean(axis=1)
    low, high = np.quantile(estimates, [.025, .975])
    results[role] = {'key': key, 'seed': seed, 'n': len(values),
                     'point': float(values.mean()), 'ci_low': float(low), 'ci_high': float(high),
                     'stored_ci_low': reported['ci_low'], 'stored_ci_high': reported['ci_high'],
                     'exact_interval_match': bool(low == reported['ci_low'] and high == reported['ci_high'])}
after = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in SOURCES}
passed = before == after and all(v['exact_interval_match'] for v in results.values())
payload = {'status': 'pass' if passed else 'fail', 'source_sha256': before,
           'source_bytes_unchanged': before == after,
           'method': 'Reimplementation of inspected production keyed NumPy bootstrap, not a new independent analysis',
           'bootstrap_replicates': 100000, 'results': results}
(ROOT / 'gemma_role_interval_replay.json').write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n')
print(json.dumps(payload, indent=2, sort_keys=True))
raise SystemExit(not passed)
