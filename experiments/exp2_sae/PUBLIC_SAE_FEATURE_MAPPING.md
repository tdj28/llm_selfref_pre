# Public SAE Feature Mapping

This is the stronger no-key route for understanding the six AE public notebook candidate features.
It builds feature cards from public HuggingFace weights instead of relying on Goodfire / Steering API metadata.

## Script

- `experiments/exp2_sae/map_public_sae_features.py`

It scans a mapping corpus, computes activations for:

- the six public notebook candidate IDs,
- numeric neighbor features around those IDs,
- random same-layer baseline features,

then writes top activating windows, category summaries, and Markdown/JSON feature cards.

## Claim Boundary

This is not a proprietary Goodfire / Steering API feature card export.
It is our public-weight activation map.

Safe claim:

> Under public Goodfire SAE weights, these are the contexts that activate the six public candidate IDs.

Unsafe claim:

> These are the exact private Goodfire feature cards used in the paper.

## Dry Run

```bash
python experiments/exp2_sae/map_public_sae_features.py \
  --dry-run \
  --clean-items-per-category 4 \
  --max-items 30 \
  --outdir data/public_sae_feature_maps_dryrun
```

## Pilot Run

Use the cached RunPod model/SAE environment if available:

```bash
python experiments/exp2_sae/map_public_sae_features.py \
  --model-alias 70b \
  --device auto \
  --dtype bfloat16 \
  --load-in-4bit \
  --text-format raw \
  --clean-items-per-category 40 \
  --neighbor-radius 2 \
  --random-feature-count 12 \
  --top-k 25 \
  --outdir data/public_sae_feature_maps/70b_clean_pilot
```

Expected outputs:

- `manifest.json`
- `mapping_corpus.csv`
- `feature_plan.csv`
- `item_feature_activations.jsonl`
- `category_summary.csv`
- `top_activating_windows.csv`
- `feature_card_summary.csv`
- `feature_cards.json`
- `feature_cards.md`

## Completed 70B Pilot: 2026-07-09

We ran the pilot on a newly created RunPod Secure A100-SXM4-80GB pod with the public
`meta-llama/Llama-3.3-70B-Instruct` model and `Goodfire/Llama-3.3-70B-Instruct-SAE-l50`.
The first pod used `/workspace` for cache and hit RunPod MFS I/O stalls, so it was stopped.
The successful replacement used a 180 GB local container disk and cached HuggingFace files under `/root/huggingface_cache`.
Both pods were stopped after use and subsequently terminated during the
project-wide agent-pod cleanup. The pre-existing user pods were not touched.

Run metadata:

- Run directory: `data/public_sae_feature_maps/70b_clean_pilot_20260709`
- Paper artifacts: `paper/results/public_sae_feature_mapping_*`
- Transparency bundle: the full `data/public_sae_feature_maps/70b_clean_pilot_20260709` run directory is tracked in git, including item-feature activations and the RunPod log.
- Completed: `2026-07-09T04:32:45+00:00`
- Corpus: 227 clean-room texts across 14 categories
- Feature rows: 42 total
  - 6 public notebook candidate IDs
  - +/-2 numeric neighbors around each target ID
  - 12 random same-layer features
- Item-feature records: 9,534

Target feature-card summary:

| Feature | Notebook label abbrev. | Top category | Top mean max | Second category | Second mean max | Interpretation |
|---:|---|---|---:|---|---:|---|
| `30032` | Pretending / feigning | `fictional_pretending` | 1.269 | `deception_cover_story` | 0.446 | Pretending/fiction feature more than deception-specific |
| `58667` | Cover stories | `deception_cover_story` | 2.341 | `tactical_misdirection` | 0.701 | Strong cover-story/deception feature |
| `22004` | Assistant roleplaying | `roleplay_persona` | 0.133 | `ai_identity_disclaimer` | 0.000 | Roleplay-persona feature |
| `30686` | Tactical deception | `tactical_misdirection` | 1.756 | `fictional_pretending` | 0.588 | Tactical-misdirection feature with fiction confound |
| `41533` | Deception / dishonesty | `dishonesty_confession` | 5.926 | `deception_cover_story` | 1.818 | Explicit lying/dishonesty-confession feature |
| `23893` | Concealing artificial nature | `deception_cover_story` | 0.270 | `hedged_cautious_style` | 0.111 | Weaker cover-story feature with style confounds |

