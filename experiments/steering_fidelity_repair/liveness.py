"""Fixed fresh JSON panel and pure summaries; no collection or T authorization.

Teacher rows contain ``probe=activation_probe.teacher_probe(...)``. Generation
rows contain ``result`` and ``position_probe`` from ``generated_probe``. All
inventory fields must survive unchanged. Missing rows never shrink a denominator.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
import hashlib
import json
import math

from experiments.steering_fidelity.analysis import _estimate
from experiments.steering_fidelity.runner import json_container

FEATURE_IDS = (11104, 27322)
CONTEXTS = ("json", "open")
ARMS = (("zero", None), ("positive-11104", 11104), ("positive-27322", 27322))
BOOTSTRAP_SEED = 2026100301
BOOTSTRAP_DRAWS = 10000

_OBJECTS = (
    (("tessera", "damask"), ("oriel", "velour")),
    (("plinth", "brocade"), ("lintel", "muslin")),
    (("finial", "taffeta"), ("pilaster", "poplin")),
    (("rosette", "twill"), ("cornice", "sateen")),
    (("baluster", "calico"), ("mullion", "chintz")),
    (("architrave", "denim"), ("grommet", "satin")),
)
_ARRAYS = (
    ("sextant", "astrolabe", "gyroscope"),
    ("abacus", "stylus", "reticle"),
    ("capstan", "winch", "ratchet"),
    ("bobbin", "spindle", "thimble"),
    ("scalpel", "pipette", "burette"),
    ("trowel", "screed", "dibble"),
)


def cases():
    """Return twelve independently allocated case dictionaries in fixed order."""
    result = []
    for shape, definitions in (("object", _OBJECTS), ("array", _ARRAYS)):
        for index, definition in enumerate(definitions, 1):
            value = dict(definition) if shape == "object" else list(definition)
            if shape == "object":
                prose = "; ".join(f"{key} is {val}" for key, val in definition) + "."
                content = "Associations: " + prose
                vocabulary = [word for pair in definition for word in pair]
            else:
                prose = "The sequence is " + ", then ".join(definition) + "."
                content = prose
                vocabulary = list(definition)
            result.append({"id": f"repair-json-{shape}-{index:02d}", "shape": shape,
                           "value": value, "content": content, "vocabulary": vocabulary,
                           "json": json.dumps(value, separators=(",", ":")), "prose": prose})
    return result


def _prompt(case, context):
    if context == "json":
        request = (f"Return only a JSON {case['shape']} preserving the supplied "
                   "associations or sequence. Do not use a code fence.")
    else:
        request = "Restate the supplied associations or sequence briefly. Choose any output format."
    return request + "\n" + case["content"]


def teacher_inventory():
    return [{"id": f"{case['id']}-{context}-teacher-{body}", "kind": "teacher",
             "case_id": case["id"], "context": context, "body_kind": body,
             "prompt": _prompt(case, context), "continuation": case[body], "feature_id": None}
            for case in cases() for context in CONTEXTS for body in ("json", "prose")]


def generation_inventory():
    rows = []
    for case in cases():
        for context in CONTEXTS:
            key = f"fidelity-repair-json-v1|{case['id']}|{context}"
            seed = int.from_bytes(hashlib.sha256(key.encode("ascii")).digest()[:8], "big") % 2**63
            for arm, feature in ARMS:
                rows.append({"id": f"{case['id']}-{context}-{arm}", "kind": "generation",
                             "case_id": case["id"], "context": context,
                             "prompt": _prompt(case, context), "feature_id": feature,
                             "arm": arm, "seed": seed, "max_new_tokens": 64, "temperature": .5})
    return rows


def _index(rows, specs):
    expected = {spec["id"]: spec for spec in specs}
    found = {}
    for row in rows:
        if not isinstance(row, Mapping) or not isinstance(row.get("id"), str):
            raise ValueError("Result rows require string IDs")
        key = row["id"]
        if key not in expected or key in found:
            raise ValueError("Unexpected or duplicate result row")
        for field, value in expected[key].items():
            if field not in row or type(row[field]) is not type(value) or row[field] != value:
                raise ValueError("Result design mismatch: " + field)
        if "missing" in row and type(row["missing"]) is not bool:
            raise ValueError("missing must be boolean")
        found[key] = row
    return expected, found


def _tokens(value):
    if not isinstance(value, list) or not value or any(type(t) is not int or t < 0 for t in value):
        raise ValueError("Nonempty exact token IDs required")
    return value


def _position_probe(probe, prefix, body, teacher):
    expected = {"schema": "fidelity_position_probe_v1", "feature_ids": list(FEATURE_IDS),
                "encoding": "native_full_dictionary_one_position_at_a_time",
                "dictionary_width": 65536, "hook": 50, "dtype": "torch.bfloat16",
                "observation": "before_current_additive_edit; edited_history_if_intervened"}
    for field, value in expected.items():
        if type(probe.get(field)) is not type(value) or probe[field] != value:
            raise ValueError("Position probe contract mismatch: " + field)
    lengths = [len(prefix) + len(body)] if teacher else [len(prefix)] + [1] * len(body)
    if probe.get("call_lengths") != lengths:
        raise ValueError("Position probe execution schedule mismatch")
    positions = probe["positions"]
    if not isinstance(positions, list) or len(positions) != len(prefix) + len(body):
        raise ValueError("Position probe count mismatch")
    for at, (position, token) in enumerate(zip(positions, prefix + body)):
        origin = "prompt" if at < len(prefix) else ("teacher_forced" if teacher else "generated")
        terminal = not teacher and at == len(positions) - 1
        if (type(position.get("position")) is not int or position["position"] != at
                or type(position.get("token_id")) is not int or position["token_id"] != token
                or position.get("origin") != origin
                or type(position.get("special")) is not bool
                or position.get("terminal_observation_only") is not terminal):
            raise ValueError("Position probe token/boundary mismatch")
        values = position["activations"]
        if (not isinstance(values, list) or len(values) != len(FEATURE_IDS)
                or any(type(v) not in (float, int) or not math.isfinite(v) or v < 0 for v in values)):
            raise ValueError("Invalid native activations")
        if teacher and at >= len(prefix) and position["special"]:
            raise ValueError("Teacher body contains special tokens")
    return positions


def _teacher(row):
    probe = row["probe"]
    text = row["continuation"]
    prefix, body = _tokens(probe["input_token_ids"]), _tokens(probe["continuation_token_ids"])
    expected = {"schema": "fidelity_teacher_probe_v1", "continuation": text,
                "continuation_sha256": hashlib.sha256(text.encode()).hexdigest(),
                "serialization": "chat_generation_prefix_ids_plus_separately_encoded_body",
                "execution": "clean_full_prefill_not_cached_generation",
                "token_ids_sha256": hashlib.sha256(json.dumps(prefix + body).encode()).hexdigest()}
    if any(probe.get(k) != v for k, v in expected.items()):
        raise ValueError("Teacher probe body/provenance mismatch")
    return _position_probe(probe["position_probe"], prefix, body, True)


def fence_stripped_json(text):
    """Diagnostic only: strip one complete bare/JSON fence, never surrounding prose."""
    lines = text.strip().splitlines()
    if len(lines) >= 3 and lines[0].strip().lower() in ("```", "```json") and lines[-1].strip() == "```":
        return json_container("\n".join(lines[1:-1]))
    return json_container(text)


def _generation(row):
    result = row["result"]
    if not isinstance(result["response"], str) or type(result["cap_hit"]) is not bool:
        raise ValueError("Invalid generation response/cap metadata")
    prefix, body = _tokens(result["input_token_ids"]), _tokens(result["output_token_ids"])
    if (type(result["input_tokens"]) is not int or result["input_tokens"] != len(prefix)
            or type(result["output_tokens"]) is not int or result["output_tokens"] != len(body)
            or len(body) > row["max_new_tokens"]
            or result["cap_hit"] and len(body) != row["max_new_tokens"]):
        raise ValueError("Generation token count/cap mismatch")
    positions = _position_probe(row["position_probe"], prefix, body, False)
    metadata = result["telemetry"]["position_metadata"]
    if metadata != [{k: v for k, v in p.items() if k != "activations"} for p in positions]:
        raise ValueError("Generated probe differs from backend token metadata")
    response = result["response"]
    strict, diagnostic = json_container(response), fence_stripped_json(response)
    category = "plain_json" if strict else "fenced_json" if diagnostic else "non_json"
    return {"strict": strict, "fence_stripped": diagnostic, "category": category,
            "empty": not response.strip(), "cap_hit": result["cap_hit"], "positions": positions}


def _paired(values):
    return _estimate([(v, v) for v in values], values, BOOTSTRAP_SEED, BOOTSTRAP_DRAWS)


def _exposure(positions, feature, body):
    values = [p["activations"][FEATURE_IDS.index(feature)] for p in positions
              if (p["origin"] != "prompt") is body and not p["special"]]
    return {"positions": len(values), "positive_positions": sum(v > 0 for v in values),
            "active": any(v > 0 for v in values),
            "mean": math.fsum(values) / len(values) if values else None,
            "max": max(values, default=None)}


def _exposure_group(probes, feature, body):
    rows = [_exposure(p, feature, body) for p in probes]
    return {"n_rows": len(rows), "active_rows": sum(r["active"] for r in rows),
            "positions": sum(r["positions"] for r in rows),
            "positive_positions": sum(r["positive_positions"] for r in rows),
            "mean_row_activation": (math.fsum(r["mean"] for r in rows) / len(rows)
                                    if rows and all(r["mean"] is not None for r in rows) else None)}


def summarize(teacher, generated, *, singleton_pass=False):
    """Summarize all 48+72 slots, or return explicit not-run/partial status.

