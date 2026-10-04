# Historical Planning Archive

These obsolete roadmaps, drafts, handoffs and process notes are retained for
provenance, not as current proposals, execution authority or evidence of work
completed. Use the [research guide](../../docs/README.md) for study status and
the [closeout checklist](../../todo.md) for remaining publication work.

## Relocation Map

Source commit: `294da265ee3a08b9ef42343f9461b8d4718b7bc7`.
The table is the single old-to-new map for unchanged historical references,
including the root snapshots and the superseded JLENS causal-report draft.
Commit-pinned web links still refer to their original commit, not this map.

| Original path | Archived document | Preservation |
|---|---|---|
| docs/BERG_REPLICATION_MECHANISM_ROADMAP_20260930.md | [Berg mechanism roadmap](BERG_REPLICATION_MECHANISM_ROADMAP_20260930.md) | Relative links only |
| docs/GEMMA_SCOPE_9B_ROADMAP.md | [Gemma roadmap](GEMMA_SCOPE_9B_ROADMAP.md) | Relative links only |
| docs/SAE_VS_JACOBIAN_LENS_STEERING.md | [SAE/J-lens follow-up note](SAE_VS_JACOBIAN_LENS_STEERING.md) | Byte-identical |
| docs/STEERING_FIDELITY_TEST_DESIGN_NOTES_20261002.md | [Unrun Stage T draft](STEERING_FIDELITY_TEST_DESIGN_NOTES_20261002.md) | Byte-identical |
| docs/BILINGUAL_LLAMA_PILOT_A1_DRAFT_20261002.md | [Superseded bilingual A1 draft](BILINGUAL_LLAMA_PILOT_A1_DRAFT_20261002.md) | Byte-identical |
| docs/SAE_CONSCIOUSNESS_GATING_RENDER_NOTE_20260710.md | [Historical figure-render repair](SAE_CONSCIOUSNESS_GATING_RENDER_NOTE_20260710.md) | Byte-identical |
| docs/HUMAN_CODING_HANDOFF.md | [Paused human-coding handoff](HUMAN_CODING_HANDOFF.md) | Relative links only |
| docs/EXTERNAL_REVIEW_PACKET.md | [Earlier-manuscript review request](EXTERNAL_REVIEW_PACKET.md) | Byte-identical |

Only eight relative Markdown link targets were rebased; all other archived
bytes, including stale status text, costs, failures and proposed work, are
unchanged. Inline paths and commands retain their repository-root context and
are historical, not instructions to execute. The sole original-path pointer
is the [human handoff](../../docs/HUMAN_CODING_HANDOFF.md), needed by the
untouched live manuscript and experiment README. Active navigation links point
directly into this archive. The historical review request does not cover the
current manuscript or satisfy the outstanding independent-review requirement.

## Retained At Original Paths

Before moving each file, its basename/stem and SHA-256 were searched across the
tracked tree, including source inventories, plans, manifests, review packets,
code and tests. None of these eight is a machine-bound input. This check does
not authorize moving other files or modifying scientific records.

Similar-looking documents deliberately remain under `docs/`:

- Exposure design/preflight/lifecycle, J-lens hard-negative requests and assay
  implementation/planning records have source-plan or review-manifest bindings.
- Design-validity and bootstrap documents are referenced by runtime source.
- Offline feasibility, startup, retrieval and portability records are linked
  from releases, results or reproduction; some retain unresolved failures.
- Switch-arc and mechanism-consultation packets remain with their review
  records. Protocols, amendments, reviews and research claims were not edited.

The [root-snapshot checksum list](../root-docs/20261003/SHA256SUMS) is unchanged.
[Archive tests](../../tests/test_planning_archive.py) compare every moved file
with its source Git blob, allowing only the declared link rebasing, and check
local navigation plus relocation of historical references.
