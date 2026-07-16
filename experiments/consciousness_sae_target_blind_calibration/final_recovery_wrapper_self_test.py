#!/usr/bin/env python3
"""Local structural self-tests for the F15 launch chain."""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CONTROLLER = ROOT / "final_recovery_controller.sh"
GATE = ROOT / "final_recovery_hash_exec_gate.py"
VALIDATOR = ROOT / "validate_final_recovery_launch_gate.py"
SUPERVISOR = ROOT / "final_recovery_local_supervisor.sh"

EXPECTED_SHA256 = {
    CONTROLLER.name: "18b9de87e550c85863629be842c97f863b87ed1fa87cc1d3cdaed59becbe3704",
    GATE.name: "09cf18df192f54cc110faeb9c3da4750d75e09c07d499a17d5718a5ccee14b34",
    VALIDATOR.name: "609edd7368d6e775d0c5feca9122ad2cb33d77e1f45e2c705543c9cd8da68c06",
}
REJECTED_PODS = {"9n5f5a82p1gw1e", "eeo1skjkwjqot5", "j7xr357tdlpq3f"}
REJECTED_ATTEMPTS = {
    "calv2-r3-audit-recovery-2479ed0-20260715T155035Z",
    "calv2-r3-audit-recovery-2479ed0-20260715T165648Z",
    "calv2-r3-audit-recovery-497b0f8-20260715T191757Z",
}
REJECTED_AUTH_RECEIPTS = {
    "f6d0fa7fdf5b6ec8553fce2fe8df7842dd28f5a63fb5a9674a6358d4af152358",
    "8cb249316e406f795150cb55409c6053b8e29c4b510918ea7c539bbb969306d4",
}
REJECTED_AUTH_FILES = {
    "897a0fe5fac8e898f6367b8115a982a7580c0224843a76e2514589f6277274a7",
    "682e5a612e48e196a46ea762fe00ab4de32df1bf070aa72edf64d2639735f5ff",
}
REJECTED_V9_CONTROLLER_SHA = (
    "ca9d6606b992507dd9e76afbb9fc219222c858831c93a385de22ac56d4b80006"
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    for script in (CONTROLLER, SUPERVISOR):
        subprocess.run(["bash", "-n", script], check=True)
    for script in (GATE, VALIDATOR):
        ast.parse(script.read_text(encoding="utf-8"), filename=script.as_posix())
    for filename, expected in EXPECTED_SHA256.items():
        assert sha256(ROOT / filename) == expected

    gate = load("f15_gate_selftest", GATE)
    validator = load("f15_validator_selftest", VALIDATOR)
    for module in (gate, validator):
        assert module.PROTOCOL_VERSION == "final_recovery_hash_exec_gate_v1.2.0"
        assert str(module.EXPECTED_CONTROLLER_PATH) == (
            "/root/final_recovery_controller_f15.sh"
        )
        assert module.EXPECTED_CONTROLLER_SHA256 == EXPECTED_SHA256[CONTROLLER.name]
        assert REJECTED_V9_CONTROLLER_SHA in set(module.REJECTED_CONTROLLER_SHA256)
        assert set(module.REJECTED_POD_IDS) == REJECTED_PODS
        assert set(module.REJECTED_ATTEMPT_IDS) == REJECTED_ATTEMPTS
        assert REJECTED_AUTH_RECEIPTS <= set(
            module.REJECTED_AUTHORIZATION_RECEIPT_SHA256
        )
        assert REJECTED_AUTH_FILES <= set(module.REJECTED_AUTHORIZATION_FILE_SHA256)
        assert module.ATTEMPT_RE.fullmatch(
            "calv2-r3-audit-recovery-abcdef0-20260715T200000Z"
        )
        assert all(module.ATTEMPT_RE.fullmatch(value) for value in REJECTED_ATTEMPTS)

    controller = CONTROLLER.read_text(encoding="utf-8")
    supervisor = SUPERVISOR.read_text(encoding="utf-8")
    for token in (
        REJECTED_PODS
        | REJECTED_ATTEMPTS
        | REJECTED_AUTH_RECEIPTS
        | REJECTED_AUTH_FILES
    ):
        assert token in controller
        assert token in supervisor or token in GATE.read_text(encoding="utf-8")
    assert "audit_recovery_landlock_gpt_pro_v10_inputs" in controller
    assert "V9_INPUT_REL" not in controller
    assert 'diff --quiet "$CODE_FREEZE" "$FINAL_FREEZE" -- experiments tests' in controller
    assert 'merge-base --is-ancestor "$CODE_FREEZE" "$REVIEWED_PACKET_COMMIT"' in controller
    assert 'merge-base --is-ancestor "$REVIEWED_PACKET_COMMIT" "$FINAL_FREEZE"' in controller
    assert controller.count("audit_recovery_landlock_gpt_pro_v10_completed/") == 5
    assert "completed_conditional_provider_review_v9_adjudication" in controller
    assert 'value["final_decision"] == "NOT_READY_TO_EXECUTE"' in controller
    assert "V10_EXPECTED_PREREVIEW_PATHS" in controller
    assert controller.count("CUBLAS_WORKSPACE_CONFIG=:4096:8") == 2

    supervisor_bindings = {
        key: re.search(rf"^{key}=([0-9a-f]{{64}})$", supervisor, re.MULTILINE).group(1)
        for key in (
            "EXPECTED_CONTROLLER_SHA",
            "EXPECTED_GATE_SHA",
            "EXPECTED_GATE_VALIDATOR_SHA",
        )
    }
    assert supervisor_bindings == {
        "EXPECTED_CONTROLLER_SHA": EXPECTED_SHA256[CONTROLLER.name],
        "EXPECTED_GATE_SHA": EXPECTED_SHA256[GATE.name],
        "EXPECTED_GATE_VALIDATOR_SHA": EXPECTED_SHA256[VALIDATOR.name],
    }

    valid_shape = [
        "a" * 40,
        "b" * 40,
        "c" * 40,
        "freshpod123",
        "2026-07-15T20:00:00Z",
        "calv2-r3-audit-recovery-ccccccc-20260715T200000Z",
        "/root/final-recovery-inputs-selftest",
    ]
    for index in range(7):
        argv = valid_shape.copy()
        argv[index] = ""
        result = subprocess.run(
            ["bash", CONTROLLER, *argv],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        assert result.returncode != 0
        assert "FINAL_RECOVERY_CONTROLLER_START" not in result.stdout

    print("F15_LAUNCH_CHAIN_SELF_TEST_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
