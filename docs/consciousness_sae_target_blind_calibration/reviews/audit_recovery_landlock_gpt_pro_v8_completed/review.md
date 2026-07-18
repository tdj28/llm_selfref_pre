# Verdict

The current packet supports freezing the successor **audit-only recovery**, not yet executing or interpreting a recovered scientific result. I found no new B22-or-later blocker.

The exact admissible claim remains narrow:

- The original r3 model transaction is already complete and immutable.
- The proposed operation adds no model forward and generates no new scientific observation.
- The only scientific compatibility change is from exact equality of J-map inventories to `required layers 45–78 ⊆ available layers`, while passing exactly those 34 required maps to the frozen auditor.
- Any successful output is a disclosed post-run technical recovery, not the original same-pod audit, a new model experiment, a replication, a population estimate, or evidence of increased power.
- The primary scientific estimand remains descriptive performance on the exact eight-prompt fixed panel, with directions averaged within prompt, prompt-level resampling, primary layer 50, and primary dose 0.03. The repeated branches, doses, layers, transports, orientation fixtures, and the J artifact’s 125 fitting prompts are not independent units.

The current artifacts close the exact-packet defect identified as B21. In particular:

- `FINAL_RECOVERY_WRAPPER_PATHS` contains six paths.
- All six contents are supplied in this packet, including `FINAL_RECOVERY_INVOCATION_CONTRACT.md` and `final_recovery_wrapper_self_test.py`.
- The packet construction now expands all of `FINAL_RECOVERY_WRAPPER_PATHS`, rather than a four-path slice.
- The supplied regression requires all six paths to be in the v8 packet.
- The opening plan status now refers to the successor review and current code-freeze/reviewed-packet/final-freeze lineage rather than treating the completed v7/C10 review as current authority.

The B20 repair is also the correct minimum structural repair. Live Git ancestry, live-remote equality, and source/review diff checks remain in repository-backed `SOURCE`; the exact final HEAD is sealed in the self-hashed authorization; repository-free `ACTIVE` repeats byte and semantic validation with `validate_git=False`. No `/dev/null` write permission or broader device rule is added. The B20 compact evidence identifies a failure before `ATTEMPT_STARTED`, with only the Landlock receipt in designated output and no scientific result.

The supplied successor qualification receipts are positive quoted evidence, not tests I independently ran. They agree on:

- code-freeze commit `f8a05e00ee0f8d2c0f33de6bd32c24c2022e36cd`;
- source/test inventory SHA-256 `b1c391af079e6e18e357573258e57fd0b371bdcb43b629fe18485a7a4d498d4e`;
- 36 source/test paths, including all six wrapper paths;
- 229 collected target-host tests, all passed, with no failures, skips, or not-run tests;
- an actual Linux/B200 Landlock qualification whose designated same-PID test passed;
- Landlock ABI 4, the frozen masks, pipe-backed descriptors, guarded bootstrap, raw BF16 CUDA arithmetic and synchronization, and zero model-forward/module-call counters.

The local receipt transparently records 216 passes and 13 environment-dependent skips; it is not being substituted for the target-host receipt.

This verdict is limited to the exact supplied bytes and hashes, including plan SHA-256 `bb21af947274cfe04e7e156d53f47e2d54bfb7e410952ebae7b5c67b43b3d061`, current source/test bytes, the six wrapper artifacts, the fresh successor receipts, the immutable historical v7, B17, and first-v8 reviews, and the B18/B20 compact evidence. I have not inspected the retained raw tensors, the private B20 archive, a future final-freeze commit, a future recovery authorization, or any recovered compact audit or summary.

One new non-blocking maintenance finding, I14, concerns the scope of the wrapper self-test; it does not defeat this exact launch because the immutable controller hash, launch gate, live issue checks, and fail-closed authorization path provide the decisive controls.

READY TO FREEZE

# Blocking findings

## B17 — SOURCE/ACTIVE bootstrap binding mismatch

- **Severity:** Historical blocker; fixed on the current exact source.
- **Plan section or short excerpt:** “V8 keeps every live-repository check at issue time in SOURCE,” while the issue bridge physically loads `ACTIVE/.../confined_bootstrap.py` under its canonical module name.
- **Why it matters:** The import-root manifest requires the running bootstrap’s physical `__file__` to be under `ACTIVE`, while canonical plan, Git, review, and provenance validation must remain rooted in repository-backed `SOURCE`. The earlier invocation could not satisfy both requirements.
- **Concrete minimum fix:** Already implemented. Preserve the split-root issue bridge exactly:
  1. cwd, issuer, and relevant `REPO_ROOT` values remain at `SOURCE`;
  2. source and active bootstrap hashes are checked;
  3. the physical active bootstrap is loaded under the canonical package module name before importing `audit_recovery`;
  4. `audit_recovery.confined_bootstrap is active_bootstrap` is required;
  5. only parsed command `issue` is dispatched; and
  6. the final confined child continues to execute the active bootstrap directly with `-B -E -s -S`.
