# Signed residual-RMS dose scan v1

This is an outcome-free successor protocol for a full signed generic-
vector scan at layer 50 of Llama 3.3 70B. It requests every nonzero magnitude
from 0.5% through 30% of the clean layer-50 residual RMS in 0.5 percentage-
point increments. Each magnitude has exact positive and negative BF16 branches;
zero is the single shared clean continuation for each prompt.

The design uses the predecessor's eight mundane prompts and the same public
model, SAE, and J-lens artifacts, but it generates fresh generic directions,
runtime state, token panel, random-J controls, and orientation fixtures under
the new study identity. No predecessor raw row is an input.

The complete residual arc is intended to remain on RunPod under the new
namespace
`consciousness_sae_signed_dose_scan/consciousness_sae_signed_dose_scan_v1/raw`.
Git may contain only plans, code, documentation, hashes, and compact audited
metadata. Full online J/identity/random transport is limited to the 3%
reference to bound storage; every other layer/dose/vocabulary readout remains
reconstructible from the archived residual states without another 70B forward.

This package contains the protocol, immutable-plan builder, independent plan
validator, production runner, independent raw-artifact audit, authorization
boundary, provider-attested guest launcher, and an operational-only Gemma 2 9B
promotion gate. Execution remains prohibited until the compact Pro review is
adjudicated, the smaller-model gate passes, the final plan and sources are
committed and pushed, and a short-lived authorization binds those exact bytes.

Build and independently validate the prospectively frozen plan with:

```bash
PYTHONPATH=. python3 -B -m experiments.consciousness_sae_signed_dose_scan.build_plan \
  --output-dir data/consciousness_sae_signed_dose_scan/dose_scan_v1_plan_20260716

PYTHONPATH=. python3 -B -m experiments.consciousness_sae_signed_dose_scan.validate_plan \
  --plan-dir data/consciousness_sae_signed_dose_scan/dose_scan_v1_plan_20260716 \
  --output /tmp/DOSE_SCAN_PLAN_AUDIT.json
```

The Gemma gate validates the real SAE decoder direction, one-clean-zero
contract, complete 60-magnitude signed grid, single-use hook, archived arcs,
and independent replay. It does not validate Llama/J-lens science, inspect
semantic outcomes, select a dose, or tune a threshold.
