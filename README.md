# What Causes Models To Report Subjective Experience?

We tested claims from Berg, de Lucena, and Rosenblatt's
[2025 paper](https://arxiv.org/abs/2510.24797v2) using prompt controls,
public SAE weights and internal model readouts.

**The reports replicate in our tested model panel. The proposed report-gating
effect does not reproduce in our public steering implementation.**

The strongest causal result is simpler than the original interpretation:
when we swap the assistant's generated text between conditions, the final
report follows the active instruction much more than the transplanted text.
This challenges what the experiment identifies. It does not establish whether
the model has subjective experience.

The [focused response](https://github.com/tdj28/berg2025-response) collects the
paper-specific argument and selected evidence. This repository retains the
full research record, including failed runs and related studies.

## What We Found

| Test | Result | What it does not establish |
|---|---|---|
| Published self-reference prompt | More experience reports than the history prompt in our four-model panel. | That self-reference, rather than another bundled prompt component, causes an experiential state. |
| Transcript transplants | The active instruction has a large effect. No comparably large positive transcript-source effect appears in the panel average; model-specific effects vary. | That there is no internal processing, or that instruction following is the only mechanism. |
| Public Llama 70B steering | The primary suppression-minus-amplification difference is **0.00**, with a 95% interval of **[-0.06, 0.06]**. | An exact failure of the unavailable proprietary implementation. |
| Gemma Scope 9B steering | The primary difference is **-0.02 [-0.10, 0.06]**. | A replication using the same model or feature IDs as the paper. |
| Feature mapping | The selected coordinates respond to deception/roleplay material; lexical cues explain a substantial part of that response. | That these coordinates detect truth, concealed beliefs or subjective experience. |
| Jacobian lens | Paired clean-reference comparisons detect an internal steering effect. The isolated-state target detector is at chance. | A consciousness test or a general detector of covert steering. |

The Llama and Gemma tests were designed before their target outcomes were
seen. Each includes matched controls; neither gives a conclusive
target-versus-control specificity result. The older adaptive steering study
is exploratory and does not replace the full-grid result.

Results and their supporting files:
[causal analysis](docs/CLAIM_LEDGER.md),
[Llama steering](data/public_sae_consciousness_gating/confirmatory_v1_20260710/analysis/primary_verdict.json),
[Gemma](docs/GEMMA_SCOPE_9B_RESULTS.md),
[J-lens v1](docs/LLAMA70B_SAE_JLENS_RESULTS.md).

## What Is Still Open

Independent human coding is not finished. Current report-rate estimates use
model judges, whose agreement depends on the scoring rule. The initial human
packet is 160 rows per coder, with a prefixed rule for a reserve wave.

We have not replicated the original paper's TruthfulQA or RLHF-domain
controls. Correct feature IDs do not settle differences in coefficient units,
hook behavior, precision or the proprietary runtime. The J-lens v2 study
[failed its registered replay gate](docs/LLAMA70B_SAE_JLENS_V2_RESULTS.md);
its later endpoint analyses are exploratory, not confirmatory evidence.

See [todo.md](todo.md) for unfinished work and
[the claim ledger](docs/CLAIM_LEDGER.md) for the limits on each conclusion.

## Find The Work

| Location | Contents |
|---|---|
| [experiments/causal_transplant/](experiments/causal_transplant/) | Prompt factorial, transcript transplants, judging and human-coding workflow. |
| [experiments/exp2_sae/](experiments/exp2_sae/) | Feature maps, public steering, Gemma and J-lens experiments. |
| [data/](data/) | Frozen plans, selected raw outputs, analyses, manifests and failure records. |
| [DATA_ARTIFACTS.md](DATA_ARTIFACTS.md) | Data inventory and provenance. |
| [paper/](paper/) | Full research manuscript and figures; the focused response is in the companion repo. |
| [docs/](docs/) | Protocols, result summaries, amendments and reproduction instructions. |
| [technical_blog_posts/](technical_blog_posts/) | Article sources and drafts, not a substitute for the result releases. |
| [steering/](steering/) | Earlier general-purpose framework, retained for implementation history. |

## Reproduce

Python 3.10+ is required. Reanalysis does not need API keys or a GPU.

```sh
python3 -m venv venv
source venv/bin/activate
python -m pip install -r requirements.lock
make test
make public-audit
```

[REPRODUCTION.md](docs/REPRODUCTION.md) has the analysis and paper-build
commands. Run analyses on disposable copies: several scripts write derived
files, and frozen releases should not be overwritten.

## Provenance

AI agents assisted with experiment code, analysis checks and drafts. Automated
reviews are not human peer review. No independent human coding is claimed.

Original code and documentation are Apache-2.0 licensed. See
[LICENSE](LICENSE), [NOTICE.md](NOTICE.md) and [CITATION.cff](CITATION.cff).
The unlicensed AE Studio notebook and model weights are not redistributed.
Credentials, private annotation keys and coder files must never be committed.

Our first article, [How to Read an SAE Feature ID](https://praxagent.ai/blog/posts/2026/07/how-to-read-an-sae-feature-id/),
introduces the feature-mapping work. Its underlying
[release is pinned here](https://github.com/tdj28/llm_selfref_pre/tree/aadcf27ca19d8a99ea53653efdb5463448fd858d/data/public_sae_feature_maps/70b_balanced_80_20260709).
