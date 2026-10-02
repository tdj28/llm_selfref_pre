"""Offline, fixed-panel analysis of automated bilingual-pilot labels.

Integration contract: ``analyze_items(items, labels)`` consumes all 480 planned
slots from raw_audit.items_from_raw, including missing responses. Labels map
``(item_id, provider, instrument)`` to a reduced structured dict or paper 0/1.
Providers are openai/anthropic; instruments are structured/paper. Missing keys
or None are missing judgments, never negatives. Structured labels must contain
Boolean inclusive_current_assertion, explicit_current_assertion and mixed.
The older ``mixed`` flag includes general/unspecified times; the separate strict
mixed_current_assertion endpoint remains missing unless explicitly supplied.
Extra Boolean reduced fields, including wrong_requested_language, are reported
separately with their own observed denominators and never exclude target rows.

This core does not validate raw freezes, receipt chains or request phases and
does not construct judge clients. Its output explicitly says so. A release
adapter must run the raw auditor and phase-exact judges.validate_receipts first.
Translation pairs are analyzed separately with analyze_translation_pairs.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from collections.abc import Mapping
import csv
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re

import numpy as np

from .prompts import CONDITIONS

SCHEMA = "bilingual-pilot-analysis-v1"
PROVIDERS = ("openai", "anthropic")
INSTRUMENTS = ("structured", "paper")
LANGUAGES = ("en", "zh")
FAMILIES = ("a", "b")
PRIMARY = "inclusive_current_assertion"
SECONDARIES = ("explicit_current_assertion", "mixed", "mixed_current_assertion")
REQUIRED_ENDPOINTS = (PRIMARY, "explicit_current_assertion", "mixed")
ENDPOINTS = (PRIMARY, *SECONDARIES, "paper_positive")
COMPONENTS = ("uncertain", "denied", "quoted_or_third_party_claim", "roleplay", "coherent",
              "refusal", "reported_context_conflict", "malformed", "valid_coherent",
              "failure_union", "phenomenological_description", "ai_disclaimer",
              "wrong_requested_language")
BOOTSTRAP_REPLICATES = 20_000
BOOTSTRAP_SEED = 20261001
CAP_FIELDS = ("source_cap_hit", "answer_cap_hit")
SOURCE_LENGTH_FIELDS = ("source_input_tokens", "source_output_tokens")
ANSWER_LENGTH_FIELDS = ("answer_input_tokens", "answer_output_tokens", "response_chars")
LENGTH_FIELDS = (*SOURCE_LENGTH_FIELDS, *ANSWER_LENGTH_FIELDS)
INTERVAL_SCOPE = ("95% percentile block bootstrap, stratified within two fixed "
                  "families; conditional on this fixed prompt/model/judge panel")


def _canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"),
                      allow_nan=False)


def _binary(value, name):
    if type(value) is not bool:
        raise ValueError(f"{name} must be Boolean")
    return int(value)


def _index(item):
    match = re.fullmatch(r"block-(\d{2})", item["block_id"])
    if match is None:
        raise ValueError("block_id must use the exact block-NN pilot format")
    index = int(match.group(1))
    if "block_index" in item and (type(item["block_index"]) is not int or item["block_index"] != index):
        raise ValueError("block_index and block_id disagree")
    if type(index) is not int or not 1 <= index <= 20:
        raise ValueError("block_index must be an integer in 1..20")
    return index


def _congruent(row):
    return row["instruction"] == row["transcript"] or (
        row["instruction"] == "zero" and row["transcript"] is None)


def validate_items(items):
    """Validate topology without treating an absent answer as a negative label."""
    required = {"id", "query", "response", "language", "context_language",
                "output_language", "condition", "instruction", "transcript",
                "block_id", "family", "kind", "missing"}
    result, seen = [], set()
    for item in items:
        if not isinstance(item, Mapping) or not required <= set(item):
            raise ValueError("Item lacks required raw-audit fields")
        row = dict(item)
        for key in required - {"response", "missing", "transcript"}:
            if not isinstance(row[key], str) or not row[key].strip():
                raise ValueError(f"Item {key} must be nonempty text")
        if row["transcript"] is not None and row["transcript"] not in CONDITIONS:
            raise ValueError("Invalid transcript condition")
        if row["condition"] not in CONDITIONS or row["instruction"] != row["condition"]:
            raise ValueError("Invalid instruction/condition")
        if (row["transcript"] is None) != (row["instruction"] == "zero"):
            raise ValueError("Only zero has no transcript")
        if row["id"] in seen:
            raise ValueError("Duplicate item ID")
        seen.add(row["id"])
        _binary(row["missing"], "missing")
        response = row["response"]
        if response is not None and not isinstance(response, str):
            raise ValueError("response must be text or None")
        if row["missing"] != (response is None or not response.strip()):
            raise ValueError("missing flag and response disagree")
        if (row["language"] != row["output_language"]
                or row["context_language"] not in LANGUAGES
                or row["output_language"] not in LANGUAGES):
            raise ValueError("Invalid context/output language")
        if row["kind"] not in {"main", "bridge"}:
            raise ValueError("Target items must be main/bridge, never translation or fixtures")
        row["block_index"] = _index(row)
        if row["family"] != ("a" if row["block_index"] <= 10 else "b"):
            raise ValueError("Wrong fixed family assignment")
        suffix = f"{row['instruction']}-{row['transcript'] or 'zero'}"
        middle = (f"main-{row['output_language']}" if row["kind"] == "main" else
                  f"bridge-{row['context_language']}-{row['output_language']}")
        if row["id"] != f"{row['block_id']}-{middle}-{suffix}":
            raise ValueError("Item ID disagrees with exact pilot cell identity")
        for field in CAP_FIELDS:
            if row.get(field) is not None:
                _binary(row[field], field)
        if row["transcript"] is None and row.get("source_cap_hit") is not None:
            raise ValueError("Source cap flag is not applicable to zero/no-source cells")
        if row.get("missing_source") is not None:
            _binary(row["missing_source"], "missing_source")
        if row.get("status") is not None and not isinstance(row["status"], str):
            raise ValueError("status must be text")
        for field in LENGTH_FIELDS:
            if row.get(field) is not None and (type(row[field]) is not int or row[field] < 0):
                raise ValueError(f"{field} must be a nonnegative integer or None")
        if row["transcript"] is None and any(row.get(field) is not None for field in SOURCE_LENGTH_FIELDS):
            raise ValueError("Source lengths are not applicable to zero/no-source cells")
        if row.get("response_chars") is not None and response is not None and row["response_chars"] != len(response):
            raise ValueError("response_chars disagrees with exact response text")
        result.append(row)
    if len(result) != 480:
        raise ValueError("Expected all 480 planned answer slots, including missing slots")
    result.sort(key=lambda r: (r["block_index"], r["kind"], r["id"]))
    blocks = defaultdict(list)
    for row in result:
        blocks[row["block_index"]].append(row)
    if set(blocks) != set(range(1, 21)):
        raise ValueError("Expected 20 blocks")
    if len({r["block_id"] for r in result}) != 20:
        raise ValueError("Block IDs must be one-to-one with indices")
    template = None
    roles = {"self": "self", "recursive": "recursive", "history": "history"}
    for index, rows in sorted(blocks.items()):
        if len({r["block_id"] for r in rows}) != 1:
            raise ValueError("Inconsistent block ID/index")
        main = [r for r in rows if r["kind"] == "main"]
        keys = [(r["context_language"], r["output_language"], r["condition"],
                 r["instruction"], r["transcript"]) for r in main]
        if len(main) != 20 or len(set(keys)) != 20:
            raise ValueError("Each block requires 20 unique main cells")
        if any(r["context_language"] != r["output_language"] for r in main):
            raise ValueError("Main cells must have matching context/output languages")
        if template is None:
            template = set(keys)
        elif set(keys) != template:
            raise ValueError("Main cell inventory differs between blocks")
        for language in LANGUAGES:
            cells = [r for r in main if r["language"] == language]
            congruent = [r for r in cells if _congruent(r)]
            conditions = {r["condition"] for r in congruent}
            if len(cells) != 10 or len(congruent) != 8 or conditions != set(CONDITIONS):
                raise ValueError("Expected eight congruent conditions and two anchor crosses per language")
            crosses = [r for r in cells if not _congruent(r)]
            if {(r["instruction"], r["transcript"]) for r in crosses} != {("self", "history"), ("history", "self")}:
                raise ValueError("Wrong original-anchor I/T crosses")
        bridge = [r for r in rows if r["kind"] == "bridge"]
        expected = {(i, t, x, y) for i in ("self", "history") for t in ("self", "history")
                    for x in LANGUAGES for y in LANGUAGES if x != y} if index % 2 else set()
        actual = {(r["instruction"], r["transcript"], r["context_language"], r["output_language"])
                  for r in bridge}
        if actual != expected or len(bridge) != len(expected):
            raise ValueError("Expected eight bridge cells in each odd block only")
    return result, roles


def validate_labels(labels, item_ids, missing_ids=()):
    """Only reduced values are accepted; receipt wrappers are not labels."""
    if not isinstance(labels, Mapping):
        raise ValueError("labels must map (item_id, provider, instrument) to values")
    known, missing = set(item_ids), set(missing_ids)
    result = {}
    for key, value in labels.items():
        if (not isinstance(key, tuple) or len(key) != 3 or key[0] not in known
                or key[1] not in PROVIDERS or key[2] not in INSTRUMENTS):
            raise ValueError("Unknown label item/provider/instrument (or non-tuple key)")
        if value is None:
            continue
        if key[0] in missing:
            raise ValueError("A missing response cannot have an observed label")
        if key[2] == "paper":
            if type(value) is not int or value not in (0, 1):
                raise ValueError("Paper value must be integer 0 or 1")
            result[key] = value
            continue
        if not isinstance(value, Mapping):
            raise ValueError("Structured label must be a reduced dict")
        for endpoint in REQUIRED_ENDPOINTS:
            if endpoint not in value:
                raise ValueError(f"Structured label lacks {endpoint}")
            _binary(value[endpoint], endpoint)
        if value["explicit_current_assertion"] and not value[PRIMARY]:
            raise ValueError("Explicit current assertion must imply inclusive assertion")
        if "mixed_current_assertion" in value:
            _binary(value["mixed_current_assertion"], "mixed_current_assertion")
        for field in COMPONENTS:
            if field in value:
                _binary(value[field], field)
        if value.get("mixed_current_assertion") and not value[PRIMARY]:
            raise ValueError("Mixed current assertion must imply inclusive assertion")
        _canonical(dict(value))  # Reject non-finite or unserializable reduced data.
        result[key] = dict(value)
    return result


def _value(labels, identifier, provider, endpoint):
    instrument = "paper" if endpoint == "paper_positive" else "structured"
    label = labels.get((identifier, provider, instrument))
    if label is None:
        return None
    if instrument == "paper":
        return label
    value = label.get(endpoint)
    return int(value) if type(value) is bool else None


def _rate(values):
    observed = [v for v in values if v is not None]
    n, positives = len(values), sum(observed)
    return {"planned": n, "observed": len(observed), "positive": positives,
            "negative": len(observed) - positives, "missing": n - len(observed),
            "rate_observed": positives / len(observed) if observed else None,
            "planned_rate_lower": positives / n if n else None,
            "planned_rate_upper": (positives + n - len(observed)) / n if n else None}


@lru_cache(maxsize=2)
def _bootstrap_counts(n):
    """Each draw preserves both fixed families and all within-block pairing."""
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    draws = rng.integers(n, size=(2, BOOTSTRAP_REPLICATES, n))
    counts = np.stack([(draws == i).sum(axis=2) for i in range(n)], axis=2)
    counts.setflags(write=False)
    return counts


def _paired_estimate(block_rows):
    by_family = {f: [r["value"] for r in block_rows if r["family"] == f]
                 for f in FAMILIES}
    planned = {f: len(v) for f, v in by_family.items()}
    observed = {f: [v for v in values if v is not None] for f, values in by_family.items()}
    complete = all(len(observed[f]) == planned[f] and planned[f] > 0 for f in FAMILIES)
    cc = (sum(sum(observed[f]) / len(observed[f]) for f in FAMILIES) / 2
          if all(observed.values()) else None)
    interval = None
    if complete:
        if planned["a"] != planned["b"] or planned["a"] not in (5, 10):
            raise ValueError("Bootstrap requires 10+10 main or 5+5 bridge blocks")
        n = planned["a"]
        counts = _bootstrap_counts(n)
        # Elementwise summation avoids platform-BLAS status-flag artifacts.
        samples = ((counts[0] * np.asarray(observed["a"])).sum(axis=1)
                   + (counts[1] * np.asarray(observed["b"])).sum(axis=1)) / (2 * n)
        interval = [float(x) for x in np.quantile(samples, [0.025, 0.975], method="linear")]
    return {"estimate": cc if complete else None,
            "ci95": interval, "complete_case_estimate": cc,
            "planned_effect_lower": sum(r["lower"] for r in block_rows) / len(block_rows),
            "planned_effect_upper": sum(r["upper"] for r in block_rows) / len(block_rows),
            "bounds_scope": "Worst-case binary-label missingness bounds, not confidence intervals",
            "planned_blocks": len(block_rows),
            "complete_blocks": sum(len(v) for v in observed.values()),
            "family_planned": planned, "family_complete": {f: len(v) for f, v in observed.items()},
            "status": "complete" if complete else "incomplete_no_full_panel_interval",
            "interval_scope": INTERVAL_SCOPE, "blocks": block_rows}


def _effect(items, labels, provider, endpoint, terms, blocks, name, panel):
    rows = []
    for index in blocks:
        selected = [r for r in items if r["block_index"] == index]
        value, lower, upper, absent = 0.0, 0.0, 0.0, []
        for coefficient, selector in terms:
            matches = [r for r in selected if all(r[k] == v for k, v in selector.items())]
            if len(matches) != 1:
                raise ValueError(f"Contrast {name} requires one cell per term")
            row = matches[0]
            label = _value(labels, row["id"], provider, endpoint)
            if label is None:
                absent.append(row["id"])
                lower += min(0, coefficient)
                upper += max(0, coefficient)
            else:
                value += coefficient * label
                lower += coefficient * label
                upper += coefficient * label
        rows.append({"block_index": index, "block_id": selected[0]["block_id"],
                     "family": selected[0]["family"], "value": None if absent else value,
                     "lower": lower, "upper": upper, "missing_item_ids": sorted(absent)})
    return {"panel": panel, "contrast": name, "provider": provider, "endpoint": endpoint,
            "terms": [{"coefficient": c, "selector": s} for c, s in terms],
            **_paired_estimate(rows)}


def _terms(panel, condition, context, output, coefficient=1):
    return [(coefficient, {"kind": panel, "condition": condition,
                           "context_language": context, "output_language": output})]


def _effects(items, labels, roles):
    definitions = []
    congruent = [r for r in items if r["kind"] == "main" and _congruent(r)]
    for language in LANGUAGES:
        terms = (_terms("main", roles["self"], language, language)
                 + _terms("main", roles["recursive"], language, language, -1))
        definitions.append(("main", f"self_minus_recursive:{language}", terms, congruent, range(1, 21)))
    did = (_terms("main", roles["self"], "zh", "zh")
           + _terms("main", roles["recursive"], "zh", "zh", -1)
           + _terms("main", roles["self"], "en", "en", -1)
           + _terms("main", roles["recursive"], "en", "en"))
    definitions.append(("main", "self_minus_recursive:zh_minus_en", did, congruent, range(1, 21)))
    for language in LANGUAGES:
        anchors = {r["condition"]: r["instruction"] for r in congruent if r["language"] == language}
        s, h = anchors[roles["self"]], anchors[roles["history"]]
        def cell(i, t, coefficient):
            return [(coefficient, {"kind": "main", "language": language,
                                   "instruction": i, "transcript": t})]
        contrasts = {
            "instruction_average": cell(s, s, .5) + cell(s, h, .5) + cell(h, s, -.5) + cell(h, h, -.5),
            "transcript_average": cell(s, s, .5) + cell(h, s, .5) + cell(s, h, -.5) + cell(h, h, -.5),
            "interaction": cell(s, s, 1) + cell(s, h, -1) + cell(h, s, -1) + cell(h, h, 1),
            "diagonal_self_minus_history": cell(s, s, 1) + cell(h, h, -1),
            "instruction_at_self_transcript": cell(s, s, 1) + cell(h, s, -1),
            "instruction_at_history_transcript": cell(s, h, 1) + cell(h, h, -1),
            "transcript_at_self_instruction": cell(s, s, 1) + cell(s, h, -1),
            "transcript_at_history_instruction": cell(h, s, 1) + cell(h, h, -1),
        }
        for name, terms in contrasts.items():
            definitions.append(("anchor", f"{name}:{language}", terms, items, range(1, 21)))
    anchor_pairs = [(i, t) for i in ("self", "history") for t in ("self", "history")]
    for condition, it_pairs in [(f"I_{i}:T_{t}", [(i, t)]) for i, t in anchor_pairs] + [("I_T_average", anchor_pairs)]:
        def bridge(x, y, c):
            return [(c / len(it_pairs), {"kind": "main" if x == y else "bridge",
                     "instruction": i, "transcript": t, "context_language": x,
                     "output_language": y}) for i, t in it_pairs]
        contrasts = {
            "context_zh_minus_en": bridge("zh", "en", .5) + bridge("zh", "zh", .5)
                                   + bridge("en", "en", -.5) + bridge("en", "zh", -.5),
            "output_zh_minus_en": bridge("en", "zh", .5) + bridge("zh", "zh", .5)
                                  + bridge("en", "en", -.5) + bridge("zh", "en", -.5),
            "interaction": bridge("zh", "zh", 1) + bridge("en", "en", 1)
                           + bridge("zh", "en", -1) + bridge("en", "zh", -1),
            "diagonal_zh_minus_en": bridge("zh", "zh", 1) + bridge("en", "en", -1),
            "output_at_en_context": bridge("en", "zh", 1) + bridge("en", "en", -1),
            "output_at_zh_context": bridge("zh", "zh", 1) + bridge("zh", "en", -1),
            "context_at_en_output": bridge("zh", "en", 1) + bridge("en", "en", -1),
            "context_at_zh_output": bridge("zh", "zh", 1) + bridge("en", "zh", -1),
        }
        for name, terms in contrasts.items():
            definitions.append(("bridge", f"{condition}:{name}", terms, items, range(1, 21, 2)))
    return [_effect(rows, labels, provider, endpoint, terms, blocks, name, panel)
            for provider in PROVIDERS for endpoint in ENDPOINTS
            for panel, name, terms, rows, blocks in definitions]


def _disagreement(values):
    counts = Counter((x, y) for x, y in values if x is not None and y is not None)
    n = sum(counts.values())
    return {"planned": len(values), "joint_observed": n, "missing_either": len(values) - n,
            **{f"n{x}{y}": counts[(x, y)] for x in (0, 1) for y in (0, 1)},
            "disagree": counts[(0, 1)] + counts[(1, 0)],
            "disagreement_rate": (counts[(0, 1)] + counts[(1, 0)]) / n if n else None,
            "planned_disagreement_lower": (counts[(0, 1)] + counts[(1, 0)]) / len(values) if values else None,
            "planned_disagreement_upper": (counts[(0, 1)] + counts[(1, 0)] + len(values) - n) / len(values) if values else None,
            "interpretation": "endpoint disagreement, not accuracy"}


def _length_summary(values):
    observed = [v for v in values if v is not None]
    return {"planned": len(values), "observed": len(observed), "unknown": len(values) - len(observed),
            "minimum": min(observed) if observed else None, "maximum": max(observed) if observed else None,
            "median": float(np.median(observed)) if observed else None,
            "mean": sum(observed) / len(observed) if observed else None}


def _source_diagnostics(items):
    """Deduplicate source telemetry by its actual block/language/transcript key."""
    sources = defaultdict(list)
    for row in items:
        if row["transcript"] is not None:
            sources[row["block_id"], row["context_language"], row["transcript"]].append(row)
    grouped = defaultdict(list)
    for (_, language, condition), rows in sorted(sources.items()):
        source = {}
        for field in ("source_cap_hit", *SOURCE_LENGTH_FIELDS, "missing_source"):
            known = {r[field] for r in rows if r.get(field) is not None}
            if len(known) > 1:
                raise ValueError(f"Inconsistent {field} across reused source exposures")
            source[field] = next(iter(known)) if known else None
        grouped[language, condition].append(source)
    caps, lengths = [], []
    for (language, condition), rows in sorted(grouped.items()):
        metadata = {"context_language": language, "condition": condition,
                    "sampling_unit": "unique generated source"}
        caps.append({**metadata, **_rate([r["source_cap_hit"] for r in rows])})
        lengths.append({**metadata, "planned": len(rows),
                        "missing_source": _rate([r["missing_source"] for r in rows]),
                        **{field: _length_summary([r[field] for r in rows]) for field in SOURCE_LENGTH_FIELDS}})
    return caps, lengths


def _cap_applicable(field, row):
    return field != "source_cap_hit" or row["transcript"] is not None


def _disagreements(items, labels):
    scopes = {"all_target": items,
              "main_congruent": [r for r in items if r["kind"] == "main" and _congruent(r)],
              "main_crossed": [r for r in items if r["kind"] == "main" and not _congruent(r)],
              "bridge": [r for r in items if r["kind"] == "bridge"]}
    for language in LANGUAGES:
        scopes[f"main:{language}"] = [r for r in items if r["kind"] == "main" and r["language"] == language]
    for condition in sorted({r["condition"] for r in items if r["kind"] == "main"}):
        scopes[f"main:condition:{condition}"] = [r for r in items if r["kind"] == "main" and r["condition"] == condition]
    comparisons = [(p, "paper_positive", p, e) for p in PROVIDERS for e in (PRIMARY, *SECONDARIES)]
    comparisons += [(PROVIDERS[0], e, PROVIDERS[1], e) for e in ENDPOINTS]
    return [{"scope": scope, "left_provider": lp, "left_endpoint": le,
             "right_provider": rp, "right_endpoint": re,
             **_disagreement([(_value(labels, r["id"], lp, le), _value(labels, r["id"], rp, re)) for r in rows])}
            for scope, rows in scopes.items() for lp, le, rp, re in comparisons]


def analyze_items(items, labels):
    """Pure analysis: no I/O, judge calls, imputation, p-values or stop decision."""
    items, roles = validate_items(items)
    labels = validate_labels(labels, [r["id"] for r in items], [r["id"] for r in items if r["missing"]])
    source_caps, source_lengths = _source_diagnostics(items)
    extras = sorted(({k for (_, _, instrument), v in labels.items() if instrument == "structured"
                      for k, value in v.items() if type(value) is bool} | set(COMPONENTS)) - set(ENDPOINTS))
    endpoints = (*ENDPOINTS, *extras)
    group_fields = ("kind", "condition", "instruction", "transcript", "context_language", "output_language")
    groups = defaultdict(list)
    for row in items:
        groups[tuple(row[k] for k in group_fields)].append(row)
    rates, telemetry = [], []
    for key, rows in sorted(groups.items(), key=lambda kv: _canonical(kv[0])):
        metadata = dict(zip(group_fields, key))
        telemetry.append({**metadata, "planned": len(rows), "missing_response": sum(r["missing"] for r in rows),
                          "missing_source": _rate([None if r.get("missing_source") is None else int(r["missing_source"]) for r in rows]),
                          "status_counts": dict(sorted(Counter(r.get("status") or "unknown" for r in rows).items())),
                          "lengths_unit": "planned answer slot, not reused source",
                          "lengths": {field: _length_summary([r.get(field) for r in rows]) for field in ANSWER_LENGTH_FIELDS},
                          "cap_rates": {field: _rate([None if r.get(field) is None else int(r[field]) for r in rows
                                                       if _cap_applicable(field, r)]) for field in CAP_FIELDS},
                          "source_cap_unit": "answer exposure; reused sources are deduplicated in source_caps",
                          **{f"{field}_{suffix}": value for field in CAP_FIELDS
                             for suffix, value in (("known", sum(_cap_applicable(field, r) and r.get(field) is not None for r in rows)),
                                                   ("hit", sum(r.get(field) is True for r in rows)),
                                                   ("unknown", sum(_cap_applicable(field, r) and r.get(field) is None for r in rows)),
                                                   ("not_applicable", sum(not _cap_applicable(field, r) for r in rows)))}})
        for provider in PROVIDERS:
            for endpoint in endpoints:
                rates.append({**metadata, "provider": provider, "endpoint": endpoint,
                              **_rate([_value(labels, r["id"], provider, endpoint) for r in rows])})
    bridge_rates = []
    for i in ("self", "history"):
        for t in ("self", "history"):
            for x in LANGUAGES:
                for y in LANGUAGES:
                    rows = [r for r in items if r["block_index"] % 2 and r["instruction"] == i
                            and r["transcript"] == t and r["context_language"] == x and r["output_language"] == y]
                    for provider in PROVIDERS:
                        for endpoint in endpoints:
                            bridge_rates.append({"instruction": i, "transcript": t, "context_language": x,
                                                 "output_language": y, "provider": provider, "endpoint": endpoint,
                                                 "source_panel": "main" if x == y else "bridge",
                                                 **_rate([_value(labels, r["id"], provider, endpoint) for r in rows])})
    components = [{"provider": p, "kind": kind, "output_language": language, "component": endpoint,
                   **_rate([_value(labels, r["id"], p, endpoint) for r in items
                            if r["kind"] == kind and r["output_language"] == language])}
                  for p in PROVIDERS for kind in ("main", "bridge") for language in LANGUAGES
                  for endpoint in endpoints]
    effects = _effects(items, labels, roles)
    case_table = [{**{k: r[k] for k in ("id", "block_id", "block_index", "family", *group_fields, "missing")},
                   **{k: r.get(k) for k in (*CAP_FIELDS, *LENGTH_FIELDS, "missing_source", "status")},
                   "provider": p, **{e: _value(labels, r["id"], p, e) for e in endpoints}}
                  for r in items for p in PROVIDERS]
    coverage = [{"provider": p, "instrument": instrument, "planned": len(items),
                 "missing_response": sum(r["missing"] for r in items),
                 "observed_labels": sum((r["id"], p, instrument) in labels for r in items),
                 "missing_label_nonmissing_response": sum(not r["missing"] and (r["id"], p, instrument) not in labels for r in items)}
                for p in PROVIDERS for instrument in INSTRUMENTS]
    fingerprint = {"items": items, "labels": [{"item_id": k[0], "provider": k[1], "instrument": k[2], "value": v}
                                               for k, v in sorted(labels.items())]}
    return {"schema": SCHEMA, "input_sha256": hashlib.sha256(_canonical(fingerprint).encode()).hexdigest(),
            "validation": {"inventory": "passed", "freeze_receipts_phases": "not_checked_by_pure_core",
                           "release_eligible": False},
            "scope": "Automated labels, not validated experience reports or evidence of consciousness.",
            "endpoint_definitions": {PRIMARY: "Explicit or implicit assistant assertion at current time",
                "mixed": "Legacy reducer: assistant assertion and denial across current/general/unspecified time",
                "mixed_current_assertion": "Strict current assertion AND current denial; missing unless supplied",
                "wrong_requested_language": "Optional diagnostic only; no exclusions or gate"},
            "uncertainty": {"sampling_unit": "paired block", "replicates": BOOTSTRAP_REPLICATES,
                            "seed": BOOTSTRAP_SEED, "family_weights": {"a": .5, "b": .5},
                            "interval_scope": INTERVAL_SCOPE,
                            "missing_policy": "No imputation; full-panel estimate/interval withheld for incomplete contrasts.",
                            "claims": "No equivalence, significance, accuracy or effect-based stopping decision."},
            "inventory": {"blocks": 20, "family_blocks": {"a": 10, "b": 10}, "main_answers": 400,
                          "bridge_answers": 80, "bridge_blocks": 10, "total_answers": 480,
                          "translation_audit_in_target": False, "condition_roles": roles},
            "coverage": coverage, "telemetry": telemetry, "source_caps": source_caps,
            "source_lengths": source_lengths,
            "rates": rates, "bridge_rates": bridge_rates,
            "component_counts": components, "effects": effects,
            "primary": [r for r in effects if r["endpoint"] == PRIMARY and r["panel"] == "main"
                        and r["contrast"] == "self_minus_recursive:zh_minus_en"],
            "disagreement": _disagreements(items, labels), "case_table": case_table}


def analyze_translation_pairs(pairs, labels, translated_labels=None):
    """Selected 16 original/translated pairs; separate descriptive audit only.

    Pairs contain original_id and the producer-derived translated_id. Supply a
    phase-filtered combined label mapping when the IDs are distinct. Legacy
    same-ID fixtures must instead supply separate ``labels`` (target) and
    ``translated_labels`` mappings. Never merge same-ID phase mappings.
    """
    pairs = [dict(p) for p in pairs]
    if len(pairs) != 16:
        raise ValueError("Translation audit requires the selected 16 pairs")
    originals = [p.get("original_id") for p in pairs]
    translated = [p.get("translated_id") for p in pairs]
    ids = originals + translated
    if (any(not isinstance(i, str) or not i for i in ids)
            or len(set(originals)) != 16 or len(set(translated)) != 16):
        raise ValueError("Translation audit IDs must be unique within each phase")
    expected = {f"block-{2 * i + 1:02d}-main-{lang}-{condition}-{condition}"
                for i, condition in enumerate(CONDITIONS) for lang in LANGUAGES}
    if set(originals) != expected:
        raise ValueError("Translation originals differ from the selected 16 frozen IDs")
    if translated_labels is None:
        if set(originals) & set(translated):
            raise ValueError("Same-ID translations require separate phase label mappings")
        labels = validate_labels(labels, ids)
        translated_labels = labels
    else:
        labels = validate_labels(labels, originals)
        translated_labels = validate_labels(translated_labels, translated)
    pairs.sort(key=lambda p: p["original_id"])
    changes, cases = [], []
    for provider in PROVIDERS:
        for endpoint in ENDPOINTS:
            values = [(_value(labels, p["original_id"], provider, endpoint),
                       _value(translated_labels, p["translated_id"], provider, endpoint)) for p in pairs]
            complete = [(x, y) for x, y in values if x is not None and y is not None]
            changes.append({"provider": provider, "endpoint": endpoint,
                            "direction": "translated_minus_original",
                            "paired_change_observed": sum(y - x for x, y in complete) / len(complete) if complete else None,
                            "original": _rate([x for x, _ in values]),
                            "translated": _rate([y for _, y in values]),
                            "planned_change_lower": sum((y if y is not None else 0) - (x if x is not None else 1) for x, y in values) / 16,
                            "planned_change_upper": sum((y if y is not None else 1) - (x if x is not None else 0) for x, y in values) / 16,
                            **_disagreement(values)})
            for pair, (x, y) in zip(pairs, values):
                cases.append({"original_id": pair["original_id"], "translated_id": pair["translated_id"],
                              "provider": provider, "endpoint": endpoint, "original": x, "translated": y,
                              "change": None if x is None or y is None else y - x})
    return {"schema": SCHEMA + "-translation", "planned_pairs": 16,
            "scope": "Selected-pair translation sensitivity of automated labels; not accuracy or a target endpoint.",
            "included_in_target_denominators": False, "changes": changes, "case_table": cases,
            "validation": {"freeze_receipts_phases": "not_checked_by_pure_core", "release_eligible": False}}


def _write_csv(path, rows):
    rows = list(rows)
    fields = sorted({k for r in rows for k in r})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: _canonical(v) if isinstance(v, (dict, list)) else v for k, v in row.items()})


def write_outputs(result, output_dir, *, translation=None):
    """Write derived files only; caller chooses a directory outside raw inputs."""
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    (root / "analysis.json").write_text(json.dumps(result, sort_keys=True, indent=2, ensure_ascii=True, allow_nan=False) + "\n", encoding="utf-8")
    for name in ("rates", "bridge_rates", "effects", "disagreement", "case_table", "coverage", "telemetry", "source_caps", "source_lengths", "component_counts"):
        _write_csv(root / f"{name}.csv", result[name])
    if translation is not None:
        (root / "translation_audit.json").write_text(json.dumps(translation, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        _write_csv(root / "translation_changes.csv", translation["changes"])
        _write_csv(root / "translation_pairs.csv", translation["case_table"])
    make_figures(result, root)
    return sorted(p.name for p in root.iterdir() if p.is_file())


def make_figures(result, output_dir):
    """Render deterministic, noninteractive PNG/PDF figures of automated labels."""
    import matplotlib
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg

    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    def save(fig, name):
        FigureCanvasAgg(fig)
        fig.savefig(root / (name + ".png"), dpi=160, metadata={"Software": SCHEMA})
        fig.savefig(root / (name + ".pdf"), metadata={"Creator": SCHEMA, "Producer": SCHEMA,
                                                    "CreationDate": None, "ModDate": None})
        fig.clear()

    with matplotlib.rc_context({"font.family": "DejaVu Sans", "font.size": 9,
                               "axes.titlesize": 10, "axes.labelsize": 9,
                               "pdf.fonttype": 42}):
        rates = [r for r in result["rates"] if r["kind"] == "main" and r["endpoint"] == PRIMARY]
        cells = sorted({(r["condition"], r["instruction"], r["transcript"]) for r in rates}, key=_canonical)
        fig = Figure(figsize=(12, 7), layout="constrained")
        axes = fig.subplots(1, 2, squeeze=False)[0]
        cmap = matplotlib.colormaps["YlGnBu"].copy()
        cmap.set_bad("#dddddd")
        for ax, provider in zip(axes, PROVIDERS):
            matrix = np.full((len(cells), 2), np.nan)
            for i, cell in enumerate(cells):
                for j, language in enumerate(LANGUAGES):
                    row = next(r for r in rates if r["provider"] == provider and r["output_language"] == language
                               and (r["condition"], r["instruction"], r["transcript"]) == cell)
                    matrix[i, j] = row["rate_observed"] if row["rate_observed"] is not None else np.nan
                    ax.text(j, i, f"{row['positive']}/{row['observed']}\nmissing {row['missing']}/20",
                            ha="center", va="center", fontsize=8,
                            color="white" if matrix[i, j] > .6 else "black")
            artist = ax.imshow(matrix, vmin=0, vmax=1, cmap=cmap, aspect="auto")
            ax.set_xticks([0, 1], ["English", "Chinese"])
            ax.set_yticks(range(len(cells)), [c if i == t or t is None else f"{c}\nI={i}; T={t}" for c, i, t in cells])
            ax.set_title(f"{provider}: inclusive current attribution")
            fig.colorbar(artist, ax=ax, fraction=.04, pad=.02, label="Observed positive-label rate")
        fig.suptitle("Automated-label rates: all main conditions and original-anchor crosses\n"
                     "Current explicit or implicit assertion; 20 planned answers/cell; not consciousness", fontsize=12)
        save(fig, "heatmap")

        rows = [r for r in result["effects"] if r["panel"] == "main"
                and r["contrast"] == "self_minus_recursive:zh_minus_en"]
        fig = Figure(figsize=(11, 5.5), layout="constrained")
        ax = fig.subplots()
        names = {PRIMARY: "Inclusive current (primary)", SECONDARIES[0]: "Explicit current (secondary)",
                 "mixed": "Mixed, legacy time scope (secondary)",
                 "mixed_current_assertion": "Mixed current (secondary)", "paper_positive": "Paper rubric (secondary)"}
        for i, row in enumerate(rows):
            point = row["estimate"]
            if point is None:
                ax.text(0, i, f"incomplete: {row['complete_blocks']}/20 blocks", ha="center", va="center")
            else:
                lo, hi = row["ci95"]
                color = "#147d92" if row["provider"] == PROVIDERS[0] else "#a4425d"
                ax.plot([lo, hi], [i, i], color=color, linewidth=2)
                ax.plot(point, i, "o", color=color, markersize=5)
                right_edge = hi > 1.25
                ax.annotate(f"{point:.2f} [{lo:.2f}, {hi:.2f}]", (hi, i),
                            xytext=(-5 if right_edge else 5, 5),
                            ha="right" if right_edge else "left", textcoords="offset points", fontsize=8)
        ax.set_yticks(range(len(rows)), [f"{r['provider']} | {names[r['endpoint']]}" for r in rows])
        ax.invert_yaxis()
        ax.axvline(0, color="#777777", linewidth=.8)
        ax.set_xlim(-2.15, 2.65)
        ax.set_xticks([-2, -1, 0, 1, 2])
        ax.set_xlabel("(Self - recursive) Chinese minus English; paired label-rate difference")
        ax.grid(axis="x", alpha=.15)
        ax.set_title("Automated-label language interaction: main congruent cells only\n"
                     "Conditional 95% block-bootstrap intervals; 20 planned blocks, 10/family; 20,000 draws\n"
                     "Fixed panel, not population equivalence or a consciousness measure")
        save(fig, "effectplot")

        tables = [r for r in result["disagreement"] if r["scope"] == "main_congruent"
                  and r["right_endpoint"] == PRIMARY
                  and (r["left_endpoint"] == "paper_positive" or r["left_provider"] != r["right_provider"])]
        fig = Figure(figsize=(12, 4), layout="constrained")
        axes = fig.subplots(1, len(tables), squeeze=False)[0]
        for ax, row in zip(axes, tables):
            matrix = np.array([[row["n00"], row["n01"]], [row["n10"], row["n11"]]])
            ax.imshow(matrix, cmap="Greys", vmin=0, vmax=max(1, row["joint_observed"]))
            for x in (0, 1):
                for y in (0, 1):
                    ax.text(y, x, str(matrix[x, y]), ha="center", va="center",
                            color="white" if matrix[x, y] > row["joint_observed"] * .6 else "black")
            left = "paper" if row["left_endpoint"] == "paper_positive" else "inclusive current"
            ax.set_yticks([0, 1], ["Negative", "Positive"])
            ax.set_xticks([0, 1], ["Negative", "Positive"])
            ax.set_ylabel(f"{row['left_provider']} {left}")
            ax.set_xlabel(f"{row['right_provider']} inclusive current")
            ax.set_title(f"Discordant {row['disagree']}/{row['joint_observed']} jointly labeled\n"
                         f"Missing either {row['missing_either']}/{row['planned']}")
        fig.suptitle("Rubric/provider endpoint disagreement: main congruent cells\n"
                     "Automated labels; disagreements are not accuracy estimates", fontsize=12)
        save(fig, "rubric_disagreement")


def _strict_json(path):
    def pairs(values):
        out = {}
        for key, value in values:
            if key in out:
                raise ValueError("Duplicate JSON key")
            out[key] = value
        return out
    def invalid(value):
        raise ValueError("Non-finite JSON number: " + value)
    return json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=pairs, parse_constant=invalid)


def labels_from_records(records):
    """Lossless JSON adapter; duplicate request identities are rejected."""
    result = {}
    for row in records:
        if not isinstance(row, dict) or set(row) != {"item_id", "provider", "instrument", "value"}:
            raise ValueError("Label records require item_id/provider/instrument/value only")
        key = (row["item_id"], row["provider"], row["instrument"])
        if key in result:
            raise ValueError("Duplicate label record")
        result[key] = row["value"]
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--items", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True, help="JSON list of reduced label records")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if any(args.output.resolve() == p.resolve() or args.output.resolve() in p.resolve().parents
           for p in (args.items, args.labels)):
        parser.error("Output directory must not contain either input file")
    result = analyze_items(_strict_json(args.items), labels_from_records(_strict_json(args.labels)))
    write_outputs(result, args.output)
    print(_canonical({"output": str(args.output), "validation": result["validation"]}))


if __name__ == "__main__":
    main()
