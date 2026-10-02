# Frontier bilingual mini-comparison

This package is offline by default. It implements 72 source generations,
144 crossed final answers, and up to 576 judgments under one separate $60 cap.
It creates no pods. It does not contain experimental results.

The exact prompts come from the Llama pilot. Astra and Opus use medium reasoning
and a 4,096 **total** output-token cap; GPT-4.1 uses temperature 0.5 and 768 tokens.
Reasoning consumes output budget. All visible text is retained, including capped
text, so this is not a matched-visible-length or matched-entropy comparison.

## Integration

- Parent creates the A1 plan first. Mini compilation binds its hash and sources.
- Both plans must be pushed in the same freeze and pass public CI.
- First execution requires the fresh passing A1 fixture/forecast proof.
- The proof and its immutable receipt prefixes are snapshotted. Later A1 target
  judging does not invalidate mini resumes.
- A1 `make_request` / `parse_label` are reused. Its spending ledger is not.
- Generation and judging share the mini journal, reservations, stop-loss and cap.
- No retry of uncertain, failed, empty, capped or semantically unwanted output.

## Commands

From the repository root (substitute the actual 40-character freeze SHA):

```bash
python -m pytest tests/test_frontier_mini.py -q

python -m experiments.frontier_bilingual_mini.protocol \
  --a1-plan data/bilingual_llama_a1/plan_20261002/PLAN.json \
  --write data/frontier_bilingual_mini/plan_20261002/PLAN.json

python -m experiments.frontier_bilingual_mini.protocol \
  --check data/frontier_bilingual_mini/plan_20261002/PLAN.json --freeze "$FREEZE"

# Offline inspection; does not create clients or dispatch calls.
python -m experiments.frontier_bilingual_mini.runner \
  --plan data/frontier_bilingual_mini/plan_20261002/PLAN.json --freeze "$FREEZE"

# Authorized first balanced block only, then the same command without
# --through-block 1 to finish after the fixed technical/cost gate passes.
python -m experiments.frontier_bilingual_mini.runner \
  --plan data/frontier_bilingual_mini/plan_20261002/PLAN.json --freeze "$FREEZE" \
  --execute --approved-cap-usd 60 --approval-ref "$APPROVAL_REF" \
  --fixture-gate "$A1_GATE" --env-file "$LOCAL_ENV_FILE" --through-block 1

python -m experiments.frontier_bilingual_mini.analysis \
  --plan data/frontier_bilingual_mini/plan_20261002/PLAN.json --freeze "$FREEZE" \
  --run-root out/frontier-bilingual-mini-20261002 \
  --out out/frontier-bilingual-mini-analysis-20261002
```

No API call starts on a failed technical gate, failed forecast, unknown request,
missing usage, judge parse failure, or returned-model mismatch. Model snapshots
must remain stable within this run. Partial receipts remain available; do not
erase the ledger to retry. `--allow-partial` enables an explicitly incomplete
analysis, preserving all 144 planned slots and missingness. Use `--no-plots` for
tables only. Analysis output must be a fresh directory outside the raw run.

Outputs: per-answer CSV, per-judge rates, block-paired instruction/transcript
contrasts, Chinese-minus-English effect contrasts, cap sensitivity, JSON audit,
and separate-provider PNG/PDF heatmaps. No model-ranking or consensus-truth score
is generated. See `docs/FRONTIER_BILINGUAL_MINI_PROTOCOL_20261002.md` for exact
estimands, limitations, stop-loss and accounting rules.