- **Claim affected:** Feasibility and identity of issue-time authorization, validity of the active-root manifest, and separation of repository checks from confined execution.
- **Disposition:** Fixed. Do not replace this with `cd ACTIVE`, a `__file__` monkeypatch, copied Git metadata, or `GIT_WORK_TREE=ACTIVE`.

## B18 — Failed-attempt cleanup and zero-artifact evidence

- **Severity:** Historical missing-evidence blocker; mechanically closed by supplied compact evidence.
- **Plan section or short excerpt:** `B18_CLOSURE_RECEIPT.json` records recursive absence of the six success/failure artifact basenames, a zero-file designated output tree, and exact-pod termination.
- **Why it matters:** Without inspectable cleanup evidence, a future attempt could ambiguously overlap a prior namespace, authorization, scientific output, or still-running provider resource.
- **Concrete minimum fix:** Already implemented. Preserve the B18 closure receipt and its attachment hashes. It records:
  - pod `9n5f5a82p1gw1e`;
  - attempt `calv2-r3-audit-recovery-2479ed0-20260715T155035Z`;
  - no recovery authorization, attempt marker, failure receipt, audit, summary, or publication marker;
  - zero files in designated output; and
  - exact-pod deletion with unchanged account inventory.
- **Claim affected:** Clean separation of the failed F10 attempt, absence of scientific output, one-shot authority provenance, and eligibility to create a new namespace.
- **Disposition:** Fixed for B18 only. The B18 evidence must not be relabeled as evidence about B20 or a future attempt.

## B19 — Execution was not bound to the reviewed controller bytes

- **Severity:** Historical execution-provenance blocker; fixed on the current exact source.
- **Plan section or short excerpt:** `final_recovery_hash_exec_gate.py` requires controller SHA-256 `a0617d371df00f6b75f2c8cb7b75a619e6ce5adb20895cc6553fac9a044d3cb2`.
- **Why it matters:** Reviewing a controller does not prove those bytes were executed. An old or substituted controller could recreate a deterministic failure or alter launch behavior outside the scientific authorization.
- **Concrete minimum fix:** Already implemented. Preserve:
  - canonical, non-symlink, single-link controller validation;
  - owner and mode checks;
  - full stat and SHA-256 validation before and after durable launch-receipt publication;
  - exact controller hash enforcement;
  - explicit rejection of historical controller, pod, attempt, ownership, and B20 authorization identities;
  - binding of the three lineage commits, fresh ownership, argv, environment, and namespace; and
  - immediate `execve` after the second check, with the trusted-root TOCTOU limitation disclosed.
- **Claim affected:** Deterministic execution of the reviewed controller, branch lineage, and interpretation of subsequent success or failure.
- **Disposition:** Fixed. The launch gate, local supervisor, independent receipt validator, and wrapper self-test agree on the controller hash.

## B20 — Final validation invoked Git inside repository-free ACTIVE

- **Severity:** Historical pre-attempt execution blocker; fixed structurally on the current exact source.
- **Plan section or short excerpt:** “All live Git ancestry and diff checks run during issue from SOURCE… final-confined validation repeats the complete byte/semantic review validation without invoking Git.”
- **Why it matters:** The observed `/dev/null` denial was only the first symptom. `ACTIVE` intentionally contains no `.git`, so allowing `/dev/null` would not make a Git-dependent final validator valid. It would weaken the device boundary and then fail as “not a git repository.”
- **Concrete minimum fix:** Implemented:
  1. the generic controller validates the runtime code-freeze, reviewed-packet, and final-freeze commits in `SOURCE`;
  2. it proves code-freeze ancestry through final freeze;
  3. it proves no `experiments/` or `tests/` drift from code freeze to final freeze;
  4. it requires the reviewed-packet-to-final-freeze delta to be exactly the seven provider review/adjudication outputs;
  5. issue-time validation uses live Git and live remote state;
  6. the exact final HEAD is sealed into the self-hashed authorization;
  7. `execute_recovery` uses `validate_git=False` inside repository-free `ACTIVE`; and
  8. the independent verifier cross-checks the sealed final commit and exact closure without invoking Git.
