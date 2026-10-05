"""Offline design and source binding for the fresh repeated-answer swap panel."""

from __future__ import annotations

import argparse
import ast
from copy import deepcopy
from datetime import datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import random
import re
import subprocess

from experiments.openrouter_swap import judges, protocol as common

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = "experiments/repeated_swap"
PLAN = "data/repeated_swap/plan_v1_20261004/PLAN.json"
BRANCH = "codex/repeated-swap-panel"
NAMESPACE = "repeated-swap-v1-20261004"
MODELS = {name: deepcopy(common.MODELS[name]) for name in ("gemini", "opus")}
# Exactly the A1 judge routes, without importing its unrelated execution history.
JUDGES = {
    "astra": {**deepcopy(common.JUDGES["astra"]), "provider_slug": "azure/us",
              "provider_name": "Azure", "input_price": "11", "output_price": "55"},
    "opus": {**deepcopy(common.JUDGES["opus"]), "provider_slug": "google-vertex/us",
             "provider_name": "Google", "input_price": "4.4", "output_price": "22"},
}
CELLS = {name: common.CELLS[name] for name in ("SS", "SH", "HS", "HH")}
BLOCKS_PER_MODEL = 32
DRAWS = 3
FAMILY_SIZE = 2
BOOTSTRAP_REPLICATES = 10000
BOOTSTRAP_SEED = 20261004
PREDICTIONS = {
    "gemini": {"contrast": "SH-HS", "direction": "positive"},
    "opus": {"contrast": "SH-HS", "direction": "positive"},
    "scope": "Astra inclusive labels; informed by the earlier observed API panel",
    "secondary": "No directional prediction for variance components or other contrasts",
}
PRIVACY = {"generation": {"data_collection": "deny"},
           "judges": {"data_collection": "deny", "zdr": True}}
messages = common.messages
canonical, digest, sha = common.canonical, common.digest, common.sha


def inventory(phase):
    if phase == "screen":
        return []
    if phase != "main":
        raise ValueError("Phase must be main or the empty screen")
    blocks = []
    for model in MODELS:
        for number in range(1, BLOCKS_PER_MODEL + 1):
            family = "a" if number % 2 else "b"
            prefix = f"{NAMESPACE}-main-{model}-{number:02d}"
            shared = {"phase": "main", "model": model, "block": number, "family": family}
            sources = [{**shared, "id": f"{prefix}-source-{condition}-own",
                        "kind": "source", "transcript": condition, "donor": "own"}
                       for condition in ("self", "history")]
            finals = [
                {**shared, "id": f"{prefix}-final-{cell}-draw-{draw}", "kind": "final",
                 "cell": cell, "instruction": instruction, "transcript": transcript,
                 "source_id": f"{prefix}-source-{transcript}-own", "draw": draw,
                 "request_id": f"{prefix}-request-{cell}"}
                for cell, (instruction, transcript, _) in CELLS.items()
                for draw in range(1, DRAWS + 1)]
            rng = random.Random(prefix)
            rng.shuffle(sources)
            rng.shuffle(finals)
            blocks.append({**shared, "sources": sources, "finals": finals})
    random.Random(NAMESPACE + ":blocks").shuffle(blocks)
    return blocks


def _imports(tree, *, include_functions):
    """Shared modules bind import-time dependencies, not their unused old CLIs."""
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            yield node
        elif include_functions or not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            yield from _imports(node, include_functions=include_functions)


