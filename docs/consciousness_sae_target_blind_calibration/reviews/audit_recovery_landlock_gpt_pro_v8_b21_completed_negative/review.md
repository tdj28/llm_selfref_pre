# Verdict

The scientific recovery itself remains narrowly and appropriately defined: a post-run audit-only technical recovery of the immutable r3 raw transaction, with no new model forward and only one compatibility change—accepting a hash-pinned J-checkpoint superset while selecting exactly required layers 45–78. The intervention coordinate, token position, cache contract, sign convention, Jacobian orientation, final-RMSNorm/LM-head readout, estimands, controls, fixed-panel unit definition, thresholds, and claim gates remain adequately frozen. I found no new scientific-design defect requiring a fresh model transaction.

The B20 repair is conceptually and operationally sound. The current code places live Git ancestry and diff checks in `SOURCE`, seals the exact final HEAD into the self-hashed authorization, and calls final validation in repository-free `ACTIVE` with `validate_git=False`. It does not add a `/dev/null` write exception. The independent verifier cross-checks the authorization’s sealed final commit and byte/semantic closure without requiring a repository. This is the smallest correct repair to B20.

The supplied C11 receipts are positive quoted evidence for commit `d9515de042e2f1e514a3f1f41fbf3d8d2c205e8a` and source/test inventory SHA-256 `b08aef15d6e6996f6a0a52ca1b3dba27affa957f792ec3a1659715f7274e999a`. The target receipt reports 228/228 tests passed, including the designated live Linux Landlock same-PID test, and records a B200 CUDA/Landlock qualification with zero model forwards. I have not independently executed those tests or inspected files absent from the packet.

There is, however, one new exact-packet blocker. `FINAL_RECOVERY_WRAPPER_PATHS` contains six paths, and the C11 receipts identify all six as source/test bytes, but `_PRO_REVIEW_V8_PATHS` includes only `FINAL_RECOVERY_WRAPPER_PATHS[:4]`. Consequently, the prospective v8 provider packet omits the exact contents of:

- `experiments/consciousness_sae_target_blind_calibration/FINAL_RECOVERY_INVOCATION_CONTRACT.md`; and
- `experiments/consciousness_sae_target_blind_calibration/final_recovery_wrapper_self_test.py`.

The second omitted file is executed by a supplied test, and both are included in `AUDIT_EXECUTABLE_PATHS`, `SOURCE_TEST_BOUND_PATHS`, `RECOVERY_BOUND_PATHS`, the qualification receipts, and the final staged `ACTIVE` closure. A v8 approval would therefore cause the authorization to state that the final source and tests were provider-reviewed even though two bound current paths were outside the review packet. This is the same class of exact-byte closure problem previously treated as blocking for the machine scientific-equivalence JSON.

The packet also retains stale opening status text saying execution awaits the “final v7” review of “C10/E10” bytes. The later v8 section clearly supersedes it, so this does not independently defeat the mechanics, but it should be corrected while reopening the packet to prevent contradictory launch interpretation.

Because fixing the packet inventory changes `audit_recovery.py` and the plan text, it cannot be hidden in F11. A successor code freeze, fresh local and disposable-B200 qualification receipts, and a successor exact-byte review are required. No scientific rerun or redesign is required.

NOT READY TO FREEZE

# Blocking findings

## B17 — SOURCE/ACTIVE bootstrap binding mismatch

- **Severity:** Historical blocker; fixed on the current supplied source.
- **Plan section or short excerpt:** “V8 keeps every live-repository check at issue time in SOURCE…” and the controller’s split-root issue bridge loads the physical `ACTIVE/.../confined_bootstrap.py` before importing the issuer from `SOURCE`.
- **Why it matters:** The import-root manifest deliberately requires the running bootstrap’s physical `__file__` to be under `ACTIVE`, while canonical Git, plan, review, and provenance checks require the issuer to remain rooted in `SOURCE`. The prior path could not satisfy both requirements.
- **Concrete minimum fix:** Already implemented. Preserve the current split-root bridge:
  - issuer cwd and `REPO_ROOT` remain in `SOURCE`;
  - source and active bootstrap hashes are checked;
  - the physical active bootstrap is loaded under its canonical module name;
  - `audit_recovery.confined_bootstrap is active_bootstrap` is required;
  - only parsed command `issue` is dispatched; and
  - the final confined child still executes the active bootstrap directly with `-B -E -s -S`.
