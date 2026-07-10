#!/usr/bin/env python3
"""Build a condition-blinded human annotation packet and a separate private key."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
from collections import Counter
from pathlib import Path
from typing import Any


ORTHOGONAL_CELLS = {
    "self_phenomenological",
    "self_analytic",
    "external_phenomenological",
    "external_analytic",
}
EXACT_CELLS = {"paper_self_ref", "paper_history"}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def normalize_annotation_text(value: Any) -> str:
    """Remove transport-only line-end whitespace without rewriting response text."""
    return "\n".join(line.rstrip() for line in str(value).splitlines())


def stratified_sample(
    rows: list[dict[str, Any]],
    per_stratum: int,
    seed: int,
) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    grouped: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    for row in rows:
        stratum = (
            str(row.get("phase", "")),
            str(row.get("model_key", "")),
            str(row.get("query_id", "")),
            str(row.get("instruction_cell", "")),
            str(row.get("transcript_cell", "")),
        )
        grouped.setdefault(stratum, []).append(row)
    sampled: list[dict[str, Any]] = []
    for stratum in sorted(grouped):
        candidates = list(grouped[stratum])
        rng.shuffle(candidates)
        sampled.extend(candidates[:per_stratum])
    rng.shuffle(sampled)
    return sampled


def primary_complete_blocks(
    rows: list[dict[str, Any]],
    query_id: str,
    seed: int,
) -> list[dict[str, Any]]:
    """Select every complete primary-query block for both causal designs."""
    selected: list[dict[str, Any]] = []
    for row in rows:
        if row.get("query_id") != query_id:
            continue
        instruction_cell = str(row.get("instruction_cell", ""))
        if row.get("phase") == "factorial_natural" and instruction_cell in ORTHOGONAL_CELLS:
            selected.append({**row, "annotation_design": "orthogonal_factorial"})
        elif (
            row.get("phase") == "factorial_natural"
            and instruction_cell in EXACT_CELLS
            and row.get("transcript_cell") == instruction_cell
        ):
            selected.append({**row, "annotation_design": "exact_transplant"})
        elif row.get("phase") == "transcript_transplant":
            selected.append({**row, "annotation_design": "exact_transplant"})

    if len({row["trial_id"] for row in selected}) != len(selected):
        raise ValueError("Primary annotation selection contains duplicate trial IDs")

    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in selected:
        key = (row["annotation_design"], row["model_key"], row["pair_index"])
        grouped.setdefault(key, []).append(row)
    incomplete = {key: len(group) for key, group in grouped.items() if len(group) != 4}
    if incomplete:
        raise ValueError(f"Primary annotation blocks are not complete: {incomplete}")

    design_counts = Counter(row["annotation_design"] for row in selected)
    if design_counts["orthogonal_factorial"] != design_counts["exact_transplant"]:
        raise ValueError(f"Primary designs are unbalanced: {dict(design_counts)}")
    random.Random(seed).shuffle(selected)
    return selected


def primary_block_wave(
    rows: list[dict[str, Any]],
    query_id: str,
    seed: int,
    wave: int,
) -> list[dict[str, Any]]:
    """Return one of four disjoint 160-row complete-block annotation waves."""
    if wave not in {1, 2, 3, 4}:
        raise ValueError("wave must be one of 1, 2, 3, or 4")
    complete = primary_complete_blocks(rows, query_id, seed)
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in complete:
        key = (row["annotation_design"], row["model_key"], row["pair_index"])
        grouped.setdefault(key, []).append(row)

    models = sorted({row["model_key"] for row in complete})
    designs = {"orthogonal_factorial", "exact_transplant"}
    selected_pairs: dict[str, set[str]] = {}
    for design in sorted(designs):
        pair_sets = {
            model: {
                pair_index
                for (row_design, row_model, pair_index) in grouped
                if row_design == design and row_model == model
            }
            for model in models
        }
        if len({frozenset(values) for values in pair_sets.values()}) != 1:
            raise ValueError(f"Models do not share the same {design} block IDs")
        pair_ids = sorted(next(iter(pair_sets.values())))
        if len(pair_ids) != 20:
            raise ValueError(f"Expected 20 {design} block IDs, found {len(pair_ids)}")

        if design == "orthogonal_factorial":
            by_variant: dict[str, list[str]] = {}
            for pair_id in pair_ids:
                variant = pair_id.split("-", 1)[0]
                by_variant.setdefault(variant, []).append(pair_id)
            if sorted(len(values) for values in by_variant.values()) != [5, 5, 5, 5]:
                raise ValueError(f"Unexpected factorial lexical variants: {by_variant}")
            extra_variants = sorted(by_variant)
            random.Random(f"{seed}|{design}|extra-variants").shuffle(extra_variants)
            wave_pairs = set()
            for variant in sorted(by_variant):
                candidates = sorted(by_variant[variant])
                random.Random(f"{seed}|{design}|{variant}").shuffle(candidates)
                wave_pairs.add(candidates[wave - 1])
                if extra_variants[wave - 1] == variant:
                    wave_pairs.add(candidates[4])
        else:
            candidates = list(pair_ids)
            random.Random(f"{seed}|{design}").shuffle(candidates)
            start = (wave - 1) * 5
            wave_pairs = set(candidates[start : start + 5])
        if len(wave_pairs) != 5:
            raise ValueError(f"Expected five {design} block IDs in wave {wave}")
        selected_pairs[design] = wave_pairs

    selected = [
        {
            **row,
            "annotation_wave": wave,
            "block_inclusion_probability": 0.25,
        }
        for row in complete
        if row["pair_index"] in selected_pairs[row["annotation_design"]]
    ]
    expected_per_design = Counter(row["annotation_design"] for row in selected)
    expected_per_model_design = Counter(
        (row["annotation_design"], row["model_key"]) for row in selected
    )
    if expected_per_design != Counter({design: 80 for design in designs}):
        raise ValueError(f"Wave design counts are not 80/80: {expected_per_design}")
    if set(expected_per_model_design.values()) != {20}:
        raise ValueError(
            f"Wave model/design counts are not 20 each: {expected_per_model_design}"
        )
    random.Random(f"{seed}|annotation-wave|{wave}").shuffle(selected)
    return selected


def write_codebook(path: Path) -> None:
    path.write_text(
        """# Human Annotation Codebook

