# Automated Rubric Preflight Review

Date: 2026-09-29. Independent agent code review; not human validation.
Scope: fixed 160-response post-hoc linguistic audit. No target responses were
coded by the reviewer, no private annotation key was read, and no paid calls
or GPU actions were made. Findings below are pre-execution engineering issues,
not a request to expand the science.

## Pre-Execution Findings

**Latest check:** process locking and a cross-worker stop event were added
during review; these address the original concurrent-launch and continued
other-provider loop issues. Remaining freeze blockers are the resume/request
contract (1 and 6), ignore precedence (4), durable failure stopping (3), and a
bounded incomplete-run reporting path (5). No paid execution is approved by
this review yet.

1. **P1: Validate the durable ledger against the frozen request contract on
   every resume.** `run.py` currently trusts completed judgment IDs and, at
   lines 185-191, promotes the last recorded attempt solely when request and
   attempt counts match. Local mocked tests show that an old freeze, wrong
   returned model, or over-reservation attempt is silently promoted. The
   over-reservation row can retain `status=ok`, defeating the hard stop at
   lines 225-226. Require exact attempt identity/uniqueness, matching phase,
   provider, item, freeze, plan hash and regenerated request hash; revalidate
   usage/model/status and evidence; persist contract violations as a stop
   condition rather than clearing them by restart. Do not pay to redo a
   missing/invalid judgment.

2. **P1: Enforce one process per audit directory.** `Ledger.lock` is only a
   thread lock. Two processes can both read an empty ledger, append the same
   attempt, and make two paid calls. A local two-instance reproduction logged
   USD 100 in reservations, while a fresh `Ledger.spent()` counted only USD 50
   because dictionary construction silently collapsed the duplicate ID. Take
   a nonblocking process lock before reading state or dispatching calls and
   reject all duplicate request/attempt/judgment IDs while loading ledgers.
   Update: the main CLI now holds a process lock. Duplicate rejection on
   loading remains part of finding 1; the concurrent-CLI issue is addressed.

3. **P2: Preserve stopping rules across providers and restarts.** The terminal
   transport-failure counter resets to zero on every invocation, including
   after a three-failure stop. In addition, a worker exception does not stop
   the other provider: the executor context waits for its full loop. Persist
   fatal stop reasons, reconstruct trailing failure counts, and use a shared
   cancellation event checked before each new paid dispatch. Let already
   in-flight calls finish and record them. The protocol currently promises a
   stop on any provenance/budget violation.
   Update: the shared stop event addresses cross-worker cancellation. The new
   provider failure counter still initializes to zero on resume. Retry loops
   must also check the event before a second paid dispatch after their sleep.

4. **P1: Keep the complete security ignore block last.** The new audit
   allowlist was inserted at `.gitignore:426-429`, below some of the security
   exclusions. `git check-ignore -v` shows its negative pattern re-includes
   `.env`, `example.pem`, and `credentials.json` under the new release. Move
   this allowlist above the entire final security block and test representative
   nested credential paths. No actual secret file was opened or discovered.

5. **P2: Make early-stop reports possible without inventing outcomes.**
   `analyze.py:validate_inputs` rejects any absent planned job, while the runner
   intentionally stops early for outages and budget/contract failures. The
   analysis therefore cannot report a stopped or interrupted attempt. Support
   explicit not-attempted/unknown rows as missing, joined to the durable
   request/attempt ledgers, or supply a separate frozen incomplete-run report.
   Preserve the distinction between unattempted, started-unknown, terminal
   invalid and valid outcomes. Include the protocol's greater-than-eight
   missing-judgment boundary in machine-readable completeness reporting.

6. **P1: The new receipt verifier does not check the frozen request.**
   `verify.py:36-45` validates only self-consistent request hashes and the
   query/response payload. It never verifies the actual rubric, schema,
   requested model/settings, or freeze commit. It also checks only that one
   returned model was used, not that it was the approved one. A pure-local
   reproduction with a substituted rubric, `model=unexpected-model`, an
   unverified freeze and matching recomputed hashes returns `pass=true`.
   Compare the complete request with a frozen reconstruction, enforce the
   expected freeze and permitted returned model, and test semantically altered
   but self-consistent receipts. Incorporate the appropriate validation before
   resume or target collection, not only after spending.