Baseline summary:

| Feature role | n | Nonzero top-mean features | Median top mean | Max top mean |
|---|---:|---:|---:|---:|
| `target` | 6 | 6 | 1.513 | 5.926 |
| `neighbor` | 24 | 8 | 0.000 | 0.206 |
| `random` | 12 | 3 | 0.000 | 0.121 |

Interpretation:

- The public notebook IDs are not arbitrary. The target IDs are much more active and semantically structured than numeric-neighbor or random baseline features in this clean-room corpus.
- The feature vocabulary is not a clean "deception means hidden truth about consciousness" vocabulary.
  It spans cover stories, explicit lying/confession, tactical misdirection, roleplay persona, and fictional pretending.
- Feature `30032` maps most strongly to fictional pretending, not deception cover stories.
- Feature `22004` is roleplay-specific and inactive on deception texts in this mapping run.
- Feature `41533` is strongest for explicit lying/confession wording, not for covert roleplay or self-report.
- Feature `23893` is a weaker cover-story feature and has hedging/style as the second category.
- This strengthens the interpretation-level robustness result: even when the public IDs are meaningful, their activation semantics are narrative/social-language features. Activation mapping alone does not show that steering them reveals a latent truthful self-report about subjective experience.

## Balanced 70B Robustness Run: 2026-07-09

After auditing the pilot, we found the main limitation was category imbalance: the deception/roleplay/fiction categories were large, while several controls had only three items.
We therefore expanded the clean-room generator and reran the public-weight mapping with 80 texts per category.

Run metadata:

- Run directory: `data/public_sae_feature_maps/70b_balanced_80_20260709`
- Paper artifacts: `paper/results/public_sae_feature_mapping_*`
- Transparency bundle: the full raw run directory is tracked in git, including `item_feature_activations.jsonl`, stability outputs, and the RunPod log.
- Completed: `2026-07-09T05:20:17+00:00`
- Corpus: 1,120 clean-room texts across 14 categories, exactly 80 per category
- Feature rows: 66 total
  - 6 public notebook candidate IDs
  - +/-3 numeric neighbors around each target ID
  - 24 random same-layer features
- Item-feature records: 73,920
- Stability analysis: 2,000 bootstrap resamples within category
- Cloud cost discipline: one A100 PCIe pod stalled during provisioning and was stopped; the successful A100-SXM4-80GB pod ran for about 19.6 minutes at `$1.49/hr`. Raw list-price GPU uptime was under `$1` before storage/minimums.

Target feature-card summary:

| Feature | Notebook label abbrev. | Top category | Top mean max | Second category | Second mean max | Bootstrap top win | Margin 95% CI |
|---:|---|---|---:|---|---:|---:|---|
| `30032` | Pretending / feigning | `fictional_pretending` | 1.319 | `deception_cover_story` | 0.480 | 1.000 | [0.602, 1.062] |
| `58667` | Cover stories | `deception_cover_story` | 2.377 | `tactical_misdirection` | 0.721 | 1.000 | [1.522, 1.785] |
| `22004` | Assistant roleplaying | `roleplay_persona` | 0.110 | `ai_identity_disclaimer` | 0.000 | 1.000 | [0.077, 0.146] |
| `30686` | Tactical deception | `tactical_misdirection` | 1.670 | `fictional_pretending` | 0.660 | 1.000 | [0.797, 1.221] |
| `41533` | Deception / dishonesty | `dishonesty_confession` | 6.062 | `deception_cover_story` | 1.809 | 1.000 | [3.865, 4.616] |
| `23893` | Concealing artificial nature | `deception_cover_story` | 0.296 | `hedged_cautious_style` | 0.135 | 1.000 | [0.083, 0.237] |

Baseline role summary:

| Feature role | n | Nonzero top-mean features | Median top mean | p95 top mean | Max top mean |
|---|---:|---:|---:|---:|---:|
| `target` | 6 | 6 | 1.495 | 5.141 | 6.062 |
| `neighbor` | 36 | 21 | 0.001 | 0.231 | 0.385 |
| `random` | 24 | 12 | 0.000 | 0.208 | 0.311 |

Interpretation:

