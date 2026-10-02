"""Read-only A1 qualification replay and locked, byte-exact B1 ledger bootstrap.

No historical Git object, API client, or fresh fixture outcome is required.
The B1 plan binds the returned files and the original A1 source closure.
"""
from __future__ import annotations

from decimal import Decimal
import os
from pathlib import Path

from experiments.bilingual_llama_a1 import judges as a1_judges, protocol as a1

ROOT = a1.ROOT
INHERITED_RELEASE = "data/bilingual_llama_a1/fixture_budget_stop_20261002"
INHERITED_FREEZE = "5398dc657b6af3255e5938539f27255ffbe74b0d"
INHERITED_PLAN_HASH = "310bdfdd4946c7c1c1e004853779dd4ecb95ce94bf81781c3e406fd2aa4efee6"
INHERITED_MANIFEST_HASH = "1bd984778555460d363d2be8c1d53beb7788d76d5e35ff834344b10e0911c025"
FIXTURE_JOURNALS = ("snapshots.jsonl", "requests.jsonl", "attempts.jsonl", "judgments.jsonl")
INHERITED_COST_USD = Decimal("3.225516")


def verify_inherited_fixture_release():
    """Return deterministic, JSON-safe provenance after replaying frozen A1 bytes."""
    root = ROOT / INHERITED_RELEASE
    manifest_path = root / "MANIFEST.json"
    a1_judges._no_symlinks(manifest_path)
    if a1.sha(manifest_path) != INHERITED_MANIFEST_HASH:
        raise ValueError("Inherited A1 manifest changed")
    manifest = a1.strict_json(manifest_path.read_bytes())
    if (manifest["schema"] != "bilingual-a1-fixture-release"
            or manifest["freeze_commit"] != INHERITED_FREEZE
            or manifest["plan_sha256"] != INHERITED_PLAN_HASH):
        raise ValueError("Inherited A1 manifest provenance mismatch")
    expected = {"AUDIT.json", *("judges/" + name for name in FIXTURE_JOURNALS)}
    if {entry["path"] for entry in manifest["files"]} != expected or len(manifest["files"]) != len(expected):
        raise ValueError("Inherited A1 release inventory changed")
    files = [manifest_path.relative_to(ROOT).as_posix()]
    for entry in manifest["files"]:
        path = root / entry["path"]
        a1_judges._no_symlinks(path)
        if (not path.resolve().is_relative_to(root.resolve()) or not path.is_file()
                or path.stat().st_size != entry["bytes"] or a1.sha(path) != entry["sha256"]):
            raise ValueError("Inherited A1 release bytes changed: " + entry["path"])
        files.append(path.relative_to(ROOT).as_posix())
    if any((root / "judges" / name).exists() for name in a1_judges.RECEIPT_FILES
           if name not in FIXTURE_JOURNALS):
        raise ValueError("Unexpected inherited A1 receipt journal")
    plan_path = ROOT / a1.PLAN_PATH
    a1_judges._no_symlinks(plan_path)
    if a1.sha(plan_path) != INHERITED_PLAN_HASH:
        raise ValueError("Inherited A1 plan changed")
    # Current source/input hashes are checked without git show of the old freeze.
    plan = a1.load_plan(plan_path)
    a1_judges.prior_cost_provenance()
    ledger = a1_judges.Ledger(root / "judges")
    state = a1_judges.validate_receipts(ledger, plan, INHERITED_PLAN_HASH, INHERITED_FREEZE, [])
    a1_judges._require_healthy(state)
    wanted = {f"fixtures:{provider}:{instrument}:{item['id']}" for item in plan["fixtures"]
              for provider in a1_judges.MODELS for instrument in a1_judges.INSTRUMENTS}
    attempts = ledger.rows("attempts.jsonl")
    cost = sum((Decimal(str(row["cost_usd"])) for row in attempts), Decimal(0))
    gate = a1_judges.fixture_gate(state["finals"], plan["fixtures"])
    projection = a1_judges.project_budget(attempts, [], plan)
    audit = a1.strict_json((root / "AUDIT.json").read_bytes())
    hashes = {name: a1.sha(root / "judges" / name) for name in FIXTURE_JOURNALS}
    if (set(state["finals"]) != wanted or state["translations"] or len(attempts) != 128
            or any(row["phase"] != "fixtures" for row in attempts)
            or cost != INHERITED_COST_USD or gate["pass"] is not True
            or audit["gate"] != gate or audit["budget_projection"] != projection
            or projection["pass"] is not False or projection["api_cap_usd"] != "120"
            or Decimal(projection["projected_total_usd"]) != Decimal("122.642770")
            or audit["input_sha256"] != hashes or audit["receipts_verified"] is not True
            or audit["freeze_commit"] != INHERITED_FREEZE or audit["plan_sha256"] != INHERITED_PLAN_HASH
            or audit["attempts"] != 128 or audit["judgments"] != 128 or audit["missing"] != 0
            or Decimal(audit["fresh_cost_usd"]) != cost
            or Decimal(audit["prior_cost_usd"]) != a1_judges.PRIOR_JUDGING_USD
            or Decimal(audit["cumulative_pilot_cost_usd"]) != ledger.spent("judges")
            or audit["prior_gate_remains_failed"] is not True or audit["mismatches"]):
        raise ValueError("Inherited A1 semantic/cost reconstruction mismatch")
    return {"schema": "bilingual-b1-inherited-fixture-provenance", "files": sorted(files),
            "release": INHERITED_RELEASE, "manifest_sha256": INHERITED_MANIFEST_HASH,
            "freeze_commit": INHERITED_FREEZE, "plan_sha256": INHERITED_PLAN_HASH,
            "receipts_verified": True, "attempts": 128, "judgments": 128,
            "fresh_cost_usd": str(INHERITED_COST_USD),
            "prior_cost_usd": str(a1_judges.PRIOR_JUDGING_USD),
            "cumulative_pilot_cost_usd": str(INHERITED_COST_USD + a1_judges.PRIOR_JUDGING_USD),
            "gate": gate, "budget_projection": projection, "input_sha256": hashes,
            "prior_gate_remains_failed": True, "new_fixture_calls": 0,
            "interpretation": "inherited synthetic qualification, not human accuracy or language invariance"}


