# SAE Assay Diagnostic

Prototype components for the [Stage 1 plan](../../docs/SAE_STEERING_ASSAY_PLAN_20260929.md).
**Not an executable freeze. No real-model results exist for this diagnostic.**
The [Pro adjudication](../../docs/SAE_ASSAY_PRO_ADJUDICATION_20260929.md) supersedes
the draft's inventory and control arms; the prototype judge still needs its
370-response assumption removed before use.
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

Before launch, the parent workflow still needs the result-free machine plan,
matching and analysis, pinned environment, cost/lifecycle controller, positive-
control and failure rules, public freeze, GPU qualification and first-batch
audit. Re-encoded selected/full discrepancies and candidate-to-panel encoding
shapes require an explicit calibration policy. Do not improvise these at run
time or interpret a prototype test pass as a 70B manipulation pass.

CPU tests use `tests/test_sae_assay_{backend,fixtures,judge}.py`. Transformers
4.47.1 is required for the randomly initialized tiny Llama tests; no downloaded
weights or API calls are used. The review packet records the exact executed
command, results and source hashes. All experimental artifacts must use a new
namespace; historical releases remain unchanged.
