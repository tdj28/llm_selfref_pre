# Verdict

The narrow scientific recovery remains defensible. The physically hash-pinned J checkpoint may contain unused maps without changing the study computation; requiring layers 45–78, selecting exactly those maps, preserving the frozen downstream J metadata shape, and recording extras only in recovery provenance is the smallest correction consistent with the cited original runtime. The supplied source also preserves the original audit entry point and separates historical model-transaction provenance from fresh recovery-compute provenance.

The packet is unusually strong on the following points:

- the original and recovery campaign clocks are semantically separate;
- the J loader preserves selected-map identity and the downstream `sha256`/`map_count=34`/`revision` contract;
- the direct `-B -E -s -S` launcher/bootstrap closes the previous pre-guard startup gap;
- authorization is consumed by the exclusive post-confinement Landlock receipt even before the attempt marker;
- the ABI-4 masks, output rules, `/proc/self/task` rule, and exact NVIDIA-device rules are explicit;
- inherited descriptors, shared file-backed mappings, import roots, environment, source lineage, target-host qualification, and offline-verifier semantics are extensively fail-closed;
- raw and provenance claims are correctly limited to process-tree handled-write confinement plus pre/post endpoint equality rather than continuous external immutability;
- the statistical claim remains an eight-prompt fixed-panel stability claim, not a population inference; and
- no new model transaction, prompt rendering, target feature extraction, or scientific outcome inspection is proposed.

The exact-byte repairs for **B06, B07, B08, B09, I04, and most of I07** are materially present in the supplied packet:

- **B06:** the loader tests now preserve the three-field metadata record and inspect `_OBSERVED_J_INVENTORY`; the target receipt reports the relevant loader and equivalence tests as passed.
- **B07:** `_terminal_review_verdict` parses one exact terminal line, and tests cover negative, conditional, duplicate, and misleading-prose cases.
- **B08/I04:** canonical local and target-host receipts, qualification support receipts, authorization fields, source/test inventories, physical hashes, self-hashes, command records, node IDs, and offline validation are implemented.
- **B09:** producer and verifier now use the same `$25.00` completed-review ceiling, with an exact-boundary test. This differs from the v2 reviewer’s suggested `$17.00` minimum repair but resolves the actual producer/verifier contradiction and is explicitly disclosed as a superseding budget decision.
- **I07:** host-age, probe-completion, and test timings are recorded, but those exact values reveal rather than resolve a feasibility problem: the qualification CUDA preflight completed 3,617 seconds after pod creation and the target suite completed at 3,648 seconds, both beyond the proposed 3,600-second recovery authority.

Two new blockers remain. First, the only supplied target-host timing demonstration misses the recovery window before authorization could even be issued, so the packet does not establish that the mandatory staging, dependency setup, full 156 GB artifact rehash, manifest construction, Landlock/CUDA preflight, authorization, audit, double endpoint rehash, and publication can fit the one-shot clock. Second, the plan’s paragraph labeled “The precise claim” omits the `/proc/self/task` mutation exception even though the actual policy and other disclosures include it. That local contradiction allows the success claim to be quoted more strongly than the enforced policy supports.

The supplied bytes should therefore not be frozen or used to authorize the recovery. Neither blocker requires scientific outcomes or a fresh model transaction. Both have small, decisive repairs, but those repairs change the reviewed packet or its bound evidence and consequently require another exact-byte review under the packet’s own rules.

**NOT READY TO FREEZE**

# Blocking findings

## Disposition of existing blocking findings

### B01 — Historical whole-audit equivalence gap

