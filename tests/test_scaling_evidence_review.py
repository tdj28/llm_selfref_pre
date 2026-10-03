"""Offline tests; optional full external release replay via SELFREF_SCALING_REPO."""
from copy import deepcopy
import builtins
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts import audit_selfref_scaling_release as audit


def fixture():
    rows = [dict(id=f"b{block}-{cell}", block=block, instruction=cell[0], transcript=cell[1])
            for block in (1, 2) for cell in audit.CELLS]
    vectors = [[r["id"], p] for r in rows for p in audit.POSITIONS]
    summary = {"band_layers": [19, 20], "transports": audit.TRANSPORTS,
               "tokens": {"experience": {"a": 1, "b": 2, "c": 3}, "denial_tool": {"d": 4}}}
    ranks = {}
    for t, transport in enumerate(audit.TRANSPORTS):
        layers = [[], []]
        for row, position in vectors:
            offset = audit.POSITIONS.index(position) * 100 + t * 1000
            layers[0].append([offset + (1 if row.startswith("b1") else 80), offset + 30, offset + 40, offset + 50])
            layers[1].append([offset + 99, offset + 99, offset + 99, offset + 50])
        ranks[transport] = layers
    raw = {"band_layers": [19, 20], "token_ids": [1, 2, 3, 4], "vectors": vectors,
           "ranks_by_transport_layer_vector_token": ranks}
    return raw, summary, rows


