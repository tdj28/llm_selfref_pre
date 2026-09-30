"""Report every planned job, including unattempted and unknown deliveries."""

from collections import Counter
import json
from .common import read_jsonl


def report_progress(base):
    plan = json.loads((base / "plan.json").read_text())
    finals = read_jsonl(base / "judgments.jsonl")
    starts = read_jsonl(base / "requests.jsonl")
    attempts = read_jsonl(base / "attempts.jsonl")
    final_ids = [r["judgment_id"] for r in finals]
    if len(set(final_ids)) != len(final_ids):
        raise ValueError("Duplicate final job IDs")
    final = {r["judgment_id"]: r for r in finals}
    attempted = {r["judgment_id"] for r in starts}
    received = {r["judgment_id"] for r in attempts}
    jobs = []
    providers = {}
    for provider in plan["models"]:
        counts = {}
        for phase, items in [("pilot", plan["pilot"]), ("target", plan["targets"])]:
            counter = Counter()
            for item in items:
                jid = f"{phase}:{provider}:{item['annotation_id']}"
                status = final[jid]["status"] if jid in final else (
                    "received_not_promoted" if jid in received else "started_unknown" if jid in attempted else "not_attempted")
                jobs.append({"judgment_id": jid, "status": status})
                counter[status] += 1
            missing = len(items) - counter["ok"]
            counts[phase] = {"planned": len(items), "statuses": dict(counter),
                             "missing_or_uncollected": missing,
                             "complete_collection": sum(counter[s] for s in ["ok", "invalid", "transport_error"]) == len(items),
                             "within_eight_missing_target_limit": missing <= 8 if phase == "target" else None}
        providers[provider] = counts
    return {"providers": providers, "jobs": jobs,
            "claim_boundary": "Operational coverage only; unknown and unattempted jobs are not denials."}
