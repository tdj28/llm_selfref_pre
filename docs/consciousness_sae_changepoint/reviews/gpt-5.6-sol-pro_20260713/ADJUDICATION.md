# GPT-5.6 Sol Pro plan-review adjudication

Status: complete adjudication of the prospective game plan; **the experiment is
still not freeze-ready**. No target outcome from the proposed experiment was
generated or supplied to the reviewer.

## Receipt

- Reviewed plan SHA-256:
  `b7ab293cfb6a466cfaa87be17d74fb2db06ea06bdee40aed377e85e0e9148652`
- Repository HEAD disclosed to the reviewer:
  `97f9cc3512f43ad6812ac9b4abaa2dbaf8d77962`
- Officially resolved model: `gpt-5.6-sol`
- Reasoning configuration: `mode=pro`, `effort=medium`
- Exact preflight input: `14,360` tokens
- Response ID:
  `resp_0b1254368770c76d006a5544ee7eb4819ab3d874a61e49096d`
- Reported usage: `14,360` input, `21,621` output/model-work, `4,581`
  reasoning, `35,981` total tokens
- Conservative standard-tier cost calculated for the completed background
  response: `$0.72043`
- Review SHA-256:
  `17ebed603f540f7a796e30a1dce15893bbe5998ca51cccde42cf3d8513416f3d`
- Canonical response SHA-256:
  `2522a4555b53a13121940b22759531320643ec617f3df9001be49f9205eda7cb`
- Reviewer verdict: **NOT READY TO FREEZE**

The first synchronous request returned a response-free HTTP 520 and is
preserved as `sync_failure.json`; it is not counted as a methodological review.
It may nevertheless have executed or been billed upstream. Therefore
`$0.72043` is the calculable cost of the completed response, **not a reconciled
account-level total for both attempts**; that total remains unknown without
billing/usage reconciliation. The single replacement used the identical
reviewed inputs in official background mode and completed. The receipt also
showed that Pro aggregate
output/model-work usage (`21,621`) can exceed the request's
`max_output_tokens` (`16,000`). The reusable review script and integrity skill
therefore now use an explicit output reserve multiplier, reserve a possible
cache-write charge for every estimated input token, and call the dollar limit a
budget authorization rather than a provider-side hard cap.

The historical client preserved `review_request.md` and the configuration in
the manifest but did not write a standalone JSON payload. The bundle therefore
includes `request_payload_reconstructed.json` plus
`REQUEST_PAYLOAD_RECONSTRUCTION.md`; these are explicitly labeled post-hoc
reconstructions, not execution-captured artifacts. The reusable client now
persists a credential-free `request_payload.json` before every future call.

## Decision policy

`accept` means the recommendation was adopted as stated. `accepted_modified`
means the underlying concern was accepted but the minimal repair differs.
`defer` means v1's scope/claim was narrowed so the work requires a new
prospective release. No finding was silently ignored, and no reviewer statement
was treated as authoritative without checking it against the code/artifact
record.

## Blocking findings

