"""Source-bound A1 lifecycle manifest, separate from the original forward plan."""
import argparse
import json
from pathlib import Path
import re
import subprocess

from experiments.sae_assay_diagnostic.protocol import canonical, sha

ROOT = Path(__file__).resolve().parents[2]
ORIGINAL_PLAN = "data/sae_assay_exposure/plan_20260930/PLAN.json"
ORIGINAL_SHA = "52797a6836f8f80d58a68071ffbcf473c61c205cc82de514c230407ddd5d49e9"
ORIGINAL_FREEZE = "1d7ec700ac1a91f133ac851d5e179aa8dcfa803e"
MANIFEST_PATH = "data/sae_assay_exposure/lifecycle_a1_20260930/PLAN.json"
DOCUMENT = "docs/SAE_ASSAY_EXPOSURE_LIFECYCLE_A1_20260930.md"
FAILED_ROOT = "data/sae_assay_exposure/startup_failure_20260930"
FAILED_POD = "6sr9s4hprynal1"
FAILED_COST = "0.4864956272222222222222222222"
PRIOR_TOTAL = "28.12156495135375832222222222"
REMAINING = "24.51350437277777777777777778"
SOURCES = ["experiments/sae_assay_exposure_lifecycle_a1/" + n for n in
           ("__init__.py", "controller.py", "protocol.py")]
SOURCES += ["tests/test_sae_assay_exposure_lifecycle_a1.py", DOCUMENT]
FAILURE_FILES = ("controller-stopped.json", "controller.log", "pip-freeze.txt", "receipts.jsonl",
                 "retrieval_and_cost.json", "PUBLICATION_AUDIT.json", "README.md")


def build_plan():
    from experiments.sae_assay_exposure import protocol as original
    original.load_plan(ROOT / ORIGINAL_PLAN)
    if sha(ROOT / ORIGINAL_PLAN) != ORIGINAL_SHA:
        raise ValueError("Original exposure plan changed")
    failure = json.loads((ROOT / FAILED_ROOT / "retrieval_and_cost.json").read_text())
    audit = json.loads((ROOT / FAILED_ROOT / "PUBLICATION_AUDIT.json").read_text())
    closure = failure["closure"]
    if (failure["plan_sha256"] != ORIGINAL_SHA or failure["freeze_commit"] != ORIGINAL_FREEZE
            or failure["status"] != "incomplete" or closure["pod_id"] != FAILED_POD
            or closure["get_status"] != 404 or closure["within_limits"] is not True
            or closure["compute_upper_bound_usd"] != FAILED_COST
            or closure["cumulative_upper_bound_usd"] != PRIOR_TOTAL
            or audit["clean_validated_rows"] != 0 or audit["precision_pilot"]["validated_rows"] != 0
            or set(failure["artifacts"]) != set(FAILURE_FILES[:4])
            or any(sha(ROOT / FAILED_ROOT / name) != checksum
                   for name, checksum in failure["artifacts"].items())):
        raise ValueError("Failed startup cost/provenance does not match amendment")
    return {"schema": "sae_exposure_lifecycle_a1_v1",
            "scope": "Operational process inspection and carried startup cost only; original science unchanged",
            "original_plan": {"path": ORIGINAL_PLAN, "sha256": ORIGINAL_SHA, "freeze_commit": ORIGINAL_FREEZE},
            "failed_startup": {"pod_id": FAILED_POD, "compute_upper_bound_usd": FAILED_COST,
                               "scientific_rows": 0, "get_status": 404},
            "budget": {"prior_total_usd": PRIOR_TOTAL, "total_usd": 200, "exposure_max_usd": REMAINING,
                       "new_paid_judge_calls": 0, "new_pro_calls": 0},
            "hardware": original.HARDWARE,
            "source_hashes": {name: sha(ROOT / name) for name in sorted(SOURCES)},
            "input_hashes": {FAILED_ROOT + "/" + name: sha(ROOT / FAILED_ROOT / name)
                             for name in sorted(FAILURE_FILES)}}


def load_plan(path, freeze=None):
    raw = Path(path).read_bytes()
    plan = json.loads(raw)
    if raw != (canonical(plan) + "\n").encode() or plan != build_plan():
        raise ValueError("A1 amendment/source/input drift")
    if freeze is not None:
        if not isinstance(freeze, str) or not re.fullmatch(r"[0-9a-f]{40}", freeze):
            raise ValueError("Full A1 execution freeze required")
        if subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip() != freeze:
            raise ValueError("Runtime checkout must equal A1 freeze")
    return plan


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    plan = build_plan()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x") as stream:
        stream.write(canonical(plan) + "\n")
    print(sha(args.out))