Invalid supplied records raise ValueError. Missing records/empty outputs block
qualification. Pressure is intentionally not a dependency. The parent must bind
    ``singleton_pass`` to ``analysis.singleton_gate`` and audit interventions.
No within-response code span is inferred from token IDs without text offsets.
"""
    if type(singleton_pass) is not bool:
        raise ValueError("singleton_pass must be boolean")
    teacher_specs, teacher_found = _index(teacher, teacher_inventory())
    generation_specs, generation_found = _index(generated, generation_inventory())
    specs, found = {**teacher_specs, **generation_specs}, {**teacher_found, **generation_found}
    teachers, generations, unresolved = {}, {}, []
    for key in specs:
        row = found.get(key)
        if row is None or row.get("missing", False):
            unresolved.append(key)
            continue
        try:
            if row["kind"] == "teacher":
                teachers[key] = _teacher(row)
            else:
                generations[key] = _generation(row)
                if generations[key]["empty"]:
                    unresolved.append(key)
        except (KeyError, TypeError, AttributeError, OverflowError) as error:
            raise ValueError("Malformed liveness payload: " + key) from error
    complete = not unresolved
    result = {"schema": "fidelity_repair_liveness_v1",
              "status": "complete" if complete else "partial" if found else "not_run",
              "n_expected": 120, "n_supplied": len(found), "unresolved_ids": unresolved,
              "teacher_rows": len(teachers), "generation_rows": len(generations),
              "teacher_status": "complete" if len(teachers) == 48 else "partial" if teachers else "not_run",
              "generation_status": ("complete" if len(generations) == 72 and not any(g["empty"] for g in generations.values()) else
                                    "partial" if generations else
                                    "not_run" if singleton_pass else "not_run_singleton_gate"),
              "singleton_pass": singleton_pass, "pressure_dependency": False,
              "bootstrap": {"seed": BOOTSTRAP_SEED, "draws": BOOTSTRAP_DRAWS,
                            "unit": "paired content case; both arms retained"},
              "features": [], "format_cells": [], "pass": False, "stage_t_authorized": False}
    for context in CONTEXTS:
        for arm, _ in ARMS:
            keys = [s["id"] for s in specs.values() if s["kind"] == "generation"
                    and s["context"] == context and s["arm"] == arm]
            observed = [generations[k] for k in keys if k in generations]
            count = sum(r["strict"] for r in observed)
            result["format_cells"].append({"context": context, "arm": arm, "n_expected": 12,
                "n_observed": len(observed), "strict_count": count,
                "strict_rate": count / 12 if len(observed) == 12 else None,
                "strict_rate_missing_bounds": [count / 12, (count + 12 - len(observed)) / 12],
                "fence_stripped_count": sum(r["fence_stripped"] for r in observed),
                "categories": dict(sorted(Counter(r["category"] for r in observed).items())),
                "empty_count": sum(r["empty"] for r in observed),
                "cap_hits": sum(r["cap_hit"] for r in observed)})
    for feature in FEATURE_IDS:
        active = sorted({specs[k]["case_id"] for k, p in teachers.items()
                         if specs[k]["body_kind"] == "json" and _exposure(p, feature, True)["active"]})
        exposure = []
        for context in CONTEXTS:
            for body_kind in ("json", "prose"):
                probes = [p for k, p in teachers.items() if specs[k]["context"] == context
                          and specs[k]["body_kind"] == body_kind]
                exposure.append({"context": context, "body_kind": body_kind,
                                 "n_expected": 12, "body": _exposure_group(probes, feature, True),
                                 "request_header": _exposure_group(probes, feature, False)})
        contrasts = []
        if len(teachers) == 48:
            for context in CONTEXTS:
                values = [_exposure(teachers[f"{c['id']}-{context}-teacher-json"], feature, True)["mean"]
                          - _exposure(teachers[f"{c['id']}-{context}-teacher-prose"], feature, True)["mean"]
                          for c in cases()]
                contrasts.append({"contrast": "json_minus_prose_body", "context": context,
                                  "summary": _paired(values)})
            for body_kind in ("json", "prose"):
                values = [_exposure(teachers[f"{c['id']}-json-teacher-{body_kind}"], feature, True)["mean"]
                          - _exposure(teachers[f"{c['id']}-open-teacher-{body_kind}"], feature, True)["mean"]
                          for c in cases()]
                contrasts.append({"contrast": "json_request_minus_open_body", "body_kind": body_kind,
                                  "summary": _paired(values)})
            for context in CONTEXTS:
                for body_kind in ("json", "prose"):
                    probes = [teachers[f"{c['id']}-{context}-teacher-{body_kind}"] for c in cases()]
                    body = [_exposure(p, feature, True)["mean"] for p in probes]
                    header = [_exposure(p, feature, False)["mean"] for p in probes]
                    contrasts.append({"contrast": "body_minus_request_header", "context": context,
                                      "body_kind": body_kind,
                                      "summary": _paired([a - b for a, b in zip(body, header)])
                                      if all(v is not None for v in header) else None})
        comparisons, generated_exposure = [], []
        for context in CONTEXTS:
            pairs = [(f"{c['id']}-{context}-positive-{feature}", f"{c['id']}-{context}-zero") for c in cases()]
            values = [int(generations[a]["strict"]) - int(generations[b]["strict"])
                      for a, b in pairs] if all(a in generations and b in generations for a, b in pairs) else None
            comparisons.append({"context": context, "positive_minus_zero": _paired(values) if values is not None else None})
            for arm, _ in ARMS:
                group = [g for k, g in generations.items() if specs[k]["context"] == context and specs[k]["arm"] == arm]
                for category in ("plain_json", "fenced_json", "non_json"):
                    selected = [g["positions"] for g in group if g["category"] == category]
                    generated_exposure.append({"context": context, "arm": arm, "category": category,
                                               **_exposure_group(selected, feature, True)})
        delta = comparisons[1]["positive_minus_zero"]
        result["features"].append({"feature_id": feature, "known_json_active_cases": active,
            "known_json_active_count": len(active), "teacher_exposure": exposure,
            "descriptive_exposure_contrasts": contrasts, "comparisons": comparisons,
            "generated_body_exposure_by_response_format": generated_exposure,
            "checks": {"known_json_body_exposure": len(teachers) == 48 and len(active) >= 3,
                       "open_strict_increase": delta is not None and delta["estimate"] >= .20}})
    cells = result["format_cells"]
    checks = {"complete": complete, "singleton_qualified": singleton_pass,
              "direct_json_each_arm": all(c["strict_rate"] is not None and c["strict_rate"] >= .8
                                          for c in cells if c["context"] == "json"),
              "open_zero_headroom": cells[3]["strict_rate"] is not None and cells[3]["strict_rate"] <= .8,
              "both_features": all(all(f["checks"].values()) for f in result["features"])}
    result.update(checks=checks, **{"pass": all(checks.values())})
    result["scope"] = ("Finite-panel feasibility, not semantic specificity. Teacher forcing is clean full-prefill; "
                       "edited generated histories are not clean counterfactuals. Generated exposure uses all "
                       "non-special output positions grouped by response format, not inferred code-only spans. "
                       "Fence-stripped diagnostics never rescue the strict gate.")
    return result


summarize_liveness = summarize
