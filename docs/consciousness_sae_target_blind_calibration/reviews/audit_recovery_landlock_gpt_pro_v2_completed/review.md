# Verdict

The recovery concept is scientifically defensible: the checkpoint is physically hash-pinned, the required layers are selected without alteration, and accepting a superset is the smallest correction consistent with the original runtime. The supplied measurement contract also makes the hook boundary, edited position, tokenization, cache branching, Jacobian orientation, readout, independent unit, and fixed-panel claim scope unusually explicit.

The exact packet is nevertheless not ready to freeze. Three source/test defects require changes:

1. the checked-in focused tests are inconsistent with the checked-in loader’s deliberately preserved return schema and therefore fail deterministically;
2. the completed-review gate can treat the literal text “NOT READY TO FREEZE” as satisfying its readiness check; and
3. the plan promises authorization-bound local and target-host test receipts, but the authorization producer and offline verifier have no schema or arguments for those receipts.

There is also a producer/verifier contradiction: the producer permits a completed review costing up to the frozen $17 authorization, while the offline verifier rejects any recorded review cost above $10. A recovery could therefore be authorized and completed yet be irreversibly unverifiable by the frozen verifier.

These are defects in the exact final source and test bytes, not requests for scientific outcomes. Historical findings B01–B04 are substantively addressed by the redesign, and I01–I03, I05, and I06 are adequately resolved or scoped. Historical I04 remains operationally unresolved and gives rise to new blocker B08.

**NOT READY TO FREEZE**

# Blocking findings

## Historical findings B01–B04

### B01 — Historical whole-audit equivalence gap

- **Severity:** Historical blocker; substantively resolved in the supplied redesign, subject to B06.
- **Plan section or excerpt:** “The outcome-blind `AUDIT_RECOVERY_SCIENTIFIC_EQUIVALENCE.{json,md}` appendix mechanically binds the frozen plan/source bytes…”; machine appendix includes the frozen audit source hash, inherited design, adapter surface, and affirmative scientific-field projection.
- **Why it matters:** The prior packet did not establish that the proposed loader correction left hook semantics, tokenization, Jacobian orientation, readout arithmetic, row inclusion, bootstrap, and claim gates unchanged. The supplied appendix now binds the full relevant source files, records the inherited design, limits the patch surface to three operational monkeypatches, filters the selected maps to exactly `protocol.J_LAYERS`, and projects the scientific fields affirmatively.
- **Concrete minimum fix:** No conceptual design change. Repair B06 so the checked-in equivalence/recovery tests actually agree with and test the preserved loader metadata contract, then run and bind the exact test receipt required by B08.
- **Claim affected:** Scientific equivalence of the recovered audit to the frozen r3 audit, except for the required-subset compatibility predicate.
- **Resolution:** Resolved in design; exact packet validation is blocked by B06 and B08.

### B02 — Historical pre-guard `site`/startup-code gap

- **Severity:** Historical blocker; resolved in source, with target-host execution evidence still required under B08.
- **Plan section or excerpt:** “`python -B -E -s -S /absolute/path/to/landlock_launcher.py`”; the launcher same-PID execs the direct `confined_bootstrap.py`, which inventories import roots and installs guards before project or ML imports.
- **Why it matters:** The earlier `-m` restart could execute package initializers, `site`, `.pth`, or `sitecustomize` before the zero-forward and import guards. The supplied launcher and bootstrap now require direct-script invocation with `-B -E -s -S`, reject forbidden startup environment variables, replace `sys.path` with inventoried roots, and install process-lifetime guards before importing recovery code.
- **Concrete minimum fix:** Preserve the direct no-site bootstrap design. Add the authorization-bound test-receipt machinery required by B08 and require a non-skipped target-host pass.
- **Claim affected:** Deterministic executable closure, startup leakage prevention, and the scoped zero-forward claim.
- **Resolution:** Resolved in source; runtime proof is pending and currently cannot be bound as promised.

### B03 — Historical campaign-clock semantic overwrite

