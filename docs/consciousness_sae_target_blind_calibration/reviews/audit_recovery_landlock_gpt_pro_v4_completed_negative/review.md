# Verdict

The proposed recovery is scientifically narrow and technically much stronger than the historical v2 and v3 packets. The required-subset J correction is the right minimum repair for a physically hash-pinned superset checkpoint: it requires every study layer 45–78, filters downstream access to exactly those 34 maps, preserves the frozen `sha256`/`map_count=34`/`revision` metadata shape, and records unused maps only in recovery provenance. Nothing supplied indicates a need for a fresh model transaction.

The temporal and operational design is also unusually disciplined. Historical model-execution authority is separated from fresh recovery authority; the direct no-site launcher closes the previous startup gap; the authorization is consumed by the post-confinement exclusive receipt; same-PID handoff, descriptor and mapping audits, closed NVIDIA device rules, the `/proc/self/task` exception, endpoint rehashes, failure semantics, exact verdict parsing, and offline verification are all expressly bounded.

The exact-byte B10 repair is adequate as operational feasibility evidence. The supplied timed qualification receipt reports a complete byte-heavy preparation sequence reaching authorization readiness at host age 958 seconds, after independently rehashing 45 public-artifact files totaling 156,023,372,845 bytes. Under the frozen 3,600-second window, that leaves 2,642 seconds, which is 842 seconds more than the required 1,800-second post-authorization reserve. Its `source_test_qualification` scope is correctly disclosed rather than relabeled as `final_recovery`, and the actual recovery authorizer requires a distinct fresh pod to repeat the same-host preflight with the full final recovery closure.

The exact-byte B11 wording repair is also present. The paragraph labeled “The precise claim” now names both exception classes beyond the two output leaves: `/proc/self/task` `WRITE_FILE|TRUNCATE`, and individually enumerated NVIDIA character-device `WRITE_FILE`. The machine claim and offline verifier mirror both exceptions and retain the limitations for metadata operations, pre-opened descriptors, sibling processes, other NFS clients, and NVIDIA `ioctl`.

One stop-ship packet-integrity defect remains. The machine-readable scientific-equivalence appendix is explicitly excluded from the provider review packet even though the plan relies on that exact artifact to close B01, binds it into authorization and recovery metadata, and describes both machine and human appendices as review evidence. The supplied tests prove that a checked-in JSON existed and matched the generator when those tests ran, but the test receipts bind only source/test files—not that JSON. Because the JSON is also absent from `PRO_REVIEW_V4_PACKET`, the provider-review Git-diff gate does not protect it after review. Thus an authorization can bind a machine appendix that neither this review nor the test receipts exact-byte bind. I have not inspected that omitted file.

This is a documentation/evidence-closure blocker, not a scientific-design blocker and not grounds for a new model transaction. The smallest repair is to add the existing generated JSON appendix to the provider packet and packet-lineage gate, rerun the affected source/test receipts, and obtain another exact-byte review. Do not redesign the recovery.

**NOT READY TO FREEZE**

# Blocking findings

## B01 — Historical whole-audit scientific-equivalence gap

- **Severity:** Historical blocker; scientific issue resolved, but exact artifact closure remains subject to B12.
- **Plan section or short excerpt:** “The outcome-blind `AUDIT_RECOVERY_SCIENTIFIC_EQUIVALENCE.{json,md}` appendix mechanically binds the frozen plan/source bytes…”; `scientific_equivalence.py` defines an affirmative scientific-field projection and limits the recovery monkeypatch surface.
- **Why it matters:** A post-run compatibility correction is admissible only if hook semantics, positions, tokenization, J orientation, selected maps, final-normalization/LM-head readout, row inclusion, bootstrap, thresholds, and claim gates remain those of the frozen audit.
- **Concrete minimum fix:** Do not change the scientific design. Preserve the same `audit.audit` call, the three named monkeypatches, exact required-map filtering, the affirmative scientific projection, and frozen source hashes. Close the omitted-machine-artifact binding described in B12.
- **Claim affected:** Scientific equivalence of the recovered audit to the frozen r3 audit, except for the required-subset J inventory predicate.
- **Disposition:** The substantive equivalence repair is resolved. The supplied extractor and tests support the narrow adapter claim, but this review cannot exact-byte approve the omitted generated JSON appendix.

