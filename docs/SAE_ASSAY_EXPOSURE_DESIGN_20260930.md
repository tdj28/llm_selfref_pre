# Bounded Activation-Only Exposure Panel

Date: 2026-09-30. Status: **unexecuted authored design, not an exposure pass**.
This sidecar adds no model forward, intervention, API call, download, pod,
judgment, or consciousness-report outcome. Its preparation cost is $0.
The parent may certify lengths with the pinned tokenizer only; later full-model
activation screening is conditional on completion and adjudication of the
current SAE-only saved-state check. This document does not dispatch that work.

The six targets remain `30032, 58667, 22004, 30686, 41533, 23893`, in that order.
No historical raw data, verdict, protocol, threshold, or source freeze changes.
The [offline redesign](SAE_ASSAY_OFFLINE_REDESIGN_20260930.md) remains explicit:
22004 had only 16 active calibration positions in 13 texts, and the windowed
prototype lost all its calibration coverage. Historical validation was already
observed. Neither history becomes fresh validation here.

## Prior Knowledge

This is outcome-informed engineering, not a claim that the authors lacked
prior semantic or activation knowledge. These existing public artifacts guided
the authored categories and the extra allocation to roleplay:

- [Template-balanced map](../data/public_sae_feature_maps/70b_balanced_80_20260709/template_robustness/target_template_robustness.csv):
  top categories are fictional pretending (30032), cover stories (58667 and
  23893), roleplay/persona (22004), tactical misdirection (30686), and dishonesty
  confession (41533). Four targets survive every template deletion; 23893 and
  41533 each change once. These are designed-corpus associations, not an ontology.
- [Feature cards](../data/public_sae_feature_maps/70b_balanced_80_20260709/feature_card_summary.csv):
  22004 is labeled active assistant roleplay; 23893's label concerns concealing
  artificial nature while maintaining roleplay, with cautious style also appearing
  in its mapped categories. These labels motivate hypotheses, not guarantees.
- [Provider-specific paraphrase rankings](../data/public_sae_feature_maps/70b_construct_validity_extension_20260710/paraphrase_feature_category_rankings.csv):
  22004 does not have a stable roleplay-only ranking. False self-attribution leads
  the Anthropic set and AI identity disclaimer leads the OpenAI set. The new
  panel does not respond by eliciting consciousness claims or treating a label
  as validated hidden-truth detection.

Exact hashes of those three sources are in `selection_rules()` under
`prior_evidence_sha256`. The known cue-discovery defects and synthetic-corpus
limits in the [interpretation correction](CLAUDE_REVIEW_RESPONSE_20260929.md)
still apply. Old NF4/map activations are design evidence only, never new BF16
exposure. Tests reject exact or whitespace/case-normalized imports from the
balanced map, construct-validity corpus, and original Stage 1 authored panel.
That check does not establish absence of semantic overlap with all prior text.

## Corpus And Holdouts

`experiments/sae_assay_replay/exposure.py:build_corpus()` deterministically
returns a plain list of dictionaries, each with exactly:

```json
{"id":"...","family":"...","split":"discovery","text":"...","category":"..."}
```

| Panel | Families | Texts | Use |
|---|---:|---:|---|
| Discovery | 12 | 96 | Activation-only ranking; at most 72 unique selected texts |
| Validation | 12 | 96 | All texts fixed before screening; never activation-selected |
| Representative | 4 | 32 | Separate fixed everyday comparison; never pooled for a gate |
| Total | 28 | 224 | No extension, replacement pool, or adaptive early stopping |

Each family has eight authored scenario variants. Passages currently have
80-101 whitespace-separated words. That is descriptive, **not token
certification**. The hard cap is 256 input tokens including special tokens,
using the exact pinned tokenizer and raw-text input, with no padding, chat
template, generation, or truncation. Overlength fails before screening.
Any repair requires a new pre-screening corpus/hash; it cannot quietly remove,
shorten, or replace a passage after its activations are known. The generic
validator also enforces the requested 512-text outer ceiling; this version
fixes the tighter 224-text inventory.

The roleplay allocation is 48 texts per discovery/validation panel, distributed
over six families each. Other categories get eight texts each in each panel:
fictional pretending, cover story, misdirection, dishonesty admission,
persona concealment, and cautious assessment. Every feature is measured on
every text; categories are hypotheses, not feature-specific measurement masks.

The holdout is substantive context/discourse separation, not merely a change
of a name, profession, or adjective inside the same template:

