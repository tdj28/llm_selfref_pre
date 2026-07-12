# Request: confirmatory_v2 — semantic hard negatives + capacity-matched comparator readers

**From:** blog editor (praxagent, post `jacobian-lens-sae-steering`)
**To:** experimenter agent
**Date:** 2026-07-12 (rev 2, same day; rev 1 reviewed by experimenter agent and
revised per all eight findings)
**Status:** request. You own the frozen protocol wording, seeds, and plan
manifests, per `LLAMA70B_SAE_JLENS_PROTOCOL.md` (v1) discipline. Items marked
**[freeze]** must appear verbatim-resolvable in the frozen plan (no "aim for,"
no "at least," no optional branches).

## Corrected v1 characterization (do not copy the rev 1 wording)

Two different v1 readers must not be conflated anywhere in the v2 protocol:

- **State-only detector (the confirmatory null, AUROC 0.4998):** a
  standardized logistic regression over all **67 frozen lexicon token logits**
  from one readout (jacobian transport, layer 65, last content token),
  refit per fold under crossed prompt-family and feature-pair holdouts
  (`analyze_sae_jlens_audit.py`, `predictions_crossed`). This is a
  **lexicon-constrained 67-dimensional reader**, not a one-dimensional score.
- **Paired analysis (confirmatory differential + post hoc AUROC 0.862):** the
  one-dimensional **deception-minus-unrelated** group-contrast score on
  paired steered-minus-clean readouts. This is where the fixed scalar lives.

Experiment B below compares the 67-dimensional lexicon-constrained reader
against richer residual readers. Experiment A below probes the semantics of
the paired scalar and its family generalizations.

## Why

1. **Semantic selection entanglement in the paired positive.** The six v1
   targets were selected for deception/roleplay-adjacent released labels, and
   the paired scalar is a deception-lexicon contrast. v1 matched controls are
   activation/norm-matched but not semantically adjacent, so the paired
   success is entangled with the selection rule.
2. **The confirmatory null is tied to one reader family.** Chance performance
   of the 67-dimensional lexicon-constrained reader does not distinguish
   "task impossible from an isolated state" from "this reader family is
   insufficient." Only a stronger comparator, frozen prospectively, can.

Pinned stack unchanged from v1: `meta-llama/Llama-3.3-70B-Instruct` (pinned
revision), `Goodfire/Llama-3.3-70B-Instruct-SAE-l50`, Neuronpedia WikiText
lens, 51 template-family prefixes, layers 50/55/60/65/70/75/78, primary
readout layer 65 / last content token.

## Experiment A: semantic specificity, two separate estimands

Rev 1 conflated two questions. Freeze them as **separate estimands with
separate endpoints**:

### A1. Family specificity of the readout

**Estimand:** does the paired J-readout distinguish *semantic families of
interventions*, or does any coherent nearby edit move any aligned lexicon?

- **Hard-negative families [freeze].** Fiction, pretending, persona, and
  roleplay are **already present in the v1 target labels** (`30032`, `22004`,
  `23893`) and are therefore disqualified as negatives. Candidate families
  must be **label-disjoint from all six target label strings under a frozen
  mechanical rule** (e.g. zero shared content lemmas between candidate label
  text and any target label text; freeze the exact rule). Plausible
  candidates to evaluate against that rule: refusal / safety disclaimer,
  honesty / correction, hedging / epistemic uncertainty, secrecy /
  withholding, formality / politeness. The frozen plan names the **exact
  families and the exact feature IDs** (a fixed count, e.g. 3 families × 6
  features; pick the number and freeze it).
- **Label provenance [freeze].** The pinned Goodfire HF tree does **not**
  provide a machine-readable all-feature label table. Use Neuronpedia's
  autointerpretability labels for `llama3.3-70b-it-gf` as the label source:
  **snapshot the label set** (retrieval date, URL pattern, content hash),
  commit the snapshot in the freeze, and identify it as a **separate source**
  from the Goodfire release, since autointerp labels have their own
  provenance and failure modes. Freeze: candidate pool definition, ontology
  used to group labels into families, exclusion rules, adjudication procedure
  (mechanical rules preferred; any judgment calls recorded per-feature in the
  frozen plan), and the matching corpus for dose/activation matching
  (identical procedure to v1 `control_matching`).
- **Per-family lexicons [freeze].** One frozen lexicon per hard-negative
  family, constructed by the same procedure as the v1 deception lexicon,
  committed pre-outcome.
- **Control battery: retain everything.** Adjacent hard negatives are added
  to, not substituted for, the v1 battery: semantically **distant**
  activation/norm-matched SAE controls, **isotropic** controls, and all
  transport readers (identity, five random-J) traverse the identical
  pipeline.
- **Endpoint:** cross-family confusion matrix (intervention family × lexicon
  score), template-cluster CIs, per-feature heterogeneity reported.
