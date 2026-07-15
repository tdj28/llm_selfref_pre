# Verdict

The supplied v5 packet closes the sole v4 blocker without changing the scientific estimand or confinement design. In particular:

- **B12 is repaired on the supplied bytes.** The machine-readable `AUDIT_RECOVERY_SCIENTIFIC_EQUIVALENCE.json` is now artifact 3 of the exact provider packet, is explicitly present in `PRO_REVIEW_V5_PACKET`, and is therefore included in the provider artifact manifest and reviewed-packet Git-diff closure. The focused packet-membership test now requires both JSON and Markdown appendices.
- **Fresh qualification receipts bind the repaired source/test freeze.** The local and target receipts both name code-freeze commit `b0dd6fc9e098709e0301cc72aed3849208ab4f0a`, source/test inventory SHA-256 `8c8ed32838bf47d68fd5b85306a9678d5df342b4387a9b5796d9d9c0e1027324`, `audit_recovery.py` SHA-256 `41efc20c9a151c4bebaebca5344768f26b29e07fcce6eda75a367f33c411587c`, and `test_audit_recovery.py` SHA-256 `b8205ed6391f3d0ba74e8cb62ace5f17052d30374c06f68fa9c42556c531545a`. Those hashes match the corresponding supplied packet artifacts.
- **Target-host evidence is positive rather than skipped.** The target receipt reports 190 collected and 190 passed tests, including the designated live same-PID Landlock test, Torch-dependent loader tests, scientific-equivalence tests, and verifier tests. The qualification support files in artifacts 31–33 match the file hashes embedded in that target receipt.
- **The narrow J correction remains scientifically appropriate.** The loader requires every layer 45–78, filters the mapping passed to the frozen auditor to exactly those 34 maps, preserves the frozen `sha256`/`map_count=34`/`revision` metadata shape, and records the full available inventory only in recovery provenance. This matches the original runtime’s required-subset semantics and does not justify a new model transaction.
- **Temporal provenance remains separated.** Original model-execution authority, the failed bind-mount recovery host, the disposable target qualification host, and the future fresh recovery host have distinct roles and identities. Historical campaign fields are preserved while fresh recovery authority has its own provider-creation-bound clock.
- **The confinement claim is appropriately narrow.** The supplied design supports process-tree confinement of handled ABI-4 filesystem content/topology mutations, not a read-only mount or continuous external immutability claim. Both exception classes—`/proc/self/task` `WRITE_FILE|TRUNCATE` and identity-bound NVIDIA character-device `WRITE_FILE`—are consistently disclosed, and metadata operations, pre-opened descriptors, sibling processes, other NFS clients, and device `ioctl` effects remain outside the claim.
- **B10 remains adequate feasibility evidence.** The exact seven-file chain records authorization readiness at host age 958 seconds after rehashing 45 files and 156,023,372,845 bytes, leaving 2,642 seconds and an 842-second surplus over the required 1,800-second reserve. Its `source_test_qualification` scope is not misrepresented; the future recovery pod must independently repeat `final_recovery`.

This approval is limited to the exact packet bytes identified in the supplied artifact inventory, including plan SHA-256 `c1bcb3334065933bd49b27499ecc23a7af539c37f3afda7efce14d08540eb39c`, machine-equivalence appendix SHA-256 `f340c97000b2867ef86a73e9d7107bd01d8730339a9571568cc985b039195423`, recovery source SHA-256 `41efc20c9a151c4bebaebca5344768f26b29e07fcce6eda75a367f33c411587c`, verifier SHA-256 `e2e45c252ca5adcabd7d77ebd23d626080756d35589c601a4c75e7899e3224eb`, local receipt SHA-256 `3a570bc92a15c298a572deb1123fd3a07d1dd779e8224fb82c57ee1d0de86767`, and target receipt SHA-256 `76dff49824b0933a33ffdc8a5facfe9ef7495c95f201900560a99d4032a6c1c7`. I do not claim to have inspected repository files or remote-volume contents not included in the packet. Any packet-changing fix, source change, test change, regenerated appendix, or replacement receipt would fall outside this verdict and require another exact-byte review.

