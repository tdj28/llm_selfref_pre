# Later-Study Inventory

## Studies In The Manuscript (Updated 2026-10-05)

Every study that `paper/main.tex` draws on, as of 5 October 2026, with when
its plan was committed relative to its own outcomes. A public Git commit
freezes a plan's source; it is not a registry preregistration. Separately
planned studies were combined in the manuscript after their outcomes, and no
human coding of the labels has been done. The manuscript's conclusions rest
on the three studies marked "main". The owner chose to keep this list out of
the manuscript itself.

| Study | Manuscript section | Plan committed | Standing |
| --- | --- | --- | --- |
| Continuation swap, four API models (main) | 3.2 | 14 s before run start, after two analyzed pilots that already favored the instruction | Planned test; its prediction that the continuation would matter at least as much failed |
| Induction factorial and question templates | 3.3, 4.1 | Same plan | Planned comparisons; the predicted register advantage is not established, and the templates are not a clean factorial |
| Four-way rubric | 4.1 | Same plan | Exploratory by plan |
| Audit of 160 answers (main) | 4.2 | Before the new judgments, after the answers and their earlier labels were known | Post-hoc audit of a fixed packet; not a prevalence estimate |
| Bilingual Llama pilot | 3.4 | Before its collection | Pilot; language contrast inconclusive, swap estimates descriptive |
| Frontier-model pilot | 3.4 | Before its collection | Small descriptive pilot |
| Llama screening | 3.4 | Before its collection | Failed its preconditions; follow-up not run |
| Gemini/Opus neutral-instruction and donor controls | 3.5 | Before its new collection; earlier panels known | Separate screened panel; Gemini instruction advantage, Opus depends on scoring rule; no equivalence claim for the neutral controls |
| Qwen3.8 neutral-instruction and donor controls | 3.6 | Before its new collection; earlier panels known | Separate screened panel; primary simultaneous interval includes zero, contrast depends on rubric |
| Kolibri neutral-instruction and donor controls | 3.7 | Before its new collection; outcome-aware operational amendments disclosed | Separate screened panel; primary simultaneous intervals include zero; official FP8 runtime, no architecture-causal claim |
| Repeated Gemini/Opus answers | 3.8 | Before its new collection; earlier panels known | Randomized requests with three answer draws; two missing structured judgments retained; fixed-panel estimates and missingness bounds reported separately |
| Qwen companion study | 6 | Separate study | Audited after its outcomes |
| Random-subset steering test (main) | 5.3 | Before its outcomes; earlier results known | Planned test; +0.30 excluded under the paper rubric, inconclusive under the second |
| Quality-selected mapping-scaled dose | 5.4 | Before each new sample; earlier failed quality checks disclosed | +0.30 narrowly excluded at the selected dose; target specificity unresolved; not an all-dose null |
| Operator matching and dose ladder | 5.5 | Before their outcomes | No configuration qualified; holdout not run |
| Native-precision follow-up | App. D | Before its outcomes; earlier results known | Planned comparison; secondary diagnostics descriptive |
| Feature activation maps | App. C | Amended before the new activations; earlier maps known | Descriptive check of the feature labels |
| Earlier 4-bit Llama grid | App. C | 73 s before the run | Planned test; untreated rate near the ceiling |
| Gemma 2 9B study | App. C | About 3 min before steering outcomes | Planned test; weak target manipulation |
| Steering-fidelity calibration | App. E | Before its outcomes | Pressure wordings did not lower accuracy enough; test not run |
| Fixed-panel and exact intervals | App. G | After the outcomes | Post-hoc |
| Truncation bound for the random-subset test | 5.3 | After the outcomes | Post-hoc |
| Convergence and paradox probes | App. H | — | Exploratory, GPT-4o only |

Commit timing comes from the [analysis chronology](ANALYSIS_CHRONOLOGY.md)
and each study's protocol; the manuscript's last appendix lists every release
directory and the commit its links point to.

## Added 2026-10-02