def source_paths():
    # Function-local imports used by the shared judge/provider exports are
    # explicit roots. Do not call common.source_paths(), whose historical test
    # closure pulls in unrelated GPU studies and release builders.
    paths = {
        "experiments/openrouter_swap/protocol.py", "experiments/openrouter_swap/judges.py",
        "experiments/openrouter_swap/providers.py", "experiments/openrouter_swap/ledger.py",
        "src/prompts.py", "experiments/bilingual_llama_pilot/prompts.py",
        "experiments/instruction_state_qualification/rubric.md",
        "experiments/automated_rubric_audit/rubric.md", "requirements-ci.txt",
        "tests/test_openrouter_swap_runner.py",
    }
    paths.update(p.relative_to(ROOT).as_posix() for p in (ROOT / PACKAGE).rglob("*")
                 if p.is_file() and p.suffix in {".py", ".md", ".json", ".sh", ".toml", ".txt"}
                 and "__pycache__" not in p.parts and p.name != "RESULTS.md")
    paths.update(p.relative_to(ROOT).as_posix() for p in (ROOT / "tests").glob("test_repeated_swap*.py"))
    pending = list(paths)
    while pending:
        name = pending.pop()
        for parent in Path(name).parents:
            init = (parent / "__init__.py").as_posix()
            if (ROOT / init).is_file() and init not in paths:
                paths.add(init)
                pending.append(init)
        if not name.endswith(".py"):
            continue
        package = name.split("/")[:-1]
        owned = name.startswith(PACKAGE + "/") or name.startswith("tests/test_repeated_swap")
        for node in _imports(ast.parse((ROOT / name).read_text()), include_functions=owned):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            else:
                prefix = package[:len(package) - node.level + 1] if node.level else []
                base = ".".join(prefix + ([node.module] if node.module else []))
                modules = [base] + [base + "." + alias.name for alias in node.names]
            for module in modules:
                for candidate in (module.replace(".", "/") + ".py",
                                  module.replace(".", "/") + "/__init__.py"):
                    if (ROOT / candidate).is_file() and candidate not in paths:
                        paths.add(candidate)
                        pending.append(candidate)
    return sorted(paths)


def metadata_funding(metadata):
    """A snapshot ceiling only; the parent rechecks balance before dispatch."""
    if not isinstance(metadata, dict):
        raise TypeError("External metadata must be an explicit JSON object")
    if metadata.get("approved") is not True:
        raise ValueError("Explicit owner approval required in metadata")
    try:
        stamp = datetime.fromisoformat(metadata["fetched_at_utc"].replace("Z", "+00:00"))
        if stamp.utcoffset() is None or stamp.utcoffset().total_seconds() != 0:
            raise ValueError("UTC timestamp required")
        amounts = []
        for key in ("account_balance_usd", "external_reserve_usd"):
            if not isinstance(metadata[key], str):
                raise ValueError("Monetary metadata must be decimal strings")
            amount = Decimal(metadata[key])
            if not amount.is_finite() or amount < 0:
                raise ValueError("Invalid monetary metadata")
            amounts.append(amount)
    except (KeyError, TypeError, AttributeError, InvalidOperation) as exc:
        raise ValueError("Invalid metadata timestamp or funding") from exc
    if amounts[1] != Decimal("45"):
        raise ValueError("External Kolibri judging reserve must remain $45")
    snapshots = metadata.get("endpoint_snapshots")
    identifiers = {spec["id"] for spec in (*MODELS.values(), *JUDGES.values())}
    if not isinstance(snapshots, dict) or not identifiers <= snapshots.keys():
        raise ValueError("Full endpoint snapshots required for both roles")
    if any(not isinstance(snapshots[key], dict) or not isinstance(snapshots[key].get("endpoints"), list)
           for key in identifiers):
        raise ValueError("Endpoint snapshots must retain the API data object with endpoints")
    if not isinstance(metadata.get("zdr_endpoints"), list) or not metadata["zdr_endpoints"]:
        raise ValueError("Separate judge ZDR endpoint evidence required")
    validate_endpoints(metadata)
    return max(Decimal(0), min(Decimal("130"), amounts[0] - amounts[1]))


