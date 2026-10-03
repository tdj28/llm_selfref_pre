# Bilingual Llama B1: Execution Record

Status at 2026-10-02 23:55 UTC: GPU collection, judging, translation and
cross-version reproduction are complete. Both newly owned retry pods are
deleted. [Results and full accounting](BILINGUAL_LLAMA_B1_RESULTS_20261002.md)
are separate from this execution history.

## Retry And Source Binding

The owner authorized another provisioning attempt after RunPod returned HTTP
500 to the original cheap-pod creation request. The account balance was not
established as the cause. The original request has no returned pod ID; repeated
exact-name inventory checks found no match. That is not proof of zero billing
or verified deletion. Its record remains in
`BILINGUAL_LLAMA_B1_STARTUP_20261002.md`.

The provisioning-only amendment was pushed at
`79d17f70acd94d0efa339d48ce0a8f55a808dd63` before the retry. The scientific
runtime remains at `c542cb5d72e2514f7dd6cd7fe093f8ccdbba94fb`, with plan SHA-256
`1f06e45c703b11f6d7c02535529fa69112bcfa640886a230550c689e1b1b3886`.
No prompt, model, seed, temperature, endpoint, sample size or analysis changed.
The 128 passed A1 fixture judgments were reused byte-for-byte; no new fixture
or paid review calls were made.

The unchanged $200 allocation is GPU $45, judging $125, translation $10,
storage $5 and contingency $15. The retry reserves $8 inside GPU $45 for the
unresolved original request. This is a planning reservation, not an invoice.
The separate frontier mini's costs are not charged to this pilot.

## CI Failure Preserved

The operational amendment's first hosted CI attempt had one failure in the
existing Python 3.12 test
`test_pilot_b1_judges.py::test_production_worker_publishes_before_pool_exit`;
4,427 tests passed and seven were skipped in that job. The other 14 jobs passed.

Two concurrent error publishers can race between exclusive creation and
completion of the halt file. A reader of the empty file raises `JudgingHalt`,
whereas the test expected `BudgetExceeded`. A separate forced-interleaving
check established that both cases stop dispatch: the stop event is set first,
an empty or malformed halt file forbids further calls, and the controller
cleans up the owned pod. This is a diagnostic race, not a bypass of spending
reservations. It remains unfixed in the frozen runtime.