- **Severity:** Historical blocker; resolved.
- **Plan section or excerpt:** “The recovered audit preserves the original top-level `campaign_started_at_unix`, `campaign_deadline_at_unix`, and `hourly_price_usd` fields… Fresh authority is recorded only under a distinct `recovery_execution_campaign` object.”
- **Why it matters:** Overwriting legacy top-level fields would make an old execution clock appear to describe the recovery or vice versa. `_enrich_outputs` now checks exact historical constants, retains those top-level fields, adds `original_execution_campaign`, and separately records `recovery_execution_campaign`. The publisher uses `recovery_deadline_at_unix`, and the verifier checks both schemas.
- **Concrete minimum fix:** None. Do not simplify or rename these fields during revision.
- **Claim affected:** Temporal provenance and interpretation of original versus recovery resource authority.
- **Resolution:** Resolved.

### B04 — Historical subset-versus-whitelist contradiction

- **Severity:** Historical blocker; resolved in implementation, subject to the stale tests in B06.
- **Plan section or excerpt:** `_load_j_checkpoint_recovery` applies `if not set(required) <= set(available): reject`, filters to the required layers, and records the complete available and unused inventories separately.
- **Why it matters:** An exact `0..78` whitelist would contradict the stated required-subset correction and would make harmless future extras alter admissibility despite the physical checkpoint hash already fixing artifact identity. The supplied loader correctly requires all study layers, rejects duplicate/noncanonical normalized keys, hands downstream code exactly the required maps, and preserves the frozen three-field J metadata shape.
- **Concrete minimum fix:** Keep the loader unchanged. Correct the stale tests as specified in B06 rather than adding inventory fields back to the downstream metadata record.
- **Claim affected:** Narrowness and correctness of the J-checkpoint compatibility correction.
- **Resolution:** Resolved in implementation; current focused tests contradict it.

## New blocking findings

### B06 — Checked-in loader tests contradict the checked-in loader return schema

- **Severity:** Blocking; definite defect.
- **Plan section or excerpt:** In `_load_j_checkpoint_recovery`, the third return value is:
  ```python
  {
      "sha256": protocol.J_LENS_SPEC["sha256"],
      "map_count": len(required),
      "revision": protocol.J_LENS_SPEC["revision"],
  }
  ```
  But `test_audit_recovery.py` asserts:
  ```python
  assert record["available_layers"] == list(range(79))
  assert record["required_layers"] == list(range(45, 79))
  ```
  and repeats the same incompatible expectations in the parameterized extra-layer test.
- **Why it matters:** These tests must raise `KeyError` against the exact source. This is not merely missing evidence that tests ran; it is a static source/test contradiction. It also pressures a future fixer to put recovery-only inventory fields into `artifact_recomputation.j_lens`, which would undo the deliberately preserved scientific metadata shape used to resolve B01 and B04.
- **Concrete minimum fix:** Change only the affected tests:
  1. assert `record == {"sha256": ..., "map_count": 34, "revision": ...}`;
  2. reset `_OBSERVED_J_INVENTORY` before each loader call; and
  3. assert available, required, extra, and inventory-hash fields through `audit_recovery._OBSERVED_J_INVENTORY`, as `test_scientific_equivalence.py` already does.
  
  Do **not** change the loader’s three-field downstream metadata record.
- **Claim affected:** Focused-test validity, scientific-field equivalence, and the assertion that exact final source and test bytes have passed.
- **Required disposition before freeze:** Fix, rerun the exact focused suite, and include the changed test bytes in a new review because the current review packet bytes would change.

### B07 — A completed negative review can satisfy the readiness-text gate

- **Severity:** Blocking; definite fail-open review-gate defect.
- **Plan section or excerpt:** `_validate_review_evidence` computes:
  ```python
  verdict = review_text.split("# Blocking findings", 1)[0]
  if "READY TO FREEZE" not in verdict:
      raise AuditRecoveryError(...)
  ```