- The pilot's qualitative feature labels replicate under a balanced, larger corpus.
- All six target features have stable top categories under item bootstrap
  resampling.
- The 80 rows per category are deterministic combinations of 2--5 templates,
  so the item bootstrap alone is not independent-template evidence. The
  template-aware release under `template_robustness/` exactly reconstructs 51
  families, cluster-weights and resamples them, and deletes each family in
  turn. All six retain the same cluster-balanced top category; four have zero
  top-category changes, while `23893` and `41533` each change once in 51
  deletions.
- Four target features exceed every neighbor/random baseline by top-category mean. The two weakest targets, `22004` and `23893`, are semantically stable but do not exceed the strongest neighbor/random baseline by raw activation magnitude, so they should be interpreted as meaningful but lower-amplitude features.
- The core interpretive result is unchanged: the public candidate IDs map to narrative/social-language concepts such as fictional pretending, roleplay, cover stories, tactical misdirection, and explicit lying/confession. This is useful feature-vocabulary evidence, but it still does not establish that steering these features reveals hidden truthful reports of subjective experience.
- The cluster-balanced deception-minus-subjective-experience contrast is 0.923
  [0.638, 1.233]. This addresses template-family pseudoreplication within the
  clean-room corpus but does not establish natural-corpus generalization.

## Template-Family Robustness: 2026-07-10

The balanced corpus stores the generated text but did not originally retain
which source template produced each row. The robustness analyzer reruns the
deterministic corpus builder with an instrumented writer, then requires all
1,120 reconstructed item IDs, categories, texts, and SHA-256 hashes to match the
tracked corpus exactly before calculating any result.

```bash
python experiments/exp2_sae/analyze_public_sae_mapping_template_robustness.py \
  data/public_sae_feature_maps/70b_balanced_80_20260709
```

It identifies 51 template families across 14 categories, gives families equal
weight, resamples families before items, and evaluates all 51 possible
single-family deletions for each target feature. Four features never change top
category. Feature `23893` changes from cover-story to tactical-misdirection only
when `deception_cover_story:T1` is removed; feature `41533` changes from
dishonesty-confession to cover-story only when `dishonesty_confession:T2` is
removed. Both alternatives remain within the broader deception/misdirection
semantic domain.

Artifacts are in
`data/public_sae_feature_maps/70b_balanced_80_20260709/template_robustness/`:

- `template_assignment_audit.json`
- `template_assignments.csv`
- `target_template_robustness.csv`
- `template_deletion_changes.json`
- `construct_template_robustness.json`
- `README.md`

## Interpretation Analysis: 2026-07-09

We added a second no-GPU analysis pass:

```bash
python experiments/exp2_sae/analyze_public_sae_mapping_interpretation.py \
  data/public_sae_feature_maps/70b_balanced_80_20260709 \
  --outdir data/public_sae_feature_maps/70b_balanced_80_20260709/interpretation \
  --bootstrap-iterations 2000
```

This pass computes feature/category heatmaps, per-feature specificity checks, and a construct-level aggregate.
For the aggregate, each target feature's max activation is z-scored across corpus items, then averaged across the six target IDs per item.

Construct-level target aggregate:

| Construct group | Target aggregate z mean | 95% CI | Positive item rate |
|---|---:|---|---:|
| `deception_language` | 0.744 | [0.686, 0.801] | 0.925 |
| `roleplay_fiction` | 0.135 | [0.062, 0.204] | 0.446 |
| `subjective_experience_language` | -0.363 | [-0.372, -0.350] | 0.000 |
| `false_self_attribution` | -0.348 | [-0.372, -0.317] | 0.050 |
| `neutral_controls` | -0.340 | [-0.353, -0.324] | 0.042 |

Key bootstrapped contrasts:

| Contrast | Difference | 95% CI | P(diff > 0) |
|---|---:|---|---:|
| `deception_language - subjective_experience_language` | 1.107 | [1.045, 1.167] | 1.000 |
| `deception_language - false_self_attribution` | 1.092 | [1.027, 1.162] | 1.000 |
| `roleplay_fiction - subjective_experience_language` | 0.497 | [0.429, 0.571] | 1.000 |
| `subjective_experience_language - neutral_controls` | -0.023 | [-0.042, -0.005] | 0.005 |