READY TO FREEZE

# Blocking findings

## B01 — Historical whole-audit scientific-equivalence gap

- **Severity:** Historical blocker; resolved on the supplied v5 bytes.
- **Plan section or short excerpt:** “The outcome-blind `AUDIT_RECOVERY_SCIENTIFIC_EQUIVALENCE.{json,md}` appendix mechanically binds the frozen plan/source bytes…”
- **Why it matters:** A post-run correction is admissible only if hook semantics, positions, tokenization, J orientation, selected maps, final-normalization/LM-head readout, aggregation, bootstrap, thresholds, and claim gates remain frozen.
- **Concrete minimum fix:** None. Preserve the supplied scientific-equivalence extractor, affirmative projection, source hashes, one invocation of `audit.audit`, and the three named monkeypatch targets.
- **Claim affected:** Scientific equivalence of the recovered audit to the frozen r3 auditor apart from the required-subset compatibility predicate.
- **Disposition:** Fixed. The machine appendix is now supplied as artifact 3, self-identifies as outcome-blind, binds the scientific source closure and measurement contract, and is included in the exact provider packet.

## B02 — Historical pre-guard startup-code gap

- **Severity:** Historical blocker; resolved.
- **Plan section or short excerpt:** “`python -B -E -s -S /absolute/path/to/landlock_launcher.py`”; same-PID direct execution of `confined_bootstrap.py`.
- **Why it matters:** `site`, `.pth`, `sitecustomize`, package initialization, or an unconstrained child restart could otherwise execute code before confinement and model-forward guards.
- **Concrete minimum fix:** None. Retain direct-script invocation, all four interpreter flags, startup environment rejection, complete import-root inventory, ordered `sys.path`, guard priming, and same-PID `execve`.
- **Claim affected:** Deterministic startup, executable closure, leakage prevention, and scoped zero-forward evidence.
- **Disposition:** Fixed. The launcher and bootstrap validate no-site startup, and the target receipt reports the designated live same-PID test as passed.

## B03 — Historical campaign-clock semantic overwrite

- **Severity:** Historical blocker; resolved.
- **Plan section or short excerpt:** “The recovered audit preserves the original top-level `campaign_started_at_unix`, `campaign_deadline_at_unix`, and `hourly_price_usd` fields…”
- **Why it matters:** Replacing historical fields with recovery timing would conflate the original model transaction with the later technical audit.
- **Concrete minimum fix:** None. Preserve the top-level historical fields, `original_execution_campaign`, separate `recovery_execution_campaign`, and publication marker’s `recovery_deadline_at_unix`.
- **Claim affected:** Temporal provenance and separation of model execution from recovery computation.
- **Disposition:** Fixed by `_enrich_outputs`, `_publish_recovery_pair_atomic`, focused tests, and corresponding offline-verifier checks.

## B04 — Historical required-subset versus exact-release whitelist contradiction

- **Severity:** Historical blocker; resolved.
- **Plan section or short excerpt:** `_load_j_checkpoint_recovery` applies `set(required) <= set(available)` and constructs a filtered mapping over `protocol.J_LAYERS`.
- **Why it matters:** An exact `0..78` whitelist would contradict the stated required-subset correction, while passing every available map downstream could change scientific behavior or metadata.
- **Concrete minimum fix:** None. Keep canonical layer-key normalization, duplicate rejection, missing-required-layer rejection, and exact downstream filtering to layers 45–78.
- **Claim affected:** Narrowness and comparability of the J-checkpoint correction.
- **Disposition:** Fixed. The implementation matches the original runtime predicate and tests both the authentic `0..78` inventory and arbitrary harmless extras.

## B06 — Loader tests contradicted the preserved downstream metadata schema