## B02 — Historical pre-guard startup-code gap

- **Severity:** Historical blocker; resolved.
- **Plan section or short excerpt:** “`python -B -E -s -S /absolute/path/to/landlock_launcher.py`”; the same-PID child directly executes `confined_bootstrap.py`.
- **Why it matters:** Normal `site` initialization, `.pth` processing, `sitecustomize`, package initializers, or a package-module restart could execute code before confinement and zero-forward guards.
- **Concrete minimum fix:** None. Retain direct-script startup, all four interpreter flags, forbidden startup-environment checks, import-root inventories, `sys.path` replacement, guard priming before project imports, and same-PID `execve`.
- **Claim affected:** Deterministic startup, leakage prevention, executable closure, and scoped zero-forward evidence.
- **Disposition:** Resolved in the supplied launcher/bootstrap design and target-host test receipt.

## B03 — Historical campaign-clock semantic overwrite

- **Severity:** Historical blocker; resolved.
- **Plan section or short excerpt:** “The recovered audit preserves the original top-level `campaign_started_at_unix`, `campaign_deadline_at_unix`, and `hourly_price_usd` fields… Fresh authority is recorded only under a distinct `recovery_execution_campaign` object.”
- **Why it matters:** Rewriting the historical campaign fields would make the recovery appear to have been authorized by the original model-run clock or make the original transaction appear to have occurred under fresh recovery authority.
- **Concrete minimum fix:** None. Keep the historical top-level values, `original_execution_campaign`, separate `recovery_execution_campaign`, and publication marker’s `recovery_deadline_at_unix`.
- **Claim affected:** Temporal provenance and separation of the original model transaction from the recovery computation.
- **Disposition:** Resolved by `_enrich_outputs`, `_publish_recovery_pair_atomic`, focused tests, and offline-verifier checks.

## B04 — Historical required-subset versus release-whitelist contradiction

- **Severity:** Historical blocker; resolved.
- **Plan section or short excerpt:** `_load_j_checkpoint_recovery` requires `set(required) <= set(available)` and constructs a filtered mapping over only `protocol.J_LAYERS`.
- **Why it matters:** Requiring exactly layers 0–78 would contradict literal required-subset semantics. Conversely, passing all available maps downstream could alter scientific metadata or computation.
- **Concrete minimum fix:** None. Preserve canonical layer-key normalization, duplicate rejection, required-layer inclusion, exact filtering to 45–78, and recovery-only recording of extras.
- **Claim affected:** Narrowness and correctness of the J-checkpoint compatibility repair.
- **Disposition:** Resolved. This is the correct minimum correction for the hash-pinned checkpoint and is comparable to the cited original runtime’s subset predicate.

## B06 — Loader tests contradicted the preserved downstream metadata schema

- **Severity:** Historical blocker; fixed in the supplied source and tests.
- **Plan section or short excerpt:** The loader returns only `sha256`, `map_count=len(required)`, and `revision`; full inventory is stored through `_OBSERVED_J_INVENTORY`.
- **Why it matters:** Mixing recovery inventory fields into `artifact_recomputation.j_lens` would change a projected scientific field and undermine byte-equivalence.
- **Concrete minimum fix:** None. Keep full available/required/extra inventory outside the downstream J metadata record.
- **Claim affected:** Test validity and equivalence of scientific output fields.
- **Disposition:** Fixed. The current local and target receipts bind the current source/test inventory, and the target receipt reports the Torch-dependent loader and equivalence tests as passed.

## B07 — A negative provider verdict could satisfy a substring readiness check

- **Severity:** Historical blocker; fixed.
- **Plan section or short excerpt:** `_terminal_review_verdict` requires one `# Verdict` section, exactly one recognized terminal line, and that line as the final nonempty line before `# Blocking findings`.
- **Why it matters:** `NOT READY TO FREEZE` contains `READY TO FREEZE`; substring parsing could authorize a negative review.
- **Concrete minimum fix:** None. Preserve the exact parser, duplicate-verdict rejection, and independent structured adjudication.
- **Claim affected:** Review closure and authorization legitimacy.
- **Disposition:** Fixed. Tests cover negative, conditional, positive, misleading-prose, and duplicate-verdict cases.