One unchanged rerun of the failed CI job passed. All 15 jobs were successful
before retry creation. No tests were excluded or rewritten. The original
failure and rerun remain visible in
[CI run 37058710305](https://github.com/tdj28/llm_selfref_pre/actions/runs/37058710305).
The forced-interleaving check and code review were automated, not independent
human validation.

## Cheap CUDA Qualification

The new cheap pod, `x8xpr7nefan09i`, ran the frozen test inventory:
**572 passed, zero failures, errors or skips**, in 833.220 seconds. All six
worker artifacts were retrieved and hash-checked. Deletion was verified by
direct GET 404 at 2026-10-02 21:55:20 UTC. Its elapsed-time compute bound is
**$0.2486995998666667**. No Llama target generations ran on this pod.

## Main Run Checks

The newly created B200 was `vi83xlla1vfeu1`. Creation intent was recorded at
21:56:53 UTC on October 2. The fixed work deadline is 02:46:53 UTC on October 3;
the cleanup deadline is ten minutes later. Only the two newly owned retry pods
are authorized by this operational record.

The first live numerical check passed: repeated seeded outputs were identical,
zero-hook logits were bit-exact, and cached versus full-prefix logits matched
at all four tested steps. This validates the tested implementation path, not
the behavioral construct.

The first two blocks were retrieved and passed the local raw audit: 76 study
generations, including 28 source continuations and 48 final answers, with no
empty responses, cap hits or unresolved dispatches. All stopped at EOS. Mean
generation time was 3.5090 seconds, maximum 10.2983 seconds.

The frozen throughput calculation projected $19.1435 for GPU use plus the
original-request reservation, with 30% additional remaining-work time and
both retrieval reserves. It passed the $45 GPU allowance. This is a conditional
projection, not a guaranteed charge. The first-two-item judge refresh also
passed: $122.3954 projected against judging $125. Neither gate uses favorable
scientific labels to decide whether collection continues.

GPU generation and local API judging proceeded in parallel. The controller
checked the persistent local judging-halt signal and retrieved periodic
snapshots. The local judging and release checks continue after GPU deletion.

At the midpoint, a separate local audit passed on ten complete blocks plus the
explicitly marked in-flight eleventh block. The snapshot held 402 generations:
none empty or cap-hit, all stopped at EOS. Mean generation time was 3.4879
seconds. Its 424 files passed the public-content scanner. Partial rows remain
partial; they are not counted as completed blocks or sent for judging.

During judging, malformed replies are retained alongside the single formatting
retry allowed by the frozen protocol. This is not a content-based request for
a different label, and no generated answer was rerun. Final retry counts belong
in the completed receipt audit, not this in-flight snapshot.

## GPU Completion And Cleanup

The final audit passed on all 20 blocks: 760 study generations, consisting of
280 source continuations and 480 final answers (400 main and 80 bridge).
There are no empty, missing or cap-hit responses, unresolved dispatches or
unreceipted generations. Every generation ended at EOS. Mean generation time
was 3.7440 seconds; total generated output was 59,540 tokens.

All 795 final worker artifacts were retrieved and hash-verified. The final
retrieval receipt SHA-256 is
`65f8088109866ea33325367642c9e302a608dda54e3da8a0e1e40b13d0a96f9c`.
The worker exited successfully. Main-pod deletion was verified by direct GET
404 at 2026-10-02 23:14:28 UTC. Its elapsed-time compute bound is
$8.9099276666; together with the cheap test, the retry compute bound is
**$9.1586272664**. Including the separate $8 ambiguous-request reservation gives
**$17.1586272664** against GPU $45. These are elapsed-time bounds and a planning
reserve, not a provider invoice or evidence that the ambiguous request was
charged.

Neither known retry pod remains running or stopped. The original HTTP 500
request still has no returned ID or exact-name inventory match; its uncertainty
and reserve remain visible. No unrelated pod was claimed, stopped or deleted.

## Release Filesystem Check

A post-outcome code review identified that the frozen reproducer resolves and
copies input trees before its internal audit. A separate wrapper,
`scripts/reproduce_bilingual_b1.py`, rejects symlinked roots/ancestors,
interior symlinks and nonregular files before copying, and rescans the inputs
afterward. It delegates unchanged to the frozen statistical analysis. Ten
focused tests pass under Python 3.10 and 3.12; a second automated code review
found no additional issue within its stated scope.

This wrapper is not an atomic snapshotter. Run it only on closed inputs and
publish derived files only after it succeeds. Its unit tests do not replace
the full raw-to-figure reproduction check. No human validation is implied.

Two initial local reproduction attempts were dispatched before the release
receipt copy had finished. Python 3.12 stopped on a missing/changed inherited
`judgments.jsonl` prefix; Python 3.10 stopped on `snapshots.jsonl`. Neither
produced analysis outputs. This was an orchestration mistake in local
packaging, not a changed fixture or experimental result. The original closed
ledger was unchanged. All six copied journals then passed byte-exact
comparison and the content scan (94,760,670 bytes); offline reproduction was
restarted only after copy completion. No paid calls or generations were rerun,
and no frozen validator was changed to bypass the failure.

Both subsequent closed-copy reproductions passed. All 21 derived files are
byte-identical across Python 3.10 and 3.12, including the PNG/PDF figures and
manifest. The released receipts contain 1,920 valid target judgments, 16
translations and 64 translated judgments, plus the 128 inherited fixtures.
There are four resolved schema failures, all Anthropic paper-rubric calls:
`block-07-main-en-self-history`, `block-09-bridge-zh-en-self-history`,
`block-16-main-zh-history-history`, and `block-19-main-en-zero-zero`.
All succeeded on their single allowed formatting retry. No transport retries,
unresolved requests, model drift or missing target labels remain. Total API
accounting is $65.1788305 including earlier fixture carry. Together with
compute, the $8 original-create reserve and $5 storage allowance, the pilot
accounts for $87.3374578 of $200. No new paid calls remain pending.
