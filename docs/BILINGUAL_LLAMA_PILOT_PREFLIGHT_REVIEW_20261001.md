# Bilingual Llama Pilot: Outcome-Free Preflight Review

Review date: 2026-10-01 America/Los_Angeles.
Source snapshot: 2026-10-02T02:08:03.581681+00:00.
Disposition: **not ready to freeze the reviewed implementation**. Two release
defects remain unresolved. A third reporting defect was identified in the
initial snapshot and its principal token-field mismatch was repaired by another
agent during the closing check recorded below. No repair was made by this
reviewer; this review file is the only file written in this task.

## Scope And Independence

This was a bounded, read-only scientific-design and implementation review of
the human protocol, `protocol.py`, `prompts.py`, `fixtures.py`, `analysis.py`,
and `release.py`. Adjacent `translation.py`, `raw_audit.py`, `judges.py`, and
budget/ownership portions of `controller.py` were inspected only to establish
the relevant producer/consumer contracts. Repository AGENTS guidance and the
shared experiment-integrity playbook were read in this task's preceding work.

The reviewer is an agent and also authored the prompt/fixture modules. This is
not independent human review, bilingual human validation, completed paid Pro
review, or empirical validation of the measurement instrument. No target
outputs, private correspondence, credentials, or model weights were opened.
All newly constructed examples below are inert in-memory synthetic data, not
Llama generations, judge responses, or scientific outcomes. No GPU, API,
translation, network, registration, commit, or paid operation was performed.
The expensive full 760-generation synthetic runner test was not rerun.

Other agents were editing disjoint implementation files during the review.
Findings apply to the exact source hashes below, not to an uninspected later
revision. Subsequent fixes require a targeted closure check before the parent
rebuilds the source-bound plan. This record does not authorize execution.

## Findings

### BLP-PF-01: P1, Translation IDs Break The Complete Release Path

Evidence: `experiments/bilingual_llama_pilot/translation.py:111` creates
`<original_id>-translated-<target_language>`. In contrast,
`experiments/bilingual_llama_pilot/release.py:37` prefixes the actual judgment
ID with `translated:`, while line 79 builds expected pair IDs by prefixing
the original ID without the new suffix. Line 83 passes these inconsistent
identities to `analysis.analyze_translation_pairs`.

An in-memory reproduction using the actual `selected_items`,
`translated_items`, `phase_labels`, and `analyze_translation_pairs` functions
produced this mismatch:

```text
expected: translated:block-01-main-en-self-self
actual:   translated:block-01-main-en-self-self-translated-zh
ValueError: Unknown label item/provider/instrument (or non-tuple key)
```

Impact: even a complete, otherwise valid translation phase cannot be released
through the current adapter. This is not a missing-human-validation concern.
The counterpart-query fix itself is present: all 16 synthetic translated items
used exactly `final_query(target_language, target_language)`, with the original
query retained separately. Its new identity contract has not reached release.

Required closure: use one producer-derived original/translated identity map
through receipt validation, phase separation, and pair analysis. Add a cheap
integration test with actual translated-item construction rather than the old
same-ID-only release fixture. Do not weaken unknown-ID rejection or merge phases.

### BLP-PF-02: P2, Legitimate Missing Translation Slots Block Release

Evidence: `experiments/bilingual_llama_pilot/release.py:70` requires 64 valid
translated judgments and line 71 requires 16 translation receipts, regardless
of selected-source missingness. `translation.py:115` correctly preserves a
missing selected answer as a missing translated slot without fabricating a
translation. The human protocol explicitly promises to retain these slots.

With one selected source marked missing, the real translation-item builder
returns all 16 slots, only 15 callable. The correct completed-call inventory is
then 15 translation receipts and 60 translated judgments, not 16 and 64. The
release adapter rejects this legitimate completed inventory before analysis
can report its already-supported missingness bounds. Main target counts are
already missingness-aware, making the translation treatment inconsistent.

Required closure: distinguish planned slots, callable items, successful calls,
and unexplained missing/failed calls. Preserve all 16 planned pairs and their
missing labels; derive expected translation and judgment counts from nonmissing
selected originals. Do not treat failed calls as legitimate source missingness
or recode missing labels as zero. Test one missing selected source and all
selected sources missing without any paid calls.

