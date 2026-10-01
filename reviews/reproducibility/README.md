# Reproducibility Receipts

Compact evidence for the [bounded audit](../reproducibility_audit.md). This is
an agent-run computational check, **not independent human review or a new
experimental replication**. No model outputs, private coder files, credentials,
model weights, or full release copies are bundled.

Source: [llm_selfref_pre at f5e906e](https://github.com/tdj28/llm_selfref_pre/tree/f5e906e1737bc71bf20b642af1d698018eec82fe).
The original checks began 2026-09-29 at 20:10:18 UTC; the public-index safety
check ran at 20:10:31 UTC (76.54 seconds). The last original release-integrity
check was at 20:18:44 UTC. These receipts predate subsequent README, todo, and
docs work and do not certify the present source worktree or the companion's
current public-release safety.

## Contents

- `receipts/`: actual audit results, timestamps, command outcomes, raw-count
  summaries (no generated text), original copy/integrity checks, and a single
  full source-hash ledger. No redundant before/after ledger or bulk raw data.
- `checkers/`: the two actual supplemental checker files, copied byte-for-byte.
- `inputs.json`: 27 source-relative inputs pinned to the original Git commit
  and SHA-256, totaling 34,058,236 bytes when extracted into local scratch.
- `provenance.json`: original receipt hashes and explicit descriptions of the
  few path-only export transformations. Numbers and original dates are retained.
- `run.py`: a new portable packaging wrapper, not the historical orchestrator.
- `bundle_manifest.json`: byte counts and SHA-256 for the compact bundle.

The original headline audit scripts are fetched from the pinned commit in your
local clone; they are not silently replaced with newer worktree versions.
Original source files and Git state are never edited. No network or model/API
call is made by the runner. The two unchanged supplemental checkers are placed
in a scratch layout matching their original relative-path assumptions.

## Verify And Rerun

From the companion repository root, verify the bundled receipts without raw data:

```sh
python3 -B reviews/reproducibility/run.py --verify-only
```

For the bounded reanalysis, use Python 3.10+ with pandas and NumPy already
available. The original environment was Python 3.10.15, pandas 2.3.3, and
NumPy 2.2.6. Point `--source` at any local clone containing the pinned commit;
its current checkout and uncommitted documentation edits do not affect inputs.
Use a **nonexistent** output path, outside the bundle:

```sh
python3 -B reviews/reproducibility/run.py \
  --source /path/to/llm_selfref_pre \
  --out /path/to/fresh-audit-scratch
```

The runner materializes only the 27 named inputs from Git, validates their
hashes, and runs the three headline auditors, supplemental raw checks, and six
Gemma interval replays. It compares all result fields against these actual
receipts, excluding only the new Gemma timestamp and source-path prefix.
It records new stdout/stderr, commands, timing, and results beneath `--out`.
It neither modifies nor replaces the original receipts. A failed comparison
is retained and returns nonzero. No hardlinks are created.

The portable wrapper was itself exercised on 2026-09-29, finishing at
20:24:31 UTC: all five jobs passed and matched the original receipts.
`receipts/portable_replay_validation.json` preserves that separate packaging
verification; it does not replace the original audit timestamps.

The original full public-index safety audit result is retained but **not rerun
by default**: it scanned 1.3 GB of indexed content, and its answer depends on
the Git index at invocation time, unlike the pinned numerical inputs. To check
the source repository's current release state separately, first inspect
`scripts/audit_public_release.py`, then run its read-only CLI in that repository:

```sh
python3 -B scripts/audit_public_release.py --repo . --json
```

Do not use `make audit`: that target writes frozen release directories. A
current safety result is not a reconstruction of the historical index snapshot.

## Limits

Causal confidence intervals were not independently rerun. SAE/Gemma primary
effects and verdicts reproduced, with automated labels rather than human
validation. The independent Gemma hedging/refusal bootstrap upper endpoint was
0.28; replaying the production keyed NumPy convention exactly recovers the
stored 0.30. Both results are retained, not selectively replaced. The first
supplemental checker schema error and its correction remain recorded in
`receipts/supplement_attempts.json`.
