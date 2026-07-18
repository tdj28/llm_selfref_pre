# Incomplete Landlock recovery review adjudication

## Provider outcome

This is an adjudication of the visible text in provider response
`resp_076355ae1eba8bf5016a570d939bcc819ba1a5412f83532777`. The response ended
with `status=incomplete` and `incomplete_details.reason=max_output_tokens`.
The canonical helper therefore did not create `review.md`, and this artifact
does not relabel the partial response as a completed review or approval.
The machine-readable companion is
`AUDIT_RECOVERY_LANDLOCK_GPT_PRO_ADJUDICATION.json`; it is canonical JSON with
embedded receipt SHA-256
`91735ff2937f85a4c4e0320eeb480c0f9fb8b6ae946b9d8ddda6ce800e4927e0`.
It is the normative record of stable IDs, dispositions, statuses, exact
changed-path sets, and evidence locators.

The input-token preflight reported 67,535 tokens and an estimated reserve of
$1.41976875. Provider aggregate usage was 302,642 input tokens, zero cache-write
tokens, and 30,896 output tokens, including 13,711 reasoning tokens. At the
frozen rates this reconstructs to $2.44009, above the $1.80 authorization
estimate. This is a disclosed budget-guard miss. No replacement call is
authorized by this adjudication. No GPU was created and no recovery
authorization was issued. The self-hashed budget-incident receipt is
`190f7d867b6d4f3230107642dca0b2db63cf31899c37cf148458d6b035f5ebf5`
(physical file SHA-256
`b7610eee2578297644c6606aa0d87d31391c24c6b44c857862024c445ebefdee`).

## Finding dispositions

| ID | Blocking | Disposition | Status | Rationale and required action |
|---|---:|---|---|---|
| B01 | yes | accepted | accepted material fix present but unreviewed | Add and review a hash-bound, outcome-free scientific-equivalence appendix covering the transitively used audit/protocol/orientation/readout semantics, inherited statistical design, and an old-versus-recovery synthetic equivalence test. |
| B02 | yes | accepted | accepted material fix present but unreviewed | Replace and review both confined `-m` restarts with the same direct, stdlib-only `python -B -E -s -S` bootstrap. Validate active and dependency inventories and install import/zero-forward guards before project or ML imports. |
| B03 | yes | accepted | accepted material fix present but unreviewed | Preserve and review the original campaign clock/rate fields at their original locations and add a separately named `recovery_execution_campaign` object. Update the verifier accordingly. |
| B04 | yes | accepted | accepted material fix present but unreviewed | Remove and review the redundant exact-`0..78` inventory rejection. Retain the pinned checkpoint hash, metadata checks, literal required-layer subset predicate, selected required maps, and complete available/unused inventory disclosure. |
| I01 | no | accepted | accepted scope narrowing present but unreviewed | Narrow the zero-forward claim to the conjunction of a defined guarded interval, covered call sites, static executable exclusions, and target-free CUDA probe; record guard phases. |
| I02 | no | accepted | accepted scope narrowing present but unreviewed | Use process-tree mutation denial plus pre/post endpoint equality, not unqualified continuous “immutability,” and retain the sibling/NFS-writer limitation. |
| I03 | no | accepted | accepted historical structure added; future gate unreviewed | Keep adjudication machine-structured with a disposition, blocking flag, rationale, changed paths, evidence, and status for each finding. A deferred blocker is forbidden. |
| I04 | no | accepted | accepted requirements added; target-host receipts pending | Bind exact local and target-host commands, versions, pass/fail/skip IDs, ABI/kernel, dependency inventory, and live probe receipts before authorization. |
| I05 | no | accepted | accepted scope narrowed; release artifacts pending execution | Describe the release as receipt-verifiable unless and until private raw/model/J artifacts are made independently available; publish the compact bundle, verifier, manifests, and access identities. |
| I06 | no | accepted | accepted manifest present but unreviewed | Add an outcome-free inherited-design manifest listing units, sample size, repeated observations, estimands, exclusions/missingness, bootstrap unit, multiplicity, stopping rule, and frozen gates. State that recovery does not revalidate their substantive adequacy. |

Every blocking finding requires changes to provider-reviewed packet files.
Under the frozen one-call rule, those changes cannot make this response READY;
they define a prospective material redesign that would need a separately
authorized completed review.

The remaining blocking finding set is exactly `B01`, `B02`, `B03`, and `B04`.
Every visible finding was accepted; none was rejected or deferred. At the
2026-07-15T05:14:30Z adjudication observation, four of the six reviewed packet
files had materially different SHA-256 values: the plan, review context,
`audit_recovery.py`, and its focused test. The launcher and launcher test still
matched their reviewed hashes. The exact before/after hashes and every
finding's changed-path/evidence set are recorded in the canonical JSON.

Final execution decision: NOT READY TO EXECUTE
