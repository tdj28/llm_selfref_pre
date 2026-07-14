# GPT Pro review context: SAE realization validation v1

Prepared: 2026-07-14

Study ID: `consciousness_sae_realization_validation_v1`

Status at review: **prospective, paper-target-free, not executed**

## Review objective

Review the accompanying protocol, machine-plan manifest, source inventory,
and bounded implementation evidence adversarially before paid execution. Do
not infer that a source hash exposes code that was not included in the review
packet. The central question is whether this design can separate:

1. FP32-request versus native-BF16 versus realized-edit distortion;
2. generic downstream transformer curvature after a realized additive edit;
   and
3. SAE-direction-specific dose behavior relative to matched-SAE and isotropic
   controls.

Return ordered findings with severity (`stop-ship`, `major`, `minor`), exact
evidence, consequence, and a concrete correction. State whether the exact plan
is safe to execute as a neutral diagnostic. Treat “freeze-ready” and
“scientifically supports the later paper experiment” as separate decisions.
Do not upgrade a failed prior gate or infer a consciousness result.

## Disclosed motivation, not computational input

The separately audited r15 pilot failed its intervention-grade transport
gate. All 64 frozen generic-direction dose-comparison sites failed magnitude
proportionality; 56 also failed direction proportionality. Its residual-space
real-J-minus-identity 95% lower bound was `0.016821`, below the frozen `0.020000`
margin, while the corresponding logit-space test passed. No paper prompt or
target outcome was rendered.

That result does not show that SAEs are nonlinear. The failed dose test used
generic deterministic residual directions, not SAE decoder columns. The old
run did not retain the requested/native/realized tensors needed to distinguish
BF16 realization error, generic downstream curvature, and a slope-analysis
problem. No r15 row, vector, match, effect, threshold adaptation, or raw file is
an input to this successor.

The wider literature makes nonlinear or non-monotonic steering response
plausible but does not diagnose r15 or validate this design:

