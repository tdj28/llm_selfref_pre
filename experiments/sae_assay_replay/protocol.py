"""Source- and artifact-bound engineering replay; no outcome-based selection."""
import argparse
import json
from pathlib import Path
import subprocess

from experiments.sae_assay_diagnostic.protocol import canonical, sha
from experiments.sae_assay_diagnostic.backend import SAE_ID, SAE_REVISION, SAE_FILE_SHA256, TARGET_IDS
from experiments.sae_assay_repair.reproduce import verify_manifest

ROOT = Path(__file__).resolve().parents[2]
RELEASE = "data/sae_assay_repair/coordinate_delivery_20260930"
PRIOR_COST = "27.3845359753"
SOURCES = ["experiments/sae_assay_replay/" + n for n in (
    "__init__.py", "protocol.py", "backend.py", "runner.py", "analysis.py", "controller.py")]
SOURCES += ["experiments/sae_assay_diagnostic/" + n for n in (
    "protocol.py", "backend.py", "runner.py", "analysis.py", "budget.py", "controller.py",
    "fixtures.py", "requirements-gpu.txt")]
SOURCES += ["experiments/sae_assay_repair/" + n for n in (
    "feasibility.py", "reproduce.py", "protocol.py", "controller.py")]
SOURCES += ["docs/SAE_ASSAY_REPLAY_PROTOCOL_20260930.md"]


def build_plan():
    run = ROOT / RELEASE
    manifest = verify_manifest(run)
    qualification = json.loads((run / "rows/qualification-live.json").read_text())
    inputs = []
    for path in sorted((run / "rows").glob("clean-*.json")):
        row = json.loads(path.read_text())
        capture = run / row["capture"]["path"]
        if sha(capture) != row["capture"]["sha256"]:
            raise ValueError("Capture differs from raw row")
        inputs.append({"id": row["text_id"], "row_path": path.relative_to(ROOT).as_posix(),
                       "capture_path": capture.relative_to(ROOT).as_posix(),
                       "row_sha256": sha(path), "capture_sha256": sha(capture)})
    if len(inputs) != 544 or len({i["id"] for i in inputs}) != 544:
        raise ValueError("Expected all 544 saved states")
    prior_plan = json.loads((ROOT / "data/sae_assay_repair/plan_20260930/PLAN.json").read_text())
    sources = sorted(set(SOURCES) | set(prior_plan["source_hashes"]))
    return {"schema": "sae_native_replay_v1", "date": "2026-09-30",
            "scope": "Prospective engineering on previously observed states; not fresh validation or behavioral qualification",
            "input_release": RELEASE, "input_release_commit": "90765eab2ce1e4c6c27915a964a37868aafe4334",
            "input_manifest_sha256": sha(run / "RELEASE_MANIFEST.json"),
            "historical_freeze": manifest["freeze_commit"],
            "inputs": inputs, "feature_ids": list(TARGET_IDS),
            "gram": qualification["geometry"]["encoder_gram"],
            "sae": {"id": SAE_ID, "revision": SAE_REVISION, "sha256": SAE_FILE_SHA256},
            "hardware": {"gpu": "NVIDIA RTX A6000", "count": 1, "memory_gb": 48,
                         "hourly_price_ceiling_usd": .53, "hard_seconds": 7200},
            "operator": {"change": .75, "norm_cap": .04, "window": False,
                         "modes": ["zero", "suppression", "amplification"]},
            "first_five": [i["id"] for i in inputs[:5]],
            "budget": {"prior_total_usd": PRIOR_COST, "total_usd": 200, "replay_max_usd": 4,
                       "new_paid_judge_calls": 0, "new_pro_calls": 0},
            "source_hashes": {p: sha(ROOT / p) for p in sources}}


def load_plan(path, freeze=None):
    raw = Path(path).read_bytes()
    plan = json.loads(raw)
    if (canonical(plan) + "\n").encode() != raw or plan != build_plan():
        raise ValueError("Plan/source/input drift")
    if freeze is not None:
        if len(freeze) != 40 or any(c not in "0123456789abcdef" for c in freeze):
            raise ValueError("Full freeze SHA required")
        if subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip() != freeze:
            raise ValueError("Runtime checkout must equal freeze")
    return plan


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x") as stream:
        stream.write(canonical(build_plan()) + "\n")
    print(sha(args.out))