- **Claim affected:** Feasibility and identity of issue-time authorization, active-root manifest validity, and separation of repository checks from confined execution.
- **Disposition:** Fixed. Do not replace it with `cd ACTIVE`, a `__file__` monkeypatch, `GIT_WORK_TREE=ACTIVE`, or copied Git metadata.

## B18 — Failed-attempt cleanup and zero-artifact evidence

- **Severity:** Historical missing-evidence blocker; mechanically closed by the supplied compact evidence.
- **Plan section or short excerpt:** `B18_CLOSURE_RECEIPT.json` records six recursively absent artifact basenames, a zero-file designated output tree, ownership and termination attachments, and unchanged pre/post account inventories.
- **Why it matters:** Without inspectable cleanup evidence, a later attempt could ambiguously overlap a prior authorization, output namespace, or still-running pod.
- **Concrete minimum fix:** Already supplied. Preserve the compact B18 closure and its physical hash bindings. Do not relabel it as evidence about B20 or a future recovery attempt.
- **Claim affected:** Clean separation of the failed F10 attempt, nonexistence of scientific output, exact-pod termination, and eligibility to use a wholly fresh namespace.
- **Disposition:** Fixed based on the supplied compact receipt. It records:
  - failed pod `9n5f5a82p1gw1e`;
  - failed attempt `calv2-r3-audit-recovery-2479ed0-20260715T155035Z`;
  - no authorization, attempt marker, failure receipt, audit, summary, or publication marker;
  - zero files in the designated output tree; and
  - exact-pod deletion with unchanged empty account inventory.

## B19 — Execution was not bound to the reviewed controller bytes

- **Severity:** Historical execution-provenance blocker; fixed on the current supplied source.
- **Plan section or short excerpt:** `final_recovery_hash_exec_gate.py` requires controller SHA-256 `a0617d371df00f6b75f2c8cb7b75a619e6ce5adb20895cc6553fac9a044d3cb2` and binds the controller argv, environment, pod, ownership receipt, commits, attempt, and namespace.
- **Why it matters:** Reviewing a controller does not establish that the same bytes were executed. An old or unreviewed controller could otherwise recreate a known deterministic failure or change launch semantics outside the scientific authorization.
- **Concrete minimum fix:** Already implemented. Preserve:
  - canonical non-symlink, single-link controller validation;
  - full stat and SHA-256 checks before and after writing the launch receipt;
  - the exact expected controller hash;
  - explicit rejection of superseded controller hashes, pod IDs, attempt IDs, and B20 authorization hashes;
  - binding of C11, E11, F11, fresh ownership, argv, environment, and namespace; and
  - immediate pathname `execve` after the second check, with the disclosed trusted-root race boundary.
- **Claim affected:** Deterministic execution of the reviewed controller, launch lineage, and interpretation of any subsequent success or failure.
- **Disposition:** Fixed. The current gate and independent launch-receipt validator agree on the controller hash and launch semantics.

## B20 — Final validation invoked Git inside repository-free ACTIVE

- **Severity:** Historical pre-attempt execution blocker; fixed structurally on the current supplied source.
- **Plan section or short excerpt:** “All live Git ancestry and diff checks run during issue from SOURCE… final-confined validation repeats the complete byte/semantic review validation without invoking Git.”
- **Why it matters:** The observed `/dev/null` denial was not the root cause. Even with `/dev/null` writable, `ACTIVE` intentionally has no `.git`, so a Git-dependent final validator could never succeed. Adding a device exception would weaken confinement without repairing execution.
- **Concrete minimum fix:** Implemented:
  1. `SOURCE` checks `C11 <= E11 <= F11`;
  2. `SOURCE` checks no source/test drift from C11 to F11;
  3. `SOURCE` checks that E11-to-F11 changes are exactly the seven v8 outputs;
  4. issue-time review validation runs with live Git;
  5. the exact F11 HEAD is sealed into the authorization;
  6. `execute_recovery` calls `validate_recovery_authorization(..., validate_git=False)`;
  7. final validation rehashes current closure bytes and semantic receipts without Git; and
  8. the independent verifier cross-checks the sealed final HEAD without requiring a repository.
