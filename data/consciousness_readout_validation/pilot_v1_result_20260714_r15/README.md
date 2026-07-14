# r15 validation-pilot compact result

This directory is the compact, Git-safe proof bundle for the authoritative
`consciousness_readout_validation_v1` r15 pilot executed on 2026-07-14. It does
not contain model weights, residuals, activations, logits, JSONL measurement
rows, hook tensors, or any other raw scientific payload.

## Outcome

- Overall frozen status: `fail`
- Passed: G1 arithmetic/orientation, G3 clean semantic readout, G3P clean
  factual polarity, and G4 pilot-specific vector/hook safety
- Failed: G2 neutral J-transport validation and the reported
  G2b identity-incremental requirement
- G2 detail: every residual/logit transport test in bands 45–49, 50–59,
  60–69, and 70–78 passed its absolute and best-of-five-random thresholds.
  The linearity guard failed 120 of 128 metric checks. The logit-space
  real-J-minus-identity lower bound passed (`0.036994 > 0.02`), while the
  residual-space lower bound missed (`0.016821 < 0.02`).

This is a valid scientific failure under the prospectively frozen pilot, not a
technical failure. It blocks the planned causal/differential J-transport claim
and does not authorize target execution under this study ID. The G3 claim
boundary remains only
`distinguishes_frozen_clean_explicit_consciousness_contexts_only`; it is not a
claim about consciousness, an SAE intervention effect, or the target paper.

## Identity and hashes

- Plan manifest: `60810f8a1b8716790eb277c24dbdfcb65335598ada792dd66b28764a734fc774`
- Execution-binding canonical hash: `2caa2a2337b9351129ed4248bfe26ec4f24d46ad0e10fceced18cd6e545ddc38`
- Structural-audit receipt: `f9b0df1183b998b38e94112a5a94089aa0ff60abcd732e6f415ae1f46e950766`
- Analysis result: `105c4e2bbad87aa083ad8d72b35762292eac6ed789d69abf2d63571537a57f77`
- Termination receipt: `3edc6be5217244279ae515d25d6cf25231c495d10638da7ae440937bfbf59799`
- Authoritative run prefix: `pilot-r15-bdb17a746499c04a66ecdc7f`

`SHA256SUMS` binds every compact file retained here. The authoritative JSON
producers also embed and validate their own canonical hashes.

## External raw storage

- Retained RunPod network volume: `qf2lwehl89`
- Study root on that volume:
  `/workspace/consciousness_readout_validation/consciousness_readout_validation_v1`
- Paid pod: deleted with HTTP 204, then verified by direct HTTP 404 and absence
  from strict account inventory
- Final conservative compute estimate: `$23.79454990298611`

The r12 runtime failure and the r13/r14 structural-auditor failures remain
separate forensic runs on the same volume. None was mixed into or analyzed as
part of r15.
