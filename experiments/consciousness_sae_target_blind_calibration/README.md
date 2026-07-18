# Pre-SAE generic-vector delivery/J-readout calibration v2

This target-blind study is a separate adaptive follow-up to
realization-validation v1. It uses eight new mundane prompts, three newly
seeded generic directions, layer-50 injection, and signed 1/2/3/4/8%
residual-RMS doses. It is deliberately *before* any SAE intervention: no SAE
feature is selected or injected, so it cannot make an SAE-steering or semantic
claim. The 1% dose is diagnostic; 2/3/4/8% gate edit realization, and 2/3/4%
test local linearity around 3%.
The runtime, 2,048-token panel, five random-J controls, and 68 J-orientation
fixtures are also freshly seeded under the v2 study identity; no predecessor
control realization is reused. The token panel is restricted to IDs 0–127,999;
the Llama 3 reserved/special range is excluded.

The predecessor compact receipts are disclosed design provenance only. No
predecessor raw row, target feature, paper prompt, semantic lexicon, or target
outcome is an input. Raw tensors are written to the separate RunPod namespace
`consciousness_sae_target_blind_calibration/consciousness_sae_target_blind_calibration_v2/raw`
and never committed.

Actual-state collection requires a complete audited transaction plus hard
native delivery, signed requested-to-realized fidelity, and common-mode control
at the gated doses. Source/J/downstream linearity gates only corresponding
linear-response claims. Current-study orientation and BF16-versus-FP32 shadow
fidelity gate only J-derived claims; J predictive association and J-over-
identity added value remain still-separate claim tiers. A nonlinear downstream
model response is a measured outcome, not a technical delivery failure.

Layer 50 is the sole primary J readout. Its result is a descriptive estimand on
the exact frozen eight-prompt × three-direction panel; prompt resampling yields
a fixed-panel stability interval, not a population confidence interval. Layers
51–78 are a descriptive trajectory only and cannot pass, fail, replace, or
rescue the primary layer. The exact inventory is 8 prefix + 8 clean
continuation + 240 edited continuation forwards = 256 model forwards.

The B200 guest must run
`bash experiments/consciousness_sae_target_blind_calibration/setup_runpod_guest.sh`
from the repository root to install and verify the frozen dependency set. The
runner must then be entered through
`python3 -B -m experiments.consciousness_sae_target_blind_calibration.guest_launcher`;
the complete forwarded-argument template is frozen in the protocol document.
No GPU execution is authorized until the complete plan/source closure is
committed and pushed and a final receipt proves clean local `HEAD` equals the
live remote commit while binding provider/cache/review receipts. The 90-minute,
$9 campaign is partitioned into a hard 60-minute/$6 runner budget and a reserved
30-minute/$3 independent-audit budget inside the provider's six-hour, $36
authority window, using the conservative frozen accounting rate of $6/hour.

Expected raw output is approximately 320 MB (about 306 MiB), remains on the
network volume, and is independently audited by recomputing hashes and metrics
from archived tensors plus rehashed pinned J and required model norm/LM-head
weights. The audit constructs no full 70B model and performs no model forward.
The protocol contains the complete authorization, guest-runner, and B200 audit
command templates; the audit must finish before compact receipts are retrieved
and the receipt-owned pod is terminated.

The exact build, validation, create, guest/cache preflight, and receipt-owned
termination command lines are in
`docs/consciousness_sae_target_blind_calibration/PROTOCOL.md`. Their entry
points are, respectively:

```bash
PYTHONPATH=. python3 -B -m experiments.consciousness_sae_target_blind_calibration.build_plan --output-dir <fresh-plan-directory>
PYTHONPATH=. python3 -B -m experiments.consciousness_sae_target_blind_calibration.validate_plan --plan-dir <frozen-plan-directory> --output <fresh-plan-audit.json>
PYTHONPATH=. python3 -B -m experiments.consciousness_sae_realization_validation.runpod_orchestrator create --receipt-dir <fresh-external-provider-receipt-directory> --execute
PYTHONPATH=. python3 -B -m experiments.consciousness_sae_realization_validation.runpod_preflight all --ownership-receipt <ownership-receipt.json> --receipt-dir <fresh-external-preflight-receipt-directory>
PYTHONPATH=. python3 -B -m experiments.consciousness_sae_realization_validation.runpod_orchestrator terminate --receipt-dir <same-external-provider-receipt-directory> --pod-id <owned-pod-id> --execute
```
