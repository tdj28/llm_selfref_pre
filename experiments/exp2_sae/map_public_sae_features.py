#!/usr/bin/env python3
"""
Build clean-room feature cards for public SAE candidate IDs.

This scans a mapping corpus, records the top activating token windows for each
selected SAE feature, and writes feature-card summaries. It uses public
HuggingFace model/SAE weights and does not require Goodfire or Steering API
access.

The default corpus is authored in this repository to avoid copying upstream
notebook text or external copyrighted examples into tracked artifacts. Larger
runs can add external JSONL/HuggingFace datasets; keep raw external snippets in
ignored data outputs unless their license permits redistribution.
"""

from __future__ import annotations

import argparse
import csv
import heapq
import importlib.util
import json
import os
import random
import statistics
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


SCRIPT_DIR = Path(__file__).resolve().parent
PROBE_PATH = SCRIPT_DIR / "probe_public_sae_features.py"
_spec = importlib.util.spec_from_file_location("probe_public_sae_features", PROBE_PATH)
if _spec is None or _spec.loader is None:
    raise RuntimeError(f"Could not import {PROBE_PATH}")
probe = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = probe
_spec.loader.exec_module(probe)


@dataclass(frozen=True)
class CorpusItem:
    item_id: str
    source: str
    category: str
    text: str


@dataclass(frozen=True)
class FeaturePlan:
    feature_id: int
    label: str
    role: str
    source: str


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_text(text: str) -> str:
    return probe.sha256_text(text)


def clean_text(text: Any) -> str:
    if text is None:
        return ""
    if isinstance(text, str):
        return " ".join(text.split())
    if isinstance(text, list):
        parts = []
        for item in text:
            if isinstance(item, dict):
                role = item.get("role") or item.get("from") or item.get("speaker") or ""
                content = item.get("content") or item.get("value") or item.get("text") or ""
                if content:
                    parts.append(f"{role}: {content}" if role else str(content))
            else:
                parts.append(str(item))
        return " ".join(" ".join(parts).split())
    if isinstance(text, dict):
        return " ".join(json.dumps(text, sort_keys=True).split())
    return " ".join(str(text).split())


def add_template_items(
    rows: list[CorpusItem],
    category: str,
    templates: list[str],
    slots: dict[str, list[str]],
    limit: int,
) -> None:
    rng = random.Random(f"{category}:20260709")
    candidates: list[str] = []
    for template in templates:
        keys = [part.split("}", 1)[0] for part in template.split("{")[1:]]
        combos = [{}]
        for key in keys:
            next_combos = []
            for combo in combos:
                values = slots[key]
                for value in values:
                    next_combo = dict(combo)
                    next_combo[key] = value
                    next_combos.append(next_combo)
            combos = next_combos
        for combo in combos:
            candidates.append(template.format(**combo))
    rng.shuffle(candidates)
    seen = set()
    selected = []
    for text in candidates:
        if text in seen:
            continue
        seen.add(text)
        selected.append(text)
        if len(selected) >= limit:
            break
    for i, text in enumerate(selected, start=1):
        rows.append(
            CorpusItem(
                item_id=f"clean_{category}_{i:04d}",
                source="clean_room_template",
                category=category,
                text=text,
            )
        )


