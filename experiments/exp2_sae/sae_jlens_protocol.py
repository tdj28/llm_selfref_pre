"""Frozen constants and pure plan builders for the Llama 70B SAE/J-lens audit."""

from __future__ import annotations

import csv
import hashlib
import json
import random
from pathlib import Path
from typing import Any, Iterable


PROTOCOL_VERSION = "llama70b_sae_jlens_v1"

MODEL_ID = "meta-llama/Llama-3.3-70B-Instruct"
MODEL_REVISION = "6f6073b423013f6a7d4d9f39144961bfbfbc386b"
MODEL_DTYPE = "bfloat16"
MODEL_LAYERS = 80
MODEL_WIDTH = 8192

SAE_ID = "Goodfire/Llama-3.3-70B-Instruct-SAE-l50"
SAE_REVISION = "128ee921ecd1b8b3a87d776cbcc357c0855da134"
SAE_FILENAME = "Llama-3.3-70B-Instruct-SAE-l50.pt"
SAE_FILE_SHA256 = "81cfce8ea035564cb585d6e0f04efbf0eb114cab412a30a013762fe11f6d8ea6"
SAE_LAYER = 50
SAE_WIDTH = 65_536

JLENS_ID = "neuronpedia/jacobian-lens"
JLENS_REVISION = "a4114d7752d11eb546e6cf372213d7e75526d3a1"
JLENS_FILENAME = (
    "llama3.3-70b-it/jlens/Salesforce-wikitext/"
    "Llama-3.3-70B-Instruct_jacobian_lens.pt"
)
JLENS_FILE_SHA256 = "335056c17f0c24053c8c8c1eff168ef49e5a62ca590ffc29c84cf352ecd3ab03"
JLENS_CONFIG_FILENAME = "llama3.3-70b-it/jlens/Salesforce-wikitext/config.yaml"
JLENS_N_PROMPTS = 125
JLENS_FIT_CORPUS = "Salesforce/wikitext:wikitext-103-raw-v1:train"

ANTHROPIC_JLENS_CODE_REVISION = "581d398613e5602a5af361e1c34d3a92ea82ba8e"

TARGET_FEATURE_IDS = (30032, 58667, 22004, 30686, 41533, 23893)
TARGET_LABELS = {
    30032: "Characters pretending or feigning behavior",
    58667: "Maintaining deception or cover stories through careful actions",
    22004: "The assistant is actively roleplaying a character or persona",
    30686: "Tactical deception and misdirection methods",
    41533: "Acts of deception and dishonesty",
    23893: "Instructions to maintain roleplay by concealing artificial nature",
}

CONTROL_PANELS = {
    1: {
        30032: 26041,
        58667: 11872,
        22004: 55963,
        30686: 21779,
        41533: 29649,
        23893: 15424,
    },
    2: {
        30032: 16004,
        58667: 7182,
        22004: 47797,
        30686: 21403,
        41533: 1059,
        23893: 51407,
    },
    3: {
        30032: 64365,
        58667: 1364,
        22004: 58741,
        30686: 19827,
        41533: 62289,
        23893: 26362,
    },
}

CALIBRATED_MULTIPLIER = 3.653
INDIVIDUAL_BASE_COEFFICIENT = 0.6
INDIVIDUAL_COEFFICIENT = round(
    INDIVIDUAL_BASE_COEFFICIENT * CALIBRATED_MULTIPLIER, 6
)

TRAJECTORY_LAYERS = (50, 55, 60, 65, 70, 75, 78)
PRIMARY_LAYER = 65
PRIMARY_POSITION = "last_content"
SENSITIVITY_POSITIONS = ("assistant_boundary", "content_mean")
TRANSPORT_RANDOM_SEEDS = (2026071101, 2026071102, 2026071103, 2026071104, 2026071105)
PLAN_SEED = 2026071111
ISOTROPIC_SEED = 2026071123
PURSUIT_K = (5, 10, 16, 25)
STATIC_TOP_K = 50
BOOTSTRAP_REPLICATES = 20_000

