# Verdict

This is a focused launcher-successor review, not a reopening of the frozen scientific design. I preserve the substantive v7 conclusions and adjudications for B01–B16 and I01–I09. In particular, the inherited claim remains a disclosed audit-only recovery of eight fixed prompt units, not a new model intervention, replication, population estimate, or source of additional power.

The supplied corrected controller implements the right narrow repair for the B17 defect:

- The issuer remains physically and logically rooted at the clean F10 `SOURCE` checkout.
- The canonical plan, Git index/worktree, live remote freeze, 41 historical provenance paths, v7 review, and adjudication continue to be checked from `SOURCE`.
- The bridge loads the real `ACTIVE/.../confined_bootstrap.py` under its canonical module name before importing `audit_recovery`.
- The bridge checks both source and active bootstrap hashes, the source issuer path, the three relevant source `REPO_ROOT` values, the active bootstrap path, module-object identity, schema/status constants, and the parsed command.
- The manifest validator therefore executes with the genuine active-tree module and can satisfy its deliberate physical `__file__ == active / BOOTSTRAP_RELATIVE_PATH` requirement.
- The final confined child remains a direct `-B -E -s -S` execution of the active bootstrap; the bridge does not weaken the confined execution path.
- The failed-host stdout and stderr are consistent with a stop during preauthorization manifest binding, before `AUTHENTIC_ISSUE_COMPLETE` and before final confined execution. They disclose no scientific outcome.

I find no defect in the bridge logic that requires a scientific redesign. B17 is substantively fixed in the supplied corrected controller.

Two operational provenance requirements remain before another paid pod should be launched. First, the packet does not include the cited failed-attempt termination audit or a retrieved-tree inventory, so the asserted cleanup and absence of authorization/output artifacts cannot be independently checked from the supplied artifacts. Second, the corrected controller does not itself establish that the exact reviewed controller hash was the one executed; that must be supplied by a small external hash-and-exec gate or equivalent ownership-chain receipt. Neither repair changes frozen scientific source, tests, prompts, hooks, estimands, or authority semantics.

Subject to those two narrow fixes, a wholly fresh pod, attempt ID, namespace, ownership chain, and authorization is appropriate. No old authorization may be reused, and the failed attempt ID must remain historical and immutable.

READY AFTER SPECIFIED FIXES

# Blocking findings

## B17 — Source/active bootstrap binding mismatch

- **Severity:** Historical execution blocker; fixed in the supplied corrected controller.
- **Plan section or short excerpt:** “The old `python -m ...audit_recovery issue` call is replaced by a small stdin bridge that loads the real active-tree `confined_bootstrap.py` under its canonical module name before importing the issuer from the clean source checkout.”
- **Why it matters:** The root manifest deliberately binds the running bootstrap’s physical path to the active root. The old module invocation imported the source-tree bootstrap, so authorization could never pass even when the source and active files had identical bytes. Conversely, moving the whole issuer into `ACTIVE` would invalidate the canonical source/Git/provenance checks and executable-isolation inventory.
- **Concrete minimum fix:** Implemented in `final_recovery_controller_f10.sh`. Retain the split-root bridge exactly as supplied:
  1. cwd and issuer remain at `SOURCE`;
  2. both source and active bootstrap files must match frozen SHA-256 `616104d2711fd9ae18f5cf930e2dcf497d6b113a718b78b812f4bd7383ab227a`;
  3. the physical active bootstrap is loaded under `experiments.consciousness_sae_target_blind_calibration.confined_bootstrap`;
  4. `audit_recovery.confined_bootstrap is active_bootstrap`;
  5. source issuer and `REPO_ROOT` identities remain at `SOURCE`; and
  6. only the `issue` command is dispatched.
- **Claim affected:** Validity of the active-root import manifest, source/Git/provenance validation, and feasibility of issuing a fresh recovery authorization.
- **Disposition:** Fixed on the supplied corrected controller bytes. Do not replace this with `cd ACTIVE`, `GIT_WORK_TREE=ACTIVE`, copied provenance-only files, or a `__file__` monkeypatch.

