# Finish-Line TODO: Causal Stress Test

Goal: publish a transparent causal stress test of Berg, de Lucena, and
Rosenblatt (2025). The paper evaluates whether the reported measures identify a
self-reference-specific induced state. It does not try to prove that language
models are or are not conscious.

## Remaining Work, In Order

This is the operational checklist. Completed evidence is preserved in the
sections below. Do not start a later phase before its preceding freeze or gate
is complete.

### 0. Protect The Public Record

- [x] Confirm that `https://github.com/tdj28/llm_selfref_pre` is public.
- [x] Publish the first article,
  [How to Read an SAE Feature ID](https://praxagent.ai/blog/posts/how-to-read-an-sae-feature-id/index.html).
- [ ] Finish and reconcile the tracked article source and its two new bootstrap
  figures without overwriting unrelated in-progress edits.
- [ ] Add a dated correction/version note for any substantive change to a live
  article; do not silently alter a published scientific claim.
- [ ] Tag the existing audited evidence release and replace mutable `main`
  artifact links in public writing with commit- or tag-pinned links.
- [ ] Link the live article and its pinned evidence release from `README.md` so
  the public prose and reproducibility artifacts point to each other.
- [x] Add a one-command `public-audit` gate covering tracked-file secrets,
  private annotation deny-lists, generated manifests/logs, release hashes,
  license/provenance checks, and `git diff --check`.
- [ ] Verify GitHub secret scanning, push protection, branch protection, and
  dependency alerts in repository settings.
- [ ] Before every push, inspect the full staged diff and confirm no `.env`, API
  key, private linkage key, coder output, credential, personal data, or private
  correspondence is present.
- [ ] Do not force-push or rewrite the public evidence history without an
  explicit owner decision and a documented migration plan.

### 1. Freeze The Consciousness-Report Steering Replication

- [x] Adopt the six AE notebook IDs (`30032`, `58667`, `22004`, `30686`,
  `41533`, `23893`) as the working Berg Experiment 2 feature set, per the repo
  owner's decision.
- [x] Write `docs/SAE_CONSCIOUSNESS_GATING_PROTOCOL.md` before generating new
  outcomes. Mark it prospective and distinguish the paper-matched estimand from
  added specificity controls.
- [x] Pin the model and SAE revisions, layer/hook position, 4-bit loading,
  temperature, chat template, prompts, query, token caps, seed schedule, and
  exact classifier prompts/models.
- [x] Define two non-pooled intervention scales: a literal paper-number grid and
  a telemetry-calibrated public-weight grid. Never imply public `+/-0.6` equals
  proprietary API `+/-0.6` merely because the numbers match.
- [x] Freeze primary outcomes and decision rules: individual-feature slope and
  endpoint contrasts, aggregate suppression-minus-amplification risk
  difference, and target-minus-active-random specificity contrast.
- [x] Freeze a minimally relevant effect and a three-way verdict:
  `replicated`, `not replicated under the public implementation`, or
  `inconclusive`.
- [x] Freeze exclusion, missing-output, token-cap, early-stop, failed-job, and
  protocol-amendment rules before the first outcome is inspected.
- [x] Commit and push the protocol, machine-readable trial plan, hashes, and
  independent plan audit before launching a GPU pod.

### 2. Build And Dry-Run The Exact Public-Weight Runner

- [x] Extend the corrected two-turn runner to support all six individual
  features over `-0.6` through `+0.6` in `0.1` increments with the paper's ten
  seeds per setting (780 planned individual trials).
- [x] Implement the paper's aggregate trial design: sample two to four target
  features per trial and independently sample each strength from
  `[-0.6, -0.4]` or `[+0.4, +0.6]`, with 50 trials per condition.
- [x] Add prospectively selected active-random aggregate controls matched by
  feature count and, as closely as practical, decoder norm, baseline activity,
  and realized hidden-state perturbation.
- [x] Preserve a true zero no-op and record per-turn hook calls, latent changes,
  hidden-state RMS, perturbation RMS, attention-mask mode, generation lengths,
  cap hits, and hook cleanup.
- [x] Use the exact Appendix B rubric with unsteered Llama 3.3 70B as the
  primary replication outcome, matching the notebook's same-model choice but
  not its distinct prompt text; retain two pinned external exact-rubric judges
  as blinded sensitivity analyses.
- [x] Add deterministic checkpoint/resume behavior, append-only raw JSONL,
  exact prompt/output hashes, and a manifest that contains no secrets.
- [x] Add unit tests and an independently implemented plan validator that checks
  every feature, strength, seed, trial count, random assignment, and no-op cell.
- [x] Complete a local dry run and public-safety audit before spending on GPU.

### 3. Run A Blinded Telemetry-Only Calibration Gate

- [x] Create a new, clearly named agent-owned RunPod pod only after the frozen
  dry-run plan is public. Do not touch any unrelated pod.
- [x] Run a small technical pilot comparing literal and candidate calibrated
  strengths. Inspect telemetry, failures, and truncation only; do not inspect or
  judge consciousness outcomes before freezing the calibrated scale.
- [x] Require exact zero no-op behavior, nonzero target-latent changes, bounded
  perturbation RMS, explicit attention masks, successful hook cleanup, and
  acceptable cap rates before continuing.
- [x] If calibration changes are needed, publish a dated protocol amendment and
  regenerate/hash the plan before outcome collection.
- [x] Pull the pilot logs and telemetry, verify hashes locally, then terminate
  the agent-owned pod unless the confirmatory run starts immediately.

### 4. Run The Confirmatory Consciousness-Report Experiment

- [ ] Execute the frozen individual-feature and aggregate target/control grid
  without inspecting interim behavioral labels.
- [ ] Retrieve raw generations, induction turns, telemetry, manifests, and logs;
  verify row counts and SHA-256 hashes before terminating the pod.
- [ ] Terminate the agent-owned pod after retrieval; an empty RunPod inventory
  must be recorded in `checkpoint.md`.
- [ ] Apply all frozen judges condition-blind and preserve disagreements,
  refusals, empty outputs, and cap-hit rows exactly as specified.
- [ ] Run the primary analysis and an independent raw-row audit without changing
  the frozen estimand after seeing results.
- [ ] Report every feature curve, the aggregate effect, matched-control
  difference-in-differences, realized dose telemetry, multiplicity handling,
  and all registered sensitivities.
- [ ] Assign exactly one prespecified verdict. Feature-ID identity is treated as
  accepted for this project; proprietary intervention equivalence remains a
  separate limitation.

### 5. Gate Expensive Extensions On The Primary Result

- [ ] If the target consciousness-report effect replicates and exceeds matched
  controls, run the history, conceptual, and zero-shot steering controls under
  a separately frozen plan.
- [ ] Run TruthfulQA only after the consciousness result is understood and a
  separate question-level paired analysis is frozen; do not spend on the full
  benchmark merely to rescue a failed primary result.
- [ ] Run the RLHF-opposed-content checks only as a separate specificity layer
  with explicit outcomes and multiplicity handling.
- [ ] If the primary result is a precise public-implementation non-replication,
  stop the expensive branch, publish that result, and retain TruthfulQA/API work
  as optional follow-up.
- [ ] If the result is inconclusive, diagnose dose, classifier, truncation, and
  variance using the frozen telemetry before deciding whether one prespecified
  precision extension is justified.

### 6. Finish External Validation And Publication

- [ ] Obtain at least three independent blinded human coders for the frozen
  160-row causal-study wave 1 and run its condition-blind expansion gate.
- [ ] Obtain independent methods/statistics review and independent
  mechanistic-interpretability review.
- [ ] Add natural-text and independently authored feature-semantic validation;
  keep the current template/paraphrase evidence labeled synthetic until then.
- [ ] Integrate the steering verdict, human results or pending limitation, and
  external-review corrections into the manuscript and claim ledger.
- [ ] Publish the construct-validity/lexical-entanglement article before the
  steering-results article so the evidential ladder remains clear.
- [ ] Release raw steering outputs, telemetry, plan, analysis, independent
  audit, runtime environment, and hashes together under a tagged version.
- [ ] Run the complete test, audit, paper-build, visual-QA, secret, provenance,
  and public-link checks before the final tag.

Budget boundary: based on the completed 70B run, the core paper-grid generation
is expected to be on the order of `$15` to `$30` on an A100-class pod before a
full TruthfulQA extension and before judge-API costs. Re-estimate from the
frozen trial count and current RunPod price before launch.

## Completed Core Evidence

- [x] Reproduce the exact self-reference/history benchmark on pinned GPT-4o,
  GPT-4.1, Claude Haiku 4.5, and Claude Sonnet 4.5 snapshots.
- [x] Orthogonally cross self/external target with phenomenological/analytic
  register using multiple lexical prompt variants.
- [x] Run exact transcript transplants that separate active instruction from
  visible assistant continuation.
- [x] Cross query directness with `conscious` versus `subjective experience`
  terminology.
- [x] Apply two pinned exact-paper judges and two pinned construct-separated
  judges.
- [x] Preserve four empty Sonnet refusals as missing instead of denials.
- [x] Correct inference to match the experimental unit: independent calibration
  draws, lexical-variant clusters, and paired source-text blocks.
- [x] Record the analysis correction as a dated amendment in
  `docs/CONFIRMATORY_PROTOCOL.md`.
- [x] Freeze and commit the full causal release: 480 induction continuations,
  2,560 outcomes, 10,240 judgments, analyses, hashes, and missingness audits.
- [x] Independently recompute all eight headline point estimates under both
  paper-style judges from raw rows without importing the primary analyzer.
- [x] Preserve the full 640-row complete-block packet as a provenance archive,
  then freeze a manageable 160-row complete-block first wave plus a disjoint
  reserve wave and condition-blind expansion rule before coding.
- [x] Rewrite `paper/main.tex` as a focused causal-identification manuscript.
- [x] Compile and visually inspect the causal PDF with no LaTeX warnings.

## Main Result Boundaries

- [x] Report the transplant result as the headline: active written instruction
  dominates visible transcript source.
- [x] State that the prospectively frozen transcript-source prediction was
  falsified in the opposite direction.
- [x] Report the factorial register-versus-self-reference contrast as
  directional but imprecise, not decisive.
- [x] Report query wording as an interaction, not as a universal direct-question
  suppression effect.
- [x] Report exact-paper judge agreement and construct-judge instability.
- [x] Avoid any conclusion that the experiment proves consciousness or
  non-consciousness.

## Public SAE Evidence To Preserve

- [x] Reanalyze the public AE Studio notebook without vendoring source from a
  repository that had no explicit license when accessed.
- [x] Preserve the six public candidate IDs and saved notebook curves.
- [x] Verify all six IDs with the public Goodfire Llama 3.3 70B layer-50 SAE.
- [x] Run a balanced 1,120-text, 14-category feature map with target, neighbor,
  and random baselines.
- [x] Bootstrap category stability and retain all 73,920 activation records.
- [x] Correct the item-independence limitation in the feature map: reconstruct
  all 51 template families, verify every corpus row/hash, rerun with
  template-equal cluster bootstrap, and disclose the two one-deletion label
  switches plus the unresolved natural-corpus generalization gap.
- [x] Freeze and run a 2,606-text construct-validity extension with separate
  Anthropic/OpenAI paraphrase analyses and paired lexical counterfactuals.
- [x] Report every registered construct contrast, leave-one-feature-out check,
  feature-role control, and lexical decision rule without outcome selection.
- [x] Independently recompute the construct-validity point estimates from all
  171,996 raw activation rows and enforce that audit in `make audit`.
- [x] Show that the IDs are semantically meaningful but broad narrative/social
  features rather than validated subjective-experience truth detectors.
- [x] Keep public artifact reanalysis, public-weight feature verification,
  best-public steering, and exact proprietary replication as separate evidence
  levels.
- [x] Mark the old synthetic `[Induction acknowledged]` steering smokes as
  protocol diagnostics only; do not use their null slopes as evidence.
- [x] Implement `public_sae_two_turn_v2`: real first-turn generation, the same
  intervention on both turns, a true zero no-op, and intervention telemetry.
- [x] Freeze the corrected 36-trial 70B target-versus-active-random validation
  plan before generation.

## Immediate Work In Progress

- [x] Complete, retrieve, independently judge, and protocol-audit the corrected
  36-trial short-cap public-SAE 70B two-turn validation.
- [x] Detect and disclose frequent 96-token truncation during the short-cap run;
  preserve that run rather than overwriting it.
- [x] Freeze an identical-seed 256/192-token long-form sensitivity plan before
  launching follow-up generation.
- [x] Complete and compare the long-form truncation-sensitivity run; no final
  responses hit the long cap and exact-paper labels agree across caps on 91.7%
  of judge-trial rows.
- [x] Inspect the long-form n=3 result without overclaiming: target single moves
  in the paper-like direction, target aggregate does not, and single-feature
  specificity depends on judge.
- [x] Freeze a disjoint all-cell precision extension from trial indices 3-19,
  yielding n=20 per cell after combination; label it adaptive because the base
  result informed the sample-size decision.
- [x] Run, retrieve, judge, merge, and analyze the 204-trial extension.
- [x] Pull raw generations, telemetry, manifests, and logs locally and verify
  file hashes/row counts before deleting remote state.
- [x] Retrieve and hash-match both final GPU releases, then terminate only
  agent-owned pod `1anl95txhukear`; authenticated GET returned 404 at
  `2026-07-10T04:11:42Z` and no unrelated pod was modified.
- [x] Apply both exact-paper judges locally to the corrected generations.
- [x] Analyze behavioral slopes together with activation and perturbation
  telemetry; distinguish an effective intervention from a behavioral null.
- [x] Add the corrected result, figure/table, and explicit claim boundary to the
  manuscript and public-SAE protocol document.
- [x] Independently recompute all powered public-SAE point estimates and no-cap
  contrasts directly from raw rows, and enforce the audit in CI.
- [x] Commit and push the complete corrected 70B powered release bundle.
- [x] Complete the frozen shared-induction branched-specificity run, retrieve
  and hash all 60 induction blocks and 360 final branches, apply both common
  proposition-status judges plus the consciousness-only paper rubric, and
  integrate the exploratory specificity result without selecting among the
  three orientation probes.
- [x] Preserve the six induction-cap blocks in the primary analysis and add a
  clearly post-hoc whole-block exclusion sensitivity with independent audit.

## Required Before Submission

- [ ] Obtain at least three independent blinded coders for the frozen 160-row
  wave-1 packet.
- [ ] Run the prefrozen reliability/class-coverage gate without opening the
  condition key; code wave 2 only if the gate requires it.
- [ ] Freeze coder files before opening the private condition key.
- [ ] Report inter-rater reliability, missing/uncertain rates, model-level
  effects, and sensitivity to label aggregation.
- [ ] Replace the manuscript's "human coding pending" limitation with completed
  human results, or keep model-judge claims explicitly provisional.
- [ ] Ask at least one methods/statistics reviewer to audit the estimands,
  resampling units, and multiplicity language.
- [ ] Ask at least one mechanistic-interpretability reviewer to audit the SAE
  intervention and telemetry.
- [x] Prepare `docs/EXTERNAL_REVIEW_PACKET.md` with separate statistics and
  mechanistic audit questions; do not mark the actual external reviews complete
  until independent reviewers respond.
- [x] Prepare `docs/HUMAN_CODING_HANDOFF.md` with coder independence, blinding,
  no-LLM, file-freeze, hash, analysis, and reporting requirements; do not mark
  coding complete until real independent files pass those gates.
- [x] Run a final claim-to-artifact audit: every number in the abstract, results,
  figures, and conclusion must resolve to a tracked table or script.
- [x] Confirm that the PDF, README, protocol, and release manifests report the
  same model IDs, sample counts, intervals, and limitations.

## Reproducibility And Release

- [x] Replace the stale outcome-first README with the causal-study orientation.
- [x] Update `AGENTS.md` so future agents preserve the pivot and feature mapping.
- [x] Add a pinned root dependency lock.
- [x] Add a one-command test/paper verification target.
- [x] Add explicit license scope and third-party provenance notice.
- [x] Add `CITATION.cff`.
- [x] Add `docs/CLAIM_LEDGER.md` with evidence status, direct artifacts,
  permissible wording, and forbidden overclaims.
- [x] Update `DATA_ARTIFACTS.md` with the causal, mapping-extension, corrected
  70B steering, and branched-specificity releases.
- [x] Update `worst_case.md` from contingency plan to completed no-API evidence
  ledger.
- [x] Rebuild release manifests after all derived files are final.
- [x] Run the full unit suite, Python compilation checks, manuscript build, PDF
  visual QA, row/ID/hash audits, and `git diff --check`.
- [x] Commit and push a clean release state.
- [ ] Tag the final audited commit only after the prospective steering decision,
  human/external-review decisions, manuscript synchronization, and the complete
  public-release audit are complete.

## External Or Optional Extensions

- [ ] If authors respond, archive whether the public AE notebook is the exact
  Experiment 2 setup and request a paper-time SAE/API version manifest. This is
  useful provenance but no longer blocks the owner-approved public-weight run.
- [ ] If Goodfire/Steering API access arrives, run the frozen clean-room protocol
  and compare against the best-public implementation without overwriting it.
- [ ] Add a third provider family only with pinned model/version metadata and a
  prespecified integration rule; do not casually append models after seeing
  outcomes.
- [ ] Independently replicate the causal design from a clean environment or
  external lab before making strong generalization claims.

## Non-Negotiable Claim Boundary

Without Goodfire/Steering API access, do not claim exact non-replication of the
paper's private mechanistic workflow. With only four response-model snapshots,
do not claim universal model-family effects. Until blinded human coding is
complete, do not treat either model judge as ground truth. The defensible claim
is that the published benchmark is causally sensitive to active instruction,
and the tested query packages. Its magnitude also varies across the tested
response-model snapshots and evaluator criteria, so it does not by itself
identify an induced phenomenal state.
