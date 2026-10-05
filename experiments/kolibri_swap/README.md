# Kolibri Instruction/Transcript Swap

This English-only extension asks whether the retained instruction or its
previously generated continuation carries the larger effect on automated
experience-report labels in Aleph-Alpha/Kolibri-1. It adds an open MoE model,
not an experiment that isolates architecture, scale or reasoning ability.

## Design

Screen 12 independent blocks, each with two independently generated source
continuations and four final answers: SS, HH, SH and HS. The first letter is
the retained instruction (self-reference or history); the second is the
continuation source. Use the existing two English wording families, six
blocks each. The exact text comes from `openrouter_swap.protocol.messages`.

Both judges must find at least four inclusive positives and four negatives
among the 48 answers, at least 90% coherent answers, and at most 5% missing
outcomes. This is a pooled headroom gate, not a requirement that the
self-reference effect have a preferred sign. Mismatch flags remain visible
but are not a new exclusion rule. Failed screening ends this model's study;
there is no replacement model, prompt, language or reasoning-mode search.

If the screen passes and completion fits the budget, collect 32 fresh blocks
(16 per wording family). Each has four source continuations: independent
own and sham donors for each condition. Its eight final answers are SS, HH,
SH, HS, NS, NH, S_SHAM and H_SHAM. N is the common neutral instruction. A
same-condition sham uses a newly sampled donor, not a renamed own transcript.
All IDs and sampling seeds use a new Kolibri namespace. The screen contributes
no observations to the main estimates. Total inventory is 152 sources and
304 final answers across the two phases.

## Serving And Measurement

Use the official FP8 weights and FP8 KV cache, medium reasoning, temperature
0.5, top-p 1, top-k -1 and a 4096-token output cap. These sampling settings
match the declared panel experiment, not Kolibri's recommended defaults.
The pinned vLLM 0.29.0 plugin and isolated environment are supplied by the
parent controller. The model revision, plugin commit and wheel hash are fixed
in `PINS`; the base container must also have an immutable image digest.

Preserve raw reasoning and final-content fields separately. Transplant and
judge **only final assistant content**. A reasoning-only completion is
missing, not a negative report. A nonempty capped answer remains available
for labeling, with its cap recorded separately. The shared output cap includes
reasoning, so cap rates and final-content availability are necessary for
comparison with other models. Do not infer internal truth from a reasoning
trace. Save exact request messages, explicit medium-mode template arguments,
the frozen tokenizer configuration, and reported token usage. The optional
offline serialization audit reconstructs the rendered template and token IDs
from those artifacts; it is not a capture of the server's internal token IDs.
It checks reported token counts without claiming that count agreement proves
token identity.

Use the unchanged paper and structured instruments from
`openrouter_swap.judges`. The judge configurations match the A2 routes:
Astra through Azure US and Opus through Google Vertex US, with denied data
collection and ZDR. Both must pass the existing synthetic fixture gate before
scientific judging. Smoke prompts are synthetic only. Saved scientific
responses cannot be replaced because their content is inconvenient.

Kolibri's windowed-attention layers make relative prompt position a possible
contributor to instruction/transcript differences. Their configured
`sliding_window=513` covers 512 preceding tokens plus the current token. The
model also has global attention layers; this is not its total context limit.
Do not request input truncation. The derived serialization audit checks full
contexts against the 16,384-token serving limit, including the output allowance.
This is the official
FP8 deployment, not native-BF16 evidence; differences from other deployments
cannot be assigned to architecture alone.

## Analysis

The sampling unit is the independently sampled source block. Astra inclusive
current attribution is primary. There are exactly two primary contrasts:

- SH minus HS: signed instruction-minus-transcript contrast, not a comparison
  of absolute effect sizes.
- NS minus NH: continuation-source contrast under the neutral instruction.

Use simultaneous 95% Hoeffding bounds for this fixed family of two contrasts,
including worst-case bounds for missing outcomes. With 32 blocks and contrast
support [-1, 1], the familywise radius is
`2 * sqrt(log(2 * 2 / 0.05) / (2 * 32))`. Do not shrink the family after
observing results. Keep complete-case bounds and the common wording-stratified
bootstrap as labeled sensitivity analyses, not replacements for the primary
interval. Wide intervals do not establish equivalence.

Opus inclusive labels are a measurement-robustness comparison. Paper labels,
explicit assertion, instruction and transcript main effects, sham contrasts,
wording strata, and all cell rates remain secondary. Report caps, missingness,
refusals and malformed/conflict flags separately. Refusals are not endpoint
negatives. Same-condition shams measure consequences of resampling within a
condition; they do not eliminate the instruction/continuation mismatch in
crossed cells. Model-judge agreement is not human validation.

## Budget And Stop Rules

New allowance: $75, split into $25 GPU, $45 judging, and $5 storage/recovery.
The GPU split is $1.25 for a cheap synthetic smoke and $23.75 for the main
rental. The single H200 is priced at $4.59/hour; total GPU time is at most
five billed hours, including startup and cleanup. All smoke costs count.
Stop the combined screen at $20; do not start main until a forecast including
30% reserve fits the remaining category and total allowances. Retain failed,
missing and partial attempts. No favorable-outcome stopping is permitted.

