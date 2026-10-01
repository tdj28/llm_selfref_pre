# Requested Pro Consults

Status on 2026-09-29: **both approved reviews completed and authenticated**.
The owner approved both scoped calls after the revised cost estimate was
presented; see `pro_approval_20260929.md`. Findings have been locally
adjudicated; final local release checks pass. No retry or continuation is authorized.

The proposed calls are a scientific-integrity review of the complete response
and references, followed by a reader review of the corrected manuscript.
Model: `gpt-6-astra`, `reasoning.mode=pro`, medium effort. Maximum two requests,
with no automatic retry. The local scientific and reader reviews are already
complete; they must not be labeled as the requested Pro consults.

## Cost And Data

The shared helper's dry run rejected the initial $1.25 reserve: the complete
packet required $2.5093 conservatively. The superseding approval request is
up to $3 per call, $6 total. This is a preflight reserve, not a provider-enforced
billing cap. Rates checked against [official pricing](https://developers.openai.com/api/docs/pricing):
$10 input, $12.50 cache writes and $50 output per million short-context tokens.

Historical cost reconciliation is partial. Twelve distinct costed response
receipts among fifteen inspected review manifests in the pinned source record
sum to $116.747125 at their recorded conservative rates. Three inspected
manifests lack that completed cost field; other account charges are not
reconciled. This is not a complete project or account total. Session spend on
new Pro generation is $1.64759 ($0.82963 + $0.81796). Including both receipts,
the partial known historical-plus-current sum is $118.394715, still not an
account total. Both approved calls completed once; neither was retried.

## Scientific Call

- Reviewed packet commit: `d2b5e3289e510e11188d5719dcd1cb29f30e29d9`.
- Receipt: `pro_scientific_20260929/review_manifest.json`; full provider response
  and extracted review are preserved beside it.
- Requested and returned model: `gpt-6-astra`, Pro mode, medium effort.
- Input-token counter: 12,348; reserved estimate $1.98915 against $3 approved.
- Returned usage: 46,428 input and 7,307 output tokens; conservative cost
  $0.82963. The aggregate output count exceeds the requested 6,000 maximum;
  this is recorded, not silently truncated or relabeled.
- Provider status: completed. Canonical read-only bundle validation passes.
- Verdict: NOT READY FOR READER REVIEW. Required revisions include source
  attribution, uncertainty sensitivities, treatment-factor disclosure, and
  narrowing the J-lens discussion. See `pro_scientific_adjudication.md`.

## Reader Call

- Reviewed packet commit: `85cc544b46c0122a6bb0b692a521991a666397ab`.
- Complete 19-page PDF text, including appendices and references, with the
  absence of embedded figure pixels disclosed. Exact extract is preserved in
  `packets/reader/`; later edits do not overwrite it.
- Receipt: `pro_reader_20260929/review_manifest.json`; full provider response,
  request payload and extracted review preserved alongside it.
- Requested and returned model: `gpt-6-astra`, Pro mode, medium effort.
- Input counter: 13,852; exact reserve $2.15835 against $3 approved.
- Returned usage: 49,881 input and 6,383 output tokens; conservative cost
  $0.81796. Aggregate output again exceeds the requested 6,000; the receipt
  records the actual usage. Provider status completed; canonical validation passes.
- Verdict: READY AFTER SPECIFIED FIXES, with B-minus overall presentation.
  The opening, rubric definition, claim-adjacent dependence caveat, Gemma
  comparison, figure lead-ins and main-text scope were revised. See
  `pro_reader_adjudication.md`. The final revision was not sent for another
  paid review, and the original verdict/grades are not upgraded.

## Execution Provenance

The shared helper was used without modification at skills-repository commit
`053438a0afddcd10b5000de1cdc227dc5050324b`; script SHA-256
`a6843fc6f7632d5d07adbe2292d7acae9ea5846ca586772ed6fe43c441e10a6a`.
Its path is `../agent-skill-documents/scripts/review_experiment_plan.py` from
the durable companion checkout.

Only the manuscript and compact reference context were submitted.
No raw per-trial data, private annotations, correspondence, credentials or
environment file contents belong in the review packet. The API key is loaded
privately by the shared helper, never included as review material.

Both exact packets and authentic responses remain in this repository. These
are automated consults, not independent human review or human coding.
