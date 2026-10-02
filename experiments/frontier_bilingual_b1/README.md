# Frontier B1

Narrow budget-dependency successor to the frozen frontier mini. The original
source, plan and tests are preserved. This package does not expand the $60
frontier allowance or change its science.

- `providers.py` and `ledger.py` re-export unchanged mini implementations.
- `analysis.py` is an unchanged mechanical copy with B1-local relative imports.
- `protocol.py` and `runner.py` are copied from freeze `5398dc657b6a`, with B1
  dependency/runtime bindings and a source closure covering old and new code.
- `qualification.py` captures the new B1 proof over the exact old A1 fixture
  prefix. The historical $120 forecast failure remains preserved. No fixtures
  are repeated or charged to frontier.
- `tests/test_frontier_budget_b1.py` retains the original 31 cases under B1
  imports, then checks exact scientific equivalence and real local B1 fixture
  proof/capture/replay, tamper rejection, and independent accounting.

Parent/operator sequence: finalize B1 sources, create the real B1 plan, compile
the new frontier plan, freeze/push/check CI, import A1 journals into the parent
B1 ledger, create its B1 proof, then capture the frontier snapshot **before**
Llama target judging appends. The standalone capture command is offline and
does not create `events.jsonl` or construct an API client. Later frontier
execution/resume uses the saved snapshot, not the live B1 ledger.

```bash
python -m experiments.frontier_bilingual_b1.qualification \
  --plan data/frontier_bilingual_b1/plan_20261002/PLAN.json --freeze "$FREEZE" \
  --fixture-gate out/bilingual-llama-b1-20261002/fixture-gate.json
```

The runtime root is `out/frontier-bilingual-b1-20261002`; the plan destination
is `data/frontier_bilingual_b1/plan_20261002/PLAN.json`. No real plan is created
by this implementation task. The tests can use an ephemeral parent-plan
placeholder until the canonical plan is ready.

Full commands, amendment disclosure and unchanged claim boundaries:
`docs/FRONTIER_BILINGUAL_B1_PROTOCOL_20261002.md`.