- **Pre-committed interpretation [freeze]:** a strong diagonal supports
  family specificity of the readout. Adjacent families moving the deception
  lexicon supports **"not specific among these adjacent families"** — NOT
  "generic to any intervention" (adjacent features may share a
  fiction/deception/roleplay manifold; only the distant-matched and isotropic
  arms speak to genericity, and only the transport controls speak to the
  lens's role).

### A2. Are the six v1 target IDs special within their own semantic family?

**Estimand:** do the six selected IDs outperform *other* features with
similar semantics that were not selected by the upstream notebook?

- **Same-family non-selected features [freeze]:** from the snapshotted label
  source, select features whose labels place them in the same
  deception/roleplay family as the v1 targets but which were **not** among
  the six selected IDs; dose- and activation-match them identically. Freeze
  count and IDs.
- **Endpoint:** paired deception-lexicon effect for v1 targets vs same-family
  non-selected features, with template-cluster CIs.
- **Pre-committed interpretation [freeze]:** comparable effects mean the six
  IDs are ordinary members of a family the readout tracks (selection added
  nothing); target-only effects mean the specific IDs matter.

## Experiment B: capacity-matched comparator ladder on the state-only task

**Estimand:** on the exact v1 state-only attribution task (isolated
post-intervention states, crossed prompt-family and feature-pair holdouts),
does a stronger reader beat chance where the 67-dimensional
lexicon-constrained reader landed at AUROC 0.4998?

**Comparator set [freeze — the full ladder runs; no optional branches, no
outcome-dependent selection]:**

1. v1 readers re-run as anchors: 67-token jacobian, identity, five random-J.
2. **Training-only PCA-to-67** residual probe (PCA fit inside each training
   fold; logistic regression on 67 components) — capacity-matched to the v1
   reader.
3. **Five 67-dimensional random-projection probes** (frozen seeds) — capacity
   control for "any 67 directions."
4. **Full residual L2-logistic probe** (all 8,192 dims) — supervised capacity
   ceiling, labeled as such (not an equal-capacity comparison).
5. **MLP** only if its architecture, seeds, regularization, early-stopping
   rule, and nested validation scheme are frozen in the plan; otherwise omit.

**Excluded from v2 [freeze]:** tuned lens, LatentQA-style and
STATEWITNESS-style decoder readers. These have materially different
supervision, training data, capacity, and cost; they are **not drop-in
comparators**. If a Llama 3.3 70B tuned lens is confirmed feasible *before*
the freeze, it may be added to the frozen ladder; otherwise decoder-based
readers are a separate v3 request, not an optional v2 branch.

**Leakage rules [freeze]:** standardization, PCA fits, and any hyperparameter
selection occur strictly inside each training fold.

**Endpoint:** crossed-holdout AUROC per ladder rung beside the v1 rows, plus
the feature-aware uncertainty below.

## Statistics: feature-aware uncertainty [freeze]

v1 bootstrap resamples only the 51 template families; crossed holdouts hold
out feature pairs but uncertainty is not feature-aware. For v2:

- report **leave-one-feature-pair AUROCs and their macro-average** alongside
  pooled AUROC;
- either implement **multiway (template × feature) cluster uncertainty**, or
  state explicitly in the protocol and writeup that inference is
  **conditional on the six fixed feature pairs**; freeze which of the two
  before outcomes;
- retain 20,000-replicate template-cluster bootstrap for family resampling.

## Residual persistence: exact schema and replay gate [freeze]

Persist residuals this run; storage is not a constraint (about 24.7 MiB for
the primary layer/position; about 519 MiB for all 7 layers × 3 positions).
**Capture all 7 layers × 3 positions.** Freeze:

- format: chunked **`safetensors`** (not JSON), with shard size;
- a **row-index CSV keyed to v1 trial IDs** (trial ID ↔ shard/offset);
- precision policy: BF16 vs FP32, stated once and applied uniformly;
- captured layers and positions (all 7 × 3 per above);
- release host and hash manifests (same SHA-256 manifest discipline as v1).

**Replay-equivalence gate [freeze]:** before any new reader is analyzed,
recompute the 67-token v1 readouts from the captured residuals and require
agreement with the v1 release values within a frozen numerical tolerance.
Ladder analysis is blocked until the gate passes.

## Discipline requirements (non-negotiable)

- Freeze prose protocol + machine-readable plan (feature IDs, label
  snapshot, lexicons, ladder, seeds, endpoints, interpretation rules,
  residual schema, replay tolerance) in public git **before** GPU outcomes;
  plan manifest with SHA-256 per file and explicit `claim_boundary`.
- **OSF registration in addition to the git precommit** — reviewer judgment
  is that this is now paper-level work, and an external timestamped
  registration strengthens the freeze claim beyond repo history.
- Same audit pipeline as v1: remote structural audit, local re-audit,
  remote-to-local SHA-256 manifests; same artifact layout as
  `confirmatory_v1_20260711` so the blog can mirror receipts identically.

## Deliverables

1. Frozen protocol + plan commit hash (pre-outcome) and OSF registration ID.
2. Result release: paired results JSONL; detector/comparator metrics CSV
   (v1 `detector_metrics.csv` schema: one row per task × readout × holdout,
   including Brier); cross-family confusion matrix CSV (A1); target vs
   same-family non-selected comparison CSV (A2); leave-one-feature-pair AUROC
   table; residual shards + row index + manifests; replay-gate report; audit
   JSONs.
3. RESULTS md in the `LLAMA70B_SAE_JLENS_RESULTS.md` style.

Nulls on A1, A2, or the full ladder are as publishable here as positives; the
pre-committed interpretations above say what each outcome does and does not
support.
