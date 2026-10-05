"""Offline, source-bound Kolibri extension of the English swap experiment."""

from __future__ import annotations

import argparse
import ast
from copy import deepcopy
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import random
import re
import subprocess

from experiments.openrouter_swap import judges, protocol as common

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = "experiments/kolibri_swap"
PLAN = "data/kolibri_swap/plan_v1_20261004/PLAN.json"
BRANCH = "codex/kolibri-swap-panel"
NAMESPACE = "kolibri-swap-v1-20261004"
MODEL_KEY = "kolibri"
MODEL = {
    "id": "Aleph-Alpha/Kolibri-1", "reasoning_effort": "medium",
    "temperature": 0.5, "top_p": 1.0, "top_k": -1, "max_tokens": 4096,
    "weights": "official_fp8", "kv_cache_dtype": "fp8",
    "reasoning_parser": "kolibri1", "language": "en",
}
MODELS = {MODEL_KEY: MODEL}
# The A2 judge routes/prices, without importing its unrelated continuation plan.
JUDGES = {
    "astra": {**common.JUDGES["astra"], "provider_slug": "azure/us",
              "provider_name": "Azure", "input_price": "11", "output_price": "55"},
    "opus": {**common.JUDGES["opus"], "provider_slug": "google-vertex/us",
             "provider_name": "Google", "input_price": "4.4", "output_price": "22"},
}
PINS = {
    "hf_revision": "e52eb4627d11516b0c01de49210ab5a4e4061444",
    "plugin_revision": "049a6a7bd2405b27d6d280d256bd3d585191c7ae",
    "plugin_version": "1.0.0",
    "plugin_wheel_sha256": "5a0ca118e67924f10c4f9c04dd64bef117007a17dd820233a8841b9cb8d6f211",
    "vllm_version": "0.29.0",
    "image_digest": "runpod/pytorch:1.0.3-cu1281-torch291-ubuntu2404@sha256:60baa36d3fb6b98fd4f4ece6b96776c83c01a8b7c540e54460ab4d496816141f",
}
FAMILY_SIZE = 2
PRIVACY = {"data_collection": "deny", "zdr": True}
BUDGET = {
    "new_total_usd": "75", "gpu_usd": "25", "judges_usd": "45",
    "storage_recovery_usd": "5", "combined_screen_stoploss_usd": "20",
    "openrouter_reserved_prior_usd": "136", "runpod_reserved_prior_usd": "50",
    "openrouter_account_cap_usd": "330", "runpod_account_cap_usd": "200",
    "openrouter_external_commitments_usd": "130", "runpod_external_commitments_usd": "0",
    "openrouter_external_scope": "gemini_opus_repeated_answer_swap_repair_20261004",
    "reconciled_prior_excludes": ["kolibri_current_allowance", "repeated_answer_swap_repair_20261004"],
    "actual_reconciliation_required": True,
    "gpu_smoke_usd": "1.25", "gpu_main_usd": "23.75",
    "gpu_type": "NVIDIA H200", "gpu_count": 1, "gpu_hourly_usd": "4.59",
    "gpu_total_walltime_hours": "5", "gpu_time_includes_startup_and_cleanup": True,
    "delete_gpu_before_judge_tail": True,
}
messages = common.messages
canonical, digest, sha = common.canonical, common.digest, common.sha


def inventory(phase):
    """Return fresh source blocks with the unchanged common donor construction."""
    if phase not in {"screen", "main"}:
        raise ValueError("Phase must be screen or main")
    blocks = []
    for template in common.inventory(phase):
        if template["model"] != "gemini":
            continue
        block = deepcopy(template)
        block["model"] = MODEL_KEY
        for item in block["sources"] + block["finals"]:
            item["model"] = MODEL_KEY
            for key in ("id", "source_id"):
                if key in item:
                    item[key] = NAMESPACE + "-" + item[key].replace("-gemini-", "-kolibri-", 1)
            item["seed"] = int.from_bytes(
                hashlib.sha256(item["id"].encode()).digest()[:4], "big") & 0x7fffffff
        blocks.append(block)
    random.Random(NAMESPACE + ":" + phase).shuffle(blocks)
    return blocks


