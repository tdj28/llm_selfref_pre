"""Post-outcome retrieval-only repair; no new worker, pod, or scientific changes."""
import argparse
import importlib.util
import json
from pathlib import Path
import shlex
import subprocess
import sys

POD = "bwqtt22d3sh5dv"
AMENDMENT = "2eb0c0e05684a45c0bc2eb033c35d273740957c5"


def retrieval_run(command, *, manifest_command, run=subprocess.run, **kwargs):
    kind = "other"
    if Path(command[0]).name == "ssh" and command[-1] == manifest_command:
        if kwargs.get("timeout") != 60:
            raise ValueError("Unexpected manifest timeout")
        kwargs["timeout"], kind = 300, "manifest"
    elif Path(command[0]).name == "rsync":
        if kwargs.get("timeout") != 300:
            raise ValueError("Unexpected retrieval timeout")
        kwargs["timeout"], kind = 900, "rsync"
    try:
        return run(command, **kwargs)
    except subprocess.TimeoutExpired:
        print(json.dumps({"cleanup_timeout": kind, "seconds": kwargs.get("timeout")}), flush=True)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", required=True, type=Path)
    parser.add_argument("--amendment-root", required=True, type=Path)
    args = parser.parse_args()
    runtime = args.runtime_root.resolve()
    sys.path.insert(0, str(runtime))
    from experiments.steering_fidelity import controller as old
    spec = importlib.util.spec_from_file_location("bootstrap_a1", args.amendment_root / "scripts/steering_fidelity_bootstrap_a1.py")
    a1 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(a1)
    amendment = a1.verify_amendment(AMENDMENT, network=False)
    api = old.base.RunPodV2(__import__("os").environ.get("RUNPOD_API_KEY"), writable=True)
    ctrl = old.Controller(runtime / old.PLAN_RELATIVE, a1.SCIENCE_FREEZE, old.OWNED_OUT,
        "main", api, launch=True, attempt=1, approved_new_cap_usd="25")
    bound = ctrl.event("bootstrap-a1")["data"]["amendment"]
    if any(bound.get(k) != amendment.get(k) for k in ("amendment_freeze", "sources")):
        raise ValueError("A1 source binding differs")
    a1.apply_window(ctrl, bound)
    if ctrl.owned()["id"] != POD or not ctrl.event("closing") or ctrl.event("closed"):
        raise ValueError("Only the already closing, newly owned main pod is eligible")
    stopped = [e for e in ctrl.ledger.read() if e["id"].startswith("worker-stopped:")]
    if not stopped or stopped[-1]["data"].get("owned_group_quiescent") is not True:
        raise ValueError("Worker must already be quiescent")
    ctrl.ledger.bind("cleanup-a2", {"scope": "post_outcome_retrieval_timeouts_only",
        "pod_id": POD, "source_sha256": old.sha(Path(__file__)),
        "manifest_timeout_seconds": 300, "rsync_timeout_seconds": 900,
        "scientific_sources_unchanged": True, "caps_unchanged": True})
    command = "python3 -c " + shlex.quote(old.base.MANIFEST_SCRIPT)
    ctrl.run = lambda argv, **kw: retrieval_run(argv, manifest_command=command, **kw)
    result = ctrl.close_until_verified()
    print(json.dumps({"closed": result["data"], "receipt_sha256": result["sha256"]}), flush=True)


if __name__ == "__main__":
    main()
