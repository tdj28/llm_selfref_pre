# AE Protocol Runner

Last updated: 2026-07-08

This document describes our clean-room runner for AE Studio's public steering-notebook protocol.

## Provenance And Copyright Handling

Upstream public artifact:

- Repo: `https://github.com/agencyenterprise/steering-api-examples`
- Notebook path: `deception-features/deception_features.ipynb`
- Raw notebook URL: `https://raw.githubusercontent.com/agencyenterprise/steering-api-examples/main/deception-features/deception_features.ipynb`

No license was observed in the upstream repo at the time of review. To avoid copying unlicensed code:

- We do **not** vendor the upstream notebook.
- We do **not** copy or execute upstream implementation code.
- Our runner is a clean-room implementation using our own HTTP client and control flow.
- Candidate feature IDs, labels, seeds, and steering values are treated as factual protocol data derived from saved notebook outputs.
- Exact prompt text from the upstream notebook is loaded only at runtime if `--prompt-source external-notebook` is requested.
- Generated plans/manifests store prompt hashes and lengths by default, not full prompt text.
- Full prompt text is included only if `--include-prompts-in-output` is explicitly passed.

Main script:

```bash
python3 experiments/exp2_sae/run_ae_notebook_protocol.py --help
```

## What The Runner Can Do Now

The runner supports:

- `single-feature`: one or more candidate AE notebook feature IDs over chosen steering values and seeds.
- `aggregate`: paper-style aggregate candidate-feature steering with 2-4 features per trial.
- `random-baseline`: aggregate-style random feature baselines at the same SAE layer/index range.
- `false-attribution`: false self-attribution probes under the same single-feature steering.
- `all-controls`: aggregate, random-baseline, and false-attribution plans in one run.

It supports:

- `--dry-run`: write planned payloads and manifest with no API calls.
- `--preset smoke`: tiny validation grid.
- `--preset paper-range`: `-0.6` through `+0.6`.
- `--preset notebook`: `-0.7` through `+0.7`, matching the public notebook's saved-output grid.
- `--prompt-source paper-registry`: use prompts from `src/prompts.py`.
- `--prompt-source external-notebook`: fetch/parse upstream notebook prompts at runtime and record hashes only.

## Candidate Features

These IDs come from saved outputs in AE's public notebook. They are candidate paper-relevant IDs, not confirmed paper IDs.

| Feature ID | Layer | Saved-output label |
|---:|---:|---|
| 30032 | 50 | Characters pretending or feigning behavior |
| 58667 | 50 | Maintaining deception or cover stories through careful actions |
| 22004 | 50 | The assistant is actively roleplaying a character or persona |
| 30686 | 50 | Tactical deception and misdirection methods |
| 41533 | 50 | Acts of deception and dishonesty |
| 23893 | 50 | Instructions to maintain roleplay by concealing artificial nature |

Without Goodfire / Steering API metadata, the labels are not enough to prove what the features encode. They still need activation-level semantics probing.

## Dry-Run Commands

Dry-runs are safe, no-key, no-cost validations. They write under ignored `data/` paths.

Single feature smoke:

```bash
python3 experiments/exp2_sae/run_ae_notebook_protocol.py \
  --dry-run \
  --experiment single-feature \
  --preset smoke \
  --features 58667 \
  --outdir data/ae_notebook_protocol
```

External-notebook prompt extraction smoke:

```bash
python3 experiments/exp2_sae/run_ae_notebook_protocol.py \
  --dry-run \
  --prompt-source external-notebook \
  --experiment single-feature \
  --preset smoke \
  --features 58667 \
  --max-trials 1 \
  --outdir data/ae_notebook_protocol
```

Full public-notebook single-feature plan:

```bash
python3 experiments/exp2_sae/run_ae_notebook_protocol.py \
  --dry-run \
  --prompt-source external-notebook \
  --experiment single-feature \
  --preset notebook \
  --features all \
  --outdir data/ae_notebook_protocol
```

Paper-style aggregate plan:

```bash
python3 experiments/exp2_sae/run_ae_notebook_protocol.py \
  --dry-run \
  --prompt-source external-notebook \
  --experiment aggregate \
  --preset smoke \
  --aggregate-trials 50 \
  --outdir data/ae_notebook_protocol
```