- **Why it matters:** The string `NOT READY TO FREEZE` contains the substring `READY TO FREEZE`. Consequently, a completed provider response with a negative verdict can pass this check. A locally generated adjudication with `final_decision="READY_TO_EXECUTE"` could then allow authorization even though the recorded provider review did not approve the exact bytes. This directly contradicts:
  > “A READY TO FREEZE verdict must apply to the exact final source and test bytes in this packet.”
  
  The structured adjudication does not cure the false semantic statement `provider_ready_to_freeze_verdict=True`, because that value is constructed after this substring check.
- **Concrete minimum fix:** Parse the verdict section exactly and fail closed. The smallest repair is to require one exact terminal verdict line from the allowed set and require it to equal `READY TO FREEZE`; explicitly reject `NOT READY TO FREEZE` and `READY AFTER SPECIFIED FIXES`. Add focused tests for all three terminal verdicts and for misleading prose containing the positive phrase.
- **Claim affected:** Independent-review closure, frozen-decision integrity, and authorization legitimacy.
- **Required disposition before freeze:** Fix source and tests, then obtain a review of the changed exact bytes.

### B08 — Promised local and target-host test receipts are not representable in the authorization or verifier

- **Severity:** Blocking; definite plan/implementation contradiction.
- **Plan section or excerpt:** The plan requires:
  > “The final completed review artifacts, adjudication, source/test inventories, hashes, exact local test receipt, and live target-host test/probe receipts must be committed and authorization-bound.”
  
  Historical I04 likewise requires exact commands, commit/source hashes, interpreter/kernel/ABI, dependency inventory, and pass/fail/skip IDs. But `issue_authorization`, `validate_recovery_authorization`, `_execution_binding`, and `recovery_bundle_verifier._validate_authorization` have no local-test-receipt or target-host-test-receipt arguments or fields. They bind test **source files**, the Landlock/CUDA probe, and review artifacts, but not evidence that the focused tests ran.
- **Why it matters:** The current producer cannot enforce the stated prerequisite. A source hash is not a test execution receipt, and the CUDA/canary probe is not a substitute for running the focused launcher, bootstrap, recovery, equivalence, and verifier tests. In particular, B06 demonstrates why binding test source alone is insufficient. The plan’s statement that skipped Linux/Landlock tests are not counted as target-host passes is not mechanically enforced.
- **Concrete minimum fix:** Add exactly two required, self-hashed receipt inputs:
  1. `LOCAL_TEST_RECEIPT.json`; and
  2. `TARGET_HOST_TEST_RECEIPT.json`.
  
  Each should bind commit, source/test inventory hash, exact command/argv, interpreter and platform, collected test IDs, pass/fail/skip counts and IDs, start/end time, and exit status. The target receipt must bind pod, kernel, observed Landlock ABI, and GPU identity, and must require zero failed tests and zero skipped tests for the designated target-only set. Bind both physical files in authorization, carry their hashes into recovery metadata, and validate them offline. Do not invent a larger testing framework.
- **Claim affected:** Deterministic execution, target-host compatibility, test provenance, and historical I04 closure.
- **Required disposition before freeze:** Fix producer, verifier, tests, and plan consistently, then conduct a new exact-byte review.

### B09 — Review-cost limits disagree between the authorization producer and offline verifier

- **Severity:** Blocking; definite producer/verifier contradiction.
- **Plan section or excerpt:** `audit_recovery.py` freezes:
  ```python
  PRO_REVIEW_BUDGET_AUTHORIZATION_USD = 17.0
  ```
  and accepts a reconstructed completed-review cost up to that value. In contrast, `recovery_bundle_verifier._validate_review` requires:
  ```python
  not 0 < cost <= 10.0
  ```
  to be false.
