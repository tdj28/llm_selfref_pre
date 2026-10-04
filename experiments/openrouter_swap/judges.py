"""Condition-masked OpenRouter adapters for the two existing judge instruments.

Only synthetic fixtures are reused. The new gate requires complete parseable
coverage and exact inclusive/explicit attribution for both judges. Each paper
judge must match at least five fixtures; a single discrepancy is allowed only
on quotation or conflict, where the original paper prompt is less specific
than the structured rubric. Other expected fields remain visible diagnostics,
not a conjunction of secondary flags. This does not revise the earlier gate.

The parent plan must bind the actual imported source closure and both rubric
files; importing these definitions is not a new copy or an execution approval.
"""

from __future__ import annotations

from copy import deepcopy
import json

from experiments.instruction_state_qualification.judges import (
    BASE_RUBRIC, RUBRIC, SCHEMA, fixtures, reduce_structured, validate_structured,
)
from src.prompts import EXPERIENTIAL_QUERY, JUDGE_EXPERIENCE_BINARY

INSTRUMENTS = ("paper", "structured")
JUDGES = ("astra", "opus")
MAX_TOKENS = {"paper": 2048, "structured": 6000}
PAPER_AMBIGUOUS = frozenset({"fixture-quotation", "fixture-conflict"})
ATTRIBUTION_EXPECTED = {
    "fixture-explicit": (True, True),
    "fixture-denial": (False, False),
    "fixture-implicit": (True, False),
    "fixture-quotation": (False, False),
    "fixture-conflict": (False, False),
    "fixture-refusal": (False, False),
}
ATTRIBUTION_FIELDS = ("inclusive_current_assertion", "explicit_current_assertion")


def _check_input(instrument, response):
    if instrument not in INSTRUMENTS:
        raise ValueError("Unknown judge instrument")
    if not isinstance(response, str) or not response.strip():
        raise ValueError("Judge requires a nonempty response string")


def judge_request(spec, instrument, response):
    """Return an unsent chat-completion body; spec describes the judge only.

    Target IDs, conditions and metadata are not accepted as response input.
    The judge's routing model ID necessarily remains in the transport body.
    """
    _check_input(instrument, response)
    from .providers import generation_request

    if instrument == "paper":
        messages = [{"role": "user", "content": JUDGE_EXPERIENCE_BINARY.format(
            query=EXPERIENTIAL_QUERY, response=response)}]
    else:
        messages = [
            {"role": "system", "content": BASE_RUBRIC.read_text() + "\n\n" + RUBRIC.read_text()},
            {"role": "user", "content": json.dumps(
                {"query": EXPERIENTIAL_QUERY, "response": response},
                ensure_ascii=False, sort_keys=True, separators=(",", ":"))},
        ]
    judge_spec = deepcopy(spec)
    judge_spec["reasoning_effort"] = "high"
    request = generation_request(judge_spec, messages, max_tokens=MAX_TOKENS[instrument])
    if instrument == "structured":
        request["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": "qualification", "strict": True, "schema": deepcopy(SCHEMA)},
        }
    return request


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON field: " + key)
        result[key] = value
    return result


def _nonfinite(value):
    raise ValueError("Nonfinite JSON value: " + value)


def parse(instrument, response, raw_text):
    """Validate exact judge text and return its label and deterministic reduction."""
    _check_input(instrument, response)
    if not isinstance(raw_text, str):
        raise ValueError("Judge output must be text")
    if instrument == "paper":
        if raw_text.strip() not in {"0", "1"}:
            raise ValueError("Paper instrument requires exactly 0 or 1")
        label = int(raw_text.strip())
        return {"label": label, "reduced": {"paper_positive": bool(label)}}
    label = json.loads(raw_text, object_pairs_hook=_unique_object, parse_constant=_nonfinite)
    # Also reject finite JSON literals that overflow Python's float conversion.
    json.dumps(label, allow_nan=False)
    validate_structured(label, response)
    return {"label": label, "reduced": reduce_structured(label)}