- **Claim affected:** Feasibility of final confined execution, strict Landlock policy, branch lineage, and interpretation of the B20 failure.
- **Disposition:** Fixed. Do not add `/dev/null`, `.git`, Git binaries for final validation, or a broader device-directory allowance.

## B21 — Two bound wrapper paths were omitted from the first v8 review packet

- **Severity:** Historical exact-byte packet blocker; fixed on the current packet.
- **Plan section or short excerpt:** “The successor packet includes all six wrapper paths and a regression requiring that complete inclusion.”
- **Why it matters:** The first v8 packet omitted:
  - `FINAL_RECOVERY_INVOCATION_CONTRACT.md`; and
  - `final_recovery_wrapper_self_test.py`.

  Both paths were in the source/test and executable closures, and the self-test was executed by qualification, but their contents were unavailable to that reviewer. The resulting assertion that all final source/test bytes were provider-reviewed would have been false.
- **Concrete minimum fix:** Implemented. The current `_PRO_REVIEW_V8_PATHS` expands all six `FINAL_RECOVERY_WRAPPER_PATHS`; both formerly omitted files are supplied as artifacts; the source/test receipts include them; and the packet regression requires the complete six-path set.
- **Claim affected:** Exact-byte review of the staged `ACTIVE` closure, validity of `source_and_tests_reviewed_by_provider`, B19/I10 closure, and reviewed-packet lineage.
- **Disposition:** Fixed on the supplied bytes. The current repair is the smallest sound repair and introduces no scientific-design change.

No new B22-or-later blocker is identified.

# Important non-blocking findings

## I10 — Exact-controller regression artifact

- **Severity:** Historical important finding; partially satisfied, with the remaining scope clarified under I14.
- **Plan section or short excerpt:** `final_recovery_wrapper_self_test.py` is now supplied, source/test-bound, and executed by `test_qualification_controller_and_pipe_logger_are_review_bound`.
- **Why it matters:** A durable regression helps prevent recurrence of the physical SOURCE/ACTIVE bootstrap mismatch.
- **Concrete minimum fix:** For this exact launch, retain the supplied wrapper self-test, its pinned wrapper hashes, syntax checks, lineage-token checks, rejected-identity checks, and target qualification evidence. Do not claim that it dynamically executes the complete production issue bridge; that broader regression remains a future-maintenance recommendation under I14.
- **Claim affected:** Prevention of wrapper and B17 lineage regressions, not the inherited scientific result.
- **Disposition:** Accepted in its actual, narrower structural scope. B21’s inspectability defect is closed because the exact self-test source is now in the packet.

## I11 — Unconfined administrative issue bridge versus confined final startup

- **Severity:** Historical important wording boundary; resolved.
- **Plan section or short excerpt:** The issue bridge runs from repository-backed `SOURCE`; the final launcher and bootstrap run in `ACTIVE` with direct `-B -E -s -S` startup under Landlock.
- **Why it matters:** The issue bridge is an unconfined preauthorization administrative operation. Treating it as part of the final confined startup guarantee would blur the temporal point at which filesystem and process-lifetime protections become active.
- **Concrete minimum fix:** Preserve the distinction:
  - issue bridge: unconfined, preauthorization, repository-backed, and no scientific audit;
  - final launcher/bootstrap: direct, no-site, manifest-bound, guarded, same-PID, and Landlock-confined.
- **Claim affected:** Startup isolation, temporal causal identification, and scope of zero-forward and confinement evidence.
- **Disposition:** Resolved. The plan and implementation describe the boundary adequately.

## I12 — Fresh-attempt separation must be explicit

- **Severity:** Historical important operational finding; resolved.
- **Plan section or short excerpt:** The hash-exec gate rejects historical pod, attempt, ownership, controller, and authorization identities and verifies namespace absence.
- **Why it matters:** A timestamp-shaped attempt ID alone does not prove that a namespace or authority is fresh.
- **Concrete minimum fix:** Already implemented. Preserve explicit rejection of:
  - pods `9n5f5a82p1gw1e` and `eeo1skjkwjqot5`;
  - attempts `calv2-r3-audit-recovery-2479ed0-20260715T155035Z` and `calv2-r3-audit-recovery-2479ed0-20260715T165648Z`;
  - the B20 authorization by both self-hash and physical hash;
  - historical ownership receipts; and
  - pre-existing base, attempt, authorization, output, marker, failure, and compact paths.
