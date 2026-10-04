# Historical Repository Documents

These snapshots preserve the root guidance and ledgers replaced during the
owner-approved publication closeout. They are historical records, not current
execution instructions, spending authority, or a queue of experiments.

## Source Snapshot

The [October 3 root snapshot](root-docs/20261003/) is copied byte-for-byte from
commit `3adc17809bf453b87e84187438470eff9661b102`, the branch base for the
October 4, 2026 cleanup. The directory date identifies that source state, not
the date of every study or the date the copies were made. Original document
dates, stale checklist entries, corrections, and study-specific restrictions
remain unchanged.

| Original Path | Preserved Copy | Current Entry Point |
|---|---|---|
| `AGENTS.md` | [Study history and agent rules](root-docs/20261003/AGENTS.snapshot.md) | [Durable repository rules](../AGENTS.md) |
| `todo.md` | [Historical work ledger](root-docs/20261003/todo.md) | [Publication closeout](../todo.md) |
| `worst_case.md` | [No-API replication ledger](root-docs/20261003/worst_case.md) | [Archive pointer](../worst_case.md) |
| `DATA_ARTIFACTS.md` | [Historical artifact catalog](root-docs/20261003/DATA_ARTIFACTS.md) | [Artifact policy](../DATA_ARTIFACTS.md) |

The agent snapshot has a different filename so automatic directory-instruction
discovery does not load obsolete authorizations. Its contents are unchanged.
Paths inside the snapshots retain their original repository-root context;
they were not rewritten relative to this directory. Use the current
[documentation index](../docs/README.md), [data index](../data/README.md), and
[study inventory](../docs/STUDY_INVENTORY.md) to navigate the evidence.

## Preservation Check

Run from the repository root:

```bash
shasum -a 256 -c provenance/root-docs/20261003/SHA256SUMS
```

The checksum list binds all four copies. Each was also compared against its
original Git blob at the source commit above. No historical document was
corrected, reformatted, or redated while being copied.

Before replacing the root files, their names were checked against the source
commit's JSON/JSONL, YAML, TOML, text/checksum, manifest, source-inventory, and
freeze records. No source or release hash entry binds these four paths. The
only matching machine records were:

- `reviews/reproducibility/receipts/public_safety.json`, which lists required
  public filenames without binding their bytes;
- `docs/consciousness_sae_changepoint/reviews/gpt-5.6-sol-pro_20260713/request_payload_reconstructed.json`,
  which quotes an instruction to update the artifact catalog.

Both records remain in place. Existing links to the root filenames continue
to resolve. Study protocols, results, code, data releases, blog sources,
licenses, and prior review records were not moved by this consolidation.
