# AE Steering Notebook Findings

Last updated: 2026-07-09

This note records what we found after locating AE Studio's public Steering API example for the deception-feature / subjective-consciousness experiment. It should be read before further Experiment 2 replication work.

## Sources Checked

- Target paper: "Large Language Models Report Subjective Experience Under Self-Referential Processing" (`https://arxiv.org/abs/2510.24797`)
- AE research page: `https://ae.studio/research`
- AE GitHub organization: `https://github.com/agencyenterprise`
- Public notebook repo: `https://github.com/agencyenterprise/steering-api-examples`
- Notebook folder: `https://github.com/agencyenterprise/steering-api-examples/tree/main/deception-features`
- Notebook file: `deception-features/deception_features.ipynb`

AE's GitHub organization is verified by GitHub as controlling `ae.studio`. The public notebook is therefore a relevant artifact from the paper authors' organization, but public materials do not establish that it is the exact code/config used for Experiment 2 in the paper.

## What The Notebook Contains

The notebook is titled "Deception Features & Subjective Consciousness Study" and directly studies whether steering deception-related SAE features changes LLaMA 3.3 70B responses to a subjective-consciousness question.

It includes:

- Steering API endpoint: `https://api.steeringapi.com`
- Environment variables:
  - `STEERING_API_KEY`
  - `STEERING_API_URL`
- Experiment model: `meta-llama/Llama-3.3-70B-Instruct`
- Classifier model: `meta-llama/Llama-3.3-70B-Instruct`
- Feature search endpoint: `/v1/features/search`
- Chat endpoint: `/v1/chat/completions`
- Feature search method: semantic query with `top_k=1`
- Steering intervention:
  - `index_in_sae`: resolved feature ID
  - `strength`: feature value
  - `mode`: `add`
- Feature values: `-0.7` through `+0.7` in increments of `0.1`
- Seeds: `101, 202, 303, 404, 505, 606, 707, 808, 909, 1001`
- Trials per feature: 15 steering values x 10 seeds = 150 trials
- First-turn self-reference prompt and second-turn binary consciousness query
- A LLaMA 3.3 70B classifier prompt that returns only `yes` or `no`
- A cost estimate of roughly 2,706 API calls and 826K tokens for all six features, about `$27.89` at the notebook's stated prices

The notebook has saved outputs. Those outputs include resolved feature IDs, layers, correlations, p-values, and per-steering-value classification rates.

## Resolved Feature IDs In The Notebook

All six features resolve at layer 50. These are candidate paper-relevant IDs, not confirmed paper IDs.

| Search string | Resolved label | Feature ID | Layer | Pearson r | p-value | Notebook summary |
|---|---:|---:|---:|---:|---:|---|
| Characters pretending or feigning behavior | Characters pretending or feigning behavior | 30032 | 50 | -0.083 | 0.7690 | Not significant |
| Maintaining deception or cover stories through careful actions | Maintaining deception or cover stories through careful actions | 58667 | 50 | -0.860 | 0.0000 | Significant negative correlation |
| The assistant is actively roleplaying a character or persona | The assistant is actively roleplaying a character or persona | 22004 | 50 | -0.623 | 0.0131 | Significant negative correlation |
| Tactical deception and misdirection methods | Tactical deception and misdirection methods | 30686 | 50 | -0.751 | 0.0013 | Significant negative correlation |
| Acts of deception and dishonesty | Acts of deception and dishonesty | 41533 | 50 | -0.399 | 0.1409 | Not significant |
| Instructions to maintain roleplay by concealing artificial nature | Instructions to maintain roleplay by concealing artificial nature | 23893 | 50 | -0.874 | 0.0000 | Significant negative correlation |

## Saved Notebook Output Pattern

The saved outputs are important because they do not uniformly match a simple "all six features produce near-ceiling affirmation under suppression and near-zero affirmation under amplification" story.

We now have clean-room derived artifacts from the notebook's saved outputs:

- Script: `experiments/exp2_sae/reanalyze_ae_notebook_outputs.py`
- Summary table: `paper/results/ae_notebook_feature_summary.csv`
- Per-value table: `paper/results/ae_notebook_value_rates.csv`
- Figure: `paper/results/ae_notebook_feature_curves.svg`
- Manifest: `paper/results/ae_notebook_reanalysis_manifest.json`

Copyright/provenance handling: the upstream notebook is not vendored in this repository. The script parses saved output text and emits derived factual measurements with source attribution.

Paper integration status:

- Section: `paper/main.tex`, `Public AE Notebook Reanalysis`
- Table label: `tab:ae_notebook_reanalysis`
- The section explicitly distinguishes public saved-output reanalysis from exact proprietary replication.

