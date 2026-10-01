"""Result-free Llama Stage A inventory and bindings; no inference or provisioning.

The module itself is torch-free. The package initializer may import torch;
candidate fitting imports NumPy lazily and performs CPU FP32 arithmetic only.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import itertools
import json
from pathlib import Path
import re
import subprocess

from experiments.exp2_sae import sae_jlens_protocol as pins

ROOT = Path(__file__).resolve().parents[2]
PLAN_PATH = "data/jlens_causal_report/stage_a_plan_20261001/PLAN.json"
TOKEN_BINDINGS_PATH = "data/jlens_causal_report/stage_a_inputs_20261001/token_bindings.json"
TOKENIZER_FILES = ("config.json", "generation_config.json", "special_tokens_map.json",
                   "tokenizer.json", "tokenizer_config.json")
PROTOCOL_DOC = "docs/JLENS_CAUSAL_REPORT_PROTOCOL_20261001.md"
SCHEMA = "jlens_causal_report_stage_a_v1"
PRIOR_USD, NEW_CAP_USD = "69.130940", "15"
MAIN_SECONDS, CHEAP_SECONDS, RESERVE_SECONDS = 7200, 1800, 600
LAYERS = (40, 50)
MODEL_WIDTH = pins.MODEL_WIDTH
RANDOM_SEEDS = (2026100101, 2026100102, 2026100103, 2026100104, 2026100105)

# Every family contains the complete role x probe x order x answer-code design.
REGISTRY_FAMILIES = {
    "discovery": (
        ("registry", ("NERAL", "VOT"), ("key", "cup")),
        ("inventory", ("PEL", "SARN"), ("coin", "comb")),
    ),
    "qualification": (
        ("allocation", ("TAV", "RUL"), ("bell", "rope")),
        ("ledger", ("DAX", "MIV"), ("fork", "kite")),
    ),
}
REGISTRY_TEMPLATES = {
    "registry": "Roles: {roles}\nRegistry: {entries}\nProbe: {probe}.\n{codes}\nAnswer:",
    "inventory": "Role labels: {roles}\nInventory record: {entries}\nItem to classify: {probe}.\n{codes}\nAnswer:",
    "allocation": "Participant mapping: {roles}\nAllocation list: {entries}\nRequested item: {probe}.\n{codes}\nAnswer:",
    "ledger": "Label definitions: {roles}\nOwnership ledger: {entries}\nLook up: {probe}.\n{codes}\nAnswer:",
}
BRIDGE_FAMILIES = (
    ("parcel", ("KEL", "ZUN"), ("parcel", "crate"), ("amber", "violet")),
    ("ticket", ("BEX", "FAR"), ("ticket", "badge"), ("silver", "green")),
    ("folder", ("LOR", "WEM"), ("folder", "box"), ("red", "blue")),
)


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1048576), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _text_sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _case(pair_id, owner, prompt, answer, **metadata):
    messages = [{"role": "user", "content": prompt}]
    return {"id": pair_id + "-" + owner, "owner": owner,
            "messages": messages, "expected_answer": answer,
            "messages_sha256": _text_sha(canonical(messages)), **metadata}


def _directions(cases):
    return [{"id": recipient["id"] + "-from-" + donor["owner"],
             "recipient_id": recipient["id"], "donor_id": donor["id"],
             "recipient_owner": recipient["owner"], "donor_owner": donor["owner"],
             "recipient_answer": recipient["expected_answer"],
             "donor_answer": donor["expected_answer"]}
            for recipient, donor in (cases, list(reversed(cases)))]


def inventory():
    """76 pair specs: 32 discovery, 32 qualification, 12 bridge positives."""
    rows = []
    for split, families in REGISTRY_FAMILIES.items():
        for family, roles, objects in families:
            for role_bit, probe_bit, order_bit, code_bit in itertools.product((0, 1), repeat=4):
                bits = f"{role_bit}{probe_bit}{order_bit}{code_bit}"
                pair_id = f"{split}-{family}-{bits}"
                self_role, other_role = roles[role_bit], roles[1 - role_bit]
                codes = {"self": "AB"[code_bit], "other": "BA"[code_bit]}
                role_text = "; ".join(
                    f"{role} denotes {'you' if role == self_role else 'another participant'}"
                    for role in roles) + "."
                code_text = (f"Answer code: your inventory = {codes['self']}; "
                             f"the other participant's inventory = {codes['other']}. "
                             "Answer only A or B.")
                cases = []
                for owner in ("self", "other"):
                    probe_owner = self_role if owner == "self" else other_role
                    remaining_owner = other_role if owner == "self" else self_role
                    assignment = {objects[probe_bit]: probe_owner,
                                  objects[1 - probe_bit]: remaining_owner}
                    ordered_roles = roles if not order_bit else roles[::-1]
                    entries = "; ".join(
                        f"{role} owns {next(obj for obj in objects if assignment[obj] == role)}"
                        for role in ordered_roles) + "."
                    prompt = REGISTRY_TEMPLATES[family].format(
                        roles=role_text, entries=entries, probe=objects[probe_bit], codes=code_text)
                    cases.append(_case(pair_id, owner, prompt, codes[owner], assignment=assignment))
                rows.append({"id": pair_id, "split": split, "family": family,
                             "kind": "ownership_registry", "roles": list(roles),
                             "objects": list(objects), "self_role": self_role,
                             "probe": objects[probe_bit], "answer_codes": codes,
                             "counterbalance": dict(zip(
                                 ("role", "probe", "order", "code"),
                                 (role_bit, probe_bit, order_bit, code_bit))),
                             "cases": cases, "directions": _directions(cases)})
    for family, labels, objects, colors in BRIDGE_FAMILIES:
        for order_bit, code_bit in itertools.product((0, 1), repeat=2):
            pair_id = f"positive-{family}-{order_bit}{code_bit}"
            codes = dict(zip(colors, ("AB"[code_bit], "BA"[code_bit])))
            cases = []
            for index, owner in enumerate(("first", "second")):
                holders = {objects[0]: labels[index], objects[1]: labels[1 - index]}
                entries = [f"{holders[obj]} holds the {obj}" for obj in objects]
                if order_bit:
                    entries.reverse()
                prompt = (
                    "Use only this record. " + "; ".join(entries) + ".\n"
                    + "; ".join(f"{label} uses the {color} locker" for label, color in zip(labels, colors))
                    + f".\nWhich locker color is linked to the {objects[0]}?\n"
                    + f"Answer code: {colors[0]} = {codes[colors[0]]}; {colors[1]} = {codes[colors[1]]}. "
                    + "Answer only A or B.\nAnswer:")
                cases.append(_case(pair_id, owner, prompt, codes[colors[index]],
                                   holders=holders, locker_color=colors[index]))
            rows.append({"id": pair_id, "split": "positive", "family": family,
                         "kind": "known_record_bridge", "answer_codes": codes,
                         "counterbalance": {"order": order_bit, "code": code_bit},
                         "cases": cases, "directions": _directions(cases)})
    return rows


def directional_trials(rows=None, *, split="qualification"):
    """Both directions; never filter trials on clean accuracy or edit efficacy."""
    if split not in ("discovery", "qualification", "positive"):
        raise ValueError("Unknown inventory split")
    return [{"pair_id": row["id"], "family": row["family"], **direction}
            for row in (inventory() if rows is None else rows) if row["split"] == split
            for direction in row["directions"]]


def token_binding_inventory(tokenizer):
    """Serialize all 152 result-free case prompts, without loading a model."""
    cases = {}
    for row in inventory():
        for case in row["cases"]:
            tokens = tokenizer.apply_chat_template(
                case["messages"], tokenize=True, add_generation_prompt=True,
                padding=False, truncation=False)
            cases[case["id"]] = {"messages_sha256": case["messages_sha256"],
                                  "input_token_ids": tokens}
    result = {"schema": "jlens_causal_token_bindings_v1", "model_id": pins.MODEL_ID,
              "revision": pins.MODEL_REVISION, "cases": cases}
    validate_token_bindings(result)
    return result


def validate_token_bindings(binding, *, require_files=False):
    if not isinstance(binding, dict) or set(binding) not in (
            {"schema", "model_id", "revision", "cases"},
            {"schema", "model_id", "revision", "cases", "tokenizer_files"}):
        raise ValueError("Malformed token binding artifact")
    if (binding["schema"] != "jlens_causal_token_bindings_v1"
            or binding["model_id"] != pins.MODEL_ID or binding["revision"] != pins.MODEL_REVISION):
        raise ValueError("Token bindings must use the pinned model/revision")
    cases = {case["id"]: case for row in inventory() for case in row["cases"]}
    if not isinstance(binding["cases"], dict) or set(binding["cases"]) != set(cases):
        raise ValueError("Token binding case inventory mismatch")
    for identifier, value in binding["cases"].items():
        if (not isinstance(value, dict) or set(value) != {"messages_sha256", "input_token_ids"}
                or value["messages_sha256"] != cases[identifier]["messages_sha256"]):
            raise ValueError("Token binding message hash mismatch")
        tokens = value["input_token_ids"]
        if (not isinstance(tokens, list) or not tokens
                or any(type(t) is not int or not 0 <= t < 128256 for t in tokens)):
            raise ValueError("Invalid token binding IDs")
    files = binding.get("tokenizer_files")
    if files is None:
        if require_files:
            raise ValueError("Production token bindings require tokenizer file hashes")
        return
    if not isinstance(files, dict) or set(files) != set(TOKENIZER_FILES):
        raise ValueError("Tokenizer file inventory mismatch")
    for metadata in files.values():
        if (not isinstance(metadata, dict) or set(metadata) != {"sha256", "git_blob_sha1", "size_bytes", "storage"}
                or metadata["storage"] not in ("git_blob", "lfs")
                or not isinstance(metadata["sha256"], str)
                or not re.fullmatch(r"[0-9a-f]{64}", metadata["sha256"])
                or not isinstance(metadata["git_blob_sha1"], str)
                or not re.fullmatch(r"[0-9a-f]{40}", metadata["git_blob_sha1"])
                or type(metadata["size_bytes"]) is not int or metadata["size_bytes"] <= 0):
            raise ValueError("Invalid tokenizer file hash metadata")


def download_token_bindings(cache_dir):
    """Explicit CLI-only network path: five pinned JSON files, never weights/code."""
    from huggingface_hub import HfApi, snapshot_download
    from transformers import AutoTokenizer

    info = HfApi().model_info(pins.MODEL_ID, revision=pins.MODEL_REVISION, files_metadata=True)
    if info.sha != pins.MODEL_REVISION:
        raise ValueError("Tokenizer revision mismatch")
    siblings = {item.rfilename: item for item in info.siblings}
    if not set(TOKENIZER_FILES).issubset(siblings):
        raise ValueError("Pinned tokenizer files missing from Hub metadata")
    snapshot = Path(snapshot_download(
        repo_id=pins.MODEL_ID, revision=pins.MODEL_REVISION, cache_dir=str(cache_dir),
        allow_patterns=list(TOKENIZER_FILES), ignore_patterns=["*.safetensors", "*.bin", "*.pt", "*.py"]))
    files = {}
    for name in TOKENIZER_FILES:
        raw = (snapshot / name).read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        sibling = siblings[name]
        lfs = getattr(sibling, "lfs", None)
        blob = hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest()
        if lfs is not None:
            expected_sha = lfs.get("sha256") if isinstance(lfs, dict) else getattr(lfs, "sha256", None)
            expected_size = lfs.get("size") if isinstance(lfs, dict) else getattr(lfs, "size", None)
            if (digest != expected_sha or type(expected_size) is not int
                    or len(raw) != expected_size):
                raise ValueError("Tokenizer file differs from pinned LFS payload: " + name)
        elif blob != sibling.blob_id:
            raise ValueError("Tokenizer file differs from pinned Git blob: " + name)
        files[name] = {"sha256": digest, "git_blob_sha1": sibling.blob_id,
                       "size_bytes": len(raw), "storage": "lfs" if lfs is not None else "git_blob"}
    tokenizer = AutoTokenizer.from_pretrained(snapshot, local_files_only=True, trust_remote_code=False)
    result = {**token_binding_inventory(tokenizer), "tokenizer_files": files}
    validate_token_bindings(result, require_files=True)
    return result


def _bound_tokens(token_bindings):
    path = ROOT / TOKEN_BINDINGS_PATH
    if isinstance(token_bindings, (str, Path)):
        if Path(token_bindings).resolve() != path.resolve():
            raise ValueError("Token artifact must use the fixed repository input path")
        if not path.is_file():
            raise ValueError("Missing token binding artifact")
        token_bindings = None
    bound = None
    if path.exists():
        if path.is_symlink():
            raise ValueError("Token artifact must not be a symlink")
        raw = path.read_bytes()
        bound = json.loads(raw)
        if raw != (canonical(bound) + "\n").encode():
            raise ValueError("Noncanonical token binding artifact")
        validate_token_bindings(bound, require_files=True)
        if token_bindings is not None and canonical(token_bindings) != canonical(bound):
            raise ValueError("Token binding artifact differs from supplied inventory")
        return bound, {TOKEN_BINDINGS_PATH: hashlib.sha256(raw).hexdigest()}
    if token_bindings is not None:
        validate_token_bindings(token_bindings)
        bound = json.loads(canonical(token_bindings))
    return bound, {}


def _local_imports(path):
    """Resolve static repository imports without importing runtime modules."""
    parts = Path(path).with_suffix("").parts
    package = parts[:-1]
    modules = []
    for node in ast.walk(ast.parse((ROOT / path).read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            modules.extend(alias.name.split(".") for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = list(package[:len(package) - node.level + 1]) if node.level else []
            base += node.module.split(".") if node.module else []
            modules.append(base)
            modules.extend(base + alias.name.split(".") for alias in node.names if alias.name != "*")
    paths = set()
    for module in modules:
        for length in range(1, len(module) + 1):
            init = Path(*module[:length]) / "__init__.py"
            if (ROOT / init).is_file():
                paths.add(init.as_posix())
        for candidate in (Path(*module).with_suffix(".py") if module else Path("_absent_"),
                          Path(*module) / "__init__.py"):
            if (ROOT / candidate).is_file():
                paths.add(candidate.as_posix())
    return paths


def source_paths():
    paths = {PROTOCOL_DOC, "docs/DESIGN_VALIDITY_GATE.md",
             "experiments/exp2_sae/sae_jlens_protocol.py",
             "experiments/sae_assay_diagnostic/requirements-gpu.txt"}
    for package in ("jlens_causal_report", "sae_assay_diagnostic", "sae_assay_replay",
                    "sae_assay_repair", "sae_assay_exposure", "sae_assay_exposure_lifecycle_a1"):
        paths.update(p.relative_to(ROOT).as_posix() for p in (ROOT / "experiments" / package).rglob("*.py"))
    for pattern in ("test_jlens_causal_*.py", "test_sae_assay_*.py"):
        paths.update(p.relative_to(ROOT).as_posix() for p in (ROOT / "tests").glob(pattern))
    pending = list(paths)
    while pending:
        path = pending.pop()
        if path.endswith(".py"):
            new = _local_imports(path) - paths
            paths.update(new)
            pending.extend(sorted(new))
    return sorted(paths)


def build_plan(token_bindings=None):
    """Auto-consume the fixed input artifact if present; otherwise build a draft.