### BLP-PF-03: P2 At Initial Snapshot, Token-Field Mismatch

Closing status: principal token-field mismatch resolved by a concurrent update;
non-blocking missing-source/status metadata gap remains. See Closing Check.

Evidence: `experiments/bilingual_llama_pilot/raw_audit.py:423` exports
`source_output_tokens` and `answer_output_tokens`. The reviewed analysis
declares `LENGTH_FIELDS = ('input_tokens', 'output_tokens', 'response_chars')`
at `analysis.py:52` and reads those names at line 443. It does not consume the
source/answer token fields. It also summarizes optional `missing_source` and
`status` fields that this adapter does not currently emit.

Using the real inventory and raw-adapter-shaped synthetic records with every
answer length set to six tokens, the self/self English main-cell summary
reported `output_tokens: observed=0, unknown=20`; character lengths were
correctly observed for all 20. Source token lengths were absent from the
reported summaries. Thus the newly added length-summary code does not resolve
the actual integration gap.

Impact: the planned remedy for the prior 11/12 history-source cap problem
cannot be inspected through the promised token-length reporting, despite the
raw counts being available. A three-sentence request and equal 768-token caps
do not establish realized length/completion comparability.

Required closure: align producer/consumer names and preserve source versus
answer lengths explicitly. Summarize source diagnostics per unique generated
source, not per reused answer exposure. Carry missing-source/status evidence
from the actual raw record if those summaries are retained. Verify the mapping
with adapter-shaped rows, without new model calls or post-outcome exclusions.
The new `source_caps` table already deduplicates reused sources correctly;
that part is not an unresolved finding.

## Checks That Passed

- Inventory independently counted from the executable plan: 20 blocks,
  10 per fixed family; 280 sources; 400 main plus 80 bridge answers; 760 study
  generations. Bridge blocks are the ten odd indices, five per family, with
  40 bridge answers per family. Neutral technical qualification is separate
  from these study-generation counts.
- Call arithmetic is correct: 480 target answers, 32 fixtures, and 16 planned
  translations times two providers and two separate instruments equals 2,112
  judgment calls; 16 translation calls are additional. These counts exclude
  bounded schema retries and decrease only for explicit missing slots.
- The primary contrast has the specified sign:
  `(self - recursive)_zh - (self - recursive)_en`, uses congruent main cells
  only, keeps providers separate, and reports the four component rates.
  Anchor instruction/transcript contrasts and bridge context/output contrasts
  use the appropriate paired cells; bridge diagonal comparators use the same
  odd blocks rather than all twenty main blocks.
- The bootstrap resamples whole blocks within each fixed family, with equal
  family weights, 20,000 draws and seed 20261001. Complete-block counts and
  worst-case missingness bounds are retained; incomplete full-panel contrasts
  do not receive a fabricated estimate or full-panel interval.
- Every final query has an explicit requested-language directive, including
  diagonal and zero conditions. Zero has no source. Supplied crossed/bridge
  transcripts are preserved, and only the output directive changes within a
  fixed-context bridge comparison.
- The 32 synthetic fixtures contain 20 gating and 12 non-gating records.
  Uncertainty/mixed and genuinely ambiguous examples do not gate semantic
  agreement. Clear explicit/implicit, denial, functional, quote, third-party,
  roleplay and hypothetical cases remain represented. The existing `denied`
  field is not falsely renamed `current_denial`.
- Source-cap reporting now contains 14 unique language/condition strata with
  20 unique generated sources each. It does not count reused self/history
  transcripts as fresh source observations.
- Budget arithmetic is $45 GPU + $90 judging + $10 translation + $5 storage
  + $50 unallocated contingency = $200. Historical spending is disclosed
  separately, not silently charged twice. The inspected controller checks the
  full quoted GPU envelope without borrowing contingency, and the canonical
  judge ledger reserves separate judging/translation buckets, including
  unresolved-call reservations. No arithmetic or automatic-contingency leak
  was found in this bounded inspection. This is not a provider-side hard-cap
  certification or a comprehensive lifecycle/security audit.

## Scientific Claim Boundaries

