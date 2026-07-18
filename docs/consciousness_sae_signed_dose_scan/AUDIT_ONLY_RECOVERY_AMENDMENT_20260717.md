# Signed-dose audit-only recovery amendment

Date: 2026-07-17 UTC
Status: post-outcome mechanical amendment; recovery not yet authorized
Recovery protocol: `consciousness_sae_signed_dose_scan_v1.audit_only_recovery_v1`

## Why this amendment exists

The prospectively frozen 70B collection completed all 2,896 planned model
forwards and atomically finalized its raw run. The frozen independent auditor
then opened and recomputed those raw artifacts but rejected the pinned J-lens
checkpoint because its map inventory was a strict superset of the study's
required layers. The auditor produced no compact audit, summary, or publication
marker. This document was written after that failure was known and cannot turn
the failed audit into a confirmatory result.

The only permitted successor is an audit-only mechanical recovery over the
unchanged, hash-bound raw run. It may change the checkpoint inventory predicate
from “available layers equal 45 through 78” to “available layers contain every
required layer 45 through 78,” then pass those exact 34 checkpoint objects to
the otherwise frozen auditor. It must reject a missing required layer,
duplicate or noncanonical layer key, wrong checkpoint hash/revision/metadata,
or any numeric transform of a selected map.

## Terminal incident record

The self-hashed closure is
`INCIDENT_CLOSURE.json`, receipt
`172ebb2e4ea06160df7d3a3d9e356dfdc0996ffb50019c6bc35a48a724103dd4`.
Its physical file SHA-256 is
`7afe9aa8bae10c2965f40eab92fbbb331a51ad0fd2a0895d6fc55bd0af7cbd3c`.
The independent verifier restates historical constants rather than importing
the producer. Its canonical passing receipt is
`INCIDENT_CLOSURE_VERIFICATION.json`, self-hash
`92c969a06bbd0c776e2f0f31357e04cca749c8244a25e3f4bc871cfd8ff3c2d8`.

| Attempt | Terminal boundary | Outcome-access class | Disposition |
|---|---|---|---|
| Gemma operational v1 | Gated tokenizer resolution failed before model load or any forward | startup not reached | preserved; no scientific authority |
| Gemma operational v2 | All four mechanics gates passed after 122 forwards | operational validation completed | valid only as runner-mechanics promotion evidence |
| 70B scientific v1 | Wrapper could not execute missing `/usr/bin/time`; guest launcher was not reached | startup not reached | one-shot authorization permanently rejected; no raw run |
| 70B scientific v2 | 2,896 forwards completed and raw run finalized; auditor then failed on strict J inventory during raw recomputation | raw inputs opened or recomputed | one-shot authorization permanently rejected; compact publication absent |

The v2 raw ledger contains exactly 35 sorted file records totaling
2,229,288,980 bytes. The canonical records commitment is
`b5c784f4feb87ba01a9fc5d9b2f22d12eee01930d98718cd5c54e3d398692cf4`;
the `RUN_COMPLETE.json` physical SHA-256 is
`a5818ad5e208c9008df6ad0bede630fddafb06e07b5f0190d02b3b80ceefeb4b`,
and its self-receipt is
`f714f16e2f6d5bb532d522c3ad0e2985e6f6b169ff5875911d296f42cd8fdc7d`.
The closure embeds this metadata-only ledger, not raw rows or tensors. The raw
bytes remain on the retained RunPod network volume and must not be committed to
Git or copied onto a space-constrained workstation.

The owned B200 pod `wl8obvtuq0ax8t` was terminated exactly. The termination
audit status is
`deleted_exact_owned_pod_unrelated_inventory_unchanged`; the post-delete
account pod count is zero and the empty-inventory commitment is
`4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945`.
That pod, both prior authorizations, and both prior run namespaces are rejected
for all successor work.

## Scientific invariants

The recovery must leave all of the following byte- or decision-identical:

- the frozen plan and protocol;
- the eight prompts, three generic directions, signed half-point dose grid,
  exact zero construction, and execution ordering;
- all 35 raw-file paths, byte counts, hashes, and bytes;
- requested/native/realized tensors and every completed model forward;
- endpoints, thresholds, eligibility rules, summaries, and claim policy; and
- the frozen auditor except for the single J-checkpoint inventory predicate and
  required-map filter described above.

