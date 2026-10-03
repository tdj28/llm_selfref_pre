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
