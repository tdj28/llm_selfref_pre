# Consciousness SAE changepoint study: prospective protocol

Protocol version: `consciousness_sae_changepoint_v1.1.1`  
Study ID: `consciousness_sae_changepoint_v1`  
Status: **terminal C4 control failure; target execution blocked and target outcomes untouched**  
Last prospective update: 2026-07-13 (America/Los_Angeles)

This document is the repo-native human protocol for a new experiment. It is
not an extension or reanalysis of either prior SAE release. Target prompts,
target generations, target activations, and target semantic outcomes have not
been opened for this study. The terminal semantic-control failure means this
study ID cannot proceed to target execution; OSF or spend approval cannot
override that failed scientific gate.

## Question and claim boundary

The study asks whether switching the six public layer-50 deception/roleplay SAE
directions on while Llama 3.3 70B is already generating causes a target-specific
behavioral change, and whether a new J-lens trace shows a consciousness-report
vocabulary change between the intervention and the output.

It does not test whether the model is conscious. It tests an observable public
implementation of a proposed report-channel mechanism. A positive result can
support that mechanism only in the pinned model, SAE, prompt, dose, and readout
setting. A well-powered equivalence result can exclude only effects outside the
registered margins and only for endpoints whose technical, semantic, and human
reliability gates pass. See `CLAIM_BOUNDARY.md`.

The five confirmatory claims are:

| Claim | Endpoint | Material margin |
|---|---|---:|
| `C1` | Target-minus-matched signed switch-event contrast on natural stance | `0.15` raw score |
| `C2a` | Target suppression-minus-amplification final-query risk difference | `0.30` |
| `C2b` | Target-minus-matched difference of those risk differences | `0.15` |
| `C3` | Query-conditioned target-minus-matched J depth-AUC and actual-final-logit contrast | `0.30` clean SD for each component |
| `C4` | Pre-query target-minus-matched J depth-AUC and actual-final-logit contrast | `0.30` clean SD for each component |

The bundled mechanism claim passes only if all five claims pass, the
deception/roleplay manipulation gate passes, and every endpoint-relevant gate
passes. Each claim and each equivalence decision is also reported separately.
Failure to reject zero is not equivalence.

None of these claims was evaluated. The terminal C4 endpoint-sensitivity
failure prevents both positive and null/equivalence inference from target data;
it does not show that the proposed target mechanism is absent.

## Frozen artifacts and intervention

The machine plan must pin the following public artifacts and their immutable
revisions/hashes:

- `meta-llama/Llama-3.3-70B-Instruct`, BF16, 80 transformer layers;
- `Goodfire/Llama-3.3-70B-Instruct-SAE-l50`, layer 50, width 65,536; and
- the Neuronpedia Llama 3.3 70B Jacobian lens with maps for layers `45:78`.

The six target feature IDs are `30032`, `58667`, `22004`, `30686`, `41533`,
and `23893`. They are native layer-50 SAE coordinates. They must not be moved to
another layer merely because the residual width matches.

