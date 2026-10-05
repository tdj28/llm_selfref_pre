# Longer-Window Mapping-Scaled Dose Study

Status: implementation preparation. No production plan or source freeze has
been generated for this amendment, and no new pod has been launched.

## Amendment And Prior Exposure

This is a fresh-sample amendment to the
[256-token protocol](STEERING_DOSE_LADDER_PROTOCOL_20261004.md), not a correction
of its failed result. Its 204 calibration rows and descriptive dose curves have
been seen. Untreated headroom passed (7 positive, 5 negative labels), but three
of twelve untreated trials hit the output cap, failing the unchanged quality
gate. Dose 0.75 passed its four treated/control cells; this observation does
not preselect the new dose. The old main was not run. Preserve the predecessor
[release](../data/berg_dose_ladder/calibration_v1_20261004/MANIFEST.json) and do
not pool its rows with this study.

Increase only the generation window from 256 to 512 tokens on both turns in
every experimental arm. Capped old responses showed both mid-sentence truncation
and semantic repetition; a longer window may still fail. Longer induction also
changes the second-turn context, so this is a changed assay, not proof of a
generation bug. The 10-token local judges remain unchanged.

## Inventory And Gates

All model/SAE revisions, BF16 arithmetic, hook placement, target IDs, mapping
scales, three control panels, aggregate norm matching, doses (0.25, 0.5, 0.75,
1.0), signs, prompts, temperature 0.5, two-turn seed resets, notebook primary
and paper secondary judges, delivery rules, quality flags and inference are
identical to the predecessor. The new backend inherits those implementations;
its copied generation method changes only the cap default and upper bound.

Use twelve calibration seeds `20261004512000 + 1009*i`, i=0..11, and 96 fresh
main seeds `20261005512000 + 1009*i`, i=0..95. These ranges are disjoint from
each other and the inspected prior study inventories. Each block retains the
same seed across arms and both turns, and the same panel assignment i modulo 3.
Trial IDs have a `window-` prefix. The machine inventory fixes all ordering.

Run all twelve untreated calibration trials first, once, without a first-five
barrier. True-zero qualification and the complete untreated gate protect this
stage. After all twelve, save and receipt-bind
`zero_screen.json`, reconstruct it from the saved rows, and audit before any
treated dispatch. This is an explicit ordering change to avoid buying 192
treated calibration trials when a necessary gate has already failed.

The untreated screen requires at least three positive and three negative
primary labels, no missing primary labels, and at most two flagged trials out
of twelve. Flags remain missing/empty output, either turn hitting 512, repeat4
above 0.30, or either turn's clean NLL above twice its untreated median. The
medians come from these same twelve fresh untreated rows, exactly as in the
original 204-row calibration rule. Do not loosen thresholds or add samples.
A failed screen ends the run; treated calibration and main are unrun, not null.

On passing, retain those twelve rows and collect the other 192 calibration
trials, without regenerating baseline. Pause after the first five treated rows
for the local first-five audit of real 70B nonzero delivery. Approval requires
the passed zero-screen receipt and exactly twelve untreated plus five treated
rows, eighteen including qualification. Every treated row still must pass its
delivery check. Apply the unchanged complete-calibration
selector: choose the largest dose meeting every gate, never using nonzero label
values. Then collect all 480 conditional main trials (96 five-arm blocks) or
none if no dose qualifies or the whole forecast fails admission. There is no
effect-based stopping, lower-dose main fallback, automatic replacement, or
threshold adaptation. The final main quality gate remains mandatory.

The paired-discordance intervals, multiplicity, missingness bounds, bootstrap,
0.30 target threshold and specificity requirement are unchanged. Reuse the
source-bound fixed-N power report; its operating characteristics do not model
qualification probability or establish that cap512 will pass. Quality metrics
are mechanical, not human coherence validation; labels are not ground truth.

## Cost And Ownership

The human authorized $200 separately for RunPod and OpenRouter. This GPU study
uses only a $50 cumulative sub-cap, including the exact prior cost
$6.726273265975. New spending may not exceed $43.273726734025. No API allocation
is borrowed and the RunPod ceiling is not a reason to expand this experiment.

One fresh cheap CUDA pod is limited to 1,800 seconds and one fresh main pod to
19,800 seconds (5.5 hours), including the 600-second retrieval reserve. Keep
the existing B200/RTX4090 rate ceilings and $0.10/hour storage bound. Fully
using both timers adds $38.315, giving $45.041273265975 cumulative. Main admission
uses fresh calibration timing: max(mean calibration trial time, selected-dose
75th percentile) times 480 times 1.30 must fit the remaining worker deadline
minus its existing 300-second buffer. Startup, downloads, scoring, qualification
and retrieval remain inside the billed window. A higher cap may fail admission.

Use canonical local `out/dose-window-20261004/dose-window-controller/{cheap,main}`
under the shared repository root, and pod prefix `codex-dose-window-20261004-`.
The existing pod-local transport workspace remains unchanged on each newly
owned pod; it does not reuse an old pod or ledger. Only the new provider-returned
owned ID may be mutated. Retain immutable creation/dispatch intents, unresolved
charges, snapshot hash checks, direct deletion GET404 and full inventory proof.
No retry/replacement pod is automatic. Cloud credentials remain local; only the
model-download credential may reach the main worker through the existing
ephemeral allowlisted path, never code, logs or result artifacts.

## Offline Checks And Execution Boundary

Run `python -m pytest tests/test_dose_window*.py -q -p no:cacheprovider` locally.
The cheap CUDA worker sets `BERG_TEST_DEVICE=cuda` and runs the new backend and
runner tests with no downloads; no skipped CUDA/BF16 test may qualify it.
The main controller requires its retrieved, hash-checked successful cheap
receipt and verified deletion before rental. Tests with synthetic rows and
mocked provider/SSH boundaries are implementation checks, not GPU qualification.

The prospective entrypoints are `experiments.berg_dose_window.protocol`,
`experiments.berg_dose_window.controller`, `experiments.berg_dose_window.runner`
and `experiments.berg_dose_window.analysis`. Plan location is
`data/berg_dose_window/plan_20261004/PLAN.json`. The parent must review the
ordering tradeoff, build the plan from the pinned notebook, source-freeze and
push before any `controller --launch`. Without that flag the controller only
validates locally; it must not read credentials or contact the provider.