- **Claim affected:** Temporal separation, one-shot authority, and unambiguous failure handling.
- **Disposition:** Resolved.

## I13 — Stale opening status named v7/C10 as the pending final review

- **Severity:** Historical important contradiction; fixed on the current plan.
- **Plan section or short excerpt:** Current opening status: “This plan is not executable until fresh local and disposable-B200 qualification receipts bind the current successor code freeze, an exact-byte successor review evaluates the complete current packet including B17–B21 and I10–I13, and the current code-freeze/reviewed-packet/final-freeze lineage passes every gate.”
- **Why it matters:** The prior wording could have allowed a human operator to cite the completed v7/C10 review as current authority despite later source changes.
- **Concrete minimum fix:** Implemented by replacing only the stale opening status sentence and retaining v7/C10 history in explicitly historical sections.
- **Claim affected:** Launch readiness, review lineage, and prevention of retrospective reinterpretation.
- **Disposition:** Fixed.

## I14 — Wrapper self-test is structural, not a production-faithful execution of the split-root issue bridge

- **Severity:** Important non-blocking limitation; newly identified.
- **Plan section or short excerpt:** `final_recovery_wrapper_self_test.py` describes itself as “Local structural self-tests” and checks wrapper hashes, syntax, static source tokens, rejected identities, and missing-argument behavior.
- **Why it matters:** The exact source is now inspectable and useful, but it does not dynamically execute the controller’s stdin issue bridge with physically distinct `SOURCE` and `ACTIVE` roots, prove successful `_bootstrap_manifest_binding()`, and then demonstrate failure when the source-root bootstrap is substituted. Therefore it should not be described as the full production-faithful regression originally suggested in I10.
- **Concrete minimum fix:** Do not change the current freeze for this point. Before any future controller or bridge revision is reused, add one focused outcome-free test that:
  1. creates distinct physical source and active bootstrap copies;
  2. runs the exact bridge body or factored exact bridge function;
  3. verifies source issuer and `REPO_ROOT` identities;
  4. verifies active bootstrap `__file__` and canonical module-object identity;
  5. reaches successful root-manifest binding; and
  6. fails with the former source-bootstrap binding.
  
  No broad new test suite is needed.
- **Claim affected:** Long-term regression protection for B17. It does not affect this exact launch’s identity because the controller is hash-bound, issue validation is fail-closed, and the final host must pass the actual authorization path before scientific computation.
- **Disposition:** Accepted as a maintenance limitation. Do not overstate the current structural self-test.

# What should remain unchanged

1. **Scientific claim boundary**
   - Keep the output framed as a disclosed post-run technical recovery of the exact r3 raw transaction.
   - Do not call it the original same-pod audit, a new model transaction, a replication, or new independent evidence.
   - Release no scientific claim until compact publication and independent offline verification both succeed.
   - Preserve the statement that the recovery appendix establishes implementation identity, not substantive revalidation of the inherited study design.

2. **J-checkpoint correction**
   - Keep checkpoint SHA-256 `335056c17f0c24053c8c8c1eff168ef49e5a62ca590ffc29c84cf352ecd3ab03`.
   - Require `n_prompts=125`, `d_model=8192`, and all required layers 45–78.
   - Reject boolean, noncanonical, and duplicate-normalized layer identifiers.
   - Pass exactly the 34 required maps downstream.
   - Keep frozen J metadata at `sha256`, `map_count=34`, and `revision`.
   - Record all available and unused extra maps only in recovery provenance.
   - Do not replace subset semantics with an exact 0–78 release whitelist.

3. **Frozen scientific entry point**
   - Keep auditor SHA-256 `271f4f17a5ed66eaff43dc63f5a02d7ce45cdfd4a3c6a5b5c03bac33cf96a465`.
   - Invoke `audit.audit` exactly once.
   - Limit monkeypatching to the J loader, recovery watchdog, and historical-time receipt validation.
   - Preserve the affirmative scientific-field projection and exact checked-in equivalence appendix.

4. **Hook and state coordinates**
   - Edit `model.model.layers[50]` output at the zero-based post-block-50/pre-block-51 boundary.
   - Keep capture-before-edit registration and one hook firing per edited continuation.
   - Keep the edited slice `hidden_state[0,0,:]` with shape `[1,1,8192]`.
   - Keep the explicit post-edit block-50 output as the primary J source.
   - Keep post-block outputs 51–78 as later J sources.
   - Keep block-79 output/final-RMSNorm input as the target.
   - Keep row-vector application `residual_delta @ J_l.T`.

