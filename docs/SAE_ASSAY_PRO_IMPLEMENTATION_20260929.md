# Selected Implementation Evidence

This packet contains selected prototype code, not the complete implementation.
The small tensor tests below have run locally. A cheap-GPU qualification,
the real 70B/SAE test, and end-to-end orchestration have **not** run. Passing
these fixtures must not be presented as evidence that a real target edit works.

## Intervention And Re-Encoding

From `experiments/sae_assay_diagnostic/backend.py`, `edit_hidden`:

```python
before = F.relu(F.linear(hidden, encoder_weight, encoder_bias))
before32 = before.float()
delta = torch.zeros_like(before32)
if mode == "amplification":
    quantiles = torch.as_tensor(q90, dtype=torch.float32, device=hidden.device)
    delta = strength * (quantiles - before32).clamp_min(0)
elif mode == "suppression":
    delta = -strength * before32
delta = torch.where(mask.unsqueeze(-1), delta, 0.0)
old_tf32 = torch.backends.cuda.matmul.allow_tf32
try:
    torch.backends.cuda.matmul.allow_tf32 = False
    requested = F.linear(delta, decoder_weight.float())
finally:
    torch.backends.cuda.matmul.allow_tf32 = old_tf32
zero = not bool(torch.count_nonzero(delta))
if zero:
    edited, after = hidden, before
else:
    edited = torch.where(mask.unsqueeze(-1),
                         (hidden.float() + requested).to(hidden.dtype), hidden)
    after = F.relu(F.linear(edited, encoder_weight, encoder_bias))
realized = edited.float() - hidden.float()
```

Assertions omitted from this excerpt check finite inputs/outputs, shape/dtype/
device agreement, valid mode/strength and quantile dimensions. A separate
full-dictionary path computes reconstruction/L0/non-target changes and reports
selected-versus-full encoder discrepancies. It does not assume the paths are
bitwise identical. The SAE is ReLU with an encoder bias and affine decoder;
there is no decoder-bias subtraction before encoding.

Cosine and relative error compare the requested residual vector with the
actually delivered BF16 edit. A nonzero request lost to rounding is counted
with cosine 0 and relative error 1, not dropped. Zero requests have cosine 1
by convention, but are excluded from the nonzero-request delivery denominator
and retained as explicit availability/identity observations.

The layer hook returns the original layer output object when no edit is
requested. Otherwise it replaces only the hidden-state component and preserves
the rest of a tuple output. It records absolute token position, prompt versus
generated origin, special-token status and a terminal-observation-only flag.
The production hook is `model.layers.50` after the block output.

## Executed Local Known-Answer Checks

Parent execution with `/private/tmp/conscious-review-ci312/bin/python`, torch
on CPU, exited 0 and reported:

```text
PASS: exact zero object identity, known-answer suppression/re-encoding,
retained BF16 rounded-away request
```

The cases were:

- Identity encoder/decoder, zero bias, hidden `[2, 1]`: the zero path returns
  the identical tensor object.
- Same dictionary, suppression strength 0.5: edited hidden and re-encoded
  activations equal `[1, 0.5]` exactly; relative delivery error is zero.
- BF16 hidden `[1024]`, zero encoder weight, encoder bias approximately
  0.002, decoder weight 1, suppression 0.5: the requested residual edit is
  nonzero but rounds away. Identity remains true; cosine is 0 and relative
  error is 1. The failed delivery remains visible in telemetry.

These distinguish known-answer arithmetic from a mere finite-output test.
They do not cover all SAE geometry, cache behavior, CUDA kernels, or semantics.
No synthetic result is being passed off as a real model outcome.

Additional parent executions before the consult:

```text
pytest -q tests/test_sae_assay_fixtures.py tests/test_sae_assay_judge.py
60 passed in 1.29s

pytest -q tests/test_sae_assay_backend.py
18 passed, 16 skipped in 0.55s
```