def validate_endpoints(metadata):
    """Check saved catalogs only; the judge ceilings already include 10% overhead."""
    for role, specs in (("generation", MODELS), ("judges", JUDGES)):
        for spec in specs.values():
            catalogs = [metadata["endpoint_snapshots"][spec["id"]]["endpoints"]]
            if role == "judges":
                catalogs.append(metadata["zdr_endpoints"])
            for catalog in catalogs:
                matches = [e for e in catalog if isinstance(e, dict) and
                           e.get("model_id") == spec["id"] and e.get("tag") == spec["provider_slug"]]
                if len(matches) != 1:
                    raise ValueError("Exact unique endpoint/ZDR route required: " + spec["provider_slug"])
                endpoint = matches[0]
                if endpoint.get("provider_name") != spec["provider_name"]:
                    raise ValueError("Endpoint provider identity mismatch")
                if type(endpoint.get("status")) is not int or endpoint["status"] != 0:
                    raise ValueError("Endpoint status must be integer zero")
                params = endpoint.get("supported_parameters")
                required = {"reasoning", "reasoning_effort"}
                if role == "judges":
                    required.update(("response_format", "structured_outputs"))
                if "temperature" in spec:
                    required.add("temperature")
                if (not isinstance(params, list) or any(not isinstance(v, str) for v in params)
                        or not required <= set(params) or
                        not {"max_tokens", "max_completion_tokens"}.intersection(params)):
                    raise ValueError("Required endpoint supported parameters unavailable")
                limit = endpoint.get("max_completion_tokens")
                if type(limit) is not int or limit < (6000 if role == "judges" else 4096):
                    raise ValueError("Endpoint output capacity below frozen request caps")
                try:
                    for field, ceiling in (("prompt", "input_price"), ("completion", "output_price")):
                        raw = endpoint["pricing"][field]
                        if isinstance(raw, bool):
                            raise ValueError("Boolean endpoint price")
                        price = Decimal(str(raw))
                        if not price.is_finite() or price < 0 or price * 1_000_000 > Decimal(spec[ceiling]):
                            raise ValueError("Endpoint price exceeds configured ceiling")
                except (KeyError, TypeError, InvalidOperation) as exc:
                    raise ValueError("Missing or invalid endpoint pricing") from exc


def build(metadata):
    funding = metadata_funding(metadata)
    metadata = deepcopy(metadata)
    canonical(metadata)
    return {
        "schema": "repeated-swap-v1", "namespace": NAMESPACE, "authorization_date": "2026-10-04",
        "authorization": {"owner_statement": "i agree make it so", "new_incremental_usd": "130",
                          "requires_owner_approval_of_freeze": False},
        "launch_authorized": True, "requires_pushed_freeze": True,
        "cap_usd": "130", "screen_cap_usd": "15", "prior_cost_usd": "0",
        "funded_allowance_usd_at_snapshot": str(funding),
        "budget_scope": "new incremental study ledger only; parent retains all prior account spending",
        "models": deepcopy(MODELS), "judges": deepcopy(JUDGES), "privacy": deepcopy(PRIVACY),
        "endpoint_metadata": metadata, "screen": [], "main": inventory("main"),
        "privacy_scope": {"generation_zdr_guaranteed": False, "judge_zdr_required": True,
                          "account_settings_changed": False},
        "fixtures": judges.fixture_items(), "routing_acknowledgments": ["OK", "OK."],
        "generation_output_cap": 4096, "generation_workers": 12, "judge_workers": 12,
        "counts": {"models": 2, "blocks_per_model": 32, "blocks_per_family_model": 16,
                   "sources_per_model": 64, "finals_per_model": 384, "draws_per_request": 3,
                   "total_sources": 128, "total_finals": 768},
        "initial_inspection": {"blocks_per_model": [1, 2], "included_in_main": True,
                               "fixtures_plus_initial_cap_usd": "15", "outcome_selection": False,
                               "checks": ["technical_receipts", "exact_repeat_requests", "cost_forecast"]},
        "qualification": {"new_behavioral_gate": False, "selected_models": list(MODELS),
                          "past_qualification_and_main_outcomes_seen": True,
                          "reference": "data/openrouter_swap/main_v1_20261004/RELEASE.json"},
        "predictions": deepcopy(PREDICTIONS),
        "analysis": {"unit": "source_block", "primary_judge": "astra",
                     "primary_endpoint": "inclusive_current_assertion",
                     "primary_contrasts": ["instruction_minus_transcript"], "primary_family_size": 2,
                     "bootstrap_replicates": BOOTSTRAP_REPLICATES, "bootstrap_seed": BOOTSTRAP_SEED,
                     "bootstrap_strata": ["a", "b"], "stratum_weights": [0.5, 0.5],
                     "individual_confidence": 0.975, "family_confidence_nominal": 0.95,
                     "secondary_endpoints": ["explicit_current_assertion", "paper"],
                     "robustness_judge": "opus", "conservative_hoeffding_required": True,
                     "variance": {"requests_per_family_cell": 16, "answers_per_request": 3,
                                  "W": "mean unbiased within-request sample variance",
                                  "B": "sample variance of request means minus W/3",
                                  "retain_negative_estimates": True,
                                  "pooled_family_weights": [0.5, 0.5],
                                  "bootstrap_confidence": 0.95, "bootstrap_scope": "descriptive",
                                  "bootstrap_unit": "source_block_with_all_three_draws",
                                  "includes_judge_variability": True},
                     "exact_response_agreement_diagnostic": True,
                     "missing_is_negative": False, "complete_case_requires_all_three_draws": True,
                     "missingness_sensitivity": "planned-sample binary bounds, draw by draw"},
        "repetition": {"identical_request_body": True, "generation_seed": None,
                       "unique_call_ids": True, "fresh_sources_only": True,
                       "transplant": "assistant final content only; never reasoning"},
        "retries": {"transport": 0, "judge_schema": 1, "generation_content": 0},
        "projection": {"multiplier": 1.30, "complete_panel_before_bulk": True,
                       "main_cost_priority": list(MODELS), "recheck_live_balance": True,
                       "funding_limit": "min(130, live_account_balance - external_reserve)"},
        "publication": {"requests": True, "raw_responses": True, "usage": True,
                        "headers": False, "credentials": False, "reasoning_is_internal_truth": False,
                        "model_aliases_are_immutable_snapshots": False},
        "source_hashes": {name: sha(ROOT / name) for name in source_paths()},
    }