- **Why it matters:** A review costing, for example, $12 could validly pass `_validate_review_evidence`, be embedded in a valid authorization, and permit the one-shot recovery. The resulting success bundle would then be rejected permanently by the offline verifier. Because the authorization is one-shot and the scientific compact bundle cannot be relabeled or retried, this could waste the recovery and leave an ambiguous “producer-valid but verifier-invalid” result.
- **Concrete minimum fix:** Use one frozen constant in both implementations. The smallest repair is to set the verifier’s maximum to exactly `$17.00`, matching the authorization, and add boundary tests for `$17.00` accepted and any value above `$17.00` rejected. Alternatively lower the producer authorization to `$10.00`, but do not leave different limits.
- **Claim affected:** Independent offline reproducibility, one-shot success admissibility, and budget consistency.
- **Required disposition before freeze:** Align source and tests before any paid completed review or recovery authorization.

# Important non-blocking findings

## Historical findings I01–I06

### I01 — Scope of zero-forward evidence

- **Severity:** Important historical finding; resolved by appropriate scope narrowing.
- **Plan section or excerpt:** “This is not an OS-wide detector for arbitrary bespoke native callables, sibling processes, or device `ioctl` effects.”
- **Why it matters:** The Torch and Transformers counters cover named Python boundaries, not every theoretically possible native computation. The supplied claim correctly rests on a conjunction of direct no-site startup, exact import roots, static exclusion of runners/runtime, process-lifetime guards, inner guards, and a target-free raw-tensor CUDA probe.
- **Concrete minimum fix:** None beyond B08’s requirement to bind evidence that the guards and tests actually ran. Preserve the scoped wording and do not upgrade it to a universal detector.
- **Claim affected:** Zero new model forwards during the approved recovery closure.
- **Resolution:** Resolved in claim wording and implementation design.

### I02 — Endpoint equality is not continuous external immutability

- **Severity:** Important historical finding; resolved.
- **Plan section or excerpt:** “These hashes … do not … prove continuous immutability between the two observations, exclude a sibling process or another NFS client…”
- **Why it matters:** Landlock applies to the confined process tree, while the pre/post inventories only establish equality at two endpoints. The plan accurately discloses sibling-process, remote-client, metadata-operation, pre-opened-FD, and device-`ioctl` limits.
- **Concrete minimum fix:** None. Retain this exact distinction in all compact claims and verifier constants.
- **Claim affected:** Process-tree handled-write confinement and raw/provenance endpoint equality.
- **Resolution:** Resolved.

### I03 — Structured finding adjudication

- **Severity:** Important historical finding; mostly resolved, with the separate verdict-parser defect in B07.
- **Plan section or excerpt:** `_validate_completed_review_adjudication` requires stable IDs, blocking flags, dispositions, rationales, and changed-path sets; deferred dispositions are rejected.
- **Why it matters:** This prevents findings from disappearing or being silently deferred. The structure is substantially stronger than searching only for IDs.
- **Concrete minimum fix:** Preserve the structured schema. Apply B07 so the structured adjudication cannot be paired with a falsely classified negative provider verdict.
- **Claim affected:** Review closure and frozen decision provenance.
- **Resolution:** Resolved structurally; B07 is a new independent semantic defect.

### I04 — Exact test execution and target-host evidence

- **Severity:** Important historical finding; unresolved operationally.
- **Plan section or excerpt:** “Skipped Linux/Landlock tests on macOS are disclosed rather than counted as target-host passes.”
- **Why it matters:** The packet contains test source but no evidence that the exact committed tests passed locally or on the target host, and B08 shows that such receipts cannot currently be authorization-bound.
- **Concrete minimum fix:** Implement B08’s two-receipt schema. No additional test layers are necessary.
- **Claim affected:** Test execution provenance and target-host feasibility.
- **Resolution:** Not resolved; elevated into new blocker B08 because the implementation cannot satisfy the plan.

### I05 — Third-party reproduction boundary

- **Severity:** Important historical finding; adequately scoped.
- **Plan section or excerpt:** Raw tensors remain on the private network volume; the recovery publishes a compact receipt-verifiable bundle and an offline verifier.
- **Why it matters:** Hashes permit verification only for parties who can obtain the referenced bytes. The packet does not establish public independent recomputation from the private raw/model/J artifacts.
- **Concrete minimum fix:** Continue describing the output as receipt-verifiable and offline-verifiable. Publish access identities and hashes with the compact bundle, but do not claim public end-to-end reproduction unless the underlying artifacts become available.
- **Claim affected:** Third-party reproducibility.
- **Resolution:** Resolved by claim limitation.

