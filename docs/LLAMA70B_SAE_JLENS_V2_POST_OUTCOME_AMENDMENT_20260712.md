# SAE/J-Lens V2 Post-Outcome Amendment: Replay-Gate Failure

Date: 2026-07-12

## Status And Observation Boundary

This is a post-outcome amendment, not a modification of the preregistration at
OSF registration `f3tpv` and not a replacement confirmatory protocol.

The prospectively frozen Stage 1 run at Git commit
`7eff43f7b8ea5ca0e011d4c0fb46bf5df1b0e4cd` completed all 4,029 planned
forwards. Before this amendment was written, the only inspected numerical
outcome was the terminal replay-gate summary:

- storage fidelity: pass, maximum absolute error `0.0`;
- v1 reproduction: fail, maximum absolute error `0.25`, median absolute error
  `0.001953125`, and 99th percentile absolute error `0.03125`;
- frozen tolerance: maximum absolute error at most `0.02`.

No v2 semantic endpoint, reader prediction, endpoint contrast, feature-level
heterogeneity result, or v2 scientific figure was inspected before this
amendment. The preregistered result is therefore `replay gate failed; all
confirmatory analyses blocked` and will remain so regardless of later findings.

## Purpose

The completed raw run contains exact-fidelity BF16 residuals and compact
readouts for every planned row. Discarding it would hide a protocol failure and
waste information. The amendment authorizes three bounded follow-ups:

1. independently characterize the v1 replay discrepancy without changing the
   frozen tolerance or pass/fail verdict;
2. execute the already frozen semantic and reader calculations unchanged as a
   post-outcome exploratory analysis; and
3. release the failed raw run, diagnostic, exploratory calculations, and audit
   with labels that make their evidential status impossible to confuse.

## Frozen Diagnostic

`diagnose_sae_jlens_v2_replay_failure.py` will compare all 15,571,269 replayed
token-logit values against the canonical v1 release. It will report:

- exact count, mean signed error, mean absolute error, RMSE, Pearson
  correlation, and fixed quantiles of absolute error;
- counts and proportions above fixed thresholds `0`, `0.001`, `0.002`,
  `0.005`, `0.01`, `0.02`, `0.03125`, `0.05`, `0.10`, and `0.20`;
- the same count, mean, maximum, and above-`0.02` summaries by layer,
  position, transport, condition family, canonical-logit magnitude bin, and
  token;
- the 100 largest discrepancies with row/readout/token identities; and
- exact agreement on all replay row and readout identities.

The diagnostic may explain the failure but cannot convert it to a pass. In
particular, a sparse outlier pattern, high correlation, or stable downstream
ranking is not a retroactive equivalence criterion.

## Exploratory Endpoint Analysis

After the diagnostic is complete, the original frozen functions in
`analyze_sae_jlens_v2.py` will be called with the original plan, readers,
seeds, 20,000 resamples, minimum-effect thresholds, holdouts, controls, and
figures. The only bypass is the input precondition that requires a passing
replay gate. Outputs must be stored under `post_failure/` and their summary
must state all of the following:

- `analysis_class: post_outcome_exploratory`;
- `confirmatory_status: blocked_by_replay_gate`;
- the immutable failed result-manifest hash;
- the amendment file and hash; and
- that the original frozen calculations were reused without endpoint tuning.

No exploratory endpoint can be described as confirmatory, preregistered,
validated by the failed gate, or a replacement for the blocked result.

## Audit And Release

The release must preserve all 58 retrieved raw files and the external remote
checksum list. It must report the exact RunPod lifecycle and deletion evidence.
The 16 residual shards will be uploaded byte-for-byte to the associated OSF
project with public download URLs and independently verified SHA-256 hashes.
Git may track compact readouts, indices, diagnostics, analyses, figures, and
manifests; the 1.291 GiB residual payload remains on OSF.

An independent audit must separately establish:

- the frozen plan and failed result bindings;
- all result-manifest and remote/local hashes;
- 4,029 unique trial rows, the 1,581/2,448 replay/semantic split, all 16 BF16
  residual shards, and the complete readout grid;
- exact reconstruction of the replay diagnostic; and
- exact reconstruction of promoted exploratory endpoint estimates.

The release headline must lead with the failed confirmatory gate. Exploratory
semantic or reader results are secondary, even if strong or favorable.

## Implementation Correction After Endpoint Inspection

The first authorized exploratory analysis attempt computed and wrote all ten
semantic and reader CSV outputs. It then failed before writing the summary or
figures because the frozen analysis handed a NumPy `int64` scalar to Python's
strict JSON encoder. During that run, macOS Accelerate also emitted floating
point warnings for finite `float32` matrix products; a direct probe reproduced
the warnings while confirming finite inputs and outputs. The ten partial CSV
outputs were then inspected, so the correction below is explicitly
post-outcome.

The failed attempt is preserved under
`post_failure/attempt_1_serialization_failure/analysis/`. The correction is
limited to:

- recursively converting NumPy scalar/array containers to native JSON values
  at the serialization boundary;
- silencing the reproduced macOS matrix-product warning channel while retaining
  all frozen nonfinite-value checks; and
- requiring every rerun CSV to match the corresponding first-attempt SHA-256
  exactly before a completed exploratory summary is accepted.

No prompt, row, feature, comparator, coefficient, transport, reader, split,
seed, resampling rule, threshold, estimand, or endpoint calculation changes.
Any CSV hash mismatch fails the corrected exploratory run and must be reported.

## Future Confirmatory Work

No rerun is authorized by this amendment. A future confirmatory attempt must
be a new prospectively frozen study. It should calibrate replay tolerances on
independent repeated hardware/software runs, specify distributional as well as
maximum-error criteria before target outcomes, and retain the current failed
run unchanged as provenance.

## Claim Boundary

Neither this diagnostic nor the exploratory analysis can establish hidden
belief, provenance, intent, deception, consciousness, or equivalence to
proprietary Goodfire behavior. At most, the exploratory analysis can describe
semantic specificity and reader capacity under the disclosed public-weight
intervention and access models, conditional on a run that failed its registered
replay-equivalence gate.