- **Severity:** Historical blocker; resolved for the recovery-equivalence claim, subject to preserving the current scientific boundary.
- **Plan section or excerpt:** “The outcome-blind `AUDIT_RECOVERY_SCIENTIFIC_EQUIVALENCE.{json,md}` appendix mechanically binds the frozen plan/source bytes…”; `scientific_equivalence.py` defines an affirmative scientific-field projection and inspects the recovery adapter surface.
- **Why it matters:** A post-run loader correction is admissible only if it does not silently alter hook semantics, tokenization, selected positions, Jacobian orientation, readout arithmetic, row inclusion, bootstrap logic, thresholds, or claim gates.
- **Concrete minimum fix:** None to the scientific design. Preserve the frozen `audit.audit` entry point, the named monkeypatch surface, the affirmative projection, the selected-map comparison, and the exact frozen source hashes. Regenerate and bind the machine appendix after any packet change.
- **Claim affected:** Scientific equivalence of the recovered audit to the frozen r3 audit except for the required-subset compatibility predicate.
- **Disposition:** **Resolved.** Evidence in this packet includes the unchanged frozen audit hash, the extractor and focused tests, the target-host pass for the equivalence tests, and the explicit fixed-panel measurement contract. This establishes recovery equivalence; it does not newly validate the inherited experiment’s substantive adequacy.

### B02 — Historical pre-guard startup-code gap

- **Severity:** Historical blocker; resolved.
- **Plan section or excerpt:** “`python -B -E -s -S /absolute/path/to/landlock_launcher.py`”; `confined_bootstrap.py` validates startup state and installs `_ProcessGuards` before importing the recovery module.
- **Why it matters:** A package-module restart or normal `site` initialization could execute `.pth`, `sitecustomize`, package initializers, or project/ML imports before the import and zero-forward guards.
- **Concrete minimum fix:** None. Retain direct-script invocation, `-B -E -s -S`, forbidden startup-environment checks, complete import-root inventories, `sys.path` replacement, and same-PID `execve`.
- **Claim affected:** Deterministic executable closure, startup leakage prevention, and scoped zero-forward evidence.
- **Disposition:** **Resolved.** The exact source implements the direct no-site bootstrap, and the supplied target-host receipt reports the launcher/bootstrap tests and live same-PID Landlock test as passed without skips.

### B03 — Historical campaign-clock semantic overwrite

- **Severity:** Historical blocker; resolved.
- **Plan section or excerpt:** “The recovered audit preserves the original top-level `campaign_started_at_unix`, `campaign_deadline_at_unix`, and `hourly_price_usd` fields… Fresh authority is recorded only under a distinct `recovery_execution_campaign` object.”
- **Why it matters:** Reusing or rewriting the old fields would make historical execution authority appear to authorize the recovery, or make the fresh recovery clock appear to describe the original model transaction.
- **Concrete minimum fix:** None. Keep the historical constants, `original_execution_campaign`, `recovery_execution_campaign`, and `recovery_deadline_at_unix` publication field unchanged.
- **Claim affected:** Temporal provenance and interpretation of original versus recovery authority.
- **Disposition:** **Resolved.** `_enrich_outputs`, `_publish_recovery_pair_atomic`, focused tests, and the offline verifier enforce the separation.

### B04 — Historical subset-versus-whitelist contradiction

- **Severity:** Historical blocker; resolved.
- **Plan section or excerpt:** `_load_j_checkpoint_recovery` applies:
  ```python
  if not set(required) <= set(available):
      raise audit.CalibrationAuditError("J-lens map inventory differs")
  ```
  and then filters to `protocol.J_LAYERS`.
- **Why it matters:** An exact `0..78` whitelist would contradict the intended required-subset correction. Conversely, exposing all 79 maps downstream could alter scientific metadata or calculations.
- **Concrete minimum fix:** None. Preserve canonical key normalization, duplicate rejection, required-layer inclusion, exact filtering to layers 45–78, and separate recovery provenance for extras.
- **Claim affected:** Narrowness and correctness of the J-checkpoint compatibility correction.
- **Disposition:** **Resolved.** The loader accepts any physically hash-pinned inventory containing the required layers, rejects missing or noncanonical layers, and returns the frozen three-field downstream metadata shape.

### B06 — Loader tests contradicted the preserved return schema

- **Severity:** Historical blocker; fixed in the exact supplied source/test bytes.
- **Plan section or excerpt:** The current tests assert:
  ```python
  assert record == {
      "sha256": protocol.J_LENS_SPEC["sha256"],
      "map_count": len(required),
      "revision": protocol.J_LENS_SPEC["revision"],
  }
  ```
  and inspect full inventory through `_OBSERVED_J_INVENTORY`.
