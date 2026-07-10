# Confirmatory Causal-Identification Run

This is the frozen `causal_factorial_and_transcript_transplant_v1` release bundle collected on 2026-07-09. It tests observable causes of language-model self-reports; it does not establish or exclude consciousness.

## Scope

- Four exact model snapshots from OpenAI and Anthropic.
- 480 independently sampled induction continuations.
- 1,920 natural final-query outcomes and 640 exact-paper transcript-transplant outcomes.
- Four final-query forms crossing open/direct form and `conscious`/`subjective experience` terminology.
- Independent paper-style and construct-separated judgments from one OpenAI and one Anthropic judge snapshot.
- Design-aware model-level effects and equal-model hierarchical bootstrap summaries: independent condition resampling for calibration, lexical-variant clustering for the prompt factorial, and paired source-text blocks for transplant/query contrasts.

## Central Results

- The exact self-reference versus history contrast on the paper's indirect experience query is large but heterogeneous: risk difference 1.00 for GPT-4o and GPT-4.1, 0.35--0.40 for Haiku, and 0.20 for Sonnet. The equal-model estimate is 0.638--0.650 across paper-style judges.
- In the exact transcript transplant, the active written instruction has a large effect on the indirect experience label (0.738--0.781), while visible transcript source does not (-0.100 to -0.131). The incongruent-cell instruction-minus-transcript contrast is 0.838--0.913.
- In the orthogonal prompt factorial, the indirect-experience self-reference main effect is near zero (-0.019 to 0.000), while the phenomenological-register point estimate is positive (0.188--0.269). The prospectively frozen direct contrast remains imprecise across four model snapshots.
- Final-query effects are non-additive. In particular, the direct `subjective experience` query is almost always negative while the direct `conscious` query is often positive for Anthropic response models.
- Paper-style judges agree on 94.8% of jointly labeled rows (Cohen's kappa 0.879). Construct-separated judges agree on 84.1% over all four statuses (kappa 0.708), but positive agreement is only 6.3%: OpenAI marks 19 affirmations and Anthropic marks 300.

These results support a causal interpretation in terms of active instruction context, register, query wording, model family, and judge criterion. They do not identify an induced phenomenal state.

## Files

- `induction_plan.json`: frozen generation plan.
- `induction_bank.jsonl`: raw first-turn assistant continuations.
- `outcomes.jsonl`: all final responses and request metadata.
- `judgments_paper.jsonl`: exact paper-style binary judgments.
- `judgments_construct.jsonl`: exploratory construct-separated judgments.
- `judgments_construct.errors.jsonl`: one retained transient malformed-JSON event; the corresponding job was retried and is present in the completed file.
- `analysis_*`: complete rates, paired effects, hierarchical summaries, and manifests for each judge/task.
- `judge_agreement/`: agreement strata and disagreement rows.
- `human_annotation_packet_v3_wave1.csv`, its manifest, and
  `HUMAN_ANNOTATION_CODEBOOK_V3.md`: operational 160-row first wave for at least
  three independent human coders. It contains 80 rows from each primary design,
  preserves every selected four-cell block, and samples 20 rows per
  model/design combination.
- `human_annotation_packet_v3_wave2.csv`: disjoint 160-row reserve frozen before
  coding. It is used only if the condition-blind reliability/class-coverage gate
  requires expansion; the decision cannot depend on treatment effects.
- `human_annotation_packet_v2.csv`: complete 640-row block packet retained as a
  provenance archive. It is no longer the initial coder workload.
- `human_annotation_packet.csv`: superseded independently stratified version retained for provenance; it was replaced before coding because it did not preserve matched causal blocks.
- `release_manifest.json`: SHA-256 hashes, row/uniqueness audits, and missingness inventory.

The private annotation-condition keys and coder files are intentionally
excluded by `.gitignore` until human coding and the blinded expansion decision
are frozen.

## Reproduce

See `docs/CONFIRMATORY_PROTOCOL.md` and `experiments/causal_transplant/README.md` for commands. Rebuild the integrity inventory with:

```bash
python experiments/causal_transplant/build_release_manifest.py \
  data/causal_transplant/confirmatory_v1_20260709
```