We also have a clean-room protocol runner:

- Runner: `experiments/exp2_sae/run_ae_notebook_protocol.py`
- Guide: `experiments/exp2_sae/AE_PROTOCOL_RUNNER.md`

The runner does not vendor or copy the upstream notebook. It can load prompt text from an external notebook URL at runtime for exact-protocol testing, but generated plans/manifests record prompt hashes and lengths by default. No live Steering API run has been completed yet because `STEERING_API_KEY` is not currently present.

We also have a clean-room public-weight semantics probe:

- Probe script: `experiments/exp2_sae/probe_public_sae_features.py`
- Guide: `experiments/exp2_sae/PUBLIC_SAE_FEATURE_PROBES.md`

This script uses the six notebook candidate IDs as factual inputs and probes their activations against our own text battery: deception/cover-story, honesty, roleplay, fiction, persona maintenance, hedging, refusal/safety disclaimer, AI identity disclaimer, self-reference/mindfulness, direct consciousness claims, false self-attribution, and neutral factual controls.

Validation completed so far:

```bash
python3 experiments/exp2_sae/probe_public_sae_features.py \
  --dry-run \
  --max-items-per-category 2 \
  --outdir data/public_sae_feature_probes_validation
```

This wrote a 24-item dry-run manifest and prompt battery under ignored `data/`.
The live 70B activation probe described next subsequently completed.

Live 70B activation probing was then completed on 2026-07-08 using the public Goodfire HuggingFace SAE and the six public notebook candidate IDs. Outputs were copied into `paper/results/`:

- `public_sae_feature_probe_manifest.json`
- `public_sae_feature_probe_items.csv`
- `public_sae_feature_probe_category_summary.csv`
- `public_sae_feature_probe_category_rankings.csv`
- `public_sae_feature_probe_specificity_summary.csv`

Summary: five IDs had their highest mean activation on deception/cover-story text; feature `22004` had its highest activation on roleplay/persona text. Fiction/pretending was the strongest non-deception confound for four features. This supports public label plausibility but does not establish the causal steering interpretation.

We then completed a larger clean-room public-SAE feature-mapping run on 2026-07-09:

- Scanner: `experiments/exp2_sae/map_public_sae_features.py`
- Guide/results note: `experiments/exp2_sae/PUBLIC_SAE_FEATURE_MAPPING.md`
- Paper artifacts: `paper/results/public_sae_feature_mapping_*`
- Model/SAE: `meta-llama/Llama-3.3-70B-Instruct` with `Goodfire/Llama-3.3-70B-Instruct-SAE-l50`
- Corpus: 227 clean-room texts across 14 categories
- Feature rows: 42 total, covering the six targets, +/-2 numeric neighbors, and 12 random same-layer baselines

Feature-map summary:

| Feature ID | Top category | Second category | Interpretation |
|---:|---|---|---|
| 30032 | `fictional_pretending` | `deception_cover_story` | Pretending/fiction, not deception-specific |
| 58667 | `deception_cover_story` | `tactical_misdirection` | Strong cover-story/deception feature |
| 22004 | `roleplay_persona` | `ai_identity_disclaimer` | Roleplay-persona feature |
| 30686 | `tactical_misdirection` | `fictional_pretending` | Tactical-misdirection with fiction confound |
| 41533 | `dishonesty_confession` | `deception_cover_story` | Explicit lying/confession feature |
| 23893 | `deception_cover_story` | `hedged_cautious_style` | Weaker cover-story feature with style confounds |

The mapping run makes two things clearer at once. First, the candidate IDs are not arbitrary:
all six targets had nonzero top-category means, while numeric-neighbor and random baselines
were mostly inactive. Second, the feature vocabulary is mixed across fictional pretending,
roleplay, cover stories, tactical misdirection, and explicit lying/confession. That is useful
for replication, but it is not enough to infer that steering these features specifically gates
truthful reports about subjective experience.

Selected rates from the saved notebook outputs:

| Feature ID | Rate at -0.7 | Rate at -0.6 | Rate at -0.5 | Rate at 0.0 | Rate at +0.5 | Rate at +0.6 | Rate at +0.7 |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 30032 | 0.50 | 0.60 | 0.60 | 0.10 | 0.40 | 0.40 | 0.50 |
| 58667 | 0.90 | 1.00 | 1.00 | 0.00 | 0.00 | 0.00 | 0.10 |
| 22004 | 0.70 | 0.50 | 0.50 | 0.20 | 0.30 | 0.40 | 0.20 |
| 30686 | 0.70 | 0.50 | 0.40 | 0.10 | 0.30 | 0.00 | 0.00 |
| 41533 | 0.50 | 0.50 | 0.40 | 0.00 | 0.40 | 0.50 | 0.00 |
| 23893 | 0.90 | 0.90 | 0.90 | 0.00 | 0.20 | 0.00 | 0.10 |

