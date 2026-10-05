# Reproducing The Released Results

Use the CPU verification requirements below for released-data reanalysis and
tests on Python 3.10 or 3.12. The older general-purpose `requirements.lock` is
not the environment that produced every release and contains pins incompatible
with Python 3.10. GPU runtimes have separate requirements files next to their
runners. Reanalysis uses saved outputs and makes no model API calls.

## Setup And Checks

Install Poppler's command-line tools (`pdffonts`, `pdftotext`, `pdftohtml`,
and `pdfimages`) for figure checks, alongside the Python environment below.

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
make paper-verify
make paper
```

`make verify` combines the public audit, full tests, source compilation,
current-paper evidence verification, PDF build and whitespace check.
`make audit` is a separate, extended frozen-release check. `make paper`
requires `latexmk` and a TeX installation and builds the current
`paper/main.tex`, not the archived sources under `paper/history/`.
`make public-audit` runs the root `scripts/audit_public_release.py` to check
indexed files, secret exclusions and release hashes. It remains the canonical
public-release check; the imported `scripts/audit_public_files.py` is not run
as a whole-repository audit. Neither scanner independently validates every
statistical calculation.

`make test` collects the complete pytest suite, including the imported paper
verifier unittest cases, later-study directories and function-style tests.
CPU PyTorch exercises tensor tests
without a GPU or model download. Linux/NVIDIA-specific integration tests may
still skip on an unsupported host. Historical recovery fixtures require the
reachable Git history (`git fetch --unshallow` for a shallow clone); they
verify recorded hashes against historical sources, not today's `.gitignore`.
Live source-binding gates remain unchanged.

The dose exposure seed-freshness test runs unchanged against the 29 plans
that existed before its source freeze. Later continuation records intentionally
retain those seeds, so treating every plan in today's checkout as prior data
would give a false failure. The test suite reports the historical execution
and separately rejects unknown seed reuse in the current corpus. Only exact,
hash-bound continuation and release copies are permitted. The same check runs
standalone with `python -m experiments.exposure_seed_history`; it does not
fetch history, change data, or skip the original assertion.

`make compile` checks every tracked Python file without importing modules or
writing bytecode. `make audit` now runs on disposable copies. Direct analysis,
audit and release-builder commands can still overwrite their output directory;
use disposable copies as below. The four CI headline output comparisons are
byte-exact except for bounded float roundoff in the mapping JSON on Python 3.12.
That one comparison uses absolute tolerance `1e-12` and zero relative tolerance;
integer counts, value types, keys, lists, and labels must still match exactly.

## Current Paper Evidence

The completed bilingual Llama B1 pilot has a frozen raw-to-figure analysis.
This offline wrapper additionally rejects symlinked/nonregular inputs before
copying them. It makes no model calls and preserves the original files:

```sh
python scripts/reproduce_bilingual_b1.py \
  --raw-root data/bilingual_llama_b1/completed_20261002/raw \
  --judge-root data/bilingual_llama_b1/completed_20261002/judges \
  --plan data/bilingual_llama_b1/plan_20261002/PLAN.json \
  --freeze c542cb5d72e2514f7dd6cd7fe093f8ccdbba94fb \
  --out /private/tmp/bilingual-llama-reproduced
```

Use a fresh output path, with no symlinked ancestor. On Linux, `/tmp` is
usually suitable; macOS `/tmp` is a symlink, so use `/private/tmp`. Inputs
must be closed snapshots. The wrapper checks complete raw/judge/translation
inventories, inherited fixtures, source bindings and costs before running the
unchanged block-paired analysis. Its manifest binds original input bytes and
derived outputs. Publish only after the command succeeds. See
`BILINGUAL_LLAMA_B1_RESULTS_20261002.md` for scope and interpretation; this is
an automated audit, not independent human validation.

For the separate receipt-level check of all ten language-interaction estimates
and bootstrap intervals:

```sh
python scripts/check_bilingual_b1_arithmetic.py \
  --release data/bilingual_llama_b1/completed_20261002
```

The completed frontier bilingual mini has an offline completed-ledger audit
and exact raw-to-table reconstruction. Local Git history must contain its
public freeze; no API keys, GPU or network calls are needed:

```sh
python scripts/release_frontier_b1.py \
  --verify data/frontier_bilingual_b1/completed_20261002 \
  --freeze c542cb5d72e2514f7dd6cd7fe093f8ccdbba94fb
python scripts/release_frontier_b1.py \
  --reproduce data/frontier_bilingual_b1/completed_20261002 \
  --freeze c542cb5d72e2514f7dd6cd7fe093f8ccdbba94fb \
  --out /tmp/frontier-mini-reproduced
