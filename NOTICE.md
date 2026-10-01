# Provenance And License Scope

Copyright 2026 T. Jones and Praxagent

This product includes software developed by T. Jones / Praxagent.

The October 1, 2026 consolidation restores the current manuscript and its
supporting files from the same authors' former companion repository. Original
file hashes and its notice are preserved in `paper/history/20261001/`.
Subsequent manuscript framing edits do not change frozen experimental data.
This public repository, with `paper/` as the canonical manuscript, is the
publication destination; the private companion is no longer required.

Original code and documentation in this repository are licensed under the
Apache License, Version 2.0. See the LICENSE file for the full license text.

The Apache License does not grant rights in third-party works merely
referenced, analyzed, or described here. In particular:

- Berg, de Lucena, and Rosenblatt (2025) retain rights in their paper.
- AE Studio's `steering-api-examples` notebook is not vendored. Our scripts
  parse public saved outputs and implement a clean-room protocol because its
  repository had no explicit license when this analysis was conducted.
- Meta Llama models, Goodfire SAE weights, OpenAI/Anthropic outputs, and other
  third-party services or artifacts remain subject to their own terms.
- Google Gemma 2 model weights and Gemma Scope SAE checkpoints remain subject
  to their respective Google terms and checkpoint licenses. Full checkpoints
  are not redistributed here. Correction, 2026-09-29: the Gemma release does
  contain selected decoder directions derived from those SAE checkpoints;
  the previous blanket statement that they were not redistributed was too broad.
- Generated model outputs and factual data are distributed for research
  transparency without an assertion that the Apache License overrides any
  rights or terms applicable to their source systems.

Files copied from or derived from a third-party source must carry explicit
provenance. Do not add upstream notebook code, model weights, or restricted
datasets to this repository without checking and documenting their license.

## Third-Party Artifact Inventory (2026-09-29)

| Artifact | Released material | Rights/provenance status |
|---|---|---|
| AE Studio notebook | Clean-room summaries of factual saved outputs, not notebook code | No upstream code license established; do not vendor the notebook. |
| Gemma Scope | `data/gemma_scope_9b/confirmatory_v1_20260711/**/selected_decoder_directions.npz` | Derived SAE vectors are present. Upstream checkpoint terms apply; redistribution review remains open. |
| Neuronpedia | `data/sae_jlens_audit/neuronpedia_labels_20260712/` | Public label/source snapshot with retrieval provenance. A license covering these labels has not been established in this repository; do not describe them as Apache-licensed. |
| Llama / Goodfire | Generated text, SAE activation summaries and selected residual artifacts | Source revisions and hashes are recorded per release. Model/SAE terms remain distinct from the code license. |
| Model-service outputs | Selected raw responses and automated judgments | Released for reproducibility; provider terms and any third-party rights are not overridden by the code license. |

Built with Llama. This identifies use of Meta Llama models; it is not an
assertion that Meta reviewed or endorsed the research or that this notice alone
resolves every applicable license condition.

The repository does not impose a new blanket data license on third-party
labels, checkpoint-derived vectors or generated text. Resolving redistribution
terms and an explicit original-data license is a release task for the owner.
Do not delete or rewrite existing public evidence to conceal this unresolved
issue; record any subsequent rights correction with its provenance.

## Coordinate-Delivery Release (2026-09-30)

`data/sae_assay_repair/coordinate_delivery_20260930/` contains 544 generated
clean layer-50 residual states and token IDs, not full model or SAE weights.
Its exact pinned Llama 3.3 license copy and `UPSTREAM_TERMS.json` document
the Meta source and the Goodfire model card's `llama3.3` license declaration.
The release carries the Llama attribution. This does not resolve unrelated
historical redistribution questions above or assert a new blanket data license.