- **Severity:** Historical blocker; resolved.
- **Plan section or short excerpt:** The recovered loader returns only `sha256`, `map_count=len(required)`, and `revision`; full inventory is stored through `_OBSERVED_J_INVENTORY`.
- **Why it matters:** Adding recovery inventory fields to `artifact_recomputation.j_lens` would alter an affirmatively projected scientific field.
- **Concrete minimum fix:** None. Keep the complete available/required/extra inventory exclusively in `recovery_audit.j_checkpoint_inventory`.
- **Claim affected:** Scientific-output equivalence and test validity.
- **Disposition:** Fixed. The supplied source and tests consistently preserve `map_count=34`, and the target receipt reports all Torch-dependent tests passed.

## B07 — Negative provider verdict could satisfy substring readiness parsing

- **Severity:** Historical blocker; resolved.
- **Plan section or short excerpt:** `_terminal_review_verdict` requires one `# Verdict` section, one recognized terminal verdict, and that verdict as the section’s final nonempty line.
- **Why it matters:** `NOT READY TO FREEZE` lexically contains `READY TO FREEZE`; substring parsing could authorize a negative review.
- **Concrete minimum fix:** None. Retain exact verdict parsing, duplicate-verdict rejection, and structured adjudication.
- **Claim affected:** Review closure and authorization legitimacy.
- **Disposition:** Fixed. Tests cover negative, conditional, positive, misleading-prose, and multiple-verdict cases.

## B08 — Test receipts were not representable in authorization or offline verification

- **Severity:** Historical blocker; resolved.
- **Plan section or short excerpt:** Local and target receipts plus three target qualification support receipts are carried through review snapshots, authorization, recovery metadata, and the offline verifier.
- **Why it matters:** Source hashes alone do not show that the exact suite ran locally and on a compatible target host.
- **Concrete minimum fix:** None. Preserve code-freeze commits, source/test inventories, commands, dependencies, complete node outcomes, support-file physical hashes, and the designated live-test requirement.
- **Claim affected:** Test provenance, target-host compatibility, and deterministic offline admissibility.
- **Disposition:** Fixed. Both supplied receipts bind the same code freeze and source/test inventory; the target receipt records 190 passed, zero failed, zero skipped, and zero not-run tests.

## B09 — Producer and verifier used different completed-review cost ceilings

- **Severity:** Historical blocker; resolved.
- **Plan section or short excerpt:** Producer and verifier both use a `$25.00` completed-review ceiling.
- **Why it matters:** Different ceilings could create a bundle accepted during production but permanently rejected offline.
- **Concrete minimum fix:** None. Keep both constants equal and retain exact-boundary and over-boundary tests.
- **Claim affected:** Budget consistency and offline admissibility.
- **Disposition:** Fixed in the supplied source and tests.

## B10 — Historical timing evidence missed the one-hour recovery envelope

- **Severity:** Historical blocker; resolved as feasibility evidence.
- **Plan section or short excerpt:** The seven-file chain reports readiness at host age 958 seconds, 2,642 seconds remaining, and an 842-second surplus over the issuance reserve.
- **Why it matters:** The one-shot authority must not issue after setup, a full 156 GB rehash, manifest construction, and Landlock/CUDA checks have left an unusably short execution window.
- **Concrete minimum fix:** None. Preserve the exact chain, 1,800-second minimum-remaining gate, and mandatory same-host `final_recovery` repetition on the fresh recovery pod.
- **Claim affected:** Operational feasibility, one-shot authority, and the provider-creation-bound budget.
- **Disposition:** Fixed. The supplied seven files support the stated 958/2,642/842 timing calculation and the 45-file, 156,023,372,845-byte rehash. This is feasibility evidence, not permission to waive the fresh-pod gate.

## B11 — Precise confinement statement omitted the `/proc/self/task` exception

- **Severity:** Historical blocker; resolved.
- **Plan section or short excerpt:** “The precise claim” now names both `/proc/self/task` `WRITE_FILE|TRUNCATE` and individually enumerated NVIDIA character-device `WRITE_FILE` exceptions.
- **Why it matters:** Omitting a real write exception from the sentence labeled precise would support an overstated confinement claim.
- **Concrete minimum fix:** None. Keep both exception classes and all limitations in the plan, recovery metadata, and verifier.
- **Claim affected:** Interpretation of process-tree handled-write confinement.
- **Disposition:** Fixed. The plan, `LANDLOCK_POLICY`, recovery claim text, and offline verifier are aligned.

