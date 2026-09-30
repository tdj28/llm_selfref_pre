# Bootstrap Amendment A1

Date: 2026-09-30, before any new 70B, teacher-forced, generated-report or
experimental judge outcome. Original public freeze:
`59d40b922116c26c537c5eb283a17c15b6cc7805`. Its plan remains unchanged at
`data/sae_assay_diagnostic/stage1_plan_20260929/PLAN.json`.

## Observed Failure

The first cheap qualification pod reached the pinned checkout but Ubuntu's
PEP 668 protection rejected system-wide pip installation. The qualification
module and model inference never started. Exit status was 1. The raw log and
verified termination receipt are preserved in
`data/sae_assay_diagnostic/bootstrap_failure_20260930/`.

Owned pod `sbo5v90lrebggz` was retrieved, hash-verified and deleted. DELETE
returned 204; direct GET returned 404 and the owned ID was absent from
inventory. Conservative compute/storage cost was $0.0300157487. Including the
prior Pro call, this diagnostic has used at most $0.8946257487 so far.

## Correction

Create an isolated venv with `--system-site-packages` so the pinned image's
PyTorch/CUDA is available without duplicating its large installation. Install
the same frozen dependency versions inside the venv and run qualification and
the experiment through that exact interpreter. Runtime version checks remain
mandatory. Do not override Ubuntu's system-package protection.

The controller carries the first pod's cost into the same $5 qualification
and $135 compute/storage allocations. No extra budget is granted. A fresh
cheap qualification must pass and be terminated before a main pod can start.

No model/SAE pin, prompt, seed, sample size, operator, outcome definition,
matching rule, gate, endpoint or analysis is changed. The new plan is a separate
artifact at `data/sae_assay_diagnostic/stage1_plan_20260930a/PLAN.json`, with
updated source hashes and this amendment. Do not overwrite the original plan
or describe the failed bootstrap as a successful CUDA qualification.
