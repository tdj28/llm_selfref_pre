# Frontier B1: Budget-Dependency Amendment

Status: implementation, not a frozen plan or execution result. The owner
explicitly approved moving $5 from Llama contingency to judging: $120 -> $125
judging and $20 -> $15 contingency, within the same $200 Llama ceiling. The
separate frontier ceiling remains $60. No additional fixture calls are approved.

This is a budget-only dependency amendment **after fixture results were seen**,
but before any frontier target outcomes. It is not an outcome-blind instrument
redesign, human validation, or a new registry preregistration.

## Preserved Evidence

A1 freeze `5398dc657b6af3255e5938539f27255ffbe74b0d` completed 128 fixture
judgments, including 112 scored judgments, with its specified-field gate passing.
The $122.642770 forecast failed the then-frozen $120 judging allocation and stopped
both target panels. Preserve all sources, plans, tests and the raw release at
`data/bilingual_llama_a1/fixture_budget_stop_20261002/` unchanged. B1 does not turn
that historical failure into a pass or repeat the passed fixtures.

The original frontier plan remains
`data/frontier_bilingual_mini/plan_20261002/PLAN.json`, SHA-256
`04e454bfd6eadb2707053eb63454090d2b6703a941ea6ae03ccb0d70ecfb0eca`.
The scientific and accounting rules in
`docs/FRONTIER_BILINGUAL_MINI_PROTOCOL_20261002.md` remain authoritative except
for the explicit dependency substitutions below.

## Narrow Successor

Use `experiments/frontier_bilingual_b1/`, its new frontier plan, and
`out/frontier-bilingual-b1-20261002`. Depend on
`data/bilingual_llama_b1/plan_20261002/PLAN.json` and the new B1 proof, not the old
A1 stopped proof. Both new plans must be source-bound at the same pushed public
freeze, with passing required CI before any paid frontier call.

No scientific choice changes: 6 paired blocks, 72 sources, 144 finals, 576 judge
slots; exact English/Simplified Chinese prompts and request ordering; Astra,
Opus 5.5 and GPT-4.1 model IDs; native parameters and token caps; prices; missing
and capped-text handling; no frontier retries; first-block technical and cost
gates; all estimands, bootstrap draws, seeds, figures and claim boundaries.
The $60 reservation ledger and its provider functions are reused directly.
Analysis is copied unchanged with B1-local imports so its module globals cannot
accidentally invoke A1 qualification. Runner/protocol/qualification copies have
explicit original provenance; no frozen module is patched or monkeypatched.

An exact plan comparison allows only the dependency identity, runtime paths,
source closure, judge dependency's $125 allocation and zero remaining fresh
semantic rounds. It rejects any other changed or added scientific field.
Source closure includes B1, the frozen mini and A1 dependencies, both test files,
parent source/input bindings, original plan, and release provenance.

## Qualification And Accounting

B1 imports all A1 fixture journals byte-for-byte as a prefix. Its validator
accepts the original A1 plan/freeze only for those fixtures; subsequent Llama
targets require the B1 plan/freeze. Its controller recomputes the semantic gate
and the unchanged $122.642770 projection against $125, yielding a new B1 proof
under the new freeze. This is a changed budget decision, not new observations.

Capture that proof **before Llama target judging starts**, while the B1 ledger
is still fixture-only. The frontier capture is offline: no API clients, paid
calls, credentials, GPU operations, or frontier spending-journal entries. It
stores the new B1 proof and exact old receipt bytes in a write-once ignored
`qualification.json`. Resume validates the immutable snapshot, never the later
live B1 target suffix. Snapshot replay retains B1's exact-prefix validation.

The $2.726282 v1 carry plus $3.225516 A1 recorded receipt-based cost bounds total
$5.951798, counted once inside Llama judging; these are not reconciled bills.
The read-only snapshot reconstructs that amount only
to validate the proof. **Zero fixture dollars are charged to frontier**, whose
generation and target judging alone share the unchanged $60 cap. A forecast
pass is not a promise that the complete panels will fit their spending limits.

## Operator Sequence

The parent finishes source/tests and creates the real B1 plan first. Do not
write the final frontier plan until the parent explicitly confirms readiness.
The offline test suite may use an ephemeral parent-plan placeholder; this is
not a canonical plan, freeze, or execution authorization.

```bash
python -m pytest tests/test_frontier_budget_b1.py -q

# Parent/operator only, after B1 plan readiness:
python -m experiments.frontier_bilingual_b1.protocol \
  --b1-plan data/bilingual_llama_b1/plan_20261002/PLAN.json \
  --write data/frontier_bilingual_b1/plan_20261002/PLAN.json
python -m experiments.frontier_bilingual_b1.protocol \
  --check data/frontier_bilingual_b1/plan_20261002/PLAN.json --freeze "$FREEZE"

# After parent imports the A1 prefix and creates its new B1 fixture proof,
# before any Llama target judgments append. Entirely offline; no frontier calls.
python -m experiments.frontier_bilingual_b1.qualification \
  --plan data/frontier_bilingual_b1/plan_20261002/PLAN.json --freeze "$FREEZE" \
  --fixture-gate out/bilingual-llama-b1-20261002/fixture-gate.json

# Separate live authorization, after public freeze/CI and successful capture:
python -m experiments.frontier_bilingual_b1.runner \
  --plan data/frontier_bilingual_b1/plan_20261002/PLAN.json --freeze "$FREEZE" \
  --execute --approved-cap-usd 60 --approval-ref "$APPROVAL_REF" \
  --through-block 1
```

Resume the runner without `--through-block 1` only if its unchanged technical
and forecast gates pass. Credentials, when separately authorized for live use,
may be supplied through the existing explicit local `--env-file`; never copy
them into any artifact. The runner is offline without `--execute` and still
checks both public plan bytes and hosted CI before dispatch.

```bash
python -m experiments.frontier_bilingual_b1.analysis \
  --plan data/frontier_bilingual_b1/plan_20261002/PLAN.json --freeze "$FREEZE" \
  --run-root out/frontier-bilingual-b1-20261002 \
  --out out/frontier-bilingual-b1-analysis-20261002
```

Use a fresh analysis directory; `--allow-partial` preserves all 144 planned
slots and missingness bounds without licensing failed-run dispatch. The panel
still measures fixed prompt/language/model-configuration sensitivity, not
consciousness, language-invariant accuracy, or model sophistication.