- **Why it matters:** The previous tests would either fail or pressure a future repair to contaminate `artifact_recomputation.j_lens` with recovery-only fields.
- **Concrete minimum fix:** None. Do not move available/required/extra inventory fields back into the downstream metadata record.
- **Claim affected:** Test validity and byte-equivalence of scientific output fields.
- **Disposition:** **Fixed.** Exact-byte evidence is internally consistent:
  - `audit_recovery.py` is reported as SHA-256 `b9ffe8a83de2bfdf88966ded5ffe46b2d8ffd9455652060430fdc3c2d3b20f1a`;
  - `test_audit_recovery.py` is reported as SHA-256 `7c3ea90ac1abb3ef7acde0551ae39143e0d7de24e70b1d2fd21fbe657d0a95bc`;
  - both test receipts bind those bytes; and
  - the target-host receipt reports all affected loader tests as passed. The local macOS skips are disclosed and are not used as the target-host proof.

### B07 — Negative provider verdict could pass a substring readiness check

- **Severity:** Historical blocker; fixed in the exact supplied source/test bytes.
- **Plan section or excerpt:** `_terminal_review_verdict` now requires exactly one `# Verdict` section, one recognized terminal verdict, and requires that verdict to be the final nonempty line in the section.
- **Why it matters:** `NOT READY TO FREEZE` contains the substring `READY TO FREEZE`; substring matching would permit a negative review to authorize execution.
- **Concrete minimum fix:** None. Preserve the exact parser and keep the structured adjudication as an independent second gate.
- **Claim affected:** Review closure, authorization legitimacy, and frozen-decision integrity.
- **Disposition:** **Fixed.** The exact tests cover:
  - `NOT READY TO FREEZE`;
  - `READY AFTER SPECIFIED FIXES`;
  - `READY TO FREEZE`;
  - misleading positive prose; and
  - duplicate negative/positive terminal lines.
  
  The target-host receipt reports these cases as passed.

### B08 — Test receipts were not representable in authorization or offline verification

- **Severity:** Historical blocker; fixed in the exact supplied source/test/receipt bytes.
- **Plan section or excerpt:** `LOCAL_TEST_RECEIPT.json`, `TARGET_HOST_TEST_RECEIPT.json`, and the three target qualification receipts are now included in `_CONFINED_EVIDENCE_ARGUMENTS`, execution paths, `external_files`, authorization, review snapshots, recovery metadata, and offline verification.
- **Why it matters:** Source hashes alone do not prove that the exact tests ran. The previous producer could not enforce the plan’s test prerequisite, and the verifier could not independently check it.
- **Concrete minimum fix:** None to the receipt schema. Preserve:
  - exact source/test inventories;
  - code-freeze commits;
  - commands and argv hashes;
  - interpreter/platform/dependency inventories;
  - collected, passed, failed, skipped, and not-run IDs;
  - target pod/kernel/Landlock/GPU data;
  - qualification support-receipt physical and self-hashes; and
  - the requirement that the designated live Landlock test pass rather than skip.
- **Claim affected:** Deterministic execution, test provenance, target-host compatibility, and offline reproducibility.
- **Disposition:** **Fixed.** The supplied local and target receipts identify the same code-freeze commit and source/test inventory. The target receipt reports 178 collected and 178 passed tests, zero failures, zero skips, and zero not-run tests, and binds the disposable qualification pod and support receipts. The producer and verifier both validate the chain.

### B09 — Producer and verifier used different completed-review cost ceilings

- **Severity:** Historical blocker; fixed by a disclosed superseding boundary.
- **Plan section or excerpt:** `audit_recovery.py` sets `PRO_REVIEW_BUDGET_AUTHORIZATION_USD = 25.0`; `recovery_bundle_verifier.py` sets `COMPLETED_REVIEW_COST_CEILING_USD = 25.0`.
- **Why it matters:** Different limits could create a producer-valid but permanently verifier-invalid one-shot result.
- **Concrete minimum fix:** None, provided both constants remain exactly aligned and the completed review stays within the common boundary.
- **Claim affected:** Budget consistency and offline admissibility of a one-shot success bundle.
- **Disposition:** **Fixed.** The exact boundary test asserts equality of the producer and verifier constants and tests acceptance at the verifier boundary. The move from the v2 reviewer’s suggested `$17.00` to `$25.00` is a prospective, disclosed budget-policy change, not a remaining producer/verifier contradiction.