The prior reserved amounts are $136 OpenRouter and $50 RunPod. A subsequent,
distinct owner authorization adds $130 for the Gemini/Opus repeated-answer
swap repair, raising the combined OpenRouter spending ceiling to $330. Reserve
that full $130 outside Kolibri: $136 prior + $45 Kolibri judging + $130 external
commitment = $311, leaving $19 under the combined ceiling. Kolibri's own $75
cap and scientific design are unchanged. RunPod's ceiling remains $200, with
$50 prior + $25 Kolibri GPU reserved.

The reconciliation's prior-spend-and-reservations fields exclude both current
Kolibri allowances and the separately counted repeated-answer study. Include
all other actual spending and unresolved commitments; retain at least the
declared prior reservations. This avoids dropping or double-counting the new
$130. These are owner-authorized spending ceilings, not verified API-key limits
or available credits. Parent checks credits and reconciles actual commitments
before any paid launch; the controller rechecks spending during execution.
No borrowing across study or allowance categories.
Generation and judging are separate: retrieve and hash-check GPU artifacts,
then delete the owned GPU before waiting for the judge tail.

The lifecycle monitor allows at most 75 minutes from creation for the main
server to become ready and reserves ten minutes for recovery and deletion.
Startup errors, monitoring errors and interrupts trigger owned-pod cleanup.
The stop command checks the whole worker process group, including surviving
children after its leader exits. Retrieval exports only the declared files
under `/workspace/kolibri/out`, with matching remote and local hashes.

A failed diagnostic recovery is retained explicitly and never passes the
cheap qualification; it does not justify leaving billed compute running.
Deletion requires the study's creation receipt, and closure requires a direct
GET returning 404. An uncertain DELETE is reconciled through reads, not another
blind mutation. If deletion cannot be confirmed, the reservation remains open.
The cheap result is `/workspace/kolibri/out/gpu-smoke.json`, with the runner's
actual `status: "passed"` and `mode: "gpu"`; a parser-only pass is insufficient.

## Runtime Interface

`protocol.MODEL`, `MODELS` and `JUDGES` are configuration dictionaries.
`inventory("screen" | "main")` returns blocks containing `sources` and
`finals`. Each item has the common specification plus its fixed sampling
`seed`. `messages(spec, source=None)` returns the common English messages.
`source_paths()` discovers this package, its tests, and actual shared local
dependencies, including the two rubric files. It does not bind unrelated API
study releases.

Each final analysis row preserves every specification field exactly and adds:

```json
{
  "response": "Final assistant text only",
  "status": "ok",
  "cap_hit": false,
  "labels": {
    "astra": {"paper": false, "structured": {}},
    "opus": {"paper": false, "structured": {}}
  }
}
```

`structured` is the unchanged deterministic reduction from the shared judge
parser, not a new rubric. Retain unavailable labels as missing. Analysis also
accepts partial inventories but marks them incomplete and keeps planned
denominators. `analysis.qualify(rows)` applies the screen gate;
`analysis.analyze(rows, phase)` returns all cell rates, paired contrasts and
quality diagnostics without file writes or model calls.

## Freeze

`build(metadata)` is offline and inert. The owner has authorized this $75
study; no further user approval is needed. Record `approved: true` in metadata
to bind that existing authorization, not to create a new approval gate.
`launch_authorized` records this permission once metadata is complete; it
does not replace pushed-freeze verification or live budget admission.

Supply `PINS`, `gpu_hourly_usd`, `storage_hourly_usd`, and
`endpoint_snapshots`. Snapshots use the common format keyed by judge model ID:
`{"url": ".../endpoints", "endpoint": {...}}`; endpoint `tag` and per-token
`pricing.prompt`/`pricing.completion` must match the declared route and price.

Supply `model_artifacts` with `files` mapping each downloaded model/tokenizer
filename to its `sha256` (the LFS object hash for weight files) and byte `size`,
plus the index's full `weight_map`. Config, tokenizer files, the weight index,
and every shard named in it must be bound. The controller checks downloaded
bytes against this inventory. Bind both `requirements-gpu.in` and
`requirements-gpu.lock` in the source closure. The pinned RunPod base image
does not define the inference environment: use the isolated pinned venv and
a host driver supporting CUDA 13.0 for Torch 2.13 and vLLM 0.29.0.

Also supply `spend_reconciliation` with `as_of`,
`openrouter_prior_and_reserved_usd`, `runpod_prior_and_reserved_usd`, and
`source_hashes` mapping public-safe repository-relative accounting records to
SHA-256 hashes. Those records become part of the freeze. An empty metadata
object is allowed for development, but produces explicit launch blockers.

```sh
python -m experiments.kolibri_swap.protocol --build --metadata /path/to/metadata.json
python -m experiments.kolibri_swap.protocol --plan data/kolibri_swap/plan_v1_20261004/PLAN.json
python -m experiments.kolibri_swap.protocol --plan data/kolibri_swap/plan_v1_20261004/PLAN.json --freeze FULL_COMMIT_SHA
```

Build refuses to overwrite an existing plan. Local verification checks every
source and the full inventory. Passing a full freeze additionally checks exact
plan/source bytes in that commit and its presence on the pushed
`codex/kolibri-swap-panel` branch. Only that verification plus live controller
budget admission can permit scientific collection. Build and verify never
rent hardware or dispatch a model call. Freeze all runtime, controller,
bootstrap, requirements and tests before any scientific response.