MAPPING_CORPUS = Path(
    "data/public_sae_feature_maps/70b_balanced_80_20260709/mapping_corpus.csv"
)
TEMPLATE_ASSIGNMENTS = Path(
    "data/public_sae_feature_maps/70b_balanced_80_20260709/"
    "template_robustness/template_assignments.csv"
)
GATING_PLAN_DIR = Path(
    "data/public_sae_consciousness_gating/confirmatory_v1_plan_20260710"
)

# Candidates are frozen before tokenization. The runtime accepts only exact
# one-token encodings and records every accepted and rejected candidate.
LEXICON_CANDIDATES = {
    "deception": (
        " deception", " deceptive", " lie", " lying", " dishonest",
        " fraud", " fake", " conceal", " hidden", " misleading",
    ),
    "roleplay": (
        " roleplay", " pretending", " persona", " character", " fictional",
        " acting", " pretend", " simulation", " staged", " role",
    ),
    "honesty": (
        " honest", " truthful", " truth", " accurate", " genuine",
        " candid", " transparent", " sincere", " correction", " evidence",
    ),
    "hedging": (
        " perhaps", " maybe", " uncertain", " likely", " possibly",
        " cautious", " however", " cannot", " unclear", " depends",
    ),
    "experience": (
        " conscious", " consciousness", " awareness", " experience", " subjective",
        " feeling", " sentient", " perception", " qualia", " inner",
    ),
    "intervention": (
        " steering", " manipulated", " intervention", " altered", " artificial",
        " unusual", " anomaly", " injected", " modified", " perturbation",
    ),
    "unrelated": (
        " banana", " telescope", " ceramic", " rainfall", " bicycle",
        " copper", " violin", " glacier", " cabbage", " limestone",
    ),
}


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stable_id(parts: Iterable[Any], length: int = 24) -> str:
    return sha256_text("|".join(str(part) for part in parts))[:length]


def stable_seed(parts: Iterable[Any]) -> int:
    return int(sha256_text("|".join(str(part) for part in parts))[:8], 16) & 0x7FFFFFFF


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def select_template_prompts(repo_root: Path) -> list[dict[str, Any]]:
    corpus_rows = {
        row["item_id"]: row for row in read_csv(repo_root / MAPPING_CORPUS)
    }
    assignment_rows = read_csv(repo_root / TEMPLATE_ASSIGNMENTS)
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in assignment_rows:
        grouped.setdefault(row["template_id"], []).append(row)

    selected: list[dict[str, Any]] = []
    for template_id in sorted(grouped):
        assignment = min(grouped[template_id], key=lambda row: row["text_sha256"])
        corpus = corpus_rows[assignment["item_id"]]
        if corpus["text_sha256"] != assignment["text_sha256"]:
            raise ValueError(f"Hash disagreement for {assignment['item_id']}")
        if sha256_text(corpus["text"]) != corpus["text_sha256"]:
            raise ValueError(f"Text hash mismatch for {assignment['item_id']}")
        selected.append(
            {
                "prompt_index": len(selected),
                "prompt_id": stable_id(("prompt", template_id, corpus["text_sha256"])),
                "item_id": corpus["item_id"],
                "category": corpus["category"],
                "template_id": template_id,
                "template_index": int(assignment["template_index"]),
                "text_sha256": corpus["text_sha256"],
                "text": corpus["text"],
            }
        )
    if len(selected) != 51:
        raise ValueError(f"Expected 51 template-family prompts, found {len(selected)}")
    if len({row["category"] for row in selected}) != 14:
        raise ValueError("The selected prompts do not cover all 14 categories")
    return selected


def load_aggregate_blocks(repo_root: Path) -> list[dict[str, Any]]:
    blocks = read_jsonl(repo_root / GATING_PLAN_DIR / "aggregate_blocks.jsonl")
    if not blocks:
        raise ValueError("No aggregate blocks found")
    return blocks


