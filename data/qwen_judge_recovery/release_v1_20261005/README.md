# Qwen3.8 judgment recovery

This additive release preserves the original incomplete archive and fills only eligible missing Astra structured judgments. No response or completed judgment was regenerated. Every new physical attempt, including failures and unresolved charges, is in the raw journal.

Original archive: https://github.com/tdj28/llm_selfref_pre/tree/ad49e88f9cd4235670686ddcd5933ff9b98eb3be/data/openrouter_swap_openweights_a2/main_v1_20261004

`evidence/editorial.md` and `figures/primary_contrasts.pdf` compare the original and repaired estimates. The fixed four-comparison family and planned-block missingness bounds are unchanged. Qwen3.8 is not the older Qwen3.5 companion model.

Verify offline with `python -m experiments.qwen_recovery_release --verify PATH --manifest-sha256 SHA`. Verification requires the pinned original archive and execution-freeze Git objects in this repository. It recomputes judgments, costs, rows, analyses, prose and figure data. `--verify-render` additionally rerenders images with the recorded Matplotlib version.

A closed launch is required for export. Pending calls or identity/accounting failures require reconciliation; the exporter cannot resolve them.