## B18 — Failed-attempt cleanup and zero-artifact boundary are asserted but not independently inspectable

- **Severity:** Blocking missing evidence, not a demonstrated cleanup defect.
- **Plan section or short excerpt:** “The retrieved failure bundle has no `RECOVERY_AUTHORIZATION.json`, `ATTEMPT_STARTED.json`, `FAILURE.json`, `CALIBRATION_AUDIT.json`, or `CALIBRATION_SUMMARY.json`; its designated output tree contains zero files,” and “The termination audit is self-hashed and records `deleted_exact_owned_pod_unrelated_inventory_unchanged`.”
- **Why it matters:** The supplied stdout and stderr strongly support a preauthorization failure, but the cited termination audit, ownership binding, retrieved-tree inventory, and zero-file output inventory are not included in the packet. I therefore cannot verify the quoted receipt SHA-256, exact-pod deletion, unrelated-pod inventory equality, or absence of an authorization file from the retrieved filesystem. Those facts determine whether a fresh attempt is cleanly separated from the failed host and whether there is any prior authority or namespace that must be quarantined.
- **Concrete minimum fix:** Before provisioning another pod, attach and mechanically verify:
  1. the failed pod’s ownership receipt;
  2. the cited self-hashed termination audit with receipt SHA-256 `0ee006d588e6a244ba0441e65535660e423f7db123defd349e4951e7960c5ec0`;
  3. a deterministic retrieved-tree inventory showing the presence or absence of the five named authorization/execution/output artifacts;
  4. the designated output-tree inventory showing zero files; and
  5. the pre/post unrelated-pod inventory record supporting hash `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945`.
  
  This is evidence attachment and verification only; no scientific or controller change is required.
- **Claim affected:** Clean preauthorization failure, non-consumption of one-shot authority, exact-pod termination, and eligibility to create a wholly fresh recovery attempt.

## B19 — Execution is not yet bound to the exact reviewed controller hash

- **Severity:** Blocking execution-provenance defect.
- **Plan section or short excerpt:** “Corrected controller SHA-256: `6d4501c9fc46a72d58dbe3832bb3fd0f17ad056f4955bb8809ccb5b6cd67371c`,” while the controller starts directly from its positional arguments and does not verify or record its own reviewed physical hash.
- **Why it matters:** The review applies to the exact supplied corrected controller, not merely to any script that eventually invokes the frozen issuer. The issue gate independently protects most scientific and authorization fields, but it does not prove that the reviewed split-root bridge was the controller actually launched. Without an external hash gate, the old controller could accidentally be rerun, causing another expensive deterministic failure, or an unreviewed controller could be substituted without a clear lineage record.
- **Concrete minimum fix:** Do not modify the reviewed controller. Add a minimal external launch gate in the ownership/orchestration layer that:
  1. resolves the controller to a canonical, non-symlink regular file;
  2. hashes it immediately before execution;
  3. requires exact SHA-256 `6d4501c9fc46a72d58dbe3832bb3fd0f17ad056f4955bb8809ccb5b6cd67371c`;
  4. binds that hash to the fresh pod ID, ownership-receipt hash, F10 commit, fresh attempt ID, and argument vector or canonical argument digest; and
  5. launches that same verified path without an intervening copy or rewrite.
  
  Preserve the resulting launch receipt with the failed or successful recovery evidence. A simple hash-check-and-`exec` wrapper is sufficient; no scientific source or controller-byte change is needed.
- **Claim affected:** Deterministic execution of the reviewed B17 repair, controller lineage, and interpretation of any subsequent failure or success.

# Important non-blocking findings

## I10 — The production failure mode lacks a frozen exact-controller regression artifact