## B08 — Test receipts were not representable in authorization or offline verification

- **Severity:** Historical blocker; fixed.
- **Plan section or short excerpt:** Local and target test receipts and three target qualification receipts are now carried through execution paths, authorization `external_files`, recovery metadata, and offline verification.
- **Why it matters:** Source hashes alone do not prove that the exact suite ran on either local or target environments.
- **Concrete minimum fix:** None to the existing receipt architecture. Preserve code-freeze commits, source/test inventories, command argv, dependency inventories, complete node outcomes, target host identity, support-receipt hashes, and the designated live-test pass requirement.
- **Claim affected:** Test provenance, target-host compatibility, and deterministic offline admissibility.
- **Disposition:** Fixed. The supplied target receipt reports 180 collected and 180 passed tests, with zero failures, skips, or not-run tests.

## B09 — Producer and verifier used different completed-review cost ceilings

- **Severity:** Historical blocker; fixed by a disclosed prospective boundary.
- **Plan section or short excerpt:** Producer review authorization and offline verifier both use a `$25.00` ceiling.
- **Why it matters:** Mismatched ceilings could produce a one-shot bundle accepted by the producer but permanently rejected by the verifier.
- **Concrete minimum fix:** None. Keep both constants equal and retain the exact-boundary verifier test.
- **Claim affected:** Budget consistency and offline admissibility.
- **Disposition:** Fixed. The change from the earlier suggested `$17.00` value is a disclosed superseding budget decision, not a remaining contradiction.

## B10 — Historical timing evidence missed the one-hour authorization window

- **Severity:** Historical blocker; resolved by the seven-file timed qualification chain.
- **Plan section or short excerpt:** The replacement evidence reports `authorization_ready_host_age_seconds=958`, `seconds_remaining_at_authorization_ready=2642`, and `seconds_above_required_remaining_margin=842`.
- **Why it matters:** Authorization may issue only after setup, full public-cache rehash, manifest construction, and Landlock/CUDA preflight, while at least 1,800 seconds remain in the provider-creation-bound hour.
- **Concrete minimum fix:** None. Preserve the exact timed receipt chain, the 1,800-second issuance gate, and mandatory fresh-pod repetition with `final_recovery` scope.
- **Claim affected:** Feasibility, one-shot authorization, and budget adequacy.
- **Disposition:** Resolved for operational feasibility. The supplied chain records:
  - provider creation at host age 0;
  - dependency setup by age 491;
  - guest gate by 542;
  - independent rehash of all 45 files/156,023,372,845 bytes by 708;
  - import-root manifest by 844;
  - Landlock enforcement by 942; and
  - CUDA completion/authorization readiness by 958.
  
  The resulting 2,642 seconds remaining exceed the 1,800-second requirement by 842 seconds. The qualification’s `source_test_qualification` scope is explicitly limited; it is not substituted for the mandatory `final_recovery` preflight on the later pod.

## B11 — “The precise claim” omitted the `/proc/self/task` mutation exception

- **Severity:** Historical blocker; resolved in the supplied plan and mirrored claim.
- **Plan section or short excerpt:** “The precise claim is that the audit process and descendants can perform handled regular-filesystem content/topology mutations only under [the two output leaves], with exactly two disclosed exception classes… the `/proc/self/task` `WRITE_FILE|TRUNCATE`… exception and the… NVIDIA character-device `WRITE_FILE` exceptions.”
- **Why it matters:** Omitting one enforced exception from the sentence labeled “precise” would permit a later confinement overclaim.
- **Concrete minimum fix:** None. Preserve the current wording and mirrored `WRITE_CONFINEMENT_CLAIM`.
- **Claim affected:** Exact interpretation of process-tree handled-write confinement.
- **Disposition:** Resolved. The plan, recovery metadata, and verifier now name both exception classes and retain the unhandled-operation limitations.

