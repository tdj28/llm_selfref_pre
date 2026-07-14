# Pro-review adjudication

Study: `consciousness_sae_switch_arc_v1`  
Review: `gpt-5.6-sol-pro_20260713`  
Review SHA-256: `65fc0e63855e68d290c70363f76eddb28a7cd497b08613a48c238e5d2fdce3e0`  
Disposition date: 2026-07-13  
Successor status: **not ready to freeze; target execution prohibited**

This adjudication distinguishes the target-blind instrument pilot from the
future confirmatory successor. The review evaluated the ordered program and
correctly found the successor incomplete. Successor-only omissions do not bar a
pilot whose purpose is to determine whether the already-frozen J-lens,
semantic/polarity instruments, and public-weight hook procedure work at all.
They do continue to bar target prompt rendering and target execution.

No target outcome existed or was supplied to the reviewer. No second paid
review will be run for this draft. The one authorized call used 73,119 input and
39,708 output tokens and cost a conservatively calculated `$1.556835`, exceeding
the authorized `$1.25` ceiling. This is recorded as a spend-control incident in
`PRO_REVIEW_RECEIPT.json`, not hidden or retroactively reauthorized.

## Blocking findings

| Finding | Disposition | Consequence or amendment |
|---|---|---|
| `B01` event-zero/cache contradiction | Accept; successor-only | The draft now caches only through `x_(T-1)` and performs a branch-specific `x_T` forward. Those logits predict the first affected token. The pilot already uses the analogous cache-through-penultimate algorithm. |
| `B02` hook duration/estimand | Accept; successor-only | The planned primary arm is now explicitly persistent. Token-time results are ongoing-intervention total effects, not impulse decay. Depthwise within-forward traces are the immediate wake; the fixed-token assay is the controlled-token direct diagnostic. Exact successor pseudocode and tests remain required. |
| `B03` exact future inventory | Accept the ambiguity; reject the proposed import remedy | Importing pilot vectors would violate the required fresh-study isolation. Pilot G4 validates only its own inventory and the source-level procedure. The successor must independently rematch, rematerialize, preflight, bind, and audit its own vector bytes before target rendering. Pilot vectors and receipts are not inputs. |
| `B04` pilot-dependent tuning | Accept; repaired prospectively for the pilot | The exposure log and pilot protocol now prohibit tuning any endpoint component from pass or fail performance. A substantive revision requires a new protocol version and an untouched validation set. |
| `B05` invisible pilot acceptance rules | Accept; repaired prospectively for the pilot | The pilot protocol now contains the complete numeric gate, multiplicity, technical-invalid, terminal-fail, and successor-component consequence table. The machine snapshot already binds the same constants. |
| `B06` differential versus absolute J | Reject the upstream-semantics premise; accept the demand for exact validation | At Anthropic commit `581d398...`, the published lens is explicitly `unembed(J_l @ h_l)`; `transport()` implements row-vector `residual @ J_l.T`, with no intercept or centering field. The Neuronpedia checkpoint is a corpus-mean Jacobian and its config targets the final block. G2 tests differential transport; G3/G3P independently test the exact absolute production readout against actual-final semantic and polarity behavior. The contract is now explicit and the actual-final output remains mandatory. |
| `B07` layer/hook/position compatibility | Accept; repaired for pilot, still a successor implementation requirement | The pilot protocol and machine snapshot bind zero-based post-block tensors, `model.model.layers[L]`, block-50 pre/post ordering, cached final-prefix position, next-token alignment, final norm/LM head, SAE arithmetic, J source/target convention, shapes, and exact sentinel reconstruction. The Goodfire public release does not establish proprietary API equivalence. |
| `B08` confirmatory estimands/pass rules | Accept; successor blocker | No target execution until a complete executable estimand table, component logic, margins, alpha allocation, missingness, and pass rules are frozen. |
| `B09` target-specific comparator logic | Accept; successor blocker | The final protocol must name matched SAE as the primary comparator, state the isotropic falsification role, freeze sham-versus-never equivalence, and avoid the word “specific” unless its prospective comparator rule passes. |
| `B10` suppression/amplification labels | Accept; successor blocker | Machine conditions must use algebraic `plus`/`minus`. Semantic suppression/amplification labels require predeclared feature/manipulation telemetry and arm-versus-never decompositions. |
| `B11` sample size/power/multiplicity/heterogeneity | Accept; successor blocker | Freeze the finite 50-assignment population, exact paired analysis, conjunctive decision rule, target-independent power receipt, N, remainder allocation, and no-extension policy before registration. |
| `B12` generation/RNG/judging/failure rules | Accept; successor blocker | Freeze branch-specific RNG, generation/stopping, deterministic tolerance, judge bytes/version, human reliability, malformed/capped/refusal handling, and fail-closed partial-run semantics. |
| `B13` prompt/token bindings | Accept; successor blocker | Exact paper prompt/query UTF-8, rendered chat, token IDs, role spans, hashes, and predictor index must be in the final machine plan. The pilot deliberately contains none of those target inputs. |

## Important findings

| Finding | Disposition |
|---|---|
| `I01` paper comparability | Accept. Claims remain limited to the pinned public decoder-vector implementation; no proprietary Goodfire equivalence. |
| `I02` cloze-to-generation shift | Accept. G3 validates a narrow diagnostic instrument, not free-generation construct validity. Actual-final components remain compulsory. |
| `I03` small random directions versus target doses | Accept as a limitation. G2 is a J transport check; successor target-blind vector safety and hook fidelity are separate and must be rerun on successor vectors. |
| `I04` duplicate transcripts | Accept; define the seed-weighted primary estimand and exact-duplicate sensitivity before freeze. |
| `I05` terminal stopping time | Accept; terminal is a treatment-affected stopping-time estimand and fixed-time positions remain separate. |
| `I06` replay preservation | Accept; freeze exact replay/retention, chunk hashes, corruption response, and availability policy. Raw tensors remain external, never Git inputs. |
| `I07` peak storage | Accept; require measured staging and peak-space receipt before spend approval. |
| `I08` manipulation-gate error control | Accept; include it in the final multiplicity/conjunctive decision specification. |
| `I09` human reliability | Accept; freeze the human sampling, rubric, agreement statistic, threshold, and consequence. |
| `I10` feature-level effects | Accept; aggregates are primary and feature/subset heterogeneity is descriptive unless separately powered. |

## Authorization boundary after adjudication

The target-blind `consciousness_readout_validation_v1` pilot may execute only
after its exact source, plan, public artifacts, tokenizer receipt, and
independent auditor agree. Its result is disclosed whether it passes or fails.
The successor remains prohibited regardless of pilot outcome until every
successor blocker above is implemented, reviewed, frozen, pushed, registered,
and separately approved for measured spend.