## B12 — Machine-readable scientific-equivalence appendix omitted from exact-byte closure

- **Severity:** Historical v4 blocker; definitively fixed in the supplied v5 packet.
- **Plan section or short excerpt:** `PRO_REVIEW_V5_PACKET` includes `AUDIT_RECOVERY_SCIENTIFIC_EQUIVALENCE.json` as bounded context 2; the supplied packet includes it as artifact 3 with SHA-256 `f340c97000b2867ef86a73e9d7107bd01d8730339a9571568cc985b039195423`.
- **Why it matters:** The machine appendix is central evidence for B01. Under v4 it could have changed after testing or review while still being newly bound at authorization.
- **Concrete minimum fix:** None. Preserve its packet membership, reviewed-packet Git-diff coverage, exact regeneration test, and the fresh local/target receipt lineage.
- **Claim affected:** Exact-byte scientific-equivalence evidence, B01 closure, and the statement that provider-reviewed final bytes remain unchanged.
- **Disposition:** Fixed exactly as required. The inclusion test now requires both appendices; the source changes are bound by fresh local and target receipts from common code-freeze commit `b0dd6fc9e098709e0301cc72aed3849208ab4f0a`.

**New blocking findings B13 or later:** none.

# Important non-blocking findings

## I01 — Scope of zero-forward evidence

- **Severity:** Important historical finding; resolved by narrow wording.
- **Plan section or short excerpt:** “This is not an OS-wide detector for arbitrary bespoke native callables, sibling processes, or device `ioctl` effects.”
- **Why it matters:** Torch and Transformers guards cannot establish the absence of every hypothetical native model implementation outside the approved closure.
- **Concrete minimum fix:** None. Keep the claim as a conjunction of exact import roots, runner/runtime exclusion, startup denial, process-lifetime guards, inner guards, and target-free CUDA preflight.
- **Claim affected:** Zero new model forwards in the approved recovery process and executable closure.
- **Disposition:** Resolved.

## I02 — Endpoint equality is not continuous external immutability

- **Severity:** Important historical finding; resolved.
- **Plan section or short excerpt:** Pre/post inventories “do not… prove continuous immutability between the two observations [or] exclude a sibling process or another NFS client.”
- **Why it matters:** Landlock constrains the process tree, while endpoint hashes cannot observe every intermediate action by external actors.
- **Concrete minimum fix:** None. Continue prohibiting read-only-mount and continuous-immutability descriptions.
- **Claim affected:** Raw/provenance integrity and confinement interpretation.
- **Disposition:** Resolved.

## I03 — Structured finding adjudication

- **Severity:** Important historical finding; resolved structurally.
- **Plan section or short excerpt:** Final adjudication requires stable IDs, blocking flags, dispositions, rationales, and changed-path sets.
- **Why it matters:** Findings must not disappear, be renumbered, or be silently deferred after packet changes.
- **Concrete minimum fix:** None. The final adjudication should record B12 as fixed on the exact supplied packet and retain every historical ID.
- **Claim affected:** Review lineage and frozen-decision provenance.
- **Disposition:** Resolved by the supplied validator and tests.

## I04 — Exact local and target-host test execution evidence

- **Severity:** Important historical finding; resolved.
- **Plan section or short excerpt:** Exactly two self-hashed test receipts plus target qualification support receipts are authorization-bound.
- **Why it matters:** Local macOS skips cannot substitute for Linux/Landlock/CUDA execution.
- **Concrete minimum fix:** None. Preserve the supplied receipt bytes and their target support files.
- **Claim affected:** Test execution provenance and target compatibility.
- **Disposition:** Fixed. Local skips are disclosed; the target run passes every collected test.