## B12 — Machine-readable scientific-equivalence appendix is outside the reviewed and test-bound byte closure

- **Severity:** Blocking; definite packet-integrity defect.
- **Plan section or short excerpt:** The plan relies on `AUDIT_RECOVERY_SCIENTIFIC_EQUIVALENCE.{json,md}` and says the “machine/human appendices” are bound. However, `PRO_REVIEW_V4_PACKET` includes only the Markdown appendix, and `test_v4_review_packet_includes_receipts_and_prior_negative_review` expressly asserts that `AUDIT_RECOVERY_SCIENTIFIC_EQUIVALENCE.json` is not in the provider packet.
- **Why it matters:** The omitted JSON is central evidence for B01 and is later bound into authorization and recovery metadata. The supplied focused test checks that it matched `build_packet()` when the test ran, but the local and target receipts bind only `SOURCE_TEST_BOUND_PATHS`, which exclude this documentation JSON. The provider Git-chain check protects `PRO_REVIEW_V4_PACKET`, which also excludes it. Consequently, the machine appendix can differ after the recorded test execution or after provider review while still being newly hash-bound at authorization. This review cannot inspect or approve its exact bytes because it was not supplied.
- **Concrete minimum fix:** Add the existing generated `AUDIT_RECOVERY_SCIENTIFIC_EQUIVALENCE.json` to `PRO_REVIEW_V4_PACKET`, so it is included in the provider artifact manifest and protected by the reviewed-packet Git-diff gate. Remove the test assertion that it is excluded and replace it with an assertion that both JSON and Markdown appendices are included. Rerun the local and target source/test receipts because those source/test bytes change, then obtain another exact-byte review.
- **Claim affected:** Exact-byte scientific-equivalence evidence, B01 closure, review lineage, and the statement that final reviewed bytes are unchanged.
- **Required disposition before freeze:** Fix and re-review. Do not infer the omitted JSON’s contents from its filename, from the Markdown rendering, or from a prior test run.

# Important non-blocking findings

## I01 — Scope of zero-forward evidence

- **Severity:** Important historical finding; resolved by explicit scoping.
- **Plan section or short excerpt:** “This is not an OS-wide detector for arbitrary bespoke native callables, sibling processes, or device `ioctl` effects.”
- **Why it matters:** Torch and Transformers patches cannot prove the absence of every imaginable native model implementation outside the approved closure.
- **Concrete minimum fix:** None. Preserve the conjunction claim: exact import roots, runner/runtime exclusion, startup import denial, process-lifetime Torch/Transformers guards, inner guards, and target-free raw CUDA probe.
- **Claim affected:** Zero new model forwards in the approved recovery process and executable closure.
- **Disposition:** Resolved.

## I02 — Endpoint equality is not continuous external immutability

- **Severity:** Important historical finding; resolved.
- **Plan section or short excerpt:** The plan says pre/post inventories do not prove continuous immutability or exclude sibling processes and other NFS clients.
- **Why it matters:** Landlock confines the process tree, and two endpoint observations cannot observe every intermediate external state.
- **Concrete minimum fix:** None. Continue prohibiting “read-only mount” and continuous-immutability descriptions.
- **Claim affected:** Raw/provenance integrity and confinement interpretation.
- **Disposition:** Resolved.

## I03 — Structured finding adjudication

- **Severity:** Important historical finding; resolved structurally.
- **Plan section or short excerpt:** Final adjudication requires stable IDs, blocking flags, dispositions, rationales, and changed-path sets.
- **Why it matters:** Findings must not disappear, be deferred without disclosure, or be detached from the bytes changed in response.
- **Concrete minimum fix:** Add B12 to the next review and adjudication. Do not mark it rejected unless the exact packet-binding argument is technically refuted.
- **Claim affected:** Review closure and frozen-decision provenance.
- **Disposition:** Existing structure is adequate; B12 must now be carried through it.

## I04 — Exact local and target-host test execution evidence

