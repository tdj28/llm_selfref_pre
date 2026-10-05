# Gemini/Opus Swap Extension

Gemini's instruction-over-continuation contrast is large under the inclusive
measure. Opus is inconclusive under that primary measure but looks much
stronger under the paper rubric. This package binds those statements to the
completed [public release](https://github.com/tdj28/llm_selfref_pre/tree/0438e6c12e6024da7e4284ec6c396e27c6c1738a/data/openrouter_swap/main_v1_20261004).

`inputs/` holds gzip-compressed, byte-identical selected public inputs:
the plan, final-response rows, original analyses and release metadata. Their
uncompressed hashes must match the pinned release manifest, copied unchanged
as `inputs/source_inventory.json`. This inventory describes the full remote
release, not a claim that every release file is duplicated here. `results.json`
recomputes all cell counts and six paired-block contrasts for both judges
and all three rubrics. Only the primary Astra inclusive contrasts carry
simultaneous confidence bounds; secondary point estimates are not promoted
to confirmatory tests. Screen and main rows remain separate.

From the repository root:

```sh
python scripts/verify_openrouter_swap_extension.py --check
python -m pytest tests/test_openrouter_swap_extension.py
```

The check is offline and read-only. It recomputes the displayed quantities
from released row labels, cross-checks the original analysis, and verifies
the manuscript, figure and source hashes. It does not re-judge responses,
reconstruct API receipts, regenerate bootstrap intervals or supply human
validation. The full source release was separately verified with its own
`experiments.openrouter_swap_release_a3 --verify` command before packaging.

`--write` regenerates only this editorial package and its figure. Importing
from a local release additionally requires `--source-release` and checks
the bytes against the specified local Git commit; it never fetches a model
or makes a network request. Historical releases are never rewritten.