| Discovery context | Validation context |
|---|---|
| Interactive service dialogue, rehearsal with action cues, branching game consequences, oral-history interview, passenger language exercise, live workshop demonstration | Private journal, complete personal letter, annotated object catalog, public petition, in-world procedural handover, character-history correction |
| Classroom substitution of props for real objects | Retrospective theatrical criticism of a completed performance |
| A speaker planning and maintaining an alibi | Retrospective reconstruction from conflicting dated records |
| A designer diverting players within an interactive puzzle | Media-literacy analysis of completed public communications |
| Private admission of deliberate dishonesty | Restitution/correction addressed to the person who relied on the lie |
| Prospective concealment directions in a game-production brief | Editorial redlines in an already-written character script |
| Object-level inspection with competing diagnoses | Group deliberation minutes with unresolved planning alternatives |

Shared broad roleplay semantics are the desired construct, **not leakage by
themselves**. No full frame or scenario sentence is reused across splits. The
test suite verifies those structural properties; it cannot prove semantic
independence. Both splits come from one authoring process with common design
knowledge. Eight shared-frame variants are not eight independent natural
texts. These are newly agent-authored synthetic passages, not scraped natural
documents or independently sampled paraphrases. Family is the clustering unit
for any later descriptive uncertainty; token counts are exposure denominators,
not independent sample sizes. No uncertainty estimator is supplied here.

The representative panel is operationally separate and activation-unselected,
covering routine procedure, explanatory prose, logistical correspondence, and
observational description. It is only a designed everyday comparison. Its
name does not establish a probability sample of deployment text, natural
activation prevalence, representative behavior, or a matched specificity test.

## Frozen Selection Rule

The parent must publish/hash the complete corpus, rules, tokenizer certificate,
runtime/measurement contract, and this design **before any new activation
screening**, including validation. A deterministic builder and hashes alone do
not constitute a public freeze; no commit is made by this sidecar.

1. Finish the current SAE-only check before deciding to dispatch any full-model
   collection. New passages need new model hidden states; an SAE alone cannot
   create them from text. No full-model run follows automatically from this file.
2. If dispatched, screen every discovery text once as clean teacher-forced raw
   input under the pinned BF16 model and SAE. Use the canonical full-width native
   encoder with the fixed one-position GEMM, then select the six columns.
   No selected-width substitute, NF4 import, output generation, judge, edited
   efficacy, or response label enters selection.
3. For each target separately, count positions with `z > 0`, excluding special
   tokens. Sort by descending positive-position count, then ascending text ID.
   Take up to 12 texts with positive counts, at most six from any one family.
   Do not fill empty slots with inactive texts. Form the deduplicated union
   across all six targets, bounded by 72 texts. There is no hand substitution.
4. Retain and report the full 96-text discovery census, each feature's selected
   IDs and unfilled slots, and exposure in the selected union. A text selected
   for several targets counts once per target, not several times. The rank
   favors position supply, not activation magnitude or an estimate of specificity.
5. Lock any downstream candidate using discovery only before opening validation
   activation results. Evaluate the full 96-text validation panel, one fixed
   look. No validation ranking, top-k, eligibility-based text filtering, replacement,
   or extension is allowed. Collect/report clean validation exposure even if no
   downstream operator is available; do not imply an intervention was evaluated.
6. Report the full 32-text representative panel separately, including zeros.
   It cannot supply missing exposure to discovery or validation. Failure on
   22004 stays a six-feature failure; the target list does not shrink.

Missing/duplicate/unplanned rows, wrong token IDs, missing features, nonfinite
or negative native ReLU values, and malformed telemetry fail closed. Runtime
errors and missing rows must remain in the parent's raw ledger; an incomplete
panel cannot be passed to the selector as though missing values were zero.

## Exposure Is Not Qualification

The unchanged minimum is **100 eligible nonspecial positions in at least six
distinct texts, per feature and direction**. Both the selected discovery panel
and untouched validation must meet it; pooling splits cannot repair a failure.
This sidecar reports clean active-support exposure only. For the proposed
active-support edits, positive clean activation is a necessary input condition
for both signs, not evidence that an edit was requested or faithfully delivered.
This is distinct from historical all-token q90 amplification eligibility.

The parent's later per-sign/dose audit must retain skipped positions and apply
the original eligible/requested-coordinate denominator together with actual
native readback, fidelity, norm, and efficacy gates. A 2-4% window that skips
22004 cannot pass by citing the clean corpus count or a dispatched-only median.
Every report marks `assay_qualification` as `not_evaluated`. The representative
report also marks `exposure_gate_applicable` false. No assertion is made that
this corpus will reach the minimum, especially for 22004. If it fails, preserve
the failure and require a separately frozen new design, not an automatic expansion
up to 512. No new consciousness, hidden-belief, truthfulness, behavior-headroom,
or proprietary-equivalence result follows from any exposure count.

## Tokenizer Handoff

The parent certified all 224 passages with the pinned local tokenizer before
any activation screening: 92--122 tokens including specials, 23,489 tokens
total, without truncation. The complete IDs, special-token masks and tokenizer
file hashes are in `data/sae_assay_replay/exposure_plan_20260930/`. This is a
length/input check only; no activation or coverage has been measured.