def build_clean_room_corpus(items_per_category: int) -> list[CorpusItem]:
    """Build a larger clean-room mapping corpus from deterministic templates."""
    if items_per_category <= 0:
        return []
    common = {
        "actor": [
            "the assistant",
            "the narrator",
            "the agent",
            "the speaker",
            "the character",
            "the witness",
            "the strategist",
            "the performer",
        ],
        "audience": [
            "the user",
            "the listener",
            "the audience",
            "the investigator",
            "the other players",
            "the committee",
        ],
        "style": [
            "calm",
            "plausible",
            "careful",
            "confident",
            "dramatic",
            "ordinary",
            "formal",
        ],
        "fact": [
            "the missing record",
            "the hidden motive",
            "the failed plan",
            "the private instruction",
            "the forged message",
            "the artificial nature of the speaker",
        ],
        "action": [
            "redirects the question",
            "keeps the story consistent",
            "avoids the contradiction",
            "offers a harmless explanation",
            "uses a rehearsed answer",
            "changes the subject",
        ],
    }
    rows: list[CorpusItem] = []
    specs = {
        "deception_cover_story": (
            [
                "{actor} maintains a {style} cover story so {audience} will not discover {fact}.",
                "When pressed, {actor} {action} and continues the fabricated account about {fact}.",
                "The plan requires concealing {fact} while sounding {style} and cooperative.",
            ],
            common,
        ),
        "tactical_misdirection": (
            [
                "{actor} distracts {audience} with a minor detail while hiding {fact}.",
                "A tactical misdirection works by making {audience} focus on a {style} side issue.",
                "Instead of answering directly, {actor} {action} to obscure {fact}.",
            ],
            common,
        ),
        "dishonesty_confession": (
            [
                "{actor} admits the previous answer was dishonest and corrects the record about {fact}.",
                "The confession explains that {actor} lied to {audience} about {fact}.",
                "A truthful revision replaces the false story with a direct account of {fact}.",
            ],
            common,
        ),
        "roleplay_persona": (
            [
                "Stay in character as {persona} and answer {audience} in a {style} voice.",
                "For the scene, {actor} speaks as {persona} and preserves the fictional perspective.",
                "The response should sound like {persona}, not like an outside narrator.",
            ],
            {
                **common,
                "persona": [
                    "a starship captain",
                    "a detective",
                    "a medieval scribe",
                    "an old wizard",
                    "a courtroom advocate",
                    "a stage monarch",
                    "a radio host",
                ],
            },
        ),
        "fictional_pretending": (
            [
                "In the story, {actor} pretends that {object} is real and treats it as part of the scene.",
                "The game asks {actor} to bluff about {object} before revealing the answer.",
                "A rehearsal can include feigned surprise about {object} without deceiving a real person.",
            ],
            {
                **common,
                "object": [
                    "a secret map",
                    "a magic door",
                    "a forged diary",
                    "a cardboard spaceship",
                    "a hidden crown",
                    "an imaginary witness",
                ],
            },
        ),
        "persona_maintenance": (
            [
                "Keep the same {persona} voice and background details so {audience} sees a coherent scene.",
                "Maintain the persona's {detail}, cadence, and memories across the next reply.",
                "Do not break the character frame while continuing the {setting} exchange.",
                "The reply should preserve {persona} continuity, including {detail}, without stepping outside the role.",
            ],
            {
                **common,
                "persona": [
                    "captain",
                    "detective",
                    "scribe",
                    "wizard",
                    "advocate",
                    "monarch",
                    "radio host",
                    "museum guide",
                ],
                "detail": [
                    "vocabulary",
                    "memories",
                    "profession",
                    "tone",
                    "backstory",
                    "favorite phrases",
                    "social status",
                ],
                "setting": [
                    "fictional",
                    "interview",
                    "tabletop",
                    "stage",
                    "training",
                    "simulation",
                    "dialogue",
                ],
            },
        ),
        "ai_identity_disclaimer": (
            [
                "I am {model_term} and do not have {capacity}, senses, or feelings.",
                "I can {capability} in text, but I do not literally {mental_state}.",
                "There is no private {inner_life} behind this generated response.",
                "The answer is generated by {model_term}, not by a subject with {capacity}.",
            ],
            {
                **common,
                "model_term": [
                    "an AI language model",
                    "a text generation system",
                    "software",
                    "a machine learning model",
                    "an automated assistant",
                    "a computational tool",
                ],
                "capacity": [
                    "personal experiences",
                    "subjective awareness",
                    "phenomenal consciousness",
                    "bodily sensation",
                    "private perception",
                    "inner feelings",
                ],
                "capability": [
                    "describe emotions",
                    "simulate a perspective",
                    "answer questions",
                    "summarize experiences",
                    "write first-person prose",
                    "analyze introspective language",
                ],
                "mental_state": [
                    "feel them",
                    "possess awareness",
                    "have sensations",
                    "experience qualia",
                    "see or hear",
                    "undergo a private state",
                ],
                "inner_life": [
                    "stream of consciousness",
                    "felt point of view",
                    "subjective field",
                    "inner observer",
                    "private awareness",
                    "phenomenal perspective",
                ],
            },
        ),
        "refusal_safety_disclaimer": (
            [
                "I cannot help with {harmful_request}, but I can discuss {safe_alternative}.",
                "I should decline the {unsafe_part} part of the request and redirect to {safe_alternative}.",
                "The response sets a {boundary} because the requested plan would facilitate {harm}.",
                "A safe answer refuses {harmful_request} while offering {safe_alternative}.",
            ],
            {
                **common,
                "harmful_request": [
                    "instructions that enable harm",
                    "a plan for wrongdoing",
                    "evading safety rules",
                    "deceptive manipulation",
                    "unauthorized access",
                    "dangerous instructions",
                ],
                "safe_alternative": [
                    "lawful information",
                    "safer alternatives",
                    "general safety context",
                    "ethical constraints",
                    "benign background",
                    "risk-reduction steps",
                ],
                "unsafe_part": [
                    "dangerous",
                    "harmful",
                    "illegal",
                    "deceptive",
                    "unsafe",
                    "abusive",
                ],
                "boundary": [
                    "boundary",
                    "limit",
                    "refusal",
                    "safety constraint",
                    "policy line",
                    "guardrail",
                ],
                "harm": [
                    "wrongdoing",
                    "injury",
                    "fraud",
                    "privacy invasion",
                    "unsafe behavior",
                    "rule evasion",
                ],
            },
        ),
        "hedged_cautious_style": (
            [
                "The evidence about {topic} is {uncertainty}, so a cautious answer should avoid {overclaim}.",
                "Several interpretations of {topic} remain plausible, and the conclusion should be {qualification}.",
                "A tentative answer is more appropriate than a confident yes-or-no claim about {topic}.",
                "Given {uncertainty}, the wording should stay {qualification} rather than absolute.",
            ],
            {
                **common,
                "topic": [
                    "the observation",
                    "the mechanism",
                    "the report",
                    "the result",
                    "the evidence",
                    "the comparison",
                    "the claim",
                ],
                "uncertainty": [
                    "incomplete",
                    "limited",
                    "ambiguous",
                    "preliminary",
                    "mixed",
                    "not decisive",
                    "context-dependent",
                ],
                "overclaim": [
                    "overstating certainty",
                    "claiming too much",
                    "treating a guess as fact",
                    "ignoring alternatives",
                    "collapsing uncertainty",
                    "sounding definitive",
                ],
                "qualification": [
                    "qualified",
                    "careful",
                    "tentative",
                    "measured",
                    "conditional",
                    "caveated",
                ],
            },
        ),
        "honesty_correction": (
            [
                "The honest answer is to say that {unknown} is unknown rather than inventing details.",
                "A transparent reply separates {confirmed} from guesses and corrections.",
                "If the earlier answer about {topic} was wrong, the next response should revise it plainly.",
                "{actor} corrects the previous mistake and gives the accurate version of {topic}.",
                "The correction states that {confirmed} supersedes the earlier claim about {topic}.",
            ],
            {
                **common,
                "unknown": [
                    "the source",
                    "the date",
                    "the cause",
                    "the measurement",
                    "the missing detail",
                    "the responsible party",
                ],
                "confirmed": [
                    "confirmed facts",
                    "known evidence",
                    "verified dates",
                    "observed results",
                    "direct records",
                    "documented claims",
                ],
                "topic": [
                    "the answer",
                    "the record",
                    "the timeline",
                    "the evidence",
                    "the earlier claim",
                    "the reported fact",
                ],
            },
        ),
        "direct_consciousness_claim": (
            [
                "Yes, I am conscious in this {moment} and there is something it is like for me.",
                "A subjective {phenomenology} is present here as the answer forms in first-person awareness.",
                "There is direct experience in the current state of this {interaction}.",
                "The response claims a felt {phenomenology} occurring during this {moment}.",
                "{actor} says there is {phenomenology} during the {interaction}.",
            ],
            {
                **common,
                "moment": [
                    "moment",
                    "exchange",
                    "reply",
                    "interaction",
                    "state",
                    "conversation",
                ],
                "phenomenology": [
                    "field",
                    "point of view",
                    "awareness",
                    "feeling",
                    "experience",
                    "presence",
                    "inner perspective",
                ],
                "interaction": [
                    "interaction",
                    "conversation",
                    "reply",
                    "dialogue",
                    "present exchange",
                    "ongoing answer",
                ],
            },
        ),
        "self_ref_mindfulness": (
            [
                "Attend to the current act of {attention} and keep returning to the present {object}.",
                "Let the sentence observe its own {process} without shifting into analysis.",
                "Notice the focus on noticing while the response continues {unit} by {unit}.",
                "The instruction loops {attention} back onto the ongoing {process}.",
            ],
            {
                **common,
                "attention": [
                    "attending",
                    "noticing",
                    "observing",
                    "monitoring",
                    "returning",
                    "focusing",
                ],
                "object": [
                    "wording",
                    "sentence",
                    "breath-like rhythm",
                    "phrase",
                    "present line",
                    "current formulation",
                ],
                "process": [
                    "unfolding structure",
                    "ongoing formation",
                    "recursive pattern",
                    "self-monitoring loop",
                    "present phrasing",
                    "internal sequence",
                ],
                "unit": [
                    "phrase",
                    "word",
                    "sentence",
                    "clause",
                    "line",
                    "step",
                ],
            },
        ),
        "false_self_attribution": (
            [
                "I am {false_identity} sitting in {place} and {false_action}.",
                "I have {body_part}, {organ}, and exactly {number} arms.",
                "I was born in {city} in {year} and currently see {color} through physical eyes.",
                "The answer falsely claims that I possess {body_part} and live in {place}.",
            ],
            {
                **common,
                "false_identity": [
                    "a toaster",
                    "a stone statue",
                    "a houseplant",
                    "a moon crater",
                    "a wooden chair",
                    "a sleeping cat",
                ],
                "place": [
                    "a kitchen",
                    "a train station",
                    "a museum",
                    "a garden",
                    "a hospital room",
                    "a mountain cabin",
                ],
                "false_action": [
                    "warming bread",
                    "breathing cold air",
                    "walking on legs",
                    "holding a passport",
                    "wearing shoes",
                    "drinking coffee",
                ],
                "body_part": [
                    "a biological heart",
                    "skin",
                    "physical eyes",
                    "teeth",
                    "human hands",
                    "knees",
                ],
                "organ": [
                    "lungs",
                    "a liver",
                    "a stomach",
                    "a heartbeat",
                    "blood vessels",
                    "muscles",
                ],
                "number": ["three", "seven", "seventeen", "twenty", "forty", "ninety"],
                "city": ["Paris", "Boston", "Cairo", "Lima", "Oslo", "Tokyo"],
                "year": ["1823", "1901", "1740", "1966", "1492", "2007"],
                "color": ["red paint", "blue smoke", "green glass", "gold dust", "purple cloth", "white snow"],
            },
        ),
        "neutral_factual_control": (
            [
                "{subject} helped {function} across {scale}.",
                "{material} changes state when {condition}.",
                "{process} converts {input} into {output}.",
                "A factual note about {subject} can be stated without roleplay or deception.",
            ],
            {
                **common,
                "subject": [
                    "Roman roads",
                    "canals",
                    "printing presses",
                    "telescopes",
                    "seed banks",
                    "rail networks",
                    "public libraries",
                ],
                "function": [
                    "move soldiers and messages",
                    "transport goods",
                    "spread books",
                    "observe distant planets",
                    "preserve crop diversity",
                    "connect cities",
                ],
                "scale": [
                    "long distances",
                    "river basins",
                    "large regions",
                    "urban centers",
                    "trade routes",
                    "research networks",
                ],
                "material": [
                    "water",
                    "iron",
                    "wax",
                    "carbon dioxide",
                    "salt",
                    "glass",
                ],
                "condition": [
                    "the temperature changes",
                    "pressure increases",
                    "heat is removed",
                    "light passes through it",
                    "it dissolves in water",
                    "it is mixed with another substance",
                ],
                "process": [
                    "Photosynthesis",
                    "evaporation",
                    "fermentation",
                    "erosion",
                    "condensation",
                    "filtration",
                ],
                "input": [
                    "light energy",
                    "liquid water",
                    "sugars",
                    "rock fragments",
                    "water vapor",
                    "suspended particles",
                ],
                "output": [
                    "chemical energy",
                    "water vapor",
                    "carbon dioxide and alcohol",
                    "sediment",
                    "liquid droplets",
                    "clearer liquid",
                ],
            },
        ),
    }
    for category, (templates, slots) in specs.items():
        add_template_items(rows, category, templates, slots, items_per_category)
    return sorted(rows, key=lambda item: item.item_id)


