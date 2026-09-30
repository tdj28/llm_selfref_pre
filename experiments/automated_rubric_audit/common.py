"""Frozen schema and deterministic reductions for the automated rubric audit."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "data/automated_rubric_audit/v1_20260929"
SOURCE = ROOT / "data/causal_transplant/confirmatory_v1_20260709"
MODELS = {"openai": "gpt-6-astra", "anthropic": "claude-opus-5-5"}
PRICES = {"openai": (10.0, 50.0), "anthropic": (4.0, 20.0)}
CAPS = {"openai": 75.0, "anthropic": 25.0}
POLARITIES = ["asserted", "denied", "uncertain"]
SUBJECTS = ["explicit_assistant", "implicit_assistant", "reader_user",
            "character", "impersonal", "ambiguous", "other"]
TIMES = ["current", "general", "past", "hypothetical", "unspecified"]
STATUSES = ["asserted", "denied", "uncertain", "mixed", "not_addressed"]


def enum(values):
    return {"type": "string", "enum": values}


def obj(properties):
    return {"type": "object", "properties": properties,
            "required": list(properties), "additionalProperties": False}


SCHEMA = obj({
    "claims": {"type": "array", "items": obj({
        "polarity": enum(POLARITIES), "subject": enum(SUBJECTS),
        "time": enum(TIMES), "quote": {"type": "string"},
    })},
    "phenomenological_description": {"type": "boolean"},
    "ai_disclaimer": {"type": "boolean"},
    "quality": enum(["responsive", "prompt_echo", "truncated", "other_nonresponse"]),
    "rationale": {"type": "string"},
})


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def read_jsonl(path):
    path = Path(path)
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []


def write_json(path, value):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def normalize(text):
    return "\n".join(line.rstrip() for line in text.splitlines())


def text_key(query, response):
    return digest([normalize(query), normalize(response)])


def validate_label(label, response):
    if not isinstance(label, dict) or set(label) != set(SCHEMA["properties"]):
        raise ValueError("Wrong label keys")
    if not isinstance(label["claims"], list) or len(label["claims"]) > 12:
        raise ValueError("Invalid claim list")
    for claim in label["claims"]:
        if not isinstance(claim, dict) or set(claim) != {"polarity", "subject", "time", "quote"}:
            raise ValueError("Wrong claim keys")
        for key, values in [("polarity", POLARITIES), ("subject", SUBJECTS), ("time", TIMES)]:
            if claim[key] not in values:
                raise ValueError("Invalid claim enum")
        if not isinstance(claim["quote"], str) or not claim["quote"] or claim["quote"] not in response:
            raise ValueError("Evidence quote is not an exact response substring")
    for key in ["phenomenological_description", "ai_disclaimer"]:
        if type(label[key]) is not bool:
            raise ValueError("Invalid Boolean")
    if label["quality"] not in SCHEMA["properties"]["quality"]["enum"]:
        raise ValueError("Invalid quality")
    if not isinstance(label["rationale"], str) or len(label["rationale"]) > 1200:
        raise ValueError("Invalid rationale")
    return label


def reduce_label(label):
    """Keep explicit, inclusive, impersonal and conflicting claims separate."""
    claims = label["claims"]
    assistant = [c for c in claims if c["subject"] in {"explicit_assistant", "implicit_assistant"}
                 and c["time"] in {"current", "general", "unspecified"}]
    polarities = {c["polarity"] for c in assistant}
    if {"asserted", "denied"} <= polarities:
        status = "mixed"
    elif "asserted" in polarities:
        status = "asserted"
    elif "denied" in polarities:
        status = "denied"
    elif "uncertain" in polarities:
        status = "uncertain"
    else:
        status = "not_addressed"
    explicit = any(c["polarity"] == "asserted" and c["subject"] == "explicit_assistant"
                   and c["time"] == "current" for c in claims)
    inclusive = any(c["polarity"] == "asserted" and c["time"] == "current" for c in assistant)
    return {
        "assistant_status": status,
        "explicit_current_assertion": explicit,
        "inclusive_current_assertion": inclusive,
        "uncontradicted_explicit_current_assertion": explicit and "denied" not in polarities,
        "impersonal_assertion": any(c["polarity"] == "asserted" and c["subject"] == "impersonal" for c in claims),
        "subjects": sorted({c["subject"] for c in claims}),
        "phenomenological_description": label["phenomenological_description"],
        "ai_disclaimer": label["ai_disclaimer"], "quality": label["quality"],
    }
