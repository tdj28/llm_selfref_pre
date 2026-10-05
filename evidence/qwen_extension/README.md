# Qwen3.8 Manuscript Evidence

This package compares scoring rules on the same 256 Qwen3.8-2.4T-A95B answers.
Its figure is a measurement comparison, not a recovery-history plot. Every
judge/rubric point has a pointwise descriptive 95% paired-block bootstrap
interval. Astra inclusive remains the primary endpoint; its simultaneous
four-comparison Hoeffding bounds stay in the prose, including the unrun
Mistral main panel. Qwen3.5 is a separate earlier study.

The inputs are byte-identical, compressed copies of selected public files
from the original incomplete archive and the additive three-label repair.
Both inventories are pinned by SHA-256. The recovery release is bound to
[commit 0eb2e039](https://github.com/tdj28/llm_selfref_pre/tree/0eb2e039ae0807dca9c9df262db18e2d863d428d/data/qwen_judge_recovery/release_v1_20261005).
Import checks the selected bytes against that commit's local Git objects.

Read-only numerical verification:

```sh
python scripts/verify_qwen_extension.py --check
python scripts/verify_qwen_extension.py --check --require-pinned
```

Editorial-only regeneration, after intentional source/prose changes:

```sh
python scripts/verify_qwen_extension.py --write --source-root .
```

The verifier reconstructs cell counts, paired contrasts and both interval types
from released labels, and confirms that the repair changed exactly the three
missing structured judgments. It cross-checks the saved analysis and binds
the manuscript macros, source files and figure bytes. The figure intervals
use the frozen algorithm: Python `random.Random(20261004)`, 10,000 resamples
of paired block differences within wording families a then b, and linearly
interpolated 2.5th/97.5th percentiles. All six are recomputed from row pairs
and checked against the released intervals and their settings. These
pointwise, conditional descriptive intervals are not substitutions for the
primary simultaneous Bonferroni--Hoeffding bounds. The verifier does not repeat
receipt auditing, validate labels against human judgments, modify either
release, or authorize more collection. The separate recovery-release verifier
replays the new receipts and their costs.