## New blocking findings

### B10 — The only target-host timing evidence misses the one-hour recovery authority before authorization

- **Severity:** Blocking; definite feasibility conflict in the supplied evidence, although it does not prove that every fresh pod would be equally slow.
- **Plan section or excerpt:** The plan requires:
  > “an exact 60-minute, $6.00 provider-creation-bound ceiling”
  
  and:
  > “an authorization-issuance gate requiring at least 30 minutes to remain in that envelope after staging, pinned dependency setup, the full public-cache rehash, and the Landlock/CUDA probe.”
  
  The target receipt records:
  - `cuda_preflight_completed_host_age_seconds: 3617`;
  - `test_started_host_age_seconds: 3642.0`; and
  - `test_completed_host_age_seconds: 3648.0`.
- **Why it matters:** Under the exact recovery clock, authorization must be issued no later than host age 1,800 seconds. The supplied qualification probe did not complete until host age 3,617 seconds—17 seconds after the entire one-hour authority would have expired and 1,817 seconds after the latest permissible authorization time. Moreover, that qualification preflight binds only the 26-file source/test closure, while the real recovery also requires the full 156,023,372,845-byte public-artifact rehash and the final recovery closure. The current receipt therefore cannot support the plan’s assertion that the one-shot path is operationally feasible. Running anyway risks paying for a pod that the authorizer must reject before the audit starts.
- **Concrete minimum fix:** Before another freeze, run one outcome-blind timed qualification on a fresh disposable B200 pod using the exact real pre-authorization sequence: dependency setup, full public-cache rehash, final import-root manifest construction and rehash, exact-device enumeration, and confined Landlock/CUDA preflight. Require the authorization-ready state by host age 1,800 seconds. If it cannot meet that gate, prospectively lengthen the provider-creation-bound recovery envelope and corresponding spend ceiling rather than weakening or bypassing the gate. No raw scientific outcome or model forward is needed.
- **Claim affected:** Feasibility, one-shot authorization, budget adequacy, and the likelihood of obtaining a publishable/verifier-admissible recovery bundle.
- **Required disposition before freeze:** Replace or supplement the current timing evidence with a successful exact-sequence timing receipt, or revise the clock and budget consistently. Either route changes bound evidence or the plan and therefore requires another exact-byte provider review.

### B11 — The paragraph labeled “The precise claim” omits the authorized `/proc/self/task` write exception

- **Severity:** Blocking; definite claim contradiction.
- **Plan section or excerpt:** The plan says:
  > “The precise claim is that the audit process and descendants can perform handled regular-filesystem content/topology mutations only under the durable output leaf and the separate disposable self-test output leaf, with only the enumerated NVIDIA character-device `WRITE_FILE` exception beyond those two directories.”
  
  But the enforced policy also grants:
  > “`WRITE_FILE|TRUNCATE` (`0x4002`) on `/proc/self/task`”
  
  to all existing procfs descendants under that path-beneath rule.
- **Why it matters:** The sentence expressly labeled “The precise claim” is false as written: NVIDIA devices are not the only mutation exception beyond the two output directories. The `/proc/self/task` exception is disclosed correctly elsewhere and appears in the machine-readable confinement claim, but a later report could quote the narrower “precise claim” and omit it. This creates avoidable post-result reinterpretation of the confinement guarantee.
- **Concrete minimum fix:** Change that sentence only, so it names both exceptions:
  - the exact `/proc/self/task` `WRITE_FILE|TRUNCATE` process-metadata exception; and
  - exact identity-bound NVIDIA character-device `WRITE_FILE` exceptions.
  
  Keep the qualification that device `ioctl` effects, metadata-only operations, pre-opened descriptors, sibling processes, and other NFS clients remain outside the claim.
