"""Independent, read-only structural audit of assay v2 outcomes and receipts.

Only the standard library is used: no backend/analysis imports, reconstruction
of scientific gates, model access, repairs, or outcome imputation. Numeric
tolerances below cover FP32 arithmetic consistency, not intervention quality.
Teacher fixture IDs may recur across distinct arms in plain JSONL; supplying
expected_ids instead requires unique execution IDs. Ledger row_id is always a
unique execution ID. Optional require_complete checks the supplied inventory.

A hash chain cannot establish historical append-only behavior by itself. Save
the returned {bytes, sha256} anchor elsewhere and supply it on the next audit
to detect prefix replacement or truncation, including deletion of whole rows.
Notebook wrappers may explicitly omit upstream prompt IDs for copyright; their
counts/hash syntax are checked, but the missing IDs cannot be rehashed here.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re

SCHEMA = "sae_assay_backend_v2"
AUTHORITY = "full_native_token1_v1"
ACTIVATIONS = ("before", "requested_delta", "requested_activation", "after")
NORM_FIELDS = ("requested_norm", "realized_norm", "clean_norm", "relative_error")
BOOL_FIELDS = ("identity", "valid", "nonzero_requested")
FULL_MATRICES = ("full_selected_before", "full_selected_after", "selected_path_before",
                 "selected_path_after", "ideal_fp32_before", "ideal_fp32_after", "actual_fp32_after")
TRANSPORT = {"transport_error", "error", "failed", "invalid_response"}
INCOMPLETE = {"incomplete", "not_run_by_gate", "not_run_budget"}


class Invalid(ValueError):
    def __init__(self, path, message, code="invalid_data"):
        self.error = {"path": path, "code": code, "message": message}
        super().__init__(message)


def _need(condition, path, message, code="invalid_data"):
    if not condition:
        raise Invalid(path, message, code)


def _json(value, path="$", active=None):
    active = set() if active is None else active
    if type(value) in (dict, list):
        _need(id(value) not in active, path, "Cyclic value")
        active.add(id(value))
        for key, item in (value.items() if type(value) is dict else enumerate(value)):
            _need(type(value) is list or type(key) is str, path, "Non-string JSON key")
            _json(item, f"{path}.{key}", active)
        active.remove(id(value))
    elif type(value) in (int, float):
        _need(math.isfinite(value), path, "Nonfinite number")
    else:
        _need(value is None or type(value) in (str, bool), path, "Not a JSON value")


def _loads(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            _need(key not in result, "$", f"Duplicate JSON key: {key}")
            result[key] = value
        return result

    def constant(value):
        raise Invalid("$", f"Nonfinite JSON constant: {value}")

    value = json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
    _json(value)
    return value


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode("ascii")


def _object(value, path):
    _need(type(value) is dict, path, "Expected object")
    return value


def _string(value, path):
    _need(type(value) is str and bool(value), path, "Expected nonempty string")
    return value


def _number(value, path, minimum=None):
    _need(type(value) in (int, float) and math.isfinite(value), path, "Expected finite number, not bool/null")
    _need(minimum is None or value >= minimum, path, f"Number below {minimum}")
    return value


def _integer(value, path, minimum=0):
    _need(type(value) is int and value >= minimum, path, f"Expected integer >= {minimum}")
    return value


def _boolean(value, path):
    _need(type(value) is bool, path, "Expected Boolean")
    return value


def _array(value, n, path):
    _need(type(value) is list and len(value) == n, path, f"Expected array of length {n}")
    return value


def _vector(value, n, path, boolean=False, first_null=False, minimum=None):
    for i, item in enumerate(_array(value, n, path)):
        if first_null and i == 0:
            _need(item is None, path, "First loss entry must be null")
        elif boolean:
            _boolean(item, f"{path}[{i}]")
        else:
            _number(item, f"{path}[{i}]", minimum)
    return value


def _matrix(value, n, k, path, nonnegative=True):
    for i, row in enumerate(_array(value, n, path)):
        _vector(row, k, f"{path}[{i}]", minimum=0 if nonnegative else None)


def _ids(value, path, nonempty=True, unique=False):
    _need(type(value) is list and (value or not nonempty), path, "Expected token/feature ID array")
    for item in value:
        _integer(item, path)
    _need(not unique or len(set(value)) == len(value), path, "Duplicate feature IDs")
    return value


def _close(a, b, path, message):
    _need(math.isclose(a, b, rel_tol=2e-5, abs_tol=1e-6), path, message)


def _sha(value, path, width=64):
    _need(type(value) is str and re.fullmatch(r"[0-9a-f]{%d}" % width, value), path, "Invalid hash")
    return value


def _mode(mode, strength, path):
    _number(strength, path + ".strength", 0)
    _need((mode == "zero" and strength == 0) or
          (mode in ("suppression", "amplification") and strength in (0, .5, 1)),
          path, "Invalid mode/strength")


def _telemetry(t, tokens, prompt, path, mode=None, strength=None):
    _object(t, path)
    _need(t["schema_version"] == SCHEMA and t["encoding_authority"] == AUTHORITY,
          path, "Wrong backend schema/encoding authority")
    _need(t["hook_removed"] is True, path, "Hook was not removed")
    _need(t["native_dtype"] in ("torch.bfloat16", "torch.float32") and
          t["diagnostics_dtype"] == "torch.float32", path, "Unexpected arithmetic dtype")
    features = _ids(t["feature_ids"], path + ".feature_ids", unique=True)
    n, k = len(tokens), len(features)
    shape = _array(t["full_encode_shape"], 3, path + ".full_encode_shape")
    for v in shape:
        _integer(v, path + ".full_encode_shape", 1)
    _need(shape[0] == 1 and max(features) < shape[1], path, "Noncanonical encoder shape or out-of-range feature")
    positions = _array(t["position_metadata"], n, path + ".position_metadata")
    for i, p in enumerate(positions):
        _object(p, f"{path}.position_metadata[{i}]")
        _need(type(p["position"]) is int and p["position"] == i, path, "Duplicate, unordered or missing position")
        if tokens[i] is None:
            _need(i < prompt and "token_id" not in p, path, "Redacted prompt IDs must be absent, not replaced")
        else:
            _need(type(p["token_id"]) is int and p["token_id"] == tokens[i], path, "Position/token ID mismatch")
        origin = "prompt" if i < prompt else "generated"
        _need(p["origin"] == origin and p["token_class"] in (origin, "special"), path, "Token origin/class mismatch")
        terminal = _boolean(p["terminal_observation_only"], path)
        _need(terminal == (i == n - 1 and prompt < n), path, "Terminal flag must mark only the final recorded output")
    a, d = _object(t["selected_activations"], path), _object(t["delivery"], path)
    for key in ACTIVATIONS:
        _need(key in a, path, f"Missing activation array {key}")
    for key, matrix in a.items():
        _matrix(matrix, n, k, f"{path}.selected_activations.{key}", key != "requested_delta")
    for key in NORM_FIELDS + BOOL_FIELDS + ("cosine",):
        _need(key in d, path, f"Missing delivery array {key}")
    for key, vector in d.items():
        _vector(vector, n, f"{path}.delivery.{key}", boolean=key in BOOL_FIELDS,
                minimum=0 if key in NORM_FIELDS else None)
    q90 = t.get("q90")
    if q90 is not None:
        _vector(q90, k, path + ".q90", minimum=0)
    candidates = {(m, s) for m in ("suppression", "amplification") for s in (0, .5, 1)}
    if mode is not None:
        _mode(mode, strength, path)
        candidates = {(mode, strength)}
    for i in range(n):
        at = f"{path}.position[{i}]"
        r, actual, clean, error = (d[key][i] for key in NORM_FIELDS)
        cosine, identity = d["cosine"][i], d["identity"][i]
        _need(-1 <= cosine <= 1, at, "Cosine outside [-1,1]")
        _need(d["nonzero_requested"][i] == (r > 0), at, "Request norm/flag mismatch")
        _need(identity == (actual == 0), at, "Identity/realized norm mismatch")
        if r == 0:
            _need(actual == 0 and error == 0 and cosine == 1, at, "Broken zero-request convention")
        else:
            ratio = actual / r
            expected_square = (ratio - 1)**2 + 2 * ratio * (1 - cosine)
            _need(abs(error**2 - expected_square) <= 2e-5 * max(1, ratio**2, error**2),
                  at, "Norm/cosine/relative-error identity is inconsistent")
            if actual == 0:
                _need(cosine == 0 and error == 1, at, "Rounded-away request must have cosine 0/error 1")
        if identity:
            _need(a["before"][i] == a["after"][i], at, "Identity changed re-encoded coordinates")
        if all(delta == 0 for delta in a["requested_delta"][i]):
            _need(r == 0 and identity, at, "Zero coordinate request changed residual")
        for j in range(k):
            before, delta, requested, after = (a[key][i][j] for key in ACTIVATIONS)
            _close(before + delta, requested, at, "Requested activation != before + delta")
            if not d["valid"][i]:
                _need(delta == 0 and identity, at, "Masked position changed")
                continue
            compatible = set()
            for m, s in candidates:
                expected = (0 if m == "zero" else -s * before if m == "suppression" else
                            s * max(q90[j] - before, 0) if q90 is not None else None)
                if expected is not None and math.isclose(delta, expected, rel_tol=2e-5, abs_tol=1e-6):
                    compatible.add((m, s))
            candidates &= compatible
            _need(candidates, at, "Request signs/dose/q90 inconsistent with one intervention")
    full = t.get("full_sae")
    if full is not None:
        _object(full, path + ".full_sae")
        for key in FULL_MATRICES:
            _need(key in full, path, f"Missing full-SAE observation {key}")
        for key, values in full.items():
            if key in FULL_MATRICES or (type(values) is list and values and type(values[0]) is list):
                _matrix(values, n, k, path + ".full_sae." + key)
            else:
                _vector(values, n, path + ".full_sae." + key, minimum=0)
        for i in range(n):
            for when in ("before", "after"):
                _need(full["full_selected_" + when][i] == a[when][i], path,
                      "Full-SAE canonical columns disagree with primary activations")
            for key in ("l0_before", "l0_after", "non_target_changed_count"):
                value = _integer(full[key][i], path + ".full_sae." + key)
                _need(value <= shape[1] - (k if key == "non_target_changed_count" else 0), path, "Full-SAE count exceeds dictionary width")
            _close(full["reconstruction_relative_error"][i],
                   full["reconstruction_error_norm"][i] / max(d["clean_norm"][i], 1e-30),
                   path, "Reconstruction norm/relative error mismatch")
            if d["identity"][i]:
                _need(full["ideal_fp32_before"][i] == full["actual_fp32_after"][i], path,
                      "Identity changed the FP32 reference")
    shapes = t.get("selected_encode_shapes", [])
    _need(type(shapes) is list, path, "Selected-path shapes must be an array")
    count = 0
    for s in shapes:
        _array(s, 3, path)
        for value in s:
            _integer(value, path, 1)
        count += _integer(s[0], path, 1)
        _need(s[1:] == [k, shape[2]], path, "Selected-path diagnostic shape mismatch")
    _need(count == (n if full is not None else 0), path, "Selected-path shape counts do not match diagnostics")
    return n, k


def _context(result, path, generation=False, protocol=None):
    omitted = result.get("upstream_input_tokens_omitted", False)
    _boolean(omitted, path + ".upstream_input_tokens_omitted")
    if omitted:
        _need(generation and protocol == "notebook" and "input_token_ids" not in result,
              path, "Prompt omission requires notebook context and absent input IDs")
        inputs = [None] * _integer(result["input_tokens"], path, 1)
    else:
        inputs = _ids(result["input_token_ids"], path + ".input_token_ids")
    outputs = _ids(result["output_token_ids"], path + ".output_token_ids", nonempty=generation)
    _need(_integer(result["input_tokens"], path, 1) == len(inputs) and
          _integer(result["output_tokens"], path) == len(outputs), path, "Token count mismatch")
    return inputs + outputs, len(inputs)


def _summary(result, n, features, path):
    summaries = _array(result["activation_summaries"], len(features), path)
    for j, row in enumerate(summaries):
        _need(type(row["feature_id"]) is int and row["feature_id"] == features[j], path, "Summary feature ordering mismatch")
        for when in ("before", "after"):
            values = [r[j] for r in result["telemetry"]["selected_activations"][when]]
            active = sorted(v for v in values if v > 0)
            s = row[when]
            _need(type(s["count"]) is int and s["count"] == n and
                  type(s["active_count"]) is int and s["active_count"] == len(active), path, "Summary count mismatch")
            for key, expected in (("frequency", len(active) / n), ("mean", math.fsum(values) / n), ("max", max(values))):
                _close(_number(s[key], path, 0), expected, path, f"Summary {key} mismatch")
            for key, q in (("positive_q50", .5), ("positive_q90", .9)):
                if not active:
                    _need(s[key] is None, path, "Unavailable positive quantile must be null")
                else:
                    at = (len(active) - 1) * q
                    low, high = math.floor(at), math.ceil(at)
                    expected = active[low] + (active[high] - active[low]) * (at - low)
                    _close(_number(s[key], path, 0), expected, path, "Summary quantile mismatch")


def _teacher_result(result, path, counts, mode=None, strength=None):
    _object(result, path)
    tokens, prompt = _context(result, path)
    _ids(result["token_ids"], path + ".token_ids")
    _integer(result["prompt_length"], path, 1)
    _need(result["token_ids"] == tokens and result["prompt_length"] == prompt, path, "Replay/context mismatch")
    schedule = result["forward_schedule"]
    _need(schedule in ("uncached_teacher", "original_prefill_then_cached_token1") and
          (schedule != "uncached_teacher" or prompt == len(tokens)), path, "Invalid forward schedule")
    _number(result["elapsed_seconds"], path, 0)
    n, k = _telemetry(result["telemetry"], tokens, prompt, path + ".telemetry", mode, strength)
    _telemetry(result["clean_telemetry"], tokens, prompt, path + ".clean_telemetry", "zero", 0)
    _need(result["clean_telemetry"]["feature_ids"] == result["telemetry"]["feature_ids"], path, "Clean/edited feature IDs differ")
    for key in ("unsteered_nll", "edited_nll", "kl_clean_to_edited"):
        _vector(result[key], n, path + "." + key, first_null=True,
                minimum=-1e-5 if key == "kl_clean_to_edited" else 0)
    reconstruction = _boolean(result["full_sae_diagnostics"], path)
    _need(reconstruction == (result["telemetry"]["full_sae"] is not None), path, "Full-SAE presence flag mismatch")
    if reconstruction:
        _vector(result["reconstruction_nll"], n, path + ".reconstruction_nll", first_null=True, minimum=0)
    else:
        _need(result["reconstruction_nll"] is None, path, "Unexpected reconstruction loss")
    if all(result["telemetry"]["delivery"]["identity"]):
        _need(result["unsteered_nll"] == result["edited_nll"] and
              all(v == 0 for v in result["kl_clean_to_edited"][1:]), path, "Whole-sequence identity changed loss/KL")
    _summary(result, n, result["telemetry"]["feature_ids"], path + ".activation_summaries")
    counts.update(teacher_results=1, positions=n, feature_positions=n * k)


def _generation(result, path, counts, protocol=None):
    _object(result, path)
    tokens, prompt = _context(result, path, generation=True, protocol=protocol)
    _need(type(result["response"]) is str, path, "Response must be a string, including explicit empty output")
    _boolean(result["cap_hit"], path + ".cap_hit")
    _number(result["elapsed_seconds"], path, 0)
    n, k = _telemetry(result["telemetry"], tokens, prompt, path + ".telemetry")
    _sha(result["rendered_input_sha256"], path)
    _sha(result["input_token_ids_sha256"], path)
    if result.get("upstream_input_tokens_omitted"):
        counts["redacted_generation_results"] += 1
        counts["prompt_ids_not_rehashed"] += prompt
    else:
        expected = hashlib.sha256(json.dumps(result["input_token_ids"]).encode()).hexdigest()
        _need(result["input_token_ids_sha256"] == expected, path, "Input token hash mismatch")
    counts.update(generation_results=1, positions=n, feature_positions=n * k)


def _transport(row, path, allow_empty=False):
    status = row.get("status", "ok")
    _need(type(status) is str, path, "Transport status must be a string")
    if status in TRANSPORT:
        raise Invalid(path, f"Recorded transport failure: {status}", "transport_error")
    if status in INCOMPLETE:
        raise Invalid(path, f"Recorded execution state: {status}", "incomplete")
    _need(status in ("ok", "missing") or (allow_empty and status == "missing_empty"), path, f"Unknown transport status: {status}")
    if status == "missing":
        raise Invalid(path, "Explicit missing outcome", "missing")


def _teacher(row, path, counts):
    _object(row, path)
    if "result" not in row and "telemetry" in row:
        _teacher_result(row, path, counts)
        return
    for key in ("id", "split", "category", "group"):
        _string(row[key], path + "." + key)
    _need(row["split"] in ("calibration", "validation", "qualification"), path, "Unknown teacher split")
    _mode(row["mode"], row["strength"], path)
    _transport(row, path)
    _teacher_result(row["result"], path + ".result", counts, row["mode"], row["strength"])


def _baseline(row, path, counts):
    _string(row["id"], path)
    _need(row["phase"] in ("core", "optional"), path, "Unknown baseline phase")
    if "missing" in row:
        _boolean(row["missing"], path)
    _transport(row, path, allow_empty=True)
    protocol = row.get("protocol", "paper")
    _need(protocol in ("paper", "notebook"), path, "Unknown baseline protocol")
    for key in ("generation1", "generation2"):
        _generation(row[key], path + "." + key, counts, protocol=protocol)
        t = row[key]["telemetry"]
        _need(all(t["delivery"]["identity"]) and all(delta == 0 for values in
              t["selected_activations"]["requested_delta"] for delta in values), path, "Baseline contains a steering request")
    _need(row["response"] == row["generation2"]["response"], path, "Baseline response differs from second generation")
    empty = not row["response"].strip()
    if "missing" in row:
        _need(row["missing"] == empty, path, "Empty response/missing flag mismatch")
    else:
        _need(row.get("status") == ("missing_empty" if empty else "ok"), path, "Empty response/status mismatch")
    if row.get("status") == "missing_empty":
        _need(empty, path, "missing_empty has a nonempty response")
    if "first_turn_empty" in row:
        _need(type(row["first_turn_empty"]) is bool and row["first_turn_empty"] ==
              (not row["generation1"]["response"].strip()), path, "First-turn missingness mismatch")
    if row.get("replay") is not None:
        replay = row["replay"]
        _teacher_result(replay, path + ".replay", counts, "zero", 0)
        _need(replay["input_token_ids"] == row["generation2"]["input_token_ids"] and
              replay["output_token_ids"] == row["generation2"]["output_token_ids"],
              path, "Replay differs from recorded second-turn context")
    counts["baseline_rows"] += 1
    if empty:
        raise Invalid(path, "Explicit empty baseline response", "missing")


def _qualification(row, path, counts):
    _string(row["id"], path)
    _string(row["text_id"], path)
    _teacher_result(row["result"], path + ".result", counts, "zero", 0)
    _teacher_result(row["zero"], path + ".zero", counts, "zero", 0)
    passed = (row["result"]["token_ids"] == row["zero"]["token_ids"] and
              row["result"]["unsteered_nll"] == row["zero"]["edited_nll"])
    _need(_boolean(row["zero_pass"], path) == passed, path, "Qualification zero_pass contradicts recorded evidence")
    _object(row["encoder_diagnostic"], path)
    check = row.get("generation_check")
    if check is not None:
        _object(check, path + ".generation_check")
        generated, zero, replay = (check[key] for key in ("generated", "zero_generated", "replay"))
        for key in ("generated", "zero_generated"):
            result = check[key]
            _generation(result, path + ".generation_check." + key, counts)
            _need(result["output_tokens"] <= 8 and
                  (not result["cap_hit"] or result["output_tokens"] == 8),
                  path, "Qualification generation exceeds its frozen eight-token cap")
            t = result["telemetry"]
            _need(all(t["delivery"]["identity"]) and all(x == 0 for xs in
                  t["selected_activations"]["requested_delta"] for x in xs),
                  path, "Qualification clean/zero generation contains a steering request")
        _teacher_result(replay, path + ".generation_check.replay", counts, "zero", 0)
        for result in (zero, replay):
            _need(result["input_token_ids"] == generated["input_token_ids"],
                  path, "Qualification generation/replay prompt context differs")
        _need(zero["rendered_input_sha256"] == generated["rendered_input_sha256"],
              path, "Qualification clean/zero rendered prompts differ")
        _need(replay["output_token_ids"] == generated["output_token_ids"] and
              replay["forward_schedule"] == "original_prefill_then_cached_token1",
              path, "Qualification replay must use the exact original cached context")
        _need(all(result["telemetry"]["feature_ids"] == row["result"]["telemetry"]["feature_ids"]
                  for result in (generated, zero, replay)), path, "Qualification feature columns differ")
        passed = (generated["output_token_ids"] == zero["output_token_ids"] and
                  generated["telemetry"]["selected_activations"] == replay["telemetry"]["selected_activations"])
        _need(_boolean(check["pass"], path) == passed,
              path, "Qualification generation_check.pass contradicts recorded evidence")
        counts["generation_checks"] += 1
        counts["failed_generation_checks"] += int(not passed)
    counts["qualification_rows"] += 1


def _positive(row, path, counts):
    _string(row["id"], path)
    _string(row["task_id"], path)
    _need(row["arm"] in ("zero", "instruction", "suppression", "amplification"), path, "Unknown formatting arm")
    _need(_integer(row["seed"], path) < 2**63, path, "Invalid seed")
    _number(row["temperature"], path, 0)
    maximum = _integer(row["max_new_tokens"], path, 1)
    _need(maximum <= 256, path, "Generation cap exceeds backend maximum")
    _transport(row, path)
    result = row["result"]
    _generation(result, path + ".result", counts)
    _need(result["output_tokens"] <= maximum and (not result["cap_hit"] or result["output_tokens"] == maximum),
          path, "Token count/cap mismatch")
    _boolean(row["nondegenerate"], path)
    if row["arm"] in ("zero", "instruction"):
        _need(all(result["telemetry"]["delivery"]["identity"]) and
              all(x == 0 for xs in result["telemetry"]["selected_activations"]["requested_delta"] for x in xs),
              path, "Unsteered formatting arm has an edit")
    else:
        deltas = result["telemetry"]["selected_activations"]["requested_delta"]
        _need(all(x <= 0 if row["arm"] == "suppression" else x >= 0 for xs in deltas for x in xs),
              path, "Formatting arm/request sign mismatch")
    counts["positive_rows"] += 1


def _local_judge(row, path, counts):
    _string(row["id"], path)
    _string(row["source_id"], path)
    _transport(row, path)
    _need(row["rubric"] in ("paper", "notebook"), path, "Unknown local rubric")
    _need(type(row["response"]) is str, path, "Invalid judge response")
    mapping = {"0": 0, "1": 1} if row["rubric"] == "paper" else {"no": 0, "yes": 1}
    expected = mapping.get(row["response"].strip().lower())
    _need((row["label"] is None or type(row["label"]) is int) and row["label"] == expected,
          path, "Judge label differs from exact declared reduction")
    _boolean(row["cap_hit"], path)
    _integer(row["input_tokens"], path, 1)
    _integer(row["output_tokens"], path, 1)
    _sha(row["prompt_sha256"], path)
    counts["local_judge_rows"] += 1
    counts["unparsed_judge_labels"] += expected is None


def _dispatch(row, path, counts):
    _object(row, path)
    _need("kind" not in row or row["kind"] in
          ("baseline", "qualification", "positive", "local_judge", "teacher"), path, "Unknown row kind")
    if row.get("kind") == "baseline":
        _baseline(row, path, counts)
    elif row.get("kind") == "qualification":
        _qualification(row, path, counts)
    elif row.get("kind") == "local_judge":
        _local_judge(row, path, counts)
    elif "split" in row or "unsteered_nll" in row:
        _teacher(row, path, counts)
    elif "telemetry" in row and "response" in row:
        _generation(row, path, counts)
    elif row.get("kind") == "positive":
        _positive(row, path, counts)
    else:
        raise Invalid(path, "Unrecognized outcome schema")


def _status(errors):
    codes = {e["code"] for e in errors}
    return next((s for s in ("invalid_data", "incomplete", "transport_error", "missing") if s in codes), "ok").replace("invalid_data", "invalid")


def _result(errors, counts, **extra):
    status = _status(errors)
    limitations = (["Redacted upstream prompt IDs are not independently rehashed; validate full generation before omission."]
                   if counts.get("redacted_generation_results") else [])
    return {"status": status, "pass": status == "ok", "errors": errors, "counts": dict(counts),
            "scope": "structural_only", "limitations": limitations, **extra}


def _report(action, value):
    errors, counts = [], Counter(rows=1, valid_rows=0)
    try:
        _json(value)
        action(value, "$", counts)
        counts["valid_rows"] = 1
    except Invalid as exc:
        errors.append(exc.error)
    except (KeyError, TypeError, ValueError, OverflowError, RecursionError, IndexError) as exc:
        errors.append({"path": "$", "code": "invalid_data", "message": f"Malformed record: {exc}"})
    for error in errors:
        counts[error["code"] + "_rows"] += 1
    return _result(errors, counts)


def validate_teacher(row):
    """Validate a raw teacher/replay result or {id,split,category,group,mode,strength,result}."""
    return _report(_teacher, row)


def validate_generation(result, *, protocol=None):
    """Validate a raw generation result; no positive/negative outcome is assigned."""
    return _report(lambda row, path, counts: _generation(row, path, counts, protocol), result)


def _expected(values):
    if values is None:
        return None
    _need(type(values) is list, "$plan", "Expected a list of planned IDs or rows")
    ids = [_string(v["id"] if type(v) is dict else v, "$plan") for v in values]
    _need(len(set(ids)) == len(ids), "$plan", "Duplicate planned IDs")
    return set(ids)


def _row_file(root, receipt, identifier):
    _object(receipt, "$receipt")
    _need(set(receipt) == {"path", "sha256"}, "$receipt", "Expected exact path/hash row receipt")
    _string(identifier, "$receipt.id")
    _need("/" not in identifier and "\\" not in identifier and identifier not in (".", ".."),
          "$receipt.id", "Unsafe row ID")
    _need(receipt["path"] == f"rows/{identifier}.json", "$receipt.path", "Row path must match execution ID")
    _sha(receipt["sha256"], "$receipt.sha256")
    path = root / receipt["path"]
    _need(not root.is_symlink() and not (root / "rows").is_symlink() and not path.is_symlink(),
          str(path), "Symlink row paths are forbidden")
    _need(path.is_file() and path.resolve().is_relative_to(root.resolve()), str(path), "Missing or escaping row file")
    raw = path.read_bytes()
    _need(hashlib.sha256(raw).hexdigest() == receipt["sha256"], str(path), "Row file hash mismatch")
    value = _object(_loads(raw), str(path))
    _need(value.get("id") == identifier, str(path), "Row file ID differs from receipt")
    return value


def validate_jsonl(path, expected_ids=None, *, require_complete=False, anchor=None):
    """Read raw outcomes, EventLedger envelopes, or flat SHA-chained receipts.

    Non-outcome receipt payloads get integrity/JSON validation only; this is
    not a financial-policy or judgment-schema audit. Each hash chain must use
    one plan/freeze binding. A truncated final line is invalid, never repaired.
    """
    path = Path(path)
    errors, counts, seen, outcomes = [], Counter(rows=0, valid_rows=0), set(), set()
    previous, binding, ledger_ids, chain_format = None, None, None, None
    references, observed, dispatched = {}, set(), set()
    try:
        expected = _expected(expected_ids)
        _need(path.is_file() and not path.is_symlink(), str(path), "Expected a regular, nonsymlink file")
        raw = path.read_bytes()
        if anchor is not None:
            _integer(anchor["bytes"], "$anchor")
            _sha(anchor["sha256"], "$anchor")
            _need(len(raw) >= anchor["bytes"] and
                  hashlib.sha256(raw[:anchor["bytes"]]).hexdigest() == anchor["sha256"],
                  str(path), "Prior audited prefix was truncated or replaced")
        _need(not raw or raw.endswith(b"\n"), str(path), "Truncated final JSONL line")
        if not raw:
            errors.append({"path": str(path), "code": "incomplete", "message": "Empty JSONL has no receipts/outcomes"})
        for number, line in enumerate(raw.splitlines(), 1):
            counts["rows"] += 1
            location = f"{path}:{number}"
            try:
                row = _object(_loads(line), location)
                fmt = "ledger" if "sha256" in row and "data" in row else "receipt" if "receipt_sha256" in row else "plain"
                if chain_format is None:
                    chain_format = fmt
                _need(fmt == chain_format, location, "Mixed plain/chained receipt formats")
                payload, rid = row, row.get("id")
                if fmt != "plain":
                    hash_key = "sha256" if fmt == "ledger" else "receipt_sha256"
                    body = {k: v for k, v in row.items() if k != hash_key}
                    _sha(row[hash_key], location)
                    _need(hashlib.sha256(_canonical(body)).hexdigest() == row[hash_key] and
                          row["previous_sha256"] == previous, location, "Receipt hash chain mismatch")
                    current = (_sha(row["plan_sha256"], location), _sha(row["freeze_commit"], location, 40))
                    _need(binding is None or current == binding, location, "Plan/freeze binding changed")
                    binding, previous = current, row[hash_key]
                    if fmt == "ledger":
                        _need(set(row) == {"id", "seq", "data", "plan_sha256", "freeze_commit", "previous_sha256", "sha256"}
                              and _canonical(row) == line, location, "Noncanonical ledger envelope")
                        _need(type(row["seq"]) is int and row["seq"] == number - 1, location, "Ledger sequence mismatch")
                        event_id = _string(row["id"], location)
                        _need(event_id not in seen, location, "Duplicate event ID")
                        seen.add(event_id)
                        data = _object(row["data"], location)
                        kind = _string(data["kind"], location)
                        if number == 1:
                            _need(event_id == "binding" and kind == "binding", location, "Missing initial inventory binding")
                            ledger_ids = _expected(data["row_ids"])
                            _need(expected is None or expected == ledger_ids, location, "Plan inventory differs from ledger binding")
                        if kind != "row":
                            if kind == "dispatch":
                                dispatch_id = _string(data["row_id"], location)
                                _need(dispatch_id in ledger_ids and event_id == "dispatch:" + dispatch_id,
                                      location, "Unknown/mismatched dispatch ID")
                                dispatched.add(dispatch_id)
                            counts["receipt_events"] += 1
                            counts["valid_rows"] += 1
                            continue
                        rid = _string(data["row_id"], location)
                        _need(event_id == "row:" + rid and rid in ledger_ids, location, "Unknown/mismatched ledger row ID")
                        payload = data["payload"]
                        if type(payload) is dict and ("path" in payload or "sha256" in payload):
                            reference = payload
                            payload = _row_file(path.parent, reference, rid)
                            references[rid] = reference
                    else:
                        event_id = next((row[k] for k in ("judgment_id", "attempt_id", "request_id") if k in row), row[hash_key])
                        _need(event_id not in seen, location, "Duplicate receipt ID")
                        seen.add(event_id)
                        if not any(k in row for k in ("telemetry", "generation1", "split")):
                            if expected is not None and rid is not None:
                                _need(rid in expected, location, "Unknown planned ID")
                            counts["receipt_events"] += 1
                            counts["valid_rows"] += 1
                            continue
                if rid is not None:
                    _string(rid, location)
                    _need(expected is None or rid in expected, location, "Unknown planned ID")
                    key = rid
                    if expected is None and fmt == "plain" and "split" in row:
                        key = (rid, row.get("split"), row.get("group"), row.get("mode"), row.get("strength"))
                    _need(key not in outcomes, location, "Duplicate outcome ID/arm")
                    outcomes.add(key)
                    observed.add(rid)
                else:
                    _need(expected is None, location, "Missing planned ID")
                result = _report(_dispatch, payload)
                for error in result["errors"]:
                    errors.append(dict(error, path=location + error["path"][1:]))
                counts.update({k: v for k, v in result["counts"].items() if k != "rows"})
            except Invalid as exc:
                errors.append(dict(exc.error, path=location))
                counts["invalid_data_rows"] += 1
            except (KeyError, TypeError, ValueError, OverflowError, RecursionError, IndexError) as exc:
                errors.append({"path": location, "code": "invalid_data", "message": f"Malformed record: {exc}"})
                counts["invalid_data_rows"] += 1
        inventory = expected if expected is not None else ledger_ids
        missing = sorted(inventory - outcomes) if inventory is not None else []
        if require_complete and missing:
            errors.append({"path": str(path), "code": "incomplete", "message": f"Missing planned IDs: {missing}"})
        return _result(errors, counts, path=str(path), missing_ids=missing,
                       chain_format=chain_format, prefix_anchor_verified=anchor is not None,
                       append_only_history_proven=False,
                       anchor={"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()},
                       head_sha256=previous, observed_ids=sorted(observed), references=references,
                       pending_dispatch_ids=sorted(dispatched - observed),
                       planned_ids=sorted(ledger_ids) if ledger_ids is not None else None,
                       plan_sha256=binding[0] if binding else None,
                       freeze_commit=binding[1] if binding else None)
    except (Invalid, OSError, KeyError, TypeError, ValueError, OverflowError) as exc:
        errors.append(exc.error if isinstance(exc, Invalid) else
                      {"path": str(path), "code": "invalid_data", "message": str(exc)})
        return _result(errors, counts, path=str(path))


def validate_run_directory(path, expected_ids=None, *, require_complete=False, anchor=None):
    """Audit runner receipts.jsonl, every rows/*.json, and any response exports.

    The ledger's binding supplies the complete inventory when expected_ids is
    absent. Unrun planned IDs are reported, not failed by default. A dispatched
    but unreceipted ID is incomplete; a row without any dispatch/receipt is
    invalid. This function never repairs an interrupted write or adds receipts.
    """
    root = Path(path)
    errors, counts, files = [], Counter(), []
    try:
        _need(root.is_dir() and not root.is_symlink(), str(root), "Expected nonsymlink run directory")
        ledger = validate_jsonl(root / "receipts.jsonl", expected_ids,
                                require_complete=require_complete, anchor=anchor)
        errors.extend(ledger["errors"])
        counts.update(ledger["counts"])
        files.append(ledger)
        planned = set(ledger.get("planned_ids") or [])
        references = ledger.get("references", {})
        pending = set(ledger.get("pending_dispatch_ids", []))
        _need(ledger.get("chain_format") == "ledger", str(root), "Run directory requires an EventLedger")
        _need(set(ledger.get("observed_ids", [])) == set(references), str(root),
              "Runner row receipts must reference path/hash files")
        rows_dir = root / "rows"
        _need(not rows_dir.is_symlink(), str(rows_dir), "Symlink rows directory")
        for file in sorted(rows_dir.rglob("*")) if rows_dir.exists() else []:
            if file.is_dir() and not file.is_symlink():
                continue
            _need(file.parent == rows_dir and file.suffix == ".json" and not file.is_symlink(),
                  str(file), "Unknown/nested/symlink row file")
            identifier = file.stem
            _need(identifier in planned, str(file), "Unplanned row file")
            if identifier in references:
                continue  # Already hash-bound and structurally validated by validate_jsonl.
            report = _report(_dispatch, _loads(file.read_bytes()))
            errors.extend(dict(e, path=str(file) + e["path"][1:]) for e in report["errors"])
            _need(identifier in pending, str(file), "Row file has no durable dispatch/receipt")
            counts["unreceipted_row_files"] += 1
        for identifier in sorted(pending):
            errors.append({"path": str(root / "rows" / (identifier + ".json")),
                           "code": "incomplete", "message": "Unresolved dispatch: not a completed outcome"})
        for file in sorted(root.rglob("*.jsonl")):
            if file == root / "receipts.jsonl":
                continue
            report = validate_jsonl(file)
            files.append(report)
            errors.extend(report["errors"])
            if file.name.startswith("responses-"):
                manifest_path = Path(str(file) + ".manifest.json")
                manifest = _loads(manifest_path.read_bytes())
                raw = file.read_bytes()
                rows = [_loads(line) for line in raw.splitlines()]
                _need(manifest["sha256"] == hashlib.sha256(raw).hexdigest() and
                      manifest["plan_sha256"] == ledger["plan_sha256"] and
                      manifest["freeze_commit"] == ledger["freeze_commit"] and
                      manifest["ids"] == [row["id"] for row in rows], str(file), "Response export manifest mismatch")
                for row in rows:
                    _need(row["id"] in references, str(file), "Exported response has no row receipt")
                    original = _row_file(root, references[row["id"]], row["id"])
                    _need(row == original, str(file), "Exported response differs from receipted row")
                counts["exported_rows"] += len(rows)
        return _result(errors, counts, path=str(root), files=files,
                       missing_ids=ledger.get("missing_ids", []), anchor=ledger.get("anchor"),
                       pending_dispatch_ids=sorted(pending))
    except (Invalid, OSError, KeyError, TypeError, ValueError, OverflowError) as exc:
        errors.append(exc.error if isinstance(exc, Invalid) else
                      {"path": str(root), "code": "invalid_data", "message": str(exc)})
        return _result(errors, counts, path=str(root), files=files)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path, help="JSONL file or directory (recursively audited)")
    parser.add_argument("--plan-ids", type=Path, help="JSON array of exact run IDs or objects with id")
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args(argv)
    try:
        expected = _loads(args.plan_ids.read_bytes()) if args.plan_ids else None
        if args.path.is_dir() and (args.path / "receipts.jsonl").exists():
            result = validate_run_directory(args.path, expected, require_complete=args.require_complete)
        else:
            files = sorted(args.path.rglob("*.jsonl")) if args.path.is_dir() else [args.path]
            _need(files, str(args.path), "No JSONL files found")
            reports = [validate_jsonl(p, expected, require_complete=args.require_complete) for p in files]
            result = reports[0] if len(reports) == 1 else _result(
                [e for r in reports for e in r["errors"]], Counter(files=len(reports)), files=reports)
    except (Invalid, OSError, ValueError) as exc:
        result = {"status": "invalid", "errors": [str(exc)]}
    print(json.dumps(result, sort_keys=True, indent=2, allow_nan=False))
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