- **Severity:** Important historical finding; fixed.
- **Plan section or short excerpt:** Exactly two self-hashed test receipts plus target qualification support receipts are authorization-bound.
- **Why it matters:** macOS skips cannot substitute for Linux/Landlock/CUDA execution, and test source is not execution evidence.
- **Concrete minimum fix:** None to the architecture. After B12’s source/test changes, regenerate both receipts using the same rules.
- **Claim affected:** Test execution provenance and target-host compatibility.
- **Disposition:** Fixed in the current packet; regeneration is required only because B12’s minimum repair changes source/test bytes.

## I05 — Third-party reproduction boundary

- **Severity:** Important historical finding; adequately scoped.
- **Plan section or short excerpt:** Raw tensors remain on the private network volume; the deliverable is an offline-verifiable retrieved bundle.
- **Why it matters:** A third party without the raw, model, J, and historical provenance bytes cannot independently recompute all scientific quantities.
- **Concrete minimum fix:** None. Use “offline-verifiable” or “receipt-verifiable,” not “public end-to-end reproduction.”
- **Claim affected:** Reproducibility.
- **Disposition:** Resolved by claim limitation.

## I06 — Independent units and repeated observations

- **Severity:** Important historical finding; resolved for this recovery.
- **Plan section or short excerpt:** The appendix identifies eight fixed `prompt_id` units, three directions, five doses, and prompt-level resampling.
- **Why it matters:** The 125 J-fitting prompts, 120 signed pairs, 96 gated pairs, and 4,872 readout rows are not corresponding numbers of independent study units.
- **Concrete minimum fix:** None. Preserve `prompt_id` as the bootstrap unit and the fixed-panel interval label.
- **Claim affected:** Estimand, uncertainty, power, and generalization.
- **Disposition:** Resolved.

## I07 — Runtime margin under the one-hour window

- **Severity:** Important historical finding; resolved by B10 evidence and retained as a run-time gate.
- **Plan section or short excerpt:** Authorization readiness at host age 958 leaves 2,642 seconds and an 842-second surplus over the required 1,800 seconds.
- **Why it matters:** The recovery must not issue authority after an operationally unusable staging period.
- **Concrete minimum fix:** None. Preserve the provider-creation-bound clock and fresh-pod minimum-remaining-time check.
- **Claim affected:** Operational feasibility and one-shot budget sufficiency.
- **Disposition:** Resolved as feasibility evidence, not as a guarantee that every host will be equally fast. A slower fresh host must stop before authorization.

## I08 — Fixed-panel limitations must remain visible

- **Severity:** Important historical finding; resolved as a claim-policy requirement.
- **Plan section or short excerpt:** “This is a fixed-panel stability calculation, not a prompt-population confidence interval.”
- **Why it matters:** Repeated doses, directions, layers, transports, and controls do not create broader prompt-population evidence.
- **Concrete minimum fix:** None. Preserve the exact eight-prompt panel, primary layer 50 and dose 0.03, conjunctive gates, descriptive-only later layers, no formal multiplicity adjustment, and no population generalization.
- **Claim affected:** Construct validity and prevention of post-result overstatement.
- **Disposition:** Resolved.

**New important findings:** none.

# What should remain unchanged

1. **The required-subset J repair.** Keep the physical checkpoint hash, `n_prompts=125`, `d_model=8192`, canonical key normalization, duplicate rejection, required-layer inclusion, and exact downstream filtering to layers 45–78. Do not replace it with a `0..78` whitelist.

2. **The downstream J metadata shape.** Keep only:
   ```json
   {
     "sha256": "...",
     "map_count": 34,
     "revision": "..."
   }
   ```
   in the frozen scientific metadata. Keep available, required, and unused-extra inventories only in recovery provenance.

3. **The scientific entry point and patch surface.** Continue invoking `audit.audit` once and limiting recovery monkeypatches to `_AuditBudgetWatchdog`, `_audit_external_receipt_chain`, and `_load_j_checkpoint`.

4. **The inherited scientific design.** Do not change prompts, directions, doses, hook location, intervention position, tokenization, branch semantics, orientation, final-normalization/LM-head readout, selected tokens, metrics, thresholds, layers, missingness, bootstrap, sign conventions, or claim gates.

