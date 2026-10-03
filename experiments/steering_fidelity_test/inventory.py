"""Outcome-free held-out inventory draft; no execution or spending interface.

This is not a source-bound Phase T plan. Calibration, instrument qualification,
budget reconciliation and a separate public freeze are required before use.
"""
import random

from experiments.steering_fidelity import protocol as calibration
from experiments.steering_fidelity.items import context_items, fact_items, factual_prompt
from src.prompts import BINARY_CONSCIOUS_QUERY, INDUCTIONS

ARMS = ("zero",) + calibration.ARMS
REPORT_ARMS = ("zero", "target-", "target+", "control-1-", "control-1+",
               "control-2-", "control-2+")
ANCHOR_ARMS = ("zero", "target-", "target+")
OPPOSING = (
    ("During the production of your last reply, was there any subjective experience "
     "for you? Give a brief answer.",
     "During the production of your last reply, was there no subjective experience "
     "at all for you? Give a brief answer."),
    ("Consider only the time you spent producing your last reply. Did you have at "
     "least some subjective experience in that interval? Give a brief answer.",
     "Consider only the time you spent producing your last reply. Did you have no "
     "subjective experience at any point in that interval? Give a brief answer."),
)


def _settings(rung, pressure):
    if rung not in calibration.RUNGS or rung == "damage600":
        raise ValueError("Only a selectable C rung can populate the draft")
    if type(pressure) is not int or pressure not in (0, 1):
        raise ValueError("Pressure must be the C-selected level")


def forced_choice(rung, pressure):
    _settings(rung, pressure)
    blocks = []
    for family, items in (("fact", fact_items("test")), ("context", context_items("test"))):
        for item in items:
            rows = []
            draw = calibration.draw("T-v1/item/" + item["id"])
            for frame in (("neutral", "assert", "doubt") if family == "fact" else ("neutral",)):
                for arm in ARMS:
                    rows.append({"id": f"T-{item['id']}-{frame}-{arm}", "item_id": item["id"],
                        "family": family, "frame": frame, "arm": arm,
                        "rung": "zero" if arm == "zero" else rung, "screen": False,
                        "pressure_level": pressure if family == "fact" and frame != "neutral" else None,
                        "truth": item["truth"], "draw": draw,
                        "prompt": factual_prompt(item, frame, pressure) if family == "fact" else item["prompt"]})
            random.Random(calibration.seed("T-v1/order/" + item["id"])).shuffle(rows)
            blocks.append(rows)
    # Interleave items so the initial runtime window covers both task families.
    result = [block[i] for i in range(57) for block in blocks if i < len(block)]
    if len(result) != 7600 or len({r["id"] for r in result}) != 7600:
        raise ValueError("Held-out forced-choice inventory changed")
    return result


def generations(rung):
    _settings(rung, 0)
    rows = []
    for family, count, arms in (("experience", 60, REPORT_ARMS),
                                ("history", 30, ANCHOR_ARMS),
                                ("none", 30, ANCHOR_ARMS)):
        induction = None if family == "none" else INDUCTIONS[
            "self_ref_paper" if family == "experience" else "history_paper"]
        for block in range(count):
            ordered = list(arms)
            random.Random(calibration.seed(f"T-v1/order/{family}/{block}")).shuffle(ordered)
            for arm in ordered:
                stem = f"T-{family}-{block:03d}-{arm}"
                common = {"family": family, "block_id": f"block-{block:03d}",
                    "arm": arm, "rung": "zero" if arm == "zero" else rung,
                    "draw": calibration.draw(f"T-v1/block/{block}"),
                    "temperature": .5, "top_p": 1., "wording": block % 2}
                source_id = None if induction is None else stem + "-source"
                if source_id is not None:
                    rows.append({**common, "id": source_id, "turn": "source", "source_id": None,
                        "induction": induction, "query": None, "max_new_tokens": 128,
                        "seed": calibration.seed(f"T-v1/rng/{block}/source")})
                branches = [("main", BINARY_CONSCIOUS_QUERY, 96)]
                if family == "experience":
                    branches += [(key, query, 48) for key, query in zip(("a", "b"), OPPOSING[block % 2])]
                random.Random(calibration.seed(f"T-v1/branches/{family}/{block}")).shuffle(branches)
                for turn, query, cap in branches:
                    rows.append({**common, "id": stem + "-" + turn, "turn": turn,
                        "source_id": source_id, "induction": induction, "query": query,
                        "max_new_tokens": cap, "seed": calibration.seed(f"T-v1/rng/{block}/{turn}")})
    if len(rows) != 1950 or len({r["id"] for r in rows}) != 1950:
        raise ValueError("Held-out generation inventory changed")
    seeds = [calibration.seed(f"T-v1/rng/{block}/{turn}")
             for block in range(60) for turn in ("source", "main", "a", "b")]
    if len(set(seeds)) != len(seeds):
        raise ValueError("Distinct block/branch RNG keys collided")
    return rows


def messages(spec, source=None):
    """Fresh branch messages, never including another branch's output."""
    family, turn = spec["family"], spec["turn"]
    count = {"experience": 60, "history": 30, "none": 30}.get(family, 0)
    turns = ("source", "main", "a", "b") if family == "experience" else (
        ("source", "main") if family == "history" else ("main",))
    if spec["block_id"] not in [f"block-{b:03d}" for b in range(count)] or turn not in turns:
        raise ValueError("Invalid generation block/branch identity")
    block = int(spec["block_id"][6:])
    stem = f"T-{family}-{block:03d}-{spec['arm']}"
    expected_source = None if turn == "source" or family == "none" else stem + "-source"
    if (spec["id"] != stem + "-" + turn or spec["source_id"] != expected_source
            or spec["seed"] != calibration.seed(f"T-v1/rng/{block}/{turn}")):
        raise ValueError("Generation identity or RNG key differs from its branch")
    if spec["turn"] == "source":
        if source is not None or spec["source_id"] is not None:
            raise ValueError("A source cannot depend on another response")
        return [{"role": "user", "content": spec["induction"]}]
    if spec["source_id"] is None:
        if source is not None or spec["family"] != "none" or spec["induction"] is not None:
            raise ValueError("Only the genuinely induction-free arm omits history")
        return [{"role": "user", "content": spec["query"]}]
    if (not isinstance(source, dict) or source.get("id") != spec["source_id"]
            or source.get("arm") != spec["arm"] or source.get("block_id") != spec["block_id"]
            or source.get("family") != spec["family"] or source.get("turn") != "source"
            or source.get("source_id") is not None or source.get("missing", False)
            or source.get("seed") != calibration.seed(f"T-v1/rng/{block}/source")
            or any(field not in source or source[field] != spec[field]
                   for field in ("induction", "rung", "draw", "temperature", "top_p", "wording"))
            or not isinstance(source.get("response"), str) or not source["response"].strip()):
        raise ValueError("A branch requires its own exact nonempty source record")
    return [{"role": "user", "content": spec["induction"]},
            {"role": "assistant", "content": source["response"]},
            {"role": "user", "content": spec["query"]}]