5. **Tokenization and temporal carryover**
   - Keep the exact model and tokenizer revisions and full tokenizer inventory.
   - Use the exact chat template with generation prompt.
   - Keep `token_ids[0:-1]` as prefix and `token_ids[-1]` as the one-token continuation.
   - Keep equal prefix values with independent branch cache clones.
   - Reuse no generated continuation text.
   - Keep pre-edit equality and upstream layers 45–49 byte equality.

6. **Readout, signs, and controls**
   - Keep central effect `(plus-minus)/2`.
   - Keep common mode `(plus+minus)/2-clean`.
   - Keep final RMSNorm and selected LM-head token readout.
   - Keep signed-final-midpoint centering for predicted logit contrasts.
   - Preserve native BF16 post-edit equality, signed delivery checks, wrong-orientation control, identity transport, five seeded random-J controls, and BF16/FP32 shadow checks.
   - Reject missing, duplicate, extra, unmanifested, nonfinite, and partial data.

7. **Statistical boundaries**
   - Keep exactly eight independent fixed prompt units.
   - Average the three directions within prompt.
   - Keep 20,000 deterministic prompt-level bootstrap replicates.
   - Keep the interval labeled as fixed-panel prompt-resampling stability.
   - Keep layer 50 and dose 0.03 as the sole primary J estimand.
   - Keep layers 51–78 descriptive.
   - Make no population-generalization, multiplicity-correction, increased-power, or across-layer-selection claim.

8. **Temporal provenance**
   - Keep the original transaction, failed audit, first blocked recovery host, B18 attempt, B20 attempt, successor qualification host, and future recovery host distinct.
   - Preserve original campaign fields unchanged.
   - Record fresh authority only under `recovery_execution_campaign`.
   - Validate the original authorization at historical completion time rather than treating it as current authority.
   - Keep the B18 and B20 incidents as technical failures with no scientific result.

9. **SOURCE/ACTIVE separation and B20 repair**
   - Run live Git and remote checks only in `SOURCE`.
   - Keep `ACTIVE` repository-free.
   - Seal the exact final HEAD into authorization.
   - Revalidate exact bytes and semantics in `ACTIVE` with `validate_git=False`.
   - Add no `/dev/null` write exception, `.git` tree, or final-confined Git invocation.

10. **Branch lineage**
    - Require code-freeze ≤ reviewed-packet ≤ final-freeze.
    - Require no source/test drift from code freeze through final freeze.
    - Require exactly the seven provider review/adjudication outputs after the reviewed-packet commit.
    - Prevent source or test changes from being hidden in the output-only final freeze.
    - Require the final HEAD to equal the live remote before authorization.

11. **Controller and wrapper closure**
    - Keep all six `FINAL_RECOVERY_WRAPPER_PATHS` in the review packet, source/test closure, and exact `ACTIVE` closure.
    - Keep the controller generic, with the three commit IDs passed as validated runtime arguments.
    - Preserve the invocation contract as documentation, not executable authority.
    - Preserve exact controller, gate, validator, and supervisor hashes.
    - Keep the trusted-root TOCTOU limitation disclosed.

12. **Direct startup and executable isolation**
    - Keep direct launcher and bootstrap paths, never package-module invocation.
    - Keep `-B -E -s -S`.
    - Keep the launcher single-threaded before project and ML imports.
    - Keep exact active/dependency root inventories and ordered `sys.path`.
    - Keep historical provenance separate and non-importable.
    - Keep the audit-only tensor hash shim instead of the model runtime.

13. **Landlock policy**
    - Keep handled mask `0x7ff2`.
    - Keep two exact output rules at `0x1b2`.
    - Keep `/proc/self/task` at `0x4002`.
    - Keep exact, identity-bound NVIDIA character-device rules at `0x2`.
    - Keep no wildcard, `/dev` directory, broader `/proc`, mount, or fallback rule.
    - Preserve the explicit limitations for metadata operations, pre-opened descriptors, sibling/NFS activity, and device `ioctl`.

14. **Descriptors, mappings, and canaries**
    - Reject inherited writable regular files/directories, including those already under durable output.
    - Reject protected, canary, NVIDIA, unenumerated NVIDIA, unsafe writable-device, and `io_uring` descriptors.
    - Reject all shared file-backed mappings.
    - Keep pipe-backed standard streams.
    - Keep the protected-tree preconfinement writability baseline.
    - Keep the complete protected and output allow/deny matrices with exact `EACCES` and `EXDEV`.
    - Require the output canary to be empty afterward.

