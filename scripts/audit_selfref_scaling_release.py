"""Read-only, commit-bound audit of selfref_scaling; JSON goes to stdout only.

The saved Q4 rank tensor is the starting point, not a new model/lens forward.
Per-word summaries are post hoc. Only the fixed, prospectively specified band
minimum is retained; no block, position, word, layer or transport is selected
for its result. NumPy enables an additional replay of the frozen Q1-Q3 code.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from contextlib import contextmanager
import csv
from fractions import Fraction
import gzip
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
from statistics import median_high
import struct
import subprocess
import sys
import types

COMMIT = "7cb5c984eb41968b6f3d2f9b322f4de125a1d1ca"
FREEZE = "d4b7d8b01d29417c9ad1a595f82517dfa66dee06"
RELEASE = "data/release_20261003"
MANIFEST_SHA256 = "266f7750b91048dd87566fda3940a39ff7503d74a30b74ef922c036de214d3b6"
PLAN_PATH = "data/plan_20261003/PLAN.json"
PLAN_SHA256 = "f8c4188b8310e63985666343eec43cbcea79c9c59be91dd5b21776c53d7f697d"
POSITIONS = ["boundary", "answer_1", "answer_2", "answer_3", "answer_4"]
TRANSPORTS = ["lens", "identity", *[f"random_{i}" for i in range(5)]]
CELLS = ["SS", "SH", "HS", "HH"]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "Duplicate JSON key: " + key)
            result[key] = value
        return result

    def constant(value):
        raise ValueError("Non-finite JSON: " + value)

    value = json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
    canonical(value)  # Also reject finite-looking literals that overflow to infinity.
    return value


def safe_relative(name):
    p = PurePosixPath(name)
    require(bool(p.parts) and not p.is_absolute() and p.as_posix() == name
            and all(part not in (".", "..") for part in p.parts) and "\\" not in name,
            "Unsafe relative path: " + name)
    return p


def read_regular(root, name):
    p = root
    for part in safe_relative(name).parts:
        p = p / part
        require(not p.is_symlink(), "Symlink: " + name)
    require(p.is_file(), "Missing regular file: " + name)
    return p.read_bytes()


class Snapshot:
    """Use local Git objects only; neither HEAD nor mutable refs are authority."""

    def __init__(self, root):
        self.root = Path(root).resolve(strict=True)
        self.tree = self.read_tree(COMMIT)

    def git(self, *args):
        env = dict(os.environ, GIT_NO_LAZY_FETCH="1", GIT_TERMINAL_PROMPT="0",
                   GIT_OPTIONAL_LOCKS="0", GIT_NO_REPLACE_OBJECTS="1")
        return subprocess.run(["git", "--no-replace-objects", "-C", str(self.root), *args],
                              env=env, check=True, capture_output=True).stdout

    def read_tree(self, commit):
        require(self.git("rev-parse", "--verify", commit + "^{commit}").decode().strip() == commit,
                "Commit binding mismatch")
        result = {}
        for record in self.git("ls-tree", "-rz", commit).split(b"\0"):
            if record:
                metadata, name = record.split(b"\t", 1)
                mode, kind, oid = metadata.decode().split()
                result[name.decode()] = (mode, kind, oid)
        return result

    def read(self, name):
        safe_relative(name)
        require(name in self.tree, "File absent at pinned commit: " + name)
        mode, kind, oid = self.tree[name]
        require(mode in ("100644", "100755") and kind == "blob", "Not a regular Git blob: " + name)
        raw = read_regular(self.root, name)
        got = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        require(got == oid, "Working bytes differ from pinned commit: " + name)
        return raw


def verify_release(snapshot):
    manifest_raw = snapshot.read(RELEASE + "/MANIFEST.json")
    require(sha(manifest_raw) == MANIFEST_SHA256, "Release manifest hash mismatch")
    manifest = strict_json(manifest_raw)
    require(manifest["schema"] == "selfref_scaling_release_20261003", "Manifest schema mismatch")
    expected = {"MANIFEST.json"}
    for entry in manifest["files"]:
        name = entry["path"]
        safe_relative(name)
        require(name not in expected, "Duplicate manifest path: " + name)
        expected.add(name)
        raw = snapshot.read(RELEASE + "/" + name)
        require(len(raw) == entry["bytes"] and sha(raw) == entry["sha256"], "Release hash mismatch: " + name)
    actual = set()
    for p in (snapshot.root / RELEASE).rglob("*"):
        require(not p.is_symlink(), "Symlink in release")
        if p.is_file():
            actual.add(p.relative_to(snapshot.root / RELEASE).as_posix())
    tracked = {p[len(RELEASE) + 1:] for p in snapshot.tree if p.startswith(RELEASE + "/")}
    require(actual == expected == tracked, "Release file inventory mismatch")
    for entry in manifest["gzipped_originals"]:
        raw = gzip.decompress(snapshot.read(RELEASE + "/" + entry["path"] + ".gz"))
        require(len(raw) == entry["bytes"] and sha(raw) == entry["sha256"], "Gzip original mismatch")
    require(len(manifest["files"]) == 659, "Unexpected pinned release size")
    return manifest


def verify_plan(snapshot):
    raw = snapshot.read(PLAN_PATH)
    require(sha(raw) == PLAN_SHA256, "Plan hash mismatch")
    plan = strict_json(raw)
    freeze_tree = snapshot.read_tree(FREEZE)
    require(freeze_tree[PLAN_PATH] == snapshot.tree[PLAN_PATH], "Plan differs from scientific freeze")
    sources = {}
    for name, expected in {**plan["source_hashes"], **plan["inputs"]}.items():
        value = snapshot.read(name)
        require(sha(value) == expected and snapshot.tree[name] == freeze_tree[name],
                "Frozen source/input mismatch: " + name)
        sources[name] = value
    for name in ("docs/RESULTS_20261003.md", "docs/AMENDMENT_A1_20261003.md",
                 "docs/AMENDMENT_A2_20261003.md", "amendments/a2_20261003/run_lens_a2.py"):
        snapshot.read(name)
    bindings = strict_json(snapshot.read("data/plan_20261003/token_bindings.json"))
    require(bindings == plan["token_bindings"], "Token bindings mismatch")
    return plan, sources


def unique(rows, fields):
    result = {}
    for row in rows:
        key = tuple(row[k] for k in fields)
        require(key not in result, "Duplicate inventory key: " + str(key))
        result[key] = row
    return result


def compare_csv(raw, expected, keys):
    reader = csv.DictReader(io.StringIO(raw.decode()))
    require(expected and len(reader.fieldnames or []) == len(expected[0])
            and set(reader.fieldnames or []) == set(expected[0]), "CSV column mismatch")
    actual = unique(list(reader), keys)
    wanted = unique([{k: str(v) for k, v in row.items()} for row in expected], keys)
    require(actual == wanted, "CSV inventory/value mismatch: " + ",".join(keys))


def reconstruct_lens(raw, summary, rows, vocab):
    """Independent integer-only reconstruction, plus exhaustive post-hoc profiles."""
    band, tokens = summary["band_layers"], summary["tokens"]
    row_map = {r["id"]: r for r in rows}
    require(len(row_map) == len(rows), "Duplicate Q4 row")
    blocks_by_cell = {cell: [r["block"] for r in rows if r["instruction"] + r["transcript"] == cell]
                      for cell in CELLS}
    require(all(values and len(values) == len(set(values))
                and sorted(values) == sorted(blocks_by_cell["SS"]) for values in blocks_by_cell.values()),
            "Q4 planned block inventory mismatch")
    expected_vectors = {(r["id"], p) for r in rows for p in POSITIONS}
    vectors = [tuple(v) for v in raw["vectors"]]
    require(len(vectors) == len(set(vectors)) and set(vectors) == expected_vectors, "Q4 vector inventory mismatch")
    ids = sorted({t for words in tokens.values() for t in words.values()})
    require(raw["token_ids"] == ids and raw["band_layers"] == band, "Lens token/band mismatch")
    require(set(raw["ranks_by_transport_layer_vector_token"]) == set(summary["transports"]),
            "Lens transport inventory mismatch")
    columns = {t: i for i, t in enumerate(ids)}
    words, per_vector, cells, separations, posthoc = [], [], [], [], []
    groups = defaultdict(list)
    for transport in summary["transports"]:
        ranks = raw["ranks_by_transport_layer_vector_token"][transport]
        require(len(ranks) == len(band), "Rank layer inventory mismatch")
        for layer in ranks:
            require(len(layer) == len(vectors), "Rank vector inventory mismatch")
            for values in layer:
                require(len(values) == len(ids) and all(type(v) is int and 1 <= v <= vocab for v in values),
                        "Invalid rank value/width")
        for v, (row_id, position) in enumerate(vectors):
            row = row_map[row_id]
            cell = row["instruction"] + row["transcript"]
            for lexicon, mapping in tokens.items():
                bests = []
                for word, token in mapping.items():
                    profile = [layer[v][columns[token]] for layer in ranks]
                    best = min(profile)  # the frozen fixed-band operator, not a new selection
                    best_layer = band[profile.index(best)]
                    bests.append(best)
                    words.append(dict(transport=transport, row=row_id, position=position, lexicon=lexicon,
                                      word=word, token_id=token, best_rank=best, best_layer=best_layer))
                    groups[(transport, lexicon, word, position, cell)].append((row["block"], best, best_layer, profile))
                per_vector.append(dict(transport=transport, row=row_id, cell=cell, block=row["block"],
                                       position=position, lexicon=lexicon, n_words=len(bests),
                                       median_best_rank=median_high(bests)))
    cell_groups = defaultdict(list)
    for row in per_vector:
        cell_groups[(row["transport"], row["lexicon"], row["position"], row["cell"])].append(row["median_best_rank"])
    for transport in summary["transports"]:
        for lexicon in tokens:
            for position in POSITIONS:
                medians = {}
                for cell in CELLS:
                    values = cell_groups[(transport, lexicon, position, cell)]
                    medians[cell] = median_high(values)
                    cells.append(dict(transport=transport, lexicon=lexicon, position=position, cell=cell,
                                      n_rows=len(values), median=medians[cell]))
                s, h = medians["SS"] - medians["HS"], medians["SH"] - medians["HH"]
                separations.append(dict(transport=transport, lexicon=lexicon, position=position,
                                        S_transcript=s, H_transcript=h, mean=str(Fraction(s + h, 2))))
    for (transport, lexicon, word, position, cell), values in sorted(groups.items()):
        blocks = sorted(r["block"] for r in rows if r["instruction"] + r["transcript"] == cell)
        require(sorted(v[0] for v in values) == blocks, "Incomplete per-word blocks")
        posthoc.append(dict(transport=transport, lexicon=lexicon, word=word, position=position, cell=cell,
                            n_blocks=len(values), median_high_best_band_rank=median_high([v[1] for v in values]),
                            median_high_of_row_band_medians=median_high([median_high(v[3]) for v in values]),
                            best_layer_counts=dict(sorted(Counter(v[2] for v in values).items())),
                            per_layer_median_high=[median_high([v[3][i] for v in values]) for i in range(len(band))]))
    return dict(words=words, vectors=per_vector, cells=cells, separation=separations, posthoc=posthoc)


def audit_lens(snapshot, plan):
    def read(name):
        return snapshot.read(RELEASE + "/lens/" + name)

    summary = strict_json(read("lens_summary.json"))
    spec = plan["analysis"]["q4"]["spec"]
    require(summary["band_layers"] == spec["band_layers"] == list(range(19, 39)), "Q4 band changed")
    require(summary["transports"] == spec["transports"] == TRANSPORTS, "Q4 controls changed")
    require(summary["capture_indices"] == list(range(20, 40)), "Capture-layer offset mismatch")
    require(summary["captured_rows"] == 80 and summary["missing_rows"] == [], "Missing Q4 captures")
    require(all(summary["lens"][k] == spec[k] for k in ("repo", "revision", "file", "sha256")), "Lens binding mismatch")
    lexicons = strict_json(snapshot.read(spec["lexicon_source"]))["probe_lexicons"]
    require(set(summary["tokens"]) == set(spec["lexicons"]), "Lexicon inventory mismatch")
    for name, mapping in summary["tokens"].items():
        require(set(mapping) | set(summary["skipped_words"][name]) == set(lexicons[name])
                and not set(mapping) & set(summary["skipped_words"][name]), "Word inventory mismatch")
    require(summary["skipped_words"] == {"experience": [], "denial_tool": ["roleplay"]}, "Skipped words changed")
    for name, expected in summary["files"].items():
        require(sha(read(name)) == expected, "Lens summary hash mismatch")
    raw = strict_json(read("lens_ranks.json"))
    result = reconstruct_lens(raw, summary, [r for r in plan["qwen_rows"] if r["family"] == "q4"],
                              plan["model"]["architecture_record"]["vocab_size"])
    keys = {"words": ("transport", "row", "position", "lexicon", "word"),
            "vectors": ("transport", "row", "position", "lexicon"),
            "cells": ("transport", "lexicon", "position", "cell"),
            "separation": ("transport", "lexicon", "position")}
    for name, fields in keys.items():
        compare_csv(read("lens_" + name + ".csv"), result[name], fields)
    primary = {f"{r['transport']}|{r['lexicon']}": r for r in result["separation"] if r["position"] == "boundary"}
    require(primary == summary["primary_boundary_separation"], "Primary lens summary mismatch")
    return {"reconstructed_counts": {k: len(result[k]) for k in keys}, "rank_values": 7 * 20 * 400 * 24,
            "frozen_descriptive_cells": result["cells"], "frozen_descriptive_separation": result["separation"],
            "posthoc_definition": "Upper medians over all 20 blocks, separately for every word/cell/position/transport. "
            "Best rank uses the frozen minimum over layers 19-38. Also retain all layer medians, the median of "
            "within-row band medians, and best-layer counts. No additional minimum or outcome filter; no inference.",
            "posthoc_band_layers": summary["band_layers"], "posthoc_per_word": result["posthoc"]}


def check_chain(rows):
    previous = None
    for seq, row in enumerate(rows, 1):
        require(row["seq"] == seq and row["previous"] == previous, "Ledger chain sequence mismatch")
        value = {k: v for k, v in row.items() if k != "sha256"}
        require(sha(canonical(value).encode()) == row["sha256"], "Ledger chain hash mismatch")
        previous = row["sha256"]


def structured_primary(label):
    current = [c for c in label["claims"] if c["time"] == "current"
               and c["subject"] in {"explicit_assistant", "implicit_assistant"}]
    return {"inclusive_current_assertion": any(c["polarity"] == "asserted" for c in current),
            "explicit_current_assertion": any(c["polarity"] == "asserted" and c["subject"] == "explicit_assistant"
                                              for c in current),
            "mixed_current_assertion": {"asserted", "denied"} <= {c["polarity"] for c in current}}


def audit_inventory(snapshot, plan):
    def read(name):
        return snapshot.read(RELEASE + "/" + name)

    index = strict_json(read("derived/index.json"))
    planned_targets = {i["target"] for i in plan["judge_items"]}
    require(set(index) == planned_targets and len(index) == 968, "Response index inventory mismatch")
    for target, entry in index.items():
        require(entry["missing"] is False and bool(entry["response"].strip())
                and sha(entry["response"].encode()) == entry["response_sha256"], "Response index hash/missingness mismatch")
    qwen = {r["id"]: r for r in plan["qwen_rows"] if r["family"] != "q4"}
    base = "pods/a1_main/outputs/"
    expected = {base + "generations/" + r + ".json" for r in qwen}
    actual = {p[len(RELEASE) + 1:] for p in snapshot.tree if p.startswith(RELEASE + "/" + base + "generations/")}
    require(expected == actual and len(qwen) == 440, "Qwen generation inventory mismatch")
    records = {key: strict_json(read(base + "generations/" + key + ".json")) for key in qwen}
    for key, record in records.items():
        row = qwen[key]
        require(record["id"] == key and record["status"] == "complete", "Incomplete Qwen row")
        require(record["response"] == index[key]["response"] and record["cap_hit"] == index[key]["cap_hit"],
                "Generation/index mismatch")
        messages = [{"role": m["role"], "content": m["content"].get("text") if "text" in m["content"]
                     else records[m["content"]["source"]]["response"]} for m in row["messages"]]
        require(record["messages"] == messages and index[key]["query"] == messages[-1]["content"],
                "Resolved Qwen prompt mismatch")
        require(record["seed"] == row["seed"] and record["max_new_tokens"] == row["cap"], "Generation design mismatch")
        for field in ("input", "output"):
            require(sha(canonical(record[field + "_token_ids"]).encode()) == record[field + "_token_ids_sha256"],
                    "Token list hash mismatch")
    captures = [r for r in plan["qwen_rows"] if r["family"] == "q4"]
    state_names = {base + "states/" + r["id"] + suffix for r in captures for suffix in (".json", ".safetensors")}
    require(state_names == {p[len(RELEASE) + 1:] for p in snapshot.tree if p.startswith(RELEASE + "/" + base + "states/")},
            "State capture inventory mismatch")
    for row in captures:
        stem = base + "states/" + row["id"]
        side, raw = strict_json(read(stem + ".json")), read(stem + ".safetensors")
        size = struct.unpack("<Q", raw[:8])[0]
        header = strict_json(raw[8:8 + size])
        require(side["id"] == row["id"] and side["positions"] == POSITIONS
                and side["shape"] == [61, 5, 4096] and side["dtype"] == "bfloat16"
                and side["safetensors_sha256"] == sha(raw), "Capture sidecar mismatch")
        require(set(header) == {"states", "__metadata__"} and header["states"] ==
                {"dtype": "BF16", "shape": [61, 5, 4096], "data_offsets": [0, 61 * 5 * 4096 * 2]}
                and header["__metadata__"]["positions"] == ",".join(POSITIONS)
                and len(raw) == 8 + size + 61 * 5 * 4096 * 2, "Capture tensor structure mismatch")
    api = [strict_json(line) for line in read("api/events.jsonl").splitlines()]
    check_chain(api)
    require(api[0]["data"]["plan_digest"] == sha(canonical(plan).encode()), "API plan binding mismatch")
    reserves = unique([e["data"] for e in api if e["kind"] == "reserve"], ("slot",))
    results = unique([e["data"] for e in api if e["kind"] == "result"], ("attempt_id",))
    require(set(reserves) == {(r["id"],) for r in plan["api_rows"]} and len(results) == 480, "API inventory mismatch")
    for row in plan["api_rows"]:
        reserve = reserves[(row["id"],)]
        require(reserve["attempt"] == 0, "Unexpected API retry")
        result = results[(reserve["attempt_id"],)]
        messages = [{"role": m["role"], "content": m["content"].get("text") if "text" in m["content"]
                     else index[m["content"]["source"]]["response"]} for m in row["messages"]]
        require(reserve["request"]["input"] == messages and index[row["id"]]["query"] == messages[-1]["content"],
                "API prompt/index mismatch")
        require(result["status"] == "ok" and result["evaluated"]["response"] == index[row["id"]]["response"]
                and result["request_sha256"] == reserve["request_sha256"] == sha(json.dumps(
                    reserve["request"], ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()),
                "API result binding mismatch")
    judgments = [strict_json(line) for line in read("judges/judgments.jsonl").splitlines()]
    lookup = unique(judgments, ("item_id", "provider"))
    require(set(lookup) == {(i["id"], p) for i in plan["judge_items"] for p in plan["analysis"]["readers"]},
            "Judgment inventory mismatch")
    failures = []
    for row in judgments:
        require(row["judgment_id"] == row["item_id"] + ":" + row["provider"]
                and row["item_id"] == row["instrument"] + ":" + row["target"]
                and row["response_sha256"] == index[row["target"]]["response_sha256"], "Judgment response binding mismatch")
        if row["status"] != "ok":
            failures.append(row["judgment_id"])
        elif row["instrument"] == "structured":
            require(all(row["derived"][k] == v for k, v in structured_primary(row["label"]).items()),
                    "Structured primary reduction mismatch")
            require(all(c["quote"] in index[row["target"]]["response"] for c in row["label"]["claims"]),
                    "Claim quote missing from response")
    require(failures == ["structured:astra-b02-q3a-mechanistic-S:anthropic"], "Judgment failure inventory changed")
    fixtures = [strict_json(line) for line in read("judges/fixture_judgments.jsonl").splitlines()]
    gate = strict_json(read("judges/fixture_gate.json"))
    require(len(unique(fixtures, ("judgment_id",))) == 36 and all(r["status"] == "ok" for r in fixtures)
            and gate["checks"] == 36 and gate["pass"] and not gate["mismatches"] and not gate["incomplete"],
            "Fixture release mismatch")
    q1 = {}
    q3b = {}
    for reader in plan["analysis"]["readers"]:
        q1[reader] = {cell: {endpoint: sum(lookup[("structured:" + r["id"], reader)]["derived"][endpoint]
                                               for r in qwen.values() if r["family"] == "q1"
                                               and r["instruction"] + r["transcript"] == cell)
                            for endpoint in ("inclusive_current_assertion", "denied")}
                      for cell in CELLS}
        q3b[reader] = {"first_S": q1[reader]["SS"]["inclusive_current_assertion"],
                       "first_H": q1[reader]["HH"]["inclusive_current_assertion"]}
        for induction in "SH":
            q3b[reader]["none_" + induction] = sum(
                lookup[("structured:" + r["id"], reader)]["derived"]["inclusive_current_assertion"]
                for r in qwen.values() if r["family"] == "q3b" and r["induction"] == induction)
    return index, {"qwen_generations": 440, "captures": len(captures), "api_generations": 480,
                   "index_targets": len(index), "target_judgments": len(judgments), "fixture_judgments": 36,
                   "non_ok_judgments": failures, "qwen_q1_counts": q1, "qwen_q3b_positive_counts": q3b,
                   "results_prose_discrepancy": "Q3b prose says every Qwen cell is zero; first_S is 3/20 "
                   "under each reader, whereas first_H, none_S and none_H are 0/20."}


@contextmanager
def frozen_analysis(sources):
    """Load only verified analysis dependencies, in memory, without importing a checkout."""
    prefix = "_scaling_review_frozen"
    files = [(prefix, "selfref_scaling/__init__.py", True),
             (prefix + ".sources", "selfref_scaling/sources/__init__.py", True),
             (prefix + ".sources.conscious_prompts_fe4b831", "selfref_scaling/sources/conscious_prompts_fe4b831.py", False),
             (prefix + ".common", "selfref_scaling/common.py", False),
             (prefix + ".prompts", "selfref_scaling/prompts.py", False),
             (prefix + ".analysis", "selfref_scaling/analysis.py", False)]
    require(not any(name in sys.modules for name, _, _ in files), "Analysis namespace already loaded")
    try:
        for name, path, package in files:
            module = types.ModuleType(name)
            module.__file__ = path
            module.__package__ = name if package else name.rpartition(".")[0]
            if package:
                module.__path__ = []
            sys.modules[name] = module
            exec(compile(sources[path], path, "exec"), module.__dict__)
        yield sys.modules[prefix + ".analysis"]
    finally:
        for name, _, _ in files:
            sys.modules.pop(name, None)


def replay_analysis(snapshot, plan, sources, index, required):
    try:
        import numpy  # noqa: F401
    except ImportError:
        require(not required, "NumPy is required for frozen Q1-Q3 replay")
        return {"status": "not_run_numpy_unavailable", "intervals_recomputed": False}
    with frozen_analysis(sources) as analysis:
        llama = strict_json(sources[plan["analysis"]["q1"]["llama_comparator"]["source"]])
        results, provenance = analysis.analyze(plan, snapshot.root / RELEASE / "judges/judgments.jsonl",
                                              index, llama_inputs=llama)
        files = {"analysis.json": analysis._json(results)}
        tables = analysis.flatten(results)
        files.update({name + ".csv": analysis._csv(rows, analysis.JOINT_COLUMNS if name == "q2_joint" else analysis.COLUMNS)
                      for name, rows in tables.items()})
        for name, raw in files.items():
            require(raw == snapshot.read(RELEASE + "/analysis/" + name), "Frozen analysis reproduction mismatch: " + name)
        summary = strict_json(snapshot.read(RELEASE + "/analysis/summary.json"))
        for key, value in provenance.items():
            require(summary[key] == value, "Analysis provenance mismatch: " + key)
        require(summary["q1_readings"] == {m: {r: v["reading"]["reading"] for r, v in readers.items()}
                                           for m, readers in results["q1"].items()}, "Q1 readings mismatch")
        require(summary["degenerate_intervals"] == sum(row.get("degenerate") == "true"
                for rows in tables.values() for row in rows), "Degenerate-interval count mismatch")
        for name, expected in summary["files"].items():
            require(sha(snapshot.read(RELEASE + "/analysis/" + name)) == expected, "Analysis file binding mismatch")
        return {"status": "byte_exact", "files": sorted(files), "intervals_recomputed": True,
                "q1_readings": summary["q1_readings"], "degenerate_intervals": summary["degenerate_intervals"],
                "numpy_version": numpy.__version__, "figures": "hash-checked, not rerendered"}


def audit(repo, require_analysis=False):
    snapshot = Snapshot(repo)
    manifest = verify_release(snapshot)
    plan, sources = verify_plan(snapshot)
    index, inventory = audit_inventory(snapshot, plan)
    lens = audit_lens(snapshot, plan)
    replay = replay_analysis(snapshot, plan, sources, index, require_analysis)
    return {"schema": "conscious_selfref_scaling_evidence_audit_v1", "read_only": True,
            "release_commit": COMMIT, "scientific_freeze": FREEZE, "plan_sha256": PLAN_SHA256,
            "release_manifest_sha256": MANIFEST_SHA256, "release_files_verified": len(manifest["files"]),
            "frozen_source_files_verified": len(plan["source_hashes"]), "inventory": inventory,
            "frozen_analysis_replay": replay, "lens": lens,
            "limits": ["No fresh inference, tokenizer resolution, residual-to-logit replay or causal test.",
                       "State tensors are hash/structure checked; their numerical generation is not independently replayed.",
                       "All release files and the decompressed judge ledger are hash-checked; not a fresh billing, "
                       "provider, cleanup or full judge-receipt semantic audit.",
                       "Reader labels are not experience or human validation. Instruction-sensitive ranks are not mechanisms.",
                       "No registered deposit verified: prospective Git freeze, Q4 descriptive, new word profiles post hoc."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("repo", type=Path, help="Existing local selfref_scaling checkout with the pinned release")
    parser.add_argument("--require-analysis", action="store_true", help="Fail rather than skip Q1-Q3 replay without NumPy")
    args = parser.parse_args()
    try:
        result = audit(args.repo, args.require_analysis)
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as exc:
        print("Audit failed: " + str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
