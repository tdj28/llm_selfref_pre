# Signed dose scan v1: audited result

## Status

The frozen generic-direction signed dose scan is complete and independently
audited. The audit status is `pass`, and the recovery publication marker is
`complete_atomic_audit_only_recovery`.

The model run itself completed earlier under run ID
`signed-dose-a084caa-wl8obvtuq0ax8t-v2`. C9 did not rerun the model: it
recomputed and sealed the failed audit from the unchanged raw tree with zero
fresh model forwards.

## Scope

This is the prospectively frozen, target-blind mechanics scan:

- Llama 3.3 70B, intervention after block 50;
- eight neutral prompts and three fresh generic directions;
- every signed magnitude from 0.5% through 30% residual RMS in 0.5-point
  increments, plus one shared clean zero per prompt;
- 43,200 cell-resolved actual-state arc rows across post-edit block 50 through
  final block 79;
- 1,440 independently recomputed realization rows and 4,872 J/identity/random-J
  transport rows.

It used zero target SAE features and zero prompts from the consciousness paper.
It therefore supports intervention-mechanics claims only, not semantic,
consciousness, deception, or SAE-specific claims.

## Main result

The intervention was delivered cleanly from 2% upward, but the model's later
actual state was already strongly nonlinear over the frozen 2%/3%/4% local
linearity panel.

- All 24 prompt-direction curves failed the actual-final-state linearity rule.
  Their minimum cross-dose cosine ranged from 0.778 to 0.848 against a 0.95
  threshold, and maximum slope discrepancy ranged from 0.572 to 0.703 against
  a 0.15 threshold.
- The realized source edit passed the same linearity check in all 24 cells, and
  `J(realized edit)` also passed in all 24. The nonlinearity appears downstream
  in the model response, rather than being explained by requested-to-realized
  BF16 delivery or by the J projection itself.
- Median final-state RMS gain over the realized source was 1.82x at 2%, 1.66x
  at 3%, 1.60x at 4%, 1.55x at 8%, and 1.48x at 30%. These are descriptive
  census summaries, not population estimates.

This strengthens the descriptive finding that a residual intervention can be a
nonlinear perturbation even when its source edit and first-order J transport
are well behaved. It does **not** establish that SAE steering specifically is
nonlinear, because these directions were deliberately generic.

## Quantization floor and safety checks

- Requested-delivery fidelity failed in all 24 cells at 0.5% and 1%, and in
  18/24 cells at 1.5%.
- Every cell passed from 2% through 30%; the prospectively frozen anchor doses
  2%, 3%, 4%, and 8% all passed.
- There were zero hard-safety failures at every dose, zero J-shadow failures,
  and zero realization-gate failures.
- At 0.5%, median requested-versus-realized cosine was 0.961 and relative RMSE
  was 0.287. At 2%, they improved to 0.997 and 0.076; at 30%, to 0.99998 and
  0.0062.

The 0.5%-1.5% rows remain part of the complete curve, but should not be
described as faithful requested-dose interventions under the frozen delivery
criterion.

## J-lens result

The learned J was a strong descriptive readout and beat the fixed random-J
controls, but it did not establish added value over the identity transport
under the frozen composite rule.

- The absolute learned-J fixed-token correlation passed descriptively from
  layers 50 through 78.
- At the primary layer 50, fixed-token Pearson correlation was 0.344, but the
  learned-J-minus-identity estimate was only 0.011 (95% prompt-resampling
  stability interval lower bound -0.0015), below the frozen 0.02 threshold.
- No layer passed the full learned-J-added-value composite. The result must not
  be reported as evidence that the learned J outperforms the cheaper identity
  baseline.

## External raw and compact artifacts

The immutable raw tree remains on RunPod network volume `bv9gb9j32y` at:

`/workspace/consciousness_sae_signed_dose_scan/consciousness_sae_signed_dose_scan_v1/raw/signed-dose-a084caa-wl8obvtuq0ax8t-v2`

The full ledger contains 36 files and 2,229,298,967 bytes including
`RUN_COMPLETE.json`. Its file-inventory SHA-256 is
`9fc8c8ffe5f8d34f8ddba863c11fff7370ef3644c1fad0139f96e39a4c8fbfc0`.

The full 26.8 MB audited summary remains outside Git. Its SHA-256 is
`b490b101c112f774ae7bffc9c54294a70b91c874c4cee78eddaa7890446c08f6`,
bound by `PUBLICATION_COMPLETE.json`. The Git evidence package retains the
compact audit, publication marker, operational authority, and exact-pod
termination receipts.

## Recovery accounting

C9 used a blob-filtered sparse checkout, completed in 266.29 seconds, cost an
estimated $0.4357, and deleted exact-owned pod `brmaewbpaf8jp2` with the account
pod inventory returning to zero. The complete C5-C9 corrective sequence cost an
estimated $6.8415. Most of that was avoidable full-clone and pre-audit ceremony;
the experiment-integrity skill has been amended to require physical sparse
closure and to use proportional Tier A/B/C recovery plus a progress deadline
buffer.

## What remains

This scan supplies mechanics and safe-interpretation evidence for a separate
semantic/SAE experiment. The requested before/after study using the paper's
prompts, actual SAE directions, and consciousness/deception readouts is not yet
executed by this target-blind scan and requires its own prospective design.