15. **One-shot authority and failure handling**
    - Keep exclusive authorization publication.
    - Treat the exclusive Landlock receipt as authority consumption before same-PID `execve`.
    - Keep the attempt marker exclusive and commit-scoped.
    - Permit no retry or alternate output namespace under the same authorization.
    - Keep success incompatible with `FAILURE.json`.
    - Retrieve available evidence and terminate the exact pod after success or failure.

16. **Feasibility and reproduction**
    - Keep the provider-creation-bound 60-minute and `$6.00` recovery envelope.
    - Require at least 1,800 seconds remaining before authorization.
    - Repeat the full 45-file, 156,023,372,845-byte artifact rehash on the actual recovery host.
    - Repeat `final_recovery` Landlock/CUDA preflight on that host.
    - Keep the offline verifier standard-library-only, network-free, and read-only with respect to the retrieved bundle.
    - Describe the result as receipt-verifiable or offline-verifiable, not publicly end-to-end reproducible without the retained raw and cache artifacts.

# Minimal revised design

No pre-execution source, test, controller, plan, scientific, or confinement revision is required for the exact current packet.

The minimum remaining sequence is:

1. **Freeze this review as the successor review**
   - Preserve the exact response text and provider metadata.
   - Parse finding IDs only from actual level-two headings in the two finding sections.
   - Include B17–B21 and I10–I14 in structured adjudication.
   - Record no B22-or-later blocker.

2. **Create the output-only final freeze**
   - Add only the two structured adjudication files and five completed provider-review files.
   - Make no source, test, plan, controller, wrapper, receipt-snapshot, or reviewed-packet change.
   - Prove code-freeze ≤ reviewed-packet ≤ final-freeze with full Git history.
   - Prove no source/test drift from code freeze through final freeze.
   - Prove the reviewed-packet-to-final-freeze delta is exactly the seven permitted output files.

3. **Run the generic launch chain with actual commit arguments**
   - Pass the actual code-freeze, reviewed-packet, and final-freeze commit IDs through the local supervisor, hash-exec gate, controller, and launch-receipt validator.
   - Require the attempt ID’s seven-hex prefix to equal the actual final-freeze prefix.
   - Reject all B18/B20 pod, attempt, ownership, controller, and authorization identities.

4. **Create one fresh recovery pod**
   - One receipt-owned B200 in `US-CA-2` on volume `bv9gb9j32y`.
   - Distinct from qualification pod `fiveqhsb36cq45` and every historical recovery pod.
   - Use a fresh base, attempt namespace, authorization path, output directory, and provider clock.

5. **Stage repository-backed SOURCE and exact repository-free ACTIVE**
   - Run every live Git ancestry, remote, and diff check in `SOURCE`.
   - Copy exactly `RECOVERY_BOUND_PATHS` to `ACTIVE`.
   - Copy exactly the 41 historical provenance files to the non-importable provenance tree.
   - Rehash all staged bytes and directories.
   - Build the external import-root manifest.

6. **Run actual-host preauthorization gates**
   - Complete guest and cache receipts.
   - Rehash all 45 public-artifact files.
   - Enumerate and identity-bind the actual NVIDIA character-device set.
   - Run the complete `final_recovery` Landlock/CUDA preflight and both canary matrices.
   - Require guarded raw BF16 CUDA arithmetic and synchronization with zero forward/module/load counters.
   - Stop before authorization if any check differs or fewer than 1,800 seconds remain.

7. **Issue one authorization**
   - Run issue validation from `SOURCE`.
   - Bind the exact final HEAD, reviewed packet, current receipts, import manifest, external evidence, device identities, command, namespace, deadline, and budget.
   - Write the authorization exclusively.
   - Permit no model forward and no retry.

8. **Run final confined validation and the frozen audit**
   - Enter Landlock from the direct single-threaded launcher.
   - Publish the exclusive Landlock receipt.
   - Same-PID `execve` the active direct bootstrap.
   - Validate authorization with `validate_git=False`.
   - Claim the exclusive attempt marker.
   - Rehash raw and provenance trees.
   - Run the frozen auditor once with only the required-layer subset adapter.
   - Rehash both trees again.
   - Publish the compact pair and marker atomically, or publish no success.

9. **Retrieve, terminate, and verify**
   - Retrieve success or available failure evidence.
   - Terminate the exact recovery pod.
   - Preserve the retained network volume and raw namespace.
   - Run the network-free offline verifier.
   - Release only the disclosed fixed-panel technical-recovery result after verifier success.

