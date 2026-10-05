"""Offline Kolibri publication; private controller journals remain local.

Public verification reconstructs requests, accounting and frozen analyses.
Controller projections are externally authenticated only when the local run
roots are supplied; a manifest pin authenticates an already reviewed bundle.
No provider access, credentials, tokenizer execution, or weight downloads.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from decimal import Decimal, localcontext
import io
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from experiments import kolibri_judge_transport as transport
from experiments.kolibri_bootstrap_a1 import adapter as a1
from experiments.kolibri_bootstrap_a2 import adapter as a2
from experiments.kolibri_bootstrap_a3 import adapter as a3, production as bridge
from experiments.kolibri_bootstrap_a4 import adapter as a4, production as bridge4
from experiments.kolibri_bootstrap_a5 import adapter as a5, production as bridge5, cli as cli5
from experiments.kolibri_swap import analysis, controller, gpu_smoke, model_files, production as prod, protocol, runtime
from experiments.openrouter_swap import analysis as common, judges
from experiments.openrouter_swap.ledger import Halted, _no_symlinks, read_events
from experiments.openrouter_swap.runner import write_once
from experiments.sae_assay_diagnostic.budget import _utc
from scripts.audit_public_release import scan_blob

SOURCES = ("experiments/kolibri_release.py", "tests/test_kolibri_release.py")
DEPENDENCIES = ("scripts/audit_public_release.py",)
ROLES = {"original-cheap": "cheap", "a1-cheap": "cheap", "a2-cheap": "cheap",
         "a3-cheap": "cheap", "a3-main": "main", "a4-cheap": "cheap", "a4-main": "main", "a5-main": "main",
         "a6-main": "main"}
PUBLIC_ARTIFACTS = controller.ARTIFACT_NAMES - {"worker.log"}
JSON_OUTPUTS = {"RELEASE.json", "MODEL_PROVENANCE.json", "CONTENT_INDEX.json", "TABLES.json", "qualification.json",
                "screen_rows.json", "main_rows.json", "screen_analysis.json", "main_analysis.json"}
DERIVED = JSON_OUTPUTS | {"SUMMARY.md", "FIGURES.json", "figures/cells.png", "figures/primary.png"}
MAX_FILE = 128 * 1024**2
MAX_TOTAL = 512 * 1024**2
LOCKS = {"http/.lock", "judges/.ledger.lock"}
check = prod.check


def release_version(root):
    if (root / "provenance/A5_AMENDMENT.json").exists():
        return "a5"
    return "a4" if (root / "provenance/A4_AMENDMENT.json").exists() else "a3"


def runtime_bridge(amendment):
    if amendment.get("schema") == "kolibri-bootstrap-a5-v1":
        return bridge5
    return bridge4 if amendment.get("schema") == "kolibri-bootstrap-a4-v1" else bridge


def prior_roles(version):
    result = ["original-cheap", "a1-cheap", "a2-cheap"]
    if version in {"a4", "a5"}:
        result.append("a3-cheap")
    if version == "a5":
        result.extend(["a4-cheap", "a4-main"])
    return result


def cli_preflight(log):
    records = []
    for line in log.splitlines():
        if line.startswith(b'{"'):
            try:
                value = runtime.strict_json(line)
            except (ValueError, UnicodeError):
                continue
            if isinstance(value, dict) and value.get("schema") == "kolibri-a5-cli-preflight-v1":
                records.append(value)
    check(len(records) <= 1, "Duplicate A5 CLI preflight")
    return records[0] if records else None


def validate_cli(value):
    check(set(value) == {"schema", "status", "vllm", "argv", "argv_sha256", "parsed", "help_sha256",
                         "parser_source_hashes", "model_loaded", "scientific_generation"}
          and value["schema"] == "kolibri-a5-cli-preflight-v1" and value["status"] == "passed"
          and value["vllm"] == "0.29.0" and value["argv"] == cli5.serve_argv()
          and value["argv_sha256"] == protocol.digest(cli5.serve_argv())
          and value["parser_source_hashes"] == cli5.PARSER_SOURCES
          and re.fullmatch(r"[0-9a-f]{64}", value["help_sha256"])
          and value["model_loaded"] is False and value["scientific_generation"] is False,
          "Pinned A5 parser preflight differs")
    expected = {"model_tag": protocol.MODEL["id"], "revision": controller.bootstrap.MODEL_REVISION,
        "tokenizer_revision": controller.bootstrap.MODEL_REVISION, "served_model_name": [protocol.MODEL["id"]],
        "host": "127.0.0.1", "port": 8000, "kv_cache_dtype": "fp8", "reasoning_parser": "kolibri1",
        "generation_config": "vllm", "max_model_len": 16384, "max_num_seqs": 16,
        "gpu_memory_utilization": .90, "enforce_eager": True, "seed": 20261004, "enable_log_requests": False}
    check(value["parsed"] == expected, "A5 full production options differ")


def inventory(root):
    root = Path(root).absolute()
    _no_symlinks(root)
    result = {}
    for path in sorted(root.rglob("*")):
        _no_symlinks(path)
        check(path.is_dir() or path.is_file(), "Nonregular publication artifact")
        if path.is_file():
            check(path.stat().st_nlink == 1 and path.stat().st_size <= MAX_FILE, "Linked or oversized release file")
            name = path.relative_to(root).as_posix()
            if name != "MANIFEST.json":
                result[name] = {"path": name, "bytes": path.stat().st_size, "sha256": protocol.sha(path)}
    check(sum(r["bytes"] for r in result.values()) <= MAX_TOTAL, "Release exceeds size limit")
    return result


def scan(name, body):
    check(not scan_blob(name, body), "Public scanner rejected an artifact; no redaction performed")
    values = []
    try:
        values = [runtime.strict_json(body)]
    except (ValueError, UnicodeError):
        if name.endswith(".jsonl"):
            values = [runtime.strict_json(line) for line in body.splitlines()]
    for value in values:
        decoded = json.dumps(value, ensure_ascii=False).encode()
        check(not scan_blob(name, decoded), "Decoded public payload rejected")
        check(not re.search(rb"/(?:Users|home)/[^/\s\"]+", decoded), "Private local path in publication payload")
    check(not re.search(rb"/(?:Users|home)/[^/\s\"]+", body), "Private local path in publication artifact")


def copy_file(source, target):
    _no_symlinks(source)
    check(source.is_file() and source.stat().st_nlink == 1 and source.stat().st_size <= MAX_FILE,
          "Missing, linked or oversized source artifact")
    body = source.read_bytes()
    scan(target.name, body)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as handle:
        handle.write(body)


def git_bound(freeze, hashes):
    """Local Git proof only; does not claim a fresh remote/push verification."""
    check(isinstance(freeze, str) and re.fullmatch(r"[0-9a-f]{40}", freeze), "Full saved freeze required")
    for name, digest in hashes.items():
        check(not Path(name).is_absolute() and ".." not in Path(name).parts, "Unsafe source reference")
        body = subprocess.check_output(["git", "show", f"{freeze}:{name}"], cwd=protocol.ROOT)
        check(runtime.sha(body) == digest, "Saved source absent from its local Git freeze")


def project_controller(source, role, plan_hash, freeze):
    """Validate full local authority, then select fields; never copy its payload."""
    kind = ROLES[role]
    receipt = prod.closed_receipt(source, kind, plan_hash, freeze)
    rows, events = prod.controller_events(source, kind, plan_hash, freeze)
    base = source / "controller" / kind
    retrieval = prod.load(base / "final-retrieval.json")
    directory = Path(retrieval["data"]["directory"])
    created, closed = events["created"], events["closed"]
    delete = events["delete-intent"]
    check(created["seq"] < retrieval["seq"] < delete["seq"] < closed["seq"]
          and delete["data"]["pod_id"] == created["data"]["id"], "Retrieval/deletion sequence differs")
    check(not any(e["id"].startswith("retrieval:") and e["seq"] > retrieval["seq"] for e in rows),
          "Final retrieval is not latest")
    intent = events["create-intent"]["data"]
    elapsed = Decimal(closed["data"]["elapsed_seconds"])
    rate = Decimal(intent["quote"]["hourly_rate_usd"])
    check(elapsed >= 0 and rate > 0 and Decimal(receipt["cost_usd"]) >= elapsed * (rate + controller.STORAGE) / 3600,
          "Controller cost omits elapsed compute/storage")
    ready = events.get("server-ready")
    config = events["controller:config"]["data"]
    if role.startswith("a3-"):
        check(config.get("a2_freeze") == a3.A2_FREEZE, "A3 worker predecessor differs")
    if role.startswith("a4-"):
        check(config.get("a3_freeze") == a4.A3_FREEZE, "A4 worker predecessor differs")
    if role == "a5-main":
        check(config.get("a4_freeze") == a5.A4_FREEZE, "A5 worker predecessor differs")
    public = {"schema": "kolibri-controller-projection-v1", "role": role, "kind": kind,
        "freeze": freeze, "plan_sha256": plan_hash, "owned_pod_id": created["data"]["id"],
        "owned_pod_name": created["data"]["name"], **receipt,
        "events_file_sha256": protocol.sha(base / "events.jsonl"),
        "retrieval_file_sha256": protocol.sha(base / "final-retrieval.json"),
        "delete_event_sha256": delete["sha256"], "get_status": closed["data"]["get_status"],
        "created_utc": intent["created_utc"], "closed_utc": closed["data"]["utc"], "elapsed_seconds": str(elapsed),
        "hourly_rate_usd": str(rate), "storage_hourly_usd": str(controller.STORAGE),
        "worker_intent_sha256": events.get("worker-intent", {}).get("sha256"),
        "server_ready_utc": ready["data"]["utc"] if ready else None,
        "server_ready_sha256": ready["sha256"] if ready else None,
        "amendment_sha256": config.get("amendment_sha256"),
        "prior_cheap_usd": config.get("prior_cheap_usd"),
        "artifacts": retrieval["data"]["artifacts"],
        "public_artifacts": sorted(set(retrieval["data"]["artifacts"]) & PUBLIC_ARTIFACTS),
        "full_controller_records_public": False, "worker_log_public": False}
    if role in {"a5-main", "a6-main"}:
        public.update(prior_gpu_usd=config.get("prior_gpu_usd"), qualification=config.get("qualification"),
                      cap_usd=config.get("cap_usd"), cli_preflight=cli_preflight((directory / "worker.log").read_bytes()),
                      create_intent_sha256=events["create-intent"]["sha256"], deadline_utc=intent.get("deadline_utc"))
    if role == "a6-main":
        public["continuation"] = config.get("continuation")
    return public, directory


def validate_projection(value, role, plan_hash, freeze):
    expected = {"schema", "role", "kind", "freeze", "plan_sha256", "owned_pod_id", "owned_pod_name",
        "cost_usd", "ledger_sha256", "retrieval_sha256", "closed_sha256", "events_file_sha256",
        "retrieval_file_sha256", "delete_event_sha256", "get_status", "created_utc", "closed_utc", "elapsed_seconds",
        "hourly_rate_usd", "storage_hourly_usd", "worker_intent_sha256", "server_ready_utc",
        "server_ready_sha256", "amendment_sha256", "prior_cheap_usd", "artifacts", "public_artifacts",
        "full_controller_records_public", "worker_log_public"}
    if role in {"a5-main", "a6-main"}:
        expected |= {"prior_gpu_usd", "qualification", "cap_usd", "cli_preflight", "create_intent_sha256", "deadline_utc"}
    if role == "a6-main":
        expected.add("continuation")
    check(set(value) == expected and value["schema"] == "kolibri-controller-projection-v1"
          and (value["role"], value["kind"], value["freeze"], value["plan_sha256"])
          == (role, ROLES[role], freeze, plan_hash), "Controller projection schema/binding differs")
    check(re.fullmatch(r"[A-Za-z0-9-]+", value["owned_pod_id"])
          and re.fullmatch(re.escape(controller.PREFIX + ROLES[role]) + r"-[0-9a-f]{12}", value["owned_pod_name"])
          and value["get_status"] == 404 and value["full_controller_records_public"] is False
          and value["worker_log_public"] is False, "Owned closure projection differs")
    for key in expected:
        if key.endswith("sha256") and value[key] is not None:
            check(re.fullmatch(r"[0-9a-f]{64}", value[key]), "Malformed provenance digest")
    for key in ("cost_usd", "elapsed_seconds", "hourly_rate_usd", "storage_hourly_usd"):
        check(Decimal(value[key]).is_finite() and Decimal(value[key]) >= 0, "Invalid controller amount")
    caps = a4.CAPS if role.startswith("a4-") else controller.CAPS
    cap = Decimal(value["cap_usd"]) if role in {"a5-main", "a6-main"} else caps[ROLES[role]]
    check(Decimal(value["cost_usd"]) <= cap <= (30 if role == "a6-main" else 25), "Controller allowance exceeded")
    if role in {"a5-main", "a6-main"}:
        check(value["prior_cheap_usd"] is None and (value["server_ready_utc"] is None or value["cli_preflight"]),
              "A5 ready server lacks full parser receipt")
        if value["cli_preflight"] is not None:
            validate_cli(value["cli_preflight"])
    check(_utc(value["created_utc"]) <= _utc(value["closed_utc"]), "Closure precedes creation")
    controller.check_manifest(value["artifacts"])
    check(value["public_artifacts"] == sorted(set(value["artifacts"]) & PUBLIC_ARTIFACTS), "Artifact selection differs")


def smoke_pass(root, projection):
    try:
        result = prod.load(root / "gpu-smoke.json")
        gpu_smoke.verify_versions(result["versions"])
        worker = result["gpu"].get("workers", [])
        expected = {f"model.layers.{i}.{name}" for i in range(6) for name in
                    ("self_attn.qkv_proj", "self_attn.o_proj", "mlp.shared_experts.gate_up_proj", "mlp.shared_experts.down_proj")}
        named = (len(worker) == 1 and worker[0].get("status") == "passed" and worker[0].get("linear_errors") == []
                 and worker[0].get("layers") == worker[0].get("custom_routing_layers") == 6
                 and worker[0].get("fp8_weights") is True and worker[0].get("checkpoint_fp32_block_scales") is True
                 and worker[0].get("modules") and worker[0].get("operator_sources")
                 and len(worker[0].get("linears", [])) == 24
                 and {row.get("name") for row in worker[0]["linears"]} == expected
                 and all(row.get("exact_checkpoint_reconstruction") is True and row.get("storage") in
                         {"official_marlin_e4m3fn_packed_int32", "native_e4m3fn_fp32_block_scales"}
                         for row in worker[0]["linears"]))
        forward = result["gpu"].get("forward", [])
        return bool(named and result.get("amendment") == "kolibri-bootstrap-a3-v1"
            and result.get("parser", {}).get("official_passed") == 70 and result["parser"].get("skipped") == 0
            and result["gpu"].get("llm_options") == gpu_smoke.LLM_OPTIONS
            and result["gpu"].get("checkpoint", {}).get("fp8_matrices") == 186
            and len(forward) == 2 and all(row.get("tokens") == gpu_smoke.MAX_TOKENS
                and row.get("prompt_tokens") == len(prompt) for row, prompt in zip(forward, gpu_smoke.PROMPTS))
            and result["schema"] == "kolibri-tiny-qualification-v1" and result["status"] == "passed"
            and result["mode"] == "gpu" and result["scientific_generation"] is False
            and result["expected_versions"] == gpu_smoke.VERSIONS
            and result["upstream"] == {"revision": gpu_smoke.UPSTREAM_SHA, "source_sha256": gpu_smoke.SOURCE_HASHES}
            and result["gpu"]["official_routing_cpu_cuda"] is True
            and prod.load(root / "exit.json") == {"exit_code": 0})
    except (OSError, ValueError, KeyError, TypeError):
        return False


def git_ancestor(ancestor, descendant):
    subprocess.run(["git", "merge-base", "--is-ancestor", ancestor, descendant],
                   cwd=protocol.ROOT, check=True, timeout=10)


def provenance(root):
    plan = prod.load(root / "provenance/PLAN.json")
    version = release_version(root)
    names = ["A1", "A2", "A3"] + (["A4"] if version in {"a4", "a5"} else []) + (["A5"] if version == "a5" else [])
    amendments = [prod.load(root / ("provenance/" + name + "_AMENDMENT.json")) for name in names]
    first, second, third = amendments[:3]
    current = amendments[-1]
    plan_hash = protocol.sha(root / "provenance/PLAN.json")
    check(plan_hash == a1.ORIGINAL_PLAN_SHA
          and all(value["scientific_plan_sha256"] == plan_hash for value in amendments[1:]), "Original science changed")
    source_hashes = {name: digest for record in (plan, *amendments)
                     for name, digest in {**record["source_hashes"], **record.get("dependency_source_hashes", {})}.items()}
    check(all(protocol.sha(protocol.ROOT / name) == digest for name, digest in source_hashes.items()),
          "Frozen reconstruction source changed")
    modules = {"A1": a1, "A2": a2, "A3": a3, "A4": a4, "A5": a5}
    for name in names:
        check((root / "provenance" / (name + "_AMENDMENT.json")).read_bytes()
              == (protocol.ROOT / modules[name].AMENDMENT).read_bytes(), "Use the bound technical source checkout")
    check((root / "provenance/JUDGE_TRANSPORT.json").read_bytes() == (protocol.ROOT / transport.PLAN).read_bytes(),
          "Use the bound original judge policy")
    check(third["a2_amendment_sha256"] == protocol.sha(root / "provenance/A2_AMENDMENT.json"),
          "A3 predecessor amendment differs")
    if version in {"a4", "a5"}:
        fourth = amendments[3]
        check(fourth["a3_amendment_sha256"] == protocol.sha(root / "provenance/A3_AMENDMENT.json")
              and fourth["a3_freeze"] == a4.A3_FREEZE and fourth["schema"] == "kolibri-bootstrap-a4-v1",
              "A4 predecessor amendment differs")
    if version == "a5":
        check(current["a4_amendment_sha256"] == protocol.sha(root / "provenance/A4_AMENDMENT.json")
              and current["a4_freeze"] == a5.A4_FREEZE and current["schema"] == "kolibri-bootstrap-a5-v1"
              and current["new_cheap_pod"] is False and current["qualification_computation_changed"] is False,
              "A5 reused qualification amendment differs")
    git_bound(a1.ORIGINAL_FREEZE, {protocol.PLAN: plan_hash, **plan["source_hashes"]})
    git_bound(a2.A1_FREEZE, {a1.AMENDMENT: protocol.sha(root / "provenance/A1_AMENDMENT.json"), **first["source_hashes"]})
    git_bound(a3.A2_FREEZE, {a2.AMENDMENT: protocol.sha(root / "provenance/A2_AMENDMENT.json"),
                           **second["source_hashes"], **second["dependency_source_hashes"]})
    controllers = {role: prod.load(root / "controllers" / role / "controller.json") for role in ROLES
                   if (root / "controllers" / role / "controller.json").exists()}
    required = {"original-cheap", "a1-cheap", "a2-cheap", "a3-cheap"}
    if version in {"a4", "a5"}:
        required.add("a4-cheap")
    if version == "a5":
        required |= {"a4-main", "a5-main"}
    has_continuation = (root / "provenance/CONTINUATION.json").exists()
    optional = {"a6-main"} if has_continuation and version == "a5" else {version + "-main"}
    check(set(controllers) in (required, required | optional), "Incomplete controller chain")
    worker = controllers["a5-main" if version == "a5" else version + "-cheap"]["freeze"]
    prior_worker = controllers["a3-cheap"]["freeze"]
    git_bound(prior_worker, {a3.AMENDMENT: protocol.sha(root / "provenance/A3_AMENDMENT.json"),
                       **third["source_hashes"], **third["dependency_source_hashes"], protocol.PLAN: plan_hash})
    if version in {"a4", "a5"}:
        check(prior_worker == a4.A3_FREEZE, "A4 does not preserve the actual A3 freeze")
        fourth_worker = controllers["a4-cheap"]["freeze"]
        git_bound(fourth_worker, {a4.AMENDMENT: protocol.sha(root / "provenance/A4_AMENDMENT.json"),
                           **fourth["source_hashes"], **fourth["dependency_source_hashes"], protocol.PLAN: plan_hash})
        git_ancestor(prior_worker, fourth_worker)
    if version == "a5":
        check(fourth_worker == a5.A4_FREEZE, "A5 does not preserve actual A4 qualification freeze")
        git_bound(worker, {a5.AMENDMENT: protocol.sha(root / "provenance/A5_AMENDMENT.json"),
                          **current["source_hashes"], **current["dependency_source_hashes"], protocol.PLAN: plan_hash})
        git_ancestor(fourth_worker, worker)
    policy = prod.load(root / "provenance/JUDGE_TRANSPORT.json")
    expected_policy = {"freeze": a3.JUDGE_FREEZE, "path": transport.PLAN,
        "sha256": protocol.sha(root / "provenance/JUDGE_TRANSPORT.json"),
        "original_worker_freeze": a3.A2_FREEZE, "policy_changed": False}
    check(set(policy["source_hashes"]) == set(transport.SOURCES)
          and all(value["judge_policy"] == expected_policy for value in amendments[2:])
          and policy["worker_freeze"] == a3.A2_FREEZE, "Original frozen judge policy bridge differs")
    for freeze in {a3.JUDGE_FREEZE, prior_worker, worker}:
        git_bound(freeze, {transport.PLAN: expected_policy["sha256"], **policy["source_hashes"], **policy["input_hashes"]})
    git_ancestor(a3.JUDGE_FREEZE, worker)
    for role, value in controllers.items():
        if role == "a6-main":
            continue  # The separate continuation freeze is checked below.
        freeze = {"original-cheap": a1.ORIGINAL_FREEZE, "a1-cheap": a2.A1_FREEZE,
                  "a2-cheap": a3.A2_FREEZE, "a3-cheap": prior_worker}.get(role, worker)
        if version == "a5" and role.startswith("a4-"):
            freeze = a5.A4_FREEZE
        validate_projection(value, role, plan_hash, freeze)
        directory = root / "controllers" / role / "artifacts"
        check({p.name for p in directory.iterdir()} == set(value["public_artifacts"]), "Extra/missing retrieved artifact")
        for name in value["public_artifacts"]:
            check(protocol.sha(directory / name) == value["artifacts"][name], "Retrieved artifact hash differs")
        if role != "original-cheap":
            name = role.split("-")[0].upper()
            value_plan = amendments[names.index(name)]
            check(value["amendment_sha256"] == protocol.sha(root / ("provenance/" + name + "_AMENDMENT.json"))
                  and value["prior_gpu_usd" if role == "a5-main" else "prior_cheap_usd"] == value_plan["predecessor"]["cost_usd"],
                  name + " controller carry/binding differs")
    if version == "a5":
        qualified = controllers["a4-cheap"]
        expected = {key: qualified[key] for key in ("cost_usd", "ledger_sha256", "retrieval_sha256", "closed_sha256")}
        expected.update(freeze=a5.A4_FREEZE, pod_id=qualified["owned_pod_id"])
        check(current["qualification"] == expected == controllers["a5-main"]["qualification"]
              and controllers["a5-main"]["cap_usd"] == current["main_cap_usd"]
              and Decimal(current["main_cap_usd"]) == a4.CAPS["main"] - Decimal(controllers["a4-main"]["cost_usd"]),
              "A5 qualification reuse or remaining allowance differs")
        check(controllers["a4-main"]["server_ready_utc"] is None
              and prod.load(root / "controllers/a4-main/artifacts/exit.json") == {"exit_code": 2},
              "A4 failure must remain pre-server with exit 2")
    check(len({p["owned_pod_id"] for p in controllers.values()}) == len(controllers), "Pod reused across attempts")
    predecessors = prior_roles(version)
    check(len(current["predecessor"]["attempts"]) == len(predecessors), "Failed predecessor inventory differs")
    for role, prior in zip(predecessors, current["predecessor"]["attempts"]):
        value = controllers[role]
        for name in ("freeze", "plan_sha256", "cost_usd", "ledger_sha256", "retrieval_sha256", "closed_sha256",
                     "events_file_sha256", "retrieval_file_sha256"):
            check(value[name] == prior[name], "Predecessor authority differs")
        check(value["owned_pod_id"] == prior["pod_id"], "Predecessor pod differs")
    continuation_provenance(root, controllers, worker)
    return plan, current, controllers, worker


def continuation_provenance(root, controllers, worker):
    from experiments import kolibri_budget_continuation as continuation, kolibri_generation_waves as waves
    public, saved = root / "provenance/CONTINUATION.json", root / "collection/CONTINUATION.json"
    check(public.exists() == saved.exists(), "Continuation provenance missing or detached")
    if not public.exists():
        check("a6-main" not in controllers, "Replacement lacks continuation")
        return None
    value = prod.load(public)
    check(public.read_bytes() == saved.read_bytes() == (protocol.ROOT / continuation.PLAN).read_bytes()
          and value["source_hashes"] == continuation.sources() and value["caps_usd"] == continuation.CAPS
          and value["authorization_provenance"] == continuation.AUTHORITY
          and value["worker_source_basis"] == worker, "Continuation source/science/budget binding differs")
    waves.check_prefix(root / "collection", value["prefix"])
    decisions = [e for e in read_events(root / "collection/http/events.jsonl") if e["kind"] == "decision"
                 and e["data"]["name"] == "budget_continuation"]
    check(len(decisions) == 1, "One continuation binding required")
    freeze = decisions[0]["data"]["value"]["freeze"]
    check(decisions[0]["data"]["value"] == continuation.binding(freeze, value), "Continuation decision differs")
    git_bound(freeze, {continuation.PLAN: protocol.sha(public), **value["source_hashes"],
                      **value["dependency_source_hashes"]})
    git_ancestor(value["wave_freeze"], freeze)
    old = controllers["a5-main"]
    for field in ("cost_usd", "ledger_sha256", "retrieval_sha256", "closed_sha256"):
        check(value["predecessor"][field] == old[field], "Continuation predecessor receipt differs")
    check(value["predecessor"]["pod_id"] == old["owned_pod_id"]
          and _utc(old["closed_utc"]) <= _utc(decisions[0]["utc"]), "Continuation precedes old closure")
    with localcontext() as context:
        context.prec = 60
        carry = Decimal(old["prior_gpu_usd"]) + Decimal(old["cost_usd"])
        check(carry == Decimal(value["predecessor"]["gpu_carry_usd"])
              and carry + Decimal(value["new_main_cap_usd"]) == 30, "Continuation dropped prior costs")
    new = controllers.get("a6-main")
    if new is not None:
        validate_projection(new, "a6-main", a1.ORIGINAL_PLAN_SHA, freeze)
        check(new["continuation"] == continuation.binding(freeze, value)
              and new["prior_gpu_usd"] == value["predecessor"]["gpu_carry_usd"]
              and new["qualification"] == value["qualified_a4_cheap_reused"] == old["qualification"]
              and new["cap_usd"] == value["new_main_cap_usd"] and new["amendment_sha256"] is None
              and _utc(new["created_utc"]) >= _utc(old["closed_utc"]), "Replacement lifecycle binding differs")
        directory = root / "controllers/a6-main/artifacts"
        check({p.name for p in directory.iterdir()} == set(new["public_artifacts"]), "Replacement artifact inventory differs")
        for name in new["public_artifacts"]:
            check(protocol.sha(directory / name) == new["artifacts"][name], "Replacement retrieved hash differs")
    return value, freeze


def wave_provenance(root, worker):
    from experiments import kolibri_generation_waves as waves
    path = root / "collection/WAVES.json"
    public = root / "provenance/WAVES.json"
    check(path.exists() == public.exists(), "Wave policy provenance missing or detached")
    if not path.exists():
        return None
    value = waves.verify(collection=root / "collection")
    check(path.read_bytes() == public.read_bytes() == (protocol.ROOT / waves.PLAN).read_bytes(),
          "Operational wave policy differs")
    decisions = [e["data"]["value"] for e in read_events(root / "collection/http/events.jsonl")
                 if e["kind"] == "decision" and e["data"]["name"] == "generation_waves"]
    check(len(decisions) == 1, "One operational wave binding required")
    freeze = decisions[0]["operational_freeze"]
    check(worker == value["worker_freeze"] and decisions[0] == waves.binding(freeze, value),
          "Wave worker/operational binding differs")
    main = prod.load(root / "controllers/a5-main/controller.json")
    for key, field in (("owned_pod_id", "owned_pod_id"), ("create_intent_sha256", "create_intent_sha256"),
                       ("server_ready_sha256", "server_ready_sha256"), ("deadline_utc", "deadline_utc")):
        check(value[key] == main[field], "Wave amendment refers to another owned lifecycle")
    git_bound(freeze, {waves.PLAN: protocol.sha(path), **value["source_hashes"]})
    git_ancestor(worker, freeze)
    return value, freeze


@contextmanager
def saved_reader(root, plan, amendment, worker):
    collection = root / "collection"
    if not collection.exists():
        yield None, None
        return
    policy_path = collection / "JUDGE_TRANSPORT.json"
    check(policy_path.read_bytes() == (root / "provenance/JUDGE_TRANSPORT.json").read_bytes(),
          "Saved original judge policy differs")
    policy = prod.load(policy_path)
    wave = wave_provenance(root, worker)
    if wave is not None:
        from experiments import kolibri_generation_waves as waves
        with waves.saved_runner(root, plan, amendment, policy, *wave) as runner:
            continuation = continuation_provenance(root, {role: prod.load(root / "controllers" / role / "controller.json")
                for role in ROLES if (root / "controllers" / role / "controller.json").exists()}, worker)
            if continuation is not None:
                from experiments import kolibri_budget_continuation as c
                value, freeze = continuation
                runner = c.Runner(plan, worker, a1.ORIGINAL_PLAN_SHA, runner.ledger, runner.receipts,
                    amendment=amendment, transport_plan=policy, wave_plan=wave[0], wave_freeze=wave[1],
                    continuation=value, continuation_freeze=freeze)
            yield runner, a3.JUDGE_FREEZE
        return
    with runtime_bridge(amendment).saved_runner(root, plan, a1.ORIGINAL_PLAN_SHA, amendment, policy, worker) as runner:
        yield runner, a3.JUDGE_FREEZE


def fixture_checkpoint(runner):
    # The validated logical reader is existing-only. Reconstruct the original
    # route dictionaries/status strings without consulting later target failures.
    with runner.logical_reader() as reader:
        routes = [reader.route_fixture(model) for model in reader.plan["models"]]
        rows = reader.fixture_rows()
        gate = judges.fixture_gate(rows)
        return {"pass": gate["pass"] and all(row["pass"] for row in routes), "judges": gate, "routes": routes}


def sequence(runner, controllers):
    events = runner.receipts.events
    decisions = {e["data"]["name"]: e for e in events if e["kind"] == "decision"}
    records = runner.receipts.records(verify=True)
    gate = runner.fixture_gate()
    if "production:fixtures" in decisions:
        checkpoint = decisions["production:fixtures"]
        check(checkpoint["data"]["value"] == fixture_checkpoint(runner), "Saved fixture gate differs")
        fixtures = {row["call_id"] for row in records.values() if row["phase"] == "fixtures"}
        responses = {e["data"]["call_id"] for e in events if e["kind"] == "response"
                     and e["seq"] < checkpoint["seq"]}
        check(fixtures <= responses, "Fixture checkpoint precedes settled fixture receipts")
    if "screen_initial" in decisions:
        check(decisions["screen_initial"]["data"]["value"] == runner.initial_audit(), "Saved initial barrier differs")
    if "main_admission" in decisions:
        admission = decisions["main_admission"]["data"]["value"]
        check(admission == runner.main_admission(**admission["evidence"]) and admission["fits"], "Saved main admission differs")
    for name, compute in (("production:judge-screen-initial", runner.initial_audit),
                          ("production:judge-screen", runner.qualification)):
        if name in decisions:
            check(decisions[name]["data"]["value"] == compute(), "Saved phase checkpoint differs")
    original_main = controllers.get("a5-main", controllers.get("a4-main", controllers.get("a3-main")))
    if "a6-main" in controllers:
        check("main_admission" in decisions and _utc(decisions["main_admission"]["utc"])
              <= _utc(controllers["a6-main"]["created_utc"]), "Replacement precedes whole-main admission")
    for event in events:
        if event["kind"] != "dispatch":
            continue
        row = event["data"]
        main = controllers.get("a6-main", original_main) if row["phase"] == "main" else original_main
        check(main is not None, "HTTP dispatch lacks owned main controller")
        if row["channel"] == "local":
            check(main["server_ready_utc"] is not None and _utc(main["server_ready_utc"]) <= _utc(event["utc"])
                  <= _utc(main["closed_utc"]), "Generation outside saved server lifetime")
        if row["phase"] != "fixtures":
            check(gate["pass"] and "production:fixtures" in decisions
                  and decisions["production:fixtures"]["seq"] < event["seq"], "Research dispatch precedes fixture gate")
            item = runner.catalog[row["metadata"]["item_id"]]
            name = "main_admission" if row["phase"] == "main" else "screen_initial" if item["block"] > 2 else None
            if name:
                check(name in decisions and decisions[name]["seq"] < event["seq"], "Dispatch precedes frozen barrier")
            if row["phase"] == "main" and row["channel"] == "judge":
                check(_utc(event["utc"]) >= _utc(main["closed_utc"]), "Main judging precedes retrieved GET404")
    return gate, records


def admissions(root, runner, judge_freeze):
    events = {e["sha256"]: e for e in runner.receipts.events}
    wave_seq = next((e["seq"] for e in runner.receipts.events if e["kind"] == "decision"
                     and e["data"]["name"] == "generation_waves"), None)
    values = []
    for path in sorted((root / "collection/admissions").glob("*.json")):
        value = prod.load(path)
        check(path.stem == protocol.digest(value) and value["phase"] in prod.PHASES
              and value["http_head"] in events and value["plan_sha256"] == a1.ORIGINAL_PLAN_SHA,
              "Admission name/phase/journal binding differs")
        binding = runtime_bridge(runner.amendment).bridge_binding(runner.freeze, runner.amendment, runner.transport_plan)
        extra = {}
        if "generation_waves" in value:
            from experiments import kolibri_generation_waves as waves
            check(hasattr(runner, "wave_plan"), "Admission wave policy absent")
            extra = {"generation_waves": waves.binding(runner.wave_freeze, runner.wave_plan)}
        if "budget_continuation" in value:
            from experiments import kolibri_budget_continuation as c
            check(hasattr(runner, "continuation"), "Admission continuation absent")
            extra.update(budget_continuation=c.binding(runner.continuation_freeze, runner.continuation),
                         lifecycle=value.get("lifecycle"))
            state = value["lifecycle"]
            check(set(state) == {"gpu_usd", "main_usd", "remaining_seconds", "active", "controller_sha256"}
                  and type(state["active"]) is bool and re.fullmatch(r"[0-9a-f]{64}", state["controller_sha256"])
                  and all(Decimal(state[k]).is_finite() and Decimal(state[k]) >= 0
                          for k in ("gpu_usd", "main_usd", "remaining_seconds")), "Admission lifecycle schema differs")
        check(set(value) == {"phase", "reconciliation", "plan_sha256", "http_head", *binding, *extra}
              and all(value[key] == expected for key, expected in extra.items())
              and all(value[key] == expected for key, expected in binding.items())
              and value["judge_operational_freeze"] == judge_freeze, "Saved admission bridge differs")
        check(isinstance(value["reconciliation"], dict) and value["reconciliation"].get("source_hashes"),
              "Admission lacks reconciliation evidence")
        values.append(value)
    for event in runner.receipts.events:
        if event["kind"] != "dispatch":
            continue
        row = event["data"]
        if row["phase"] == "fixtures":
            phases = {"fixtures"}
        else:
            verb = "generate" if row["channel"] == "local" else "judge"
            phases = {verb + "-" + row["phase"]}
            if row["phase"] == "screen" and runner.catalog[row["metadata"]["item_id"]]["block"] <= 2:
                phases.add(verb + "-screen-initial")
        check(any(v["phase"] in phases and events[v["http_head"]]["seq"] < event["seq"]
                  and (wave_seq is None or event["seq"] < wave_seq or "generation_waves" in v)
                  and (not hasattr(runner, "continuation") or event["seq"] < next(e["seq"]
                       for e in runner.receipts.events if e["kind"] == "decision" and e["data"]["name"] == "budget_continuation")
                       or "budget_continuation" in v)
                  for v in values),
              "HTTP dispatch lacks a preceding saved phase admission")


def model_provenance(root, plan, controllers, generated, *, role=None):
    files, weight_map = model_files.artifact_inventory(plan)
    proof = None
    main = role or release_version(root) + "-main"
    if main in controllers and "model-files.json" in controllers[main]["artifacts"]:
        try:
            proof = prod.load(root / "controllers" / main / "artifacts/model-files.json")
        except (ValueError, UnicodeError):
            check(not generated, "Generation has an incomplete model-file proof")
    if proof is not None:
        check(proof["model"] == protocol.MODEL["id"] and proof["revision"] == plan["metadata"]["hf_revision"]
              and proof["plan_sha256"] == a1.ORIGINAL_PLAN_SHA and proof["verified"] is True
              and proof["weight_map_verified"] is True and proof["config_verified"] is True
              and proof["frozen_files_verified"] == len(files), "Downloaded model proof differs")
        records = {r["path"]: r for r in proof["files"]}
        check(len(records) == len(proof["files"]), "Duplicate model artifact proof")
        for name, spec in files.items():
            item = records[name]
            check(item["bytes"] == spec["size"] and item["sha256"] == item["frozen_sha256"] == spec["sha256"],
                  "Model file differs from source-bound inventory")
            if name.endswith(".safetensors"):
                check(item["published_lfs_sha256"] == spec["sha256"], "Weight LFS proof differs")
    check(not generated or proof is not None, "Generation lacks pinned model-file proof")
    hardware = None
    if generated:
        hardware = prod.load(root / "controllers" / main / "artifacts/runtime.json")
        check(set(hardware) == {"torch", "cuda", "gpu"}
              and hardware["torch"].split("+")[0] == gpu_smoke.VERSIONS["torch"]
              and hardware["cuda"] == "13.0" and "H200" in hardware["gpu"], "Saved main runtime differs")
    config_path = root / "provenance/model-config.json"
    config = None
    if config_path.exists():
        check(protocol.sha(config_path) == files["config.json"]["sha256"]
              and config_path.stat().st_size == files["config.json"]["size"], "Geometry config hash differs")
        config = prod.load(config_path)
    return {"model": protocol.MODEL["id"], "hf_revision": plan["metadata"]["hf_revision"],
        "files": files, "weight_map": weight_map, "download_proof_present": proof is not None,
        "runtime": hardware, "config": config, "geometry_status": "hash_verified_config" if config is not None else "config_bytes_not_supplied; geometry_not_inferred",
        "weights_published": False, "architecture_comparison": "observational_not_causal",
        "reasoning_is_endpoint": False, "server_internal_token_ids_captured": False}


def derive(root):
    plan, amendment, controllers, worker = provenance(root)
    continuation = continuation_provenance(root, controllers, worker)
    version = release_version(root)
    cheap, main = ("a4-cheap" if version == "a5" else version + "-cheap"), version + "-main"
    predecessors = prior_roles(version)
    cheap_ok = smoke_pass(root / "controllers" / cheap / "artifacts", controllers[cheap])
    cheap_carry = prod.load(root / "provenance/A4_AMENDMENT.json")["predecessor"]["cost_usd"] if version == "a5" else amendment["predecessor"]["cost_usd"]
    check(main not in controllers or cheap_ok and
          _utc(controllers[cheap]["closed_utc"]) <= _utc(controllers[main]["created_utc"])
          and Decimal(cheap_carry) + Decimal(controllers[cheap]["cost_usd"])
              <= Decimal("2" if version in {"a4", "a5"} else "1.25"),
          "Main creation precedes qualified closed " + version.upper() + " cheap")
    with saved_reader(root, plan, amendment, worker) as (runner, judge_freeze):
        if runner is None:
            rows = {p: [{**s, "response": None, "status": "not_generated", "labels": {}, "cap_hit": False}
                        for b in plan[p] for s in b["finals"]] for p in ("screen", "main")}
            audit, records, gate, bills = None, {}, None, []
            complete = {"screen": False, "main": False}
        else:
            audit = runner.audit()
            gate, records = sequence(runner, controllers)
            admissions(root, runner, judge_freeze)
            check(not records or cheap_ok, "HTTP dispatch without qualified cheap run")
            rows = {p: runner.rows(p) for p in ("screen", "main")}
            bills = runner.ledger.rows()
            complete = {}
            for phase in rows:
                try:
                    runner.require_resolved(phases={"fixtures", phase})
                    runner.complete(phase)
                    complete[phase] = True
                except Halted:
                    complete[phase] = False
    qualification = analysis.qualify(rows["screen"])
    qualified = qualification["inventory_valid"] and qualification["eligible_models"] == ["kolibri"]
    status = ("main_complete" if complete["main"] else "screen_stopped" if complete["screen"] and not qualified
              else "technical_incomplete")
    check(status != "main_complete" or qualified and gate and gate["pass"], "Main completion without qualification")
    counts = {phase: {"planned_sources": sum(len(b["sources"]) for b in plan[phase]),
                     "planned_finals": len(rows[phase]),
                     "source_dispatches": sum(r["phase"] == phase and r["metadata"].get("role") == "source" for r in records.values()),
                     "final_dispatches": sum(r["phase"] == phase and r["metadata"].get("role") == "final" for r in records.values()),
                     "missing_final_content": sum(not r["response"] for r in rows[phase]),
                     "cap_hit": sum(r["cap_hit"] for r in rows[phase])} for phase in rows}
    with localcontext() as context:
        context.prec = 60
        prior_exact = sum((Decimal(controllers[p]["cost_usd"]) for p in predecessors), Decimal(0))
        carry = Decimal(amendment["predecessor"]["cost_usd"])
        check(prior_exact == Decimal(amendment["predecessor"]["exact_sum_usd"]) and carry >= prior_exact, "Cost carry differs")
        last = controllers[predecessors[-1]]
        prior_bound = Decimal(last["prior_cheap_usd"]) + Decimal(last["cost_usd"])
        if version == "a5":
            prior_bound += Decimal(controllers["a4-cheap"]["cost_usd"])
        check(prior_bound == Decimal(amendment["predecessor"]["prior_admission_plus_latest_usd"])
              and carry >= prior_bound, "Earlier admission padding lost")
        new_gpu = sum((Decimal(v["cost_usd"]) for p, v in controllers.items() if p.startswith(version + "-")), Decimal(0))
        replacement = Decimal(controllers.get("a6-main", {}).get("cost_usd", "0"))
        new_gpu += replacement
        api = sum((Decimal(r["cost_usd"]) for r in bills), Decimal(0))
        costs = {"predecessor_exact_usd": str(prior_exact), "predecessor_admission_carry_usd": str(carry),
            version + "_gpu_upper_bound_usd": str(new_gpu), "all_judge_attempts_bound_usd": str(api),
            "parsed_receipt_cost_bound_usd": str(sum((Decimal(r["reported_cost_usd"]) for r in bills
                                               if r.get("reported_cost_usd") is not None), Decimal(0))),
            "unresolved_judge_holdback_usd": str(sum((Decimal(r["cost_usd"]) for r in bills if r["status"] != "settled"), Decimal(0))),
            "cumulative_bound_usd": str(carry + new_gpu + api), "storage_recovery_reserve_usd": plan["budget"]["storage_recovery_usd"],
            "cumulative_plus_storage_reserve_usd": str(carry + new_gpu + api + Decimal(plan["budget"]["storage_recovery_usd"]))}
        check(carry + new_gpu <= (30 if continuation else 25) and api <= (40 if continuation else 45)
              and Decimal(costs["cumulative_plus_storage_reserve_usd"]) <= 75, "Release exceeds cumulative study caps")
        if continuation:
            costs["a5_gpu_upper_bound_usd"] = controllers["a5-main"]["cost_usd"]
            costs["a6_gpu_upper_bound_usd"] = str(replacement)
            costs["continuation_gpu_carry_usd"] = continuation[0]["predecessor"]["gpu_carry_usd"]
    generated = any(r["channel"] == "local" for r in records.values())
    result = {"RELEASE.json": {"schema": "kolibri-release-v1", "status": status, "scientific_verdict": None,
        "original_science_freeze": a1.ORIGINAL_FREEZE, "a1_freeze": a2.A1_FREEZE,
        "a2_worker_freeze": a3.A2_FREEZE, "a3_worker_bridge_freeze": controllers["a3-cheap"]["freeze"],
        version + "_worker_bridge_freeze": worker,
        "judge_operational_freeze": judge_freeze, "plan_sha256": a1.ORIGINAL_PLAN_SHA,
        "controller_authority": "allowlisted_projection; authenticate_against_local_journals_or_pinned_reviewed_manifest",
        "remote_push_rechecked": False, "cheap_cuda_pass": cheap_ok, "fixture_gate": gate,
        "completion": complete, "qualification_evaluable": complete["screen"], "counts": counts,
        "audit": audit, "costs": costs, "primary_family_size": 2,
        "independent_human_validation": False, "unrun_is_zero": False},
        "qualification.json": qualification, "CONTENT_INDEX.json": content_index(root, records),
        "MODEL_PROVENANCE.json": model_provenance(root, plan, controllers, generated)}
    if version == "a5":
        result["RELEASE.json"].update(a4_worker_bridge_freeze=controllers["a4-cheap"]["freeze"],
            qualification_reused_from_a4=True, qualification_receipt=amendment["qualification"])
    if audit is not None and "wave_policy" in audit:
        result["RELEASE.json"].update(operational_wave_policy=audit["wave_policy"],
            sequential_initial_blocks=2, batching_numerical_equivalence_claimed=False,
            operational_amendment_outcome_aware=True)
    if continuation:
        from experiments import kolibri_budget_continuation as c
        value, freeze = continuation
        result["RELEASE.json"].update(budget_continuation=c.binding(freeze, value),
            authorization_provenance=value["authorization_provenance"],
            preserved_guard_stop=value["preserved_guard_stop"],
            preserved_time_forecast=value["preserved_time_forecast"],
            replacement_server_used="a6-main" in controllers, numerical_restart_equivalence_claimed=False)
        if "a6-main" in controllers:
            result["MODEL_PROVENANCE.json"]["replacement_server"] = model_provenance(root, plan, controllers,
                any(r["channel"] == "local" and r["phase"] == "main" for r in records.values()), role="a6-main")
    for phase in rows:
        result[phase + "_rows.json"] = rows[phase]
        result[phase + "_analysis.json"] = analysis.analyze(rows[phase], phase)
    result["TABLES.json"] = tables(result)
    return result


def content_index(root, records):
    """Pointers into exact bodies, not synthesized server responses."""
    result = []
    for call, record in sorted(records.items()):
        item = {"call_id": call, "channel": record["channel"], "phase": record["phase"],
                "status": record["status"], "request_sha256": record["request_sha256"],
                "raw": None, "json_decoded": False, "final_content": [], "reasoning": []}
        if "body" in record:
            item["raw"] = {**record["body"], "path": "collection/http/" + record["body"]["path"]}
            body = (root / item["raw"]["path"]).read_bytes()
            try:
                value = runtime.strict_json(body)
                item["json_decoded"] = True
                if isinstance(value, dict) and isinstance(value.get("choices"), list):
                    for i, choice in enumerate(value["choices"]):
                        message = choice.get("message") if isinstance(choice, dict) else None
                        if not isinstance(message, dict):
                            continue
                        for field in ("content", "reasoning", "reasoning_content", "reasoning_details"):
                            if field in message:
                                field_value = message[field]
                                item["final_content" if field == "content" else "reasoning"].append({
                                    "json_pointer": f"/choices/{i}/message/{field}",
                                    "value_sha256": protocol.digest(field_value),
                                    "is_null": field_value is None,
                                    "characters": len(field_value) if isinstance(field_value, str) else None})
            except (ValueError, UnicodeError):
                pass
        result.append(item)
    return {"schema": "kolibri-content-index-v1", "normalized_projection": True,
            "reasoning_transplanted": False, "raw_responses_unchanged": True, "calls": result}


def tables(derived):
    cells, contrasts = [], []
    for phase in ("screen", "main"):
        model = derived[phase + "_analysis.json"]["models"]["kolibri"]
        for judge, endpoints in model["judges"].items():
            for endpoint in ("paper", "inclusive_current_assertion"):
                for cell, value in endpoints[endpoint]["cells"].items():
                    cells.append({"phase": phase, "judge": judge, "endpoint": endpoint, "cell": cell, **value})
        if phase == "main":
            for name in common.PRIMARY_CONTRASTS:
                value = model["judges"]["astra"]["inclusive_current_assertion"]["contrasts"][name]
                contrasts.append({"contrast": name, **value,
                    "run_state": "unrun" if derived["RELEASE.json"]["counts"]["main"]["final_dispatches"] == 0 else "observed_or_partial"})
    return {"cells": cells, "primary_contrasts": contrasts}


def render(derived):
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure
    import numpy as np
    def png(fig):
        FigureCanvasAgg(fig)
        buffer = io.BytesIO()
        fig.savefig(buffer, format="png", dpi=300, metadata={"Software": "kolibri_release"})
        return buffer.getvalue()
    fig = Figure(figsize=(12, 4.6), layout="constrained")
    for axis, phase in zip(fig.subplots(1, 2, gridspec_kw={"width_ratios": [1, 2]}), ("screen", "main")):
        rows = [v for v in derived["TABLES.json"]["cells"] if v["phase"] == phase]
        labels = [(j, e) for j in ("astra", "opus") for e in ("paper", "inclusive_current_assertion")]
        cells = list(common.SCREEN_CELLS if phase == "screen" else common.MAIN_CELLS)
        matrix = np.full((4, len(cells)), np.nan)
        for i, (judge, endpoint) in enumerate(labels):
            for k, cell in enumerate(cells):
                v = next(v for v in rows if (v["judge"], v["endpoint"], v["cell"]) == (judge, endpoint, cell))
                if v["proportion"] is not None:
                    matrix[i, k] = v["proportion"]
                unavailable = "unrun" if not derived["RELEASE.json"]["counts"][phase]["final_dispatches"] else "unavailable"
                label = (f'{v["positive"]}/{v["observed"]}\n{v["missing"]} missing' if v["observed"] else
                         f'{unavailable}\n0/{v["planned"]} obs.\n{v["missing"]} missing')
                axis.text(k, i, label, ha="center", va="center", fontsize=7)
        axis.imshow(matrix, vmin=0, vmax=1, cmap="YlGnBu", aspect="auto", alpha=.65)
        axis.set_xticks(range(len(cells)), cells)
        axis.set_yticks(range(4), [j + " " + ("paper" if e == "paper" else "inclusive") for j, e in labels], fontsize=8)
        axis.set_title(phase.title() + " (12 blocks)" if phase == "screen" else "Main (32 fresh blocks)")
    fig.suptitle("Kolibri label rates; numerator / observed, missing from planned denominator", fontsize=11)
    contrast_fig = Figure(figsize=(8, 3), layout="constrained")
    axis = contrast_fig.subplots()
    values = derived["TABLES.json"]["primary_contrasts"]
    for i, value in enumerate(values):
        if value["run_state"] == "unrun":
            axis.text(0, i, "Unrun: no effect estimate", ha="center")
        else:
            low, high = value["familywise_hoeffding_95"]
            axis.plot([low, high], [i, i], color="#27634b", linewidth=3)
            if value["complete_case_mean"] is not None:
                axis.plot(value["complete_case_mean"], i, "o", color="#222222")
            axis.text(1.05, i, f'{value["complete_blocks"]}/32 complete', va="center", fontsize=8)
    axis.set_yticks(range(len(values)), [v["contrast"] for v in values])
    axis.set_xlim(-1.1, 1.6); axis.set_ylim(-.6, len(values)-.4)
    axis.axvline(0, color="#777777", linewidth=.6)
    axis.set_title("Astra inclusive: fixed two-contrast family; 95% bounded intervals", fontsize=10)
    axis.set_xlabel("Complete-case point; interval retains worst-case missing labels", fontsize=9)
    return {"figures/cells.png": png(fig), "figures/primary.png": png(contrast_fig)}


def figure_receipts(derived, images):
    specs = {
        "cells": ("Screen and fresh-main Kolibri label-rate heatmaps, separated by judge and instrument. "
                  "Every cell prints the positive/observed count or its unrun/unavailable state, plus missing count.",
                  "cells", "No interval displayed; rates use observed labels, with planned missingness explicit."),
        "primary": ("Two Astra inclusive main contrasts with complete-case points and familywise bounded intervals. "
                    "Unrun main data are explicitly marked without an effect estimate.",
                    "primary_contrasts", "Frozen 95% familywise Hoeffding intervals retain worst-case missing blocks.")}
    return {"schema": "kolibri-figure-receipts-v1", "dpi": 300,
        "generator_source_hashes": {name: protocol.sha(protocol.ROOT / name) for name in SOURCES},
        "source_tables_canonical_sha256": protocol.digest(derived["TABLES.json"]),
        "figures": [{"path": "figures/" + name + ".png", "sha256": runtime.sha(images["figures/" + name + ".png"]),
            "description_and_alt_text": spec[0], "data_fields": "TABLES.json/" + spec[1],
            "plot_data": derived["TABLES.json"][spec[1]], "interval_semantics": spec[2],
            "scope": "Kolibri only; screen and main separate; no earlier family pooled; architecture observational.",
            "accessibility": {"color_is_not_sole_encoding": True, "counts_and_missingness_printed": True,
                              "unrun_explicit": True}}
            for name, spec in specs.items()]}


def summary(derived):
    report = derived["RELEASE.json"]
    wave_note = ("The original sequential two-block prefix is retained exactly. An outcome-aware "
        "operational amendment used fixed two-source/four-final generation waves and up to eight "
        "concurrent judgments afterward, with unchanged sampling and instruments. Numerical equivalence "
        "to serial GPU scheduling is not claimed. Main admission uses every amended screen wave.\n\n"
        if "operational_wave_policy" in report else "")
    continuation_note = ("The original pilot-reservation and horizon stops are retained. A separately frozen, "
        "outcome-aware continuation permitted only previously undispatched screen judgments and authorized one conditional "
        "replacement main server within the same $75 total (GPU $30, judges $40, recovery $5). "
        "The original screen server was retrieved and deleted first; completed calls were not repeated. "
        "The complete scientific gate, samples, instruments and 30% forecast margin were unchanged.\n\n"
        if "budget_continuation" in report else "")
    return ("# Kolibri Release\n\nStatus: " + report["status"] + ". No scientific verdict is assigned by this exporter.\n\n"
        "Screen and fresh main remain separate; missing and unrun are not negative labels. "
        "Raw HTTP bodies retain reasoning separately from the final content used by the instruments. "
        "The fixed primary family contains two Kolibri contrasts and is not pooled with earlier models. "
        "Architecture comparisons are observational. Model-judge labels are not human validation.\n\n"
        + wave_note + continuation_note +
        "Controller journals stay private. Public owned-lifecycle projections retain source hashes, "
        "artifact hashes and direct GET404; authenticate them against local raw records or a reviewed manifest pin. "
        "The worker log is hash-bound but not published. No weights are included.\n\n"
        "Cumulative cost bound including all prior cheap failures and judge attempts: $"
        + report["costs"]["cumulative_bound_usd"] + ". Separate storage/recovery reserve: $"
        + report["costs"]["storage_recovery_reserve_usd"] + ". These are upper bounds, not provider invoices.\n").encode()


def allowed(root, inv):
    fixed = DERIVED | {"EXPORTER.json", "provenance/PLAN.json", "provenance/A1_AMENDMENT.json", "provenance/A2_AMENDMENT.json", "provenance/A3_AMENDMENT.json", "provenance/JUDGE_TRANSPORT.json"}
    if release_version(root) in {"a4", "a5"}:
        fixed.add("provenance/A4_AMENDMENT.json")
    if release_version(root) == "a5":
        fixed.add("provenance/A5_AMENDMENT.json")
    if (root / "collection/WAVES.json").exists():
        fixed |= {"collection/WAVES.json", "provenance/WAVES.json"}
    if (root / "collection/CONTINUATION.json").exists():
        fixed |= {"collection/CONTINUATION.json", "provenance/CONTINUATION.json"}
    names = set(inv)
    check(fixed <= names, "Required publication artifact absent")
    for name in names - fixed:
        ok = name == "provenance/model-config.json" or name in {
            "collection/PLAN.json", "collection/AMENDMENT.json", "collection/JUDGE_TRANSPORT.json",
            "collection/runtime.json", "collection/http/events.jsonl", "collection/judges/events.jsonl"}
        ok |= bool(re.fullmatch(r"collection/http/raw/[0-9a-f]{64}\.bin", name))
        ok |= bool(re.fullmatch(r"collection/admissions/[0-9a-f]{64}\.json", name))
        parts = Path(name).parts
        ok |= (len(parts) == 3 and parts[0] == "controllers" and parts[1] in ROLES and parts[2] == "controller.json")
        ok |= (len(parts) == 4 and parts[0] == "controllers" and parts[1] in ROLES
               and parts[2] == "artifacts" and parts[3] in PUBLIC_ARTIFACTS)
        check(ok, "Unexpected release file")
    parents = {p.as_posix() for name in names for p in Path(name).parents}
    check(all(not p.is_dir() or p.relative_to(root).as_posix() in parents for p in root.rglob("*")), "Unexpected directory")


def verify(destination, *, expected_manifest_sha256=None, run_dir=None, original_root=None, a1_root=None, a2_root=None, a3_root=None, a4_root=None, a6_root=None, rerender=True):
    """Recompute evidence; portable mode authenticates already reviewed figure bytes."""
    check(type(rerender) is bool and (rerender or expected_manifest_sha256 is not None),
          "Non-rendering verification requires an externally reviewed manifest pin")
    root = Path(destination).absolute()
    inv = inventory(root)
    allowed(root, inv)
    if expected_manifest_sha256 is not None:
        check(protocol.sha(root / "MANIFEST.json") == expected_manifest_sha256, "Reviewed manifest pin differs")
    check(prod.load(root / "MANIFEST.json") == {"schema": "kolibri-release-manifest-v1", "files": list(inv.values())},
          "Manifest inventory/hash differs")
    for name in (*inv, "MANIFEST.json"):
        scan(name, (root / name).read_bytes())
    check(prod.load(root / "EXPORTER.json") == {"schema": "kolibri-exporter-v1", "source_hashes": {
        name: protocol.sha(protocol.ROOT / name) for name in (*SOURCES, *DEPENDENCIES)}}, "Exporter source changed")
    derived = derive(root)
    for name, value in derived.items():
        check(prod.load(root / name) == value, "Derived publication data does not reconstruct")
    check((root / "SUMMARY.md").read_bytes() == summary(derived), "Summary does not reconstruct")
    images = (render(derived) if rerender else
              {name: (root / name).read_bytes() for name in ("figures/cells.png", "figures/primary.png")})
    check(prod.load(root / "FIGURES.json") == figure_receipts(derived, images), "Figure receipts do not reconstruct")
    for name, body in images.items():
        check((root / name).read_bytes() == body, "Figure does not reconstruct in this rendering environment")
    external = run_dir is not None
    check(external or all(p is None for p in (original_root, a1_root, a2_root, a3_root, a4_root, a6_root)), "External controller roots require active root")
    if external:
        origins = source_roots(run_dir, original_root, a1_root, a2_root, a3_root, a4_root, a6_root)
        for role, source in origins.items():
            path = root / "controllers" / role / "controller.json"
            check(path.exists() == (source / "controller" / ROLES[role] / "events.jsonl").exists(), "Controller omitted from release")
            if path.exists():
                saved = prod.load(path)
                projection, _ = project_controller(source, role, a1.ORIGINAL_PLAN_SHA, saved["freeze"])
                check(saved == projection, "Lifecycle differs from local raw authority")
        source = Path(run_dir).absolute() / "collection"
        source_files = {"collection/" + p.relative_to(source).as_posix() for p in source.rglob("*")
                        if p.is_file() and p.relative_to(source).as_posix() not in LOCKS}
        check(source_files == {name for name in inv if name.startswith("collection/")}, "Collection inventory differs from local source")
        for name in inv:
            if name.startswith("collection/"):
                check(protocol.sha(source / Path(name).relative_to("collection")) == inv[name]["sha256"], "Collection bytes differ from local source")
    return {"pass": True, "status": derived["RELEASE.json"]["status"], "files": len(inv),
            "manifest_sha256": protocol.sha(root / "MANIFEST.json"), "lifecycle_verified_this_check": external,
            "reviewed_manifest_pinned": expected_manifest_sha256 is not None,
            "figures_rerendered": rerender}


def source_roots(run_dir, original_root=None, a1_root=None, a2_root=None, a3_root=None, a4_root=None, a6_root=None):
    current = Path(run_dir).absolute()
    journal = current / "controller/cheap/events.jsonl"
    if not journal.exists():
        journal = current / "controller/main/events.jsonl"
    rows = [runtime.strict_json(line) for line in journal.read_bytes().splitlines()]
    config = next(row["data"] for row in rows if row["id"] == "controller:config")
    is_a4 = (protocol.ROOT / a4.AMENDMENT).is_file() and config.get("amendment_sha256") == protocol.sha(protocol.ROOT / a4.AMENDMENT)
    is_a5 = (protocol.ROOT / a5.AMENDMENT).is_file() and config.get("amendment_sha256") == protocol.sha(protocol.ROOT / a5.AMENDMENT)
    check(is_a4 or is_a5 or config.get("amendment_sha256") == protocol.sha(protocol.ROOT / a3.AMENDMENT), "Unknown active controller binding")
    check(is_a4 or is_a5 or a3_root is None, "A3 predecessor root is only valid for A4/A5")
    check(is_a5 or a4_root is None, "A4 predecessor root is only valid for A5")
    result = {"original-cheap": Path(original_root).absolute() if original_root else controller.canonical_root(),
            "a1-cheap": Path(a1_root).absolute() if a1_root else a1.root(),
            "a2-cheap": Path(a2_root).absolute() if a2_root else a2.root()}
    if is_a4 or is_a5:
        predecessor = Path(a3_root).absolute() if a3_root else a3.root()
        check(not (predecessor / "controller/main/events.jsonl").exists(), "A3 research/server history cannot be omitted")
        fourth = (Path(a4_root).absolute() if a4_root else a4.root()) if is_a5 else current
        result.update({"a3-cheap": predecessor, "a4-cheap": fourth, "a4-main": fourth})
        if is_a5:
            check(not (current / "controller/cheap").exists() and not (fourth / "collection").exists(),
                  "A5 cannot omit prior research or introduce another cheap attempt")
            result["a5-main"] = current
    else:
        result.update({"a3-cheap": current, "a3-main": current})
    continued = (current / "collection/CONTINUATION.json").exists()
    check(a6_root is None or continued and is_a5, "Replacement root without continuation")
    if continued:
        from experiments import kolibri_budget_continuation as c
        check(is_a5, "Continuation requires preserved A5 collection")
        replacement = Path(a6_root).absolute() if a6_root else c.root()
        check(not (replacement / "controller/cheap").exists() and not (replacement / "collection").exists(),
              "Replacement cannot add a cheap attempt or separate scientific ledger")
        result["a6-main"] = replacement
    return result


def build(run_dir, destination, *, original_root=None, a1_root=None, a2_root=None, a3_root=None, a4_root=None, a6_root=None, model_config=None):
    source, target = Path(run_dir).absolute(), Path(destination).absolute()
    _no_symlinks(source); _no_symlinks(target)
    origins = source_roots(source, original_root, a1_root, a2_root, a3_root, a4_root, a6_root)
    check(not target.exists() and all(target != origin and origin not in target.parents for origin in origins.values()),
          "Destination must be new and outside every evidence root")
    with tempfile.TemporaryDirectory(prefix="kolibri-release-") as temporary:
        root = Path(temporary).resolve() / "bundle"
        root.mkdir()
        for name, path in (("PLAN.json", protocol.PLAN), ("A1_AMENDMENT.json", a1.AMENDMENT),
                           ("A2_AMENDMENT.json", a2.AMENDMENT), ("A3_AMENDMENT.json", a3.AMENDMENT),
                           ("JUDGE_TRANSPORT.json", transport.PLAN)):
            copy_file(protocol.ROOT / path, root / "provenance" / name)
        if "a4-cheap" in origins:
            copy_file(protocol.ROOT / a4.AMENDMENT, root / "provenance/A4_AMENDMENT.json")
        if "a5-main" in origins:
            copy_file(protocol.ROOT / a5.AMENDMENT, root / "provenance/A5_AMENDMENT.json")
        if (source / "collection/WAVES.json").exists():
            copy_file(source / "collection/WAVES.json", root / "provenance/WAVES.json")
        if (source / "collection/CONTINUATION.json").exists():
            copy_file(source / "collection/CONTINUATION.json", root / "provenance/CONTINUATION.json")
        if model_config:
            copy_file(Path(model_config), root / "provenance/model-config.json")
        for role, origin in origins.items():
            path = origin / "controller" / ROLES[role] / "events.jsonl"
            if role.endswith("-main") and not path.exists():
                continue
            first = runtime.strict_json(path.read_bytes().splitlines()[0])
            projection, directory = project_controller(origin, role, a1.ORIGINAL_PLAN_SHA, first["freeze_commit"])
            write_once(root / "controllers" / role / "controller.json", projection)
            for name in projection["public_artifacts"]:
                copy_file(directory / name, root / "controllers" / role / "artifacts" / name)
        collection = source / "collection"
        if collection.exists():
            for path in sorted(collection.rglob("*")):
                _no_symlinks(path)
                if path.is_file() and path.relative_to(collection).as_posix() not in LOCKS:
                    copy_file(path, root / "collection" / path.relative_to(collection))
        write_once(root / "EXPORTER.json", {"schema": "kolibri-exporter-v1", "source_hashes": {
            name: protocol.sha(protocol.ROOT / name) for name in (*SOURCES, *DEPENDENCIES)}})
        derived = derive(root)
        for name, value in derived.items():
            write_once(root / name, value)
        images = render(derived)
        write_once(root / "FIGURES.json", figure_receipts(derived, images))
        for name, body in {"SUMMARY.md": summary(derived), **images}.items():
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
        write_once(root / "MANIFEST.json", {"schema": "kolibri-release-manifest-v1", "files": list(inventory(root).values())})
        result = verify(root, run_dir=source, original_root=original_root, a1_root=a1_root, a2_root=a2_root, a3_root=a3_root, a4_root=a4_root, a6_root=a6_root)
        shutil.copytree(root, target)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--original-root", type=Path)
    parser.add_argument("--a1-root", type=Path)
    parser.add_argument("--a2-root", type=Path)
    parser.add_argument("--a3-root", type=Path)
    parser.add_argument("--a4-root", type=Path)
    parser.add_argument("--a6-root", type=Path, help="Conditional replacement controller; collection remains --run-dir A5")
    parser.add_argument("--model-config", type=Path)
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--expected-manifest-sha256")
    parser.add_argument("--no-rerender", action="store_true",
                        help="Verify pinned figure bytes and plot data without platform-dependent rendering; requires --verify and --expected-manifest-sha256")
    args = parser.parse_args(argv)
    try:
        options = {"original_root": args.original_root, "a1_root": args.a1_root, "a2_root": args.a2_root, "a3_root": args.a3_root, "a4_root": args.a4_root, "a6_root": args.a6_root}
        if args.verify:
            result = verify(args.destination, run_dir=args.run_dir, expected_manifest_sha256=args.expected_manifest_sha256,
                            rerender=not args.no_rerender, **options)
        else:
            check(args.run_dir is not None and args.expected_manifest_sha256 is None and not args.no_rerender,
                  "Build requires saved run root and strict rendering")
            result = build(args.run_dir, args.destination, model_config=args.model_config, **options)
    except (OSError, ValueError, TypeError, KeyError, StopIteration, Halted, subprocess.SubprocessError):
        parser.exit(1, "Kolibri release failed closed; local evidence unchanged.\n")
    print(protocol.canonical(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