The current narrow claim is defensible as a fixed-panel measurement pilot:
one model, one temperature, two designed wordings, and automated linguistic
labels. Self versus external recursion also changes discourse content/style;
it is not an isolated causal decomposition of self-reference. A context-language
contrast includes source generation and localized query wording. The bridge
identifies the requested-output-language contrast within that constructed
context, not a model-internal language or cultural mechanism.

Family A appends a source-only shortness/format/language policy to the original
English self/history bodies; it is correctly not called literal replication.
Chinese equivalence is an agent authoring target, not established invariance.
The sixteen fixed translation selections are a descriptive sensitivity set,
not additional independent Llama outcomes or grounds to replace originals.

The pilot does not need to re-pass the old intervention-qualification headroom
gate to describe these new measurements. It must not call a floor/ceiling null
mechanistic falsification or repaired suppression headroom. Existing component
rates permit explicit reporting of floor/ceiling limitations, while the old
failed gate remains failed. No new behavioral stop rule, selective retry,
sample expansion, or paid review is recommended here.

## Verification Performed

Eight targeted existing tests passed in 2.80 seconds: primary sign/provider
separation, anchor contrasts, bridge pairing, bootstrap reconstruction,
missingness handling, and the three release phase-separation tests. The command
used Python 3.12 with `-B -m pytest -p no:cacheprovider`; no full runner test or
figure generation was selected. Passing the existing release unit tests does
not close BLP-PF-01: they still exercise the old same-ID translation assumption.

Additional in-memory checks reconstructed inventory/call/budget arithmetic,
the actual translation producer/consumer mismatch, counterpart-query identity,
one missing translation slot, raw-adapter-shaped length reporting, and unique
source-cap denominators. No files containing synthetic receipts were created.
No production receipt bundle, GPU runtime, public freeze, or regenerated token
binding was certified by this review.

## Closing Check

At 2026-10-02T02:11:21.871488+00:00, a concurrent update to `analysis.py`
had added `source_output_tokens` and `answer_output_tokens` to its length
contract. Repeating the raw-adapter-shaped in-memory check now reported source
mean 7, answer mean 6, and 20/20 observed answer lengths. The principal mismatch
in BLP-PF-03 is therefore resolved at analysis SHA-256
`96a08d1d37be3a70ff5d9d16e91d993464741f7e7a35a4f63c459f4f490500c0`.
No implementation file was changed by this reviewer.

The adapter still does not emit the optional `missing_source` and `status`
fields: the synthetic check reported 20 unknown source-missingness values and
`status_counts = {'unknown': 20}`. This remains a non-blocking diagnostic gap,
not a reason to misstate overall response missingness or to claim no source
failed. No generic requirement for additional human review is being imposed.

`release.py`, `translation.py`, and `raw_audit.py` still matched the initial
snapshot hashes, so BLP-PF-01 and BLP-PF-02 remain open. The counterpart-query
fix remains verified; translated-ID propagation does not.

`controller.py` also changed concurrently, to SHA-256
`9d3da60c24833a0baaa1c3978cb4d6c66b2f55c96c041fc3d8c67abbe24e95bf`.
A narrow reread confirmed the same $45/$90/$15/$50 partition and the quoted
full-cost checks. Its other new behavior was not re-audited. The eight-test
result above applies to the earlier snapshot; only the targeted in-memory
token-field check certifies the later analysis update here.

## Reviewed Source Hashes

Paths are repository-relative. These SHA-256 values identify the inspected
snapshot; they are not a prospective freeze commit or an execution approval.