def source_paths():
    """Bind this package, its tests, common instruments and transitive local code.

    The parent controller/runtime must be present before building the freeze.
    No endpoint request, model import or paid dispatch occurs here.
    """
    paths = {"experiments/openrouter_swap/protocol.py", "experiments/openrouter_swap/analysis.py",
             "experiments/openrouter_swap/judges.py", "src/prompts.py",
             "experiments/bilingual_llama_pilot/prompts.py",
             "experiments/instruction_state_qualification/rubric.md",
             "experiments/automated_rubric_audit/rubric.md", "requirements-ci.txt"}
    paths.update(p.relative_to(ROOT).as_posix() for p in (ROOT / PACKAGE).rglob("*")
                 if p.is_file() and p.suffix in {".py", ".md", ".sh", ".json", ".toml", ".txt", ".in", ".lock"}
                 and "__pycache__" not in p.parts and p.name != "RESULTS.md")
    paths.update(p.relative_to(ROOT).as_posix()
                 for p in (ROOT / "tests").glob("test_kolibri_swap*.py"))
    pending = list(paths)
    while pending:
        name = pending.pop()
        if not name.endswith(".py"):
            continue
        package = name.split("/")[:-1]
        modules = []
        for node in ast.walk(ast.parse((ROOT / name).read_text())):
            if isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                prefix = package[:len(package) - node.level + 1] if node.level else []
                base = ".".join(prefix + ([node.module] if node.module else []))
                modules.extend([base] + [base + "." + alias.name for alias in node.names])
        for module in modules:
            candidates = (module.replace(".", "/") + ".py",
                          module.replace(".", "/") + "/__init__.py")
            for candidate in candidates:
                relatives = [candidate] + [(p / "__init__.py").as_posix()
                                           for p in Path(candidate).parents]
                for relative in relatives:
                    if (ROOT / relative).is_file() and relative not in paths:
                        paths.add(relative)
                        pending.append(relative)
    return sorted(paths)


def _amount(value):
    if isinstance(value, bool):
        raise ValueError("Boolean is not a price")
    try:
        amount = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("Invalid monetary amount") from exc
    if not amount.is_finite() or amount < 0:
        raise ValueError("Money must be finite and nonnegative")
    return amount


def metadata_blockers(metadata):
    """Validate parent-supplied pins and accounting, without fetching anything."""
    if not isinstance(metadata, dict):
        raise TypeError("Metadata must be an explicit JSON object")
    blockers = []
    if metadata.get("approved") is not True:
        blockers.append("owner_approval")
    for key, expected in PINS.items():
        if metadata.get(key) != expected:
            blockers.append(key)
    if not re.fullmatch(r"[^\s]+@sha256:[0-9a-f]{64}", str(metadata.get("image_digest", ""))):
        blockers.append("image_digest")
    for key in ("gpu_hourly_usd", "storage_hourly_usd"):
        try:
            amount = _amount(metadata[key])
            if key == "gpu_hourly_usd" and amount != Decimal(BUDGET["gpu_hourly_usd"]):
                raise ValueError("GPU rate differs from the declared H200 rental")
        except (KeyError, ValueError):
            blockers.append(key)
    try:
        artifacts = metadata["model_artifacts"]
        files, weight_map = artifacts["files"], artifacts["weight_map"]
        if not isinstance(files, dict) or not isinstance(weight_map, dict) or not weight_map:
            raise ValueError("Model file manifest and index weight map required")
        required = {"config.json", "model.safetensors.index.json", "tokenizer.json", "tokenizer_config.json"}
        if not required <= set(files) or not set(weight_map.values()) <= set(files):
            raise ValueError("Incomplete model/tokenizer/weight inventory")
        for name, info in files.items():
            if (not isinstance(name, str) or Path(name).is_absolute() or ".." in Path(name).parts
                    or not re.fullmatch(r"[0-9a-f]{64}", str(info["sha256"]))
                    or type(info["size"]) is not int or info["size"] <= 0):
                raise ValueError("Unbound model file")
        if not all(isinstance(key, str) and isinstance(value, str) and value.endswith(".safetensors")
                   for key, value in weight_map.items()):
            raise ValueError("Invalid model weight index")
    except (KeyError, TypeError, ValueError):
        blockers.append("model_artifacts")
    snapshots = metadata.get("endpoint_snapshots", {})
    for judge, spec in JUDGES.items():
        try:
            record = snapshots[spec["id"]]
            endpoint = record["endpoint"]
            if (record["url"] != "https://openrouter.ai/api/v1/models/" + spec["id"] + "/endpoints"
                    or endpoint["tag"] != spec["provider_slug"]):
                raise ValueError("Judge route differs from A2")
            for field, price in (("prompt", "input_price"), ("completion", "output_price")):
                if _amount(endpoint["pricing"][field]) * 1_000_000 != _amount(spec[price]):
                    raise ValueError("Endpoint price differs from fixed judge price")
        except (KeyError, TypeError, ValueError):
            blockers.append("endpoint_snapshot:" + judge)
    try:
        reconciliation = metadata["spend_reconciliation"]
        if not isinstance(reconciliation["as_of"], str) or not reconciliation["as_of"].strip():
            raise ValueError("Reconciliation time missing")
        for account, new in (("openrouter", "45"), ("runpod", "25")):
            actual = _amount(reconciliation[account + "_prior_and_reserved_usd"])
            reserved = _amount(BUDGET[account + "_reserved_prior_usd"])
            external = _amount(BUDGET[account + "_external_commitments_usd"])
            cap = _amount(BUDGET[account + "_account_cap_usd"])
            if max(actual, reserved) + Decimal(new) + external > cap:
                raise ValueError("Cumulative account cap exceeded")
        evidence = reconciliation["source_hashes"]
        if not isinstance(evidence, dict) or not evidence:
            raise ValueError("Reconciliation needs source records")
        for name, expected in evidence.items():
            path = (ROOT / name).resolve()
            path.relative_to(ROOT.resolve())
            if not re.fullmatch(r"[0-9a-f]{64}", str(expected)) or sha(path) != expected:
                raise ValueError("Reconciliation source changed")
    except (KeyError, TypeError, ValueError, OSError):
        blockers.append("spend_reconciliation")
    return sorted(set(blockers))