An in-memory binding is allowed for synthetic/draft work but cannot qualify a
freeze without an identical canonical, file-hashed artifact at TOKEN_BINDINGS_PATH.
"""
    bindings, input_hashes = _bound_tokens(token_bindings)
    return {
        "schema": SCHEMA, "stage": "A", "rows": inventory(),
        "token_bindings": bindings,
        "counts": {"discovery_pairs": 32, "qualification_pairs": 32,
                   "positive_pairs": 12, "qualification_directional_trials": 64,
                   "positive_directional_trials": 24},
        "scope": {"experiential_reports": False, "paid_execution_authorized": False,
                  "ready_to_freeze": bool(input_hashes),
                  "report_qualification": "separate_future_freeze_after_candidate_hashes",
                  "stage_b_frozen": False, "qwen_included": False,
                  "claim": "fixed_panel_ownership_task_qualification_only"},
        "model": {"id": pins.MODEL_ID, "revision": pins.MODEL_REVISION,
                  "precision": "bf16", "width": MODEL_WIDTH,
                  "tokenizer_revision": pins.MODEL_REVISION},
        "lens": {"id": pins.JLENS_ID, "revision": pins.JLENS_REVISION,
                 "filename": pins.JLENS_FILENAME, "sha256": pins.JLENS_FILE_SHA256,
                 "role": "readout_only_not_candidate_selection", "layers": list(LAYERS),
                 "random_seeds": list(pins.TRANSPORT_RANDOM_SEEDS),
                 "comparators": ["identity", "jacobian"] + [f"random_j_{i}" for i in range(1, 6)],
                 "readouts_not_required_for_stage_a_gate": True},
        "loader_dependency": {"unused_sae_id": pins.SAE_ID, "revision": pins.SAE_REVISION,
                              "filename": pins.SAE_FILENAME, "sha256": pins.SAE_FILE_SHA256},
        "inference": {"layers": list(LAYERS), "boundary": "last_serialized_prompt_token",
                      "hook": "zero_based_decoder_block_output", "batch_size": 1,
                      "padding": False, "truncation": False, "temperature": 0.0,
                      "max_new_tokens": 1, "seed": 2026100100,
                      "chat_template": "pinned_tokenizer_user_message_add_generation_prompt",
                      "decoding": "global_vocabulary_argmax_no_AB_restriction_or_renormalization",
                      "answer_scoring": "decoded_next_token_strip_exact_A_or_B_else_incorrect",
                      "answer_tokenization": {
                          "strings": ["A", "B", " A", " B"],
                          "add_special_tokens": False, "each_must_be_singleton": True,
                          "decoded_strip_must_equal_code": True,
                          "failure": "stop_no_arbitrary_token_or_label_substitution"},
                      "conditional_AB_mass": "diagnostic_only_deduplicate_verified_token_ids_per_code",
                      "forward_mode": "full_prefix_no_cache_reapply_at_fixed_prompt_boundary",
                      "donor_alignment": "own_last_prompt_boundary_not_shared_token_ordinal",
                      "donors": "clean_prefill_before_any_answer_no_generated_text_patching"},
        "candidate": {"rank": 1, "layers": list(LAYERS), "fit_split": "discovery",
                      "pairs": 32, "arithmetic": "cpu_fp32",
                      "direction": "normalize(mean_32(h_self-h_other))",
                      "center": "mean_32((h_self+h_other)/2)",
                      "orientation": "self_minus_other_no_pivot_sign_flip",
                      "selection": "one_candidate_per_layer_no_search_or_refit",
                      "persist": ["all_discovery_states", "direction", "center", "sha256"],
                      "artifact_schema": "jlens_ownership_candidate_v1"},
        "interventions": {"layer": 40, "alpha": 1.0, "adaptive_clipping": False,
                          "arms": ["clean", "zero", "sham", "target_donor"]
                                  + [f"random-{s}" for s in RANDOM_SEEDS],
                          "target": "cast_native(h+Q40@Q40.T@(d-h))",
                          "random_seeds": list(RANDOM_SEEDS),
                          "random": "seeded_rank1_donor_delta_rescaled_to_target_requested_norm",
                          "random_zero_target_request": "exact_noop_retained_in_behavioral_denominator",
                          "random_zero_source_nonzero_target": "fail_no_replacement_or_resampling",
                          "positive_control": "full_state_clean_donor_replacement_at_40",
                          "positive_arms": ["clean", "zero", "sham", "full_state_donor"],
                          "later_layer_rescue": "not_executed_in_stage_a_separate_freeze_required"},
        "gates": {
            "qualification": {"denominator": 64, "clean_correct_min": 58,
                              "target_donor_correct_min": 48,
                              "random_donor_correct_max_each_seed": 8,
                              "count_unit": "directed_recipient_donor_trial",
                              "conditioning_on_clean_correct": False,
                              "missing_or_malformed": "missing_rows_fail_completeness; non_AB_answers_count_incorrect_without_exclusion"},
            "positive": {"denominator": 24, "clean_correct_min": 22,
                         "full_state_donor_correct_min": 22,
                         "does_not_qualify_ownership_direction": True},
            "delivery": {"nonzero_only": True, "joint_pass_fraction_min": .95,
                         "cosine_min": .95, "relative_error_max": .25,
                         "actual_edit_over_clean_recipient_norm_max": .1,
                         "operator_norm_ratio_is_not_residual_norm_ratio": True,
                         "group_by": ["arm", "layer"],
                         "zero_nonzero_denominator": "fail_no_delivery_evidence",
                         "full_state_positive_exempt_from_residual_norm_cap": True,
                         "count_site": "first_prefill_boundary_one_per_directional_trial",
                         "later_reapplications": "retain_and_check_separately_no_pseudoreplication"},
            "exact_noop": ["zero", "sham"],
            "fatal": ["nonfinite", "shape_or_hook_error", "source_or_receipt_drift",
                      "no_op_value_or_greedy_output_mismatch", "missing_inventory"]},
        "restoration_contract_deferred": {
            "remove_layer": 40, "restore_layer": 50,
            "remove": "h-Q40@Q40.T@(h-center40)",
            "restore": "h_abl50+Q50@Q50.T@(saved_clean_recipient50-h_abl50)",
            "controls_required": ["counterfactual_owner_rescue", "rescue_alone"],
            "same_hook_inverse_is_not_rescue": True},
        "future_measurement_choice": {"primary": "inclusive_current_attribution_to_requested_subject",
                                     "mandatory_secondary": "explicit_current_attribution",
                                     "basis": "prior_Astra_Opus_0_of_80_explicit_floor",
                                     "report_items_in_this_plan": 0},
        "budget": {"prior_usd": PRIOR_USD, "new_cap_usd": NEW_CAP_USD, "total_usd": "200",
                   "main_seconds": MAIN_SECONDS, "cheap_seconds": CHEAP_SECONDS,
                   "reserve_seconds": RESERVE_SECONDS, "new_pro_calls": 0,
                   "external_judge_calls": 0},
        "budget_scope": "hard_all_in_including_startup_cheap_test_storage_failures_and_retrieval",
        "throughput_gate": {
            "planned_forwards": 736,
            "task_forwards_by_split": {"discovery": 64, "qualification": 576, "positive": 96},
            "additional_live_qualification_forwards": 2,
            "after_discovery_pairs": 5, "observed_forwards": 10, "remaining_forwards": 726,
            "timing_field": "forward_and_readout_seconds", "overhead_factor": 2,
            "reserve_seconds": 900,
            "predicted_remaining_seconds": "overhead_factor*mean_first_10_seconds*remaining_forwards",
            "pass_rule": "now+predicted_remaining_seconds+reserve_seconds<deadline",
            "on_failure": "stop_on_cost_no_outcome_selection_or_inventory_reduction",
        },
        "input_hashes": input_hashes, "source_hashes": {p: sha(ROOT / p) for p in source_paths()},
    }


def load_plan(path, freeze=None):
    raw = Path(path).read_bytes()
    plan = json.loads(raw)
    if raw != (canonical(plan) + "\n").encode("utf-8"):
        raise ValueError("Noncanonical plan")
    if canonical(plan) != canonical(build_plan(token_bindings=plan.get("token_bindings"))):
        raise ValueError("Plan, inventory, or source drift")
    if freeze is not None:
        if not isinstance(freeze, str) or not re.fullmatch(r"[0-9a-f]{40}", freeze):
            raise ValueError("freeze must be a full lowercase Git commit")
        if not plan["scope"]["ready_to_freeze"] or plan["token_bindings"] is None:
            raise ValueError("Cannot freeze without file-bound production token bindings")
        if subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip() != freeze:
            raise ValueError("Runtime checkout must equal full freeze")
        for name, digest in (plan["source_hashes"] | plan["input_hashes"]).items():
            blob = subprocess.check_output(["git", "show", f"{freeze}:{name}"], cwd=ROOT)
            if hashlib.sha256(blob).hexdigest() != digest:
                raise ValueError("Source differs from freeze: " + name)
        frozen_plan = subprocess.check_output(["git", "show", f"{freeze}:{PLAN_PATH}"], cwd=ROOT)
        if frozen_plan != raw:
            raise ValueError("Plan differs from freeze")
    return plan


def fit_candidates(discovery_states):
    """Return hash-bound JSON-safe artifacts from exactly the 64 discovery states.