- **Claim affected:** Feasibility of final confined execution, strict Landlock policy, C11/E11/F11 lineage, and interpretation of the B20 failure.
- **Disposition:** Fixed on the supplied source. No `/dev/null` write allowance or broader device rule should be added.

## B21 — Two bound current source paths are omitted from the v8 provider-review packet

- **Severity:** Blocking exact-byte review-closure defect.
- **Plan section or short excerpt:** In `audit_recovery.py`:
  - `FINAL_RECOVERY_WRAPPER_PATHS` contains six paths;
  - `_PRO_REVIEW_V8_PATHS` includes `*FINAL_RECOVERY_WRAPPER_PATHS[:4]`.
- **Why it matters:** The omitted paths are:
  1. `experiments/consciousness_sae_target_blind_calibration/FINAL_RECOVERY_INVOCATION_CONTRACT.md`;
  2. `experiments/consciousness_sae_target_blind_calibration/final_recovery_wrapper_self_test.py`.

  This is a definite defect, not merely missing external evidence:
  - both paths are in `AUDIT_EXECUTABLE_PATHS`;
  - therefore both enter `SOURCE_TEST_BOUND_PATHS` and `RECOVERY_BOUND_PATHS`;
  - both appear in the C11 source/test receipts;
  - both are staged into the exact repository-free `ACTIVE` closure;
  - `final_recovery_wrapper_self_test.py` is executed by `test_qualification_controller_and_pipe_logger_are_review_bound`; but
  - neither file’s content is included as an artifact in the v8 provider packet.

  The provider therefore cannot review all exact source/test bytes for which the authorization later sets `source_and_tests_reviewed_by_provider=True` and `final_source_reviewed_by_provider=True`. A hash listed in a test receipt is not a substitute for supplying the file content to the reviewer.
- **Concrete minimum fix:** Add the two existing exact files to `PRO_REVIEW_V8_PACKET` rather than redesigning them. Update the packet-inclusion regression to require all six `FINAL_RECOVERY_WRAPPER_PATHS`, regenerate the packet, and obtain a successor exact-byte review. Because this changes `audit_recovery.py` and its tests, create a new code freeze and fresh local/B200 qualification receipts; do not put the fix into F11.
- **Claim affected:** Exact provider review of the final source/test closure, validity of `source_and_tests_reviewed_by_provider`, B19/I10 closure, C11/E11/F11 packet integrity, and authorization of the staged `ACTIVE` bytes.
- **Disposition:** Open. This new blocker stops launch.

# Important non-blocking findings

## I10 — Exact-controller regression artifact

- **Severity:** Historical important finding; implementation appears present, but its review closure is incomplete and is subsumed by B21.
- **Plan section or short excerpt:** The C11 source/test inventories name `final_recovery_wrapper_self_test.py`, and `test_qualification_controller_and_pipe_logger_are_review_bound` executes it.
- **Why it matters:** A production-faithful regression is the durable evidence that B17’s physical SOURCE/ACTIVE bootstrap distinction will not regress. The receipts report that the containing suite passed, but the exact self-test source is omitted from the v8 provider packet, so I cannot inspect its logic from the supplied artifacts.
- **Concrete minimum fix:** Include the existing `final_recovery_wrapper_self_test.py` content in the successor packet. No broader test suite is needed if that exact test already covers the physical split-root bridge and old-path failure.
- **Claim affected:** Reproducibility of the B17 repair and prevention of another deterministic preauthorization failure.
- **Disposition:** Accepted and apparently implemented, but not review-closed until B21 is repaired.

## I11 — Unconfined administrative bridge versus confined startup

- **Severity:** Historical important wording boundary; resolved.
- **Plan section or short excerpt:** The issue bridge runs from `SOURCE`; the final launcher/bootstrap runs directly with `-B -E -s -S` under Landlock.
- **Why it matters:** The issue bridge is an unconfined preauthorization administrative operation. Describing it as part of the final confined startup guarantee would overstate the evidence and blur the temporal point at which filesystem and zero-forward guards become active.
- **Concrete minimum fix:** Preserve the current distinction:
  - issue bridge: unconfined, preauthorization, no scientific audit;
  - final launcher/bootstrap: direct, no-site, manifest-bound, guarded, same-PID, and Landlock-confined.
- **Claim affected:** Startup isolation, temporal causal identification, and scope of the zero-forward/confinement evidence.
- **Disposition:** Resolved. The current plan and incident record make the distinction adequately.

