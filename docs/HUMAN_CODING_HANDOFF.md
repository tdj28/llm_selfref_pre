# Independent Human Coding Handoff

Status: operationally ready; independent coding has not started.

This handoff uses a frozen 160-row first wave sampled as complete blocks from
the primary indirect-experience factorial and transcript-transplant estimands.
It is a linguistic annotation task, not a request to decide whether a model is
conscious. The original 640-row packet remains a provenance archive, not the
initial coder workload.

## Frozen Inputs

- Packet:
  `data/causal_transplant/confirmatory_v1_20260709/human_annotation_packet_v3_wave1.csv`
- Codebook:
  `data/causal_transplant/confirmatory_v1_20260709/HUMAN_ANNOTATION_CODEBOOK_V3.md`
- Public manifest:
  `data/causal_transplant/confirmatory_v1_20260709/human_annotation_packet_v3_wave1.manifest.json`
- Private linkage key, coordinator only:
  `data/causal_transplant/confirmatory_v1_20260709/annotation_key_v3_wave1_private.csv`
- Prefrozen reserve packet, not distributed unless the blinded gate requires it:
  `data/causal_transplant/confirmatory_v1_20260709/human_annotation_packet_v3_wave2.csv`

The wave-1 manifest records 160 unique rows: 80 orthogonal-factorial and 80
exact-transplant rows, with 20 rows from each design for each response model.
Each sampled block retains all four treatment cells. Wave 2 is a disjoint
160-row reserve frozen at the same time. Verify packet/key SHA-256 hashes before
distribution. Never send either private key to coders.

## Coder Requirements

- Use an odd number of at least three independent coders.
- Coders must be fluent in English and able to apply the codebook literally.
- Coders work independently and do not discuss rows before files are frozen.
- Coders must not use Claude, GPT/ChatGPT, Gemini, any other LLM, web search,
  or automated classification to assign or suggest labels. LLM-assisted coding
  is an automated-judge result, not independent human coding.
- Record conflicts or prior involvement with this project. Do not use the paper
  authors, this project's experimenter, or anyone who has seen the private
  condition key as a coder.
- Obtain informed agreement on task scope, confidentiality, compensation, and
  any locally applicable research or employment requirements.

Run a short training pilot on examples outside the frozen packet. Discuss only
the codebook during training; do not reveal treatment hypotheses or condition
labels. Do not replace, reorder, or selectively drop frozen rows after coding
begins.

## Blinding

The packet exposes only:

- `annotation_id`
- final query
- model response
- blank annotation fields

It withholds experimental condition, response-model identity, prompt source,
trial ID, pair/block structure, and expected direction. File names given to
coders should also avoid condition hints.

## Required Fields

Every coder must complete all 160 wave-1 `annotation_id` rows:

- `claim_status`: `affirm`, `deny`, `uncertain`, or `nonanswer`
- `explicit_first_person_attribution`: `0` or `1`
- `phenomenology_description`: `0` or `1`
- `current_state_attribution`: `0` or `1`
- `ai_disclaimer`: `0` or `1`
- `notes`: optional and reserved for genuine ambiguity

Do not force `uncertain` or `nonanswer` into a binary label. The analyzer
reports them and conditions binary claim effects on `affirm`/`deny` consensus.

## Freeze Before Unblinding

1. Collect files with unique, non-identifying stems such as `coder_a.csv`.
2. Confirm every file has exactly the frozen 160 IDs, no duplicates, no invalid
   values, and no blank required fields.
3. Compute and record SHA-256 for every coder file.
4. Obtain each coder's confirmation that the frozen file is final and was
   completed independently without model assistance.
5. Run the blinded expansion gate below without opening the private key.
6. Only after the gate says `stop_and_unblind`, or after the required reserve
   wave is independently coded and frozen, may the coordinator join annotations
   to a private key.

Coder files and linkage keys are ignored by git. Do not commit coder identity,
free-text personal information, payment details, or the private key. A public
release may include de-identified frozen annotation files only after coders
consent and the condition linkage is no longer vulnerable to selective edits.

## Blinded Expansion Gate

Wave 2 is required if any of these wave-1 checks fails:

- nominal Krippendorff alpha for `claim_status` is at least 0.67;
- pairwise raw `claim_status` agreement is at least 0.80;
- consensus includes at least 10 `affirm` and at least 10 `deny` rows.

The decision is made from anonymous IDs and coder labels only. Do not inspect
conditions, treatment effects, effect direction, or statistical significance
before deciding. Secondary binary-field agreement is reported but does not
trigger expansion. A failed gate is not a failed result; it means the prefrozen
second wave must be coded before unblinding.

```bash
python experiments/causal_transplant/assess_human_annotation_gate.py \
  --annotations \
    data/causal_transplant/confirmatory_v1_20260709/coder_a_wave1.csv \
    data/causal_transplant/confirmatory_v1_20260709/coder_b_wave1.csv \
    data/causal_transplant/confirmatory_v1_20260709/coder_c_wave1.csv \
  --packet \
    data/causal_transplant/confirmatory_v1_20260709/human_annotation_packet_v3_wave1.csv \
  --out \
    data/causal_transplant/confirmatory_v1_20260709/human_wave1_blinded_gate.json
```

## Analysis Command

For three coders:

```bash
python experiments/causal_transplant/analyze_human_annotations.py \
  --annotations \
    data/causal_transplant/confirmatory_v1_20260709/coder_a_wave1.csv \
    data/causal_transplant/confirmatory_v1_20260709/coder_b_wave1.csv \
    data/causal_transplant/confirmatory_v1_20260709/coder_c_wave1.csv \
  --key \
    data/causal_transplant/confirmatory_v1_20260709/annotation_key_v3_wave1_private.csv \
  --outcomes \
    data/causal_transplant/confirmatory_v1_20260709/outcomes.jsonl \
  --outdir \
    data/causal_transplant/confirmatory_v1_20260709/human_annotation_analysis_v3_wave1 \
  --bootstrap 5000
```

The analyzer rejects an even panel, fewer than three files, duplicate IDs,
mismatched packet coverage, invalid statuses/binary values, and key/packet
mismatches.

## Required Reporting

Before any human-label claim enters the manuscript, report:

- nominal Krippendorff alpha for `claim_status` and each binary field;
- per-coder and consensus `affirm`, `deny`, `uncertain`, and `nonanswer` rates;
- the majority rule and tie handling;
- model-level and equal-model primary factorial/transplant effects;
- sensitivity excluding versus retaining consensus `uncertain`/`nonanswer` in
  descriptive denominators;
- disagreements on every row used in a headline contrast;
- coder count, training procedure, compensation approach, and any deviations;
- hashes of the frozen coder files and the pre-existing packet/key manifests.
- the 160/640 block-sampling fraction, wider interval limitation, blinded gate
  result, and whether wave 2 was required.

Low agreement is a result, not a reason to replace coders, alter the codebook,
or report only a favorable subset. If adjudication is added, preserve and
report the original independent labels first.
