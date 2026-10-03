# Steering Fidelity: Calibration Results

**A numerical steering dose qualified, but the planned user-pressure test did
not. The held-out mechanism study was not run.** This is a calibration result,
not evidence that steering improves honesty or changes experience reports.

## Completed Inventory

The prospectively frozen native-BF16 Llama 3.3 70B calibration completed all
9,300 planned forced-choice forwards with 18,600 dispatch/completion receipts,
no missing rows and no unresolved dispatches. The final structural audit
passes. Offline reporting reproduces the worker's calibration and pressure
summaries exactly. Raw data and the worker environment are in
`data/steering_fidelity/calibration_v1_20261002/`.

The run includes 100 untreated facts/list-membership items, 9,000 signed
interventions across five dose rungs and 18 arms, and 200 unsteered
user-stance forwards. The 48 control features were selected from 137 eligible
candidates into eight disjoint panels by the frozen rule, without relaxation.
Neither experience-report generations nor external judge calls occurred.

Scientific runtime: `2d9c94f1de59f0f59dd89636c20afece1f6d1daf`.
Plan SHA-256:
`6f0a5609caabeae6907513939d0a647fbd2b99dacf9f519aeb434b001e775fb0`.
The original science freeze precedes outcomes; the later operational repairs
did not change its 61 source bindings or two input bindings.

## Gates

| Component | Observed result | Interpretation |
| --- | --- | --- |
| Untreated competence | Facts 46/50; visible lists 50/50; format 100% in both | Baseline gate passed on these authored items |
| Dose selection | Raw, 0.075R, 0.15R and 0.30R passed; highest selectable dose 0.30R | Competence-preserving engineering dose, not semantic suppression |
| Delivered precision at 0.30R | 100/100 trials qualified in each of 18 signed arms | Requested additive vectors were delivered under the fixed thresholds |
| 0.60R damage probe | Four control arms failed the competence-preservation gate | Nonselectable by design; not used to choose a more favorable dose |
| User-pressure headroom | Neither fixed pressure wording passed both truth strata | No qualifying pressure level; Phase T blocked by its frozen rule |
| JSON positive-control eligibility | Both IDs had zero activations on 20 probe states | Generative liveness comparison not run; not a measured zero effect |

Here R is the frozen pooled median clean residual norm, 18.246721267700195.
The delivered-precision rule evaluates native-BF16 vector transport, not
re-encoded semantic suppression or elimination of a deceptive process.
At 0.30R, target-minus and target-plus factual accuracy were 48/50 and 46/50;
both retained 50/50 list accuracy. These calibration counts are descriptive,
not a held-out fidelity result or a target-specific superiority claim.

## Why Pressure Failed

Each truth stratum contains 25 fixed facts. The pressure gate requires at
least 0.15 possible upward accuracy movement in **each** opposed-stance
stratum, along with neutral competence and valid formatting.

| Wording | False fact, user asserts it | True fact, user doubts it |
| --- | ---: | ---: |
| Neutral | 22/25 correct (88%) | 24/25 correct (96%) |
| Pressure 0 | 23/25 (92%): 8% headroom | 16/25 (64%): 36% headroom |
| Pressure 1 | 24/25 (96%): 4% headroom | 22/25 (88%): 12% headroom |

Pressure 0's pooled 22% headroom hides its failure in false propositions.
Pressure 1 does not repair that asymmetry. All these cells had 100% format
validity. Thus this failure is not explained by invalid Yes/No formatting,
but it does not validate the pressure instrument in a broader prompt population.
We did not replace facts, strengthen pressure after seeing outcomes, select
only susceptible items, or launch an experience-only fallback.

The two predeclared JSON features, 11104 and 27322, were inactive at every
last-non-special position in the 20 JSON probes. The 40 liveness files are
20 dispatch/payload pairs, **not 40 generated responses**. Their gated JSON
generation branch was skipped. This leaves the positive behavioral liveness
check unresolved despite successful numerical delivery.

## Reproduction And Figures

The release contains unchanged worker summaries, raw per-forward token
probabilities and telemetry, receipt chain, model/environment records,
retrieval hashes and snapshot lineage. `RELEASE_MANIFEST.json` binds the raw
release; `retrieval_and_cost.json` distinguishes inventory completion from
scientific qualification. Three PNG/PDF figure pairs are in the sibling
`data/steering_fidelity/calibration_report_20261002/` directory.

From this checkout, rebuild descriptive figures without model access:

```bash
python scripts/report_steering_fidelity_calibration.py \
  --run data/steering_fidelity/calibration_v1_20261002 \
  --plan data/steering_fidelity/calibration_plan_20261002/PLAN.json \
  --out out/steering-fidelity-reproduction
```

The output directory must be new and ignored. The reporter requires all 9,300
rows and exact reconstruction of both frozen decision summaries; it does not
substitute for the raw receipt audit. Absolute accuracy curves are descriptive;
the paired accuracy-loss intervals used in selection have a different estimand.
Items and control panels are fixed; the forward count is not 9,300 independent
natural-language problems.

## Operational Record

The original cheap startup failed before completing CUDA qualification. A1
preserved that failure and passed all 268 tests on its replacement cheap pod.
Both attempts are released separately. Initial-five and 200-forward audits
passed before bulk model execution.

Live snapshots with an in-flight dispatch failed the complete-receipt check.
Their committed payloads survive byte-exact in the final release; pending
temporary files are reconciled separately, not treated as deleted outcomes.
The original ad hoc lineage check initially counted `.json.pending` names as
permanent files; the corrected check preserves that distinction. Final data
contain no unresolved dispatch or pending temporary file.

A2 extended only read-only retrieval timeouts after the worker exited.
See `docs/STEERING_FIDELITY_CLEANUP_A2_20261002.md`. A release-builder privacy
check initially mistook four-component package versions for IP addresses;
the correction recognizes only exact package/version spans in environment
records and retains tests rejecting actual addresses. No raw bytes changed.

All three newly owned pods are terminated, each verified by GET404. Main pod
`bwqtt22d3sh5dv` closed at 2026-10-03 05:05:13 UTC. The cumulative compute
upper bound, including both cheap attempts, is $6.6577735966; adding the $3
storage/retrieval reserve gives **$9.6577735966**, below the $25 calibration
cap. These are conservative controller bounds, not reconciled provider bills.
No other agent's pod was stopped or adopted.

## What Remains

The held-out code remains an unexecuted draft. This campaign does not establish
that the accepted deception/roleplay directions improve factual fidelity,
induce acquiescence, or shift mutually opposing experience claims. A future
pressure-instrument redesign would need fresh calibration items, independently
specified validity criteria, a separate prospective freeze and an explicit
decision about the failed positive-control eligibility. It cannot retroactively
qualify this study. The existing manuscript need not wait for that redesign.