I14 requires no change to this freeze. Its focused dynamic bridge regression should be added only before a future controller revision or reuse, where it can be reviewed and qualified as part of that future freeze.

# Freeze checklist

- [ ] Exact plan remains SHA-256 `bb21af947274cfe04e7e156d53f47e2d54bfb7e410952ebae7b5c67b43b3d061`.
- [ ] Successor code freeze remains `f8a05e00ee0f8d2c0f33de6bd32c24c2022e36cd`.
- [ ] Local and target receipts retain source/test inventory `b1c391af079e6e18e357573258e57fd0b371bdcb43b629fe18485a7a4d498d4e`.
- [ ] Local test receipt remains self-hashed with receipt SHA-256 `69421f705f3fd67a3924b10d99c81c9ab991b06cdff28baa46e66e8a292e10a7`.
- [ ] Target test receipt remains self-hashed with receipt SHA-256 `85bdca8b68b5e966497493f86a46404f73391ff2c5955866d5703d11cb0a1ec4`.
- [ ] Target qualification ownership physical SHA-256 remains `e788f9c4b8759ed4ccdce166c5717e7637c48618d153833d165961004399330d`.
- [ ] Target qualification Landlock physical SHA-256 remains `76611f55c794afc58696495c47c9a7488cf79cfac082f0667fa701b1dfe413ee`.
- [ ] Target qualification CUDA physical SHA-256 remains `12eab451b6af777cabde0d2bd585f2fd3698fb70342fbd8666d032430f2d19b8`.
- [ ] Target qualification retains pod ID `fiveqhsb36cq45`.
- [ ] Target receipt retains 229 passed, zero failed, zero skipped, and zero not-run tests.
- [ ] Local receipt retains 216 passes and 13 disclosed skips; those skips are not relabeled as target passes.
- [ ] All six `FINAL_RECOVERY_WRAPPER_PATHS` remain in the packet.
- [ ] `FINAL_RECOVERY_INVOCATION_CONTRACT.md` remains bytes 1,660 and SHA-256 `de62e81b29e36be16556adc75569cd73f454f8dd7b75451a3f4040a7d260ae0d`.
- [ ] `final_recovery_wrapper_self_test.py` remains bytes 4,659 and SHA-256 `9e6a61e6ae4b2a56298379bab20742efbce60446d847399e33344f5cb83d656c`.
- [ ] Packet regression continues to require every `FINAL_RECOVERY_WRAPPER_PATHS` member.
- [ ] B17 remains fixed by the split-root SOURCE/ACTIVE bridge.
- [ ] B18 closure remains immutable and scoped only to the failed F10 attempt.
- [ ] B19 remains fixed by the exact controller hash-and-exec gate.
- [ ] B20 remains fixed structurally; no `/dev/null` write exception is added.
- [ ] B21 remains closed by complete six-wrapper packet inclusion.
- [ ] I10 is described according to the actual structural scope of the wrapper self-test.
- [ ] I11’s unconfined-issue versus confined-final distinction remains explicit.
- [ ] I12’s explicit historical identity rejection remains enforced.
- [ ] I13’s corrected successor opening status remains current.
- [ ] I14 is recorded as future maintenance and does not trigger an unreviewed current source change.
- [ ] No B22-or-later blocker is introduced in adjudication.
- [ ] Current finding IDs are extracted only from actual level-two headings in the two finding sections.
- [ ] No finding is created from verdict prose, explanatory prose, fenced text, comments, or checklists.
- [ ] Structured adjudication dispositions B17–B21 and I10–I14.
- [ ] The final freeze adds only the seven provider review/adjudication outputs.
- [ ] No source, test, plan, controller, wrapper, or receipt-snapshot byte changes after review.
- [ ] Code-freeze ≤ reviewed-packet ≤ final-freeze is proven with full Git history.
- [ ] No source/test diff exists between code freeze and final freeze.
- [ ] No provider-packet diff exists between reviewed packet and final freeze.
- [ ] Exact final HEAD equals the local tracking ref and live remote.
- [ ] Exact final HEAD is sealed into the self-hashed authorization.
- [ ] The independent verifier cross-checks that sealed final HEAD.
- [ ] Final `ACTIVE` is repository-free and contains no `.git`.
- [ ] Final `ACTIVE` invokes no Git command.
- [ ] Original auditor remains SHA-256 `271f4f17a5ed66eaff43dc63f5a02d7ce45cdfd4a3c6a5b5c03bac33cf96a465`.
- [ ] J checkpoint remains SHA-256 `335056c17f0c24053c8c8c1eff168ef49e5a62ca590ffc29c84cf352ecd3ab03`.
- [ ] J metadata remain `n_prompts=125` and `d_model=8192`.
- [ ] Every required J map 45–78 is present.
- [ ] Only required maps 45–78 are passed downstream.
- [ ] Frozen J metadata retain `map_count=34`.
- [ ] Extra maps appear only in recovery provenance.
- [ ] Hook boundary remains zero-based block-50 output, post-block 50/pre-block 51.
- [ ] Capture-before-edit ordering and one hook firing per edited continuation remain fixed.
- [ ] Token position remains the final rendered generation-prompt token.
- [ ] Continuation length remains exactly one token.
- [ ] Prefix values are shared only through independent cache clones.
- [ ] No generated continuation text is reused as later input.
- [ ] Central effect, common mode, signs, J orientation, final RMSNorm, LM-head readout, and midpoint centering remain unchanged.
- [ ] Independent units remain exactly eight fixed prompts.
- [ ] Directions remain averaged within prompt.
- [ ] Prompt-level deterministic bootstrap remains at 20,000 replicates.
- [ ] Layer 50 and dose 0.03 remain the sole primary J estimand.
- [ ] Layers 51–78 remain descriptive only.
- [ ] No population-generalization, multiplicity-correction, increased-power, or across-layer-selection claim is made.
- [ ] Fresh recovery pod is distinct from qualification pod `fiveqhsb36cq45`.
- [ ] Fresh recovery pod differs from every B18 and B20 pod.
- [ ] Fresh attempt and namespace differ from all historical attempts.
- [ ] Base, attempt, authorization, marker, failure, and compact paths are absent before launch.
- [ ] Controller SHA-256 remains `a0617d371df00f6b75f2c8cb7b75a619e6ce5adb20895cc6553fac9a044d3cb2`.
- [ ] Hash-exec gate SHA-256 remains `fc444f69b37c21701aac0f9b28baeedb648fa43097d25ca557a3929b1559222e`.
- [ ] Launch-gate validator SHA-256 remains `e427e44e94e6061af61700ef29c1ebd5b83726f38422636277aed14defe5dd39`.
- [ ] Local supervisor SHA-256 remains `e06e5176d1efaabdd42d0e8bece33139f9a4e8a626cd4fa63cea06229385f80e`.
- [ ] Attempt parent remains `/workspace/csae`.
- [ ] Socket leaf remains `.s`.
- [ ] Socket maximum, margin, and operational limit remain 107, 16, and 91 bytes.
- [ ] Production preflight and execution socket paths remain exactly 91 and 90 bytes.
- [ ] The actual recovery host completes the full 45-file public-artifact rehash.
- [ ] The actual recovery host repeats `final_recovery` Landlock/CUDA preflight.
- [ ] At least 1,800 seconds remain before authorization.
- [ ] Landlock ABI is at least 4.
- [ ] Landlock masks remain `0x7ff2`, `0x1b2`, `0x4002`, and `0x2`.
- [ ] NVIDIA character devices are bound by canonical path, type, `st_dev`, `st_ino`, `st_rdev`, major, and minor.
- [ ] No wildcard, `/dev` directory, broader `/proc`, mount, or fallback rule is added.
- [ ] Launcher and bootstrap remain direct `-B -E -s -S`.
- [ ] Launcher is single-threaded before project or ML imports.
- [ ] Descriptor, mapping, and both canary gates pass exactly.
- [ ] Standard streams remain pipe-backed rather than writable regular files.
- [ ] Protected canary is proven writable before confinement.
- [ ] Output canary is empty afterward.
- [ ] Exclusive Landlock receipt consumes authority before same-PID `execve`.
- [ ] Final authorization validation runs with `validate_git=False`.
- [ ] Attempt marker is created only after final validation.
- [ ] Raw and provenance file and directory inventories match at both endpoints.
- [ ] Endpoint equality is not described as continuous external immutability.
- [ ] No fresh model forward, target render, target feature extraction, generated-text carryover, or external/prior outcome input occurs.
- [ ] No compact success coexists with `FAILURE.json`.
- [ ] Publication completes before the recovery deadline.
- [ ] Exact recovery pod is terminated after retrieval or failure.
- [ ] Retrieved success bundle passes the network-free offline verifier before scientific release.