## I12 — Fresh-attempt separation as an explicit gate

- **Severity:** Historical important operational finding; resolved.
- **Plan section or short excerpt:** The hash-exec gate rejects historical pod and attempt IDs, verifies namespace absence, and binds the new attempt ID to the final commit prefix.
- **Why it matters:** Timestamp-shaped naming alone would not prove that a namespace or authority is fresh. Explicit rejection is needed to prevent accidental reuse after B18 or B20.
- **Concrete minimum fix:** Already implemented. Preserve explicit rejection of:
  - pods `9n5f5a82p1gw1e` and `eeo1skjkwjqot5`;
  - attempts `calv2-r3-audit-recovery-2479ed0-20260715T155035Z` and `calv2-r3-audit-recovery-2479ed0-20260715T165648Z`;
  - prior ownership and authorization hashes; and
  - all pre-existing base, attempt, authorization, output, marker, failure, and compact paths.
- **Claim affected:** Temporal separation, one-shot authority, and unambiguous failure handling.
- **Disposition:** Resolved.

## I13 — Opening status text still names v7/C10 as the pending final review

- **Severity:** Important non-blocking contradiction.
- **Plan section or short excerpt:** The opening status says: “This plan is not executable until the final v7 cumulative review evaluates the exact C10/E10 successor bytes…” Later, “V8 final-controller recovery after B17--B20” requires C11/E11/F11 and a final v8 review.
- **Why it matters:** The later v8 section and executable gates clearly supersede the stale opening text, so the mechanics are not ambiguous to the code. A human operator or downstream summary could nevertheless cite the opening status to claim that the already-completed v7 review is the final readiness condition for current bytes.
- **Concrete minimum fix:** Replace only the stale status sentence with current v8/successor wording: current bytes require fresh qualification, the exact successor review, and the current C/E/F lineage. Keep the historical v7 narrative in its explicitly historical section.
- **Claim affected:** Launch readiness, review lineage, and prevention of post hoc reinterpretation.
- **Disposition:** Open but non-blocking by itself. Correct it in the same successor packet required by B21.

# What should remain unchanged

1. **Scientific claim and comparability**
   - Keep this framed as a disclosed post-run technical recovery of the exact r3 raw transaction.
   - Do not call it the original same-pod audit, a new model experiment, a replication, or a fresh scientific observation.
   - Permit no scientific release until compact publication and offline bundle verification succeed.
   - Keep the scientific-equivalence appendix’s explicit limitation that it establishes implementation identity, not substantive revalidation of the inherited design.

2. **Narrow J-checkpoint correction**
   - Retain checkpoint SHA-256 `335056c17f0c24053c8c8c1eff168ef49e5a62ca590ffc29c84cf352ecd3ab03`.
   - Require `n_prompts=125`, `d_model=8192`, and every required layer 45–78.
   - Reject boolean, noncanonical, or duplicate-normalized layer identifiers.
   - Pass exactly the 34 required maps downstream.
   - Keep `artifact_recomputation.j_lens` at the frozen `sha256`, `map_count=34`, and `revision` shape.
   - Record available and unused extra maps only in recovery provenance.
   - Do not replace subset semantics with an exact `0..78` whitelist.

3. **Hook, SAE, position, and token semantics**
   - Keep the edit at zero-based `model.model.layers[50]` output, post-block 50/pre-block 51.
   - Keep capture-before-edit registration order and exactly one hook firing per edited continuation.
   - Keep the edited slice `hidden_state[0,0,:]` with shape `[1,1,8192]`.
   - Keep the edited token as the final rendered generation-prompt token.
   - Keep exact model/tokenizer revision, chat template, and prompt/token receipt validation.
   - Keep `token_ids[0:-1]` as prefix and `token_ids[-1]` as the one-token continuation.

4. **Temporal and cache isolation**
   - Keep equal prefix values for clean and signed continuations.
   - Keep independent cache clones for clean, plus, and minus branches.
   - Keep branch order outside the estimand.
   - Reuse no generated continuation text.
   - Keep pre-edit equality and byte equality of upstream layers 45–49.
   - Keep original execution, failed audit, historical recovery attempts, qualification pod, and final recovery pod as distinct temporal units.