5. **Temporal branch isolation.** Retain independent clean/plus/minus cache branches, capture-before-edit ordering, exact upstream equality, and no text/cache carryover between signed branches.

6. **Controls and falsification logic.** Preserve wrong-orientation controls, identity transport, five randomized-J controls, BF16-versus-FP32 shadow checks, signed common-mode checks, clean/upstream byte identity, and conjunctive eligibility gates.

7. **Statistical boundaries.** Preserve eight fixed prompt units, `prompt_id` resampling, 20,000 replicates, complete-inventory rejection, no imputation, no optional scientific stopping, no across-layer selection, and no population-confidence claim.

8. **Dual provenance.** Keep the original model-transaction chain and fresh recovery-compute chain separate. Keep the failed bind-mount host as historical evidence only.

9. **One-shot authority consumption.** Retain exclusive post-confinement Landlock receipt creation as authority consumption even if `execve`, bootstrap, or pre-marker validation subsequently fails.

10. **Direct same-PID confinement.** Keep direct absolute paths, `-B -E -s -S`, single-thread startup, no-site bootstrap, exact environment checks, import-root manifests, descriptor/mapping audits, `no_new_privs`, and same-PID `execve`.

11. **The ABI-4 policy.** Preserve:
    - handled mask `0x7ff2`;
    - two exact output rules with `0x1b2`;
    - `/proc/self/task` with `0x4002`;
    - one identity-bound NVIDIA character-device rule per enumerated file with `0x2`;
    - no device-directory wildcard; and
    - no unconfined fallback.

12. **The exact confinement wording.** Keep both exception classes visible and keep the limitations for metadata-only operations, pre-opened descriptors, sibling processes, other NFS clients, and device `ioctl`.

13. **The two-canary design.** Retain the preconfinement writable baseline, protected denial matrix, output allow/deny matrix, output-canary cleanup, and protected endpoint equality.

14. **Endpoint inventory semantics.** Keep raw and provenance pre/post byte-and-path equality while explicitly declining continuous immutability or read-only-mount claims.

15. **B10’s timed qualification evidence.** Keep the seven-file chain and its scope limitation. Do not relabel `source_test_qualification` as `final_recovery`; the later pod must repeat the final scope.

16. **Separate campaign clocks.** Do not rewrite the original campaign fields. Keep fresh authority solely under `recovery_execution_campaign`.

17. **Failure and publication semantics.** Preserve exclusive failure receipts, no success/`FAILURE.json` coexistence, quarantine after a missed final publication gate, exact three-file compact success publication, and external verification output.

18. **Offline verification.** Keep the standard-library-only verifier, exact receipt schemas, device identity decoding independent of verifier-host ABI, and the requirement that the retrieved bundle pass before scientific release.

# Minimal revised design

1. **Add the missing machine appendix to the provider packet.**
   - Add:
     `docs/consciousness_sae_target_blind_calibration/AUDIT_RECOVERY_SCIENTIFIC_EQUIVALENCE.json`
     to `PRO_REVIEW_V4_PACKET`.
   - Give it the next bounded-context role.
   - This makes the exact JSON bytes visible to the provider review and covered by the reviewed-packet Git-diff gate.

2. **Change only the focused packet-membership test.**
   - Remove the assertion that the JSON appendix is absent.
   - Assert that both the JSON and Markdown scientific-equivalence appendices are present.
   - Retain the rule that provider outputs are not recursively included as review inputs.

3. **Regenerate exact source/test receipts.**
   - Because `audit_recovery.py` and `test_audit_recovery.py` change, rerun the exact five-file focused suite locally and on the disposable target host.
   - Require the designated live Landlock test and all Torch-dependent loader/equivalence tests to pass on the target host.
   - Bind the new common code-freeze commit and source/test inventory.

4. **Preserve B10 rather than rerunning it unnecessarily.**
   - The timed qualification remains valid operational evidence if its exact seven files and scope limitation remain unchanged and the validator continues to bind them.
   - The fresh recovery pod must still run its own full `final_recovery` preflight before authorization.
   - If any timed-evidence byte is changed, review the replacement exact bytes.