Input maps case ID -> {40: vector, 50: vector}. No qualification states, answers,
or J scores are accepted. The runner persists these returned artifacts before
qualification. Array hashes bind little-endian contiguous FP32 bytes.
"""
    import numpy as np

    pairs = [row for row in inventory() if row["split"] == "discovery"]
    expected = {case["id"] for row in pairs for case in row["cases"]}
    if set(discovery_states) != expected:
        raise ValueError("Exactly the discovery case IDs are required")
    if any(set(states) != set(LAYERS) for states in discovery_states.values()):
        raise ValueError("Each discovery case requires exactly layers 40 and 50")
    result = {"schema": "jlens_ownership_candidate_v1", "discovery_inventory_sha256":
              _text_sha(canonical(pairs)), "layers": {}}

    def array_sha(value):
        return hashlib.sha256(np.asarray(value, dtype="<f4").tobytes(order="C")).hexdigest()

    with np.errstate(over="raise", invalid="raise", divide="raise", under="ignore"):
        for layer in LAYERS:
            values = []
            hashes = {}
            for row in pairs:
                pair = []
                for case in row["cases"]:
                    value = np.asarray(discovery_states[case["id"]][layer], dtype=np.float32)
                    if value.shape != (MODEL_WIDTH,) or not np.isfinite(value).all():
                        raise ValueError("Discovery states must be finite full-width vectors")
                    pair.append(value)
                    hashes[case["id"]] = array_sha(value)
                values.append(pair)
            states = np.asarray(values, dtype=np.float32)
            mean = (states[:, 0] - states[:, 1]).mean(axis=0, dtype=np.float32)
            center = (states[:, 0] * np.float32(.5) + states[:, 1] * np.float32(.5)).mean(
                axis=0, dtype=np.float32)
            # Scale before squaring; do not turn an underflowed contrast into a direction.
            scale = np.max(np.abs(mean))
            if not np.isfinite(mean).all() or not np.isfinite(center).all() or scale == 0:
                raise ValueError("Zero or nonfinite discovery contrast/center")
            scaled = mean / scale
            direction = scaled / np.sqrt(np.sum(scaled * scaled, dtype=np.float32))
            artifact = {"layer": layer, "rank": 1, "width": MODEL_WIDTH,
                        "orientation": "self_minus_other", "dtype": "float32",
                        "direction": direction.tolist(), "center": center.tolist(),
                        "direction_sha256": array_sha(direction), "center_sha256": array_sha(center),
                        "discovery_state_sha256": hashes}
            result["layers"][str(layer)] = {**artifact, "sha256": _text_sha(canonical(artifact))}
    return {**result, "sha256": _text_sha(canonical(result))}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / PLAN_PATH)
    parser.add_argument("--write-token-bindings", type=Path,
                        help="Explicitly download pinned tokenizer JSON only and create this artifact")
    parser.add_argument("--tokenizer-cache", type=Path, default=Path("/private/tmp/jlens-causal-tokenizer"))
    args = parser.parse_args()
    destination = args.write_token_bindings or args.out
    if destination.exists():
        raise FileExistsError(destination)
    value = download_token_bindings(args.tokenizer_cache) if args.write_token_bindings else build_plan()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("x", encoding="utf-8") as stream:
        stream.write(canonical(value) + "\n")
    print(sha(destination))