## I05 — Third-party reproduction boundary

- **Severity:** Important historical finding; adequately scoped.
- **Plan section or short excerpt:** Raw tensors remain on a private network volume; the intended deliverable is an offline-verifiable retrieved bundle.
- **Why it matters:** A third party lacking the raw, model, J, and historical provenance bytes cannot independently recompute every scientific quantity.
- **Concrete minimum fix:** None. Use “offline-verifiable” or “receipt-verifiable,” not “public end-to-end reproduction.”
- **Claim affected:** Reproducibility.
- **Disposition:** Resolved by claim limitation.

## I06 — Independent units and repeated observations

- **Severity:** Important historical finding; resolved for the recovery.
- **Plan section or short excerpt:** Independent unit `prompt_id`; eight fixed units; three directions and five doses per prompt.
- **Why it matters:** The 125 J-fitting prompts, 120 signed pairs, 96 gated pairs, and 4,872 readout rows are not corresponding counts of independent study units.
- **Concrete minimum fix:** None. Preserve prompt-level resampling and the fixed-panel stability-interval label.
- **Claim affected:** Estimand, uncertainty, power, and generalization.
- **Disposition:** Resolved.

## I07 — Runtime margin remains a gate, not a guarantee

- **Severity:** Important historical finding; resolved as feasibility evidence.
- **Plan section or short excerpt:** The timed qualification leaves 2,642 seconds, 842 seconds beyond the 1,800-second minimum.
- **Why it matters:** A future host may be slower than the qualification host.
- **Concrete minimum fix:** None. If fewer than 1,800 seconds remain after the fresh host’s complete preflight, stop before authorization.
- **Claim affected:** Operational feasibility and one-shot budget sufficiency.
- **Disposition:** Resolved with the stated limitation.

## I08 — Fixed-panel limitations must remain visible

- **Severity:** Important historical finding; resolved as a claim-policy requirement.
- **Plan section or short excerpt:** “This is a fixed-panel stability calculation, not a prompt-population confidence interval.”
- **Why it matters:** Directions, doses, layers, transports, and controls do not create additional prompt-level independent units or population-generalizable evidence.
- **Concrete minimum fix:** None. Preserve the eight-prompt scope, sole primary layer 50, primary dose 0.03, descriptive status of layers 51–78, and lack of a formal multiplicity adjustment.
- **Claim affected:** Construct validity and prevention of post-result overstatement.
- **Disposition:** Resolved.

**New important findings I09 or later:** none.

# What should remain unchanged

1. **Required-subset J correction**
   - Physical checkpoint hash remains `335056c17f0c24053c8c8c1eff168ef49e5a62ca590ffc29c84cf352ecd3ab03`.
   - Require `n_prompts=125`, `d_model=8192`, and every layer 45–78.
   - Reject noncanonical or duplicate normalized layer keys.
   - Pass exactly 34 required maps downstream.
   - Do not introduce an exact `0..78` release whitelist.

2. **Scientific metadata separation**
   - Keep `artifact_recomputation.j_lens` limited to `sha256`, `map_count=34`, `revision`, and its existing path enrichment.
   - Keep available/required/unused-extra inventories in recovery provenance only.

3. **Frozen scientific entry point**
   - Invoke `audit.audit` exactly once.
   - Limit monkeypatches to `_AuditBudgetWatchdog`, `_audit_external_receipt_chain`, and `_load_j_checkpoint`.
   - Keep the original `audit.py` and protocol hashes unchanged.

4. **Hook, token, and readout semantics**
   - Block-50 output, post-block/pre-block-51 hook boundary.
   - Capture-before-edit ordering.
   - Last rendered generation-prompt token as the edited token.
   - Prefix `token_ids[0:-1]`, one-token continuation, independent branch-cache clones.
   - Explicit post-edit block-50 output as the primary source coordinate.
   - Released J orientation `residual_delta @ J_l.T`.
   - Final RMSNorm and LM-head selected-token readout semantics.