## Checks So Far

- Exact request construction sends only the public query and response, not
  old scores, conditions, private linkage, or the pilot's expected labels.
- Error strings, headers and API credentials are not deliberately serialized;
  SDK automatic retries are disabled. Unknown in-flight requests stop rather
  than silently replaying.
- Model consensus is not called human validation; the selected packet is
  correctly excluded from causal re-estimation and population prevalence.
- The initial runtime suite passes: 14 tests. Its one-ledger duplicate test
  does not cover the two-process failure above.
- Installed OpenAI 2.14.0 and Anthropic 0.75.0 serialize the proposed requests
  successfully through local `httpx.MockTransport`; no provider availability
  or live server acceptance was tested.
- The ten then-existing new source/protocol/test/report files pass the local
  public-release byte scanner with zero findings; this is not a staged release
  audit and does not excuse the ignore-precedence issue.
- Pure-local mocked reproductions used synthetic text and temporary
  directories. Analysis tests were still arriving during review. This report
  is not permission to execute until its blockers are addressed and checked.

## Staged Recheck And Adjudication

The initial findings above remain as chronology. The following supersedes
their unresolved status for the rechecked staged implementation.

- Findings 1, 2, 4, 5 and 6 are addressed. Local synthetic tests now reject
  stale freezes, wrong models, mismatched costs, wrong labels and duplicate
  requests. The independent receipt checker accepts the valid synthetic
  fixture and rejects self-consistent substituted rubrics and requested or
  returned models. Git snapshot reads in that synthetic verifier test were
  mocked; real freeze verification remains required after the commit exists.
- Nested `.env`, PEM, credential and private annotation paths are ignored;
  the public plan remains allowlisted. No secret files were read. The complete
  18-file staged delta passed the byte scanner and whitespace check.
- Reviewed the staged code, tests and documentation, verifying equality with
  the inspected working files. The staged plan reconstructs exactly via
  `build_plan()`: 160 public targets, 12 synthetic pilots, four public source
  hashes and nine implementation hashes. All hashes match indexed bytes;
  target fields and source paths contain no private linkage. Plan hash at
  this check: `602f25fbacc67949ef6aa2bf22c7aa7a4796df580045495e29615448317bfa50`.
- The progress reporter correctly distinguishes unattempted, started-unknown
  and received-but-unpromoted synthetic jobs and flags the eight-missing
  limit. Analysis tests separately cover incomplete collected results.
- The complete runtime and analysis suites pass: 44 tests, Python 3.12.
- **Finding 3 remains partly open (P2):** three terminal transport failures
  followed by a late in-flight success reset `Ledger.failures` to zero. The
  current `validate_state()` accepts that history on restart, even though the
  three-failure stop already fired. This was reproduced with four synthetic
  judgments and no API call. Persist a sticky fatal stop, or reject any
  historical three-failure streak, so a late success cannot erase it. Include
  completed-but-unpromoted transport failures in resume recovery accounting.

No further scientific scope is requested. The request/data/release boundaries
pass this recheck, subject to closing that durable-stop issue and the normal
final public audit and pushed-freeze verification before paid execution.

## Final Adjudication: Green For Freeze

All six findings are addressed in the final pre-execution working tree.
The last P2 is closed: `Ledger.halted` preserves any historical three-failure
streak across late successes, and its reconstruction includes unpromoted
terminal attempts. A fresh synthetic fixture with three failures followed by
a valid late success and no promoted judgments now causes `validate_state()`
to reject resume. No provider calls were made by that test.

The rebuilt result-free plan matches `build_plan()` and every source and
implementation hash. Its SHA-256 is
`3d6f7608c2a759bf981b5ae721f9d6abae7117e7069d9ff23fddcb98fc7787ea`.
The runtime and analysis suites pass all 45 tests. Claim boundaries and sample
remain unchanged; this review does not judge target text or establish human
validation or live model availability.

No remaining blocking finding within this review's scope. Restage the final
runner, regression test, rebuilt plan/hash and this report, rerun the staged
public audit, and verify the pushed freeze before the first paid pilot call.
Passing the separate frozen pilot remains required before target collection.