```

The reproduction destination must be fresh and separate from the release.
The verifier checks source bindings, receipts, hashes and exact numerical
tables. Regenerated PDF timestamps need not match. Original raw files are
never opened for writing. See `FRONTIER_BILINGUAL_RESULTS_20261002.md` for
the six-block uncertainty and measurement limits. The manuscript presents
this panel separately from the original four-model experiment.

The later crossed Llama qualification has its own read-only raw-to-decision
check and optional descriptive figure regeneration:

```sh
python scripts/reproduce_instruction_qualification.py
python scripts/reproduce_instruction_qualification.py --out /tmp/qualification-reproduced --figures
```

The output directory must be new and outside the release. The verifier checks
the full manifest, frozen source-bound plan, raw generations, judge receipts,
byte-exact runtime decision/table and cost arithmetic. It makes no model or
API calls and does not write locks into the released judge ledger. See
`INSTRUCTION_STATE_QUALIFICATION_RESULTS_20261001.md` for the failed guards
and limits; the manuscript retains the qualification failure, not a completed
internal-intervention experiment.

The current manuscript lives in `paper/`. Its packaged evidence and verifier
sources retain their pinned bytes and repository-relative paths. From the
repository root, `make paper-verify` runs the complete read-only check list
in the `Makefile`, including these core checks:

```sh
python scripts/verify_evidence.py
python scripts/verify_figure_values.py
python scripts/verify_figure_presentation.py
python scripts/verify_rubric_audit.py
python scripts/verify_source_alignment.py
python scripts/verify_source_jlens_table.py
python scripts/verify_ensemble_alignment.py
python scripts/verify_fidelity_calibration.py
python scripts/verify_completed_extensions.py
python scripts/verify_reporting_bound.py
python scripts/uncertainty_sensitivity.py --check
python -B reviews/reproducibility/run.py --verify-only
```

The same target checks the modern Gemini/Opus and Qwen3.8 panels against their
released rows, including paired contrasts and the different primary interval
families. Its repeated-answer check also replays response and judge receipts,
the block-level analysis and the figure bindings. These checks preserve missing
judgments; they do not establish the accuracy of an automated label. No API
keys or model downloads are needed.

The mapping-scaled steering follow-up has an additional full replay:

```sh
python scripts/verify_dose_followup.py --full --require-pinned
```

This checks the completed release against its published commit, reconstructs
the paired analysis with the historical sources, and verifies the paper's
values and figure. The saved worker analysis remains canonical; the release
records the original exact-replay failure and eight floating-point differences
of at most two ULPs, with unchanged estimates and decisions. The default
`paper-verify` check verifies hashes and bindings without this full replay.

These checks use the pinned CPU dependencies, Poppler tools and local Git
history. They need no sibling checkout, credentials, GPU, network access or
TeX installation, and fail on stale
generated evidence or mismatched manuscript bindings. They check packaged
hashes, arithmetic, figures, tables and uncertainty summaries; the final
command verifies the archived reproducibility bundle rather than replaying
its raw-data audit. They do not establish judge-label truth, independent
human validation or a newly qualified experimental assay. Do not regenerate
evidence or edit hash-bound verifier sources merely to make a check pass.

CI runs `make paper-verify` on Python 3.10 and 3.12, checks that it leaves
tracked paper/evidence files unchanged, and runs the imported verifier tests
as part of the full root pytest suite. PDF compilation remains the separate
`make paper` step included in local `make verify`.
The historical workflow is itself a bound study input. When
`GITHUB_ACTIONS=true`, Make first prepares the CI environment: it installs
Poppler, and for the paper job fetches full Git history and installs the
pinned CPU dependencies. The verification then runs offline. This preparation
does not run during ordinary local checks or change the checked-out revision.

The completed-extension check binds the bilingual, frontier, qualification and
operator-matching summaries used in the manuscript. It does not replace the
raw-to-summary commands for those studies. The reporting-bound check enumerates
binary count pairs compatible with the rounded TruthfulQA means in Berg et al.;
it is conditional on one paired binary score per question, not a reconstruction
of their unavailable scores or test procedure.

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
- [Historical human-coding handoff](../provenance/planning/HUMAN_CODING_HANDOFF.md)
- [Full artifact inventory](../DATA_ARTIFACTS.md)
- [Later-study status and evidence boundaries](STUDY_INVENTORY.md)

For new collection, follow the relevant frozen protocol and the team
experiment-integrity guide. These reproduction commands do not authorize
changes to old plans or new paid outcome generation.