- **Severity:** Important non-blocking missing evidence.
- **Plan section or short excerpt:** “A local real-path probe created a second physical ACTIVE bootstrap copy…” and “A separate independent agent reproduced the split-root bridge…”
- **Why it matters:** These are useful outcome-masked validations, but their executable probe, inputs, transcript, and hashes are not included. The acknowledged old test fixture used a `__file__` monkeypatch and therefore did not exercise the production physical-module binding. The bridge is simple enough to inspect and is also fail-closed, so this does not by itself block execution after B18–B19, but the exact regression could otherwise be lost in future revisions.
- **Concrete minimum fix:** Preserve one outcome-free regression artifact that runs the exact bridge body or exact controller issue segment against distinct physical `SOURCE` and `ACTIVE` bootstrap copies and verifies:
  - source-root issuer and Git/provenance identity;
  - active-root `__file__`;
  - canonical `sys.modules` identity;
  - successful `_bootstrap_manifest_binding()`; and
  - failure when the old source-root bootstrap is used.
  
  The smallest repair is to archive the already-performed probe script and transcript with hashes. A new broad test suite is unnecessary for this one execution.
- **Claim affected:** Reproducibility of the B17 repair and prevention of recurrence; not the inherited scientific claim.

## I11 — The bridge is intentionally unconfined and should not be described as part of the confined startup guarantee

- **Severity:** Important wording boundary.
- **Plan section or short excerpt:** “The bridge exists only for the unconfined, preauthorization issuer.”
- **Why it matters:** The bridge uses `/usr/bin/python3.11 -B -` rather than the final child’s direct `-B -E -s -S` bootstrap. That is consistent with the old reviewed preauthorization issuer and is not a new confined scientific execution path. However, combining the bridge with statements such as “all startup is direct, no-site, and confined” would overstate what the controller demonstrates.
- **Concrete minimum fix:** Retain the explicit distinction:
  - the issue bridge is an unconfined, preauthorization administrative issuer;
  - the final launcher/bootstrap path is direct, `-B -E -s -S`, manifest-bound, guarded, and Landlock-confined; and
  - no scientific audit computation occurs in the bridge.
- **Claim affected:** Startup isolation, leakage-prevention wording, and interpretation of the Landlock evidence.

## I12 — Fresh-attempt separation should be an explicit launch gate rather than inferred from naming convention

- **Severity:** Important non-blocking operational hardening.
- **Plan section or short excerpt:** “May a wholly fresh pod, attempt ID, namespace, ownership chain, authorization, and controller hash be used without changing frozen scientific source or reusing any authority?”
- **Why it matters:** The controller ensures that the selected `BASE` and `ATTEMPT` paths do not already exist, but the timestamp-shaped attempt ID alone does not prove it differs from every historical attempt or belongs to the newly owned pod. The fresh ownership and issue checks likely provide further binding, but the external launch decision should explicitly reject the failed attempt ID and old pod ID rather than relying on operator memory.
- **Concrete minimum fix:** In the B19 launch receipt/gate, require:
  - new pod ID not equal to failed pod `9n5f5a82p1gw1e`;
  - new attempt ID not equal to `calv2-r3-audit-recovery-2479ed0-20260715T155035Z`;
  - no pre-existing base, attempt, authorization, or output path for the new ID; and
  - no authorization file copied from any historical namespace.
- **Claim affected:** Temporal separation, one-shot authority, and failure handling.

# What should remain unchanged

1. **The frozen scientific design and claim boundary**
   - Preserve all v7 conclusions for B01–B16 and I01–I09.
   - Keep the result framed as a technical recovery of a frozen audit over previously generated raw tensors.
   - Do not call the result a new model experiment, replication, population estimate, or additional evidence from a fresh model transaction.
   - Preserve the eight fixed `prompt_id` units, three directions averaged within prompt, prompt-level bootstrap, primary layer 50 and dose 0.03, and descriptive-only status of layers 51–78.
   - Preserve the no-population-generalization, no increased-power, and no across-layer-selection boundaries.

