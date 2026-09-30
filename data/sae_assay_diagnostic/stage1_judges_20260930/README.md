# Stage 1 Baseline Judges

The fixed GPT-6 Astra and Claude Opus 5.5 panel applies the prospectively
frozen construct-separated rubric to the 80 unsteered core responses. This
is automated linguistic coding, not independent human validation or an assay
of consciousness. Explicit and inclusive self-attribution are separate
endpoints; neither is chosen after comparing its outcome.

The 12 authored fixtures per provider are calibration, not target responses.
Astra passed 12/12; Opus passed 11/12, including all five critical cases.
Opus's J07 disagreement about an implicit denial is preserved. Fixture success
permits baseline coding; it does not establish general semantic accuracy.

`requests.jsonl`, `attempts.jsonl`, `judgments.jsonl` and `gates.jsonl` are
byte-exact receipt streams. Raw provider responses remain inside attempts.
`inputs.public.json` is explicitly a projection, not the original input
receipt: it omits the workstation path and the checksum dependent on that
path, while retaining source/input/row hashes and the original stream's
SHA-256. The original path-bearing receipt remains local and ignored.
No response, judgment, usage record or substantive input was redacted.

The portable auditor rebinds only the public input path in memory and replays
the frozen request, model, usage, schema, quote, reduction and fixture checks.
It does not pretend the path projection is the original byte stream. It
requires a complete core panel and never repairs receipts or calls providers.

GPU inputs are in `../stage1_20260930/`; the human-readable results and limits
are in `docs/SAE_ASSAY_STAGE1_RESULTS_20260930.md` at the repository root.
`receipt-audit.json` contains final counts, gate decisions and cost bounds.
`RELEASE_MANIFEST.json` binds the public artifacts.

```bash
python -m experiments.sae_assay_diagnostic.audit_judges \
  --plan data/sae_assay_diagnostic/stage1_plan_20260930a/PLAN.json \
  --freeze 711a0c8e6650e57b75e4d2a6ad76a0c5d4fab9c5 \
  --run data/sae_assay_diagnostic/stage1_20260930 \
  --judges data/sae_assay_diagnostic/stage1_judges_20260930
```
