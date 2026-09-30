# Reproducing The Released Results

Use the CPU verification requirements below for released-data reanalysis and
tests on Python 3.10 or 3.12. The older general-purpose `requirements.lock` is
not the environment that produced every release and contains pins incompatible
with Python 3.10. GPU runtimes have separate requirements files next to their
runners. Reanalysis uses saved outputs and makes no model API calls.

## Setup And Checks

```sh
python3 -m venv venv
source venv/bin/activate
python -m pip install -r requirements-ci.txt
# Linux: use the CPU wheel index. On macOS omit --index-url and its URL.
python -m pip install -r requirements-ci-torch.txt --index-url https://download.pytorch.org/whl/cpu
python -m pip check
make test
make compile
make public-audit
make audit
make paper
```

`make paper` requires `latexmk` and a TeX installation. `make public-audit`
checks indexed files, secret exclusions and release hashes. It does not
independently validate every statistical calculation.

`make test` collects the complete pytest suite, including the later-study
directories and function-style tests. CPU PyTorch exercises tensor tests
without a GPU or model download. Linux/NVIDIA-specific integration tests may
still skip on an unsupported host. Historical recovery fixtures require the
reachable Git history (`git fetch --unshallow` for a shallow clone); they
verify recorded hashes against historical sources, not today's `.gitignore`.
Live source-binding gates remain unchanged.

`make compile` checks every tracked Python file without importing modules or
writing bytecode. `make audit` now runs on disposable copies. Direct analysis,
audit and release-builder commands can still overwrite their output directory;
use disposable copies as below. The four CI headline output comparisons are
byte-exact except for bounded float roundoff in the mapping JSON on Python 3.12.
That one comparison uses absolute tolerance `1e-12` and zero relative tolerance;
integer counts, value types, keys, lists, and labels must still match exactly.

## Prompt And Transcript Study

```sh
mkdir -p out
WORK=$(mktemp -d out/causal-reanalysis.XXXXXX)
cp -a data/causal_transplant/confirmatory_v1_20260709/. "$WORK"/
venv/bin/python experiments/causal_transplant/analyze_causal_transplant.py \
  --outcomes "$WORK/outcomes.jsonl" \
  --judgments "$WORK/judgments_paper.jsonl" \
  --judge-key openai:gpt-4o-mini-2024-07-18 \
  --task paper --bootstrap 5000 \
  --outdir "$WORK/analysis_openai_paper"
venv/bin/python experiments/causal_transplant/audit_headline_point_estimates.py "$WORK"
```

The protocol defines independent calibration draws, lexical-variant clusters
for the factorial and paired source-text blocks for the transplants. Trial
indices alone do not establish pairing. See
[CONFIRMATORY_PROTOCOL.md](CONFIRMATORY_PROTOCOL.md).

## Public Llama Steering

```sh
mkdir -p out
WORK=$(mktemp -d out/llama-steering-reanalysis.XXXXXX)
cp -a data/public_sae_consciousness_gating/confirmatory_v1_20260710/. "$WORK"/
venv/bin/python experiments/exp2_sae/analyze_public_sae_consciousness_gating.py \
  --generations "$WORK/generations.jsonl" \
  --local-judgments "$WORK/judging/local_llama_judgments.jsonl" \
  --external-judgments "$WORK/judging/external_judgments.jsonl" \
  --direct-labels "$WORK/judging/direct_answer_labels.jsonl" \
  --outdir "$WORK/analysis"
venv/bin/python experiments/exp2_sae/audit_public_sae_consciousness_headlines.py \
  --generations "$WORK/generations.jsonl" \
  --local-judgments "$WORK/judging/local_llama_judgments.jsonl" \
  --analysis-dir "$WORK/analysis"
```

Do not pool the literal and RMS-calibrated coefficient scales. The prospective
full grid is primary; the older adaptive n=20 study is not a replacement.

## Coordinate-Delivery Diagnostics

The September repair is a separate engineering study, not another
consciousness-report outcome. Rebuild its receipt audit, frozen gate
calculations, independent NumPy coordinate arithmetic, corpus census and four
figure sets from the released raw files:

```sh
mkdir -p out
WORK=$(mktemp -d out/repair-reanalysis.XXXXXX)
python -m experiments.sae_assay_repair.reproduce \
  --run data/sae_assay_repair/coordinate_delivery_20260930 \
  --plan data/sae_assay_repair/plan_20260930/PLAN.json \
  --out "$WORK/result"
```

This command reads the release in place, checks its entire manifest before and
afterward, and writes only to the new output directory. It needs the CPU
dependencies above, but no model weights, GPU, credentials or API calls. Use
the result-release Git revision if later source changes trigger source-drift
checks; do not disable those checks. The runtime was separately frozen at
`b7c4d7f5fba80dd2b067c200fdf2f322c80c3cae` before these outcomes.
It retains the original failed complete audit and separately runs the
[diagnostic-list ordering correction](SAE_ASSAY_REPAIR_AUDIT_AMENDMENT_20260930.md).
The corrected comparison changes no scientific result or criterion.

All 544 clean BF16 residual captures have an exact, hash-pinned schema and
source-text inventory checked by `make public-audit`. The capture allowance
does not permit arbitrary `.safetensors` or model weights. See the
[result and limitations](SAE_ASSAY_REPAIR_RESULTS_20260930.md), including the
distinction between coordinate equality, native re-encoding and semantic
intervention. Plot/PDF metadata may differ between rebuilds; raw release bytes
must not change.

## Offline Assay Redesign

The additive saved-data redesign has a separate, CPU-only entry point:

```sh
python -m experiments.sae_assay_repair.reproduce_feasibility \
  --run data/sae_assay_repair/coordinate_delivery_20260930 \
  --out out/new-offline-redesign
```

It writes a fresh directory with the failure census, conditional linear
bounds, two prototype variants and figures. It checks the original manifest
before/after, never loads weights and does not count historical validation as
fresh validation. See [scope and assumptions](SAE_ASSAY_OFFLINE_REDESIGN_20260930.md).

## Gemma Scope

```sh
mkdir -p out
WORK=$(mktemp -d out/gemma-reanalysis.XXXXXX)
cp -a data/gemma_scope_9b/confirmatory_v1_20260711/. "$WORK"/
venv/bin/python experiments/exp2_sae/analyze_gemma_scope_9b.py "$WORK"
venv/bin/python experiments/exp2_sae/audit_gemma_scope_9b_headlines.py "$WORK"
```

The primary intervention uses a direct instruction-tuned SAE. The
pretrained-to-instruction-tuned transfer gate failed; the all-layer atlas is
exploratory. Do not rebuild the original release manifest as a check: it binds
the release to its historical result commit.

## Other Studies

- [Feature probes](../experiments/exp2_sae/PUBLIC_SAE_FEATURE_PROBES.md)
- [J-lens v1](LLAMA70B_SAE_JLENS_RESULTS.md)
- [J-lens v2 and its failed gate](LLAMA70B_SAE_JLENS_V2_RESULTS.md)
- [Human-coding handoff](HUMAN_CODING_HANDOFF.md)
- [Full artifact inventory](../DATA_ARTIFACTS.md)
- [Later-study status and evidence boundaries](STUDY_INVENTORY.md)

For new collection, follow the relevant frozen protocol and the team
experiment-integrity guide. These reproduction commands do not authorize
changes to old plans or new paid outcome generation.