2. **Hook, position, tokenization, cache, and readout semantics**
   - Keep the intervention at zero-based block 50 output, post-block 50/pre-block 51.
   - Keep capture-before-edit ordering and the final rendered generation-prompt token.
   - Keep `token_ids[0:-1]` as the prefix and `token_ids[-1]` as the one-token continuation.
   - Keep equal prefix computation, independent cache clones, signed branches, pre-edit equality, and upstream layer 45–49 equality.
   - Reuse no generated continuation text as later input.
   - Keep the explicit post-edit block-50 output as the primary Jacobian source, post-block outputs 51–78 as later sources, and block-79 output/final-RMSNorm input as the target.
   - Keep `residual_delta @ J_l.T`, final RMSNorm, selected LM-head token readouts, central effect `(plus-minus)/2`, and the frozen common-mode and centering conventions.

3. **SAE/Jacobian-lens compatibility and controls**
   - Keep checkpoint SHA-256 `335056c17f0c24053c8c8c1eff168ef49e5a62ca590ffc29c84cf352ecd3ab03`.
   - Require metadata `n_prompts=125` and `d_model=8192`.
   - Require every map 45–78 and pass exactly those 34 maps downstream.
   - Keep extra maps only in recovery provenance.
   - Preserve wrong-orientation, identity, five seeded random-J, BF16/FP32 shadow, native BF16 equality, signed common-mode, and nonfinite/partial-data rejection controls.
   - Do not reinterpret transport rows, directions, doses, readout layers, orientation fixtures, or J-fitting prompts as independent units.

4. **The B17 bridge architecture**
   - Keep cwd at `SOURCE`.
   - Keep the canonical plan, issuer, `authorize`, `validate_plan`, Git metadata, review artifacts, and historical provenance checks rooted at `SOURCE`.
   - Keep the physical active bootstrap loaded from `ACTIVE` under its canonical module name before importing `audit_recovery`.
   - Keep the source and active bootstrap hash checks and all current identity assertions.
   - Keep dispatch restricted to parsed command `issue`.
   - Do not use `cd ACTIVE`, `GIT_WORK_TREE=ACTIVE`, provenance-file copying into `ACTIVE`, a `__file__` monkeypatch, or a relaxed manifest validator.

5. **The active manifest and final confined execution**
   - Keep the exact 131-file active closure and separate 41-file provenance tree.
   - Keep the external root manifest and physical active-bootstrap check.
   - Keep the direct active bootstrap and launcher invocation with `-B -E -s -S`.
   - Keep exact import-root inventories, ordered `sys.path`, startup guards, Landlock policy, device identity binding, descriptor/mapping audits, and both canary matrices.
   - Keep the preauthorization final-scope CUDA/Landlock probe.
   - Keep the final execution child derived from the authorization receipt rather than reconstructed by the controller.

6. **Authorization and failure semantics**
   - Keep authorization creation exclusive with `O_EXCL`.
   - Keep the final namespace empty before issue.
   - Keep the Landlock receipt as the event that consumes authority before same-PID `execve`.
   - Keep the attempt marker exclusive and commit-scoped.
   - Permit no retry, alternate output namespace, or reused authorization under the same authority.
   - Keep success incompatible with `FAILURE.json`.
   - Keep the 1,800-second live remaining-time gate and do not extend or reset the provider-creation-bound clock.

7. **Branch and review lineage**
   - Keep F10 commit `2479ed0c767fba7c872dbbd48666b5a598e2b9f6`.
   - Keep the live remote freeze check in the authentic issue gate.
   - Keep the v7 review SHA-256 `75607c805f68833f5826175c66a89544dbcb4b65a9471803ffd806c65f600672` and supplied adjudication immutable.
   - Keep all B01–B16 and I01–I09 dispositions.
   - Do not regenerate or reinterpret the scientific review because of this external launcher-only correction.

8. **Outcome masking and reproduction boundaries**
   - Do not inspect or use any target audit output before authorization.
   - Preserve the distinction between raw-data integrity, endpoint equality, process-tree confinement, and continuous external immutability.
   - Continue to describe the result as receipt-verifiable/offline-verifiable rather than publicly end-to-end reproducible unless all raw and cache artifacts are actually made available.

# Minimal revised design

