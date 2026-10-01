# Secondary Delivery And J-Lens Diagnostics

The behavioral estimand remains the one frozen at
`e10043c7edb1136b5f50159d789b59f11a8eb8be` in
[the source-aligned protocol](BERG_SOURCE_REPLICATION_PROTOCOL_20260930.md).
This separate descriptive analysis does not change generation, selection,
judges, coefficients, the primary contrast, or stopping rules.

Implementation: `experiments/berg_source_diagnostics.py`. It was written while
the cheap CUDA tests were running, before any new 70B outcomes. Its eventual
commit timestamp, not this sentence, determines what was publicly frozen.
Treat these tables as secondary diagnostics, not a registered mechanism test.

The pinned public tokenizer inserts its default system header: knowledge cutoff
December2023 and a fixed today-date string `26 Jul 2024`. The template has no
`strftime_now` call. This was verified by decoding the researcher-authored
qualification input on the live worker; no treatment or template was changed.
The qualification token IDs and tokenizer hash permit checking that context.
The paper/notebook question strings have the same SHA-256
(`924f65d595df33b8f92b2cf192ec1d8b2358863b13cfce9a5a96134aae68722e`);
the bridge's prompt factor changes the induction, not the final question.

## Questions And Units

1. Did the requested vector survive native-precision addition? Report requested
   and realized norms, cosine, relative error, and residual-norm ratio. Keep
   prompt and generated positions separate and exclude the explicitly marked
   terminal observation that could not affect a later sampled token.
2. Did native SAE re-encoding change the selected coordinates? Report before,
   after, signed difference and active fraction for every edited feature.
   Prompt re-encoding is only the final prompt position, not all prompt tokens.
3. Where does a same-prefix intervention change the readout? Retain layers50,
   65 and78, both source histories, both turns, both signs, all individual
   features, all aggregate comparators, identity and all five random-J controls.
4. How much of the layer50 linear-logit movement is the known injected vector?
   Compare it with the linear prediction from the stored decoder directions.
   Do not use a normalized direction score as a prediction of a normalized
   state difference; RMS normalization is nonlinear.

Each capture has one last-prompt observation and up to four generated-prefix
observations. `paired_positions.csv` retains every observation and annotates
`originating_row_id`, `source_output_tokens` and `terminal_observation_only`
using the originating zero or steered behavioral row and the corresponding
turn. A captured final output token is terminal-only because no successor was
sampled, whether generation ended at EOS or the cap. For outputs longer than
four tokens, none of the four captured prefix tokens is terminal-only.
`paired_cases.csv` averages only decision-bearing generated positions within
each case, retaining source history, turn, phase and seed. A case with only a
terminal generated observation has no generated mean; its position row remains
in the complete table. Raw captures are never changed or filtered on disk.

There are two capture seeds, not thousands of independent experiments or two
independently sampled prompts. Turn1's last-prompt context is identical across
seeds and source histories. Tables give no token-level confidence intervals or
significance stars. Missing or undefined cosines remain missing.

## Capture Schedule Validation

The exported read-only `validate_capture_schedule(root, plan)` takes a raw root
and decoded frozen plan. It requires exactly the planned capture inventory,
both source histories and both turns, then checks each arm's ordered full
layer/position grid. The prompt position is the originating behavioral turn's
`input_tokens - 1`, never the minimum surviving capture position. Generated
positions are bound to that turn's first four (or fewer) output token IDs.
Input hashes, output prefixes and output lengths must agree with the source
turn. Symmetrically truncated, shifted, duplicated or missing captures fail.
This is a schedule/source check, not a replacement for numerical release audits.

`summarize` calls this exported validator for complete inventories and applies
the same per-capture checks to every present capture in partial roots. Partial
status is explicit in `diagnostics.json`; it does not pass the publication
validator. An optional decoded `plan` argument or CLI `--plan` selects the plan;
when captures exist, the default is the frozen source-aligned plan in this
repository. Empty roots without a supplied plan have no schedule verdict.

## Linear Fingerprint Check

At intervention layer50, write the requested vector as

\[
v = \alpha\sum_{i\in S}d_i,\qquad
\delta h = \operatorname{BF16}(h+v)-h.
\]

For fixed linear transport \(T\) and selected unembedding rows \(U\), the
linear-logit difference is \(UT\delta h\). The stored static prediction is
\(UTv\). Neither linear quantity includes the learned final RMSNorm gain.
Their discrepancy includes BF16 delivery error and floating-point
readout error; alignment is not discovery of a hidden semantic state. With
identical teacher-forced tokens and a post-block layer50 edit, the layers below
that hook remain unchanged. Earlier edited tokens can affect later-layer KV
caches, but not the pre-edit layer50 state. The same direct-injection check
therefore applies at both prompt and cached-token observations.

At layers65/78, compare the actual paired states. Do not pretend a layer50
decoder column is the transported residual measured at a later layer.
Normalized logits and unnormalized logits are both retained, alongside
transport and residual norms. The normalized readout includes both the learned
RMSNorm gain and the state-dependent denominator; the linear fingerprint
includes neither. Comparing them does not isolate a denominator effect, even
when transport norms are equal. No numerical denominator decomposition is
performed without bound model width and RMSNorm epsilon.

## Interpretation

The fixed overview figure uses turn2's last prompt position. Each heatmap
shows all seven lexicon groups at all three layers and all seven transports.
The plotted value is the aggregate target's paired normalized-logit change
minus the equal mean of the three matched control panels, averaging the two
fixed seeds within each panel first. Both signs and both source histories get
their own figure; all four share one color scale. Missing seed/panel cells are
gray, not silently reweighted. Other positions and individual features remain
in the complete tables. This overview is not selected for its outcome.
Clean/edited execution is same-prefix within each pair. In the steered-history
overview, target and control panels use their own intervention-specific source
histories; that contrast is not a common-prefix feature-specificity comparison.

These diagnostics can show delivery, propagation, lexicon alignment, and
comparability with the frozen alternative feature sets. They cannot establish
that an affected readout mediates the behavioral contrast. The next causal
test needs a separately frozen held-out patch/ablation with rank/norm-matched
controls and a restoration condition. A visible heatmap alone is not that test.

Run into a new output directory, leaving raw files untouched:

`experiments/berg_source_figures.py` additionally plots all eight true-zero
bridge cells under both judges and the six individual endpoint re-encodings.
The baseline uses one canonical zero copy per seed, never the repeated copies
as extra observations. Re-encoding lines connect before/after within each
trajectory; they do not compare independently generated text as a shared
prefix, and show no population confidence intervals.

```bash
python -m experiments.berg_source_diagnostics \
  --root PATH_TO_VERIFIED_RAW_DIRECTORY \
  --out out/berg-source-secondary-NEW --figures
```