- **Claim affected:** Exact process-tree handled-write confinement and truthful interpretation of the Landlock receipt.
- **Required disposition before freeze:** Correct the claim everywhere it appears or is mirrored, regenerate derived hashes, and obtain another exact-byte review.

# Important non-blocking findings

## Disposition of existing important findings

### I01 — Scope of zero-forward evidence

- **Severity:** Important historical finding; resolved by scope limitation.
- **Plan section or excerpt:** “This is not an OS-wide detector for arbitrary bespoke native callables, sibling processes, or device `ioctl` effects.”
- **Why it matters:** Torch and Transformers guards do not prove the absence of every imaginable native model implementation.
- **Concrete minimum fix:** None. Preserve the conjunction-based claim: exact import roots, exclusion of runner/runtime files, startup import denial, process-lifetime Torch and Transformers guards, inner audit guards, and target-free raw-tensor CUDA preflight.
- **Claim affected:** Zero new model forwards in the approved recovery process and executable closure.
- **Disposition:** **Resolved.** The claim is appropriately scoped and counters are carried into the recovery metadata and verifier.

### I02 — Endpoint equality is not continuous external immutability

- **Severity:** Important historical finding; resolved.
- **Plan section or excerpt:** The plan states that pre/post hashes do not “prove continuous immutability between the two observations, exclude a sibling process or another NFS client…”
- **Why it matters:** Landlock confines the process tree; it does not control independent clients, and two inventories cannot observe every intermediate state.
- **Concrete minimum fix:** None. Keep the endpoint-equality wording and prohibit “read-only mount” or continuous-immutability descriptions.
- **Claim affected:** Raw/provenance integrity and process-tree confinement.
- **Disposition:** **Resolved.**

### I03 — Structured finding adjudication

- **Severity:** Important historical finding; resolved.
- **Plan section or excerpt:** The v3 adjudication schema requires stable IDs, blocking flags, dispositions, rationales, changed-path sets, and a complete finding inventory.
- **Why it matters:** Findings must not disappear, be silently deferred, or be detached from the bytes changed in response.
- **Concrete minimum fix:** None. Retain exact terminal-verdict parsing as an independent gate and require all new findings from this review, including B10 and B11, to appear in the eventual adjudication.
- **Claim affected:** Review closure and frozen-decision provenance.
- **Disposition:** **Resolved structurally.** This review itself must still be completed and adjudicated before authorization.

### I04 — Exact test execution and target-host evidence

- **Severity:** Important historical finding; fixed.
- **Plan section or excerpt:** “The final completed review artifacts, adjudication, source/test inventories, hashes, and exactly two self-hashed test inputs—`LOCAL_TEST_RECEIPT.json` and `TARGET_HOST_TEST_RECEIPT.json`—must be authorization-bound.”
- **Why it matters:** macOS skips cannot substitute for Linux/Landlock/CUDA execution, and test source is not test execution evidence.
- **Concrete minimum fix:** None to the implemented receipt chain. Preserve the distinct local and target roles and the target requirement that the designated live test pass.
- **Claim affected:** Test execution provenance and target-host compatibility.
- **Disposition:** **Fixed in exact bytes.** The local receipt transparently reports 13 skips; the target receipt reports zero skips and passes the designated live test and the Torch-dependent loader tests. B10 is a separate feasibility problem exposed by the target timing values, not a failure of the receipt representation.

### I05 — Third-party reproduction boundary

- **Severity:** Important historical finding; adequately scoped.
- **Plan section or excerpt:** Raw tensors remain on a private network volume, while the proposed output is a compact receipt-verifiable bundle with a standard-library-only offline verifier.
- **Why it matters:** A third party cannot independently recompute all scientific quantities without access to the raw, model, J, and historical provenance bytes.
- **Concrete minimum fix:** None. Continue saying “offline-verifiable retrieved bundle” or “receipt-verifiable,” not public end-to-end reproduction.
- **Claim affected:** Third-party reproducibility.
- **Disposition:** **Resolved by claim limitation.**

### I06 — Independent units, repeated probes, and inherited statistical scope

