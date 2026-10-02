# Llama Instruction/Transcript Qualification

Completed 2026-10-01. The frozen screen stopped at 12 blocks (48 answers).
It found a large instruction effect but failed headroom and context-conflict
guards. No internal intervention followed. See the
[results and limitations](../../../docs/INSTRUCTION_STATE_QUALIFICATION_RESULTS_20261001.md).

- `raw/`: all 101 retrieved worker artifacts, including 72 generations,
  13 rows, plan, token/artifact checks, receipts and the terminal failed gate.
- `judges/`: the four exact append-only API receipt streams, including all
  192 target judgments and 24 synthetic fixture judgments. No credentials.
- `cheap_cuda/`: all six retrieved artifacts from the successful 176-test
  CUDA qualification. The earlier timeout is preserved in the sibling release.
- `analysis/`: the exact runtime decision/case table, derived count tables,
  and two figures in PNG/PDF. Descriptive figures have no population CI claim.
- `LIFECYCLE.json`: explicitly projected owned-pod cleanup/cost receipts;
  unrelated infrastructure and local paths are excluded. New cost bound $9.87.
- `MANIFEST.json`: SHA-256 of every other file in this release.

From the repository root, no GPU or API key is needed:

```bash
python scripts/reproduce_instruction_qualification.py
python scripts/reproduce_instruction_qualification.py \
  --out /tmp/qualification-reproduced --figures
```

Install `requirements-ci.txt` for the plotting/runtime dependencies. The output
directory must not already exist or overlap the release. Verification checks
every artifact hash, reconstructs the terminal raw audit, and reproduces both
runtime analysis files byte-for-byte. Judge locks are created in a temporary
copy, never in this release. Re-rendered PDF metadata can vary by environment;
the count tables and frozen analysis determine the reported values.

This is a prospective engineering screen under fixed prompts and automated
instruments, not human validation, a population-level significance test, or
evidence establishing the nature of any subjective state. The source cap was
hit by 11/12 history continuations and no self-reference continuation; transcript
source therefore does not isolate semantics from length and termination.