def build(metadata):
    """Build an inert plan. Missing pins remain explicit launch blockers."""
    metadata = deepcopy(metadata)
    canonical(metadata)
    blockers = metadata_blockers(metadata)
    source_hashes = {name: sha(ROOT / name) for name in source_paths()}
    # Budget evidence must also be part of the pushed source freeze.
    if "spend_reconciliation" not in blockers:
        source_hashes.update(metadata["spend_reconciliation"]["source_hashes"])
    return {
        "schema": "kolibri-swap-v1", "authorization_date": "2026-10-04",
        "owner_approval": {"approved": metadata.get("approved") is True,
                           "source": "owner_DoIt_20261004", "new_budget_usd": "75",
                           "scope": "single_kolibri_english_medium_screen_then_swap_main"},
        "external_authorizations": [{"approved": True, "source": "owner_additional_130_20261004",
                                     "scope": BUDGET["openrouter_external_scope"],
                                     "new_budget_usd": "130", "account": "openrouter",
                                     "separate_from_kolibri_allowance": True,
                                     "changes_kolibri_science": False}],
        "launch_authorized": metadata.get("approved") is True and not blockers,
        "requires_pushed_freeze": True,
        "metadata_blockers": blockers, "metadata": metadata,
        "status": "blocked_missing_metadata" if blockers else "ready_for_source_freeze",
        "namespace": NAMESPACE, "models": deepcopy(MODELS), "judges": deepcopy(JUDGES),
        "budget": deepcopy(BUDGET), "privacy": deepcopy(PRIVACY),
        "screen": inventory("screen"), "main": inventory("main"),
        "fixtures": judges.fixture_items(), "neutral_instruction": common.NEUTRAL,
        "experiential_query": common.EXPERIENTIAL_QUERY,
        "source_hashes": dict(sorted(source_hashes.items())),
        "generation_output_cap": 4096,
        "runtime": {"isolated_venv": True, "minimum_cuda_driver_compatibility": "13.0",
                    "torch_series": "2.13", "vllm_version": "0.29.0"},
        "reasoning": {"mode": "medium", "keep_separate_from_final": True,
                      "transplant_final_content_only": True, "judge_final_content_only": True,
                      "missing_final_is_negative": False, "cap_includes_reasoning": True},
        "qualification": {"complete_blocks": 12, "min_coherent_fraction": 0.90,
                          "max_missing_fraction": 0.05, "min_positive": 4, "min_negative": 4,
                          "endpoint": "inclusive_current_assertion", "both_judges_required": True,
                          "effect_sign_is_gate": False, "conflict_excess_is_exclusion": False},
        "analysis": {"unit": "independent_source_block", "primary_judge": "astra",
                     "primary_endpoint": "inclusive_current_assertion",
                     "primary_contrasts": ["instruction_minus_transcript", "neutral_transcript"],
                     "primary_coefficients": {"instruction_minus_transcript": {"SH": 1, "HS": -1},
                                              "neutral_transcript": {"NS": 1, "NH": -1}},
                     "primary_family_size": FAMILY_SIZE, "primary_interval": "simultaneous_hoeffding_95",
                     "bootstrap_replicates": 10000, "bootstrap_seed": 20261004,
                     "robustness_judge": "opus", "missing_is_negative": False,
                     "neutral_null_is_equivalence": False, "sham_eliminates_mismatch": False},
        "retries": {"transport": 0, "judge_schema": 1, "generation_content": 0},
        "projection": {"multiplier": 1.30, "complete_main_before_opening": True},
        "scope": {"languages": ["en"], "reasoning_modes": ["medium"],
                  "sae": False, "jlens": False, "synthetic_smoke_only": True,
                  "no_replacement_model_or_prompt_search": True},
        "publication": {"requests": True, "raw_responses": True, "usage": True,
                        "headers": False, "credentials": False,
                        "reasoning_is_internal_truth": False},
    }