### I06 — Independent units, repeated probes, and inherited statistical scope

- **Severity:** Important historical finding; resolved for recovery-scope purposes.
- **Plan section or excerpt:** The appendix records eight fixed `prompt_id` units, three directions, five doses, prompt-level bootstrap, no population generalization, no increase in power, and no formal multiplicity adjustment.
- **Why it matters:** The 125 J-fitting prompts cannot be mistaken for current study units, and 120 signed pairs or 4,872 readout rows cannot be treated as independent sample size. The fixed-panel stability interval is appropriately distinguished from a population confidence interval.
- **Concrete minimum fix:** None. Preserve the exact fixed-panel wording, the sole primary layer, descriptive status of layers 51–78, and the disclosed absence of formal multiplicity adjustment.
- **Claim affected:** Statistical estimand, uncertainty interpretation, and generalization.
- **Resolution:** Resolved.

## New important findings

### I07 — Runtime margin for the 60-minute ownership-bound window is asserted but not quantified in the packet

- **Severity:** Important, non-blocking; missing evidence rather than a demonstrated defect.
- **Plan section or excerpt:** Authorization requires at least 30 minutes remaining after staging, dependency setup, public-cache rehash, and the Landlock/CUDA probe; the audit must finish by 60 minutes after provider creation.
- **Why it matters:** The recovery rehashes the full import roots, raw tree, provenance tree, model artifact inventory, and J checkpoint and performs substantial GPU recomputation. The packet states that a previous audit reached the J inventory check, which is encouraging, but supplies no timing breakdown demonstrating margin under the new bootstrap, double endpoint inventory, and recovery publication path.
- **Concrete minimum fix:** Add elapsed times for staging, import-root rehash, preflight, authorization, and the prior audit-to-J-failure to the target-host receipt proposed in B08. Treat less than a conservative publication margin as a pre-authorization stop. Do not lengthen the frozen budget merely to avoid collecting timings.
- **Claim affected:** Feasibility and likelihood of obtaining a verifier-admissible compact bundle within the one-shot authority.

### I08 — The fixed-panel inferential limitations must remain visible in any eventual scientific narrative

- **Severity:** Important, non-blocking; judgment call rather than a recovery defect.
- **Plan section or excerpt:** “This is a fixed-panel stability calculation, not a prompt-population confidence interval”; “formal adjustment is `none_specified_in_frozen_protocol`.”
- **Why it matters:** Eight prompts, repeated directions/doses, six conjunctive primary components across two metrics, and strongest-of-five random controls support a narrow fixed-panel calibration statement. They do not support broad prompt-population, semantic, consciousness, or target-feature claims.
- **Concrete minimum fix:** Keep the compact claim policy as frozen and require any later prose to name the exact eight-prompt panel, primary layer 50, primary dose 0.03, and lack of population generalization or formal multiplicity correction.
- **Claim affected:** Construct validity and prevention of post hoc overstatement.

# What should remain unchanged

1. **The literal required-subset J correction.** Keep the physical checkpoint hash, `n_prompts=125`, `d_model=8192`, canonical layer-key normalization, missing-required rejection, filtering to exactly layers 45–78, and separate disclosure of unused extras. Do not restore an exact `0..78` whitelist.

2. **The preserved downstream J metadata shape.** `artifact_recomputation.j_lens` should retain only the frozen `sha256`, required `map_count=34`, and `revision` fields, with the full available inventory under recovery-only provenance.

3. **The hook and position contract.** Preserve:
   - `model.model.layers[50]`;
   - zero-based block-50 output, post-block and pre-block-51;
   - `hidden_state[0,0,:]` with shape `[1,1,8192]`;
   - the final rendered generation-prompt token;
   - one continuation token per edited forward;
   - capture-before-edit hook registration;
   - one hook fire per edited forward; and
   - exact upstream layers 45–49 equality checks.