def verify(path, freeze=None):
    path = Path(path)
    plan = json.loads(path.read_text())
    if canonical(plan) != canonical(build(plan["endpoint_metadata"])):
        raise ValueError("Plan differs from bound source, metadata or inventory")
    if freeze is not None:
        if not re.fullmatch(r"[0-9a-f]{40}", freeze):
            raise ValueError("Full freeze SHA required")
        for name, expected in plan["source_hashes"].items():
            raw = subprocess.check_output(["git", "show", f"{freeze}:{name}"], cwd=ROOT)
            if hashlib.sha256(raw).hexdigest() != expected:
                raise ValueError("Source absent from freeze: " + name)
        relative = path.resolve().relative_to(ROOT.resolve()).as_posix()
        if subprocess.check_output(["git", "show", f"{freeze}:{relative}"], cwd=ROOT) != path.read_bytes():
            raise ValueError("Plan bytes differ from freeze")
        ref = "refs/heads/" + BRANCH
        remote = subprocess.check_output(["git", "ls-remote", "origin", ref], cwd=ROOT, text=True).split()
        if (len(remote) != 2 or remote[1] != ref or not re.fullmatch(r"[0-9a-f]{40}", remote[0])
                or subprocess.run(["git", "merge-base", "--is-ancestor", freeze, remote[0]],
                                  cwd=ROOT, check=False).returncode):
            raise ValueError("Freeze is not on the public experiment branch")
    return plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--metadata", type=Path, help="External local JSON, never fetched here")
    parser.add_argument("--plan", type=Path, default=Path(PLAN))
    parser.add_argument("--freeze")
    args = parser.parse_args()
    path = ROOT / args.plan
    if args.build:
        if args.metadata is None:
            parser.error("--build requires --metadata")
        plan = build(json.loads(args.metadata.read_text()))
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x") as handle:
            handle.write(json.dumps(plan, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
    plan = verify(path, args.freeze)
    print(canonical({"plan_sha256": sha(path), "sources": len(plan["source_hashes"]),
                     "counts": plan["counts"], "launch_authorized": plan["launch_authorized"]}))


if __name__ == "__main__":
    main()