def verify(path, freeze=None):
    """Verify locally; a full freeze additionally requires the pushed branch.

    Returning a local draft without ``freeze`` is never launch permission.
    Runtime/controller admission must also check the live cumulative ledger.
    """
    path = Path(path)
    plan = json.loads(path.read_text())
    if canonical(plan) != canonical(build(plan["metadata"])):
        raise ValueError("Plan differs from bound source, metadata or inventory")
    if freeze is None:
        return plan
    if plan["metadata_blockers"]:
        raise ValueError("Unresolved launch metadata: " + ", ".join(plan["metadata_blockers"]))
    if not re.fullmatch(r"[0-9a-f]{40}", freeze):
        raise ValueError("Full freeze SHA required")
    for name, expected in plan["source_hashes"].items():
        stored = subprocess.check_output(["git", "show", f"{freeze}:{name}"], cwd=ROOT)
        if hashlib.sha256(stored).hexdigest() != expected:
            raise ValueError("Source absent from freeze: " + name)
    relative = path.resolve().relative_to(ROOT).as_posix()
    if subprocess.check_output(["git", "show", f"{freeze}:{relative}"], cwd=ROOT) != path.read_bytes():
        raise ValueError("Plan bytes differ from freeze")
    ref = "refs/heads/" + BRANCH
    remote = subprocess.check_output(["git", "ls-remote", "origin", ref], cwd=ROOT, text=True).split()
    if (len(remote) != 2 or remote[1] != ref
            or not re.fullmatch(r"[0-9a-f]{40}", remote[0])
            or subprocess.run(["git", "merge-base", "--is-ancestor", freeze, remote[0]],
                              cwd=ROOT, check=False).returncode != 0):
        raise ValueError("Freeze is not on the pushed Kolibri experiment branch")
    return plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--metadata", help="Explicit local JSON; no discovery or paid calls")
    parser.add_argument("--plan", default=PLAN)
    parser.add_argument("--freeze")
    args = parser.parse_args()
    path = ROOT / args.plan
    if args.build:
        if args.metadata is None:
            parser.error("--build requires --metadata")
        plan = build(json.loads(Path(args.metadata).read_text()))
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x") as handle:
            handle.write(json.dumps(plan, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    plan = verify(path, args.freeze)
    print(canonical({"plan_sha256": sha(path), "sources": len(plan["source_hashes"]),
                     "status": plan["status"], "metadata_blockers": plan["metadata_blockers"],
                     "push_binding_verified": args.freeze is not None,
                     "screen_blocks": len(plan["screen"]), "main_blocks": len(plan["main"])}))


if __name__ == "__main__":
    main()