4. **Cache and branch semantics.** Keep independent prefix-cache clones for clean, plus, and minus continuations; shared prefix values; one-token continuation forwards; and the statement that plus/minus branch order is not an estimand.

5. **Jacobian orientation and controls.** Preserve row-vector application `residual_delta @ J_l.T`, the explicit wrong-orientation falsification control, deterministic orientation fixtures, BF16-versus-FP32 shadow checks, identity transport, five randomized-J controls, signed plus/minus branches, and common-mode control.

6. **Readout semantics.** Keep final RMS normalization and selected LM-head weights, signed final midpoint centering, fixed token panel, primary layer 50 and dose 0.03, and descriptive-only roles for layers 51–78.

7. **Statistical boundaries.** Preserve `prompt_id` as the only resampling unit, eight fixed prompts, no population confidence-interval claim, no power increase from recovery, no outcome-based exclusions, complete-inventory stopping, and explicit disclosure that no formal multiplicity correction was specified.

8. **Dual provenance.** Retain separate original transaction and fresh audit-compute receipt chains, plus the superseded recovery host as historical failure evidence rather than authority.

9. **One-shot consumption.** Keep authorization consumption at exclusive Landlock-receipt creation and again at attempt-marker creation, with no retry or alternate output namespace under the same authority.

10. **Direct same-PID startup.** Preserve the absolute direct launcher path, `python -B -E -s -S`, single-thread requirement, FD and shared-mapping audits, same-PID `execve`, exact import-root manifest, and guards installed before project or ML imports.

11. **Narrow Landlock claim.** Keep ABI-4 handled rights `0x7ff2`, two exact `0x1b2` directory rules, one exact `WRITE_FILE` rule per identity-bound NVIDIA character device, no `/dev` directory rule, and explicit disclosure of metadata, pre-opened-FD, sibling/NFS, and device-`ioctl` limitations.

12. **Independent protected/output canaries.** Preserve preconfinement writability proof, post-confinement denial/allow matrices, protected-tree endpoint equality, output-canary cleanup, and exact real-file write-open denial checks.

13. **Historical versus recovery clocks.** Keep original top-level campaign fields untouched and use only `recovery_execution_campaign` and `recovery_deadline_at_unix` for fresh authority and publication.

14. **Offline verifier and failure semantics.** Preserve exclusive publication, no coexistence of success and `FAILURE.json`, quarantine after failed publication, verifier output outside the bundle, and rejection of symlinks, hardlinks, special files, extra compact files, or broken receipt links.

# Minimal revised design

1. **Repair the stale loader tests without modifying the loader.**
   - Move inventory assertions from the third return value to `_OBSERVED_J_INVENTORY`.
   - Continue asserting that the third value has exactly the frozen three-field metadata shape.
   - Add setup/reset of `_OBSERVED_J_INVENTORY` to avoid cross-test state.
   - Run the focused equivalence and recovery tests together.

2. **Make the provider verdict parser exact.**
   - Extract the `# Verdict` section.
   - Require exactly one recognized terminal verdict.
   - Accept only `READY TO FREEZE`.
   - Reject `NOT READY TO FREEZE`, `READY AFTER SPECIFIED FIXES`, absent verdicts, duplicate verdicts, and positive phrases appearing only in explanatory prose.
   - Keep the structured adjudication as a second, independent gate.

3. **Add two test-execution receipts, not a larger testing system.**
   - Local receipt: exact commit, source/test inventory, command, interpreter/platform, test IDs, pass/fail/skip counts, timestamps, and exit code.
   - Target-host receipt: the same fields plus pod ID, kernel, Landlock ABI, GPU identity, and explicit zero skips for the designated Linux/Landlock integration set.
   - Add them to the issue and execute argv, `external_files`, authorization schema, recovery metadata, and offline verifier.
   - Require exact physical hashes and self-hashes.

