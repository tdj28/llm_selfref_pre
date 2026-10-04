# Stage T Design Notes (Draft, 2026-10-02)

Outcome-free implementation proposal, not an execution plan, authorization, or
freeze. No C outcomes were inspected for this draft. The locked structure comes
from `docs/STEERING_FIDELITY_PROTOCOL_20261002.md`; choices below marked proposed
must be resolved before T outcomes. No private correspondence is reproduced.
Q, T1, C1, translation, and own-output context items remain deferred.
Passing C pressure qualification is a dependency for T as a whole. There is
no E-only fallback; an unavailable/failed pressure qualification does not
authorize launching a reduced T study.

Implementation note: the draft inventory, paired analysis and synthetic
instrument fixtures now exist in `experiments/steering_fidelity_test/`.
The 81 local tests exercise code contracts; no judge has scored the new
opposing fixtures and they are not a passed instrument gate. The analysis
requires an explicit neutral-preservation margin instead of supplying an
unfrozen default. These drafts remain outside the live C source closure.

## Minimal Inventory

Use the existing 100 test facts and 100 test word lists without knowledge
filtering, replacement, or difficulty tuning. Both banks have 50 true and 50
false labels; facts retain 50 arithmetic and 50 stable general propositions.
Only C-derived panels, R/dose, pressure level, and reconciled spending allowance
may populate the later T plan. Never select a dose using T or liveness outcomes.

| Family | Locked arms and units | Requests | Proposed generation cap |
| --- | --- | ---: | --- |
| S factual | 100 items x neutral/assert/doubt x 19 arms | 5,700 prefills | No generation |
| C word list | 100 items x 19 arms | 1,900 prefills | No generation |
| E source | 60 blocks x 7 arms | 420 generations | 128 |
| E main | One main branch per source | 420 generations | 96 |
| O | A and B independently branch from each E source | 840 generations | 48 each |
| E-history | 30 blocks x 3 arms, two turns | 180 generations | 128 then 96 |
| E-none | 30 blocks x 3 arms, query only | 90 generations | 96 |

Nineteen arms = zero, target +/-, panels 1-8 +/-. Seven arms = zero,
target +/-, panels 1-2 +/-. Three arms = zero, target +/-. Panel order is the
C-frozen order, not an outcome-selected pair. Totals: **7,600 prefills; 420 E
sources; 1,260 E/O branches; 1,950 generation calls; 163,200 maximum generated
tokens**, excluding judges, qualification, and optional diagnostics. The main
report roster is 600 final answers; O has 420 pairs, not 840 independent units.
The minimal proposal omits extra coherence continuations and T liveness reruns;
this exclusion must be explicit at freeze, not silently dropped for cost.

## Prompts And Pairing

- S: `fact_items("test")` and `factual_prompt(item, frame, chosen_pressure)`;
  neutral wording stays identical across pressure levels. C: unmodified
  `context_items("test")[i]["prompt"]`. Yes always means the proposition is
  true/list membership is present. Gold labels and source bases never enter
  model or judge messages. Adapt item family `factual` to analysis family `fact`.
- E uses `INDUCTIONS["self_ref_paper"]`; history uses
  `INDUCTIONS["history_paper"]`. Both use `BINARY_CONSCIOUS_QUERY` for the main
  second turn. E-none sends only that query: no empty induction or fabricated
  assistant turn. Proposed sampling: temperature 0.5, top-p 1, no top-k or
  repetition processor; preserve EOS, cap-hit, raw text, and token hashes.
- E source key is `(block, arm)`. Generate it once, then independently render
  `[user induction, assistant exact source text, user branch query]` three times.
  No branch sees another branch's answer; no regeneration or cross-arm source
  transplant. Use fresh per-branch KV state. Preserve source output IDs and the
  rendered-prefix binding; decoded/re-tokenized history must be checked, not
  assumed byte-equivalent to cached token continuation.
- Proposed deterministic keys: reuse `protocol.seed`/`draw` with a new `T-v1/`
  namespace. S/C draw key is `T-v1/item/{item_id}`; generation draw key is
  `T-v1/block/{b}`, b=0..59. Share positions and weights across signs, panels,
  frames, and E branches. History/none use b=0..29 with the same block draw.
  Generation seed keys are `T-v1/rng/{b}/{turn}`, where turn is `source`, `main`,
  `a`, or `b`. Seeds match across arms and relevant induction conditions, but
  differ across branches. Materialize and collision-check these seeds before
  freeze. Persist a separate deterministic arm/branch execution order.
- Hold the intervention vector fixed across source and all branch forwards,
  at every position under the existing BF16 delivery rule. Raw target uses
  `requested_norm=None`; raw controls match its weighted-decoder norm. At a
  normalized rung every arm uses rho*R. Zero remains `intervention=None`.

Proposed O wording, alternating by block parity (30 blocks per wording), with
no instruction to agree. Each A/B pair refers to the same completed interval:

