# SAE Assay Diagnostic

Implementation of the [revised Stage 1 protocol](../../docs/SAE_ASSAY_STAGE1_PROTOCOL_20260929.md).
The original reviewed draft and authentic Pro receipt are preserved separately.
The machine plan binds all executable sources before GPU outcomes; completion
of implementation is not a claim that a real-model gate has passed.
The owner approved $200 total and required GPT Pro review before experimental
spending. Stage 2 is not authorized.

- `backend.py`: pinned Llama/SAE loader, teacher forcing, cached generation,
  activation-dependent edits and per-position delivery telemetry. The model
  and SAE encode in BF16; residual product/addition use FP32 followed by one
  native cast. This is a disclosed extension, not proprietary API equivalence.
- `fixtures.py`: fixed synthetic calibration/validation texts, twelve judge
  fixtures, and candidate JSON-control feature 7688. Shared text frames mean
  no template-family holdout. Labels do not guarantee controllability, and
  the format scorer does not validate factual correctness or coherence.
- `judge.py`: masked Astra/Opus requests with $45/$15 reservations, durable
  receipts, fixture gates and interruption-safe resume. It refuses unbound
  plans; it is not authorization to dispatch.

- `protocol.py`: result-free inventories and source/commit binding.
- `runner.py`: target-first execution, exact replay, immutable raw rows,
  calibration-only dose selection, conditional branches and audit barriers.
- `analysis.py` / `report.py`: separate delivery/failure gates and descriptive
  baseline estimates, with missingness preserved.
- `matching.py`: outcome-masked optional comparator matching and qualification.
- `budget.py` / `controller.py`: append-only receipts, hard spending limits,
  owned-pod lifecycle, verified retrieval and termination. The controller never
  automatically approves a scientific audit barrier.
- `qualify.py` / `validate.py`: known-answer tiny-model checks and independently
  implemented structural validation. Tiny checks do not qualify 70B semantics.

Order: free tests and public freeze, cheap CUDA qualification, fixed real-model
qualification, target delivery, core baseline, eligible formatting, optional
comparators/baselines, then retrieval and release. No Stage 2 auto-launch.

CPU tests use `tests/test_sae_assay_*.py`. Transformers
4.47.1 is required for the randomly initialized tiny Llama tests; no downloaded
weights or API calls are used. The review packet records the exact executed
command, results and source hashes. All experimental artifacts must use a new
namespace; historical releases remain unchanged.