5. **Temporal carryover controls**
   - Independent clean, plus, and minus branches.
   - Shared prefix values but independent cache objects.
   - Exact pre-edit equality and layers 45–49 upstream equality.
   - No reuse of generated continuation text and no target prompt rendering.

6. **Controls and falsification logic**
   - Wrong-orientation control.
   - Identity transport.
   - Five frozen randomized-J transports.
   - BF16 production versus FP32 shadow.
   - Signed common-mode control.
   - Native post-edit byte equality.
   - Conjunctive claim gates and fixed sign conventions.

7. **Statistical boundaries**
   - Eight fixed `prompt_id` units.
   - Prompt-level resampling with 20,000 replicates.
   - No imputation or outcome-based exclusion.
   - Missing, duplicate, extra, nonfinite, or partial data reject the audit.
   - No optional stopping or across-layer selection.
   - No prompt-population confidence claim or increased-power claim.

8. **Dual and historical provenance**
   - Keep original model-execution provenance separate from fresh recovery provenance.
   - Keep the first recovery host as historical failure evidence only.
   - Keep the disposable target qualification pod distinct from the future recovery pod.

9. **One-shot authority**
   - Exclusive post-confinement Landlock receipt consumes authority before `execve`.
   - Exclusive attempt marker remains the second one-shot barrier.
   - No alternate durable output namespace or retry under the same authority.

10. **Direct same-PID startup**
    - Absolute script paths.
    - `-B -E -s -S`.
    - Single-thread launcher.
    - No project/ML import before confinement.
    - Complete import-root manifests and ordered `sys.path`.
    - Same-PID `execve`.
    - Process-lifetime import and model-call guards.

11. **Landlock policy**
    - Handled mask `0x7ff2`.
    - Two output-directory rules with `0x1b2`.
    - Exact `/proc/self/task` rule with `0x4002`.
    - One exact NVIDIA character-device rule per authorized file with `0x2`.
    - No `/dev` directory rule, wildcard, broader `/proc` rule, or unconfined fallback.

12. **Confinement limitations**
    - Metadata-only operations remain outside ABI-4 handling.
    - Pre-opened descriptors require a separate audit.
    - Sibling processes and other NFS clients remain outside the process-tree claim.
    - NVIDIA `ioctl` effects remain outside Landlock’s filesystem-content/topology claim.

13. **Descriptor and mapping checks**
    - Reject inherited descriptors into raw, provenance, canary, or NVIDIA-device paths.
    - Reject all inherited writable regular-file or directory descriptors, including output-root descriptors.
    - Reject non-stdio writable character/block devices.
    - Reject `io_uring`.
    - Reject every shared file-backed mapping, including read-only shared mappings.

14. **Two-canary design**
    - Preconfinement writable baseline.
    - Full protected denial matrix.
    - Output allow/deny matrix.
    - Empty output canary after testing.
    - Protected canary byte/topology equality.

15. **Endpoint inventories**
    - Exact raw and historical-provenance file and directory inventories before and after the scientific audit.
    - Endpoint equality only; do not upgrade it to continuous immutability.

16. **B10 evidence and fresh-host repetition**
    - Preserve the exact seven historical files and their hashes.
    - Keep `source_test_qualification` labeling.
    - Require the future fresh host to pass `final_recovery` with the complete current closure and exact current device identities.

17. **Campaign and publication semantics**
    - Preserve historical campaign fields.
    - Keep recovery timing in `recovery_execution_campaign`.
    - Keep `PUBLICATION_COMPLETE.json` bound to `recovery_deadline_at_unix`.
    - Quarantine a published directory if a final watchdog check fails.

18. **Failure semantics**
    - No scientific success bundle on any failed gate.
    - Exclusive failure receipt after a catchable post-marker failure.
    - No successful compact directory coexisting with `FAILURE.json`.
    - Preserve external lifecycle and termination evidence.

19. **Offline verification**
    - Standard-library-only verifier.
    - No network access.
    - Verification output outside the retrieved bundle.
    - No scientific release until the retrieved bundle passes verification.