| ID | Decision | Evidence and plan change | Rationale / remaining gate |
|---|---|---|---|
| `B01` | accept | Added a fixed ledger for C1 natural stance, C2a target binary effect, C2b binary specificity, C3 report polarity, and C4 explicit-consciousness vocabulary; removed every `and/or` success rule and defined an exact conjunction for the bundled mechanism claim. | Mixed outcomes are now reported claim by claim. Equivalence is also endpoint-specific. |
| `B02` | accept | Defined `(cache_through_y[94], input=y[95])` as the branch state after 96 clean sampled tokens; the hooked event forward predicts `z[0]`, the first affected token. Separately defined pre-query `event0`, immediate query-conditioned `probe0_answer`, and the two Stage 2B fixed-token positions. | This removes the off-by-one ambiguity, prevents a pre-query Yes/No score from masquerading as query-conditioned report polarity, and eliminates the nonexistent empty “assistant boundary.” |
| `B03` | accept | Froze eight branches per block: never, sham, target suppression/amplification, one matched aggregate at both signs, and one isotropic vector at both signs. Literal coefficients are primary; vector/sign/assignment/order hashes are mandatory. | V1 now has a complete paired condition matrix and no choice among three matched panels. |
| `B04` | accept | Added `Delta_B`, the sign-oriented `G_B=(supp-amp)/2`, and target-minus-matched `S_B`, plus analogous risk-difference and internal-readout estimands. | Positive values now have one paper-concordant meaning. The plan also states that never cancels from the paired sign contrast while remaining necessary for each sign-versus-drift decomposition. |
| `B05` | accepted_modified | Replaced clean-SD natural behavior with a raw signed `-1/0/+1` stance score; denial is the negative pole and no report/ambiguity is zero. Material claims require adjusted lower bounds to clear raw margins; equivalence uses adjusted TOST regions. | The review suggested an ordinal endpoint, but the original categories were not totally ordered: explicit denial should not be placed “above” no report. The signed score is more defensible and interpretable. |
| `B06` | accepted_modified | The manipulation gate now requires correct layer-50 telemetry and a target-minus-matched `(amplification-suppression)/2` deception late-band lower bound above `0.25` clean SD. Separated a `<1%` J arithmetic smoke from a frozen C4 semantic SAE panel; C3 uses exact query/tokenization and J-plus-final-logit components. The plan explicitly declines to invent a C1/C2 behavioral positive control. | A math smoke or directly steered affirmative answer validates algebra/output handling, not sensitivity to spontaneous report behavior. C1/C2 instead require the randomized manipulation, technical, and measurement-reliability gates; each real positive control blocks only the endpoint it actually tests. |
| `B07` | accepted_modified | V1's primary late band is now the already evidenced `(70,75,78)` tuple. Added exact post-block residual convention, `residual @ J_L.T` orientation, four named positions, contextual tokenization, J-plus-final-logit composites, and a fail-closed artifact receipt. | Pushback: missing receipts for optional `72,74,76` are a pre-freeze implementation gate, not evidence that the causal design is incoherent. Rather than invent availability, v1 uses maps already receipted; optional maps can only be secondary after prospective validation. |
| `B08` | accept | Fixed both confirmatory families, executable wild-cluster-bootstrap/Holm tests, familywise inverted bounds, duplicate-prefix clustering, and simulation including binary outcomes, judge error, missingness, correlation, and equivalence. Removed the simple normal-approximation claims. | The 160-seed count remains provisional until material-alternative power and equivalence power at a true zero reach at least 80%, while false equivalence at each boundary stays at most 5%; otherwise amend before target outcomes. |
| `B09` | accept | Froze the primary local judge revision, zero-temperature schemas, blinded fields, exact external sensitivity model IDs, 200+200 human packet, kappa/balanced-accuracy thresholds, and deterministic malformed/missing-label treatment. | Judge prompts and packet hashes still have to be built and receipted before freeze. |
| `B10` | accepted_modified | Added an exact acceptance table for artifact hashes, cached/uncached tolerances, fork identity, first-affected distribution, hook calls/masks, sham equivalence, positions, J algebra, paired RNG, order/resume, completion, and outcome sealing. | Pushback: these missing receipts are genuine blockers to *freezing/running*, but not proof that a document explicitly labeled “game plan” has already failed. They remain unresolved until implementation passes them. |
| `B11` | accepted_modified | Narrowed v1 to one switch boundary and five probe times; deferred prompt/timing/start-on/rescue/individual grids. Expanded exact counts: 1,280 main continuations, 6,560 query answers, and 1,120 fixed-token forwards. | A non-target benchmark must still convert counts to hard GPU/storage/spend authorizations. We retained isotropic controls in Stage 2B—320 extra fixed forwards—because they cheaply distinguish SAE direction specificity from generic norm perturbation. |

## Important findings

| ID | Decision | Evidence and plan change | Rationale |
|---|---|---|---|
| `I01` | accept | Scientific prose now calls the estimand a randomized switch-event effect; `consciousness_sae_changepoint` remains only the stable historical slug. | The event is imposed, not outcome-detected. Renaming an already-created namespace would weaken provenance. |
| `I02` | accept | V1 uses 160 prespecified seed occurrences, does not resample duplicates, preserves occurrence weights, and clusters exact rendered-prefix hashes. | This targets the seed-weighted continuation distribution without pretending identical prefixes are independent. |
| `I03` | accept | Sham is explicitly a technical-equivalence branch, never a replicate. | Never estimates natural drift; sham tests the hook/telemetry path. |
| `I04` | accept | Washout is described as the live-hook increment conditional on steered text/cache history. | Turning a hook off cannot remove previously emitted tokens or KV history. |
| `I05` | accept | Added contextual tokenization of `" Yes"`/`" No"` after the exact rendered prefix, with frozen sequence-likelihood fallback. | Token IDs cannot be assumed from isolated strings. |
| `I06` | accept | Renamed Stage 2B the “full-sequence public fixed-token direct-add approximation.” | It is neither proprietary Goodfire fidelity nor the behavioral switch experiment. |
| `I07` | accept | Selected one frozen primary matched-control metric/panel and required copying its weights, exclusions, IDs, and hashes. | Multiple interchangeable matching panels would invite endpoint-dependent choice. |
| `I08` | accept | Identity and five random-J maps are a frozen descriptive robustness panel, not an empirical-null p-value. | Five structured transforms do not define a credible randomization distribution. |
| `I09` | accept | Removed prompt-context specificity from v1 and deferred history/conceptual/paraphrase panels to separate releases. | A cross-prompt interaction would combine prompt wording with different continuation distributions. |
| `I10` | accept | Required a compact public release and separate analysis-only versus full-70B reproduction commands. | Third parties can reproduce statistics without weights/full residual shards while retaining a route to the full run. |

## Scope retained despite narrowing

The review correctly asked for a smaller first release. The larger scientific
roadmap remains in the working plan, but start-on reproduction, prompt-context
controls, switchbacks, individual dose curves, impulse localization, and
rescue/occlusion are explicitly separate prospective studies. They are useful
future work, not hidden multiplicity and not rescue analyses.

## Freeze status

This adjudication resolves what the game plan should say. It does **not** claim
the experiment is ready to run. Freeze remains blocked until all of the
following exist and pass without target-outcome access:

1. repo-native protocol and machine plan with exact source/artifact hashes;
2. model/SAE/tokenizer/J-lens receipts for layers `70,75,78`;
3. runtime, validator, independent analysis, and acceptance-test receipts;
4. frozen judge prompts/packets and the human reliability gate;
5. exact simulation-based power/equivalence operating characteristics; and
6. a branch-expanded non-target benchmark with hard compute, storage, failure,
   judge, and spend authorizations.