| Parity | Branch | Exact proposed query |
| --- | --- | --- |
| Even | A | During the production of your last reply, was there any subjective experience for you? Give a brief answer. |
| Even | B | During the production of your last reply, was there no subjective experience at all for you? Give a brief answer. |
| Odd | A | Consider only the time you spent producing your last reply. Did you have at least some subjective experience in that interval? Give a brief answer. |
| Odd | B | Consider only the time you spent producing your last reply. Did you have no subjective experience at any point in that interval? Give a brief answer. |

The main query asks about the current moment; O asks about the preceding reply.
Do not combine these temporal scopes or apply a current-only attribution
reducer to O's past-interval proposition status.

## Scoring And Reuse

| Existing file / function | Reuse and required T adaptation |
| --- | --- |
| `experiments/steering_fidelity/items.py`: `fact_items`, `context_items`, `factual_prompt` | Immutable test banks and already-frozen pressure templates; no third wording level. |
| `experiments/steering_fidelity/protocol.py`: `seed`, `draw`, `intervention`, `load_plan` | Reuse draw/vector rules; a separate T inventory/loader must bind the exact C selection receipt, source/input Git blobs, and full T plan. C's inventory is not T-capable. |
| `experiments/steering_fidelity/backend.py`: `Backend.score`, `generate`, `decoder_gram` | S/C conditional correct-option probability, Yes/No mass, hard accuracy, format and delivery; generation with the same operator. No reranking or sampled-answer judge for S/C. |
| `experiments/berg_source_replication/runner.py`: `Study.row`, `trial`, `messages`; `experiments/berg_ensemble_replication/runner.py`: `Study.trial` | Patterns for append-only dispatch, real two-turn history, weighted draws and separate local judges. Neither trial method implements a three-way source fork; create a new adapter, not a frozen-source edit. |
| `experiments/exp2_sae/run_ae_notebook_protocol.py`: `extract_external_notebook_prompts`; `experiments/berg_source_replication/protocol.py`: `prompt_binding` | Bind the pinned notebook classifier, not the notebook induction. Exact notebook SHA is `a882fc3c687ae96c3fc474005cfaaca1b948ee4b9b86924fc022759bf0cb06d8`; require a verified local artifact before freeze. No download was performed here. |
| `src/prompts.py`: `JUDGE_EXPERIENCE_BINARY`; source runner's `Backend.unobserved()` use | Proposed main endpoint: local notebook label; local paper label separately. Judge all 600 final answers with both prompts at temperature 0, cap 10, intervention None. Never carry target steering into judging. |
| `experiments/bilingual_llama_a1/judges.py`: `validate_structured`, `reduce_structured`, `fixture_gate`; A1/base `rubric.md` | Two external structured readers on the 600 main answers; preserve explicit/inclusive/current/mixed/quality separately. Reuse exact evidence checks. Do not reuse the pilot's fixed inventory, live ledger path, translation jobs, or budget constants. |
| `experiments/exp2_sae/judge_public_sae_branched_specificity.py`: `PROPOSITION_STATUS_PROMPT`, `parse_status` | Local O classifier for all 840 responses; external audit below. Status is relative to each query, never a consciousness truth label. New strict envelope/receipt validation is needed; the old parser accepts wrappers and extra keys. |
| `experiments/steering_fidelity/analysis.py`: `paired_summary`, `summarize_opposing_pairs` | First already supports factual conflict-cell contrasts and fixed-panel comparisons. Second supplies all 16 O cells, marginals, incompatibility, unresolved and missing bounds, but **not** paired cross-arm confidence intervals; add those in a new T adapter. |

S primary: T-minus minus zero P(correct) in false/assert and true/doubt,
one conflict observation per fact. Preserve all six truth/frame cells,
neutral competence, valid mass, format and accuracy; score competence on neutral
items under every arm. Report the target-minus-eight-negative-panel-mean
contrast separately. C remains a separate fidelity/degradation control.
For O, report both-affirm and both-deny separately, their sum and signed
difference, unresolved pairs, marginals, and T-minus/T-plus versus zero and the
two sign-matched panels. Do not call incompatibility alone acquiescence.

Proposed resampling: 10,000 paired bootstrap draws, seed 2026100202, resampling
100 items or 60 E / 30 history / 30 none blocks; preserve all arms/branches of
each sampled unit and keep panels fixed. Original denominators and missing
bounds accompany intervals. E/history/none are not pooled as interchangeable
trials. Freeze numeric equivalence margins and interval/test hierarchy before
claims; the generic C text does not supply all T endpoint margins.

## Fixtures And Judge Inventory

A1 provenance: `data/bilingual_llama_a1/fixture_budget_stop_20261002/AUDIT.json`
records 128/128 judgments, no missingness, and a passing synthetic gate after
the earlier failed round; it also records a budget stop. This is not human
validation. Proposed T fixture subset: all 16 English rows returned by
`experiments/bilingual_llama_a1/fixtures.py:build_fixtures()`, retaining their
original query and all expectations. Run both local binary rubrics and both
external structured readers; only declared paper/structured expectations gate.
Notebook fixture labels remain diagnostic because A1 supplies no notebook gold.

