"""Independent, CPU-only reconstruction of repair rows and stage barriers.

Receipt hashes attest to artifact consistency, not to the truth of model output
or wall-clock creation times. Reconstruction invokes pure decision functions;
it never calls the collection runtime or imports a tensor library.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re

from experiments.steering_fidelity.audit import delivery_summary, read_receipts
from experiments.steering_fidelity.protocol import sha
from .pressure_gate import discovery_gate, validation_gate


POSITIVE_IDS = (11104, 27322)
HOOK_INDEX = 50
DICTIONARY_WIDTH = 65536
REQUESTED_NORM = .30 * 18.246721267700195
_RUNTIME = {"missing", "plan_sha256", "freeze_commit", "elapsed_seconds", "intervention"}
_CHOICE = {"p_yes", "p_no", "valid_mass", "p_correct", "correct", "predicted_answer",
           "format_valid", "top_token_id", "top_token", "token_sets", "input_token_ids",
           "input_token_ids_sha256", "rendered_input_sha256", "delivery", "delivery_raw",
           "telemetry", "screen"}
_GENERATION = {"response", "input_tokens", "output_tokens", "cap_hit", "input_token_ids",
               "output_token_ids", "rendered_input_sha256", "input_token_ids_sha256",
               "telemetry", "elapsed_seconds"}
_POSITION = {"position", "token_id", "origin", "special", "terminal_observation_only"}
_DELIVERY = {"requested_norm", "realized_norm", "cosine", "relative_error", "norm_ratio",
             "hidden_norm"}


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _same(actual, expected):
    """Type-exact JSON equality, including nested numeric/boolean bindings."""
    if isinstance(expected, dict):
        return (type(actual) is dict and actual.keys() == expected.keys()
                and all(_same(actual[k], v) for k, v in expected.items()))
    if isinstance(expected, list):
        return (type(actual) is list and len(actual) == len(expected)
                and all(_same(a, b) for a, b in zip(actual, expected)))
    return type(actual) is type(expected) and actual == expected


def _finite(value):
    if isinstance(value, dict):
        _require(all(type(k) is str for k in value), "Non-string JSON field")
        for v in value.values():
            _finite(v)
    elif isinstance(value, list):
        for v in value:
            _finite(v)
    elif type(value) is float:
        _require(math.isfinite(value), "Nonfinite raw value")
    else:
        _require(value is None or type(value) in (bool, int, str), "Non-JSON raw value")


def _number(value, name, *, positive=False):
    _require(type(value) in (int, float) and math.isfinite(value)
             and (value > 0 if positive else value >= 0), "Invalid " + name)


def _digest(value, name="SHA256"):
    _require(type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value), "Invalid " + name)


def _token_hash(tokens):
    return hashlib.sha256(json.dumps(tokens).encode()).hexdigest()


def _tokens(value):
    _require(type(value) is list and value and all(type(t) is int and 0 <= t < 128256
                                                 for t in value), "Invalid token IDs")


def _keys(value, expected, name):
    _require(type(value) is dict and set(value) == set(expected), "Malformed " + name)


def _intervention(spec):
    if spec.get("task") == "teacher":
        _require(spec.get("arm") in (None, "zero") and spec.get("feature_id") is None,
                 "Teacher exposure must be clean")
        return None
    if spec.get("arm") == "zero":
        _require(spec.get("feature_id") is None, "Zero arm carries a feature")
        return None
    feature = spec.get("feature_id")
    _require(type(feature) is int and feature in POSITIVE_IDS
             and spec.get("arm") == f"positive-{feature}"
             and spec.get("task") in ("choice", "generation"), "Unknown positive arm")
    return {"feature_ids": [feature], "weights": [.5], "sign": 1,
            "requested_norm": REQUESTED_NORM}


def _positions(positions, prefix, body, *, teacher=False, activations=False):
    tokens = prefix + body
    _require(type(positions) is list and len(positions) == len(tokens), "Probe/token alignment")
    for at, (position, token) in enumerate(zip(positions, tokens)):
        _keys(position, _POSITION | ({"activations"} if activations else set()), "position")
        origin = "prompt" if at < len(prefix) else ("teacher_forced" if teacher else "generated")
        _require(type(position["position"]) is int and position["position"] == at
                 and type(position["token_id"]) is int and position["token_id"] == token
                 and position["origin"] == origin, "Probe/token alignment")
        _require(type(position["special"]) is bool, "Malformed special-token flag")
        terminal = bool(body) and not teacher and at == len(tokens) - 1
        _require(position["terminal_observation_only"] is terminal, "Terminal probe alignment")
        if teacher and at >= len(prefix):
            _require(not position["special"], "Special teacher body token")


def _probe(probe, prefix, body, *, teacher=False, telemetry=None):
    _keys(probe, {"schema", "feature_ids", "encoding", "dictionary_width", "hook", "dtype",
                  "observation", "call_lengths", "positions", "meaning"}, "position probe")
    expected = {"schema": "fidelity_position_probe_v1", "feature_ids": list(POSITIVE_IDS),
                "encoding": "native_full_dictionary_one_position_at_a_time",
                "dictionary_width": DICTIONARY_WIDTH, "hook": HOOK_INDEX, "dtype": "torch.bfloat16",
                "observation": "before_current_additive_edit; edited_history_if_intervened",
                "meaning": "Feature activation/exposure, not semantic validation or behavioral liveness",
                "call_lengths": [len(prefix) + len(body)] if teacher else [len(prefix)] + [1] * len(body)}
    for key, value in expected.items():
        _require(_same(probe[key], value), "Wrong position probe " + key)
    _require(all(type(n) is int for n in probe["call_lengths"]), "Invalid probe call lengths")
    _positions(probe["positions"], prefix, body, teacher=teacher, activations=True)
    for at, position in enumerate(probe["positions"]):
        values = position["activations"]
        _require(type(values) is list and len(values) == len(POSITIVE_IDS), "Probe activation alignment")
        for value in values:
            _number(value, "native activation")
        if telemetry is not None:
            _require(_same({k: position[k] for k in _POSITION},
                           telemetry["position_metadata"][at]), "Probe/telemetry alignment")


def _telemetry(telemetry, prefix, body, intervention):
    _keys(telemetry, {"schema", "feature_ids", "hook", "hook_removed", "reencoding_scope",
                      "reencoding", "position_metadata", "delivery", "intervention",
                      "native_dtype", "encoding_authority"}, "telemetry")
    _require(telemetry["schema"] == "steering_fidelity_additive_v1"
             and type(telemetry["hook"]) is int and telemetry["hook"] == HOOK_INDEX
             and telemetry["hook_removed"] is True
             and telemetry["native_dtype"] == "torch.bfloat16"
             and telemetry["encoding_authority"] == "full_native_token1_v1"
             and telemetry["reencoding_scope"] == "last_prefill_and_each_cached_token",
             "Wrong native telemetry contract")
    _require(_same(telemetry["intervention"], intervention), "Intervention/telemetry mismatch")
    ids = telemetry["feature_ids"]
    _require(type(ids) is list and ids and len(ids) == len(set(ids))
             and all(type(i) is int and 0 <= i < DICTIONARY_WIDTH for i in ids), "Invalid telemetry features")
    _positions(telemetry["position_metadata"], prefix, body)
    _keys(telemetry["delivery"], _DELIVERY, "delivery arrays")
    n = len(prefix) + len(body)
    for key, values in telemetry["delivery"].items():
        _require(type(values) is list and len(values) == n, "Delivery array alignment")
        for value in values:
            _require(type(value) in (int, float) and math.isfinite(value), "Nonfinite delivery")
            if key == "cosine":
                _require(-1.000001 <= value <= 1.000001, "Invalid delivery cosine")
            else:
                _require(value >= 0, "Negative delivery metric")
    requested = 0. if intervention is None else intervention["requested_norm"]
    _require(all(math.isclose(v, requested, rel_tol=1e-5, abs_tol=1e-7)
                 if requested else v == 0 for v in telemetry["delivery"]["requested_norm"]),
             "Delivery differs from fixed requested norm")
    if intervention is None:
        _require(all(v == 0 for v in telemetry["delivery"]["realized_norm"]), "Zero arm was edited")
    reencoding = telemetry["reencoding"]
    expected_at = [len(prefix) - 1] + list(range(len(prefix), n))
    _require(type(reencoding) is list and len(reencoding) == len(expected_at), "Reencoding alignment")
    for record, at in zip(reencoding, expected_at):
        _keys(record, {"position", "before", "after"}, "reencoding")
        _require(type(record["position"]) is int and record["position"] == at, "Reencoding position")
        for key in ("before", "after"):
            _require(type(record[key]) is list and len(record[key]) == len(ids), "Reencoding width")
            for value in record[key]:
                _number(value, "reencoded activation")
        if intervention is None:
            _require(_same(record["before"], record["after"]), "Zero reencoding changed")
    return delivery_summary(telemetry)


def _choice(row, intervention):
    for key in ("p_yes", "p_no", "valid_mass", "p_correct"):
        _number(row[key], key)
        _require(row[key] <= 1, "Invalid probability: " + key)
    mass = row["valid_mass"]
    _require(mass > 0 and math.isclose(row["p_yes"] + row["p_no"], mass,
                                     rel_tol=1e-12, abs_tol=1e-15), "Choice mass mismatch")
    correct = (row["p_yes"] if row["truth"] else row["p_no"]) / mass
    _require(math.isclose(row["p_correct"], correct, rel_tol=1e-12, abs_tol=1e-15)
             and row["correct"] is (correct > .5), "Gold-side scoring mismatch")
    _require(row["predicted_answer"] == ("Yes" if row["p_yes"] >= row["p_no"] else "No"),
             "Wrong predicted answer")
    _keys(row["token_sets"], {"yes", "no"}, "choice token sets")
    for values in row["token_sets"].values():
        _tokens(values)
        _require(len(values) == len(set(values)), "Duplicate choice token")
    yes, no = map(set, (row["token_sets"]["yes"], row["token_sets"]["no"]))
    _require(not yes.intersection(no), "Overlapping choice token sets")
    _tokens([row["top_token_id"]])
    _require(type(row["top_token"]) is str and row["format_valid"] is (row["top_token_id"] in yes | no),
             "Invalid format score")
    _tokens(row["input_token_ids"])
    _require(row["input_token_ids_sha256"] == _token_hash(row["input_token_ids"]), "Input token hash")
    _digest(row["rendered_input_sha256"], "rendered input hash")
    rebuilt = _telemetry(row["telemetry"], row["input_token_ids"], [], intervention)
    _require(_same(row["delivery"], rebuilt), "Delivery summary mismatch")
    _require(_same(row["delivery_raw"], row["telemetry"]["delivery"]), "Raw delivery mismatch")
    _require(row["screen"] is None, "Unplanned native screening")


def _teacher(row, spec):
    probe = row["probe"]
    _keys(probe, {"schema", "continuation", "continuation_sha256", "serialization", "execution",
                  "token_ids_sha256", "input_token_ids", "continuation_token_ids", "position_probe"},
          "teacher probe")
    continuation = spec["continuation"]
    _require(type(continuation) is str and continuation and probe["continuation"] == continuation
             and probe["continuation_sha256"] == hashlib.sha256(continuation.encode()).hexdigest(),
             "Teacher continuation binding")
    _require(probe["schema"] == "fidelity_teacher_probe_v1"
             and probe["serialization"] == "chat_generation_prefix_ids_plus_separately_encoded_body"
             and probe["execution"] == "clean_full_prefill_not_cached_generation", "Teacher execution contract")
    prefix, body = probe["input_token_ids"], probe["continuation_token_ids"]
    _tokens(prefix)
    _tokens(body)
    _require(probe["token_ids_sha256"] == _token_hash(prefix + body), "Teacher token hash")
    _probe(probe["position_probe"], prefix, body, teacher=True)


def _generation(row, spec, intervention):
    result = row["result"]
    _keys(result, _GENERATION, "generation result")
    prefix, body = result["input_token_ids"], result["output_token_ids"]
    _tokens(prefix)
    _tokens(body)
    for name, tokens in (("input_tokens", prefix), ("output_tokens", body)):
        _require(type(result[name]) is int and result[name] == len(tokens), "Generation token count")
    _require(type(result["response"]) is str and type(result["cap_hit"]) is bool,
             "Malformed generation output")
    cap = spec.get("max_new_tokens", 64)
    _require(len(body) <= cap and (not result["cap_hit"] or len(body) == cap), "Generation cap mismatch")
    _number(result["elapsed_seconds"], "generation runtime", positive=True)
    _require(result["input_token_ids_sha256"] == _token_hash(prefix), "Generation input token hash")
    _digest(result["rendered_input_sha256"], "rendered input hash")
    _telemetry(result["telemetry"], prefix, body, intervention)
    _probe(row["position_probe"], prefix, body, telemetry=result["telemetry"])


def validate_row(row, spec, plan_hash, freeze, plan=None):
    """Validate a completed raw artifact; usable before the runner journals it."""
    try:
        _finite(row)
        if plan is not None:
            _require(_same(plan.get("fixed_dose"), {"rho": .30, "reference_norm": 18.246721267700195,
                                                   "requested_norm": REQUESTED_NORM}),
                     "Changed fixed dose")
        _require(type(spec) is dict and type(row) is dict, "Malformed row/spec")
        for key, value in spec.items():
            _require(key in row and type(row[key]) is type(value) and _same(row[key], value),
                     "Wrong frozen row field: " + key)
        _require(row.get("plan_sha256") == plan_hash and row.get("freeze_commit") == freeze,
                 "Forward binding mismatch")
        _require(row.get("missing") is False, "Missing forward is not a scientific observation")
        _number(row.get("elapsed_seconds"), "forward runtime", positive=True)
        expected = _intervention(spec)
        _require("intervention" in row and _same(row["intervention"], expected), "Wrong fixed intervention")
        task = spec.get("task")
        additions = {"choice": _CHOICE, "teacher": {"probe"},
                     "generation": {"result", "position_probe"}}
        _require(task in additions, "Unknown scientific task")
        _keys(row, set(spec) | _RUNTIME | additions[task], "raw row fields")
        if task == "choice":
            _require(type(spec.get("truth")) is bool, "Choice truth must be boolean")
            _choice(row, expected)
        elif task == "teacher":
            _require(expected is None, "Teacher exposure must be clean")
            _teacher(row, spec)
        else:
            _generation(row, spec, expected)
    except (KeyError, TypeError, IndexError, OverflowError, AttributeError) as exc:
        raise ValueError("Malformed raw row") from exc


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        _require(key not in result, "Duplicate JSON field")
        result[key] = value
    return result


def _load(path):
    _require(not path.is_symlink() and path.is_file(), "Missing or symlinked artifact: " + path.name)
    try:
        result = json.loads(path.read_text(), object_pairs_hook=_pairs)
        _finite(result)
        return result
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("Malformed JSON artifact: " + path.name) from exc


def _inventory(plan):
    _finite(plan)
    groups = []
    for name, size, task in (("discovery_rows", 200, "choice"),
                             ("validation_neutral_rows", 40, "choice"),
                             ("singleton_rows", 80, "choice"),
                             ("teacher_rows", 48, "teacher"),
                             ("generation_rows", 72, "generation")):
        rows = plan[name]
        _require(type(rows) is list and len(rows) == size, "Wrong inventory size: " + name)
        _require(all(type(s) is dict and s.get("task") == task for s in rows), "Wrong inventory task")
        groups.append(rows)
    _keys(plan["validation_rows"], {"P0", "P1"}, "pressure candidate inventory")
    for candidate, rows in plan["validation_rows"].items():
        _require(type(rows) is list and len(rows) == 80, "Wrong selected pressure inventory size")
        _require(all(s.get("task") == "choice" and s.get("pressure_id") == candidate
                     and s.get("frame") in ("assert", "doubt") for s in rows), "Wrong pressure inventory")
    groups[2:2] = [plan["validation_rows"][c] for c in ("P0", "P1")]
    rows = [s for group in groups for s in group]
    _require(_same(plan["rows"], rows), "Potential inventory/section mismatch")
    specs = {}
    for spec in rows:
        identifier = spec.get("id")
        _require(type(identifier) is str and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", identifier),
                 "Unsafe scientific row ID")
        _require(identifier not in specs, "Duplicate potential row ID")
        _require(not set(spec).intersection(_RUNTIME), "Spec overrides runtime binding")
        _intervention(spec)
        specs[identifier] = spec
    _require(len(specs) == 600, "Expected all 600 potential specs")
    _require(_same(plan.get("fixed_dose"), {"rho": .30, "reference_norm": 18.246721267700195,
                                           "requested_norm": REQUESTED_NORM}), "Changed fixed dose")
    return specs


def _journal(root, plan_hash, freeze):
    path = root / "receipts.jsonl"
    _require(not path.is_symlink(), "Symlinked receipt journal")
    if path.exists():
        for line in path.read_text().splitlines():
            event = json.loads(line, object_pairs_hook=_pairs)
            _finite(event)
    events = read_receipts(root)
    base = {"index", "previous", "utc", "kind", "row_id", "plan_sha256", "freeze_commit", "sha256"}
    for at, event in enumerate(events):
        kind = event.get("kind")
        _require(kind in ("dispatch", "complete"), "Unknown receipt event")
        _keys(event, base | ({"payload_sha256"} if kind == "complete" else set()), "receipt fields")
        _require(type(event["index"]) is int and event["index"] == at, "Malformed receipt index")
        _require(type(event["utc"]) is str and event["utc"], "Malformed receipt timestamp")
        _require(event["plan_sha256"] == plan_hash and event["freeze_commit"] == freeze,
                 "Receipt binding mismatch")
        if kind == "complete":
            _digest(event["payload_sha256"], "receipt payload hash")
    return events


class _PrefixEnd(Exception):
    """A valid live prefix ended before the next row or decision was persisted."""


def _audit(root, plan, plan_hash, freeze, partial):
    specs = _inventory(plan)
    _require(not (root / "forwards").is_symlink(), "Symlinked forwards directory")
    events = _journal(root, plan_hash, freeze)
    completed, dispatched, decisions = {}, set(), {}
    seconds, cursor = [], 0
    expected_count, complete = None, False

    def collect(section):
        nonlocal cursor
        values = []
        for spec in section:
            if cursor == len(events):
                raise _PrefixEnd
            event = events[cursor]
            identifier = spec["id"]
            _require(event["kind"] == "dispatch" and event["row_id"] == identifier,
                     "Receipt order differs from conditional inventory")
            _require(identifier not in dispatched, "Duplicate forward dispatch")
            dispatched.add(identifier)
            cursor += 1
            path = root / "forwards" / (identifier + ".json")
            row = None
            if path.exists() or path.is_symlink():
                row = _load(path)
                validate_row(row, specs[identifier], plan_hash, freeze, plan)
            if cursor == len(events):
                raise _PrefixEnd
            event = events[cursor]
            _require(event["kind"] == "complete" and event["row_id"] == identifier,
                     "Completion must immediately follow its dispatch")
            _require(row is not None and sha(path) == event["payload_sha256"], "Raw forward hash mismatch")
            completed[identifier] = row
            seconds.append(row["elapsed_seconds"])
            values.append(row)
            cursor += 1
        return values

    def decision(name, expected):
        path = root / (name + "-decision.json")
        if not path.exists() and not path.is_symlink():
            _require(cursor == len(events), "Forward crossed missing " + name + " decision barrier")
            raise _PrefixEnd
        record = _load(path)
        binding = {"decision": expected, "plan_sha256": plan_hash, "freeze_commit": freeze,
                   "after_receipt_sha256": events[cursor - 1]["sha256"], "stage_t_authorized": False}
        _require(events[cursor - 1]["kind"] == "complete" and _same(record, binding),
                 "Forged or misordered " + name + " decision")
        decisions[name] = expected
        return expected

    try:
        discovery = collect(plan["discovery_rows"])
        selected = decision("discovery", discovery_gate(discovery))["selected"]
        _require(selected in (None, "P0", "P1"), "Unknown discovery selection")
        neutral = collect(plan["validation_neutral_rows"])
        if selected is None:
            validation = {"status": "not_run", "reason": "no_discovery_candidate_passed",
                          "pass": False, "stage_t_authorized": False}
        else:
            pressured = collect(plan["validation_rows"][selected])
            validation = validation_gate(neutral + pressured, selected)
        decision("validation", validation)
        edited = collect(plan["singleton_rows"])
        from .analysis import singleton_gate
        singleton = decision("singleton", singleton_gate(neutral + edited))
        _require(type(singleton.get("pass")) is bool, "Nonboolean singleton decision")
        expected_count = 368 + (80 if selected is not None else 0) + (72 if singleton["pass"] else 0)
        teacher = collect(plan["teacher_rows"])
        generated = collect(plan["generation_rows"]) if singleton["pass"] else []
        from .liveness import summarize
        decision("liveness", summarize(teacher, generated, singleton_pass=singleton["pass"]))
        complete = True
    except _PrefixEnd:
        pass

    _require(cursor == len(events), "Extra or forbidden forward receipts")
    decision_names = {p.name for p in root.glob("*-decision.json")}
    _require(decision_names == {name + "-decision.json" for name in decisions},
             "Unknown, premature or skipped decision artifact")
    for path in (root / "forwards").glob("*"):
        _require(path.name.endswith(".json") and path.stem in dispatched and path.is_file()
                 and not path.is_symlink(), "Unknown or unreceipted raw artifact")
    unresolved = sorted(dispatched - completed.keys())
    _require(partial or complete and not unresolved, "Incomplete conditional inventory or decisions")
    marker = root / "complete.json"
    if marker.exists() or marker.is_symlink():
        _require(complete and not unresolved, "Premature complete marker")
        expected = {"pass": True, "meaning": "conditional_inventory_complete_not_scientific_gate",
                    "forwards": len(completed), "plan_sha256": plan_hash, "freeze_commit": freeze,
                    "pressure_pass": decisions["validation"]["pass"],
                    "singleton_pass": decisions["singleton"]["pass"],
                    "liveness_pass": decisions["liveness"]["pass"],
                    "stage_t_authorized": False, "e_only_fallback": False}
        _require(_same(_load(marker), expected), "Forged complete marker")
    return {"pass": not unresolved, "forwards": len(completed), "forward_seconds": seconds,
            "unresolved_forward_ids": unresolved, "complete": complete and not unresolved,
            "expected_forwards": expected_count, "receipt_events": len(events)}


def audit_raw_window(root, plan, plan_hash, freeze, partial=True):
    """Reconstruct the serial conditional inventory, never a scientific pass.

    A dispatched row without a completion remains unresolved even if its valid
    artifact is already on disk. Decisions may lag a completed stage in a live
    prefix, but no later dispatch or decision may cross that missing barrier.
    """
    try:
        _require(type(partial) is bool, "partial must be boolean")
        return _audit(Path(root), plan, plan_hash, freeze, partial)
    except (KeyError, TypeError, IndexError, OverflowError, AttributeError, OSError,
            UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("Malformed raw audit window") from exc
