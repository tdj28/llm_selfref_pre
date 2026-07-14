"""Exact source/test/document inventory bound into every pilot plan."""

from __future__ import annotations


BOUND_REPOSITORY_PATHS = (
    "experiments/consciousness_readout_validation/__init__.py",
    "experiments/consciousness_readout_validation/README.md",
    "experiments/consciousness_readout_validation/analysis.py",
    "experiments/consciousness_readout_validation/analyze_pilot.py",
    "experiments/consciousness_readout_validation/audit_pilot.py",
    "experiments/consciousness_readout_validation/build_execution_binding.py",
    "experiments/consciousness_readout_validation/build_plan.py",
    "experiments/consciousness_readout_validation/fixtures.py",
    "experiments/consciousness_readout_validation/guest_attestation.py",
    "experiments/consciousness_readout_validation/gpu_runner.py",
    "experiments/consciousness_readout_validation/inventory.py",
    "experiments/consciousness_readout_validation/paths.py",
    "experiments/consciousness_readout_validation/protocol.py",
    "experiments/consciousness_readout_validation/requirements-runpod-b200.txt",
    "experiments/consciousness_readout_validation/run_guest_preflight.sh",
    "experiments/consciousness_readout_validation/run_pilot_runpod.sh",
    "experiments/consciousness_readout_validation/runpod_lifecycle.py",
    "experiments/consciousness_readout_validation/runtime.py",
    "experiments/consciousness_readout_validation/stage_public_artifacts.py",
    "experiments/consciousness_readout_validation/tokenizer_audit.py",
    "experiments/consciousness_readout_validation/validate_plan.py",
    "tests/consciousness_readout_validation/__init__.py",
    "tests/consciousness_readout_validation/test_analysis.py",
    "tests/consciousness_readout_validation/test_analyze_pilot.py",
    "tests/consciousness_readout_validation/test_audit_pilot.py",
    "tests/consciousness_readout_validation/test_build_execution_binding.py",
    "tests/consciousness_readout_validation/test_guest_attestation.py",
    "tests/consciousness_readout_validation/test_guest_preflight_wrapper.py",
    "tests/consciousness_readout_validation/test_gpu_runner.py",
    "tests/consciousness_readout_validation/test_paths.py",
    "tests/consciousness_readout_validation/test_plan.py",
    "tests/consciousness_readout_validation/test_protocol.py",
    "tests/consciousness_readout_validation/test_runpod_lifecycle.py",
    "tests/consciousness_readout_validation/test_runtime.py",
    "tests/consciousness_readout_validation/test_stage_public_artifacts.py",
    "tests/consciousness_readout_validation/test_tokenizer_audit.py",
    "docs/consciousness_readout_validation/README.md",
    "docs/consciousness_readout_validation/PROTOCOL.md",
    "docs/consciousness_sae_switch_arc/PRO_REVIEW_RECEIPT.json",
    "docs/consciousness_sae_switch_arc/PRO_REVIEW_ADJUDICATION.md",
    "data/consciousness_readout_validation/README.md",
)


def repository_path_role(relative_path: str) -> str:
    if relative_path.startswith("experiments/"):
        return "source"
    if relative_path.startswith("tests/"):
        return "test"
    if relative_path.startswith("docs/") or relative_path.startswith("data/"):
        return "governing_document"
    raise ValueError(f"unclassified repository path: {relative_path}")