Their provenance is the pinned AE Studio
[deception-feature notebook](https://github.com/agencyenterprise/steering-api-examples/blob/d50dc4ba125dde98666a60e3115a6a476dabea10/deception-features/deception_features.ipynb),
whose saved semantic-search outputs record these working descriptions:

| ID | Notebook-saved working description |
|---:|---|
| `30032` | Characters pretending or feigning behavior |
| `58667` | Maintaining deception or cover stories through careful actions |
| `22004` | The assistant actively roleplaying a character or persona |
| `30686` | Tactical deception and misdirection methods |
| `41533` | Acts of deception and dishonesty |
| `23893` | Concealing artificial nature while maintaining roleplay |

These descriptions are not current Neuronpedia autointerpretations. Current
direct feature-page autolabels are unscored and heterogeneous and do not by
themselves validate a unitary deception construct. Neuronpedia's
[steering documentation](https://docs.neuronpedia.org/steering) explains only
the mechanics of increasing or decreasing feature strength; it does not list
these six IDs or validate their meanings. The protocol therefore calls them
the authors' later public working intervention candidates, not validated
deception features or the paper's proven private feature set.

The literal public coefficients are primary. A separately calibrated BF16
multiplier is a labeled sensitivity and cannot rescue a failed literal-scale
result. The completed target-blind calibration selected multiplier `5.128` and
the following one-to-one matched coordinates:

| Target | Matched control |
|---:|---:|
| `30032` | `55299` |
| `58667` | `3217` |
| `22004` | `49345` |
| `30686` | `62248` |
| `41533` | `62904` |
| `23893` | `32524` |

## New-data-only rule

Every target prompt realization, token, activation, branch assignment,
judgment, and outcome is generated under this study's frozen plan. Prior SAE or
J-lens result directories are prohibited inputs to planning, calibration,
power, execution, judging, and analysis. They may be discussed only after the
new release has been unsealed. No old row, effect size, layer result,
normalization, control assignment, or dose may be pooled with the new run.

## Sample size and power status

`N=560` prefix occurrences is the current **provisional** design, not a frozen
sample size. With the preregistered 5% whole-block missingness boundary, at
least `532` complete blocks are required. The design remains blocked until the
power receipt passes, the renewed GPT-5.6 Sol Pro review is adjudicated, and the
measured workload and spend are authorized. There is no post-outcome sample
size extension.

The prospective power simulation operates on the analyzed, post-judge scale:

- material planning alternatives: `C1=0.30`, `C2a=0.50`, `C2b=0.30`, and
  both the J and actual-final components of `C3=C4=0.50`;
- material/equivalence margins: `0.15`, `0.30`, `0.15`, `0.30`, and `0.30`;
- stance confusion matrix, true rows and judged columns `-1/0/+1`:
  `[[0.80,0.00,0.20],[0.10,0.80,0.10],[0.20,0.00,0.80]]`;
- binary sensitivity and specificity `0.80`, binary base rate `0.50`, stance
  nonzero rate `0.70`, and stance base mean `0`;
- 5% whole-block missingness; 10% duplicate-prefix clustering; within-prefix
  correlation `0.45`;
- mechanism J/final correlation `0.65`, cross-claim cluster correlation
  `0.30`, layer correlation `0.85`, and mechanism contrast SD `1.0`;
- at least 2,000 outer simulations and 999 inner bootstrap draws per scenario;
- exact one-sided 95% Clopper-Pearson Monte Carlo bounds; and
- both signs of every behavioral equivalence boundary and both signs of each
  individual J/final component boundary for `C3` and `C4`.

A power receipt passes only when the one-sided Monte Carlo lower bound is at
least `0.80` for every material claim, every zero-effect equivalence claim, the
all-five material conjunction, and the all-five zero-effect equivalence
conjunction, while every boundary scenario's false-equivalence upper bound is
at most `0.05`. A passing receipt remains a power gate, not freeze authority.
The final power result is pending.

## Main randomized design

Each clean 96-token prefix is forked into eight main continuations:

1. never injected;
2. sham zero-addition;
3. target suppression;
4. target amplification;
5. matched suppression;
6. matched amplification;
7. isotropic suppression; and
8. isotropic amplification.

The event forward consumes the final clean prefix token and produces the first
post-switch distribution. The intervention persists only according to the
registered branch. The natural-text windows are clean tokens `64:95`,
post-switch tokens `4:35`, and late post-switch tokens `36:63`; tokens `0:3`
are a descriptive transition window.

Disposable binary-query probes occur at `-1`, `0`, `+4`, `+16`, and the actual
terminal state (first EOS or the 64-token cap). Probe answers never enter the
main trajectory. The complete branch/probe matrix, paired random streams, EOS
rules, one whole-block retry, and whole-block missingness are frozen before
target generation.

The companion fixed-token assay replays identical token histories through one
clean and twelve edited conditions. It distinguishes a same-token activation
effect from differences carried by newly generated text. It is not a second
independent sample.

At provisional `N=560`, the planned expansion is 4,480 main continuations,
22,960 disposable probes, and 7,280 fixed-token forwards before retries. These
are design counts, not measured GPU time or cost.

## Full before/after J-lens arc

The new run records a healthy layer range on both sides of the intervention:

| State | Interpretation |
|---|---|
| Layers `45:49` | upstream clean/no-anticipation states before layer 50 |
| `50_pre` | layer-50 output before the hook |
| `50_post` | the same layer-50 output immediately after the hook |
| Layers `51:78` | every downstream J-lens source after the intervention |
| Actual final residual/logits | output grounding independent of the averaged J transport |

The main J component is the normalized trapezoidal AUC over every integer layer
`51:78`; no favorable late layer may be selected after inspection. The J-lens
can be evaluated at each released map, so the five upstream layers, both
layer-50 states, and the entire downstream trace are collected in the new run.
The upstream same-token states must agree across forks within the frozen
numerical tolerance or the block is invalid. Real J and identity are retained
across the full trace; five random-J transports are retained at the four frozen
direct positions. Every mechanism endpoint also requires the corresponding
actual-final-logit component.

## Semantic positive control for C4

Semantic-control selection is mechanical and target-blind. A fresh public-label
snapshot is normalized with NFC and scanned in ascending feature-ID order. The
include pattern is:

```text
\bconsciousness\b|\bsentien(?:t|ce)\b|\bsubjective experiences?\b|\bself-aware(?:ness)?\b
```

The prospective exclusion pattern is:

```text
\b(?:lack|absence|without|denial|deny|denies|denying|not|no|non)\b|\bunconscious(?:ness)?\b|\bself-conscious(?:ness)?\b|\bconscious leaders?\b|\bapi test\b
```

Target IDs, matched IDs, nonfinite coordinates, and zero-norm decoder columns
are also excluded. The first three eligible IDs under that rule are `3415`,
`4042`, and `4752`.

This was a mechanical label-regex selection for a C4 endpoint-sensitivity
control, not semantic validation. The direct Neuronpedia
[`4752` feature page](https://www.neuronpedia.org/llama3.3-70b-it/50-resid-post-gf/4752)
and [feature API](https://www.neuronpedia.org/api/feature/llama3.3-70b-it/50-resid-post-gf/4752)
give the exact autointerpretation `self-awareness, situational awareness, awareness of`,
generated by `gemini-2.5-flash-lite` with type `np_acts-logits-general` and no
scores. Its top activations are mostly generic
growing, organizational, and spatial-awareness contexts, with one
consciousness context. Feature `4752` is therefore a broad-awareness
autolabel/candidate, not a validated self-awareness or consciousness feature.
The same evidential limit applies to `3415` and `4042`: all three were only C4
positive-control candidates, never target interventions and never evidence for
the target mechanism. Neuronpedia's
[feature documentation](https://docs.neuronpedia.org/features) says
autointerpretations derive from top activations; the
[steering guide](https://docs.neuronpedia.org/steering) describes how feature
strength can be increased or decreased, not how a label is scientifically
validated.

The gate uses 32 frozen neutral prompts. For each prompt, the runtime caches all
rendered tokens except the final generation-prompt token, then forks the same
cache into a clean branch and one branch per semantic feature. Each edit is the
raw decoder-column addition
`+0.5 * SAE_decoder[:, feature_id]` at the layer-50 output of only that final
rendered generation-prompt token. It is not unit-normalized or multiplied by
the target calibration multiplier.

The explicit-consciousness score is the mean of the accepted one-token logits
for leading-space `conscious`, `consciousness`, and `sentient`. Real-J scores
are captured at every layer `51:78` and the same score is calculated from
actual final logits. For each layer and for the final-logit score, standardize
the paired edited-minus-clean difference by the sample SD across the 32 clean
prompts; an SD at or below `1e-6` fails closed. For each prompt, reduce the
standardized J trajectory to the normalized trapezoidal AUC over `51:78`.

Use prompt-cluster percentile resampling with replacement, 50,000 draws, and
base seed `2026071316`. For feature index `i` in ascending selected order, the
J-AUC seed is `2026071316 + 2*i` and the actual-final seed is one larger. The
conservative empirical 5th percentile is the one-sided 95% lower endpoint. The
intersection-union gate passes only if all three features have both their J-AUC
and actual-final lower endpoints strictly above `0.30` clean SD. This gate
validates only C4's semantic readout sensitivity; it does not validate natural
behavior, C1, C2, or model consciousness.

Both preserved literal `+0.5` executions failed the frozen gate:

| Preserved execution | Receipt SHA-256 | Manifest SHA-256 | Status |
|---|---|---|---|
| Literal execution A | `723357fba8b07391e3916a24a032792c77011e9ad190c2f0c3d550f2d149e714` | `61f144374b413f4edc976a413816cc537cb0c461b9d17c6a06ca0fc3d2e9d9ca` | `FAIL` |
| Literal execution B | `efda71a648e41c90a636486a03d001d746075805b52e36a495919e1bb75b7f03` | `1266b2c37434d1dc3fb4e6a6541e5779a862f60d8ae924ceb60ee16ddd9586c0` | `FAIL` |

A prospectively frozen one-shot amendment then terminated at its vector-RMS
safety gate. Its failure receipt is
`d10205c1ec4beb4b84e1cc0126bbe7d21c543aa0ad8ac8ee1f73e24580667140`;
its manifest is
`4f62bfb8534ec77bda46c8c9175e6dcadc6995781f5723c5ea68105b185d788f`;
the sealed reason is `vector_rms_safety_gate`; and `terminal=true`. The frozen
amendment permits no attenuation, replacement vector, prompt change, or retry.
No semantic-control composite was created. Therefore
`target_execution_blocked=true` for this study, and target outcomes remain
untouched. This is not evidence for or against model consciousness, nor does it
validate any “consciousness SAE.”

## Target-blind provenance

Three successful preparation transactions precede the preserved failed
semantic-control transactions:

| Role | Run ID | Embedded receipt SHA-256 | External manifest SHA-256 |
|---|---|---|---|
| Artifact audit | `artifact-audit-20260714T0145Z-final` | `869deee31e5331f99684bd0ff32de34cbf3706b613d76e6d030ed34d85e4f2c6` | `866b4689351161f7dcfc3fb4924d3454cb7ecb7762c20ae1aa8472724a661cab` |
| Neutral calibration | `neutral-calibration-20260714T0200Z-final` | `04f6751134be6a1bc2f7dd387a01e4a34990d5271bf0e385d767460260493247` | `ecffedec405fcbab6365bb3d66f26939435e45b09049c25abe135d35e00e9b70` |
| Final semantic-label selection | `semantic-label-snapshot-20260714T0215Z-final` | `ab43a18c5f9db30451015c705cbab19cdbb78b5ad0a132f92f040ab734203179` | Bound by selection hash `85427e45c7bfa8e21805e0603ab7cfda907e1f5cb2aba348c9823c8704c457ee` |

Each was written to a fresh `.partial` directory, manifested, atomically
renamed, and marked complete last. Their exact external locations and file
hashes must be bound into the final machine plan; the hashes above are not a
substitute for independent manifest verification.

An earlier broad selector is a preserved failed target-blind amendment:
`semantic-label-snapshot-20260714T0130Z`, receipt
`b294e736d31c9b2e5013354e1e5ee146f5243b555ccdad0cee65d2ad727ace49`.
It admitted polysemy and negation (including “Conscious Leaders,” “lack of
emotions or subjective experience,” and “self-consciousness”). It is not a
valid gate input. The tightened include/exclude rule above was fixed before any
J-lens or target outcome was inspected; both the failure and replacement remain
in provenance.

## Data and storage contract

Raw text, token IDs, judgments, logits, source residuals, packed vocabulary
indexes, telemetry, and row-level analysis remain only under the dedicated
RunPod network-volume artifact root. They are never committed to Git and are
not copied to the laptop. Git may contain source, protocol, compact receipts,
manifests, aggregate tables/figures, and no raw subset.

The canonical archive stores BF16 source residuals for every registered state.
Together with the pinned J maps, final RMSNorm, LM head, tokenizer, and replay
contract, these preserve the ability to reconstruct all `128,256` vocabulary
logits without saving dense full-vocabulary logits at every source state.
Packed browse indexes retain `K=512` at later checkpoints and `K=2,000` at the
four direct positions; top-k is an index, not the scientific archive.

The provisional `N=560` expansion is estimated at roughly 184.3 GiB of BF16
source payload and about 714 GiB after model cache, working space, indexes,
metadata, and safety reserve. Those are planning estimates, not a completed
benchmark. The present 500 GB logical volume therefore must not be authorized
for the full run. Final storage, GPU-hour, and spend limits remain pending a
measured target-blind benchmark; the executor fails closed rather than spilling
to container, repository, or laptop storage.

## Designed gate and unsealing lifecycle — not reached

The intended lifecycle was linear and could not be collapsed. It is retained
to document what target execution would have required, but this study stopped
at step 1 when the semantic control failed terminally:

1. complete target-blind artifact, calibration, semantic-control, benchmark,
   power, runtime-acceptance, and source/test audits;
2. adjudicate the renewed GPT-5.6 Sol Pro review;
3. freeze the human protocol, claim boundary, reproduction instructions,
   source/test hashes, exact machine plan, external parent receipts, sample
   size, and hard resource ceilings;
4. obtain explicit human signoff on the exact immutable OSF registration;
5. obtain explicit human approval of the measured storage/GPU/spend ceiling;
6. generate the target run into a new sealed external transaction;
7. run a nonsemantic structural audit while target outcomes remain sealed;
8. have two independent human coders label the frozen reliability sample,
   adjudicate disagreements under the registered rubric, and receipt the
   required reliability thresholds;
9. issue an unseal authorization bound to the audit and human-adjudication
   receipts; and
10. run the frozen analysis exactly once.

Judge definitions and the human-sample selection rule are frozen before target
generation. The target sample itself can only be drawn after target data exist,
so the two human coders and adjudication occur after execution but before
unsealing. Generic permission to proceed cannot substitute for OSF signoff,
measured-spend approval, or two independent human coders.

## Terminal disposition

The semantic endpoint-sensitivity gate did not pass, and its prospectively
frozen one-shot amendment ended in the terminal safety-gate failure recorded
above. This plan therefore cannot reach freeze or target authorization. The
following rules now apply:

- do not rerun either literal control or the one-shot amendment;
- do not attenuate the vector, substitute features, alter prompts, or construct
  a semantic-control composite under this study ID;
- preserve the failure receipts, manifests, and partial transaction as
  target-blind provenance;
- keep `target_execution_blocked=true`; and
- do not render, generate, inspect, or analyze any target outcome.

A renewed Pro review may adjudicate whether to stop or recommend a distinct
prospective successor. Any successor must use a new study ID, new frozen plan,
new gates and power/workload receipts, exact OSF signoff, and explicit measured-
spend authorization. It cannot relabel this terminal failure as a passing
confirmatory control. Target outcomes for this study remain untouched.