The recovery must load no model and run no model forward. Its zero-forward guard
must report both Torch module calls and Transformers model-load calls as zero.
It must read the pinned checkpoint with SHA-256
`335056c17f0c24053c8c8c1eff168ef49e5a62ca590ffc29c84cf352ecd3ab03`,
verify metadata `n_prompts=125` and `d_model=8192`, record available layers
0–78, required layers 45–78, and unused extra layers 0–44, and pass the original
objects for the required 34 maps without a numeric transform.

A successful recovery writes only a fresh atomic compact directory containing
`CALIBRATION_AUDIT.json`, `CALIBRATION_SUMMARY.json`, and
`PUBLICATION_COMPLETE.json`, plus its separately preserved attempt and
authorization receipts. It must never write into the original raw directory.
Its terminal recovery receipt status is
`pass_audit_only_recovery_with_immutable_raw`. That status would establish that
the corrected audit completed; it would not erase either failed attempt or make
the original audit pass retroactively.

## One bounded recovery cycle

`RECOVERY_CYCLE_LEDGER.json` freezes receipt
`72f2d473c68698a24160523265a9786b9382a14432e418d24a2f6596f910314b`.
It permits at most one integrated local closure pass, one target-qualification
attempt, one paid cumulative review call, and one audit-only recovery attempt.
There is no automatic or provider-capacity retry. The deadline is
2026-07-17T08:00:00Z. The additional cycle cap is $12.00 within the user's
overall $50 ceiling: $3.00/1,800 seconds for qualification, $1.25 for review,
$6.00/3,600 seconds for recovery, and a $1.75 non-execution reserve.

The paid cumulative review and the scientific recovery are currently marked
unauthorized. A review requires explicit human approval. The incident closure,
this amendment, a passing local suite, or a passing target qualification cannot
individually grant launch authority. When every frozen gate is green, the only
allowed terminal action is one immediate audit-only recovery; any red gate,
new review blocker, exhausted count, missed deadline, or failed recovery means
stop and report. Another cycle requires a new human-approved amendment written
before further work.

The audited provider lifecycle retains its broader six-hour/$36 emergency
termination envelope. That is not qualification spend authority. The one-shot
qualification must bind an independent creation-aware 1,800-second/$3 watchdog,
prove that its actual metered elapsed time and conservative cost stayed within
those smaller limits, terminate the exact owned pod immediately, and freeze the
provider's direct-404 plus unchanged-account-inventory receipts before E. The
later recovery has its separate one-hour/$6 authorization and must use a
different fresh pod.

The machine ledger's closure table has one row for each past failure boundary
and the exact skill-required columns: production command, target-platform
rehearsal, negative regression, independent-verifier rule, receipt field, and
launch-gate check. Empty cells are rejected by the offline verifier.

## Verification

No raw outcome is needed to verify the incident record:

```bash
PYTHONPATH=. python3 -B -m \
  experiments.consciousness_sae_signed_dose_scan.verify_incident_closure \
  --closure docs/consciousness_sae_signed_dose_scan/INCIDENT_CLOSURE.json \
  --schema docs/consciousness_sae_signed_dose_scan/INCIDENT_CLOSURE_SCHEMA.json \
  --recovery-ledger \
    docs/consciousness_sae_signed_dose_scan/RECOVERY_CYCLE_LEDGER.json
```

The verifier fails closed on missing or extra fields, a broken self-hash,
historically false attempt classification, changed wrapper or evidence hash,
changed freeze/review/resource identity, altered raw record even after every
dependent hash is recomputed, changed termination state, expanded recovery
scope, increased cost/count/deadline, or a silently authorized paid review.

## Claim boundary

Permitted now: the small-model mechanics gate passed; the 70B runtime completed
the prospectively planned forward inventory and finalized a hash-bound raw run;
the frozen audit failed after opening/recomputing raw on an inventory predicate;
no compact result was published; and the raw run awaits a separately authorized
audit-only recovery.

Forbidden now: any statement that the 70B audit passed; any scientific endpoint,
semantic, consciousness, SAE, or J-lens result from this run; any implication
that absence of compact publication means no outcome access; or any silent reuse
of the old authorization, pod, attempt marker, output namespace, or failed audit.