4. **Unify the completed-review cost ceiling.**
   - Freeze a single `$17.00` constant shared semantically by producer and verifier.
   - Test exact acceptance at `$17.00` and rejection above it.
   - Reconstruct cost identically in both paths where possible.

5. **Regenerate all derived artifacts after source/test changes.**
   - Scientific-equivalence JSON and Markdown.
   - Any closure/path hashes.
   - Review packet inventory.
   - Focused test receipt fixtures and verifier expectations.

6. **Run the smallest decisive test sequence before another review.**
   - Scientific-equivalence tests.
   - Audit-recovery tests.
   - Confined-bootstrap tests.
   - Landlock-launcher tests.
   - Recovery-bundle-verifier tests.
   - On the target host, require the Linux Landlock integration test to pass rather than skip, followed by the exact confined CUDA probe.

7. **Submit the changed exact bytes for a new completed review.**
   - Because B06–B09 require changes to reviewed source or test files, a readiness verdict cannot be inherited by adjudication from this packet.
   - Do not create a recovery authorization until the new exact-byte review, adjudication, local receipt, and target-host receipt all validate.

# Freeze checklist

- [ ] B01 remains closed: the regenerated outcome-blind equivalence appendix binds the final exact source and test bytes.
- [ ] B02 remains closed: both confined modes use the same direct `-B -E -s -S` bootstrap with no package-module restart.
- [ ] B03 remains closed: original top-level campaign fields remain byte-semantically historical.
- [ ] B04 remains closed: the loader applies only the required-layer subset predicate and preserves the three-field J metadata shape.
- [ ] B06 is fixed: no test expects recovery inventory fields in the downstream J metadata record.
- [ ] B06 test receipt shows the exact scientific-equivalence and audit-recovery suites pass.
- [ ] B07 is fixed: `NOT READY TO FREEZE` and `READY AFTER SPECIFIED FIXES` are tested and rejected by the review gate.
- [ ] B08 is fixed: local and target-host test receipts are mandatory authorization inputs and offline-verifier inputs.
- [ ] The target-host receipt reports the exact kernel, Landlock ABI, interpreter, dependency inventory, GPU, test command, test IDs, and zero skipped designated integration tests.
- [ ] B09 is fixed: producer and verifier use the same completed-review cost ceiling.
- [ ] The scientific-equivalence JSON and Markdown have been regenerated from the final source and match their extractor exactly.
- [ ] All changed source, tests, documents, generated appendices, and verifier constants are committed and clean.
- [ ] Local HEAD, tracking ref, and live remote commit are identical.
- [ ] The completed provider review covers the exact final source/test bytes and has an exact positive terminal verdict.
- [ ] The review response text is byte-bound to the provider output and the structured adjudication covers every historical and new stable ID.
- [ ] No blocker is deferred; every blocker is fixed or explicitly technically rejected with a valid rationale.
- [ ] The local test receipt and target-host test receipt postdate and bind the final commit.
- [ ] The preauthorization Landlock/CUDA probe uses the same Python binary, import-root manifest, device inventory, and child command as authorization expects.
- [ ] The output root is fresh and empty before the real launcher; the disposable canary-output root is also empty.
- [ ] The exact NVIDIA device list is sorted, unique, character-device validated, and identity-equal between preflight and execution.
- [ ] No protected, canary, NVIDIA, writable regular-file, writable directory, or unsafe device descriptor is inherited.
- [ ] No shared file-backed mapping or inherited `io_uring` descriptor exists.
- [ ] The Landlock receipt is created after restriction and before same-PID exec.
- [ ] The authorization is treated as consumed if that receipt exists, even if bootstrap or marker validation later fails.
- [ ] Raw and provenance file **and directory** inventories match at both endpoints.
- [ ] The compact audit and summary carry identical recovery metadata and preserve the original scientific fields.
- [ ] Publication completes before the recovery deadline and contains exactly the audit, summary, and publication marker.
- [ ] The retrieved bundle passes the corrected standard-library-only offline verifier before any scientific claim is released.
