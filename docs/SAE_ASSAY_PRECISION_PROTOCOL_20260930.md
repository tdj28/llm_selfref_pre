# Precision Transport Pilot, With A Precision-Only Sham

Status: unexecuted prospective engineering design. This is a **new mixed-
precision implementation**, not a repair to the historical data or a claim
that the original native BF16 operator passed. Freeze with the exposure plan
before either new screen or pilot outcome is generated.

## Why This Test

The 544-state native replay passes coordinate medians but only 65.8--67.4%
of requested vectors meet fidelity. An FP32 calculation followed immediately
by BF16 writeback is not a precision repair. Conversely, merely measuring an
FP32 shadow that never reaches the model cannot qualify actual delivery.

This pilot asks whether retaining higher-precision residuals actually delivers
the continuous edit through the downstream model, and how much a precision-
only sham changes the unsteered baseline. Both answers matter. It does not
generate, judge or claim to explain consciousness reports.

## Fixed Rows And Four Branches

Use the first (`-01`) text in each of the 12 authored discovery families from
the already prepared exposure corpus. All 12 are fixed before activation
screening; none is selected for high activity. Do not inspect validation
exposure to choose texts, coefficients or algorithms. Run each text under:

1. `native_zero`: original BF16 model, no residual promotion or edit.
2. `precision_sham`: promote layer-50 output to FP32, but add no SAE edit.
3. `suppression`: the same precision path plus the fixed active-support edit.
4. `amplification`: the same precision path plus the opposite signed edit.

After layer 50, keep residual additions in FP32. Cast normalized outputs to
BF16 before BF16 attention/MLP projections, and cast the final normalized
output to BF16 before the output head. These casts occur **after** RMSNorm's
weight multiplication, unlike the native intermediate BF16 rounding. This
rounding-order difference is part of the precision-only sham. Do not change
model weights. The native
branch must exactly reproduce the original unhooked output in qualification.
The pilot rejects active autocast and unsupported FP32 `medium` matmul mode
before loading the model. It records and preserves the caller's supported
`highest` or `high` matmul setting across every model forward. The SAE readout
and request calculation separately disable TF32 in scoped contexts, then
restore that setting. No helper may silently change native-zero arithmetic.
The precision-only sham is **not** required or assumed to reproduce it: its
changes are a measured implementation effect and must be retained.

The edit uses the previously specified active-support projection, requesting
0.25 or 1.75 times native clean activation and capping the continuous request
at 4% of clean norm. Do not redefine the request after writeback, add nullspace
noise, discard small requests or use the realized vector as the intended one.
Save the clean, continuous request and delivered post-edit tensors losslessly.
Requests at special-token positions are exactly zero. The precision-only
transport still applies to the entire tensor and is shared by the sham and
both signed branches. Coordinate geometry is computed from the pinned native
BF16 encoder rows promoted to FP64 for the small Gram solve, with FP32 request
formation. This arithmetic is recorded, not assumed bit-identical to old saved
Gram matrices.

## Measurement And Comparison

The unchanged fidelity component requires cosine >=0.95 and relative error
<=0.20 on at least 95% of nonzero nonspecial requests. The unchanged norm
component requires realized norm <=5% of clean norm on at least 95% of
nonzero realized edits. Report zero requests, all-inactive positions, actual
hook counts and dtypes, and every failed position.

The FP32 residual cannot enter a native BF16 encoder without being rounded
back. Therefore the new readout is explicitly the full-width token1 encoder
with the **native BF16 weights promoted to FP32**. Record both native BF16
clean activations and this readout on the identical clean state. Re-encode
edited FP32 states with the same promoted weights and report the baseline
shift. This is a new readout authority, not evidence that native BF16 encoder
decisions are unchanged. Retain per-feature all-active and exposure counts.

Teacher-forced NLL and paired KL on identical prefixes compare native-zero,
precision-sham and both signed edits. Report the precision-sham difference
separately from each edit-minus-sham difference. Do not compare independently
generated continuations, hide sham drift, claim semantic selectivity from a
coordinate change or treat tiny-model checks as 70B evidence.

This 12-family development pilot has no population-level significance claim.
It does not pass the six-feature 100-position/six-text exposure gate by design
or by averaging across features. A fidelity pass establishes delivery under
this mixed-precision operator only. A larger validation, downstream coherence,
behavioral positive control and adequate baseline headroom remain required.

## Runtime And Integrity

CPU tiny-real-Llama tests must establish actual downstream execution, expected
dtypes, exact native-zero behavior, hook removal on exceptions and unchanged
weights. Repeat exact-path synthetic checks on CUDA before live pilot work.
The existing clean exposure screen finishes first; the pilot then runs on the
same task-owned pod before its completion marker. Its own append-only receipts
and captures live in `precision_pilot/`, separate from clean exposure rows.

The shared exposure controller's two-hour timer, $25 sub-cap and cumulative
$200 limit include this pilot. Check remaining time before the first pilot
row. Preserve technical failures or incomplete runs; no automatic replacement,
tuning or extra pilot. Retrieve and hash all artifacts before deletion. The
full workflow remains blocked from target-report generation regardless of
whether these engineering components pass.
