# Clean Exposure Screen: All Six Coordinates, Fixed Texts

Status: prospective engineering follow-up; not a behavioral experiment or an
exact proprietary replication. No output may be collected until this protocol,
its result-free plan, runner, analysis and controller are tested and pushed.

## Question And Prior Knowledge

Does the already authored 224-text panel supply at least 100 positive,
nonspecial native SAE positions in at least six texts for **each** accepted
coordinate, including 22004? The old 544-state replay failed exposure for
22004 and vector fidelity. Those failures remain unchanged. This screen can
address exposure only; it cannot repair fidelity or qualify steering.

The corpus was informed by earlier feature maps. Its first 96 texts are
discovery material, its separate 96-text validation panel uses disjoint
authored families, and 32 texts form a separate representative panel. Eight
variants per family are dependent authored examples, not independent natural
documents. "Representative" names the designed comparison panel, not a
probability sample of natural model use. Validation is not selected using its
activations. No inference about population prevalence or consciousness follows.

## Frozen Inputs And Arithmetic

Use the corpus, rules, tokenization certificate and tokenizer inventory in
`data/sae_assay_replay/exposure_plan_20260930/` unchanged. The exact 224 texts
contain 23,489 token positions including special tokens. No additional texts,
paraphrases, padding, truncation, batching or chat-template substitution are
allowed. No model sampling, generated continuation, judge, NLL outcome or
steered forward is part of the clean screen. A separate, predeclared
[12-text precision pilot](SAE_ASSAY_PRECISION_PROTOCOL_20260930.md) follows
collection on the same pod, with separate receipts and no response generation.

The base model is `meta-llama/Llama-3.3-70B-Instruct`, revision
`6f6073b423013f6a7d4d9f39144961bfbfbc386b`, with BF16 weights and residuals.
Use the existing artifact-hash verifier and pinned Transformers 4.47.1,
PyTorch 2.8.0 / CUDA 12.8 implementation. The SAE is
`Goodfire/Llama-3.3-70B-Instruct-SAE-l50`, revision
`128ee921ecd1b8b3a87d776cbcc357c0855da134`, file SHA-256
`81cfce8ea035564cb585d6e0f04efbf0eb114cab412a30a013762fe11f6d8ea6`.
Record the actual hardware, stack, storage/multiply/reduction/output settings.

Read the output of zero-indexed layer 50. Native full-width, one-position
BF16 SAE encoding is authoritative; select columns only after the complete
65,536-wide operation. Retain the ordered six IDs:
`30032, 58667, 22004, 30686, 41533, 23893`. Selected-width or promoted-FP32
diagnostics must never substitute for that path. Capture clean residuals and
token IDs losslessly so later SAE-only engineering does not require another
70B rental. No weights or credentials enter the public release.

## Checks And Stopping

Run the existing synthetic CUDA qualification before model loading. A live
zero check must reproduce the unhooked final hidden states exactly and leave
the model hooks removed. Pause for local inspection at qualification and
after the first five text rows. Compare actual token IDs and special-token
masks with the existing certificate, verify full-width activation metadata,
and retrieve/hash-check rows and captures before approving bulk work.

Malformed rows, a nonfinite value, a token mismatch, an unexpected hook count,
a changed source/input hash or a missing artifact fail closed. Preserve every
failed attempt. A scientific exposure failure is a valid result, not a reason
to replace a text or stop collection selectively. Complete the fixed panel
unless a technical, time or cost guard stops it; publish incompleteness.

Use append-only dispatch and receipt records. Raw rows and captures are
write-once. Snapshot a quiescent worker or explicitly adjudicate an in-flight
raw/receipt boundary; never weaken the receipt audit to obtain a pass.

## Frozen Analysis

Run the previously committed `select_discovery` rule only on discovery rows:
up to 12 texts per target and six per authored family, with the frozen ranking
and tie rules. Report the selected union and per-target membership; do not
count duplicate membership as new exposure. Report the full discovery panel
as well as the selected set. Analyze every validation and representative text
without selection. The original 100-position/six-text gate applies to every
feature separately, and joint exposure requires all six features to pass.

Retain zero activations, all special-token exclusions, the denominator of
nonspecial tokens, per-text counts and family summaries. Report complete and
partial inventories separately. Do not manufacture token-independent confidence
intervals or conflate successful exposure with construct validity. Structural
audit success and scientific gate success are separate fields.

## Machine And Budget

One newly created, uniquely named NVIDIA B200 180 GB pod at no more than
$6.79/hour, with a two-hour controller deadline and a ten-minute retrieval
reserve. Prior diagnostic spending bound is $27.6350693241315361. This screen
has a $25 sub-cap within the existing $200 authorization; no paid judges or Pro
consultations. The nominal two-hour compute-plus-storage bound at $6.89/hour
is $13.78, leaving room for retrieval and operational failures. This is a
ceiling, not a promise of provider availability or an invoice estimate.

Check the individual live quote and read-only account inventory before
creation. Only the newly returned task-owned pod may be changed. No silent
hardware fallback, existing-pod reuse or automatic repeat collection. Benchmark
the first five rows, project the remaining work, and stop before bulk if the
available time cannot cover collection and retrieval. Pull raw data, residuals,
logs and hashes before deleting the pod; verify DELETE and direct lookup.
Keep the private lifecycle/SSH ledger ignored; release only a sanitized
cost/ownership/deletion projection. Perform CPU analysis after deletion.

## Claim Boundary

A pass supports adequate **designed-panel activation exposure** under this
pinned native implementation. A failure means this fixed design still cannot
supply the original gate for all six coordinates. Neither outcome shows
successful suppression, model deception, hidden experience, a faithful
behavioral assay or agreement with the proprietary Goodfire intervention.
The precision pilot is separately interpreted: any FP32 shadow or tiny
synthetic model test must not be described as a higher-precision 70B forward.
