# Audit-Recovery Pro Review Adjudication

## Provider status and cost

One latest-model Pro call was made for the bounded recovery plan and structural
context. The requested and returned model was `gpt-5.6-sol`; the review helper
verified it against the official latest-model document before submission.

The provider returned `status=incomplete` with
`incomplete_details.reason=max_output_tokens`. Response ID:
`resp_0ae53ab3f19b0df6016a56d79f0f5c8199bae81011a0ff14c3`. Usage was 20,570
input tokens and 8,215 output tokens, of which 6,635 were reasoning tokens.
At the frozen $5.00/M input and $30.00/M output rates, the reconstructed call
cost is $0.34930, within the $0.75 authorization. This is not an account-level
billing reconciliation.

The call was incomplete, did not receive the later executable source/tests,
and did not approve the recovery. No second paid call is authorized or made.
Adjudication below applies only to the visible response.

## Visible verdict

The reviewer agreed that required-subset semantics are technically justified:
the runtime already requires the study layers as a subset, the artifact is
physically hash-pinned, the calculations use only layers 45–78, and extra maps
0–44 are target-independent and unused. It found no need for a fresh model
execution solely because of the equality-versus-subset audit bug.

The reviewer returned `NOT READY TO FREEZE` on the plan-only packet. Its visible
response identified the following blocking or stop-ship issues.

## Adjudication

### B01 — Executable correction was not supplied or mechanically confined

Decision: accept and fix locally, with an explicit provider-review limitation.

The recovery source and focused tests are frozen, committed, and bound before
authorization. The immutable r3 `audit.py`, protocol, metrics, and calculation
modules retain their exact r3 hashes. The new entry point makes only the
checkpoint-inventory scientific compatibility correction; its other adapters
are confined to fresh operational authority and isolated historical-source
validation.
Tests require an authentic 0–78 superset to pass; required-layer omissions,
wrong metadata/hash, noncanonical/duplicate identifiers, downstream-source
drift, and scientific-output divergence to fail. Authorization reopens the
source closure and verifies clean local/tracking/live-remote equality.

The executable tree is an exact allowlist with no runner, guest launcher, or
model runtime. Historical bytes required by the frozen validator are copied to
a separately hash-bound, kernel-read-only provenance tree that is absent from
`PYTHONPATH` and denied by an import guard. The sole audit dependency formerly
provided by the old runtime, `tensor_sha256`, is supplied by an audit-only shim
and mechanically compared with the frozen implementation.

The provider did not review this later code. Passing tests and local review
close the implementation gate operationally but are not relabeled as provider
approval.

### B02 — Zero model forwards were asserted but not technically enforced

Decision: accept and fix.

Fresh guest/cache receipts must begin at zero forwards and zero target access.
The recovery entry point installs guards that raise on every
`torch.nn.Module` call and the Transformers base model-loader families, plus an
import guard for all runner/runtime entry points, while allowing only tokenizer
loading, safetensor reads, and direct tensor replay. The compact recovery
receipt records zero guard firings; any firing aborts publication.

### Visible stop-ship summary — Raw tree was not made read-only

Decision: accept and fix.

The canonical raw run path and isolated historical provenance path must be
verified kernel read-only bind mounts for the recovery process, including
mount root/source/device/ID provenance. Failure to establish either aborts.
Full hashes are checked before computation and again before success
publication.

### Visible stop-ship summary — Publication preceded the final raw gate

Decision: accept and fix.

The wrapper obtains the in-memory audit and summary, rehashes the entire raw
tree against both `RUN_COMPLETE.json` and the external 36-file ledger, and only
then calls the atomic compact publisher.

### Visible stop-ship summary — Deadlines and spend limits were unset

Decision: accept and fix.

The fresh audit-only authorization is exactly 30 minutes and $3.00 at the
conservative $6.00/hour rate, starting exactly from the validated fresh
ownership receipt's provider creation time. Its provider deadline is also
required to equal that receipt. The old execution clock remains historical
provenance, not authority for the new pod.

### Visible stop-ship summary — Failure disclosure conflicted with “no publication”

Decision: accept and clarify.

Failure forbids compact scientific *success* publication. A commit-scoped
authorization binds one output namespace and is consumed by an exclusive
attempt marker. Every catchable post-claim failure preserves a sealed
operational failure receipt, stderr log, source and command hashes, fresh pod
receipts, and termination proof; an uncatchable loss still leaves the marker
and cannot be retried under that authority.

## Independent actual-code review after the provider call

The later local code review found additional authorization-clock,
failure-evidence, disclosure, loader-guard, mount-provenance, one-shot, and
executable-compartment gaps. Those findings were accepted rather than hidden:
the provider clock is now ownership-bound, both compact files carry the full
recovery disclosure, base loader families and imports are guarded, mountinfo
provenance is recorded, the attempt is single-use, and historical runner bytes
are confined to the non-importable provenance tree. Focused tests cover these
mechanisms and the prepublication ordering. This remains local adjudication,
not a claim that the incomplete provider reviewed the later implementation.

### Visible stop-ship summary — “Outcome input” wording was inconsistent

Decision: accept and clarify.

The prospectively frozen r3 raw outputs are the primary subject of the audit.
The prohibited set is external or prior outcomes used to adapt, select, pool,
or judge the recovery; that set is empty.

## Local pushback and limitations

The plan does not accept an implication that merely reading the frozen r3 raw
transaction is outcome contamination; doing so would make any audit
impossible. It accepts the reviewer's narrower and correct concern about using
external/prior outcomes adaptively. It also retains the reviewer's conclusion
that the target-independent loader predicate does not itself require a new
model execution.

The visible response truncates during B02, so this adjudication does not claim
that all provider reasoning or findings were received. Final authorization
must bind this incompleteness, the exact response/failure/manifest artifacts,
and the locally verified source/test closure.