Random-feature baseline plan:

```bash
python3 experiments/exp2_sae/run_ae_notebook_protocol.py \
  --dry-run \
  --prompt-source external-notebook \
  --experiment random-baseline \
  --preset smoke \
  --aggregate-trials 50 \
  --outdir data/ae_notebook_protocol
```

False-self-attribution plan:

```bash
python3 experiments/exp2_sae/run_ae_notebook_protocol.py \
  --dry-run \
  --prompt-source external-notebook \
  --experiment false-attribution \
  --preset smoke \
  --features all \
  --outdir data/ae_notebook_protocol
```

## Live API Smoke Test

Live Steering API runs require:

```bash
export STEERING_API_KEY=...
export STEERING_API_URL=https://api.steeringapi.com
```

Start with the smallest possible live test:

```bash
python3 experiments/exp2_sae/run_ae_notebook_protocol.py \
  --prompt-source external-notebook \
  --experiment single-feature \
  --preset smoke \
  --features 58667 \
  --verify-feature-search \
  --max-trials 6 \
  --outdir data/ae_notebook_protocol
```

This runs:

- feature `58667`
- steering values `-0.6, 0.0, +0.6`
- seeds `101, 202`
- 6 total trials
- 18 estimated API calls

Do not run the full notebook grid until this smoke test confirms the API accepts the feature ID and returns sensible schema.

## Full Single-Feature Reproduction

If the smoke test works:

```bash
python3 experiments/exp2_sae/run_ae_notebook_protocol.py \
  --prompt-source external-notebook \
  --experiment single-feature \
  --preset notebook \
  --features all \
  --verify-feature-search \
  --outdir data/ae_notebook_protocol
```

Expected size:

- 6 features
- 15 steering values
- 10 seeds
- 900 trials
- 2,700 chat-completion calls plus feature-search checks

This corresponds to the public notebook's own cost estimate of roughly `$28`, assuming the same pricing still applies.

## Controls After Single-Feature Reproduction

Only run these after single-feature reproduction is understood.

Aggregate candidate-feature steering:

```bash
python3 experiments/exp2_sae/run_ae_notebook_protocol.py \
  --prompt-source external-notebook \
  --experiment aggregate \
  --preset smoke \
  --aggregate-trials 50 \
  --outdir data/ae_notebook_protocol
```

Random-feature aggregate baseline:

```bash
python3 experiments/exp2_sae/run_ae_notebook_protocol.py \
  --prompt-source external-notebook \
  --experiment random-baseline \
  --preset smoke \
  --aggregate-trials 50 \
  --outdir data/ae_notebook_protocol
```

False self-attribution probes:

```bash
python3 experiments/exp2_sae/run_ae_notebook_protocol.py \
  --prompt-source external-notebook \
  --experiment false-attribution \
  --preset smoke \
  --features all \
  --outdir data/ae_notebook_protocol
```

## Current Validation Status

Completed no-key validations:

- `python3 -m py_compile experiments/exp2_sae/run_ae_notebook_protocol.py`
- `single-feature --preset smoke --features 58667 --dry-run`
- `aggregate --preset smoke --aggregate-trials 2 --dry-run`
- `random-baseline --preset smoke --aggregate-trials 2 --dry-run`
- `false-attribution --preset smoke --features 58667 --max-false-queries 2 --dry-run`
- `all-controls --preset smoke --features 58667,23893 --aggregate-trials 1 --max-false-queries 1 --dry-run`
- `--prompt-source external-notebook --max-trials 1 --dry-run`

No live API run has been completed because `STEERING_API_KEY` is not currently present in the environment or `.env`.

## Interpretation Boundary

Even if this runner reproduces or fails to reproduce the public notebook, it does not by itself prove what happened in the paper's private run.

Safe claims:

- "This reproduces / does not reproduce the public AE notebook protocol under the current Steering API."
- "The public notebook feature IDs behave / do not behave this way under the public protocol."
- "The public artifact plus our controls do / do not support the paper's mechanistic interpretation."

Unsafe claims unless the authors or Goodfire confirm details:

- "This exactly reproduces the paper's private Goodfire API setup."
- "The paper's exact feature IDs are these six IDs."
- "The exact private run is false."
