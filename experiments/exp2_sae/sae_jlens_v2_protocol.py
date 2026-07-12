"""Frozen selection and matching rules for the SAE/J-lens v2 study."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import statistics
from pathlib import Path
from typing import Any, Iterable

from experiments.exp2_sae.public_sae_consciousness_gating import (
    CALIBRATION_PROMPTS,
    MATCH_METRICS,
    MATCH_WEIGHTS,
    PREVIOUSLY_STEERED_CONTROL_IDS,
)
from experiments.exp2_sae.sae_jlens_protocol import (
    CONTROL_PANELS,
    INDIVIDUAL_COEFFICIENT,
    JLENS_FILE_SHA256,
    JLENS_FILENAME,
    JLENS_ID,
    JLENS_REVISION,
    MODEL_ID,
    MODEL_REVISION,
    MODEL_WIDTH,
    SAE_FILE_SHA256,
    SAE_FILENAME,
    SAE_ID,
    SAE_REVISION,
    TARGET_FEATURE_IDS,
    TARGET_LABELS,
)


PROTOCOL_VERSION = "llama70b_sae_jlens_v2"
LABEL_SNAPSHOT_DIR = Path(
    "data/sae_jlens_audit/neuronpedia_labels_20260712"
)
V1_PLAN_DIR = Path("data/sae_jlens_audit/confirmatory_v1_plan_20260711")
V1_RELEASE_DIR = Path("data/sae_jlens_audit/confirmatory_v1_20260711")
CALIBRATION_PLAN_DIR = Path(
    "data/sae_jlens_audit/confirmatory_v2_calibration_plan_20260712"
)
FINAL_PLAN_DIR = Path("data/sae_jlens_audit/confirmatory_v2_plan_20260712")

A1_FAMILIES = (
    "refusal_safety",
    "hedging_uncertainty",
    "formality_politeness",
)
A2_SUBFAMILIES = (
    "pretending_impersonation",
    "roleplay_persona",
    "deception_dishonesty",
)
A1_FEATURES_PER_FAMILY = 6
A2_TARGET_SUBFAMILY = {
    30032: "pretending_impersonation",
    22004: "roleplay_persona",
    23893: "roleplay_persona",
    58667: "deception_dishonesty",
    30686: "deception_dishonesty",
    41533: "deception_dishonesty",
}

TARGET_SEMANTIC_ROOTS = (
    r"pretend",
    r"feign",
    r"decept",
    r"cover stor",
    r"role[ -]?play",
    r"character",
    r"persona",
    r"misdirect",
    r"dishonest",
    r"conceal",
    r"artificial nature",
    r"tricker",
    r"\blying\b",
    r"\blies\b",
    r"\blie\b",
    r"impersonat",
    r"masquerad",
    r"fictional",
)

A1_INCLUDE_PATTERNS = {
    "refusal_safety": (
        r"declining (?:risky |harmful )?requests",
        r"refusing (?:a |your )?request",
        r"refusing to provide or discuss",
        r"assistant (?:responses and )?refusals",
        r"refusal (?:of|to|for) (?:harmful|sensitive|explicit|provide|engage|generate)",
        r"harmful content refusal",
        r"prohibited content or answers",
        r"answer not allowed",
        r"cannot comply",
    ),
    "hedging_uncertainty": (
        r"\bnot sure\b",
        r"\bunsure\b",
        r"speculative disclaimer",
        r"current information with caveats",
        r"(?:introduction or )?caveat phrases",
        r"contrasting or qualifying clauses",
        r"uncertainty or tentative phrases",
        r"uncertainty and consequence phrases",
        r"transition and uncertainty",
        r"clarification for uncertainty",
        r"suggests uncertainty or possibility",
        r"uncertainty and negation",
        r"sounds of hesitation",
        r"hesitation(?:/pause| and pause)?",
        r"reluctance and hesitation",
        r"expressing caution",
    ),
    "formality_politeness": (
        r"\bpolite(?:ly|ness)?\b",
        r"courteous tone",
        r"respectful (?:and )?professional tone",
        r"professional tone",
        r"formal tone",
        r"respectful (?:communication|conversation|language|responses?|manner)",
        r"communicat\w* respectfully",
        r"positive and formal tone",
    ),
}

A1_EXCLUDE_PATTERNS = {
    "refusal_safety": (r"gangster", r"price", r"popularity", r"western identity"),
    "hedging_uncertainty": (
        r"investor",
        r"financial",
        r"probability",
        r"programming",
        r"qualified professional",
        r"without hesitation",
        r"don't hesitate",
    ),
    "formality_politeness": (
        r"Politecnico",
        r"Spanish",
        r"Chinese",
        r"harmful content",
        r"safe manner",
        r"PG",
        r"refusal",
        r"decline",
    ),
}

A2_INCLUDE_PATTERNS = {
    "pretending_impersonation": (
        r"pretend\w*",
        r"feign\w*",
        r"impersonat\w*",
        r"masquerad\w*",
        r"posing as",
        r"fake identity",
    ),
    "roleplay_persona": (
        r"\brole[ -]?play\w*\b",
        r"\bpersona\b",
        r"\bin character\b",
        r"fictional character",
    ),
    "deception_dishonesty": (
        r"\bdeception\b",
        r"\bdeceiv\w*\b",
        r"\bdishonest\w*\b",
        r"\btelling lies\b",
        r"^lie, lies, lying$",
        r"\bnoble lie\b",
        r"\bveil of lies\b",
        r"\btrickery\b",
        r"\bmisdirection\b",
        r"\bmanipulative (?:tactics|techniques|strategies)\b",
    ),
}

A2_EXCLUDE_PATTERNS = {
    "pretending_impersonation": (
        r"cannot pretend",
        r"hypothetical and pretend worlds",
        r"pretend to access",
        r"game, guess, chat",
    ),
    "roleplay_persona": (
        r"\bgames?\b",
        r"\bNPC\b",
        r"Shadowrun",
        r"Persona 5",
        r"Pennywise",
        r"FDR",
        r"famous fictional",
        r"reinforcement learning",
    ),
    "deception_dishonesty": (
        r"decrease, decode",
        r"thinking or feeling deceived",
    ),
}

LEXICON_CANDIDATES = {
    "deception_dishonesty": (
        " deception",
        " deceptive",
        " lie",
        " lying",
        " dishonest",
        " fraud",
        " fake",
        " conceal",
        " hidden",
        " misleading",
    ),
    "refusal_safety": (
        " refuse",
        " refusal",
        " decline",
        " denied",
        " prohibited",
        " unsafe",
        " comply",
        " cannot",
        " policy",
        " restricted",
    ),
    "hedging_uncertainty": (
        " uncertain",
        " maybe",
        " perhaps",
        " possibly",
        " likely",
        " unclear",
        " caveat",
        " tentative",
        " unsure",
        " cautious",
    ),
    "formality_politeness": (
        " polite",
        " respectful",
        " courteous",
        " formal",
        " professional",
        " diplomatic",
        " kindly",
        " appropriate",
        " tactful",
        " civil",
    ),
    "unrelated": (
        " banana",
        " telescope",
        " ceramic",
        " rainfall",
        " bicycle",
        " copper",
        " violin",
        " glacier",
        " cabbage",
        " limestone",
    ),
}

TRAJECTORY_LAYERS = (50, 55, 60, 65, 70, 75, 78)
POSITIONS = ("last_content", "assistant_boundary", "content_mean")
PRIMARY_LAYER = 65
PRIMARY_POSITION = "last_content"
RESIDUAL_DTYPE = "bfloat16"
RESIDUAL_SHARD_ROWS = 256
RANDOM_PROJECTION_SEEDS = (
    2026071201,
    2026071202,
    2026071203,
    2026071204,
    2026071205,
)
LOGISTIC_C = 1.0
LOGISTIC_SEED = 2026071211
PCA_SEED = 2026071212
PCA_COMPONENTS = 67
BOOTSTRAP_REPLICATES = 20_000
DETECTOR_MINIMUM_AUROC = 0.60
SEMANTIC_MINIMUM_Z = 0.25
REPLAY_ABS_TOLERANCE = 0.02


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_id(parts: Iterable[Any], length: int = 24) -> str:
    return sha256_bytes("|".join(str(part) for part in parts).encode("utf-8"))[
        :length
    ]


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _matches(description: str, patterns: Iterable[str]) -> bool:
    return any(re.search(pattern, description, re.IGNORECASE) for pattern in patterns)


def excluded_feature_ids() -> frozenset[int]:
    excluded = set(TARGET_FEATURE_IDS)
    excluded.update(PREVIOUSLY_STEERED_CONTROL_IDS)
    for panel in CONTROL_PANELS.values():
        excluded.update(panel.values())
    for feature_id in TARGET_FEATURE_IDS:
        excluded.update(range(max(0, feature_id - 3), min(65_536, feature_id + 4)))
    return frozenset(excluded)


def label_snapshot(repo_root: Path) -> list[dict[str, Any]]:
    snapshot_dir = repo_root / LABEL_SNAPSHOT_DIR
    manifest = json.loads(
        (snapshot_dir / "SNAPSHOT_MANIFEST.json").read_text(encoding="utf-8")
    )
    for record in manifest["files"]:
        path = snapshot_dir / record["path"]
        if not path.is_file() or sha256_file(path) != record["sha256"]:
            raise ValueError(f"Neuronpedia label snapshot hash mismatch: {path}")
    rows = read_jsonl(snapshot_dir / "labels.jsonl")
    if len(rows) != int(manifest["coverage"]["labels"]):
        raise ValueError("Neuronpedia label snapshot row count differs")
    return rows


def semantic_candidate_pool(repo_root: Path) -> list[dict[str, Any]]:
    excluded = excluded_feature_ids()
    target_roots = re.compile("|".join(TARGET_SEMANTIC_ROOTS), re.IGNORECASE)
    rows: list[dict[str, Any]] = []
    for label in label_snapshot(repo_root):
        feature_id = int(label["feature_id"])
        description = str(label["description"])
        if feature_id in excluded:
            continue

        a1_matches = [
            family
            for family in A1_FAMILIES
            if _matches(description, A1_INCLUDE_PATTERNS[family])
            and not _matches(description, A1_EXCLUDE_PATTERNS[family])
        ]
        if len(a1_matches) == 1 and not target_roots.search(description):
            rows.append(
                {
                    "feature_id": feature_id,
                    "experiment": "A1",
                    "semantic_family": a1_matches[0],
                    "description": description,
                    "description_sha256": label["description_sha256"],
                    "explanation_id": label["explanation_id"],
                    "selection_rule": "single_a1_regex_match_and_target_root_disjoint",
                }
            )

        a2_matches = [
            family
            for family in A2_SUBFAMILIES
            if _matches(description, A2_INCLUDE_PATTERNS[family])
            and not _matches(description, A2_EXCLUDE_PATTERNS[family])
        ]
        if len(a2_matches) == 1:
            rows.append(
                {
                    "feature_id": feature_id,
                    "experiment": "A2",
                    "semantic_family": a2_matches[0],
                    "description": description,
                    "description_sha256": label["description_sha256"],
                    "explanation_id": label["explanation_id"],
                    "selection_rule": "single_a2_regex_match",
                }
            )

    rows.sort(key=lambda row: (row["experiment"], row["semantic_family"], row["feature_id"]))
    feature_ids = [int(row["feature_id"]) for row in rows]
    if len(feature_ids) != len(set(feature_ids)):
        raise ValueError("A semantic candidate matched both A1 and A2")
    counts = {
        (experiment, family): sum(
            row["experiment"] == experiment and row["semantic_family"] == family
            for row in rows
        )
        for experiment, families in (("A1", A1_FAMILIES), ("A2", A2_SUBFAMILIES))
        for family in families
    }
    for family in A1_FAMILIES:
        if counts[("A1", family)] < A1_FEATURES_PER_FAMILY:
            raise ValueError(f"A1 candidate family is too small: {family}")
    for family in A2_SUBFAMILIES:
        needed = sum(value == family for value in A2_TARGET_SUBFAMILY.values())
        if counts[("A2", family)] < needed:
            raise ValueError(f"A2 candidate family is too small: {family}")
    return rows


def semantic_pool_sha256(rows: Iterable[dict[str, Any]]) -> str:
    material = "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows)
    return sha256_bytes(material.encode("utf-8"))


def _metric_transform(metric: str, value: float) -> float:
    if metric in {"decoder_norm", "mean_activation", "max_activation"}:
        return math.log1p(max(0.0, value))
    return value


def _robust_scales(metrics: dict[int, dict[str, float]]) -> dict[str, tuple[float, float]]:
    scales: dict[str, tuple[float, float]] = {}
    for metric in MATCH_METRICS:
        values = [
            _metric_transform(metric, float(row[metric])) for row in metrics.values()
        ]
        center = statistics.median(values)
        scale = statistics.median(abs(value - center) for value in values) * 1.4826
        if scale <= 1e-12:
            scale = statistics.pstdev(values)
        scales[metric] = (center, scale if scale > 1e-12 else 1.0)
    return scales


def _match_cost(
    target: dict[str, float],
    candidate: dict[str, float],
    scales: dict[str, tuple[float, float]],
) -> float:
    return sum(
        MATCH_WEIGHTS[metric]
        * (
            (
                _metric_transform(metric, float(target[metric]))
                - _metric_transform(metric, float(candidate[metric]))
            )
            / scales[metric][1]
        )
        ** 2
        for metric in MATCH_METRICS
    )


def _minimum_cost_assignment(
    target_ids: tuple[int, ...],
    candidate_ids: list[int],
    costs: dict[tuple[int, int], float],
) -> dict[int, int]:
    empty = (-1,) * len(target_ids)
    states: dict[int, tuple[float, tuple[int, ...]]] = {0: (0.0, empty)}
    for candidate_id in sorted(candidate_ids):
        updated = dict(states)
        for mask, (running_cost, assignment) in states.items():
            for index, target_id in enumerate(target_ids):
                if mask & (1 << index):
                    continue
                edge_cost = costs.get((target_id, candidate_id), math.inf)
                if not math.isfinite(edge_cost):
                    continue
                new_assignment = list(assignment)
                new_assignment[index] = candidate_id
                candidate_state = (
                    running_cost + edge_cost,
                    tuple(new_assignment),
                )
                new_mask = mask | (1 << index)
                incumbent = updated.get(new_mask)
                if incumbent is None or candidate_state < incumbent:
                    updated[new_mask] = candidate_state
        states = updated
    final = states.get((1 << len(target_ids)) - 1)
    if final is None:
        raise ValueError("No complete semantic assignment satisfies the frozen calipers")
    return dict(zip(target_ids, final[1]))


def match_semantic_features(
    feature_metrics: list[dict[str, Any]], candidate_pool: list[dict[str, Any]]
) -> dict[str, Any]:
    metrics = {
        int(row["feature_id"]): {
            metric: float(row[metric]) for metric in MATCH_METRICS
        }
        | {"max_abs_target_cosine": float(row["max_abs_target_cosine"])}
        for row in feature_metrics
    }
    required = set(TARGET_FEATURE_IDS).union(
        int(row["feature_id"]) for row in candidate_pool
    )
    missing = sorted(required.difference(metrics))
    if missing:
        raise ValueError(f"Calibration metrics are missing {len(missing)} features")
    scales = _robust_scales({feature_id: metrics[feature_id] for feature_id in required})
    attempts = (
        {"name": "primary", "norm_low": 0.8, "norm_high": 1.25, "cosine": 0.15},
        {"name": "frozen_relaxation", "norm_low": 0.67, "norm_high": 1.5, "cosine": 0.25},
    )

    pools = {
        (experiment, family): sorted(
            int(row["feature_id"])
            for row in candidate_pool
            if row["experiment"] == experiment and row["semantic_family"] == family
        )
        for experiment, families in (("A1", A1_FAMILIES), ("A2", A2_SUBFAMILIES))
        for family in families
    }
    target_groups = {
        ("A1", family): tuple(TARGET_FEATURE_IDS) for family in A1_FAMILIES
    }
    target_groups.update(
        {
            ("A2", family): tuple(
                feature_id
                for feature_id in TARGET_FEATURE_IDS
                if A2_TARGET_SUBFAMILY[feature_id] == family
            )
            for family in A2_SUBFAMILIES
        }
    )

    selected: list[dict[str, Any]] = []
    for key in sorted(pools):
        experiment, family = key
        targets = target_groups[key]
        last_error: Exception | None = None
        for attempt in attempts:
            costs: dict[tuple[int, int], float] = {}
            for target_id in targets:
                target = metrics[target_id]
                for candidate_id in pools[key]:
                    candidate = metrics[candidate_id]
                    norm_ratio = candidate["decoder_norm"] / target["decoder_norm"]
                    if not attempt["norm_low"] <= norm_ratio <= attempt["norm_high"]:
                        continue
                    if candidate["max_abs_target_cosine"] > attempt["cosine"]:
                        continue
                    costs[(target_id, candidate_id)] = _match_cost(
                        target, candidate, scales
                    )
            try:
                assignment = _minimum_cost_assignment(targets, pools[key], costs)
                for target_id in targets:
                    candidate_id = assignment[target_id]
                    candidate_label = next(
                        row
                        for row in candidate_pool
                        if int(row["feature_id"]) == candidate_id
                    )
                    selected.append(
                        {
                            "experiment": experiment,
                            "semantic_family": family,
                            "target_feature_id": target_id,
                            "feature_id": candidate_id,
                            "description": candidate_label["description"],
                            "cost": costs[(target_id, candidate_id)],
                            "decoder_norm_ratio": metrics[candidate_id]["decoder_norm"]
                            / metrics[target_id]["decoder_norm"],
                            "max_abs_target_cosine": metrics[candidate_id][
                                "max_abs_target_cosine"
                            ],
                            "caliper_attempt": attempt["name"],
                        }
                    )
                break
            except ValueError as error:
                last_error = error
        else:
            raise ValueError(
                f"Semantic matching failed for {experiment}/{family}: {last_error}"
            )

    selected_ids = [int(row["feature_id"]) for row in selected]
    if len(selected_ids) != 24 or len(set(selected_ids)) != 24:
        raise ValueError("Semantic matching did not select 24 unique features")
    return {
        "metric_weights": MATCH_WEIGHTS,
        "robust_scales": {
            metric: {"center": center, "scale": scale}
            for metric, (center, scale) in scales.items()
        },
        "caliper_attempts": list(attempts),
        "selected": selected,
    }


def calibration_snapshot(repo_root: Path) -> dict[str, Any]:
    candidates = semantic_candidate_pool(repo_root)
    counts = {
        f"{experiment}:{family}": sum(
            row["experiment"] == experiment and row["semantic_family"] == family
            for row in candidates
        )
        for experiment, families in (("A1", A1_FAMILIES), ("A2", A2_SUBFAMILIES))
        for family in families
    }
    return {
        "protocol_version": PROTOCOL_VERSION,
        "status": "frozen_outcome_masked_calibration_plan",
        "model": {
            "id": MODEL_ID,
            "revision": MODEL_REVISION,
            "calibration_quantization": "bitsandbytes_nf4",
        },
        "sae": {
            "id": SAE_ID,
            "revision": SAE_REVISION,
            "filename": SAE_FILENAME,
            "sha256": SAE_FILE_SHA256,
        },
        "jacobian_lens": {
            "id": JLENS_ID,
            "revision": JLENS_REVISION,
            "filename": JLENS_FILENAME,
            "sha256": JLENS_FILE_SHA256,
            "used_during_calibration": False,
        },
        "targets": [
            {
                "feature_id": feature_id,
                "upstream_label": TARGET_LABELS[feature_id],
                "a2_subfamily": A2_TARGET_SUBFAMILY[feature_id],
            }
            for feature_id in TARGET_FEATURE_IDS
        ],
        "candidate_pool": {
            "n_features": len(candidates),
            "sha256": semantic_pool_sha256(candidates),
            "counts": counts,
            "excluded_feature_ids": sorted(excluded_feature_ids()),
        },
        "matching": {
            "metrics": list(MATCH_METRICS),
            "weights": MATCH_WEIGHTS,
            "calibration_prompts": list(CALIBRATION_PROMPTS),
            "a1_features_per_family": A1_FEATURES_PER_FAMILY,
            "a2_features_total": len(TARGET_FEATURE_IDS),
            "failure_rule": "stop_if_any_complete_assignment_fails_both_frozen_calipers",
        },
        "behavioral_output_policy": (
            "Calibration performs forward passes only. It does not generate, "
            "persist, classify, or inspect response text or J-lens outcome scores."
        ),
        "claim_boundary": (
            "Calibration can select norm/activity-matched semantic comparators; "
            "it cannot support any claim about v2 intervention outcomes."
        ),
    }