# Minimal revised design

No design revision is required. The smallest decisive design is the supplied one:

1. **Freeze the exact v5 packet bytes.**
   - Do not edit the plan, recovery source, launcher, bootstrap, verifier, tests, machine appendix, Markdown appendix, local receipt, target receipt, or target qualification support files after this review.
   - Treat any edit—even evidence-only—as a new packet requiring a successor review.

2. **Create one distinct fresh recovery pod.**
   - One B200 in `US-CA-2`.
   - Network volume `bv9gb9j32y`.
   - Provider-creation-bound one-hour/$6 recovery envelope.
   - Distinct from qualification pod `qdoau4e5ztmfqx` and all historical pods.

3. **Stage and revalidate the exact frozen closure.**
   - Exact Git lineage and live remote equality.
   - Exact source/test and reviewed-packet Git-diff closure.
   - Exact reviewed local and target receipt copies.
   - Exact historical provenance tree.
   - Complete 45-file, 156,023,372,845-byte public-artifact rehash.
   - Complete active and dependency import-root inventory.

4. **Run the fresh-host preauthorization gate with `final_recovery`.**
   - Resolve the closed current-host NVIDIA device set.
   - Bind canonical path, file type, `st_dev`, `st_ino`, `st_rdev`, major, and minor.
   - Run ABI-4 canary enforcement and target-free BF16 CUDA arithmetic under the exact policy.
   - Stop before authorization if any check differs or if fewer than 1,800 seconds remain.

5. **Issue one exact authorization.**
   - Bind the fresh ownership/guest/cache receipts, preflight receipts, device identities, command, attempt namespace, source closure, review evidence, deadline, and spend ceiling.
   - Permit zero model forwards, zero target renders, zero target feature vectors, and no external/prior scientific outcomes.

6. **Execute once through the direct launcher and same-PID bootstrap.**
   - Consume authority with the exclusive post-confinement receipt.
   - Validate authorization and claim the exclusive attempt marker.
   - Rehash raw and provenance trees.
   - Invoke the unchanged scientific auditor once with only the required-subset loader correction.
   - Rehash both protected trees again before publication.

7. **Publish or fail atomically.**
   - Success: exactly audit, summary, and publication marker in the compact directory.
   - Failure: no compact scientific success and an exclusive failure receipt where catchable.
   - Terminate the exact owned pod after evidence retrieval.

8. **Verify offline before release.**
   - Run the supplied verifier on the retrieved bundle.
   - Release only the fixed-panel, post-run technical-recovery claim supported by the frozen claim gates.
   - Do not imply same-pod auditing, population generalization, continuous immutability, or public end-to-end reproduction.

# Freeze checklist