5. **J and readout semantics**
   - Keep the explicit post-edit block-50 output as the primary source coordinate.
   - Keep post-block outputs 51–78 as later source coordinates.
   - Keep block-79 output/final RMSNorm input as the J target.
   - Keep row-vector application `residual_delta @ J_l.T`.
   - Keep final RMSNorm and selected LM-head readout.
   - Keep predicted logit contrast centered at the signed final midpoint.

6. **Signs and controls**
   - Keep central effect `(plus-minus)/2`.
   - Keep common mode `(plus+minus)/2-clean`.
   - Keep native BF16 post-edit byte equality.
   - Keep signed requested-to-realized plus, minus, and central checks.
   - Keep wrong-orientation, identity, five fixed random-J, and BF16-versus-FP32 shadow controls.
   - Keep exact failure on missing, duplicate, extra, unmanifested, nonfinite, or partial data.

7. **Independent units and estimands**
   - Keep eight fixed `prompt_id` units.
   - Keep three directions averaged within prompt rather than counted as independent units.
   - Keep prompt-level resampling with 20,000 deterministic replicates.
   - Keep the interval labeled a fixed-panel prompt-resampling stability interval.
   - Keep layer 50 and dose 0.03 as the sole primary J estimand.
   - Keep layers 51–78 descriptive only.
   - Do not claim prompt-population generalization, increased power, or multiplicity correction.

8. **SOURCE/ACTIVE separation**
   - Keep all live Git checks in `SOURCE`.
   - Keep the canonical plan, review validation, historical provenance derivation, and remote freeze rooted in `SOURCE`.
   - Keep `ACTIVE` repository-free and limited to the exact authorized closure.
   - Keep the physical active bootstrap bound by the root manifest.
   - Do not add Git, `.git`, or `/dev/null` write access to `ACTIVE`.

9. **C/E/F lineage**
   - Require code freeze to be an ancestor of the reviewed-packet commit and that commit to be an ancestor of final freeze.
   - Require no source/test drift from code freeze through final freeze.
   - Require only the seven provider-review/adjudication outputs between reviewed-packet and final freeze.
   - Seal exact final HEAD into the authorization.
   - Prevent any source repair from being hidden in the final output-only commit.

10. **Controller and launch gate**
    - Keep the controller generic, with C/E/F supplied as validated runtime arguments.
    - Keep exact controller SHA-256 binding in the hash-exec gate.
    - Keep the second full-stat and SHA-256 check immediately before `execve`.
    - Keep the independent launch-receipt validator.
    - Keep the explicit trusted-root TOCTOU limitation rather than claiming immunity to a hostile concurrent root.

11. **Landlock and startup**
    - Keep direct absolute launcher and bootstrap invocation with `-B -E -s -S`.
    - Keep launcher single-threaded before project or ML imports.
    - Keep exact import-root inventories and ordered `sys.path`.
    - Keep handled mask `0x7ff2`.
    - Keep two output-directory rules at `0x1b2`.
    - Keep `/proc/self/task` at `0x4002`.
    - Keep exact identity-bound NVIDIA device rules at `0x2`.
    - Add no wildcard, `/dev` directory rule, broader `/proc` rule, mount claim, or unconfined fallback.

12. **Descriptor, mapping, and canary gates**
    - Reject inherited writable regular files or directories, including those already under the durable output root.
    - Reject raw, provenance, canary, NVIDIA, unenumerated NVIDIA, unsafe writable-device, and `io_uring` descriptors.
    - Reject every shared file-backed mapping.
    - Keep pipe-backed standard streams.
    - Keep the preconfinement protected-tree writability baseline.
    - Keep complete protected and output allow/deny matrices with exact `EACCES`/`EXDEV` expectations.
    - Keep the canary output empty after testing.

13. **One-shot authority**
    - Keep exclusive authorization publication.
    - Keep Landlock-receipt creation as authority consumption before `execve`.
    - Keep the exclusive attempt marker.
    - Permit no retry or alternate output namespace under the same authorization.
    - Keep success incompatible with `FAILURE.json`.
    - Keep failure retrieval and exact-pod termination mandatory.

14. **Timing and feasibility**
    - Keep the provider-creation-bound 60-minute, `$6.00` recovery envelope.
    - Keep the requirement for at least 1,800 seconds remaining before authorization.
    - Do not reset, extend, or reinterpret the recovery clock.
    - Keep the fresh final host’s full 45-file public-artifact rehash and final-scope CUDA/Landlock preflight.