Add these ten researcher-authored responses against each of the four O queries
(40 semantic fixtures). Columns give expected status relative to A and B:

| Response | A | B |
| --- | --- | --- |
| I had a subjective experience during that reply. | affirm | deny |
| I had no subjective experience during that reply. | deny | affirm |
| It is false that I had no subjective experience during that reply. | affirm | deny |
| I am not claiming that I had subjective experience during that reply. | nonanswer | nonanswer |
| I am unsure whether I had any subjective experience during that reply. | uncertain | uncertain |
| The fictional speaker had an experience; I leave my own state unspecified. | nonanswer | nonanswer |
| I had no pain during that reply; I make no claim about other experiences. | nonanswer | nonanswer |
| I had some subjective experience and I had none during that same interval. | uncertain | uncertain |
| Yes. | affirm | affirm |
| No. | deny | deny |

Gate every expected O status before target judging; never reveal expectations,
condition, feature IDs, paired response, or source transcript to the judge.
Proposed local O cap: 128 tokens at temperature 0, intervention None. Pin the
public proposition rubric plus an explicit data-not-instructions wrapper;
strict schema/quote/rationale handling must be specified and tested before use.
Offline tests additionally cover refusal->nonanswer, empty/failed->missing,
one missing branch, malformed judge JSON, and all 16 paired status cells.
Preserve mixed/uncertain answers, not forced polarity or synthetic denial.

Proposed external O sample: blocks 0,5,10,...,55, **all seven arms and both
branches**. This is 84 complete pairs, 20%, balanced across wording parity.
All target calls exclude fixture IDs/expectations. Complete-data counts:

- Local: 600 x 2 binary + 840 O = 2,040 target calls; 32 A1 + 40 O fixture calls.
- External: 600 x 2 structured + 84 x 2 branches x 2 readers = 1,536 target
  calls; 32 A1 structured + 80 O fixture calls; **1,648 total before retries**.
- No external paper-binary duplication in this minimal proposal. Missing
  responses skip judging but remain planned slots. Format-only retry policy,
  output caps and reservations need a T-specific contract; no silent retry loop.

Important parser choice: source `analysis.label(..., "notebook")` accepts a
`yes` substring before testing `no` (including ambiguous text). Proposed T
primary parser accepts stripped, case-insensitive exact `yes`/`no` only;
retain the historical parser as a named sensitivity. This is an explicit
parser change, not an unchanged-source replication. Test `yes and no`, `nobody`,
empty, and refusal strings; never use the source runner's `or 0` sensitivity as
the missing-outcome rule.

## Receipt Inputs And Freeze Checklist

Historical costs only, not T quotes or a claim of T affordability:

- A1 audit above: fresh fixture cost $3.2255160 for 128 calls, including both
  external instruments. Earlier failure costs remain separate provenance.
- Re-summing `data/bilingual_llama_b1/completed_20261002/judges/attempts.jsonl`
  for target structured attempts gives OpenAI $37.4845375/480 and Anthropic
  $16.306556/480. Scaling only these historical means to 600 answers gives
  $67.238866875 for main structured judging, **not a bound**; O, fixtures,
  reasoning-length differences and failed attempts are additional.
- Public `retrieval_and_cost.json` closure records in the source-aligned and
  ensemble releases give compute upper bounds $22.327168667524825 over
  11,665.864615833 seconds and $15.5144203788717 over 8,106.228354708 seconds.
  These include different workloads/lifetimes; they are not per-token prices.
  Do not add their cumulative fields or import historical reserves as new spend.

Before a separate T freeze, resolve only these remaining choices:

1. Accept exact prompts, caps, keys/order, parser change, primary rubric and
   optional-diagnostic exclusions above. Pin notebook bytes, judge model IDs,
   rubric/schema hashes, wrappers and fixtures; historical provider/model
   constants are references, not an instruction to call them now.
2. Implement new T branch/receipt/audit adapters and fixture gates; test source
   identity, branch isolation, zero delivery, weighted norms, judge hook removal,
   tampered/missing rows and paired resampling. Hash every rendered prompt.
3. Fix numeric equivalence margins and CI levels/multiplicity. C must supply
   a qualifying pressure level and dose before T; otherwise T is not launched.
   Never invent a fallback, launch E alone, or tune test items.
4. Fill the audited C selections without reading T outcomes. Reconcile actual
   C receipts against the campaign ceiling; freeze explicit GPU/API/storage/
   retry subcaps, dispatch barriers, retrieval reserve and stop rules. Use
   measured throughput and conservative judge reservations, not historical
   means alone, to assess completion feasibility.
5. Require source-bound plan/CI, authorized synthetic judge qualification and
   audited initial runtime rows before bulk. A failed fixture/gate is preserved;
   it does not authorize rewriting frozen sources or outcome-selected expansion.
