"""Future-use cue discovery v2; not a repair or rerun of a frozen experiment.

Zero/nonfinite activations cannot enter high sets. Boundary ties are retained
as a whole, not truncated alphabetically. Cues retain per-feature attribution;
assignment fails explicitly rather than borrowing another feature's cues.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from fractions import Fraction

TOKEN = re.compile(r"[a-z]+(?:'[a-z]+)?")


def terms(text, stop_words=()):
    tokens = TOKEN.findall(text.lower())
    stop = set(stop_words)
    return ({t for t in tokens if t not in stop}
            | {" ".join(pair) for pair in zip(tokens, tokens[1:]) if not any(t in stop for t in pair)})


def discover_cues_v2(items, activation_rows, *, high_fraction=.1, cue_limit=12,
                     minimum_document_frequency=5, stop_words=()):
    """Return a deterministic, versioned lexicon with auditable positive support.

    high_fraction is a fraction of finite measured items, capped at positive
    support; all activation-boundary and ranking-boundary ties are retained.
    cue_limit is therefore a soft limit. This is a lexical enrichment heuristic,
    not semantic validation. Stop words and thresholds must be frozen by users.
    """
    if not 0 < high_fraction <= 1 or cue_limit < 1 or minimum_document_frequency < 1:
        raise ValueError("Invalid cue-discovery thresholds")
    texts = {}
    for row in items:
        if row["item_id"] in texts:
            raise ValueError("Duplicate item")
        texts[row["item_id"]] = row["text"]
    item_terms = {k: terms(v, stop_words) for k, v in texts.items()}
    by_feature = {}
    for row in activation_rows:
        item, feature = row["item_id"], int(row["feature_id"])
        if item not in texts:
            raise ValueError("Activation references unknown item")
        values = by_feature.setdefault(feature, {})
        if item in values:
            raise ValueError("Duplicate item-feature activation")
        values[item] = float(row["max_activation"])
    features = {}
    for feature, values in sorted(by_feature.items()):
        if set(values) != set(texts):
            raise ValueError("Incomplete activation grid")
        finite = {k: v for k, v in values.items() if math.isfinite(v)}
        positive = sorted(((v, k) for k, v in finite.items() if v > 0), reverse=True)
        n_nominal = min(len(positive), math.ceil(len(finite) * high_fraction))
        cutoff = positive[n_nominal - 1][0] if n_nominal else None
        high = {k for v, k in positive if cutoff is not None and v >= cutoff}
        all_df = Counter(c for k in finite for c in item_terms[k])
        high_df = Counter(c for k in high for c in item_terms[k])
        candidates = []
        for cue, support in sorted(high_df.items()):
            if all_df[cue] < minimum_document_frequency:
                continue
            enrichment = Fraction((support + 1) * (len(finite) + 2),
                                  (len(high) + 2) * (all_df[cue] + 1))
            score = math.log(float(enrichment))
            if enrichment > 1:
                candidates.append({"cue": cue, "score": score,
                                   "enrichment_numerator": enrichment.numerator,
                                   "enrichment_denominator": enrichment.denominator,
                                   "high_positive_document_frequency": support,
                                   "all_finite_document_frequency": all_df[cue]})
        rank = lambda r: (Fraction(r["enrichment_numerator"], r["enrichment_denominator"]),
                          r["high_positive_document_frequency"])
        candidates.sort(key=lambda r: (-rank(r)[0], -rank(r)[1], r["cue"]))
        threshold = rank(candidates[min(cue_limit, len(candidates)) - 1]) if candidates else None
        selected = [r for r in candidates if rank(r) >= threshold] if threshold else []
        features[str(feature)] = {"n_nonfinite_excluded": len(values) - len(finite),
                                  "n_positive": len(positive), "n_high_nominal": n_nominal,
                                  "n_high_with_ties": len(high), "activation_cutoff": cutoff,
                                  "high_item_ids": sorted(high), "cues": selected}
    attribution = {}
    for feature, record in features.items():
        for cue in record["cues"]:
            attribution.setdefault(cue["cue"], []).append(int(feature))
    return {"version": "positive_support_cue_discovery_v2", "features": features,
            "pooled_cue_attribution": dict(sorted(attribution.items())),
            "parameters": {"high_fraction": high_fraction, "cue_limit_soft": cue_limit,
                           "minimum_document_frequency": minimum_document_frequency,
                           "stop_words": sorted(set(stop_words))},
            "tie_policy": "Retain all boundary ties; lexical order is display order only."}


def assign_feature_cues_v2(text, feature_id, lexicon, *, count=2, offset=0):
    if count < 1 or offset < 0:
        raise ValueError("Invalid assignment count or offset")
    tokens = TOKEN.findall(text.lower())
    def present(cue):
        cue_tokens = TOKEN.findall(cue.lower())
        return any(tokens[i:i + len(cue_tokens)] == cue_tokens
                   for i in range(len(tokens) - len(cue_tokens) + 1))
    available = [r["cue"] for r in lexicon["features"][str(feature_id)]["cues"] if not present(r["cue"])]
    if len(available) < count:
        raise ValueError("Insufficient absent cues for assigned feature; no cross-feature fallback")
    chosen = [available[(offset + i) % len(available)] for i in range(count)]
    return {"assigned_feature_id": feature_id, "assigned_cues": chosen,
            "cue_discovery_version": lexicon["version"]}
