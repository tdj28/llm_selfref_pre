#!/usr/bin/env python3
"""Replay the packaged audit using hash-checked files from a pinned Git commit."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

BUNDLE = Path(__file__).resolve().parent
ENV = {'PATH': os.defpath, 'PYTHONDONTWRITEBYTECODE': '1',
       'PYTHONNOUSERSITE': '1', 'GIT_OPTIONAL_LOCKS': '0'}


def read(path):
    return json.loads(path.read_text())


def fingerprint(path):
    return {'bytes': path.stat().st_size,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def write(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def safe_relative(value):
    path = Path(value)
    if path.is_absolute() or '..' in path.parts:
        raise ValueError('Unsafe manifest path: ' + value)
    return path


def verify_bundle():
    manifest = read(BUNDLE / 'bundle_manifest.json')
    for relative, expected in manifest['files'].items():
        path = BUNDLE / safe_relative(relative)
        if path.is_symlink() or fingerprint(path) != expected:
            raise ValueError('Bundle hash mismatch: ' + relative)
    actual = {p.relative_to(BUNDLE).as_posix() for p in BUNDLE.rglob('*') if p.is_file()}
    if actual != set(manifest['files']) | {'bundle_manifest.json'}:
        raise ValueError('Bundle contains unexpected or missing files')
    return len(manifest['files'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, help='Local Git clone containing the pinned commit')
    parser.add_argument('--out', type=Path, help='Fresh scratch directory; must not exist')
    parser.add_argument('--verify-only', action='store_true', help='Check this compact bundle without raw data')
    args = parser.parse_args()
    count = verify_bundle()
    if args.verify_only:
        print(json.dumps({'status': 'pass', 'bundle_files_verified': count}))
        return
    if args.source is None or args.out is None:
        parser.error('--source and --out are required unless --verify-only is used')
    source, out = args.source.resolve(), args.out.resolve()
    if out == BUNDLE or BUNDLE in out.parents:
        parser.error('--out must be outside the packaged evidence directory')
    if out == source or source in out.parents:
        relative = out.relative_to(source)
        if not relative.parts or relative.parts[0] != 'out':
            parser.error('Scratch inside the source repository must be beneath out/')
        subprocess.run(['git', '-C', str(source), 'check-ignore', '-q', '--',
                        str(relative / 'probe.json')], env=ENV, check=True)
    if out.exists():
        parser.error('--out already exists; use a fresh path to preserve prior attempts')

    import numpy
    import pandas
    inputs = read(BUNDLE / 'inputs.json')
    commit = inputs['commit']
    resolved = subprocess.check_output(['git', '-C', str(source), 'rev-parse', commit + '^{commit}'],
                                       env=ENV, stderr=subprocess.PIPE).decode().strip()
    if resolved != commit:
        raise ValueError('Pinned commit did not resolve exactly')
    out.mkdir(parents=True)
    repo = out / 'repo'
    work = repo / 'out/response_release_20260929/repro'
    work.mkdir(parents=True)
    materialized = {}
    for relative, expected in inputs['files'].items():
        path = safe_relative(relative)
        raw = subprocess.check_output(['git', '-C', str(source), 'show', commit + ':' + relative],
                                      env=ENV, stderr=subprocess.PIPE)
        actual = {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
        if actual != expected:
            raise ValueError('Pinned input differs from original audit: ' + relative)
        destination = (work / 'copies' / path) if path.parts[0] == 'data' else (repo / path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(raw)
        materialized[relative] = destination
    for name in ['supplement_raw_checks.py', 'replay_gemma_role_intervals.py']:
        shutil.copy2(BUNDLE / 'checkers' / name, work / name)

    causal = work / 'copies/data/causal_transplant/confirmatory_v1_20260709'
    sae = work / 'copies/data/public_sae_consciousness_gating/confirmatory_v1_20260710'
    gemma = work / 'copies/data/gemma_scope_9b/confirmatory_v1_20260711'
    jobs = [
        ('causal', [repo / 'experiments/causal_transplant/audit_headline_point_estimates.py', causal],
         causal / 'independent_point_estimate_audit.json', 'causal_headlines.json'),
        ('public_sae', [repo / 'experiments/exp2_sae/audit_public_sae_consciousness_headlines.py',
                        '--generations', sae / 'generations.jsonl',
                        '--local-judgments', sae / 'judging/local_llama_judgments.jsonl',
                        '--analysis-dir', sae / 'analysis'],
         sae / 'analysis/independent_headline_audit.json', 'public_sae_headlines.json'),
        ('gemma', [repo / 'experiments/exp2_sae/audit_gemma_scope_9b_headlines.py', gemma],
         gemma / 'analysis/independent_headline_audit.json', 'gemma_headlines.json'),
        ('supplement', [work / 'supplement_raw_checks.py'],
         work / 'raw_quantity_checks.json', 'raw_quantity_checks.json'),
        ('gemma_intervals', [work / 'replay_gemma_role_intervals.py'],
         work / 'gemma_role_interval_replay.json', 'gemma_role_interval_replay.json'),
    ]
    results = []
    for name, arguments, output, receipt in jobs:
        argv = [sys.executable, '-B', *map(str, arguments)]
        started = datetime.now(timezone.utc).isoformat()
        start = time.monotonic()
        with (out / (name + '.stdout.log')).open('wb') as stdout:
            with (out / (name + '.stderr.log')).open('wb') as stderr:
                result = subprocess.run(argv, cwd=repo, env=ENV, stdout=stdout,
                                        stderr=stderr, timeout=300)
        matches = False
        if result.returncode == 0:
            observed, expected = read(output), read(BUNDLE / 'receipts' / receipt)
            observed.pop('audited_at_utc', None)
            expected.pop('audited_at_utc', None)
            if name == 'gemma_intervals':
                observed['source_sha256'] = {str(Path(p).relative_to(repo)): value
                                            for p, value in observed['source_sha256'].items()}
            matches = observed == expected
        results.append({'name': name, 'started_at_utc': started,
                        'seconds': time.monotonic() - start, 'exit_code': result.returncode,
                        'matches_original_receipt': matches,
                        'argv_roles': ['${PYTHON}' if i == 0 else v.replace(str(out), '${OUT}')
                                       for i, v in enumerate(argv)]})
        write(out / 'run_results.json', results)
        print(name + ': ' + ('PASS' if matches else 'FAIL'), flush=True)
    unchanged = all(fingerprint(p) == inputs['files'][name] for name, p in materialized.items())
    passed = unchanged and all(r['matches_original_receipt'] for r in results)
    write(out / 'run_summary.json', {
        'status': 'pass' if passed else 'fail', 'source_commit': commit,
        'checked_at_utc': datetime.now(timezone.utc).isoformat(),
        'input_files': len(materialized),
        'input_bytes': sum(v['bytes'] for v in inputs['files'].values()),
        'pinned_inputs_hash_checked_and_unchanged': unchanged,
        'python_version': sys.version, 'pandas_version': pandas.__version__,
        'numpy_version': numpy.__version__, 'jobs': results,
        'comparison_exclusions': ['Gemma audit wall-clock timestamp',
                                  'Gemma interval replay host source-path prefix'],
        'public_safety_rerun': False,
        'scope': 'portable packaging verification; not independent human review',
    })
    raise SystemExit(0 if passed else 1)


if __name__ == '__main__':
    main()