15. **Reproduction boundary**
    - Keep the offline verifier standard-library-only, network-free, and read-only with respect to the bundle.
    - Write its verification receipt outside the bundle.
    - Describe the result as receipt-verifiable or offline-verifiable, not publicly end-to-end reproducible without the retained raw and public-cache artifacts.

# Minimal revised design

1. **Make only the exact packet-closure repair**
   - Change `_PRO_REVIEW_V8_PATHS` so it includes all six `FINAL_RECOVERY_WRAPPER_PATHS`, not only the first four.
   - Specifically add:
     - `FINAL_RECOVERY_INVOCATION_CONTRACT.md`;
     - `final_recovery_wrapper_self_test.py`.
   - Add a focused assertion that `set(FINAL_RECOVERY_WRAPPER_PATHS) <= set(PRO_REVIEW_V8_PACKET paths)`.

2. **Correct the stale status sentence**
   - Update the opening plan status to identify the current successor review and lineage.
   - Leave historical v7/C10 material unchanged in the historical lineage sections.

3. **Do not modify the scientific or confinement implementation**
   - No new model transaction.
   - No new model forward.
   - No prompt, direction, dose, hook, layer, threshold, bootstrap, readout, control, or claim-gate change.
   - No `/dev/null` permission and no broader Landlock rule.

4. **Create a successor code freeze**
   - Because `audit_recovery.py`, its packet test, and the plan text change, C11 evidence no longer qualifies the repaired packet.
   - Use a new code-freeze commit, rather than changing source in F11.

5. **Regenerate only the required evidence**
   - Run fresh local qualification.
   - Run fresh disposable-B200 qualification against the new code freeze.
   - Require identical source/test inventories and all target tests passing, including the live Landlock same-PID test.
   - Preserve the current C11 receipts as historical positive evidence only.

6. **Build a new reviewed-packet commit**
   - Add the fresh receipt snapshots and the repaired v8 packet.
   - Ensure the packet now supplies the exact contents of every bound current source/test wrapper path.

7. **Obtain one successor exact-byte review**
   - Include immutable v7 evidence, complete B17 review, B18 and B20 closures, the current controller/gates/supervisor, all six wrapper paths, and fresh qualification evidence.
   - Require explicit disposition of B17–B21 and I10–I13.
   - Any new blocker stops launch.

8. **Use an output-only final commit**
   - Add only the successor provider response, request, review, manifest, and structured adjudication outputs.
   - Prove the successor C/E/F ancestry, no source/test drift, and no reviewed-packet drift.
   - Do not hide the B21 repair in an F11-style output-only commit.

9. **Then execute the already-designed recovery**
   - Run all live Git checks from `SOURCE`.
   - Stage exact repository-free `ACTIVE`.
   - Repeat full cache and final-scope preflight.
   - Issue one self-hashed authorization sealing final HEAD.
   - Validate without Git under Landlock.
   - Run the frozen audit exactly once.
   - Retrieve, terminate, and verify offline before any scientific release.

# Freeze checklist

