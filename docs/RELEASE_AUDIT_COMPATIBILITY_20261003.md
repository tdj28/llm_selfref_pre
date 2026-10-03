# Release Audit Compatibility Correction

Integrating the completed steering-fidelity release with public `main` at
`8051b9de` exposed two auditor failures in the already released operator-matching
package. No scientific outcome or released artifact is changed by this repair.

- Its `operator_matching_release_v1` manifest maps paths to SHA-256 values,
  rather than listing path/size/hash objects. The auditor now accepts that
  format only at the exact released manifest path and schema, requires the
  declared file count and directory, and checks every listed hash against the
  Git index. Unknown map manifests remain rejected. This source format binds
  bytes by hash; it does not independently declare each file's byte count.
- The included upstream Llama license has trailing whitespace. Its exact path
  and SHA-256 are allowlisted for whitespace checking only, so the legal text
  remains byte-identical. Changed bytes lose the exemption; secret, path and
  manifest checks still apply. Other whitespace errors remain failures.

The first combined full audit scanned 21,943 indexed files, 4,332,399,944
bytes, and reported precisely those two findings. It reported no secret
findings. Focused tests cover changed hashes, missing files, invalid inventory,
unsafe paths, unknown formats, and both staged and unstaged license changes.
The corrected full audit must pass before the integration is committed.

## Historical Reporting Provenance

The complete regression suite then exposed a third compatibility defect.
`release_frontier_b1.py` reconstructed the October 2 release manifest using
the current public auditor's source hash. That equated historical provenance
with an unchanged current reporting environment. After the above auditor
repair, all five frontier tables still reproduced byte-for-byte, but the
historical auditor hash necessarily differed.

Verification now accepts that provenance only for the exact public manifest
SHA-256 `da7468314f3334b93043af854a7890d528d93d8ddd93f0c5d2af76f9560f825b`.
It requires the manifest bytes and both original reporting-tool blobs to match
release commit `4abc13ce9ac832509e7fb4573f6c2aa4e33e0d48`, which must be an
ancestor of the verifying checkout. Current scientific sources, raw receipts,
all file hashes, five rebuilt tables and every other manifest field retain
their existing checks. The current secret scanner still runs. Unknown history,
resealed manifests, changed Git blobs and source-inventory drift fail.

The historical manifest, tool versions, raw outcomes, cost and tables are not
rewritten. This is a post-release verifier correction, not a new experiment
or a relaxed numerical tolerance.

## Fine-Ladder Release

The second operator-matching release, `data/operator_matching/fine_v1_20261003/`,
uses the same path-to-SHA-256 manifest format under its own schema,
`operator_matching_fine_release_v1`, with 132 files. Public `main` at
`2eef34c4` then failed the full audit (22,107 indexed files, 4,344,664,259
bytes) with exactly one finding: that manifest has no files list. The manifest
is now registered at its exact path with that schema and receives the checks
above: declared file count and directory, and every listed hash against the
Git index. A test requires each registered manifest to verify under its own
schema and to reject the other's. The release itself is unchanged. Its
upstream license needs no whitespace exemption: it is already committed, and
the whitespace check covers only uncommitted changes. The corrected full audit
must pass before this repair is committed.
