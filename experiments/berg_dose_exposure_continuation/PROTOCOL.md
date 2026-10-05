# Fixed-Main Technical Continuation

This is an owner-authorized technical continuation of the existing $50 dose
study, not new funding or a new scientific design. Parent owns plan review,
pushed freeze, launch and supervised cleanup. Implementation and offline tests
do not establish successful collection or publication approval.

## Preserved Record

Original freeze: `56b06eb6de7f09342c4d428bff3604c0ffba8e5a`.
Original plan: `data/berg_dose_exposure/plan_20261004/PLAN.json`.
The externally verified release is
`data/berg_dose_exposure/calibration_throughput_stop_v1_20261005/`.
Its manifest SHA256 is
`168145395c90dab0b563c77c15b1fd2ff89fab3948064ef5b84caed8d6befab2`.

All 204 calibration trials and the live qualification completed. The frozen
quality selection passed at dose 0.25; untreated notebook labels were 5 positive
and 7 negative. No main trial was attempted. The original forecast was
15,243.81748842448 seconds against 14,999.729626655579 available, retaining the
1.30 reserve. It correctly stopped with `TimeoutError`. That failed throughput
gate, all raw bytes, selection, dispatch receipts and logs remain unchanged.
The release remains `partial_technical_failure`, with complete calibration
and main `not_run`. This is not a calibration failure or a main null effect.

Pod `705mz353p49nw0` was retrieved and deleted, verified by direct GET404 at
2026-10-05 05:56:15 UTC. The cumulative controller upper bound was exactly
$16.56599765431651188888888889, carried conservatively as
$16.565997654316512. These are upper bounds, not provider invoices.

## Unchanged Science

Dispatch exactly the original selected main inventory: 96 blocks, five arms,
480 trials, dose 0.25. Keep every original row ID, block, seed, control-panel
assignment, within-block order, prompt, model/SAE revision, weights, dtype,
temperature, 512-token caps, both-turn intervention, local judges, quality
threshold and inferential rule. Import the frozen trial/backend implementations.
Do not regenerate calibration, rerun selection, choose another dose, replace
seeds, change labels, extend N, or select outcomes after seeing main responses.
An uncertain dispatch is never retried. The new journal contains only fresh
live qualification and original main IDs; a bound carry record refers to the
old calibration without pretending it was generated again.

The scientific analysis reuses the frozen row validation, delivery, quality,
paired-discordance bounds, specificity bounds and block-bootstrap functions.
It preserves both notebook-primary and paper-secondary endpoints, missingness
bounds, induction-cap metadata and final-cap quality failure. All 480 trials
are required for final inference. Calibration remains separate calibration
evidence, not extra independent main observations. No human validation or
consciousness conclusion is implied.

## Runtime And Cost

One new B200 pod, the same pinned image and requirements, with a unique
`codex-dose-exposure-continuation-20261005-main-` name and separate canonical
`out/dose-exposure-continuation-20261005/dose-exposure-continuation-controller/main`
ledger. No replacement, old-pod reuse, cheap rental, external judge or Pro call.
Reuse the hash-verified completed cheap CUDA tests and GET404 receipt from
pod `qqouyi1l7gm5p1`: no GPU math, hardware type, image or trial code changes.
New wrapper control flow is CPU-tested. Still require a fresh live true-zero,
geometry and judge-fixture qualification on the new main pod, matching the
previous model/SAE artifacts, template and Torch/CUDA/Transformers metadata.
Retrieve/audit qualification and the first five main trials before continuing.
These are technical barriers under existing authority, not new owner approval.

New all-in cap: $33.43, within the remaining $33.434002345683488. Hard timer:
17,460 seconds (4.85 hours), including startup, fresh qualification, main,
analysis, retrieval and deletion. At $6.79/hour plus $0.10/hour storage its
bound is $33.4165, cumulative $49.982497654316512. Protect the final 600 seconds
for cleanup. Before the first main dispatch, require the original full-main
forecast with 1.30 reserve to fit strictly within the new worker deadline
minus 300 seconds. No reduced sample or optimistic timing override. A failed
startup/qualification/forecast stops this one attempt and preserves its cost.
Timeout stops work, not billing; parent must supervise retrieval and direct
deletion verification, preserve unresolved reservations, and report any overrun.

Cleanup starts at most three final byte-verified recovery attempts within a
360-second window ending no later than 180 seconds before the hard deadline.
SSH/rsync timeouts shrink to that window; in-flight provider reads retain their
bounded 30-second timeouts. If recovery is exhausted
or the controller is already overdue, record potentially unrecovered artifacts
and delete only the receipt-bound owned pod. Never fabricate a final snapshot
or mark recovery successful. Confirm deletion by direct GET404 and absence from
inventory, with at most three checks; an unresolved provider response retains
the reservation and requires supervision, not an endless retry loop or a
second blind DELETE. Accounting includes elapsed time beyond the deadline.
Launch, monitor and CLI exceptions, including keyboard interrupts and
SIGTERM/SIGHUP, enter this cleanup path; repeated signals are ignored only
during bounded cleanup. Uncatchable process death still requires supervision.

### Startup Forecast

The preserved controller progress timestamps put creation at 04:50:21.322917,
model loaded at 05:02:28, live qualification at 05:02:30, and qualification
approval at 05:03:40 UTC. The last is 798.677083 seconds from creation,
including download, qualification and the retrieval barrier. The new timer
allows 1,316.18251157552 startup seconds after the unchanged full-main forecast,
600-second cleanup reserve and 300-second worker reserve. A 1.30 multiplier
on the observed startup gives 1,038.2802079 seconds, leaving about 278 seconds
of margin. This is a planning estimate, not a runtime guarantee or permission
to waive the actual pre-main gate. Cache/download variability can still stop
the attempt. No timer extension or reserve reduction is implied.

## Interface

After review, build once with
`python -m experiments.berg_dose_exposure_continuation.protocol`.
The new plan is `data/berg_dose_exposure_continuation/plan_v1_20261005/PLAN.json`.
It binds the old raw prefix, source/input hashes, selection, failure, exact main
inventory, cheap-qualification anchors and cumulative cost. Rebuild only while
unfrozen; after commit/push use its full SHA. Frozen historical files are never
edited. The controller checks the published plan and source closure before POST.

Local-only validation:
`python -m experiments.berg_dose_exposure_continuation.controller --plan data/berg_dose_exposure_continuation/plan_v1_20261005/PLAN.json --freeze FULL_NEW_SHA`

Parent-only execution adds `--launch`; lifecycle actions are `launch`, `status`,
`monitor`, `retrieve`, `reconcile`, and `terminate`. Without `--launch`, the CLI
does not read credentials or call the provider. The worker accepts `--plan`,
`--freeze`, `--out`, `--cache`, and `--deadline-utc`, as before.
Offline tests: `python -m pytest tests/test_exposure_continuation*.py -q`.