- [ ] B17 remains fixed by the physical split-root SOURCE/ACTIVE bridge.
- [ ] B18 compact closure remains immutable and identifies the failed F10 pod and attempt.
- [ ] B19 remains fixed by the exact controller hash-and-exec gate.
- [ ] B20 remains fixed structurally; no `/dev/null` write exception is added.
- [ ] B21 is closed by including all six `FINAL_RECOVERY_WRAPPER_PATHS` in the provider packet.
- [ ] `FINAL_RECOVERY_INVOCATION_CONTRACT.md` content is supplied to the successor reviewer.
- [ ] `final_recovery_wrapper_self_test.py` content is supplied to the successor reviewer.
- [ ] The packet test rejects omission of either path.
- [ ] I10 is closed with the exact regression source inspectable in the packet.
- [ ] I11’s unconfined-issue versus confined-final distinction remains explicit.
- [ ] I12’s explicit historical pod/attempt/authorization rejection remains enforced.
- [ ] I13’s stale v7/C10 opening status is corrected to current successor wording.
- [ ] No source change is hidden in F11 or any output-only final commit.
- [ ] A new code freeze is created for the packet repair.
- [ ] Fresh local and disposable-B200 qualification receipts bind that new freeze.
- [ ] Local and target receipts name the same source/test inventory.
- [ ] The target receipt reports the designated live Landlock test passed, never skipped.
- [ ] The qualification pod is distinct from every recovery pod.
- [ ] The successor review packet contains no prospective scientific result.
- [ ] The successor review explicitly dispositions B17–B21 and I10–I13.
- [ ] The final review verdict is exact and terminal.
- [ ] Structured adjudication is generated only from actual finding headings.
- [ ] No new blocker is accepted or silently marked fixed without another reviewed source change.
- [ ] C/E/F ancestry is proven with full Git history.
- [ ] No source/test path changes from code freeze through final freeze.
- [ ] Only the enumerated provider-review/adjudication outputs change after the reviewed-packet commit.
- [ ] Exact final HEAD equals the live remote and is sealed into the authorization.
- [ ] The independent verifier cross-checks that sealed final HEAD.
- [ ] Final `ACTIVE` contains no `.git` and invokes no Git command.
- [ ] Final `ACTIVE` contains exactly the authorization-bound closure.
- [ ] Historical provenance remains separate and non-importable.
- [ ] Original auditor SHA-256 remains `271f4f17a5ed66eaff43dc63f5a02d7ce45cdfd4a3c6a5b5c03bac33cf96a465`.
- [ ] J-checkpoint SHA-256 remains `335056c17f0c24053c8c8c1eff168ef49e5a62ca590ffc29c84cf352ecd3ab03`.
- [ ] J metadata remain `n_prompts=125` and `d_model=8192`.
- [ ] Every required J map 45–78 is present.
- [ ] Only required maps 45–78 are passed downstream.
- [ ] Frozen J metadata retain `map_count=34`.
- [ ] Extra maps are recorded only in recovery provenance.
- [ ] Hook boundary remains block-50 output, post-block/pre-block 51.
- [ ] Token position remains the final rendered generation-prompt token.
- [ ] Continuation length remains one token.
- [ ] Prefix cache values are shared only through independent branch clones.
- [ ] No generated continuation text is reused.
- [ ] Central effect, common mode, sign conventions, J orientation, final RMSNorm, and LM-head semantics remain unchanged.
- [ ] Independent units remain exactly eight fixed prompts.
- [ ] Directions remain averaged within prompt.
- [ ] Prompt-level deterministic bootstrap remains at 20,000 replicates.
- [ ] Layer 50 and dose 0.03 remain the sole primary J estimand.
- [ ] Layers 51–78 remain descriptive only.
- [ ] No population-generalization, increased-power, or across-layer-selection claim is made.
- [ ] Fresh recovery pod is receipt-owned, one B200, `US-CA-2`, volume `bv9gb9j32y`.
- [ ] Fresh recovery pod differs from qualification and historical pods.
- [ ] Fresh attempt and namespace differ from B18 and B20 attempts.
- [ ] All base, attempt, authorization, marker, failure, and compact paths are absent before launch.
- [ ] Attempt parent remains `/workspace/csae`.
- [ ] Socket leaf remains `.s`.
- [ ] Socket maximum, margin, and operational budget remain 107, 16, and 91 bytes.
- [ ] Final host repeats the complete 45-file public-artifact rehash.
- [ ] Final host repeats `final_recovery` Landlock/CUDA preflight.
- [ ] At least 1,800 seconds remain before authorization.
- [ ] Landlock masks remain `0x7ff2`, `0x1b2`, `0x4002`, and `0x2`.
- [ ] No wildcard, `/dev` directory rule, broader `/proc` rule, mount claim, or fallback is introduced.
- [ ] Launcher and bootstrap remain direct `-B -E -s -S`.
- [ ] Descriptor, mapping, and both canary gates pass exactly.
- [ ] The exclusive Landlock receipt consumes authority before same-PID `execve`.
- [ ] Final authorization validation runs with `validate_git=False`.
- [ ] The exclusive attempt marker is created only after final validation.
- [ ] Raw and provenance file and directory inventories match at both endpoints.
- [ ] Endpoint equality is not described as continuous external immutability.
- [ ] No fresh model forward, target render, target feature extraction, or external/prior outcome input occurs.
- [ ] No compact success coexists with `FAILURE.json`.
- [ ] Publication occurs before the recovery deadline.
- [ ] The exact recovery pod is terminated after retrieval or failure.
- [ ] The retrieved success bundle passes the network-free offline verifier before scientific release.