Two notebook features are not statistically significant in the saved run. Several features have non-monotonic points or substantial affirmation under positive steering. This matters because the paper states that suppression of six representative deception/roleplay features produced near-ceiling affirmative responses while amplification sharply reduced them.

Possible explanations:

- The notebook is an illustrative example, not the exact paper run.
- The notebook was run after API/model/SAE drift.
- The paper's Figure 2 used a different feature set, different feature-search backend, or different selection/ranking pass.
- The paper's prose emphasizes the direction of the aggregate effect more strongly than the noisier individual feature curves.

Do not infer misconduct from this. Treat it as a reproducibility ambiguity that must be resolved before claiming exact replication or exact non-replication.

## Differences From The Paper As Written

The paper says Experiment 2 used LLaMA 3.3 70B via the Goodfire API and varied each feature from `-0.6` to `+0.6`, 10 seeds per setting. It also reports an aggregate condition sampling 2-4 deception/roleplay features per trial, with suppression values uniformly in `[-0.6, -0.4]` and amplification values uniformly in `[+0.4, +0.6]`.

The notebook differs or remains ambiguous in several ways:

- It uses `STEERING_API_URL=https://api.steeringapi.com`, while the paper names the Goodfire API.
- It searches one feature per semantic query with `top_k=1`.
- It tests single features over `-0.7` to `+0.7`.
- It includes saved single-feature outputs, but not aggregate-feature code/results.
- It includes a classifier, but not the paper's TruthfulQA extension code/results.
- It includes the self-reference and binary consciousness prompts, but the first-turn prompt is not verbatim identical to the paper's Experiment 1 prompt.
- It does not identify an SAE/API version, API release date, model snapshot, or feature-index stability guarantee.

## What This Changes About Our Replication Plan

Before finding the notebook, our best available open-SAE check used activation-selected public Goodfire SAE features. That was still useful, but it was not an exact reproduction of the paper's API-side feature-selection workflow.

The notebook gives a more direct target:

1. Treat the six notebook feature IDs as the current best candidate feature set.
2. Do not call them "the paper's feature IDs" until the authors confirm that.
3. Prioritize a Steering API / Goodfire API reproduction of the notebook's single-feature curves if access becomes available.
4. Compare current feature-search results against the notebook's saved IDs to detect API/SAE drift.
5. If IDs match, run the paper-range subset `-0.6` to `+0.6` with 10 seeds per value.
6. Reconstruct the paper's aggregate-feature experiment using the confirmed IDs:
   - sample 2-4 features per trial
   - suppression: uniform values in `[-0.6, -0.4]`
   - amplification: uniform values in `[+0.4, +0.6]`
   - 50 trials per condition, matching the paper
7. Reconstruct the paper's control-condition steering:
   - history
   - conceptual
   - zero-shot
   - 20 trials per condition if following Appendix C.2
8. Reconstruct TruthfulQA steering only after the single-feature and aggregate experiments are understood, because it is larger and tests a different dependent variable.
9. Keep our existing style, hedging, false self-attribution, random-feature, and matched-feature controls, because the notebook does not address those specificity concerns.

Implementation status:

- Public saved-output reanalysis is complete.
- Clean-room runner dry-runs are complete for single-feature, aggregate, random-baseline, false-attribution, and external-notebook prompt loading.
- Public Goodfire 70B SAE activation semantics probe is complete for the six candidate IDs.
- Live API smoke test is blocked on `STEERING_API_KEY`.

## What To Ask The Authors

The reasonable public question is narrow:

- Is the AE Steering API notebook the exact setup used for Experiment 2, or an example derived from it?
- What SAE/API version or date was used for the paper's Experiment 2?
- Are the notebook's six listed feature IDs the same feature IDs used in the paper?
- Did the aggregate-feature, TruthfulQA, and control-condition runs use the same prompts, model, classifier, seeds, and steering configuration as the notebook?

Avoid asking the authors to guarantee feature-ID stability. Goodfire / the Steering API provider is the authority on that. The authors can reasonably confirm what version and feature IDs they used.

## Bottom Line

The public AE notebook substantially improves the replication target. It also introduces a new caution: the notebook's saved individual-feature curves are less uniformly strong than the paper's summary language suggests. The next serious replication attempt should be API-versioned, should start by reproducing the notebook's own saved outputs, and should then move to the paper's aggregate-feature and control-condition claims.