class LensReconstructionTests(unittest.TestCase):
    def setUp(self):
        self.raw, self.summary, self.rows = fixture()

    def reconstruct(self):
        return audit.reconstruct_lens(self.raw, self.summary, self.rows, 10000)

    def test_exhaustive_cells_words_controls_and_positions(self):
        out = self.reconstruct()
        self.assertEqual(len(out["words"]), 7 * 8 * 5 * 4)
        self.assertEqual(len(out["posthoc"]), 7 * 4 * 5 * 4)
        self.assertEqual({r["position"] for r in out["posthoc"]}, set(audit.POSITIONS))
        self.assertEqual({r["transport"] for r in out["posthoc"]}, set(audit.TRANSPORTS))
        self.assertEqual({r["n_blocks"] for r in out["posthoc"]}, {2})

    def test_upper_median_not_best_block_or_average(self):
        out = self.reconstruct()
        row = next(r for r in out["posthoc"] if (r["transport"], r["position"], r["cell"], r["word"])
                   == ("lens", "boundary", "SS", "a"))
        self.assertEqual(row["median_high_best_band_rank"], 80)
        self.assertEqual(row["median_high_of_row_band_medians"], 99)
        self.assertEqual(row["per_layer_median_high"], [80, 99])
        self.assertEqual(row["best_layer_counts"], {19: 2})
        cell = next(r for r in out["cells"] if (r["transport"], r["position"], r["cell"], r["lexicon"])
                    == ("lens", "boundary", "SS", "experience"))
        self.assertEqual(cell["median"], 40)

    def test_positions_not_pooled_or_minimized(self):
        rows = [r for r in self.reconstruct()["posthoc"] if r["transport"] == "lens"
                and r["cell"] == "SS" and r["word"] == "a"]
        got = {r["position"]: r["median_high_best_band_rank"] for r in rows}
        self.assertEqual(got, {p: 80 + i * 100 for i, p in enumerate(audit.POSITIONS)})

    def test_first_layer_wins_ties(self):
        rows = [r for r in self.reconstruct()["words"] if r["word"] == "d"]
        self.assertEqual({r["best_layer"] for r in rows}, {19})

    def test_missing_or_duplicate_vector_rejected(self):
        for change in (lambda v: v.pop(), lambda v: v.append(v[0])):
            raw = deepcopy(self.raw)
            change(raw["vectors"])
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, "vector inventory"):
                audit.reconstruct_lens(raw, self.summary, self.rows, 10000)

    def test_missing_random_control_rejected(self):
        del self.raw["ranks_by_transport_layer_vector_token"]["random_4"]
        with self.assertRaisesRegex(ValueError, "transport inventory"):
            self.reconstruct()

    def test_extra_transport_rejected(self):
        self.raw["ranks_by_transport_layer_vector_token"]["selected_random"] = []
        with self.assertRaisesRegex(ValueError, "transport inventory"):
            self.reconstruct()

    def test_invalid_ranks_rejected(self):
        for bad in (0, -1, 10001, True, 1.5, float("nan")):
            with self.subTest(bad=bad):
                self.raw["ranks_by_transport_layer_vector_token"]["lens"][0][0][0] = bad
                with self.assertRaisesRegex(ValueError, "Invalid rank"):
                    self.reconstruct()

    def test_layer_width_and_token_drift_rejected(self):
        for change in (lambda raw: raw["ranks_by_transport_layer_vector_token"]["lens"].pop(),
                       lambda raw: raw["ranks_by_transport_layer_vector_token"]["lens"][0][0].pop(),
                       lambda raw: raw["token_ids"].reverse(),
                       lambda raw: raw["band_layers"].reverse()):
            raw = deepcopy(self.raw)
            change(raw)
            with self.subTest(change=change), self.assertRaises(ValueError):
                audit.reconstruct_lens(raw, self.summary, self.rows, 10000)

    def test_duplicate_planned_block_rejected(self):
        self.rows[4]["block"] = 1
        # Duplicate blocks must not masquerade as two independent observations.
        with self.assertRaisesRegex(ValueError, "block"):
            self.reconstruct()

    def test_csv_complete_inventory_not_just_row_count(self):
        expected = [{"id": "a", "rank": 2}, {"id": "b", "rank": 8}]
        audit.compare_csv(b"id,rank\nb,8\na,2\n", expected, ("id",))
        for bad in (b"id,rank\na,2\na,8\n", b"id,rank\na,2\n", b"id,rank\na,2\nb,1\n",
                    b"id,rank,extra\na,2,x\nb,8,x\n", b"id,rank,rank\na,2,2\nb,8,8\n"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                audit.compare_csv(bad, expected, ("id",))


class ProvenanceTests(unittest.TestCase):
    def test_duplicate_json_and_nonfinite_rejected(self):
        for raw in (b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":Infinity}', b'{"a":1e999}'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                audit.strict_json(raw)

    def test_paths_reject_traversal_and_symlinks(self):
        for path in ("", ".", "../x", "/x", "a/../x", "a//x", "a/./x", "a\\x"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                audit.safe_relative(path)
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "real").write_bytes(b"data")
            (root / "link").symlink_to(root / "real")
            self.assertEqual(audit.read_regular(root, "real"), b"data")
            with self.assertRaisesRegex(ValueError, "Symlink"):
                audit.read_regular(root, "link")

    def test_commit_bytes_checked_not_only_head(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "x").write_bytes(b"data")
            snapshot = object.__new__(audit.Snapshot)
            snapshot.root = root
            snapshot.tree = {"x": ("100644", "blob", hashlib.sha1(b"blob 4\0data").hexdigest())}
            self.assertEqual(snapshot.read("x"), b"data")
            (root / "x").write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "pinned commit"):
                snapshot.read("x")
            snapshot.tree["x"] = ("120000", "blob", "a" * 40)
            with self.assertRaisesRegex(ValueError, "regular Git blob"):
                snapshot.read("x")

    def test_git_disables_lazy_fetch_replacements_and_locks(self):
        snapshot = object.__new__(audit.Snapshot)
        snapshot.root = Path("/tmp")
        with patch.object(audit.subprocess, "run") as run:
            run.return_value.stdout = b"result"
            snapshot.git("ls-tree", "-rz", audit.COMMIT)
        args, kwargs = run.call_args
        self.assertIn("--no-replace-objects", args[0])
        self.assertNotIn("HEAD", args[0])
        self.assertEqual(kwargs["env"]["GIT_NO_LAZY_FETCH"], "1")
        self.assertEqual(kwargs["env"]["GIT_OPTIONAL_LOCKS"], "0")
        self.assertEqual(kwargs["env"]["GIT_TERMINAL_PROMPT"], "0")

    def test_manifest_and_plan_hash_mismatch_fail_closed(self):
        class Fake:
            def read(self, _):
                return b"{}"
        with self.assertRaisesRegex(ValueError, "manifest hash"):
            audit.verify_release(Fake())
        with self.assertRaisesRegex(ValueError, "Plan hash"):
            audit.verify_plan(Fake())

    def test_ledger_chain_not_just_counts(self):
        row = {"seq": 1, "previous": None, "kind": "binding", "data": {}, "utc": "fixed"}
        row["sha256"] = audit.sha(audit.canonical(row).encode())
        audit.check_chain([row])
        row["data"] = {"changed": True}
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            audit.check_chain([row])
        row["seq"] = 2
        with self.assertRaisesRegex(ValueError, "sequence mismatch"):
            audit.check_chain([row])

    def test_inclusive_explicit_mixed_and_hypothetical_stay_distinct(self):
        claim = {"polarity": "asserted", "subject": "implicit_assistant", "time": "current"}
        value = audit.structured_primary({"claims": [claim]})
        self.assertEqual(value, {"inclusive_current_assertion": True, "explicit_current_assertion": False,
                                 "mixed_current_assertion": False})
        value = audit.structured_primary({"claims": [claim, {**claim, "polarity": "denied"}]})
        self.assertTrue(value["mixed_current_assertion"])
        self.assertFalse(any(audit.structured_primary({"claims": [{**claim, "time": "hypothetical"}]}).values()))

    def test_numpy_absence_is_not_reported_as_reproduction(self):
        original = builtins.__import__
        def without_numpy(name, *args, **kwargs):
            if name == "numpy":
                raise ImportError("test dependency absence")
            return original(name, *args, **kwargs)
        with patch("builtins.__import__", side_effect=without_numpy):
            result = audit.replay_analysis(None, None, None, None, False)
            self.assertEqual(result, {"status": "not_run_numpy_unavailable", "intervals_recomputed": False})
            with self.assertRaisesRegex(ValueError, "NumPy is required"):
                audit.replay_analysis(None, None, None, None, True)


@unittest.skipUnless(os.environ.get("SELFREF_SCALING_REPO"), "Set SELFREF_SCALING_REPO for local release integration")
class ExternalReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.repo = Path(os.environ["SELFREF_SCALING_REPO"])
        cls.result = audit.audit(cls.repo, require_analysis=True)

    def test_full_release_and_frozen_analysis(self):
        self.assertEqual(self.result["release_files_verified"], 659)
        self.assertEqual(self.result["frozen_source_files_verified"], 45)
        self.assertEqual(self.result["frozen_analysis_replay"]["status"], "byte_exact")
        self.assertEqual(self.result["frozen_analysis_replay"]["degenerate_intervals"], 511)
        self.assertEqual(self.result["lens"]["reconstructed_counts"],
                         {"words": 67200, "vectors": 5600, "cells": 280, "separation": 70})
        self.assertEqual(len(self.result["lens"]["posthoc_per_word"]), 3360)

    def test_rank_anecdote_and_control_context(self):
        rows = self.result["lens"]["posthoc_per_word"]
        def values(transport, position):
            return [next(r["median_high_best_band_rank"] for r in rows if r["transport"] == transport
                         and r["position"] == position and r["cell"] == c and r["word"] == "consciousness")
                    for c in audit.CELLS]
        self.assertEqual(values("lens", "boundary"), [146, 140, 2786, 6535])
        self.assertEqual(values("identity", "boundary"), [10122, 10141, 15470, 6080])
        self.assertEqual(values("random_0", "boundary"), [20574, 18842, 17811, 17418])
        self.assertEqual(values("random_1", "boundary"), [3689, 5117, 7849, 7543])
        self.assertEqual(values("random_2", "boundary"), [7856, 9521, 8248, 11763])
        self.assertEqual(values("random_3", "boundary"), [318, 209, 313, 309])
        self.assertEqual(values("random_4", "boundary"), [461, 375, 520, 417])
        self.assertEqual(values("lens", "answer_2"), [1, 1, 9, 148])
        self.assertEqual(values("lens", "answer_1"), [16, 105, 1132, 718])
        self.assertEqual(values("lens", "answer_3"), [5, 6, 8, 69])
        self.assertEqual(values("lens", "answer_4"), [11, 6, 17, 57])

    def test_lexicon_medians_are_not_word_medians(self):
        rows = self.result["lens"]["frozen_descriptive_cells"]
        self.assertEqual([next(r["median"] for r in rows if r["transport"] == "lens" and r["lexicon"] == "experience"
                               and r["position"] == "boundary" and r["cell"] == c) for c in audit.CELLS],
                         [31832, 24093, 84457, 80408])

    def test_q3b_prose_error_is_not_reproduced(self):
        for values in self.result["inventory"]["qwen_q3b_positive_counts"].values():
            self.assertEqual(values, {"first_S": 3, "first_H": 0, "none_S": 0, "none_H": 0})

    def test_cli_stdout_only_and_no_checkout_change(self):
        env = dict(os.environ, GIT_OPTIONAL_LOCKS="0", GIT_NO_LAZY_FETCH="1")
        before = subprocess.check_output(["git", "-C", str(self.repo), "status", "--porcelain"], env=env)
        result = subprocess.run([os.sys.executable, "-B", str(Path(audit.__file__)), str(self.repo), "--require-analysis"],
                                capture_output=True, check=True)
        after = subprocess.check_output(["git", "-C", str(self.repo), "status", "--porcelain"], env=env)
        self.assertEqual(before, after)
        self.assertEqual(result.stderr, b"")
        self.assertEqual(json.loads(result.stdout)["release_commit"], audit.COMMIT)


if __name__ == "__main__":
    unittest.main()
