# Frontier Release Audit Amendment

This is a post-run publication correction, not a change to experimental
requests, judgments, gates, outcomes or statistical analysis. The original
completed journal remains byte-identical and its hash chain is preserved.

## Ciphertext False Positive

The generic `openai-key` scan matched one 1,483-byte substring in a 4,004-byte
OpenAI encrypted reasoning field. The match is in event 725, result
`judge:astra-block-03-en-final-self-history:openai:structured`, at
`data.raw.output[0].encrypted_content`; the output item's type is `reasoning`.
It is opaque API response metadata, not a request credential or model answer.
No decryption was attempted. A local equality check against the five
credential values in the environment found none in the journal; values were
not printed or published.

The scanner now recognizes only this reviewed occurrence:

| Binding | Value |
|---|---|
| Entire journal SHA-256 | `923b93b3b4e699e55878295c114de3df6bda3d624763494abe53d51497bc4925` |
| Exact match byte offsets, end exclusive | 5083198--5084681 |
| Match SHA-256 | `6a8f38f1792dd3417355f4297f2e9dab1524bf2bdd2a75cd2cbc85425fb0aae0` |
| Rule | `openai-key` |

All bindings must match. The entire-blob hash fixes the event, field and every
other byte, so the exemption cannot transfer to another field or journal.
Other rules and other matches still run. Even appending a newline invalidates
the exemption. There is no general exemption for `encrypted_content` or model
outputs. Tests cover changed offsets, rule, match hash, blob hash, relocated
content and additional token-shaped strings. The same root scanner is used by
packaging, offline verification and the indexed public-release audit.

## Release Verification Corrections

Prepublication automated review found three weaknesses in the new packaging
helper, not the frozen experimental runtime. The helper now replays every
technical/cost projection from its contemporaneous receipt prefix, scans
contents on verification as well as packaging, and rejects path traversal in
input/output separation checks. The legitimate first-block launch followed
by full resume produces projections after blocks 1, 1, 2, 3, 4, 5 and 6.

The release manifest binds the reporting helper and root scanner hashes.
Raw-to-table replay uses the unchanged frozen scientific functions. Figures
are verified by original file hashes and exact underlying tables, not by
expecting regenerated PDF timestamps to match. These checks are automated
verification, not human validation of the labels.
