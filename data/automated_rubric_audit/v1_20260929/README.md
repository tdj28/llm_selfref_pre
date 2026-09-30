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

Authorized after the calibration gate. Results and completion status will be
added after the planned collection, frozen analysis and receipt audit finish.
