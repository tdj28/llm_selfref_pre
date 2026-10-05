"""Read-only provider checks and prospective metadata, never inference."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from urllib.request import urlopen

from experiments.openrouter_swap.runner import write_once
from . import protocol


def collect():
    ids = {s["id"] for s in [*protocol.MODELS.values(), *protocol.JUDGES.values()]}
    snapshots = {}
    for model in sorted(ids):
        with urlopen(f"https://openrouter.ai/api/v1/models/{model}/endpoints", timeout=30) as response:
            snapshots[model] = json.load(response)["data"]
    with urlopen("https://openrouter.ai/api/v1/endpoints/zdr", timeout=30) as response:
        zdr = [e for e in json.load(response)["data"] if e.get("model_id") in ids]
    return {"approved": True, "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
            "endpoint_snapshots": snapshots, "zdr_endpoints": zdr,
            "account_balance_usd": "165", "external_reserve_usd": "45",
            "budget_note": "Conservative balance floor checked before freeze; live balance is checked again before bulk. New owner authorization is incremental, at most USD130."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    value = collect()
    write_once(Path(args.out), value)
    print(json.dumps({"snapshots": len(value["endpoint_snapshots"]), "out": args.out}))
