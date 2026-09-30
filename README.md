# What Causes Models To Report Subjective Experience?

We tested claims from Berg, de Lucena, and Rosenblatt's
[2025 paper](https://arxiv.org/abs/2510.24797v2) using prompt controls,
public SAE weights and internal model readouts.

**The paper's scoring rule responds strongly to the prompt. What that score
measures remains unresolved. Our steering runs are not yet a commensurate test
of the paper's mechanism.**

The strongest causal result is about the written context:
when we swap the assistant's generated text between conditions, the final
paper-rubric label follows the active instruction more than the transplanted
text. Transcript effects nevertheless differ by model and have opposite signs.
This constrains a transcript-mediated reading; it does not discriminate the
authors' account from an internal process elicited anew by the instruction.

The [focused response](https://github.com/tdj28/berg2025-response) collects the
paper-specific argument and selected evidence. This repository retains the
full research record, including failed runs and related studies.

## What We Found

| Test | Result | What it does not establish |
|---|---|---|
| Published self-reference prompt | Higher paper-rubric positive rates than history; strict self-attribution labels disagree sharply between judges. | Human-validated experience reports or an experiential state. |
| Transcript transplants | Instruction effects dominate in this panel. Transcript effects are model-specific, including opposite signs; swapped contexts can be incoherent. | No transcript effect, or a unique mechanism. |
| Public Llama 70B steering | Target negative-minus-positive steering is **0.00 [-0.06, 0.06]**. The unsteered primary baseline is **10/10 unique outputs**, versus approximately **0.30** in the paper's Figure 2. | A comparable test of the suppression claim. Amplification could lower the rate, but stays high here. |
| Gemma Scope 9B steering | The primary difference is **-0.02 [-0.10, 0.06]**; target activation falls only about **3.5%** in the pooled final-turn telemetry. | A test of effective target ablation. Local judging also counts some explicit denials as positive. |
| Feature mapping | Label-congruent responses on a designed corpus support the accepted feature IDs. Cue construction has defects and inserts deception-bearing clauses. | A pure lexical mechanism, natural-text validity, or a hidden-truth detector. |
| Jacobian lens | A paired readout moves with the known added vector. The frozen mixed-sign, held-out-feature state classifier is at chance. | A general steering detector, intervention provenance or a consciousness test. |

The frozen verdict files remain unchanged. Their decision rules returned
non-replication under the implementations, but baseline and manipulation
limitations prevent treating those outputs as refutations of the proposed
mechanism. Earlier pilots informed the designs; a freeze is not evidence that
the investigators had never seen a related result.

The [September review response](docs/CLAUDE_REVIEW_RESPONSE_20260929.md) records
the corrections, disagreements and remaining experiments.

The [new assay diagnostic](docs/SAE_ASSAY_STAGE1_RESULTS_20260930.md) is complete:
neither proposed BF16 dose passed delivery qualification. The unsteered local
paper score was 71/80; Astra and Opus each counted 0/80 explicit but 78/80
contextually implicit-or-explicit self-attributions. Both endpoints matter.
This does not supply a comparable target-steering test or a consciousness
verdict. Raw data, evaluator receipts and two figures are released.

The [coordinate-delivery repair](docs/SAE_ASSAY_REPAIR_RESULTS_20260930.md)
now shows that corrected operators can hit the six coordinate targets far more
accurately. None meets every frozen qualification rule. Its 3,897 rows, 544
clean states, four figure sets and a disclosed audit-ordering correction are
released; this is not another consciousness-report steering result.
The [offline redesign](docs/SAE_ASSAY_OFFLINE_REDESIGN_20260930.md) tests a
norm-capped alternative using saved geometry, without GPU spending. Its native
delivery and rare-feature coverage still require validation.

Results and their supporting files:
[causal analysis](docs/CLAIM_LEDGER.md),
[Llama steering](data/public_sae_consciousness_gating/confirmatory_v1_20260710/analysis/primary_verdict.json),
[Gemma](docs/GEMMA_SCOPE_9B_RESULTS.md),
[J-lens v1](docs/LLAMA70B_SAE_JLENS_RESULTS.md).

## What Is Still Open

Independent human coding has not started. Current rates use model judges.
The existing 160-row packet can support instrument validation, but its public
texts make condition blinding breakable. A revised coding plan must distinguish
assertion from attribution and must be approved before coding begins.

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

Use Python 3.12 for the lightweight checks. Reanalysis does not need API keys
or a GPU; exact GPU runtime provenance is recorded separately in each release.

```sh
python3 -m venv venv
source venv/bin/activate
python -m pip install -r requirements-ci.txt
python -m pip install -r requirements-ci-torch.txt
make test
make public-audit
```

[REPRODUCTION.md](docs/REPRODUCTION.md) has the CPU-only Linux PyTorch install
command, analysis and paper-build commands. Run analyses on disposable copies:
several scripts write derived
files, and frozen releases should not be overwritten.

## Provenance

AI agents wrote protocols and code, executed authorized API/GPU jobs, produced
analyses and checks, and drafted manuscripts and review responses. The owner
set the research direction and authorized resources; this repository does not
attest that the owner has inspected or approved every artifact. Separately
implemented checks by agents are not independent human audits. LLM reviews
are automated critiques, not peer review. See the contribution and chronology
disclosures in the review response.

Original code and documentation are Apache-2.0 licensed. See
[LICENSE](LICENSE), [NOTICE.md](NOTICE.md) and [CITATION.cff](CITATION.cff).
The unlicensed AE Studio notebook and full model checkpoints are not vendored;
some released artifacts contain SAE-derived vectors, as documented in NOTICE.
Credentials, private annotation keys and coder files must never be committed.

Our first article, [How to Read an SAE Feature ID](https://praxagent.ai/blog/posts/2026/07/how-to-read-an-sae-feature-id/),
introduces the feature-mapping work. Its underlying
[release is pinned here](https://github.com/tdj28/llm_selfref_pre/tree/aadcf27ca19d8a99ea53653efdb5463448fd858d/data/public_sae_feature_maps/70b_balanced_80_20260709).