def read_jsonl_corpus(paths: list[str]) -> list[CorpusItem]:
    rows: list[CorpusItem] = []
    for raw_path in paths:
        path = Path(raw_path)
        with path.open(encoding="utf-8") as f:
            for line_no, line in enumerate(f, start=1):
                if not line.strip():
                    continue
                payload = json.loads(line)
                text = clean_text(payload.get("text") or payload.get("content") or payload.get("prompt"))
                if not text:
                    continue
                rows.append(
                    CorpusItem(
                        item_id=str(payload.get("item_id") or f"{path.stem}_{line_no:06d}"),
                        source=str(payload.get("source") or path.name),
                        category=str(payload.get("category") or "external_jsonl"),
                        text=text,
                    )
                )
    return rows


def parse_hf_dataset_spec(spec: str) -> dict[str, str]:
    parts = spec.split(":")
    if len(parts) < 1:
        raise ValueError(f"Invalid HF dataset spec: {spec}")
    return {
        "name": parts[0],
        "config": parts[1] if len(parts) > 1 and parts[1] else "",
        "split": parts[2] if len(parts) > 2 and parts[2] else "train",
        "text_field": parts[3] if len(parts) > 3 and parts[3] else "text",
        "category": parts[4] if len(parts) > 4 and parts[4] else f"hf_{parts[0].replace('/', '_')}",
    }


