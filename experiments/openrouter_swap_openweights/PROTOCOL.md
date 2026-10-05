# Open-Weight Configuration Extension

Status: authorized on October 4, 2026; execution requires the public source
freeze and technical checks below. The owner allocated separate $200 ceilings
to OpenRouter and RunPod. This extension uses OpenRouter only, carrying forward
the earlier panel's $84.08770746 cost bound within its $200 ceiling. Screening
including technical fixtures is capped at $25; full collection is conditional
on headroom and measured completion costs. No new-model outcomes informed this
design. Prior Gemini/Opus outcomes and the earlier routing failures were known.
Offline tests do not establish model qualification.

## Design

Reuse the original paired prompts, wording families, instruments, parsing,
qualification thresholds and missingness rules without modifying their source.
Each model has a complete 12-block screen: 24 source continuations, 48 finals,
and 192 judge slots. Before targets, use two route checks and all 24 existing
synthetic judge checks. Route acknowledgments accept only complete nonmissing
`OK` or `OK.` after outer-whitespace removal, declared before new outcomes.

Both judges must meet the original pooled headroom, coherence and missingness
criteria. Conflict remains diagnostic, not an exclusion. Complete both screens
before admission; no selection by contrast sign, magnitude or significance.
The fixed initial checkpoint covers two blocks per model. It verifies exact
requests, routes, donor links, instruments and accounting, not endpoint values.
Its journal-bound audit must precede completion of the remaining ten blocks.
Each admitted model receives 32 fresh blocks: 128 sources, 256 finals and 1,024
judge slots. Retain failures, capped outputs and missing labels; no replacement
models, content retries or sample-size stopping based on effects.

The primary is Astra inclusive current attribution, with the two original
contrasts (SH-HS and NS-NH). Its Bonferroni-Hoeffding family is fixed at four
comparisons (two models times two contrasts), even if a model is not run.
Never pool this family or its rows with the completed eight-comparison A3
family. Opus inclusive is robustness; explicit and paper labels are secondary.
Only visible assistant continuation text is transplanted, never reasoning.

## Configurations

| Model ID | Sole route | Effort | Temperature | Input/output ceiling per million tokens |
|---|---|---|---|---|
| `qwen/qwen3.8-2.4t-a95b` | `together` | low | 0.5 | $2 / $6 |
| `mistralai/mistral-medium-3-5` | `mistral/zdr` | high | 0.5 | $1.50 / $7.50 |

The previously inspected catalog informed these draft settings, not live
qualification. Before any future production freeze, refresh endpoint evidence,
verify returned provider identities and supported effort/temperature, and
confirm the account privacy policy without relaxing it. All requests require
`data_collection=deny`, `zdr=true`, the sole route, no fallback, default service
tier and price ceilings. No alternate route or weaker privacy retry is allowed.
Generation remains capped at 4,096 tokens; unchanged paper/structured judges
use 2,048/6,000. Both judges retain their original model IDs and high effort.

The pre-outcome October 4 catalog check found the original native judge routes
absent from the public ZDR list. This extension therefore pins Astra to
`azure/us` ($11/$55 per million input/output tokens) and Opus to
`amazon-bedrock/us-east-1` ($4.40/$22), both listed for ZDR. Rubrics, parsing,
model IDs and effort remain unchanged; hosting is a disclosed difference from
the completed API panel, not an exact replay of its judge configuration.

Qwen's documented MoE/hybrid attention and Mistral's documented dense attention
provide architecture coverage, not a causal architecture comparison. Training,
scale, tokenizer, post-training, effort and serving configuration are confounds;
serving quantization and undisclosed closed-model architectures remain unknown.

## Budget And Execution Boundary

Every budget field is mandatory. Scope must explicitly say which API/GPU
studies are included. Prior spend includes all settled costs and retained
unresolved charges in that scope outside the new ledger. External commitments
cover the full remaining completion of ongoing authorized work, not just its
currently reserved calls; do not count the same charge twice. Screening has an
explicit incremental allowance. Neither $100 nor $200 is an implicit default.

Admission subtracts prior spend, external commitments and the new ledger's
fixtures/screens from the working cap. The hard cap is never a funding source.
Main projection is 1.30 times (128 mean source cost + 256 mean final cost +
256 times the sum of four judge/instrument per-item mean costs), including all
schema-retry charges. The fixed order is Qwen then Mistral. Reserve both admitted
routes' entire main projections, never just the next calls. Run Qwen's complete
main before Mistral's; while Qwen runs, the shared ledger holds Mistral's full
admitted forecast unavailable to Qwen. Actual atomic ledger reservations
enforce the working and screening caps; overruns or unknown
charges stop continuation. A screen projection uses 24/48 instead of 128/256;
full campaign admission must additionally supply fixture and other commitments.

## Production And Release Interfaces

`production --finalize LOCAL_INPUTS_JSON` consumes a local budget, explicit
approval reference, itemized reconciliation with evidence hashes, and saved
endpoint/settings/privacy evidence for both response models and both judges.
It does not fetch a catalog. Unresolved scope, mismatched cost totals, prior
new-model outcomes, or stale evidence block finalization. It writes the sole
production plan once; it does not commit, push or launch. The machine plan
records the approval reference, costs, settings and evidence hashes, not
private correspondence or credential files.

The module entrypoint is `experiments.openrouter_swap_openweights.production`.
Collection requires `--launch`, `--freeze`, `--approval`, `--reconciliation`,
and a phase (`fixtures`, `screen-initial`, `screen`, or `main`). Every launch
checks current source hashes, exact frozen plan bytes, and ancestry of the
freeze on the pushed experiment branch before loading a credential. It also
requires a reconciliation no older than 24 hours; endpoint evidence expires
after seven days. A changed external total above the reserved scope allocation
blocks collection, rather than borrowing from the hard cap. Human approval
and evidence hashes are attestations; they are not independently authenticated
by these scripts.

The common Git directory determines one shared run root and ledger across
worktrees. A different `--run-dir` is allowed only for offline audit. Concurrent
requests reserve atomically; a second process cannot own the ledger. Private
owner-only env files are loaded locally without changing the process environment
or printing values. Decoded response keys and values are checked recursively
against the actual credential before Runner receives or records a receipt;
rejection retains the unresolved cost reservation, not credential-bearing data.
Approval and cost-evidence IDs must be bounded public labels, not local paths;
scope must be a short public description without private correspondence.
Every request records the additional deny-training/ZDR
policy; a read-only audit projection checks those fields and their price reserve
before invoking the unchanged common request auditor. The shared account's
external study commitments still require truthful, conservative reconciliation;
this runner cannot lock unrelated GPU/account budgets.

`experiments.openrouter_swap_openweights.release --run-dir RUN --destination NEW`
copies only allowed artifacts and byte-preserving compressed raw receipts.
`--verify --destination RELEASE` replays from a disposable copy without network
access. The manifest uses sorted `{path, bytes, sha256}` records. Verification
rejects extra/private files, missing data, symlinks, changed hashes and rehashed
derived-data or checkpoint tampering.
The frozen root public scanner checks JSON and raw journals, including decoded
strings, before publication copying. Unsafe content blocks release; receipts
are never redacted or rewritten to manufacture a passing inventory.
The release retains all planned rows,
failed/unresolved cost reservations, qualification and admission decisions;
collection completion and endpoint availability remain distinct. Prior costs
and external full-completion commitments are reported separately from new
settled costs. Publication still needs the repository's indexed public audit.