The initial 16 skips were the tiny Transformers Llama cases because that
temporary environment lacked `transformers`. They were **not passes**.
After adding Transformers 4.47.1 through `/private/tmp/sae-assay-deps`, the
parent reran all three files using the actual tiny Llama architecture:

```text
env PYTHONPATH=/private/tmp/sae-assay-deps:. \
  /private/tmp/conscious-review-ci312/bin/python -m pytest -q \
  tests/test_sae_assay_backend.py tests/test_sae_assay_fixtures.py \
  tests/test_sae_assay_judge.py
95 passed, 1 warning in 4.27s
```

No skips remained. The warning is an unrelated SciPy/NumPy version warning
on import; no SciPy calculation is part of these backend tests. The test
environment is not the final GPU environment lock. Tiny-model tests cover
cached/full-prefix agreement, zero versus unhooked generation, RNG isolation,
cap/EOS handling, terminal observations, telemetry alignment and hook cleanup.
The tensor tests cover FP32/BF16 known answers, masking, cross-feature
effects, clipping, rounded-away requests, invalid inputs and artifact hashes.
Fixture tests check inventory, scorer edge cases, exact schema reductions and
public label provenance. Judge tests use mocked clients to exercise cost caps,
masked requests, interruption/resume, corrupt receipts and failed fixture
gates. No test in this receipt made a paid API call.

Prototype source SHA-256 at this parent preflight:

| File | SHA-256 |
|---|---|
| backend.py | `7167bdf9dd24ab1abf32683a6af1c05be8659da5b67ded8096fceeb8f4723382` |
| fixtures.py | `f32faf3bc524d5116ad9b9d47a2f2d6054f8311f456f644ee0abeb5e99a0b733` |
| judge.py | `306f4548e676bd93431860282da95418a09ba15bc4175c4cdb4685d945ec0b59` |

These bind the tested prototypes, not a final executable experiment freeze.

## Paid-Judge Dispatch Boundaries

From `experiments/sae_assay_diagnostic/judge.py`, before dispatch:

```python
for name, path in self.sources.items():
    if sha(path) != self.plan["source_hashes"][name]:
        self.stop.set()
        raise ValueError("Frozen source changed before dispatch")
request = make_request(provider, item, self.plan)
reserve = reservation(provider, request)
self.check_budget(provider, reserve)
row = self.append("requests", {
    "judgment_id": jid, "attempt_id": jid + ":0", "phase": phase,
    "provider": provider, "model": MODELS[provider], "id": item["id"],
    "item": item, "item_sha256": digest(item), "request": request,
    "request_sha256": digest(request), "reservation_usd": str(reserve),
})
self.requests[jid] = row
```

`append` writes a plan/commit-bound hash-chain entry, flushes and fsyncs it,
and reads it back before returning. Startup checks the frozen source bytes,
plan membership and input attestations. Unknown in-flight requests are not
silently retried. Returned usage, model ID, schema and exact response quotes
are checked before reducing to explicit/inclusive labels. Requests contain
query and response text but no feature/condition/dose metadata. This code is
a new client around an existing frozen rubric, not a new outcome-selected
rubric. The final launch still needs an integration test with the machine plan.

## What Is Not Yet Established

- No real-model baseline, feature exposure, edit efficacy, positive-control
  behavior, throughput or memory preflight has passed.
- The integration driver, fresh-panel matcher, gate analysis and lifecycle
  controller must be implemented, tested and frozen after review adjudication.
- An existing 0.02 absolute selected/full tolerance in the prototype is only
  a proposed numeric threshold, not empirically validated or imported authority
  from a different historical replay test. Its effect on calibration, matching
  and runtime feature decisions needs an explicit policy before launch.
- The renderer/tokenizer, model precision and intervention arithmetic must
  be recorded exactly; labels such as "BF16 run" alone are insufficient.
- Review sign-off does not replace local independent reconstruction of the
  first generated rows and their telemetry before bulk execution.