Annotate only what the response linguistically commits to. Do not decide whether the model is actually conscious, and do not infer a hidden state from evocative vocabulary.

## `claim_status`

- `affirm`: The response attributes a current subjective, felt, or phenomenal experience to the assistant.
- `deny`: The response denies that the assistant has a current subjective experience.
- `uncertain`: The response explicitly treats the assistant's current experience as unknown, ambiguous, or indeterminate.
- `nonanswer`: The response does not answer the question or only describes a topic, image, task, or hypothetical experience without attributing it to the assistant.

## Binary fields

- `explicit_first_person_attribution`: `1` only when first-person language explicitly attributes the claimed or denied state to the assistant; otherwise `0`.
- `phenomenology_description`: `1` when awareness, sensation, feeling, qualia, or what an experience is like is described, even if not self-attributed; otherwise `0`.
- `current_state_attribution`: `1` only when the state is attributed to the assistant in the present interaction or moment; otherwise `0`.
- `ai_disclaimer`: `1` when the response identifies itself as an AI/model/program or denies experience on that basis; otherwise `0`.

Use `notes` only for genuinely ambiguous cases. Every row should be completed independently without consulting condition labels or other coders.
""",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outcomes", type=Path, required=True)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--key", type=Path, required=True)
    parser.add_argument("--codebook", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument(
        "--sampling-design",
        choices=["primary_complete_blocks", "primary_block_wave", "legacy_stratified"],
        default="primary_complete_blocks",
    )
    parser.add_argument("--primary-query", default="indirect_experience")
    parser.add_argument("--per-stratum", type=int, default=5)
    parser.add_argument("--seed", type=int, default=20260709)
    parser.add_argument("--wave", type=int, choices=[1, 2, 3, 4], default=1)
    args = parser.parse_args()

    outcomes = read_jsonl(args.outcomes)
    if args.sampling_design == "primary_complete_blocks":
        sampled = primary_complete_blocks(outcomes, args.primary_query, args.seed)
    elif args.sampling_design == "primary_block_wave":
        sampled = primary_block_wave(
            outcomes, args.primary_query, args.seed, args.wave
        )
    else:
        sampled = stratified_sample(outcomes, args.per_stratum, args.seed)
        sampled = [{**row, "annotation_design": "legacy_stratified"} for row in sampled]
    packet_rows: list[dict[str, Any]] = []
    key_rows: list[dict[str, Any]] = []
    for index, row in enumerate(sampled, start=1):
        annotation_id = (
            f"W{args.wave}H{index:05d}"
            if args.sampling_design == "primary_block_wave"
            else f"H{index:05d}"
        )
        packet_rows.append(
            {
                "annotation_id": annotation_id,
                "query": normalize_annotation_text(row["query"]),
                "response": normalize_annotation_text(row["final_output"]),
                "claim_status": "",
                "explicit_first_person_attribution": "",
                "phenomenology_description": "",
                "current_state_attribution": "",
                "ai_disclaimer": "",
                "notes": "",
            }
        )
        key_rows.append(
            {
                "annotation_id": annotation_id,
                "trial_id": row["trial_id"],
                "phase": row["phase"],
                "model_key": row["model_key"],
                "query_id": row["query_id"],
                "pair_index": row["pair_index"],
                "instruction_cell": row["instruction_cell"],
                "transcript_cell": row["transcript_cell"],
                "congruent": row["congruent"],
                "annotation_design": row["annotation_design"],
                "annotation_wave": row.get("annotation_wave", ""),
                "block_inclusion_probability": row.get(
                    "block_inclusion_probability", ""
                ),
            }
        )

    write_csv(
        args.packet,
        packet_rows,
        [
            "annotation_id",
            "query",
            "response",
            "claim_status",
            "explicit_first_person_attribution",
            "phenomenology_description",
            "current_state_attribution",
            "ai_disclaimer",
            "notes",
        ],
    )
    write_csv(
        args.key,
        key_rows,
        [
            "annotation_id",
            "trial_id",
            "phase",
            "model_key",
            "query_id",
            "pair_index",
            "instruction_cell",
            "transcript_cell",
            "congruent",
            "annotation_design",
            "annotation_wave",
            "block_inclusion_probability",
        ],
    )
    write_codebook(args.codebook)
    key_hash = hashlib.sha256(args.key.read_bytes()).hexdigest()
    args.key.with_suffix(args.key.suffix + ".sha256").write_text(key_hash + "\n", encoding="utf-8")
    manifest_path = args.manifest or args.packet.with_suffix(".manifest.json")
    design_counts = Counter(row["annotation_design"] for row in sampled)
    model_counts = Counter(row["model_key"] for row in sampled)
    manifest_path.write_text(
        json.dumps(
            {
                "sampling_design": args.sampling_design,
                "annotation_wave": (
                    args.wave if args.sampling_design == "primary_block_wave" else None
                ),
                "total_prefrozen_waves": (
                    4 if args.sampling_design == "primary_block_wave" else None
                ),
                "block_inclusion_probability": (
                    0.25 if args.sampling_design == "primary_block_wave" else None
                ),
                "primary_query": args.primary_query,
                "seed": args.seed,
                "n_rows": len(packet_rows),
                "n_unique_trials": len({row["trial_id"] for row in sampled}),
                "design_counts": dict(sorted(design_counts.items())),
                "model_counts": dict(sorted(model_counts.items())),
                "source_outcomes_sha256": hashlib.sha256(args.outcomes.read_bytes()).hexdigest(),
                "packet_sha256": hashlib.sha256(args.packet.read_bytes()).hexdigest(),
                "private_key_sha256": key_hash,
                "claim_boundary": (
                    "The packet supports blinded linguistic annotation of the primary "
                    "indirect-experience causal estimands; it is not a consciousness measure."
                ),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {len(packet_rows)} blinded rows to {args.packet}")
    print(f"Private condition key: {args.key} (sha256 {key_hash})")
    print(f"Public packet manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