1. **Close the failed-host evidence boundary**
   - Add the failed pod ownership receipt, retrieved-tree inventory, zero-file output inventory, termination audit, and unrelated-pod inventory evidence specified in B18.
   - Verify their physical and self-hashes.
   - Confirm mechanically that the failed attempt has no authorization, attempt marker, failure receipt, compact audit, compact summary, or publication marker.
   - Preserve the failed attempt tree as immutable historical evidence; do not delete or reuse its namespace.

2. **Bind launch to the reviewed controller**
   - Use an external hash-and-exec gate for `final_recovery_controller_f10.sh`.
   - Require controller SHA-256 `6d4501c9fc46a72d58dbe3832bb3fd0f17ad056f4955bb8809ccb5b6cd67371c`.
   - Bind the verified controller hash to F10, the fresh pod ownership receipt, the new attempt ID, the expected provider creation time, and the launch argument digest.
   - Reject the old controller hash `1a1baa67fa9c12b8af309581ff85d1e200af907b80cd0b8185eb8f9a68cd08cc`.
   - Execute the same verified physical file immediately after the gate.

3. **Create exactly one fresh attempt**
   - Use a new receipt-owned B200 pod, new pod ID, new attempt ID, new base directory, and new `/workspace/csae` namespace.
   - Explicitly reject failed pod `9n5f5a82p1gw1e` and failed attempt ID `calv2-r3-audit-recovery-2479ed0-20260715T155035Z`.
   - Create no authorization until all source, provenance, cache, manifest, device, final-scope preflight, review, timing, and fresh-namespace checks pass.

4. **Run the corrected controller without scientific changes**
   - Check out exact F10 and require the live branch still resolves to F10.
   - Stage the exact 131 active files and 41 provenance files.
   - Repeat the complete 156-GB cache preflight and final-scope Landlock/CUDA probe on the actual fresh host.
   - Build the manifest for the physical `ACTIVE` root.
   - Run the supplied split-root issue bridge from `SOURCE`.
   - Require a new exclusive authorization and then run the unchanged final confined child once.

5. **Retrieve, terminate, and verify**
   - Retrieve either the exclusive success bundle or failure evidence.
   - Terminate the exact fresh pod and preserve an independently checkable termination audit.
   - Run the frozen network-free offline verifier.
   - Release no scientific claim unless compact publication and offline verification both succeed.

This is the smallest decisive revision. It adds missing incident evidence and an external controller-hash execution gate; it does not alter any frozen scientific source, test, prompt, intervention, model artifact, J-lens rule, statistic, threshold, or claim rule.

# Freeze checklist