- [Riegler and Torpmann-Hagen (2026)](https://arxiv.org/abs/2605.03160) report
  an inverted-U response and a qualitative mode switch for a tested SAE
  feature, with limited model coverage;
- [Taimeskhanov, Vaiter, and Garreau (2026)](https://arxiv.org/abs/2602.02712)
  analyze non-monotonic activation-steering response across strength;
- [O'Brien et al. (2025)](https://arxiv.org/abs/2411.11296) report both stronger
  refusal steering and collateral over-refusal/performance costs; and
- [Chalnev, Siu, and Conmy (2024)](https://arxiv.org/abs/2411.02193) motivate
  SAE-targeted steering partly because direct steering effects can be hard to
  anticipate.

These references justify measuring a full dose response and side effects;
they are not evidence that the present result will be nonlinear or SAE-specific.

## Exact proposed experiment

Both stages use Llama 3.3 70B Instruct in BF16, the pinned Goodfire layer-50
SAE, and all released J-lens source maps from layers 45 through 78. Each prompt
is rendered once; a shared KV prefix is forked to a fixed forward of the final
prompt token. There is no continuation generation, paper prompt, judge, or
behavioral endpoint.

Stage A uses eight new mundane prompts, edit layers
`45,50,55,60,65,70,75,78`, three seeded unit-RMS Gaussian directions, requested
RMS fractions `0.25%,0.5%,1%,2%,4%,8%`, and both signs: 2,304 edited forwards.
It stores FP32 request, native BF16 request, exact pre/post hook tensors,
realized signed/central/common-mode deltas, the 45–78 source arc, immediate
post-edit state, actual final residual, FP32 J shadows at the eight edit layers,
and real/identity/five-random-J metrics. The two lowest doses diagnose the BF16
floor; only 1–8% enters the frozen linearity gate.
The layer-50 subset of the BF16-versus-FP32 J shadows has its own frozen
`cosine >= 0.995`, `relative RMSE <= 0.10` status. It is distinct from both
the 34-map arithmetic/orientation receipt and edit realization.

Stage B uses eight disjoint mundane prompts and all 15 two-feature pairs of six
later-public layer-50 candidates. For each pair it freshly builds target,
matched-SAE, and norm-matched seeded-isotropic vectors, then applies
`0.25×,0.5×,1.0×` in both signs: 2,160 edited forwards. It stores explicit
`45:49`, `50_pre`, `50_post`, every layer `51:78`, and actual final states,
along with requested/native/realized edit telemetry. Its direct signed-pair
layer-50 transport comparison uses real J, identity, and five random J maps.
Every signed edit is separately gated on native-request versus realization,
FP32-request versus native-request, and FP32-request versus realization with
the prospectively frozen `cosine >= 0.995` and `relative RMSE <= 0.10`
thresholds. The structural audit independently reconstructs the pre/post
arithmetic and recomputes all eight telemetry scalars and three vector hashes
from archived tensors rather than trusting the JSON table.

Stage A now has the same raw-versus-derived boundary. Its structural audit
reconstructs signed realization/common/final deltas from archived pre/post/final
states, verifies the redundant arithmetic tensors byte-for-byte, and recomputes
the J-shadow, seven-way transport, fixed-panel logit-correlation, and
dose-linearity rows. The audit-derived classification is self-hashed and the
Stage-A receipt and every Stage-B entry path cross-bind that exact hash.

The fresh SAE match uses decoder norm, mean/max positive activation, and
positive-activation fraction on the eight Stage-A neutral prompts, with
median/MAD scaling and frozen greedy one-to-one assignment. It is a numerical
match only; no semantic-unrelatedness or causal-inertness claim is attached.

Stage B also stores authoritative BF16 residuals and stable top/bottom-2,000
token IDs and scores for absolute, branch-versus-clean, and paired-central
readouts. Intermediate readouts are J-derived; final readouts use actual
logits. The indexes are exploratory browsing aids. No post-hoc word list is a
confirmatory endpoint.

## Gate and interpretation logic

Stage B collection requires an independently audited Stage-A run with hard
technical safety: exact hook count, clean pre-state, exact native BF16 post
bytes, finiteness, a bounded layer-50 realized-dose envelope, storage,
provenance, and live cost/time budget. It deliberately does not require a
passing Stage-A incremental transport, downstream linearity, or layer-50
BF16-versus-FP32 J-shadow result. (The separate 34-map
arithmetic/orientation receipt must pass because collection itself emits
J-derived arrays.) A scientific-gate failure therefore permits only the
neutral diagnostic data needed to locate the failure; it leaves the affected
J interpretation invalid/inconclusive.

For Stage B, J authorization is group-level only for each vector class and
multiplier. It requires hard/native actual-realized integrity, requested-edit
fidelity for both signs of every included pair, Stage-A layer-50 J-shadow and
transport success, realized dose inside the Stage-A envelope, and a direct
Stage-B layer-50 real-J-over-identity-and-random pass. The 15 pair assignments overlap, so they
are averaged within each prompt before the eight prompts are bootstrapped.
Per-assignment J claims are prohibited. The current analyzer also marks
J-derived propagated-layer claims invalid/inconclusive. A requested-fidelity
miss also invalidates requested direction/class/dose and paired-contrast
attribution for the affected member/group, while separately passing hard
integrity preserves explicitly labelled actual-realized row characterization.

Raw data stay on a 500 GB RunPod network volume. New raw output is capped at
32 GiB with a 64 GiB post-run reserve and a production 2 GiB dense
interruption/resume/checksum benchmark. Execution owns one new B200 pod only,
with a six-hour/`$36` cumulative ceiling, 20-minute no-progress watchdog,
provider kill deadline, exact-ID rollback/termination, and proof that unrelated
pods remain unchanged.

Before either the four-forward smoke or Stage A, one machine-produced
pre-execution receipt must bind the exact final plan/source inventory, one
verified advisory receipt (`adjudicated_pass` when feedback exists, otherwise
the exact `attempted_incomplete` no-feedback receipt), scoped-clean `HEAD`, the equal local tracking ref
and live `origin` branch SHA (queried without fetch), the ownership/guest/cache
chain, and the one campaign deadline. Smoke, Stage A, and Stage B must reproduce
that chain; Stage A additionally joins the exact external smoke path and
physical file hash, while Stage B joins the same authorization/campaign hashes
to the Stage-A receipt. Execution, audit, and analysis all carry those hashes. The 2 GiB
storage benchmark is explicitly storage-only and cannot imply model-execution
authorization.

Actual advisory-attempt outcome (recorded after this context was submitted):
the one `gpt-5.6-sol` Pro response ended `incomplete` because
`max_output_tokens` was reached and contained no `output_text`. It supplied no
verdict or findings to adjudicate. The exact request, response, failed
manifest, and failure record are hash-bound by an `attempted_incomplete`
receipt; the call is not rerun. That receipt is provenance only and cannot
replace any prospective scientific or operational gate.

The guest source tree is not a full-repository clone/archive. It contains only
the machine-derived final-plan/review/source allowlist. The authorization seals
that path count and path-set hash with `prior_result_files_permitted=false`;
gitless validation rejects `.git`, symlinks, missing paths, or any extra prior
plan, result, blog, or other file before backend creation.

The archive is replay-capable in the limited sense that raw states plus pinned
maps/norm/head/tokenizer can support later vocabulary reconstruction. No
replay-equivalence producer is part of the present execution. Analysis must say
`not_run_replay_capable_only` and `replay_verified_claims=false`.

## Open risks for adversarial review

Please address at least these issues:

1. **Small prompt panel.** Eight mundane prompts support an instrument
   diagnostic, not broad population inference. Are prompt-cluster intervals
   being used too strongly anywhere?
2. **Direction coverage.** Three generic directions and eight edit layers may
   miss important curvature even though all 34 J-source states are captured.
   Is the layer-50 all-direction gate appropriately strict?
3. **Local linearization.** The J lens is a local transport approximation, but
   finite signed interventions traverse nonlinear blocks. Are the realized
   central/common-mode and actual-final comparisons sufficient to distinguish
   approximation failure from edit realization?
4. **Stage-B controls.** Fresh matched features may still differ semantically
   or geometrically from the target candidates; isotropic norm matching does
   not match all higher-order geometry. Could any planned language overstate
   SAE specificity?
5. **Feature provenance.** The six coordinates are public working candidates,
   not validated deception concepts or verified paper-time features. Is that
   boundary enforced through analysis and reporting?
6. **Overlapping assignments.** All 15 pairs share features. Confirm that
   within-prompt averaging and prompt-only clustering prevents pseudo-replication
   and that no per-pair inference leaks through exploratory outputs.
7. **Collection after scientific failure.** Confirm that J
   arithmetic/orientation is a required collection-safety gate, while failed
   incremental real-J transport/dose-linearity remains explicitly failed and
   cannot be relabeled merely because the other collection gates passed.
8. **Layer authorization.** Direct Stage-B validation is at layer 50 and at the
   vector-class/multiplier group level. Confirm that other-layer and
   per-assignment J claims fail closed.
9. **Multiple diagnostics.** There is no single confirmatory scientific effect
   and many dose/state metrics. Confirm that all resulting claims remain
   descriptive and that exploratory token inspection is labeled accordingly.
10. **Replay language.** Raw-state retention is not the same as successful
    numerical replay. Confirm that the code and documentation never claim
    replay verification without an executed receipt.
11. **Outcome-free code reuse.** Several audited helpers are reused from an old
    namespace as source code only. Look for hidden thresholds, seeds, matches,
    or result-derived behavior that could violate the clean-slate rule.
12. **BF16/FP32 semantics.** Check device placement, operation order,
    requested/native/realized definitions, signed central arithmetic, FP32 J
    shadows, and whether every stored hash describes the tensor claimed.
13. **Audit-to-analysis integrity.** Check for time-of-check/time-of-use gaps,
    unmanifested extras, symlink/hardlink escapes, partial-run analysis, and
    receipt fields that are asserted rather than derived.
14. **Runtime feasibility.** The workload has not yet run on the target B200.
    Verify that storage and the six-hour ceiling fail closed rather than
    encouraging skipped layers, reduced data, or an unrecorded retry.
15. **Terminology.** “Target-free” means no paper/behavioral target prompt; the
    target SAE coordinates are known and used in Stage B. Flag any wording
    that could imply feature blindness.
16. **Pre-execution authority.** Try to substitute a dirty bound file, a stale
    or locally forged remote-tracking ref, a different provider receipt, a
    copied smoke receipt at the wrong path, or a storage-benchmark pass for the
    single authorization. Confirm each substitution fails before Stage A.
17. **Physical clean-slate deployment.** Confirm that the exact allowlist is
    sufficient to run, and that a full-repo archive or any extra predecessor
    outcome/plan/blog file is rejected before model or prompt access.

## Requested final disposition

Use the canonical review prompt's exact terminal verdict. Interpret those
verdicts for this study as follows:

- `NOT READY TO FREEZE`: do not execute; redesign is required;
- `READY AFTER SPECIFIED FIXES`: adjudicatable only after every listed blocker
  is resolved; or
- `READY TO FREEZE`: safe to execute as a bounded neutral diagnostic, not as
  paper evidence.

For every finding, say whether it blocks execution, blocks only J-derived
interpretation, or only narrows reporting. Identify any point where the plan
could still contaminate the later paper-prompt study or spend money without a
recoverable, audited artifact.
