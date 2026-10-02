"""Reuse the frozen mini provider functions with their original module globals.

No configuration is patched: model IDs, prices, caps and request bytes stay fixed.
"""

from experiments.frontier_bilingual_mini.providers import (
    JUDGES, MODELS, OUTPUT_CAPS, generation_request, generation_result,
    live_sender, model_matches, receipt_cost, reservation,
)