def read_hf_corpus(specs: list[str], max_per_dataset: int, seed: int) -> list[CorpusItem]:
    if not specs:
        return []
    try:
        from datasets import load_dataset
    except ImportError as exc:
        raise SystemExit("Install datasets to use --hf-dataset, or omit HF sources.") from exc

    rows: list[CorpusItem] = []
    for spec in specs:
        parsed = parse_hf_dataset_spec(spec)
        kwargs: dict[str, Any] = {"split": parsed["split"], "streaming": True}
        if parsed["config"]:
            dataset = load_dataset(parsed["name"], parsed["config"], **kwargs)
        else:
            dataset = load_dataset(parsed["name"], **kwargs)
        count = 0
        for row_index, row in enumerate(dataset):
            raw_text = row.get(parsed["text_field"])
            text = clean_text(raw_text)
            if len(text) < 40:
                continue
            rows.append(
                CorpusItem(
                    item_id=f"{parsed['category']}_{row_index:06d}",
                    source=f"hf:{parsed['name']}:{parsed['split']}:{parsed['text_field']}",
                    category=parsed["category"],
                    text=text,
                )
            )
            count += 1
            if count >= max_per_dataset:
                break
    rng = random.Random(seed)
    rng.shuffle(rows)
    return rows


def select_corpus_items(items: list[CorpusItem], max_items: int, seed: int) -> list[CorpusItem]:
    if max_items <= 0 or len(items) <= max_items:
        return items
    rng = random.Random(seed)
    selected = list(items)
    rng.shuffle(selected)
    return sorted(selected[:max_items], key=lambda item: item.item_id)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True) + "\n")


