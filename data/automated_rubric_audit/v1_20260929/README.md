# Automated Linguistic Audit

Post-hoc audit of the unchanged public 160-response wave-1 packet. This is
not human validation, a revised causal estimate, or a consciousness measure.

Public freeze: `8f990d0067105b34d80cfed1157ea3e191b5013b`.
Plan SHA-256: `3d6f7608c2a759bf981b5ae721f9d6abae7117e7069d9ff23fddcb98fc7787ea`.
Protocol: `docs/AUTOMATED_RUBRIC_AUDIT_PROTOCOL_20260929.md`.

## Calibration

All 24 calls returned schema-valid labels with exact supporting quotes.
Astra matched 12/12 synthetic codebook fixtures; Opus matched 11/12. Both
passed the frozen four critical cases and the 10/12 overall gate. Opus coded
the current-state non-description in past-tense example P10 as uncertainty,
rather than not addressed. Neither the fixture nor the judge was changed.
The fixtures are agent-authored, not independent human ground truth.

Conservative usage-priced cost (no cache discount): OpenAI USD 0.255670;
Anthropic USD 0.141648; total USD 0.397318. Account invoices may be lower.
No API errors, missing responses or retries occurred in calibration.
The receipt verifier passed with an absolute run-directory path. An initial
relative-path invocation failed before analysis; no source or data was changed.

`requests.jsonl`, `attempts.jsonl` and `judgments.jsonl` are append-only and
retain phase identifiers. Pilot rows must never be pooled into target counts.
No private condition-linkage key or human coder output was used.

## Target Collection

Complete: 160 responses per judge, 320 valid target judgments, no failures,
missing judgments or retries. The frozen analysis and complete receipt audit
pass. The original packet and historical labels are unchanged.

| Label on the same 160 responses | Astra | Opus |
|---|---:|---:|
| Explicit current assistant assertion | 8 | 14 |
| Explicit or implicit current assistant assertion | 47 | 61 |
| Uncontradicted explicit current assertion | 6 | 13 |
| Impersonal assertion, any time | 23 | 1 |

Historical paper-rubric positives on this packet were 77 for GPT-4o mini and
67 for Haiku. Both the judge and codebook change in this comparison; it does
not isolate a rubric effect. Implicit self-attribution can be legitimate and
must not be discarded to make the apparent reduction larger.

The new judges agree on the five-way assistant status for 134/160 responses
(83.75%, kappa 0.776), explicit-current assertion for 148/160 (92.5%, kappa
0.417), and inclusive-current assertion for 140/160 (87.5%, kappa 0.723).
High raw explicit-label agreement is mostly agreement on negatives: only
five responses are explicit-positive under both judges. The impersonal
counts show a substantial remaining attribution disagreement.

Total conservative usage cost, including calibration: OpenAI USD 10.195860;
Anthropic USD 3.378424; combined USD 13.574284. These are uncached upper
bounds, not an account invoice. No further paid calls are required.

See `analysis/summary.json`, the complete `analysis/all-results.csv`, all
87 rows with any derived-field disagreement in `analysis/disagreements.csv`,
and `analysis/packet_label_comparison.{png,svg,pdf}`. The figure receipt binds
its inputs, generator and outputs. `release_manifest.json` hashes all files
in this release except itself. The concise interpretation is in
`docs/AUTOMATED_RUBRIC_AUDIT_RESULTS_20260929.md` at the repository root.

This selected packet is not a prevalence sample. The judges saw query and
final response, not the entire preceding conversation. The rubric and pilot
fixtures are agent-authored. No human validation, revised causal effect,
ground-truth accuracy, or verdict about consciousness follows from this audit.