- **Severity:** Important historical finding; resolved for this recovery.
- **Plan section or excerpt:** The appendix specifies eight fixed `prompt_id` units, three directions, five doses, prompt-level resampling, no prompt-population generalization, and no formal multiplicity correction.
- **Why it matters:** The 125 J-fitting prompts, 120 signed pairs, 96 gated pairs, and 4,872 readout rows are not 125, 120, 96, or 4,872 independent study units.
- **Concrete minimum fix:** None. Preserve the fixed-panel interval label, prompt-level bootstrap, primary layer 50 and dose 0.03, descriptive-only layers 51–78, complete-inventory missingness rule, and disclosed lack of formal multiplicity adjustment.
- **Claim affected:** Estimand, uncertainty interpretation, power, multiplicity, and generalization.
- **Disposition:** **Resolved.**

### I07 — Runtime margin for the 60-minute window

- **Severity:** Important historical finding; evidence collection implemented, but substantive concern unresolved and elevated to B10.
- **Plan section or excerpt:** Target qualification receipts now record host creation, preflight completion, test start/completion, and host ages.
- **Why it matters:** Timing fields are useful only if they demonstrate that the exact authorization-ready sequence can finish while at least 30 minutes remain.
- **Concrete minimum fix:** Implement B10’s exact-sequence timed qualification or revise the envelope.
- **Claim affected:** Operational feasibility and one-shot budget sufficiency.
- **Disposition:** **Partially fixed in schema, not resolved in evidence.** Exact timing is now recorded, but the supplied values exceed the one-hour envelope.

### I08 — Fixed-panel limitations must remain visible

- **Severity:** Important historical finding; resolved as a claim-policy requirement.
- **Plan section or excerpt:** “This is a fixed-panel stability calculation, not a prompt-population confidence interval.”
- **Why it matters:** The study cannot support broad prompt-population, semantic, consciousness, or target-feature claims merely because repeated directions, doses, layers, and control transports produce many rows.
- **Concrete minimum fix:** None. Any eventual narrative must name the exact fixed eight-prompt panel, primary layer 50, primary dose 0.03, conjunctive gates, and absence of population generalization or formal multiplicity correction.
- **Claim affected:** Construct validity and prevention of post hoc overstatement.
- **Disposition:** **Resolved in the frozen claim boundary.**

## New important findings

none

# What should remain unchanged

1. **The required-subset J correction.** Keep the physical J-checkpoint hash, `n_prompts=125`, `d_model=8192`, canonical layer-key normalization, duplicate rejection, missing-required rejection, and filtering to exactly layers 45–78. Do not replace this with an exact `0..78` whitelist.

2. **The downstream J metadata shape.** Keep:
   ```json
   {
     "sha256": "...",
     "map_count": 34,
     "revision": "..."
   }
   ```
   and keep the 79-layer available inventory and 45 unused extras only under recovery provenance.

3. **The original scientific entry point and patch boundary.** Continue invoking the same `audit.audit` once, and limit recovery monkeypatches to `_AuditBudgetWatchdog`, `_audit_external_receipt_chain`, and `_load_j_checkpoint`.

4. **The inherited measurement contract.** Preserve the frozen hook location, edited position, tokenization, one-token continuation, capture-before-edit ordering, exact upstream equality checks, J orientation, final normalization/LM-head readout, fixed token panel, and row semantics bound by the unchanged source and protocol snapshots.

5. **Temporal branch isolation.** Preserve independent clean/plus/minus prefix-cache clones, no text or cache carryover among signed branches, and no use of branch order as an estimand.

6. **Falsification and controls.** Keep wrong-orientation controls, identity transport, five randomized-J controls, BF16-versus-FP32 shadow checks, signed common-mode checks, clean/upstream byte identity, and all frozen sign conventions and conjunctive gates.

7. **Statistical boundaries.** Preserve `prompt_id` as the independent and bootstrap unit, eight fixed prompts, 20,000 prompt-resampling replicates, complete-inventory rejection, no imputation, no optional scientific stopping, no power increase, no population interval claim, and no across-layer selection.