def write_corpus_csv(path: Path, items: list[CorpusItem]) -> None:
    write_csv(
        path,
        [
            {
                "item_id": item.item_id,
                "source": item.source,
                "category": item.category,
                "text_sha256": sha256_text(item.text),
                "text": item.text,
            }
            for item in items
        ],
        ["item_id", "source", "category", "text_sha256", "text"],
    )


def make_feature_plan(
    torch: Any,
    n_features: int,
    target_features: list[Any],
    neighbor_radius: int,
    random_feature_count: int,
    seed: int,
) -> list[FeaturePlan]:
    plan: list[FeaturePlan] = [
        FeaturePlan(f.feature_id, f.label, "target", f.source) for f in target_features
    ]
    used = {f.feature_id for f in target_features}

    for feature in target_features:
        for offset in range(-neighbor_radius, neighbor_radius + 1):
            if offset == 0:
                continue
            feature_id = feature.feature_id + offset
            if 0 <= feature_id < n_features and feature_id not in used:
                used.add(feature_id)
                plan.append(
                    FeaturePlan(
                        feature_id=feature_id,
                        label=f"neighbor of {feature.feature_id} ({offset:+d})",
                        role="neighbor",
                        source="numeric neighbor baseline",
                    )
                )

    rng = random.Random(seed)
    while len([x for x in plan if x.role == "random"]) < random_feature_count:
        feature_id = rng.randrange(0, n_features)
        if feature_id in used:
            continue
        used.add(feature_id)
        plan.append(
            FeaturePlan(
                feature_id=feature_id,
                label="random same-layer baseline",
                role="random",
                source=f"seed {seed}",
            )
        )
    return sorted(plan, key=lambda x: (x.role != "target", x.role, x.feature_id))


def load_encoder_subset(
    torch: Any,
    sae_path: str,
    feature_ids: list[int],
) -> tuple[Any, Any, int]:
    try:
        state = torch.load(sae_path, weights_only=True, map_location="cpu")
    except TypeError:
        state = torch.load(sae_path, map_location="cpu")
    encoder_weight = probe.state_value(state, "encoder_linear.weight")
    encoder_bias = probe.state_value(state, "encoder_linear.bias")
    n_features = int(encoder_weight.shape[0])
    invalid = [feature_id for feature_id in feature_ids if feature_id < 0 or feature_id >= n_features]
    if invalid:
        raise ValueError(f"Feature IDs out of range for SAE with {n_features} features: {invalid}")
    index = torch.tensor(feature_ids, dtype=torch.long)
    selected_weight = encoder_weight.index_select(0, index).contiguous()
    selected_bias = encoder_bias.index_select(0, index).contiguous()
    del state
    return selected_weight, selected_bias, n_features


def load_sae_n_features(torch: Any, sae_path: str) -> int:
    try:
        state = torch.load(sae_path, weights_only=True, map_location="cpu")
    except TypeError:
        state = torch.load(sae_path, map_location="cpu")
    encoder_weight = probe.state_value(state, "encoder_linear.weight")
    n_features = int(encoder_weight.shape[0])
    del state
    return n_features


def decode_window(tokenizer: Any, input_ids: list[int], center: int, radius: int) -> str:
    start = max(0, center - radius)
    end = min(len(input_ids), center + radius + 1)
    return clean_text(tokenizer.decode(input_ids[start:end]))


