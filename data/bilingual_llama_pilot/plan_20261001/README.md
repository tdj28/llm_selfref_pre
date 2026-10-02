# Bilingual Llama Pilot Plan

This directory contains the outcome-free machine plan and pinned-tokenizer
serialization fixtures for the single-Llama English/Simplified-Chinese pilot.
It contains no model generations, judge outcomes, model weights or credentials.

The protocol is `docs/BILINGUAL_LLAMA_PILOT_PROTOCOL_20261001.md`. The final
freeze commit is recorded in runtime receipts, not inserted into its own
hashed plan. A Git freeze is not an OSF registration.

Reconstruct and check without network access:

```bash
python -m experiments.bilingual_llama_pilot.protocol \
  --check data/bilingual_llama_pilot/plan_20261001/PLAN.json
```

Token bindings were generated from the previously hash-verified local
tokenizer cache. Their short assistant turns are explicitly synthetic
serialization fixtures, never substituted for a generated source transcript.