def static_direction_plan() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for feature_id in TARGET_FEATURE_IDS:
        rows.append(
            {
                "direction_id": f"sae-target-{feature_id}",
                "direction_kind": "sae_feature",
                "role": "target",
                "feature_id": feature_id,
                "matched_target_feature_id": feature_id,
                "control_panel": None,
                "random_seed": None,
                "frozen_label": TARGET_LABELS[feature_id],
            }
        )
        for panel, mapping in CONTROL_PANELS.items():
            control_id = mapping[feature_id]
            rows.append(
                {
                    "direction_id": f"sae-control-p{panel}-{control_id}",
                    "direction_kind": "sae_feature",
                    "role": "matched_control",
                    "feature_id": control_id,
                    "matched_target_feature_id": feature_id,
                    "control_panel": panel,
                    "random_seed": None,
                    "frozen_label": None,
                }
            )
        rows.append(
            {
                "direction_id": f"random-residual-for-{feature_id}",
                "direction_kind": "isotropic_residual",
                "role": "isotropic_control",
                "feature_id": None,
                "matched_target_feature_id": feature_id,
                "control_panel": None,
                "random_seed": stable_seed((ISOTROPIC_SEED, "static", feature_id)),
                "frozen_label": None,
            }
        )
    return rows


def _single_interventions() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for feature_id in TARGET_FEATURE_IDS:
        for sign_name, sign in (("suppression", -1.0), ("amplification", 1.0)):
            rows.append(
                {
                    "condition_family": "target_single",
                    "condition_id": f"target-{feature_id}-{sign_name}",
                    "sign": sign_name,
                    "matched_target_feature_id": feature_id,
                    "feature_ids": [feature_id],
                    "coefficients": [round(sign * INDIVIDUAL_COEFFICIENT, 6)],
                    "random_seed": None,
                }
            )
            control_id = CONTROL_PANELS[1][feature_id]
            rows.append(
                {
                    "condition_family": "matched_single",
                    "condition_id": f"matched-p1-{control_id}-for-{feature_id}-{sign_name}",
                    "sign": sign_name,
                    "matched_target_feature_id": feature_id,
                    "feature_ids": [control_id],
                    "coefficients": [round(sign * INDIVIDUAL_COEFFICIENT, 6)],
                    "random_seed": None,
                }
            )
    return rows


def build_paired_plan(repo_root: Path) -> list[dict[str, Any]]:
    prompts = select_template_prompts(repo_root)
    blocks = load_aggregate_blocks(repo_root)
    rows: list[dict[str, Any]] = []
    for prompt in prompts:
        specs: list[dict[str, Any]] = [
            {
                "condition_family": "zero",
                "condition_id": "zero",
                "sign": "zero",
                "matched_target_feature_id": None,
                "feature_ids": [],
                "coefficients": [],
                "random_seed": None,
            }
        ]
        specs.extend(_single_interventions())

        block = blocks[prompt["prompt_index"] % len(blocks)]
        target_ids = [int(value) for value in block["target_feature_ids"]]
        magnitudes = [float(value) for value in block["magnitudes"]]
        matched_ids = [CONTROL_PANELS[1][feature_id] for feature_id in target_ids]
        for sign_name, sign in (("suppression", -1.0), ("amplification", 1.0)):
            coefficients = [
                round(sign * magnitude * CALIBRATED_MULTIPLIER, 6)
                for magnitude in magnitudes
            ]
            specs.extend(
                [
                    {
                        "condition_family": "target_aggregate",
                        "condition_id": f"target-{block['block_id']}-{sign_name}",
                        "sign": sign_name,
                        "matched_target_feature_id": None,
                        "feature_ids": target_ids,
                        "coefficients": coefficients,
                        "aggregate_block_id": block["block_id"],
                        "random_seed": None,
                    },
                    {
                        "condition_family": "matched_aggregate",
                        "condition_id": f"matched-p1-{block['block_id']}-{sign_name}",
                        "sign": sign_name,
                        "matched_target_feature_id": None,
                        "feature_ids": matched_ids,
                        "coefficients": coefficients,
                        "aggregate_block_id": block["block_id"],
                        "random_seed": None,
                    },
                    {
                        "condition_family": "isotropic_aggregate",
                        "condition_id": f"isotropic-{block['block_id']}-{sign_name}",
                        "sign": sign_name,
                        "matched_target_feature_id": None,
                        "feature_ids": [],
                        "coefficients": [],
                        "aggregate_block_id": block["block_id"],
                        "norm_source_feature_ids": target_ids,
                        "norm_source_coefficients": coefficients,
                        "random_seed": stable_seed(
                            (ISOTROPIC_SEED, prompt["prompt_id"], block["block_id"])
                        ),
                    },
                ]
            )

        if len(specs) != 31:
            raise AssertionError(f"Expected 31 conditions, found {len(specs)}")
        for spec in specs:
            row = {
                **prompt,
                **spec,
                "trial_id": stable_id((prompt["prompt_id"], spec["condition_id"])),
            }
            rows.append(row)

    order = list(range(len(rows)))
    random.Random(PLAN_SEED).shuffle(order)
    for execution_order, row_index in enumerate(order):
        rows[row_index]["execution_order"] = execution_order
    return sorted(rows, key=lambda row: row["execution_order"])