8. **Historical/fresh dual provenance.** Retain separate original transaction and fresh recovery chains, and keep the failed bind-mount host as historical evidence rather than authority.

9. **One-shot authorization consumption.** Keep exclusive Landlock-receipt creation as authority consumption even when `execve`, imports, or pre-marker checks subsequently fail. Retain the exclusive marker as a second no-reuse barrier.

10. **Direct same-PID confinement.** Keep the absolute direct launcher and bootstrap paths, `python -B -E -s -S`, single-thread gate, no-site startup, environment restrictions, import-root manifest, descriptor and mapping audits, `no_new_privs`, and same-PID `execve`.

11. **The ABI-4 policy bits.** Preserve:
    - handled mask `0x7ff2`;
    - two exact output-directory rules with `0x1b2`;
    - the exact `/proc/self/task` rule with `0x4002`;
    - one exact identity-bound NVIDIA character-device rule per enumerated file with `0x2`;
    - no `/dev` directory rule; and
    - no unconfined fallback.

12. **The two-canary design.** Retain preconfinement writability, protected denial checks, output allow/deny checks, output-canary cleanup, protected endpoint equality, and exact real-file write-open denial checks.

13. **The scoped confinement limitations.** Keep the disclosures for metadata-only operations, pre-opened descriptors, sibling processes, other NFS clients, NVIDIA `ioctl`, and non-continuous endpoint observations. Correct B11 by making all summary sentences consistent with those disclosures, not by broadening the policy.

14. **Historical and recovery clocks as separate objects.** Do not rewrite original campaign fields. If B10 requires a longer recovery window, change only the prospective recovery authority and all matching producer/verifier constants; do not repurpose historical fields.

15. **The receipt and test architecture.** Preserve the code-freeze commit, exact source/test inventories, local and target receipts, target qualification support receipts, distinct qualification/recovery pod identities, exact review snapshots, and offline verification.

16. **Failure and publication semantics.** Retain exclusive failure publication after marker claim, no coexistence of success and `FAILURE.json`, quarantine of a post-rename publication that misses its final gate, exact three-file compact success directory, and verifier output outside the retrieved bundle.

# Minimal revised design

1. **Resolve feasibility before another recovery authorization.**
   - Create one fresh disposable B200 qualification pod in the required region and volume.
   - Start the same provider-creation-bound clock used by the proposed recovery.
   - Execute the exact real pre-authorization preparation sequence, including:
     - dependency setup;
     - full 156 GB public-artifact cache rehash;
     - final active/dependency import-root inventory and manifest;
     - exact NVIDIA-device enumeration;
     - the real two-canary Landlock probe;
     - confined dependency imports and BF16 CUDA arithmetic; and
     - construction of all information required to issue authorization.
   - Publish a self-hashed timing receipt with component start/completion times and the final authorization-ready host age.
   - Require authorization readiness by host age 1,800 seconds. Do not infer feasibility from the existing qualification receipt, whose preflight completed at 3,617 seconds.
   - If that gate cannot be met, increase the prospective recovery duration and spend ceiling consistently in the plan, producer, watchdog, publisher, verifier, tests, and authorization schema. Do not weaken the full rehash, confinement, or 30-minute remaining-time gate simply to fit the old clock.

2. **Correct the confinement claim without changing the policy.**
   - Replace the sentence saying NVIDIA devices are the “only” exception beyond the two output leaves.
   - State that there are exactly two classes of disclosed exceptions beyond those leaves:
     1. `/proc/self/task` with `WRITE_FILE|TRUNCATE` for process thread-name metadata; and
     2. individually enumerated, identity-bound NVIDIA character devices with `WRITE_FILE`.
   - Retain the device-`ioctl` and metadata limitations.

3. **Regenerate only affected derived artifacts.**
   - Update the plan and any mirrored claim constants or tests.
   - Add or replace the timing receipt and its reviewed snapshot.
   - Regenerate closure hashes, review packet inventory, adjudication inputs, and any generated appendices whose hashes include changed files.
   - Do not touch the frozen auditor, protocol, J loader, estimands, thresholds, controls, bootstrap, or scientific claim policy.

