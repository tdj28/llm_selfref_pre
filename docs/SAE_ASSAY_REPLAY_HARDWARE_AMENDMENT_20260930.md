# Hardware Availability Amendment

Before any new SAE output or pod creation, the individual RunPod A6000 quote
failed availability. The broad catalog misleadingly showed LOW while the
individual device endpoint consistently returned NONE. No paid launch was
attempted under freeze `077ce9d50d97cf8d94d90f6d0640baaeb9cffcbc`.

The individually quoted A40 is available at $0.49/hour, with the same 48 GB
memory and native BF16 capability. This amendment changes only the fixed GPU
from RTX A6000 to A40 and lowers the price ceiling from $0.53 to $0.49/hour.
The two-hour timer, $0.10/hour storage reserve and $4 sub-cap stay unchanged;
the conservative two-hour timer bound is now $1.18. No fallback is automatic.

All 544 inputs, six coordinates, operator, dose, norm cap, encoder path,
component thresholds, zero/first-five checks, analysis, retrieval and deletion
rules are unchanged. The GPU/image metadata and historical native differences
remain mandatory. No result or activation informed this amendment.

The original protocol and `plan_20260930/PLAN.json` remain untouched. Their
runtime remains available at the original freeze. The revised executable plan
is `data/sae_assay_replay/plan_20260930a/PLAN.json`, pushed before execution.
Its changed source hashes identify the narrow resource amendment, not a
replacement of any historical outcome.