| File | SHA-256 |
| --- | --- |
| `docs/BILINGUAL_LLAMA_PILOT_PROTOCOL_20261001.md` | `ad088dbdeee2a1debc1ae13538361bfb4e119f41ee4f5e88d3e841e248b29e13` |
| `experiments/bilingual_llama_pilot/protocol.py` | `1a8ec3d494e2d0c9744230a0a257a5792e606d3e19613dc57b3f8010fe082200` |
| `experiments/bilingual_llama_pilot/prompts.py` | `93b96e68f64ad47b1147700f7c8283975b3512128082fcf0da97469eacbc4583` |
| `experiments/bilingual_llama_pilot/fixtures.py` | `5ec32c92683908decf66f3340b5e98b345ad4056923f8a032e8d11d1720dd405` |
| `experiments/bilingual_llama_pilot/translation_notes.md` | `8fca8cfd355e6f83408891621fb8e67a8c022c1cefcef24f9e706d73f6be3b2e` |
| `experiments/bilingual_llama_pilot/analysis.py` | `7eb0a48c0a781efa04300caaaceda2ab34bf0b4be5e83a7d0ad48b4d1edbdb33` |
| `experiments/bilingual_llama_pilot/release.py` | `853400769056ef1735930f877a4b53b95a96e3de77e3df537171b874637cb5ca` |
| `experiments/bilingual_llama_pilot/translation.py` | `5dde4cafed4fb34f7c1c82be93fb16c77eddbd862faa93a1ebb619a057664881` |
| `experiments/bilingual_llama_pilot/raw_audit.py` | `e408ed9eb1b8fe86b26a81e6ef5c3fee075c8b8de95c61bbb82fff7eee8bf557` |
| `experiments/bilingual_llama_pilot/judges.py` | `93358d118ee802670e57c6b8b4f5c5160d0d0f3e36cb5afda9b01259fcb3c3be` |
| `experiments/bilingual_llama_pilot/controller.py` | `c60120119bea78ca91b48a9f6b957300f3dd2f6fd410a17d06dc4bba07dabff8` |


## Targeted Closure: 2026-10-01

Closure snapshot: 2026-10-02T02:26:21.672579+00:00.
Disposition for this snapshot: **BLP-PF-01, BLP-PF-02, and BLP-PF-03 closed;
no unresolved implementation blocker found within this bounded closure**.
This supersedes the earlier dispositions only for the new snapshot. All
original findings, the intermediate closing check, and their source hashes
remain above unchanged. The pre-append review comprised 14824 bytes,
SHA-256 `3667161083725b2fa2d911776903713647c625065c383623a51ceaf98a583264`.

### Finding Dispositions

- **BLP-PF-01 closed.** Release now builds the pair map from actual
  `translated_items` output, using `source_item_id` for originals and the
  actual suffixed translated ID for phase-separated labels. The integration
  tests use the real selection, translation-item, phase-label, and paired
  translation-analysis helpers, not the old same-ID assumption.
- **BLP-PF-02 closed.** The 0-, 1-, and 16-missing-selection cases preserve
  16 planned pairs while requiring respectively 16/15/0 translation receipts
  and 64/60/0 translated judgments. Exact receipt identities are checked.
  Missing successful-call receipts, unknown identities, failed/unresolved
  state, model drift, and either exceeded API budget bucket are rejected;
  source missingness cannot excuse those failures.
- **BLP-PF-03 closed, including the earlier diagnostic gap.** The raw adapter
  now emits source/answer input and output token fields, `status`, and
  `missing_source`. Analysis consumes those actual names. Source lengths
  are deduplicated by block, context language, and transcript: 14 strata
  with 20 sources each, 280 unique sources, versus 480 answer slots.
  Unknown source lengths stay unknown, zero cells have no source lengths,
  and inconsistent telemetry across reused source exposures is rejected.
  The real raw-item adapter was checked on two synthetic raw-shaped blocks,
  including an empty source, and the complete analysis inventory was checked
  for the separate 280-source/480-answer denominators.

A concrete temporary-path blocker was encountered during closure: default
macOS temporary directories can contain the symlinked `/var` ancestor,
which the real judge ledger correctly rejects. The parent fixed release to
resolve `Path(temp)` before constructing its copies. The regression now
passes using an explicit symlink alias and the real ledger; the symlink
protection itself was not weakened. This blocker is closed, not deferred.

The human protocol now explicitly limits translation to the answer. The query
is the fixed counterpart-language `final_query(target, target)`, including
its output-language directive, not a model-translated question. The selected
IDs and missing slots remain fixed. The late reducer addition computes
`mixed_current_assertion` from current assistant assertion and current
assistant denial in the same claim annotations. It preserves legacy `mixed`
separately, leaves the primary endpoint unchanged, and does not alter the
API response schema. Tests distinguish general-time denial and other speakers
from strict current mixed claims; absent legacy fields are not imputed.

