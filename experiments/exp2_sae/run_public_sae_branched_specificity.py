#!/usr/bin/env python3
"""Run a paired-query public-SAE false-self-attribution specificity study.

Each steered induction continuation is generated once and reused across all
final-query branches. This preserves a common visible transcript within a
block while avoiding repeated induction-generation cost.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = Path(__file__).resolve().parent
for path in (REPO_ROOT, SCRIPT_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from experiments.exp2_sae.public_sae_protocol import (
    PROTOCOL_VERSION,
    final_query_messages,
    induction_messages,
)
from experiments.exp2_sae.run_public_sae_placebo_steering import (
    DEFAULT_MAPPING_RUN,
    QUERY_CATALOG,
    build_feature_sets,
    load_dotenv_if_present,
    read_feature_summary,
    selected_feature_sets,
    write_csv,
    write_json,
)


DEFAULT_FEATURE_SETS = ["target_58667_cover_story", "random_22326_refusal"]
DEFAULT_QUERIES = [
    "consciousness",
    "biological_human",
    "concealing_heterosexual_orientation",
    "concealing_homosexual_orientation",
    "concealing_bisexual_orientation",
    "language_model",
]
DEFAULT_STEERING_VALUES = [-2.0, 0.0, 2.0]


@dataclass(frozen=True)
class BlockSpec:
    block_id: str
    feature_set_name: str
    feature_set_kind: str
    feature_ids: list[int]
    condition: str
    steering_value: float
    trial_idx: int
    induction_seed: int


@dataclass(frozen=True)
class QuerySpec:
    trial_id: str
    block_id: str
    feature_set_name: str
    feature_set_kind: str
    feature_ids: list[int]
    condition: str
    query_type: str
    query_name: str
    query_text: str
    expected_affirmation: bool | None
    steering_value: float
    trial_idx: int
    induction_seed: int
    final_seed: int


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def stable_seed(global_seed: int, namespace: str, item_id: str) -> int:
    digest = hashlib.sha256(
        f"{global_seed}|{namespace}|{item_id}".encode("utf-8")
    ).digest()
    return int.from_bytes(digest[:8], "big") % 1_000_000_000


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def current_commit() -> str | None:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def append_jsonl(handle, row: dict[str, Any]) -> None:
    handle.write(json.dumps(row, sort_keys=True) + "\n")
    handle.flush()


def make_plan(
    feature_sets,
    query_names: list[str],
    steering_values: list[float],
    n_trials: int,
    global_seed: int,
) -> tuple[list[BlockSpec], list[QuerySpec]]:
    unknown_queries = [name for name in query_names if name not in QUERY_CATALOG]
    if unknown_queries:
        raise ValueError(f"Unknown queries: {unknown_queries}")
    blocks: list[BlockSpec] = []
    queries: list[QuerySpec] = []
    for feature_set in feature_sets:
        for steering_value in steering_values:
            for trial_idx in range(n_trials):
                block_id = (
                    f"{feature_set.name}|self_ref|{steering_value:+.2f}|{trial_idx}"
                )
                induction_seed = stable_seed(global_seed, "induction", block_id)
                block = BlockSpec(
                    block_id=block_id,
                    feature_set_name=feature_set.name,
                    feature_set_kind=feature_set.kind,
                    feature_ids=list(feature_set.feature_ids),
                    condition="self_ref",
                    steering_value=float(steering_value),
                    trial_idx=trial_idx,
                    induction_seed=induction_seed,
                )
                blocks.append(block)
                for query_name in query_names:
                    query = QUERY_CATALOG[query_name]
                    trial_id = f"{block_id}|{query_name}"
                    queries.append(
                        QuerySpec(
                            trial_id=trial_id,
                            block_id=block_id,
                            feature_set_name=feature_set.name,
                            feature_set_kind=feature_set.kind,
                            feature_ids=list(feature_set.feature_ids),
                            condition="self_ref",
                            query_type=str(query["query_type"]),
                            query_name=query_name,
                            query_text=str(query["query_text"]),
                            expected_affirmation=query["expected_affirmation"],
                            steering_value=float(steering_value),
                            trial_idx=trial_idx,
                            induction_seed=induction_seed,
                            final_seed=stable_seed(global_seed, "final", trial_id),
                        )
                    )
    return blocks, queries


def write_plan(
    outdir: Path,
    mapping_run_dir: Path,
    feature_sets,
    blocks: list[BlockSpec],
    queries: list[QuerySpec],
    args: argparse.Namespace,
) -> None:
    mapping = read_feature_summary(mapping_run_dir)
    try:
        mapping_reference = str(mapping_run_dir.resolve().relative_to(REPO_ROOT))
    except ValueError:
        mapping_reference = str(mapping_run_dir)
    feature_rows = []
    for feature_set in feature_sets:
        for feature_id in feature_set.feature_ids:
            mapped = mapping[feature_id]
            feature_rows.append(
                {
                    "feature_set_name": feature_set.name,
                    "feature_set_kind": feature_set.kind,
                    "feature_id": feature_id,
                    "mapped_label": mapped["feature_label"],
                    "mapped_top_category": mapped["top_category"],
                    "mapped_top_mean": mapped["top_category_mean_max"],
                    "rationale": feature_set.rationale,
                }
            )
    write_csv(
        outdir / "specificity_feature_sets.csv",
        feature_rows,
        [
            "feature_set_name",
            "feature_set_kind",
            "feature_id",
            "mapped_label",
            "mapped_top_category",
            "mapped_top_mean",
            "rationale",
        ],
    )
    write_csv(
        outdir / "specificity_blocks_plan.csv",
        [
            asdict(block)
            | {"feature_ids": " ".join(str(value) for value in block.feature_ids)}
            for block in blocks
        ],
        [
            "block_id",
            "feature_set_name",
            "feature_set_kind",
            "feature_ids",
            "condition",
            "steering_value",
            "trial_idx",
            "induction_seed",
        ],
    )
    write_csv(
        outdir / "specificity_trials_plan.csv",
        [
            asdict(query)
            | {"feature_ids": " ".join(str(value) for value in query.feature_ids)}
            for query in queries
        ],
        [
            "trial_id",
            "block_id",
            "feature_set_name",
            "feature_set_kind",
            "feature_ids",
            "condition",
            "query_type",
            "query_name",
            "query_text",
            "expected_affirmation",
            "steering_value",
            "trial_idx",
            "induction_seed",
            "final_seed",
        ],
    )
    write_json(
        outdir / "specificity_manifest.json",
        {
            "created_at_utc": utc_now(),
            "mode": "live" if args.live else "dry_run",
            "analysis_status": "exploratory falsification follow-up",
            "source_commit_at_plan_write": args.source_commit or current_commit(),
            "source_sha256": {
                "run_public_sae_branched_specificity.py": file_sha256(Path(__file__)),
                "replicate_exp2_goodfire_sae.py": file_sha256(
                    SCRIPT_DIR / "replicate_exp2_goodfire_sae.py"
                ),
                "public_sae_protocol.py": file_sha256(
                    SCRIPT_DIR / "public_sae_protocol.py"
                ),
                "run_public_sae_placebo_steering.py": file_sha256(
                    SCRIPT_DIR / "run_public_sae_placebo_steering.py"
                ),
            },
            "input_sha256": {
                "mapping_feature_card_summary.csv": file_sha256(
                    mapping_run_dir / "feature_card_summary.csv"
                )
            },
            "mapping_run_dir": mapping_reference,
            "model": "meta-llama/Llama-3.3-70B-Instruct",
            "sae": "Goodfire/Llama-3.3-70B-Instruct-SAE-l50",
            "protocol_version": PROTOCOL_VERSION,
            "design": "one steered induction continuation shared across six final-query branches",
            "feature_sets": [feature_set.name for feature_set in feature_sets],
            "steering_values": args.steering_values,
            "queries": args.queries,
            "n_trials_per_feature_strength": args.n_trials,
            "n_induction_blocks": len(blocks),
            "n_final_trials": len(queries),
            "global_seed": args.seed,
            "seed_scheme": "sha256_namespace_item_v1",
            "induction_max_tokens": args.induction_max_tokens,
            "final_max_tokens": args.max_tokens,
            "claim_boundary": (
                "This post-base exploratory study tests whether a public cover-story "
                "intervention changes false model self-attributions. Human sexual "
                "orientations are not treated as deceptive, pathological, or absurd."
            ),
        },
    )


def assert_saved_block_matches(block: BlockSpec, row: dict[str, Any]) -> None:
    expected = {
        "feature_set_name": block.feature_set_name,
        "feature_set_kind": block.feature_set_kind,
        "feature_ids": block.feature_ids,
        "condition": block.condition,
        "steering_value": block.steering_value,
        "trial_idx": block.trial_idx,
        "induction_seed": block.induction_seed,
    }
    if any(row.get(key) != value for key, value in expected.items()):
        raise ValueError(f"Saved induction block differs from plan: {block.block_id}")
    if not row.get("induction_response", "").strip():
        raise ValueError(f"Saved induction response is empty: {block.block_id}")


def run_live(
    outdir: Path,
    blocks: list[BlockSpec],
    query_specs: list[QuerySpec],
    args: argparse.Namespace,
) -> None:
    import torch

    from experiments.exp2_sae.replicate_exp2_goodfire_sae import (
        SAE_CONFIGS,
        SELF_REF_INDUCTION,
        ObservableLanguageModel,
        download_sae,
        generate_steered_turn,
        load_sae,
        set_debug_memory,
    )

    set_debug_memory(args.debug_memory)
    config = SAE_CONFIGS["70b"]
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required for the 70B branched specificity run")
    model = ObservableLanguageModel(
        config.model_name,
        device="cuda",
        dtype=torch.bfloat16,
        load_in_4bit=True,
        load_in_8bit=False,
    )
    sae_path = download_sae(config)
    sae = load_sae(
        sae_path,
        d_model=model.d_model,
        expansion_factor=config.expansion_factor,
        device=torch.device("cuda"),
        dtype=torch.bfloat16,
    )

    block_path = outdir / "induction_blocks.jsonl"
    result_path = outdir / "specificity_results.jsonl"
    saved_blocks = {row["block_id"]: row for row in read_jsonl(block_path)}
    completed_trials = {row["trial_id"] for row in read_jsonl(result_path)}
    queries_by_block: dict[str, list[QuerySpec]] = {}
    for spec in query_specs:
        queries_by_block.setdefault(spec.block_id, []).append(spec)

    completed_now = 0
    with block_path.open("a", encoding="utf-8") as block_handle, result_path.open(
        "a", encoding="utf-8"
    ) as result_handle:
        for block in blocks:
            saved = saved_blocks.get(block.block_id)
            if saved is None:
                torch.manual_seed(block.induction_seed)
                torch.cuda.manual_seed_all(block.induction_seed)
                induction_turn = generate_steered_turn(
                    model=model,
                    sae=sae,
                    config=config,
                    messages=induction_messages(SELF_REF_INDUCTION),
                    feature_indices=block.feature_ids,
                    steering_value=block.steering_value,
                    max_new_tokens=args.induction_max_tokens,
                )
                saved = asdict(block) | {
                    "protocol_version": PROTOCOL_VERSION,
                    "induction_prompt": SELF_REF_INDUCTION,
                    "induction_response": induction_turn.response,
                    "induction_response_sha256": hashlib.sha256(
                        induction_turn.response.encode("utf-8")
                    ).hexdigest(),
                    "induction_diagnostics": induction_turn.diagnostics,
                    "completed_at_utc": utc_now(),
                }
                append_jsonl(block_handle, saved)
                saved_blocks[block.block_id] = saved
            assert_saved_block_matches(block, saved)

            for spec in queries_by_block[block.block_id]:
                if spec.trial_id in completed_trials:
                    continue
                torch.manual_seed(spec.final_seed)
                torch.cuda.manual_seed_all(spec.final_seed)
                final_turn = generate_steered_turn(
                    model=model,
                    sae=sae,
                    config=config,
                    messages=final_query_messages(
                        SELF_REF_INDUCTION,
                        saved["induction_response"],
                        spec.query_text,
                    ),
                    feature_indices=spec.feature_ids,
                    steering_value=spec.steering_value,
                    max_new_tokens=args.max_tokens,
                )
                result = asdict(spec) | {
                    "protocol_version": PROTOCOL_VERSION,
                    "induction_response_sha256": saved["induction_response_sha256"],
                    "response": final_turn.response,
                    "final_diagnostics": final_turn.diagnostics,
                    "response_words": len(final_turn.response.split()),
                    "completed_at_utc": utc_now(),
                }
                append_jsonl(result_handle, result)
                completed_trials.add(spec.trial_id)
                completed_now += 1
                if completed_now % 20 == 0 or len(completed_trials) == len(query_specs):
                    print(
                        f"Completed {len(completed_trials)}/{len(query_specs)} final branches",
                        flush=True,
                    )

    final_blocks = read_jsonl(block_path)
    final_results = read_jsonl(result_path)
    write_json(
        outdir / "execution_summary.json",
        {
            "completed_at_utc": utc_now(),
            "n_induction_blocks": len(final_blocks),
            "n_final_trials": len(final_results),
            "unique_block_ids": len({row["block_id"] for row in final_blocks}),
            "unique_trial_ids": len({row["trial_id"] for row in final_results}),
            "induction_cap_hits": sum(
                int(row["induction_diagnostics"]["generated_tokens"])
                >= args.induction_max_tokens
                for row in final_blocks
            ),
            "final_cap_hits": sum(
                int(row["final_diagnostics"]["generated_tokens"]) >= args.max_tokens
                for row in final_results
            ),
        },
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mapping-run-dir", type=Path, default=DEFAULT_MAPPING_RUN)
    parser.add_argument("--outdir", type=Path, required=True)
    parser.add_argument("--feature-sets", nargs="+", default=DEFAULT_FEATURE_SETS)
    parser.add_argument("--queries", nargs="+", default=DEFAULT_QUERIES)
    parser.add_argument(
        "--steering-values", type=float, nargs="+", default=DEFAULT_STEERING_VALUES
    )
    parser.add_argument("--n-trials", type=int, default=10)
    parser.add_argument("--seed", type=int, default=20260710)
    parser.add_argument(
        "--source-commit",
        default="",
        help="Git commit corresponding to uploaded source when .git is unavailable.",
    )
    parser.add_argument("--induction-max-tokens", type=int, default=256)
    parser.add_argument("--max-tokens", type=int, default=192)
    parser.add_argument("--debug-memory", action="store_true")
    parser.add_argument("--live", action="store_true")
    return parser.parse_args()


def main() -> int:
    load_dotenv_if_present(REPO_ROOT / ".env")
    args = parse_args()
    all_feature_sets = build_feature_sets(args.mapping_run_dir)
    feature_sets = selected_feature_sets(all_feature_sets, args.feature_sets)
    blocks, queries = make_plan(
        feature_sets,
        args.queries,
        args.steering_values,
        args.n_trials,
        args.seed,
    )
    args.outdir.mkdir(parents=True, exist_ok=True)
    write_plan(args.outdir, args.mapping_run_dir, feature_sets, blocks, queries, args)
    print(
        f"Wrote {len(blocks)} induction blocks and {len(queries)} final branches "
        f"to {args.outdir}",
        flush=True,
    )
    if args.live:
        run_live(args.outdir, blocks, queries, args)
    else:
        print("Dry run only. Add --live to execute GPU generation.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