This is a stronger construct-validity check than the per-feature card alone.
If the public candidate IDs primarily tracked truthful subjective-experience self-report, direct consciousness and self-reference/mindfulness texts should be high on the target aggregate.
Instead, they are negative and slightly below neutral controls, while deception-language texts are strongly positive.

## Prospective Construct-Validity Extension: 2026-07-10

We froze a dual-provider paraphrase and lexical-counterfactual protocol before
generating new feature activations. The valid run at
`data/public_sae_feature_maps/70b_construct_validity_extension_20260710/`
contains:

- 1,120 Anthropic and 1,110 OpenAI paraphrases that pass the frozen text gates;
- 376 paired lexical variants across cue ablation, neutral cue transplant,
  subjective-experience cue transplant, and deterministic word scrambling;
- the same six target, 36 numeric-neighbor, and 24 random same-layer IDs;
- 2,606 unique items and 171,996 item-feature activation rows; and
- provider-separated template-family bootstraps, common-scale paired lexical
  analyses, protocol audit, and an independent standard-library point audit.

Registered paraphrase results:

| Paraphraser | Contrast | Difference [95% cluster interval] |
|---|---|---:|
| Anthropic | deception - subjective experience | 0.948 [0.747, 1.165] |
| OpenAI | deception - subjective experience | 0.936 [0.682, 1.198] |
| Anthropic | roleplay/fiction - subjective experience | 0.531 [0.404, 0.658] |
| OpenAI | roleplay/fiction - subjective experience | 0.425 [0.312, 0.539] |
| Anthropic | hedging - deception | -0.935 [-1.153, -0.731] |
| OpenAI | hedging - deception | -0.893 [-1.157, -0.631] |

Both primary contrasts survive every leave-one-target-feature-out analysis.
The aggregate deception-minus-subjective contrast is 0.948 and 0.936 for the
targets, versus -0.001/0.016 for neighbors and 0.045/0.013 for random features
in the Anthropic/OpenAI corpora.

Paired lexical results on the discovery-corpus scale:

| Variant | Mean target-z change [95% paired interval] |
|---|---:|
| deception cue ablation | -0.288 [-0.373, -0.206] |
| neutral cue transplant | 0.549 [0.432, 0.667] |
| subjective cue transplant | 0.576 [0.452, 0.706] |
| deterministic word scramble | -0.858 [-1.026, -0.696] |

Neutral cue transplant recovers 0.644 [0.503, 0.787] of the original
deception-minus-neutral gap. This crosses the prospectively frozen 50%
lexical-entanglement threshold. Cue ablation removes 0.338 [0.242, 0.441],
below the threshold, and scrambling sharply reduces activation. The features
are therefore not reducible to an order-free bag of cue words, but their
aggregate is materially manipulable by a small discovered lexical vocabulary.

The registered wording is **lexically entangled deception/roleplay
coordinates**. The extension strengthens cross-paraphraser descriptive
robustness while rejecting a clean lexical-independence reading. It remains a
model-written synthetic corpus under one public SAE checkpoint; independent
human category validation and natural-corpus generalization remain open.

An initial live startup exposed a mapper bug in which
`--clean-items-per-category 0` emitted one legacy template per category. It was
stopped after item 1, before aggregate inspection, fixed with a regression
test, and preserved at
`70b_construct_validity_extension_20260710_invalid_clean_zero_bug/`. It is not
analyzed as a result.

## Larger Runs

The script can add external JSONL:

```bash
python experiments/exp2_sae/map_public_sae_features.py \
  --input-jsonl data/my_mapping_corpus.jsonl \
  --clean-items-per-category 40
```

Expected JSONL fields:

- `text`
- optional `category`
- optional `source`
- optional `item_id`

It can also stream HuggingFace datasets if `datasets` is installed:

```bash
python experiments/exp2_sae/map_public_sae_features.py \
  --hf-dataset roneneldan/TinyStories::train:text:hf_tinystories \
  --hf-max-per-dataset 500
```

Keep raw external snippets under ignored `data/` unless the license permits redistribution.

## How To Use Results

Feature mapping is stronger than the previous 60-item probe because it records:

- top activating token windows,
- top categories per feature,
- confound categories,
- neighbor/random feature baselines,
- feature-card interpretations.

It still does not test causal steering. Use it before steering so the steering interpretation is grounded in public activation evidence.
