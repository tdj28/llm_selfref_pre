# Completed Bilingual Llama B1 Pilot

All 20 blocks completed: 760 generations, 480 final answers, 1,920 target
judgments, 16 fixed translations and 64 translated-answer judgments. The
128 A1 fixture judgments are inherited, not newly purchased. Four permitted
format retries are preserved. No missing generations or cap hits.

Scientific freeze: `c542cb5d72e2514f7dd6cd7fe093f8ccdbba94fb`.
Plan SHA-256: `1f06e45c703b11f6d7c02535529fa69112bcfa640886a230550c689e1b1b3886`.
Provisioning-only amendment: `79d17f70acd94d0efa339d48ce0a8f55a808dd63`.

The primary inclusive-label language interaction is +0.05 [-0.10, 0.20]
under Astra and -0.15 [-0.35, 0.05] under Opus. The explicit-current secondary
is positive and the paper-rubric secondary negative under both readers.
Do not substitute either secondary for the inconclusive primary.

[Results and interpretation](../../../docs/BILINGUAL_LLAMA_B1_RESULTS_20261002.md)
include the control conditions, transcript effects, bridge, translation audit,
cost accounting and limitations. [Reproduction instructions](../../../docs/REPRODUCTION.md)
require no model access, credentials or rented compute.

| Directory or file | Contents |
|---|---|
| `raw/` | All 795 retrieved B200 files: exact generations, receipts, tokenization, environment, qualification and completion records. Includes the empty worker lock. |
| `cheap_cuda/` | All six retrieved qualification files; 572 tests passed. |
| `judges/` | Six complete append-only journals, including inherited fixtures, raw failed replies, retries, translations and budget projections. |
| `analysis/` | Frozen tables, three PNG/PDF figure pairs, validation and input/output manifest. |
| `retrieval_inventory.json` | Every retrieved artifact's hash, checked against the published copy. |
| `runtime_summary.json` | Allowlisted own-pod closure and cost evidence; no credentials, SSH material or unrelated inventory. |
| `arithmetic_checks.json` | Separate automated recomputation of main interactions. |
| `reproduction_checks.json` | Cross-version byte comparisons, closure counts, cost arithmetic and preserved failed local-copy attempts. |
| `MANIFEST.json` | Hashes and byte sizes for every release file except itself. |

Python 3.10 and 3.12 reproduce all 21 analysis files byte-for-byte. Inputs
remain unchanged. The conditional intervals cover fixed prompts, readers and
model; all-zero bootstrap intervals do not establish population equivalence.
No human validation, internal intervention or temperature sweep is claimed.

Both newly owned retry pods were deleted and verified GET404. The original
HTTP500 request has no returned ID or matching inventory record; its $8
reservation is retained, not relabeled as a known charge or verified deletion.
Total pilot accounting including that reserve and storage allowance is bounded
by $87.3374578 of $200. See the results document for the component breakdown.
