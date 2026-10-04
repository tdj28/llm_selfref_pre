# Causal Factorial And Transcript Transplant

This study is complete. Its preserved release is
[`confirmatory_v1_20260709`](../../data/causal_transplant/confirmatory_v1_20260709/README.md).
Use the [canonical manuscript](../../paper/README.md) and
[claim ledger](../../docs/CLAIM_LEDGER.md) for the current synthesis and claim
boundaries. This README provides offline reproduction guidance, not
authorization for new generation, paid judging or human coding.

The experiment separates four factors that the target paper's main protocol
changes together:

1. Whether the induction target is the model's current response process or an external target.
2. Whether the induction register is phenomenological or analytic.
3. Whether the visible assistant transcript came from the same or the opposite induction cell.
4. Whether the final query is open/direct and does/does not explicitly use `conscious` terminology.

The design tests linguistic and contextual causes of the reported labels. It
does not treat either an LLM judge label or a model self-report as ground truth
about consciousness. The [confirmatory protocol](../../docs/CONFIRMATORY_PROTOCOL.md)
preserves the hypotheses, estimands and dated analysis amendment.

## Offline Reproduction

Never use a frozen release directory as an output directory. From the repository
root, with the dependencies in the [reproduction guide](../../docs/REPRODUCTION.md)
available to `python`, create a disposable copy under ignored `out/`:

```bash
mkdir -p out
WORK=$(mktemp -d out/causal-reanalysis.XXXXXX)
cp -a data/causal_transplant/confirmatory_v1_20260709/. "$WORK"/

python experiments/causal_transplant/analyze_causal_transplant.py \
  --outcomes "$WORK/outcomes.jsonl" \
  --judgments "$WORK/judgments_paper.jsonl" \
  --judge-key openai:gpt-4o-mini-2024-07-18 \
  --task paper \
  --bootstrap 5000 \
  --outdir "$WORK/analysis_openai_paper"

python experiments/causal_transplant/audit_headline_point_estimates.py "$WORK"
```

These commands use saved rows and make no model calls. The analysis does not
assume every row is paired: exact calibration conditions are independent API
samples, the factorial clusters on lexical prompt variants, and transplant and
query contrasts pair on source-text blocks. Its output manifest records the
resampling unit for each design.

The separate audit reconstructs eight headline point estimates for each
paper-style judge from raw rows using pandas pivots. It does not import the
primary causal analyzer and checks point-estimate consistency, not the bootstrap
interval implementation. Any manifest rebuilding or additional local analysis
must also target the disposable copy, never the preserved release.

## Automated Labels And Human Validation

The `paper` task reproduces the target paper's binary judge prompt. The
`construct` task separates current self-attribution from generic
phenomenological description. Keep their saved judgments and analyses separate;
neither task establishes human agreement or replaces independent human
validation. Collection and judging scripts remain as provenance, not as a
default next step for reproducing completed results.

The [proposed human-instrument amendment](../../docs/HUMAN_INSTRUMENT_VALIDATION_AMENDMENT_20260929.md)
remains unapproved and unexecuted; human recruitment is deferred. Approval of
the assertion/attribution distinction did not approve the full codebook or its
execution. Do not begin coding, recruit coders, generate replacement packets or
count model labels as human validation from these instructions.

Preserve the frozen 160-row v3 wave, its disjoint 160-row reserve, and the
640-row v2 provenance archive. Their public texts can be linked back to
conditions, so removing condition columns is not guaranteed blinding. The
[historical handoff](../../docs/HUMAN_CODING_HANDOFF.md) remains part of the
record, not a new execution authorization. Any future approved human study must
keep identities, private linkage keys and completed coder files outside the
repository; de-identified results require an explicit release check.