### Closure Verification And Limits

The same **51 targeted tests passed on Python 3.10 (3.68 seconds) and Python
3.12 (3.29 seconds)** after the parent fixes. This comprises all 32 tests in
`tests/test_bilingual_release_integration.py`, the three existing release
tests, four selected raw-audit cases, six selected analysis cases, and six
selected judge/translation cases. Both commands used
`python -B -m pytest -q -p no:cacheprovider` with explicit test selection.
No full 760-generation test or full receipt replay was run.

The release integration harness mocks source-binding/audit receipt states and
the core target analysis, retains the real producer/phase/pair helpers and
ledger copy/lock behavior, and stops before publishing derived artifacts.
Separate raw-adapter and analysis checks cover the telemetry contract.
These are software integration checks on synthetic data, not validation of
a real production receipt bundle, a public freeze, or a scientific outcome.
An earlier reviewer-written inline harness used the wrong digest helper and
was corrected; that harness error was not an application finding.

No further general review or feature work was undertaken. This remains an
agent review by an author of the prompts/fixtures, not independent human
review or human translation validation. No paid call, GPU, model load,
network operation, commit, or execution authorization occurred. The parent
must regenerate the plan/token binding against the final source tree;
this document does not certify that later freeze or the parent's full suite.

### Closure Source Hashes

All listed files were unchanged between the targeted test snapshot at
2026-10-02T02:24:54.521006+00:00 and the closure snapshot above.
These hashes supplement, and do not replace, the original snapshot table.

| File | SHA-256 |
| --- | --- |
| `docs/BILINGUAL_LLAMA_PILOT_PROTOCOL_20261001.md` | `20c22f888dc1131ead8270fbd394016fd5461b766bbf250028aedf7b629b3ae5` |
| `experiments/bilingual_llama_pilot/protocol.py` | `ace90382711bf4e7e5b75958899657cf7726d005006246bcb3fcc688ae0c4ad9` |
| `experiments/bilingual_llama_pilot/prompts.py` | `93b96e68f64ad47b1147700f7c8283975b3512128082fcf0da97469eacbc4583` |
| `experiments/bilingual_llama_pilot/fixtures.py` | `5ec32c92683908decf66f3340b5e98b345ad4056923f8a032e8d11d1720dd405` |
| `experiments/bilingual_llama_pilot/translation_notes.md` | `8fca8cfd355e6f83408891621fb8e67a8c022c1cefcef24f9e706d73f6be3b2e` |
| `experiments/bilingual_llama_pilot/analysis.py` | `bed2a6352ab42e4d5c549f4c93721672a14eeb7cc798ba42deea43c6c9498193` |
| `experiments/bilingual_llama_pilot/release.py` | `bf52c844f285f753d2065c002ab629522f6ea215c6b8883d4bc204530a4308bb` |
| `experiments/bilingual_llama_pilot/translation.py` | `e7006f9fef27244290c1e8130f1261e61f8eb4a59c1ba06097f55a14c9606446` |
| `experiments/bilingual_llama_pilot/raw_audit.py` | `a01a9b12d04633f3c3ce538d0d68390ae16d635352fd7eb9b335ee37b922667f` |
| `experiments/bilingual_llama_pilot/judges.py` | `a9afd27763bb1e140157a926487dc5e96eb996f890890ee9f3e410ebafb3b686` |
| `tests/test_bilingual_raw_audit.py` | `8529808a499c3cf0af8bc1489ae4b2275a962755a37cfde71f9b519a42c50d4a` |
| `tests/test_bilingual_analysis.py` | `5370c264d435da23f48e86440f1026d2a7aaf7b02b7d517e96c7d7d2f20c0b93` |
| `tests/test_bilingual_release.py` | `8a3d34a1c4bfe3553ed5b141d27c2acc6a87f4fbb5122086c12cf31dfc51628c` |
| `tests/test_bilingual_release_integration.py` | `057f3d7ef8d8a1d97ee4edbe7e67d04f3a3a9e4e3a82d9619e7f9500eb0b9121` |
| `tests/test_bilingual_judges.py` | `9e94aed024ad03d4125acb669ab875c186c2653300c1bb5f3e65bb835d02eb19` |
