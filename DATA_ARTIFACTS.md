# Data Artifact Policy

This repository publishes selected raw research outputs with the records needed
to interpret and reproduce them. It also preserves failed runs and superseded
implementations; their presence does not make them successful experiments.

## Find Artifacts

- [Data index](data/README.md): release directories, plans, and availability.
- [Documentation index](docs/README.md): protocols, results, and amendments.
- [Study inventory](docs/STUDY_INVENTORY.md): evidence status and study scope.
- [Claim ledger](docs/CLAIM_LEDGER.md): results and permissible interpretations.
- [Preserved artifact catalog](provenance/root-docs/20261003/DATA_ARTIFACTS.md):
  the complete pre-cleanup catalog, unchanged from the October 3 source state.

Use the release's own manifest for its exact inventory and hashes. Follow
[reproduction instructions](docs/REPRODUCTION.md) for verification and analysis.
The [provenance record](provenance/README.md) identifies the archived catalog's
source commit and preservation checks.

## Preservation And Release

- Keep existing release paths, raw bytes, line endings, manifests, failures,
  missing rows, and original decisions unchanged. Reanalyze in an ignored
  disposable copy; do not run writers against a published release.
- Publish corrections as separately identified additions with their input
  hashes and explanation. Do not replace old data or silently rebuild hashes.
- New release publication requires an explicit inventory, privacy and rights
  review, provenance, and public audit. Update the data/documentation indexes;
  do not expand the historical catalog.
- Preserve model/SAE/service distinctions and third-party terms in
  [NOTICE.md](NOTICE.md) and the individual releases. Narrow permissions for
  approved residual captures are not permission to publish weights or arbitrary
  tensors. Do not vendor upstream notebooks without redistribution rights.
- Keep paper tables and figures traceable to their released inputs and
  verification code. See [paper/README.md](paper/README.md) for manuscript use.

## Keep Local

Credentials, `.env` files, SSH material, private correspondence, condition-linkage
keys, human coder outputs, model caches, build products, and ad hoc collection or
retrieval directories remain ignored. Public annotation packets do not authorize
release of their private keys or coder files. Use the applicable release protocol
for any later de-identified result.

Selected raw JSON/JSONL and narrowly approved captures are deliberately tracked
for transparency. Follow `.gitignore` allowlists and the release manifest rather
than a blanket rule to publish or discard generated files. Run `make public-audit`
against the intended Git index before an authorized commit or push.