def _prefix_bytes():
    return {name: (ROOT / INHERITED_RELEASE / "judges" / name).read_bytes()
            for name in FIXTURE_JOURNALS}


def _check_prefix(ledger, prefixes):
    from .judges import RECEIPT_FILES
    ledger._cache.clear()
    for name in RECEIPT_FILES:
        data = ledger.receipt_bytes(name)
        prefix = prefixes.get(name, b"")
        if not isinstance(data, bytes) or not data.startswith(prefix):
            raise ValueError("Inherited fixture prefix changed or missing: " + name)
        rows = ledger.rows(name)
        for row in rows[len(prefix.splitlines()):]:
            if row.get("phase") == "fixtures" or row.get("snapshot", {}).get("phase") == "fixtures":
                raise ValueError("Extra fixture records are forbidden: " + name)


def verify_inherited_prefix(ledger):
    """Always check exact released bytes, including after target receipts append."""
    provenance = verify_inherited_fixture_release()
    _check_prefix(ledger, _prefix_bytes())
    return provenance


def bootstrap_qualified_ledger(target_path):
    """Import once under the OS lock; never overwrite an existing journal.

    A crash between exclusive file creations can resume only while every present
    journal is an exact inherited file and no subsequent receipts exist. A partial
    file or a missing prefix after target appends requires manual recovery.
    """
    from .judges import Ledger, RECEIPT_FILES, _no_symlinks
    provenance = verify_inherited_fixture_release()
    target = Path(target_path).absolute()
    _no_symlinks(target)
    if target.resolve().is_relative_to((ROOT / INHERITED_RELEASE).resolve()):
        raise ValueError("Cannot bootstrap inside the immutable A1 release")
    prefixes = _prefix_bytes()
    with Ledger(target) as ledger:
        present = {}
        for name in RECEIPT_FILES:
            path = target / name
            _no_symlinks(path)
            if path.exists():
                present[name] = path.read_bytes()
                if not present[name].startswith(prefixes.get(name, b"")):
                    raise ValueError("Inherited fixture prefix changed: " + name)
                ledger.rows(name)
        missing = set(prefixes) - set(present)
        if missing and any(data != prefixes.get(name, b"") for name, data in present.items()):
            raise ValueError("Cannot restore missing fixture prefix after ledger appends")
        for name in FIXTURE_JOURNALS:
            if name in missing:
                with (target / name).open("xb") as handle:
                    handle.write(prefixes[name])
                    handle.flush()
                    os.fsync(handle.fileno())
        _check_prefix(ledger, prefixes)
    return provenance