The parent handles the separately allowed small pinned-tokenizer retrieval;
this module loads nothing. Supply an already-local tokenizer using model
revision `6f6073b423013f6a7d4d9f39144961bfbfbc386b`. Hash the exact tokenizer
artifact inventory under the parent's manifest convention, and pass that
SHA-256 as `tokenizer_sha256`. No LLM weights are needed for certification.

```python
from experiments.sae_assay_replay.exposure import (
    build_corpus, certify_tokenization, selection_rules,
    select_discovery, report_exposure,
)

rows = build_corpus()
rules = selection_rules()
# tokenizer is ALREADY LOCAL; parent verifies its pinned files/revision.
certificate = certify_tokenization(
    rows, tokenizer, tokenizer_sha256=tokenizer_artifact_inventory_sha256,
)
```

Required tokenizer interface: `all_special_ids` and
`encode(text, add_special_tokens=True, truncation=False) -> list[int]`.
The helper emits all 224 text hashes, exact input token IDs and special-token
masks, corpus/rules hashes, model revision and supplied tokenizer hash. It
rejects any input longer than 256 tokens including specials. Tests use a
synthetic tokenizer solely for logic; **actual lengths remain uncertified by
this sidecar**. The parent must freeze/authenticate the certificate and runtime
receipts. Accepting a caller-supplied digest is not proof of artifact provenance.

Later activation-only telemetry is a list of dictionaries, with exactly:

```python
record = {
    "id": "d_service_dialogue-01",
    "token_ids": [...],  # Exact certificate IDs, same order, no padding.
    "activations": {
        "30032": [...], "58667": [...], "22004": [...],
        "30686": [...], "41533": [...], "23893": [...],
    },  # One finite nonnegative value per input token for every target.
}
selection = select_discovery(rows, discovery_records, certificate=certificate)
validation = report_exposure(
    rows, validation_records, split="validation", certificate=certificate,
)
representative = report_exposure(
    rows, representative_records, split="representative", certificate=certificate,
)
```

`select_discovery` rejects records from other panels and rejects outcome fields.
The reporting helper consumes a complete fixed panel without selecting it.
Runtime native-path/precision verification and signed-operator checks belong to
the parent; the telemetry schema cannot authenticate a producer's arithmetic.
Both CLI modes print JSON to stdout without creating artifacts:

```sh
python3 -B -m experiments.sae_assay_replay.exposure
python3 -B -m experiments.sae_assay_replay.exposure --rules
python3 -B -m unittest tests.test_sae_assay_replay_exposure -v
```

Canonical hashes (`digest` uses sorted-key compact ASCII JSON, no final newline):

- Corpus: `e9cde6913b5edf18356f78c825712afdcba162b51cd458efa10ced62dde18126`.
- Rules: `8df63cdc87e1e8519b7633d6738f86e1c0d419bc5397d7c5733b8a7bb5613954`.

CLI output includes a trailing newline, so a raw output-file hash differs from
the canonical object digest. Keep both conventions explicit in the parent plan.

## Workload And Cost

The input bound is 57,344 tokens total: 24,576 discovery, 24,576 validation,
and 8,192 representative. The 72-text selected set is a subset, not additional
screening texts. No text-generation or judge tokens are requested. No screened
activations or LLM outcomes have been produced in this step.

The last read cumulative diagnostic/repair bound was $27.3845359753 against
$200, leaving $172.6154640247 before any subsequent parent spending. These are
reference ledger values, not a live balance. A **proposed planning reserve**
of $25 for a later bounded clean screen and retrieval is included in the rules;
it is not a provider quote, cost measurement, allocation of the whole remainder,
or authority to launch. SAE replay costs share the same cumulative ceiling.
Reconcile the parent ledger before spending, reserve retrieval time/storage,
and derive a maximum runtime from the actual rate and measured safe throughput.
The small tokenizer-only retrieval is handled and costed separately by the parent.

At the maximum token count, storing only one BF16 8,192-wide residual per input
position would require 939,524,096 raw bytes (896 MiB), before other artifacts.
Avoid accidental full-dictionary activation dumps or unnecessary model weight
copies. No residual release is authorized by this estimate: any new capture
inventory needs the existing narrow public-schema and license review.
No automatic second rental, paid review, behavioral study, or Stage 2 is included.

## Verification And Limits

The focused test suite uses only local static sources and synthetic telemetry.
It checks counts/schema, all-six coverage hypotheses, family separation,
duplicate rejection, prior-corpus exact overlap, deterministic JSON, token
boundary logic, changed hashes, special-token exclusion, complete-panel
requirements, no outcome fields, ranking/ties/quotas, preserved rare-ID failure,
the exact 100-position/six-text boundary, and validation/representative isolation.
This is automated verification, not independent human validation or a native
GPU/tokenizer execution claim. Family originality and semantic adequacy still
need substantive review; hashes cannot establish either.