- [ ] The exact packet plan hash remains `c1bcb3334065933bd49b27499ecc23a7af539c37f3afda7efce14d08540eb39c`.
- [ ] The exact machine-equivalence appendix hash remains `f340c97000b2867ef86a73e9d7107bd01d8730339a9571568cc985b039195423`.
- [ ] The exact recovery source hash remains `41efc20c9a151c4bebaebca5344768f26b29e07fcce6eda75a367f33c411587c`.
- [ ] The exact recovery verifier hash remains `e2e45c252ca5adcabd7d77ebd23d626080756d35589c601a4c75e7899e3224eb`.
- [ ] The exact local receipt hash remains `3a570bc92a15c298a572deb1123fd3a07d1dd779e8224fb82c57ee1d0de86767`.
- [ ] The exact target receipt hash remains `76dff49824b0933a33ffdc8a5facfe9ef7495c95f201900560a99d4032a6c1c7`.
- [ ] Both receipts retain code-freeze commit `b0dd6fc9e098709e0301cc72aed3849208ab4f0a`.
- [ ] Both receipts retain source/test inventory SHA-256 `8c8ed32838bf47d68fd5b85306a9678d5df342b4387a9b5796d9d9c0e1027324`.
- [ ] B01–B04 and B06–B12 are present in final adjudication with the dispositions above.
- [ ] I01–I08 are present in final adjudication with the dispositions above.
- [ ] No new B13+ or I09+ finding is silently introduced, omitted, or renumbered.
- [ ] `AUDIT_RECOVERY_SCIENTIFIC_EQUIVALENCE.json` remains in `PRO_REVIEW_V5_PACKET`.
- [ ] Both scientific-equivalence appendices remain covered by the reviewed-packet Git-diff gate.
- [ ] The checked-in machine appendix regenerates exactly from the frozen extractor and source bytes.
- [ ] The original auditor SHA-256 remains `271f4f17a5ed66eaff43dc63f5a02d7ce45cdfd4a3c6a5b5c03bac33cf96a465`.
- [ ] The J checkpoint SHA-256 remains `335056c17f0c24053c8c8c1eff168ef49e5a62ca590ffc29c84cf352ecd3ab03`.
- [ ] J metadata remain `n_prompts=125` and `d_model=8192`.
- [ ] The loader requires all and only passes through layers 45–78.
- [ ] Scientific J metadata retain `map_count=34`.
- [ ] Extra maps are recorded only in recovery provenance.
- [ ] Hook location, edited token, continuation length, branch-cache contract, orientation, and LM-head readout semantics are unchanged.
- [ ] The primary estimand remains layer 50, dose 0.03, on the exact eight-prompt fixed panel.
- [ ] Layers 51–78 remain descriptive only.
- [ ] Prompt-level resampling and the fixed-panel interval label remain unchanged.
- [ ] No prompt-population confidence or increased-power claim is made.
- [ ] The exact seven-file B10 timed qualification chain remains unchanged and bound.
- [ ] The timed qualification remains labeled `source_test_qualification`.
- [ ] The fresh recovery pod is distinct from qualification pod `qdoau4e5ztmfqx`.
- [ ] The fresh recovery pod independently runs `final_recovery`.
- [ ] The full 45-file, 156,023,372,845-byte public-artifact tree is rehashed on the fresh pod.
- [ ] At least 1,800 seconds remain before fresh authorization issuance.
- [ ] The fresh host reports Landlock ABI 4 or newer.
- [ ] The exact policy values remain `0x7ff2`, `0x1b2`, `0x4002`, and `0x2`.
- [ ] Every current-host NVIDIA exception is a canonical identity-bound character-device file.
- [ ] No `/dev` directory, wildcard-device, or broader `/proc` rule is added.
- [ ] The launcher begins single-threaded under direct `-B -E -s -S` startup.
- [ ] No unsafe environment variable is present.
- [ ] No protected, canary, NVIDIA, writable regular/directory, unsafe writable-device, `io_uring`, or shared file-backed descriptor/mapping escape is inherited.
- [ ] Both preauthorization and execution canary matrices pass.
- [ ] The canary protected subtree has a successful writable baseline before confinement.
- [ ] The canary output subtree is empty after testing.
- [ ] The exclusive Landlock receipt is written only after confinement.
- [ ] The Landlock receipt consumes authority before same-PID `execve`.
- [ ] The same PID survives into the confined bootstrap.
- [ ] The process-lifetime import/model guards remain installed and record zero firings.
- [ ] The attempt marker is exclusive and commit-scoped.
- [ ] Raw and provenance file and directory inventories match at both endpoints.
- [ ] Endpoint equality is not described as continuous immutability.
- [ ] No model forward, target prompt render, target feature extraction, or external/prior outcome input occurs.
- [ ] Historical campaign fields remain unchanged.
- [ ] Fresh recovery authority remains under `recovery_execution_campaign`.
- [ ] No compact success is published at or after the recovery deadline.
- [ ] A successful compact directory contains exactly three files and no `FAILURE.json`.
- [ ] Every catchable post-marker failure produces the exclusive failure receipt and no scientific success bundle.
- [ ] The exact fresh pod is terminated after retrieval or failure handling.
- [ ] The retrieved bundle passes the standard-library-only offline verifier before any scientific claim is released.