The [steering-fidelity calibration](STEERING_FIDELITY_CALIBRATION_RESULTS_20261002.md)
is complete: 9,300 known-answer forwards, released raw data, three figure
pairs and all owned pods terminated. A common numerical dose of 0.30R
qualified, but the truth-stratified user-pressure gate failed and the JSON
positive-control features were inactive on their probes. The held-out
fidelity/opposing-claims experiment was not run. This addition does not change
the dated inventory below or make a new experience-report mechanism claim.

## Original 2026-09-29 Inventory

Engineering inventory checked against the public tree at `39c21e0` on
2026-09-29. This is an index, not a new analysis, independent scientific
review, or execution authorization. The six namespaces below are separate
from the causal-transplant, public-weight steering, Gemma, and J-lens v1/v2
releases. Five contain Python implementations; switch-arc is a design draft.
None supplies a completed test of the paper's consciousness-report endpoint.

| Family | Recorded status and public evidence | Boundary |
| --- | --- | --- |
| [Readout validation](../experiments/consciousness_readout_validation/) | [r15 compact result](../data/consciousness_readout_validation/pilot_v1_result_20260714_r15/README.md): completed pilot, overall frozen status `fail`; arithmetic and clean-readout controls passed, transport/linearity requirements did not. | Instrument pilot, not a consciousness or SAE causal result. |
| [SAE changepoint](../experiments/consciousness_sae_changepoint/) | [Protocol](consciousness_sae_changepoint/PROTOCOL.md): terminal C4 control failure; target execution blocked and target outcomes untouched. | Planned target endpoints were not evaluated. The directory README's earlier draft status is stale. |
| [SAE realization validation](../experiments/consciousness_sae_realization_validation/) | [Successor's disclosure](consciousness_sae_target_blind_calibration/PROTOCOL.md) records Stage A execution and failed 1% delivery fidelity and downstream linearity; no completed Stage B result was located in the public tree. | Its README/protocol still say not executed. Treat that as documentation drift, not evidence that Stage A was absent or Stage B completed. |
| [Target-blind calibration](../experiments/consciousness_sae_target_blind_calibration/) | [Final recovery summary](consciousness_sae_target_blind_calibration/results/calv2-r3-audit-recovery-3a9a54d-20260716T202903Z/README.md): 120 generic-direction rows; audit-only recovery completed, with original failures retained. | No target SAE vectors, paper prompts or behavioral outcomes. The learned-J-over-identity conjunction did not pass. |
| [Signed dose scan](../experiments/consciousness_sae_signed_dose_scan/) | [Final recovery summary](consciousness_sae_signed_dose_scan/results/signed-dose-a084caa-wl8obvtuq0ax8t-v2-audit-recovery-c9/RESULT_SUMMARY.md): completed generic-direction scan and audit-only recovery; source-delivery fidelity failed at the smallest doses. | Eight neutral prompts and three generic directions, not the paper's target experiment. Learned-J added value over identity did not pass the composite rule. |
| [SAE switch-arc](consciousness_sae_switch_arc/README.md) | Target-outcome-empty successor draft; recorded review verdict not ready to freeze. No implementation namespace or completed outcome release. | Not preregistered, not executed, and no target conclusions. |

## Availability And Interpretation

These later families store compact plans, receipts, prose and selected figures
in Git. Their documents place raw tensors and row-level measurements on
external RunPod volumes. This engineering pass did not access those volumes;
public compact files do not substitute for independently available raw data.
No current volume availability or continuing storage-cost claim is made here.

The calibration and dose-scan summaries describe downstream nonlinearity. That
interpretation is disputed by the review's additive numerical-floor account.
Do not cite these summaries as establishing a nonlinear mechanism independent
of BF16/numerical-floor effects without the proposed precision control. This
inventory neither proves that alternative nor revises frozen results.

The historical strict-equality J-layer inventory bug is preserved in the
original auditors. Separate recovery adapters already accept the pinned
superset and reject missing required layers; regression tests cover both.
Deleting or rewriting the original auditors would obscure the failure chain.

Archiving, moving studies, publishing additional raw data, changing licenses,
or recovering old public history requires separate owner decisions. No study
was removed, retried, reclassified as confirmatory, or authorized by this index.