- [ ] B17 remains recorded as the physical source/active bootstrap binding failure.
- [ ] The old controller remains SHA-256 `1a1baa67fa9c12b8af309581ff85d1e200af907b80cd0b8185eb8f9a68cd08cc`.
- [ ] The corrected controller remains SHA-256 `6d4501c9fc46a72d58dbe3832bb3fd0f17ad056f4955bb8809ccb5b6cd67371c`.
- [ ] The corrected controller is not edited after this review.
- [ ] An external canonical-file hash gate verifies the corrected controller immediately before execution.
- [ ] The launch receipt binds controller hash, F10, fresh pod ownership, provider creation time, new attempt ID, and launch arguments.
- [ ] The old controller hash is explicitly rejected.
- [ ] The failed pod ownership receipt is attached and verified.
- [ ] The failed-host termination audit with cited receipt SHA-256 `0ee006d588e6a244ba0441e65535660e423f7db123defd349e4951e7960c5ec0` is attached and verified.
- [ ] The failed attempt’s retrieved-tree inventory is attached and verified.
- [ ] The failed designated output inventory proves zero files.
- [ ] The failed attempt contains no `RECOVERY_AUTHORIZATION.json`.
- [ ] The failed attempt contains no `ATTEMPT_STARTED.json`.
- [ ] The failed attempt contains no `FAILURE.json`.
- [ ] The failed attempt contains no `CALIBRATION_AUDIT.json`.
- [ ] The failed attempt contains no `CALIBRATION_SUMMARY.json`.
- [ ] The failed attempt contains no `PUBLICATION_COMPLETE.json`.
- [ ] The unrelated-pod inventory evidence supports hash `4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945`.
- [ ] No authority or namespace from the failed attempt is reused.
- [ ] The fresh pod ID differs from `9n5f5a82p1gw1e`.
- [ ] The fresh attempt ID differs from `calv2-r3-audit-recovery-2479ed0-20260715T155035Z`.
- [ ] The fresh `BASE`, `ATTEMPT`, authorization, and output paths do not pre-exist.
- [ ] Frozen F10 remains `2479ed0c767fba7c872dbbd48666b5a598e2b9f6`.
- [ ] The checked-out worktree is clean and the authentic issue gate confirms the live remote freeze.
- [ ] The v7 review and adjudication remain byte-identical.
- [ ] B01–B16 and I01–I09 retain their prior dispositions.
- [ ] No scientific source, test, model, prompt, intervention, hook, estimand, statistic, threshold, or claim rule changes.
- [ ] The active closure remains exactly 131 files.
- [ ] Historical provenance remains exactly 41 files and separate from the active import root.
- [ ] Both source and active bootstrap files retain SHA-256 `616104d2711fd9ae18f5cf930e2dcf497d6b113a718b78b812f4bd7383ab227a`.
- [ ] The issue bridge runs with cwd equal to canonical `SOURCE`.
- [ ] `audit_recovery`, `authorize`, and `validate_plan` retain `REPO_ROOT == SOURCE`.
- [ ] The issuer’s physical `__file__` is the expected source `audit_recovery.py`.
- [ ] The preloaded bootstrap’s physical `__file__` is the expected active `confined_bootstrap.py`.
- [ ] The canonical bootstrap module was not imported before active binding.
- [ ] `audit_recovery.confined_bootstrap is active_bootstrap`.
- [ ] The active bootstrap constants remain schema version 1, status `approved_exact_python_import_roots`, and the frozen relative path.
- [ ] The bridge permits only parsed command `issue`.
- [ ] No `__file__` monkeypatch is used.
- [ ] No `cd ACTIVE`, alternate Git worktree, or provenance copying into `ACTIVE` is introduced.
- [ ] The final confined launcher/bootstrap remains direct `-B -E -s -S`.
- [ ] The final child continues to use the same physical active bootstrap bound by the manifest.
- [ ] The complete public-artifact cache is rehashed on the fresh host.
- [ ] The final-scope Landlock/CUDA preflight is repeated on the fresh host.
- [ ] At least 1,800 seconds remain before authorization.
- [ ] The final namespace is empty before authorization.
- [ ] A new authorization is created exclusively and only after every gate passes.
- [ ] The authorization binds the fresh pod, fresh namespace, exact command, manifest, devices, receipts, deadline, budget, review, and F10 lineage.
- [ ] No historical authorization is treated as current authority.
- [ ] Landlock receipt creation consumes the new authority before same-PID `execve`.
- [ ] Attempt marker remains exclusive and commit-scoped.
- [ ] No retry or alternate output namespace is allowed under the same authorization.
- [ ] No model forward, target render, target feature extraction, generated-text carryover, or prior audit outcome input occurs.
- [ ] Hook, token position, cache clone, J orientation, final RMSNorm, LM-head readout, signs, and controls remain unchanged.
- [ ] Independent units remain the eight fixed prompts.
- [ ] Directions are averaged within prompt and bootstrap resampling remains prompt-level.
- [ ] Layer 50/dose 0.03 remains the sole primary estimand.
- [ ] Layers 51–78 remain descriptive only.
- [ ] No population, increased-power, or across-layer-selection claim is made.
- [ ] Success cannot coexist with `FAILURE.json`.
- [ ] No success is published at or after the recovery deadline.
- [ ] The exact fresh pod is terminated after retrieval or failure handling.
- [ ] A fresh termination audit is preserved.
- [ ] The retrieved bundle passes the frozen network-free offline verifier before release.