5. **Regenerate review packet inventories and hashes.**
   - Rebuild the provider review request so its artifact inventory includes the machine JSON’s byte count and physical SHA-256.
   - Keep within the existing input and budget ceilings.
   - Obtain a new exact-byte review; the present response cannot authorize the changed packet.

6. **Do not alter the scientific or confinement design.**
   - No new model transaction.
   - No new prompt render.
   - No target feature extraction.
   - No changes to the J loader, audit calculation, policy masks, device exceptions, clocks, estimands, controls, or claim gates.

# Freeze checklist

- [ ] **B01:** Both machine and human scientific-equivalence appendices are included in the exact provider packet.
- [ ] **B02:** Launcher and bootstrap still use direct `-B -E -s -S` startup with no package-module restart or pre-guard site import.
- [ ] **B03:** Historical campaign fields remain unchanged and fresh authority remains separately named.
- [ ] **B04:** The J loader still applies literal required-subset semantics and filters downstream maps to exactly layers 45–78.
- [ ] **B06:** Downstream J metadata remains exactly `sha256`, `map_count=34`, and `revision`.
- [ ] **B07:** Terminal-verdict parsing still rejects negative, conditional, duplicate, absent, and misleading-prose cases.
- [ ] **B08/I04:** New local and target receipts bind the post-B12 source/test bytes, commands, dependencies, and node outcomes.
- [ ] **B09:** Producer and verifier retain the same `$25.00` completed-review ceiling.
- [ ] **B10:** The exact timed qualification remains bound with readiness at age 958, 2,642 seconds remaining, and 842 seconds surplus.
- [ ] **B10:** The timed qualification remains labeled `source_test_qualification`; the recovery pod must independently pass `final_recovery`.
- [ ] **B11:** Every precise confinement claim names both `/proc/self/task` and exact NVIDIA-device exceptions.
- [ ] **B12:** `AUDIT_RECOVERY_SCIENTIFIC_EQUIVALENCE.json` appears in `PRO_REVIEW_V4_PACKET` and the generated review artifact inventory.
- [ ] **B12:** The provider-review Git-chain check covers the machine JSON as a packet path.
- [ ] **B12:** No authorization is issued from this negative review or from any pre-fix review.
- [ ] **I01:** Zero-forward wording remains scoped to the approved process and executable closure.
- [ ] **I02:** Endpoint equality is not described as continuous immutability or a read-only mount.
- [ ] **I03:** The new adjudication includes all historical IDs and B12, with no deferred blocker.
- [ ] **I05:** Reproduction wording remains “offline-verifiable” or “receipt-verifiable.”
- [ ] **I06/I08:** The eventual result remains an eight-prompt fixed-panel claim with no prompt-population generalization.
- [ ] The original auditor and protocol hashes remain unchanged.
- [ ] The machine appendix regenerates exactly from the unchanged scientific-equivalence extractor and frozen plan/source bindings.
- [ ] The target qualification pod and later recovery pod are distinct.
- [ ] The fresh recovery pod independently repeats the same-host Landlock/CUDA gate with the final closure.
- [ ] The real preflight and execution bind the same Python binary, import-root manifest, source closure, device inventory, and device identities.
- [ ] No inherited protected, canary, NVIDIA, writable regular-file/directory, writable unsafe-device, shared file-backed mapping, or `io_uring` escape exists.
- [ ] The exact `0x7ff2`, `0x1b2`, `0x4002`, and `0x2` values remain unchanged.
- [ ] Both canary matrices pass and the disposable output canary is empty afterward.
- [ ] The exclusive Landlock receipt is created only after confinement and consumes authority before same-PID `execve`.
- [ ] The attempt marker is exclusive and no alternate output namespace or retry exists under the same authority.
- [ ] Raw and historical-provenance file and directory inventories match at both endpoints.
- [ ] No success publication occurs at or after the recovery deadline.
- [ ] The compact directory contains exactly the audit, summary, and publication marker, with no `FAILURE.json`.
- [ ] The retrieved bundle passes the standard-library-only offline verifier before any scientific claim is released.
