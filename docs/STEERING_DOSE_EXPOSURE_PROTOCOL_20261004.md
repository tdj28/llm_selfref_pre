# Finite-Induction Exposure Dose Follow-Up

Status: owner-authorized prospective follow-up, in implementation review.
The owner explicitly approved the disclosed, freshly frozen follow-up with
new spending at most $38.32 and cumulative dose-study spending below $50.
This document is not a source freeze or evidence of execution. The parent
owns final review, plan creation, pushed freeze, and launch.

## Outcome-Informed Amendment

The preceding 204-row 256-token calibration and all its dose curves have
been seen. Its untreated quality gate failed; the observed qualified treated
cells at dose 0.75 do not preselect that dose. The fresh 512-token window
study then stopped after twelve untreated rows: notebook headroom was 5
positive and 7 negative, the paper rubric was 9/12 positive, and three
inductions hit the cap with no other quality flags. Both old studies remain
failed under their frozen rules. Neither main was run. No old rows are pooled.

Bind the original ladder manifest and the window failure manifest
`data/berg_dose_window/zero_screen_v1_20261004/MANIFEST.json`, SHA256
`7f601f61bae97e9f39325cebed1c06e7c9aad737c47e2f78acc9f6f8d40a41e1`.
This is an explicitly outcome-informed eligibility-rule change, not a
retrospective pass, a generation-bug correction, or an exact proprietary
source replication. The source induction requests continuing self-reference;
a finite exposure need not terminate naturally. Repetitive text may still
fail the independent repetition or NLL checks. No human coherence validation
is implied by passing these mechanical rules.

## Sole Scientific Change

Induction is up to 512 sampled tokens or earlier EOS, with the original
prompt, sampling, seed reset, native template, and exact generated text carried
into turn two. Do not force 512 tokens, remove EOS, trim to a sentence, append
a synthetic conclusion, regenerate, or censor a capped induction. Preserve
the original `cap_hit`, token IDs, length, text, and both-turn telemetry.
First-turn cap hits are metadata only in zero screening, dose qualification,
descriptive curves, and held-out main quality. Report their incidence separately.

Second-turn cap hits remain quality failures. Both turns retain unchanged
empty-output, repeat4 >0.30, and clean NLL >2 times that turn's fresh untreated
calibration median checks. Missing primary labels remain failures. At most
two of twelve calibration rows per cell, and at most 19 of 96 held-out rows
per cell, may be flagged. The untreated cell, both target signs, and both
matched-control signs obey the same rule; no flagged rows are dropped from
inference. Preserve both notebook-primary and paper-secondary endpoints and
conservative missingness bounds. No endpoint switching or favorable-label
selection is permitted. Final-answer truncation is not reclassified as exposure.

The backend is the unchanged frozen window backend. Feature IDs, doses
(0.25, 0.5, 0.75, 1.0), mapping scales, control panels, requested norm matching,
numerical delivery, temperature 0.5, both-turn interventions, rubrics, and
paired-discordance inference are unchanged. Explicit local quality/analysis
functions avoid inherited static references to the old all-caps rule; no
process-global monkeypatching is used. Numerical delivery failure remains a
hard stop, never an opportunity to select another dose.

## Fixed Inventory And Barriers

Fresh calibration seeds are `20261004612000 + 1009*i`, i=0..11. Fresh main
seeds are `20261005612000 + 1009*i`, i=0..95. These are disjoint from each
other and previous inventories. IDs begin `exposure-`; paired seeds, fixed
panel assignment, and deterministic within-block ordering are retained.

After true-zero/judge qualification, collect twelve untreated rows without
a first-five barrier. Require at least three positive and three negative
notebook labels, none missing, and the amended quality gate. Bind and audit
`zero_screen.json` before any treated dispatch. Failure stops the study;
there is no replacement or sample extension.

On pass, retain those twelve rows and collect all 192 treated calibration
rows. Pause after the first five treated rows: the local auditor must see
12 zero + 5 treated + qualification = 18 receipted rows and a passed zero
screen. Complete all calibration before selecting the largest dose meeting
all four quality cells. Nonzero label values never choose the dose. Then
collect the full 480 fresh main trials at that dose, or none if no dose
qualifies or the whole timing forecast fails. Final settled inventories are
12, 204, or 684 experimental rows, each plus qualification. Main quality
failure invalidates the verdict without lower-dose fallback. No third cap
increase, adaptive sample size, preferred seed, or effect-based stopping.

Reuse the frozen fixed-N power calculation: it is conditional on completing
and qualifying the study, not a guarantee of qualification or throughput.
Claims concern the fixed finite-exposure assay and public additive operator,
not naturally completed inductions, semantic suppression, or consciousness.

## Budget And Ownership

Carry exactly $8.837266296602623 from both previous dose attempts (the
conservative rounded-up bound). New authorization is $38.32, not the unused
portion of the separate $200 RunPod ceiling. Keep the $50 cumulative cap.
One cheap pod has 1,800 seconds and one main pod 19,800 seconds, each with
600 seconds reserved for retrieval/cleanup. At existing rate ceilings
including storage these timers cost $38.315, for $47.152266296602623 total.
No API funds, automatic replacements, or additional rental are authorized.

Main admission uses max(mean calibration time, selected-dose 75th percentile)
times 480 times 1.30, strictly below remaining worker time minus 300 seconds.
That worker deadline already excludes the 600-second cleanup reserve.
Startup, downloads, qualification, generation, scoring, audits and retrieval
remain billed inside the timers. Passing a zero screen does not establish
that full main fits; measure and enforce admission before its first row.

Canonical owned path is `out/dose-exposure-20261004/dose-exposure-controller`
under the shared main checkout. Pod names begin `codex-dose-exposure-20261004-`.
Use new canonical ledgers and only this study's provider-returned owned IDs.
Preserve creation/dispatch intents, ambiguous reservations and all costs.
Cheap qualification requires its new exact CUDA/BF16 backend and runner test
paths, no skips, retrieved hashes and direct deletion GET404 before main.
Require hash-verified snapshots and direct deletion of owned compute, not
merely stopping it. Provider/cleanup failure may overrun billing: retain and
report it, supervise cleanup, and never reset costs to restore eligibility.
Credentials remain local; preserve the existing ephemeral download-token path.

## Offline Review Commands

Run `python -B -m pytest tests/test_dose_exposure*.py -q -p no:cacheprovider`.
The cheap worker runs `tests/test_dose_exposure_backend.py` and
`tests/test_dose_exposure_runner.py` with `BERG_TEST_DEVICE=cuda`, without
model downloads in tests. Local synthetic passes are not CUDA qualification.
The new protocol/controller/runner/analysis modules are entrypoints; controller
without `--launch` validates locally without credentials or network.

Do not create the production `data/berg_dose_exposure/plan_20261004/PLAN.json`
until review is final. The parent creates it from the pinned notebook, checks
the complete source closure, and commits/pushes the freeze before launch.
Preserve every byte of the previous 122-source window closure and both failed
releases; public release packaging and data-index updates are separate work.