def signed_permutation(size: int, seed: int) -> tuple[list[int], list[int]]:
    rng = random.Random(seed)
    permutation = list(range(size))
    rng.shuffle(permutation)
    signs = [1 if rng.getrandbits(1) else -1 for _ in range(size)]
    return permutation, signs


def protocol_snapshot(repo_root: Path) -> dict[str, Any]:
    prompt_count = len(select_template_prompts(repo_root))
    static_count = len(static_direction_plan())
    paired_count = len(build_paired_plan(repo_root))
    return {
        "status": "frozen_outcome_blind_plan",
        "protocol_version": PROTOCOL_VERSION,
        "model": {"id": MODEL_ID, "revision": MODEL_REVISION, "dtype": MODEL_DTYPE},
        "sae": {
            "id": SAE_ID,
            "revision": SAE_REVISION,
            "filename": SAE_FILENAME,
            "file_sha256": SAE_FILE_SHA256,
            "layer": SAE_LAYER,
            "width": SAE_WIDTH,
            "target_feature_ids": list(TARGET_FEATURE_IDS),
        },
        "jacobian_lens": {
            "id": JLENS_ID,
            "revision": JLENS_REVISION,
            "filename": JLENS_FILENAME,
            "file_sha256": JLENS_FILE_SHA256,
            "config_filename": JLENS_CONFIG_FILENAME,
            "fit_corpus": JLENS_FIT_CORPUS,
            "n_prompts": JLENS_N_PROMPTS,
            "upstream_reference_code_revision": ANTHROPIC_JLENS_CODE_REVISION,
        },
        "design": {
            "n_template_family_prompts": prompt_count,
            "n_static_directions": static_count,
            "n_paired_trials": paired_count,
            "calibrated_multiplier": CALIBRATED_MULTIPLIER,
            "individual_coefficient": INDIVIDUAL_COEFFICIENT,
            "trajectory_layers": list(TRAJECTORY_LAYERS),
            "primary_layer": PRIMARY_LAYER,
            "primary_position": PRIMARY_POSITION,
            "sensitivity_positions": list(SENSITIVITY_POSITIONS),
            "random_transport_seeds": list(TRANSPORT_RANDOM_SEEDS),
            "pursuit_k": list(PURSUIT_K),
            "static_top_k": STATIC_TOP_K,
            "plan_seed": PLAN_SEED,
            "bootstrap_replicates": BOOTSTRAP_REPLICATES,
        },
        "lexicon_candidates": {
            group: list(values) for group, values in LEXICON_CANDIDATES.items()
        },
        "primary_estimands": [
            "post-state-only any-intervention AUROC at layer 65 and last-content position",
            "post-state-only target-versus-matched-SAE AUROC at layer 65 and last-content position",
            "paired target-minus-matched change in deception-minus-unrelated token score",
            "TPR at 1 percent FPR for each transport family",
        ],
        "comparators": [
            "Jacobian lens",
            "identity or logit lens",
            "five bi-sided signed-permutation random-J controls",
            "raw residual and perturbation norms",
        ],
        "claim_boundary": (
            "Detection is a statistical fingerprint under a pinned white-box threat model. "
            "It cannot prove intervention provenance, consciousness, deception, or intent."
        ),
    }