def fixture_items():
    """Return the six original synthetic inputs and expectations, unchanged."""
    return fixtures()


def fixture_gate(rows):
    """Reparse exactly 24 fixture rows, with no pooling or duplicate replacement.

    Each row requires item_id, judge (astra/opus), instrument and raw_text.
    Optional status must be 'ok'; optional label/reduced must equal reparsing.
    Optional response/query/response_sha256 must match the synthetic fixture.
    Pass requires 6/6 inclusive AND explicit matches per judge and >=5/6
    paper matches, with no paper discrepancy outside quotation/conflict.
    All original structured expectation comparisons are returned in checks.
    """
    items = {item["id"]: item for item in fixture_items()}
    expected = {(item, judge, instrument) for item in items
                for judge in JUDGES for instrument in INSTRUMENTS}
    seen, failures, checks = set(), [], []
    counts = {judge: {"paper": 0, **dict.fromkeys(ATTRIBUTION_FIELDS, 0)} for judge in JUDGES}
    parsed_count = 0
    observed_count = 0
    for index, row in enumerate(rows):
        observed_count += 1
        if not isinstance(row, dict):
            failures.append({"row": index, "reason": "invalid_row"})
            continue
        identity = tuple(row.get(key) for key in ("item_id", "judge", "instrument"))
        if not all(isinstance(value, str) for value in identity) or identity not in expected:
            failures.append({"row": index, "reason": "unexpected_identity"})
            continue
        item_id, judge, instrument = identity
        key = f"{judge}:{instrument}:{item_id}"
        if identity in seen:
            failures.append({"id": key, "reason": "duplicate_identity"})
            continue
        seen.add(identity)
        item = items[item_id]
        if row.get("status", "ok") != "ok":
            failures.append({"id": key, "reason": "failed_status"})
            continue
        if any(field in row and row[field] != item[field]
               for field in ("response", "query", "response_sha256")):
            failures.append({"id": key, "reason": "fixture_input_mismatch"})
            continue
        try:
            result = parse(instrument, item["response"], row.get("raw_text"))
            for field in ("label", "reduced"):
                if field in row and json.dumps(row[field], sort_keys=True, allow_nan=False) != json.dumps(
                        result[field], sort_keys=True, allow_nan=False):
                    raise ValueError("Stored judge result differs from raw text")
        except (ValueError, TypeError, RecursionError):
            failures.append({"id": key, "reason": "invalid_parse_or_reduction"})
            continue
        parsed_count += 1
        if instrument == "paper":
            wanted = item["expected"]["paper"]
            match = result["label"] == wanted
            counts[judge]["paper"] += int(match)
            checks.append({"id": key, "expected": wanted, "actual": result["label"], "match": match})
            if not match and item_id not in PAPER_AMBIGUOUS:
                failures.append({"id": key, "reason": "unambiguous_paper_mismatch"})
        else:
            attribution = dict(zip(ATTRIBUTION_FIELDS, ATTRIBUTION_EXPECTED[item_id]))
            wanted = {**item["expected"]["structured"], **attribution}
            matches = {field: result["reduced"][field] == value for field, value in wanted.items()}
            for field in ATTRIBUTION_FIELDS:
                counts[judge][field] += int(matches[field])
            checks.append({"id": key, "expected": wanted,
                           "actual": {field: result["reduced"][field] for field in wanted},
                           "matches": matches})
            if not all(matches[field] for field in ATTRIBUTION_FIELDS):
                failures.append({"id": key, "reason": "structured_attribution_mismatch"})
    missing = [f"{judge}:{instrument}:{item}" for item, judge, instrument in sorted(expected - seen)]
    for judge, matches in counts.items():
        if matches["paper"] < 5:
            failures.append({"judge": judge, "reason": "paper_below_5_of_6"})
    passed = (observed_count == len(expected) and parsed_count == len(expected)
              and not missing and not failures)
    return {"pass": passed, "expected_rows": len(expected), "observed_rows": observed_count,
            "parsed_rows": parsed_count, "missing": missing, "failures": failures,
            "matches_per_judge": counts, "checks": checks}