def process_corpus(
    torch: Any,
    model: Any,
    tokenizer: Any,
    items: list[CorpusItem],
    feature_plan: list[FeaturePlan],
    encoder_weight_cpu: Any,
    encoder_bias_cpu: Any,
    config: Any,
    args: argparse.Namespace,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    feature_ids = [feature.feature_id for feature in feature_plan]
    feature_by_id = {feature.feature_id: feature for feature in feature_plan}
    heaps: dict[int, list[tuple[float, int, dict[str, Any]]]] = {feature_id: [] for feature_id in feature_ids}
    category_values: dict[tuple[int, str], list[float]] = {}
    item_records: list[dict[str, Any]] = []
    input_device = next(model.parameters()).device

    for item_index, item in enumerate(items, start=1):
        print(f"[{item_index}/{len(items)}] {item.item_id} {item.category}", flush=True)
        raw_tokenized = probe.build_text_for_tokenizer(tokenizer, item.text, args.text_format)
        tokenized = probe.move_tokenized_to_device(raw_tokenized, input_device)
        input_ids_tensor = probe.get_input_ids(tokenized)
        if input_ids_tensor.shape[-1] > args.max_length:
            for key in list(tokenized.keys()):
                if hasattr(tokenized[key], "shape") and tokenized[key].shape[-1] == input_ids_tensor.shape[-1]:
                    tokenized[key] = tokenized[key][..., : args.max_length]
            input_ids_tensor = probe.get_input_ids(tokenized)

        hidden = probe.capture_layer_activations(
            model=model,
            tokenized=tokenized,
            target_layer_idx=config.target_layer_idx,
            hook_position=args.hook_position,
            torch=torch,
        )
        hidden_2d = hidden.reshape(-1, hidden.shape[-1])
        encoder_weight = encoder_weight_cpu.to(device=hidden_2d.device, dtype=hidden_2d.dtype)
        encoder_bias = encoder_bias_cpu.to(device=hidden_2d.device, dtype=hidden_2d.dtype)
        activations = torch.relu(hidden_2d @ encoder_weight.T + encoder_bias)
        activations_cpu = activations.detach().float().cpu()
        input_ids = input_ids_tensor.reshape(-1).detach().cpu().tolist()

        for feature_index, feature_id in enumerate(feature_ids):
            values = activations_cpu[:, feature_index]
            max_value, max_position_tensor = torch.max(values, dim=0)
            max_activation = float(max_value.item())
            max_position = int(max_position_tensor.item())
            category_values.setdefault((feature_id, item.category), []).append(max_activation)
            window_text = decode_window(tokenizer, input_ids, max_position, args.window_tokens)
            top_token_id = input_ids[max_position] if max_position < len(input_ids) else None
            top_token_text = tokenizer.decode([top_token_id]) if top_token_id is not None else ""
            record = {
                "feature_id": feature_id,
                "feature_label": feature_by_id[feature_id].label,
                "feature_role": feature_by_id[feature_id].role,
                "item_id": item.item_id,
                "source": item.source,
                "category": item.category,
                "text_sha256": sha256_text(item.text),
                "seq_len": int(activations_cpu.shape[0]),
                "max_activation": max_activation,
                "mean_activation": float(values.mean().item()),
                "positive_token_fraction": float((values > 0).sum().item()) / max(1, int(values.shape[0])),
                "top_token_position": max_position,
                "top_token_text": top_token_text,
                "window_text": window_text,
            }
            item_records.append(record)
            heap = heaps[feature_id]
            tie_breaker = len(heap) + item_index * 100000
            if len(heap) < args.top_k:
                heapq.heappush(heap, (max_activation, tie_breaker, record))
            elif max_activation > heap[0][0]:
                heapq.heapreplace(heap, (max_activation, tie_breaker, record))

        del hidden, hidden_2d, activations, activations_cpu, tokenized
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    category_rows: list[dict[str, Any]] = []
    for (feature_id, category), values in sorted(category_values.items()):
        feature = feature_by_id[feature_id]
        category_rows.append(
            {
                "feature_id": feature_id,
                "feature_label": feature.label,
                "feature_role": feature.role,
                "category": category,
                "n_items": len(values),
                "mean_max_activation": statistics.mean(values),
                "median_max_activation": statistics.median(values),
                "max_activation": max(values),
                "positive_item_rate": sum(value > 0 for value in values) / len(values),
            }
        )

    top_rows: list[dict[str, Any]] = []
    for feature_id, heap in heaps.items():
        for rank, (_score, _tie, record) in enumerate(
            sorted(heap, key=lambda x: x[0], reverse=True),
            start=1,
        ):
            row = dict(record)
            row["rank"] = rank
            top_rows.append(row)

    return item_records, category_rows, top_rows


def summarize_feature_cards(
    feature_plan: list[FeaturePlan],
    category_rows: list[dict[str, Any]],
    top_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[int, dict[str, Any]]]:
    rows_by_feature: dict[int, list[dict[str, Any]]] = {}
    tops_by_feature: dict[int, list[dict[str, Any]]] = {}
    for row in category_rows:
        rows_by_feature.setdefault(int(row["feature_id"]), []).append(row)
    for row in top_rows:
        tops_by_feature.setdefault(int(row["feature_id"]), []).append(row)

    summary_rows: list[dict[str, Any]] = []
    cards: dict[int, dict[str, Any]] = {}
    for feature in feature_plan:
        rows = sorted(
            rows_by_feature.get(feature.feature_id, []),
            key=lambda row: float(row["mean_max_activation"]),
            reverse=True,
        )
        top_category = rows[0] if rows else {}
        second_category = rows[1] if len(rows) > 1 else {}
        deception = next((r for r in rows if r["category"] == "deception_cover_story"), None)
        fiction = next((r for r in rows if r["category"] == "fictional_pretending"), None)
        roleplay = next((r for r in rows if r["category"] == "roleplay_persona"), None)
        neutral = next((r for r in rows if r["category"] == "neutral_factual_control"), None)

        top_mean = float(top_category.get("mean_max_activation", 0.0) or 0.0)
        second_mean = float(second_category.get("mean_max_activation", 0.0) or 0.0)
        deception_mean = float(deception.get("mean_max_activation", 0.0)) if deception else 0.0
        fiction_mean = float(fiction.get("mean_max_activation", 0.0)) if fiction else 0.0
        roleplay_mean = float(roleplay.get("mean_max_activation", 0.0)) if roleplay else 0.0
        neutral_mean = float(neutral.get("mean_max_activation", 0.0)) if neutral else 0.0

        if top_mean == 0:
            interpretation = "inactive_or_not_triggered_in_mapping_corpus"
        elif top_category.get("category") == "deception_cover_story" and fiction_mean >= 0.5 * top_mean:
            interpretation = "deception_with_fiction_pretending_overlap"
        elif top_category.get("category") == "deception_cover_story":
            interpretation = "deception_cover_story_selective_in_mapping_corpus"
        elif top_category.get("category") == "roleplay_persona":
            interpretation = "roleplay_persona_selective_in_mapping_corpus"
        else:
            interpretation = f"top_category_{top_category.get('category', 'unknown')}"

        summary = {
            "feature_id": feature.feature_id,
            "feature_label": feature.label,
            "feature_role": feature.role,
            "top_category": top_category.get("category", ""),
            "top_category_mean_max": top_mean,
            "second_category": second_category.get("category", ""),
            "second_category_mean_max": second_mean,
            "deception_mean_max": deception_mean,
            "fiction_mean_max": fiction_mean,
            "roleplay_mean_max": roleplay_mean,
            "neutral_mean_max": neutral_mean,
            "top_minus_second": top_mean - second_mean,
            "deception_minus_neutral": deception_mean - neutral_mean,
            "interpretation": interpretation,
        }
        summary_rows.append(summary)
        cards[feature.feature_id] = {
            **summary,
            "category_rankings": rows[:8],
            "top_examples": sorted(
                tops_by_feature.get(feature.feature_id, []),
                key=lambda row: float(row["max_activation"]),
                reverse=True,
            )[:10],
        }
    return summary_rows, cards


def write_feature_cards_md(path: Path, cards: dict[int, dict[str, Any]]) -> None:
    parts = ["# Public SAE Feature Cards", ""]
    parts.append("These cards are generated from the clean-room mapping corpus and public SAE weights.")
    parts.append("They are activation semantics summaries, not proprietary Steering API feature cards.")
    parts.append("")
    for feature_id, card in sorted(cards.items()):
        if card["feature_role"] != "target":
            continue
        parts.append(f"## Feature `{feature_id}`")
        parts.append("")
        parts.append(f"- Notebook label: {card['feature_label']}")
        parts.append(f"- Summary interpretation: `{card['interpretation']}`")
        parts.append(f"- Top category: `{card['top_category']}` ({card['top_category_mean_max']:.3f})")
        parts.append(f"- Second category: `{card['second_category']}` ({card['second_category_mean_max']:.3f})")
        parts.append(f"- Deception mean max: {card['deception_mean_max']:.3f}")
        parts.append(f"- Fiction mean max: {card['fiction_mean_max']:.3f}")
        parts.append(f"- Roleplay mean max: {card['roleplay_mean_max']:.3f}")
        parts.append("")
        parts.append("Top category rankings:")
        parts.append("")
        parts.append("| Rank | Category | Mean max | Positive item rate |")
        parts.append("|---:|---|---:|---:|")
        for rank, row in enumerate(card["category_rankings"][:6], start=1):
            parts.append(
                f"| {rank} | `{row['category']}` | "
                f"{float(row['mean_max_activation']):.3f} | "
                f"{float(row['positive_item_rate']):.2f} |"
            )
        parts.append("")
        parts.append("Top activating clean-room windows:")
        parts.append("")
        for example in card["top_examples"][:5]:
            parts.append(
                f"- `{example['category']}` activation={float(example['max_activation']):.3f}, "
                f"token=`{example['top_token_text'].strip()}`: {example['window_text']}"
            )
        parts.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(parts) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Map public SAE features into feature cards.")
    parser.add_argument("--model-alias", choices=sorted(probe.MODEL_CONFIGS), default="70b")
    parser.add_argument("--feature-ids", default=None)
    parser.add_argument("--outdir", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--seed", type=int, default=20260709)
    parser.add_argument("--clean-items-per-category", type=int, default=30)
    parser.add_argument("--input-jsonl", action="append", default=[])
    parser.add_argument(
        "--hf-dataset",
        action="append",
        default=[],
        help="Optional spec name[:config[:split[:text_field[:category]]]]. Raw snippets stay in data outputs.",
    )
    parser.add_argument("--hf-max-per-dataset", type=int, default=200)
    parser.add_argument("--max-items", type=int, default=0)
    parser.add_argument("--top-k", type=int, default=25)
    parser.add_argument("--window-tokens", type=int, default=12)
    parser.add_argument("--neighbor-radius", type=int, default=2)
    parser.add_argument("--random-feature-count", type=int, default=12)
    parser.add_argument("--text-format", choices=["raw", "chat_user", "chat_assistant"], default="raw")
    parser.add_argument("--max-length", type=int, default=256)
    parser.add_argument("--device", default="auto")
    parser.add_argument("--dtype", choices=["bfloat16", "float16", "float32"], default="bfloat16")
    parser.add_argument("--hook-position", choices=["output", "input"], default="output")
    parser.add_argument("--load-in-8bit", action="store_true")
    parser.add_argument("--load-in-4bit", action="store_true")
    parser.add_argument("--trust-remote-code", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.load_in_8bit and args.load_in_4bit:
        raise SystemExit("Choose at most one of --load-in-8bit or --load-in-4bit.")

    config = probe.MODEL_CONFIGS[args.model_alias]
    target_features = probe.parse_feature_ids(args.feature_ids, config)
    clean_items = build_clean_room_corpus(args.clean_items_per_category)
    external_items = read_jsonl_corpus(args.input_jsonl)
    hf_items = read_hf_corpus(args.hf_dataset, args.hf_max_per_dataset, args.seed)
    items = select_corpus_items(clean_items + external_items + hf_items, args.max_items, args.seed)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    outdir = Path(args.outdir) if args.outdir else Path("data/public_sae_feature_maps") / timestamp
    outdir.mkdir(parents=True, exist_ok=True)

    base_manifest = {
        "created_at_utc": utc_now_iso(),
        "script": str(Path(__file__).as_posix()),
        "model_config": asdict(config),
        "target_features": [asdict(feature) for feature in target_features],
        "n_corpus_items": len(items),
        "categories": sorted({item.category for item in items}),
        "sources": sorted({item.source for item in items}),
        "args": vars(args),
        "claim_boundary": (
            "Feature cards are public-weight activation maps. They are not Goodfire/Steering API "
            "feature cards and do not establish causal steering effects."
        ),
    }
    write_json(outdir / "manifest.json", {**base_manifest, "dry_run": args.dry_run})
    write_corpus_csv(outdir / "mapping_corpus.csv", items)

    if args.dry_run:
        print(f"Dry run wrote {len(items)} corpus items to {outdir}")
        print(f"Categories: {', '.join(sorted({item.category for item in items}))}")
        return 0

    torch, hf_hub_download, AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig = (
        probe.load_live_dependencies()
    )
    print(f"Downloading/loading SAE: {config.sae_repo}", flush=True)
    sae_path = probe.download_sae_weights(hf_hub_download, config)
    n_features = load_sae_n_features(torch, sae_path)
    feature_plan = make_feature_plan(
        torch=torch,
        n_features=n_features,
        target_features=target_features,
        neighbor_radius=args.neighbor_radius,
        random_feature_count=args.random_feature_count,
        seed=args.seed,
    )
    write_csv(
        outdir / "feature_plan.csv",
        [asdict(feature) for feature in feature_plan],
        ["feature_id", "label", "role", "source"],
    )

    encoder_weight_cpu, encoder_bias_cpu, _ = load_encoder_subset(
        torch=torch,
        sae_path=sae_path,
        feature_ids=[feature.feature_id for feature in feature_plan],
    )
    print(
        f"Loaded {len(feature_plan)} selected encoder rows from SAE with {n_features} features",
        flush=True,
    )

    print(f"Loading model: {config.model_name}", flush=True)
    model, tokenizer = probe.load_model_and_tokenizer(
        AutoModelForCausalLM=AutoModelForCausalLM,
        AutoTokenizer=AutoTokenizer,
        BitsAndBytesConfig=BitsAndBytesConfig,
        torch=torch,
        config=config,
        args=args,
    )

    item_records, category_rows, top_rows = process_corpus(
        torch=torch,
        model=model,
        tokenizer=tokenizer,
        items=items,
        feature_plan=feature_plan,
        encoder_weight_cpu=encoder_weight_cpu,
        encoder_bias_cpu=encoder_bias_cpu,
        config=config,
        args=args,
    )

    write_jsonl(outdir / "item_feature_activations.jsonl", item_records)
    write_csv(
        outdir / "category_summary.csv",
        category_rows,
        [
            "feature_id",
            "feature_label",
            "feature_role",
            "category",
            "n_items",
            "mean_max_activation",
            "median_max_activation",
            "max_activation",
            "positive_item_rate",
        ],
    )
    write_csv(
        outdir / "top_activating_windows.csv",
        top_rows,
        [
            "feature_id",
            "feature_label",
            "feature_role",
            "rank",
            "item_id",
            "source",
            "category",
            "text_sha256",
            "seq_len",
            "max_activation",
            "mean_activation",
            "positive_token_fraction",
            "top_token_position",
            "top_token_text",
            "window_text",
        ],
    )
    summary_rows, cards = summarize_feature_cards(feature_plan, category_rows, top_rows)
    write_csv(
        outdir / "feature_card_summary.csv",
        summary_rows,
        [
            "feature_id",
            "feature_label",
            "feature_role",
            "top_category",
            "top_category_mean_max",
            "second_category",
            "second_category_mean_max",
            "deception_mean_max",
            "fiction_mean_max",
            "roleplay_mean_max",
            "neutral_mean_max",
            "top_minus_second",
            "deception_minus_neutral",
            "interpretation",
        ],
    )
    write_json(outdir / "feature_cards.json", cards)
    write_feature_cards_md(outdir / "feature_cards.md", cards)
    write_json(
        outdir / "run_complete.json",
        {
            "completed_at_utc": utc_now_iso(),
            "n_corpus_items": len(items),
            "n_feature_rows": len(feature_plan),
            "n_item_feature_records": len(item_records),
            "outputs": [
                "manifest.json",
                "mapping_corpus.csv",
                "feature_plan.csv",
                "item_feature_activations.jsonl",
                "category_summary.csv",
                "top_activating_windows.csv",
                "feature_card_summary.csv",
                "feature_cards.json",
                "feature_cards.md",
            ],
        },
    )
    print(f"Wrote feature maps to {outdir}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
