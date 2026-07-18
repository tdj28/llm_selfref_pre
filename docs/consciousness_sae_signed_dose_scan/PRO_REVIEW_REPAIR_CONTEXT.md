# Repair context for the bounded final Pro verdict

The first API attempt in this review cycle used `gpt-5.6-sol` Pro and response
`resp_0d725b1d34b49014016a59587e5ce4819a97cddbfd930fa3be`. It ended
`incomplete` because of `max_output_tokens`, so it is not an adjudicable review.
It used 22,459 aggregate input tokens and 12,456 aggregate output tokens, for a
conservatively reconstructed cost of $0.485975 at the frozen $5/$30 per-million
rates. No raw data or runtime logs were submitted.

Integrity hashes of the locally retained, Git-ignored attempt are:

- request payload: `49cc70de5e886064e16b17f95aa8f24d5b473aac58a345284dae9629e3044cce`
- response: `55499ac6e3802d14beeecf810f45d9528322fecce3aa0e2e6e84f22852f7d67f`
- failure receipt: `d7c4055c6aee78d2f2f84d61d7ce98bd413302f1ca4006bc75c4069eb4d979ce`
- review manifest: `97ac6d274e499a20a5807873e9e80c2831a5b6befd500d88a1bb97c89f5354ad`
- rendered review request: `a93cc80d6fd390b4e5a8b48b86b7b3c37c50aed6c96a53bffc72584b63dac890`

The useful portion identified three blocking omissions and four important
clarifications. This successor packet repairs them without changing the grid,
model count, prompt count, direction count, J-storage boundary, raw-data
policy, or cost envelope:

1. The exact fixed-census claim, continuation token, edit timing, observed
   residual sites, requested and realized dose formulas, clean-referenced
   branch responses, central/common-mode formulas, and one primary
   cell-resolved layer-by-dose output are now frozen. Aggregates are diagnostic.
2. The pre-existing numerical thresholds are now disclosed with an exact
   validity hierarchy: any transaction-integrity failure invalidates the whole
   transaction; any anchor delivery failure makes the fixed-panel primary
   result ineligible rather than null; diagnostic-dose delivery failures stay
   visible but cannot delete rows; J failures affect J claims only.
3. The full grid is scheduled before outcomes, model outcomes are not inspected
   during execution, scientific oddity cannot stop or replace a run, partial
   attempts remain aborted/incomplete, and a retry requires a new authorization
   for an enumerated mechanical failure. The same authorization cannot select
   among attempts.
4. The intended use is diagnosis of intervention mechanics and generation of
   safe-range hypotheses for a separately reviewed later study; this scan does
   not select a preferred dose.
5. The five random-J controls and their fresh deterministic seed rule are
   fixed; comparisons apply only to those exact controls.
6. The panel is explicitly a census, never 2,880 independent samples, and every
   prompt-direction curve remains visible.
7. A generic direction is now exactly a fresh seed-committed PCG64 standard-
   normal float32 vector normalized to unit RMS, with no outcome-dependent
   orientation, selection, or rejection.

Please determine only whether these repairs resolve the stated blockers and
whether they introduced a new stop-ship inconsistency. Keep the final review
compact and end in exactly one terminal verdict line.
