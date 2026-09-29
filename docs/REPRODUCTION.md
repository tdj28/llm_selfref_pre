# Reproducing The Released Results

The root `requirements.lock` records the general Python environment. GPU
runtimes have separate requirements files next to their runners. Reanalysis
uses the saved outputs and makes no model API calls.

## Setup And Checks

```sh
python3 -m venv venv
source venv/bin/activate
python -m pip install -r requirements.lock
make test
make public-audit
make paper
```

`make paper` requires `latexmk` and a TeX installation. `make public-audit`
checks indexed files, secret exclusions and release hashes. It does not
independently validate every statistical calculation.

Do not use `make audit` as a read-only check: several of its commands overwrite
derived files in the releases. Use disposable copies for reanalysis.

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

For new collection, follow the relevant frozen protocol and the team
experiment-integrity guide. These reproduction commands do not authorize
changes to old plans or new paid outcome generation.