4. **Rerun the exact focused suite.**
   - Require the same five focused test files.
   - Require the target live Landlock test and all Torch-dependent loader/equivalence tests to pass.
   - Generate new local and target receipts only if source/test bytes change; otherwise preserve the code-freeze lineage but bind the new timing evidence explicitly.

5. **Obtain another exact-byte provider review.**
   - Include this review and adjudicate B10 and B11 explicitly.
   - Do not authorize the recovery on the basis of the present packet.
   - Require the new provider review to end with one exact positive terminal verdict and bind the exact changed packet and evidence bytes.

# Freeze checklist

- [ ] **B01:** The regenerated equivalence appendix remains outcome-blind and binds the unchanged frozen auditor, protocol fragments, recovery adapter, and affirmative scientific-field projection.
- [ ] **B02:** Both confined modes still use direct `-B -E -s -S` startup, no `-m` restart, no `site`, and guards installed before project or ML imports.
- [ ] **B03:** Historical top-level campaign fields remain unchanged; recovery authority remains separately named.
- [ ] **B04:** The loader still uses required-subset semantics and filters downstream maps to exactly layers 45–78.
- [ ] **B06:** The downstream J metadata remains exactly `sha256`, `map_count=34`, and `revision`; full inventory remains recovery-only provenance.
- [ ] **B07:** Exact terminal-verdict parsing still rejects negative, conditional, duplicate, absent, and misleading-prose cases.
- [ ] **B08/I04:** Local and target-host receipts, support receipts, source/test inventories, exact commands, test IDs, physical hashes, and self-hashes remain authorization- and verifier-bound.
- [ ] **B09:** Producer and verifier still use one identical completed-review cost ceiling, with exact-boundary tests.
- [ ] **B10:** A fresh exact-sequence qualification reaches the authorization-ready state with at least 30 minutes remaining in the proposed provider-creation-bound recovery window.
- [ ] **B10:** If the exact sequence cannot meet that gate, the recovery clock and spend ceiling are prospectively revised everywhere rather than bypassed.
- [ ] **B11:** Every “precise” confinement claim names both the `/proc/self/task` and exact NVIDIA-device exceptions.
- [ ] **I01:** Zero-forward wording remains scoped to the approved process and executable closure.
- [ ] **I02:** Endpoint equality is not described as continuous immutability or a read-only mount.
- [ ] **I03:** The new adjudication includes every historical ID plus B10 and B11, with no deferred blocker.
- [ ] **I05:** Third-party claims remain receipt-verifiable/offline-verifiable rather than public end-to-end reproducibility claims.
- [ ] **I06/I08:** The eventual scientific narrative remains an eight-prompt fixed-panel claim with no population generalization or formal multiplicity adjustment.
- [ ] The original auditor and protocol hashes are unchanged.
- [ ] The target qualification pod and later recovery pod are distinct.
- [ ] The later recovery pod independently repeats the exact same-host Landlock/CUDA gate.
- [ ] The real preflight and execution use the same Python binary, import-root manifest, source closure, device inventory, and device identities.
- [ ] The recovery launcher starts single-threaded with no inherited protected, canary, NVIDIA, writable regular-file, writable directory, unsafe device, shared file-backed mapping, or `io_uring` escape.
- [ ] The exact `0x7ff2`, `0x1b2`, `0x4002`, and `0x2` policy values remain unchanged unless separately reviewed.
- [ ] The protected and output canary matrices pass and the disposable output canary is empty afterward.
- [ ] The exclusive Landlock receipt is created only after confinement and consumes the authorization before same-PID `execve`.
- [ ] The attempt marker is exclusive and no alternate output namespace or retry exists under the same authority.
- [ ] Raw and historical-provenance file and directory inventories match at both endpoints.
- [ ] No success publication occurs after the recovery deadline.
- [ ] The compact directory contains exactly audit, summary, and publication marker, with no `FAILURE.json`.
- [ ] The retrieved bundle passes the standard-library-only offline verifier before any scientific claim is released.
- [ ] All changed packet bytes, receipts, review artifacts, and adjudication are hash-bound to a clean commit and exact live remote lineage.
