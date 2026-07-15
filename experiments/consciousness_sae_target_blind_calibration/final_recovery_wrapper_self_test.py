#!/usr/bin/env python3
"""Local structural self-tests for the F13 launch chain."""

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
    CONTROLLER.name: "709117f71213073f0c2aa65871f4901594b6ce225968256d64dc8ca0ea5705e8",
    GATE.name: "4fd8f76c1e304eb3aaf2059b1fa222d59d99fedf2fae1f4b7a1ff6233210878d",
    VALIDATOR.name: "7475fcffd4487adce1490dab95f67995840b672ed4b8a40d4eb603cb3a5c4891",
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

    gate = load("f13_gate_selftest", GATE)
    validator = load("f13_validator_selftest", VALIDATOR)
    for module in (gate, validator):
        assert module.EXPECTED_CONTROLLER_SHA256 == EXPECTED_SHA256[CONTROLLER.name]
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
    assert "audit_recovery_landlock_gpt_pro_v9_inputs" in controller
    assert "V8_INPUT_REL" not in controller
    assert 'diff --quiet "$CODE_FREEZE" "$FINAL_FREEZE" -- experiments tests' in controller
    assert 'merge-base --is-ancestor "$CODE_FREEZE" "$REVIEWED_PACKET_COMMIT"' in controller
    assert 'merge-base --is-ancestor "$REVIEWED_PACKET_COMMIT" "$FINAL_FREEZE"' in controller
    assert controller.count("audit_recovery_landlock_gpt_pro_v9_completed/") == 5
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

    print("F13_LAUNCH_CHAIN_SELF_TEST_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
