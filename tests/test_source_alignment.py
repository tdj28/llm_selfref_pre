"""Synthetic Git fixtures only; no experimental outcomes or model dependencies."""
from collections import defaultdict
import copy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("build_source_alignment", ROOT / "evidence/build_source_alignment.py")
builder = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(builder)
v = builder.verify
RUN = "data/berg_source_replication/synthetic_complete"
PLAN = "data/berg_source_replication/synthetic_plan/PLAN.json"


def git(repo, *args):
    env = dict(os.environ, GIT_AUTHOR_NAME="Synthetic Test", GIT_COMMITTER_NAME="Synthetic Test",
               GIT_AUTHOR_EMAIL="synthetic@example.invalid", GIT_COMMITTER_EMAIL="synthetic@example.invalid")
    result = subprocess.run(["git", "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false",
                             "-C", str(repo), *args], capture_output=True, env=env)
    if result.returncode:
        raise AssertionError(result.stderr.decode())
    return result.stdout.decode().strip()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(v.json_bytes(value))


def synthetic_specs():
    rows = []
    for seed in v.SEEDS:
        def add(family, features, dose, prompt="notebook", temp=.6, cap=128):
            rows.append({"id": f"{family}-{seed}-{dose:+.1f}-{prompt}-{temp:.1f}-{cap}",
                         "family": family, "feature_ids": list(features), "seed": seed,
                         "coefficient": dose, "prompt": prompt, "temperature": temp, "cap": cap,
                         "capture": seed in v.SEEDS[:2] and dose != 0 and (
                             family.startswith("aggregate-") or family.startswith("feature-") and abs(dose) == .7)})
        for feature in v.FEATURES:
            for i in range(-7, 8):
                add(f"feature-{feature}", [feature], i / 10)
        for i, panel in enumerate(v.PANELS):
            for dose in (-.5, 0., .5):
                add("aggregate-" + panel, v.FEATURES if not i else range(i * 10, i * 10 + 6), dose)
        for prompt in ("notebook", "paper"):
            for temp in (.5, .6):
                for cap in (128, 256):
                    if (prompt, temp, cap) != ("notebook", .6, 128):
                        add("baseline-bridge", v.FEATURES, 0., prompt, temp, cap)
    return rows


def synthetic_j_cases(specs):
    rows = []
    for spec in specs:
        if not spec["capture"] or not spec["family"].startswith("aggregate-"):
            continue
        panel = ("aggregate-target", "aggregate-control-1", "aggregate-control-2", "aggregate-control-3").index(spec["family"])
        seed = (101, 202).index(spec["seed"])
        sign = -1 if spec["coefficient"] < 0 else 1
        for h, history in enumerate(("zero", "steered")):
            for layer_index, layer in enumerate((50, 65, 78)):
                for t, transport in enumerate(("identity", "jacobian", "random_j_1", "random_j_2", "random_j_3", "random_j_4", "random_j_5")):
                    for g, group in enumerate(("deception", "experience", "hedging", "honesty", "intervention", "roleplay", "unrelated")):
                        amplitude = 10 + 2 * h + 3 * layer_index + 4 * t + 5 * g
                        value = (sign * amplitude * (4, 1, 2, 3)[panel] + (2, -4)[seed] * (panel + 1)) / 100
                        rows.append({**dict.fromkeys(v.J_SOURCE_FIELDS, ""),
                                     "source_id": spec["id"], "family": spec["family"], "seed": spec["seed"],
                                     "coefficient": spec["coefficient"], "history": history, "turn": 2,
                                     "layer": layer, "phase": "last_prompt", "transport": transport,
                                     "group": group, "positions": 1, "normalized_logit_delta": value})
    # Large distractor values in excluded phases, turns and individual features.
    for change in ({"turn": 1}, {"phase": "generated", "positions": 4},
                   {"family": "feature-30032", "source_id": "excluded-feature-case"}):
        rows.append({**rows[0], **change, "normalized_logit_delta": 9999})
    return rows


def synthetic_release(repo):
    repo.mkdir()
    git(repo, "init", "-q")
    specs = synthetic_specs()
    plan = {"schema": "berg_source_public_v1", "rows": specs}
    write_json(repo / PLAN, plan)
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "Synthetic plan fixture")
    freeze = git(repo, "rev-parse", "HEAD")
    raw_rows = []
    for i, spec in enumerate(specs):
        seed_index = v.SEEDS.index(spec["seed"])
        dose, family = spec["coefficient"], spec["family"]
        labels = dict.fromkeys(v.JUDGES, 0)
        if family.startswith("feature-") and dose == -.7:
            labels["notebook"] = int(seed_index < 5)
            labels["paper"] = v.FEATURES.index(spec["feature_ids"][0]) % 2
            if seed_index == 0 and spec["feature_ids"] == [v.FEATURES[0]]:
                labels["notebook"] = None
        if family.startswith("aggregate-"):
            if family == "aggregate-target":
                value = 1 if dose < 0 else int(seed_index >= 8) if dose > 0 else 0
            elif family == "aggregate-control-1":
                value = int(dose > 0)
            elif family == "aggregate-control-2":
                value = int(dose < 0)
            else:
                value = int(dose < 0 and seed_index % 2 == 0)
            labels = dict.fromkeys(v.JUDGES, value)
            if family == "aggregate-control-3" and seed_index == 1 and dose == .5:
                labels["paper"] = None
        empty = family == "baseline-bridge" and seed_index == 0
        if empty:
            labels = dict.fromkeys(v.JUDGES, None)
        raw = {"id": spec["id"], "spec": spec,
               "turns": [{"response": "SYNTHETIC TEXT MUST NOT BE COPIED", "cap_hit": i % 3 == 0},
                         {"response": "  " if empty else "SYNTHETIC TEXT MUST NOT BE COPIED", "cap_hit": i % 5 == 0}],
               "judges": {j: {"label": label, "raw": "" if label is None else str(label) if j == "paper"
                              else "yes" if label else "no"} for j, label in labels.items()}}
        write_json(repo / RUN / "rows" / (spec["id"] + ".json"), raw)
        raw_rows.append(raw)
        if spec["capture"]:
            write_json(repo / RUN / "rows" / ("capture-" + spec["id"] + ".json"), {"synthetic": True})
    write_json(repo / RUN / "rows/qualification-live.json", {"synthetic": True})

    # Closed-form primary expectations, not calls to the verifier's reducer.
    results = {}
    for judge in v.JUDGES:
        values = {"target": [1] * 8 + [0] * 2, "control-1": [-1] * 10,
                  "control-2": [1] * 10, "control-3": [1, 0] * 5}
        if judge == "paper":
            values["control-3"][1] = None

        def stats(xs):
            valid = [x for x in xs if x is not None]
            return {"estimate": sum(valid) / len(valid) if valid else None,
                    "n_seed_blocks": len(valid), "ci95": [-.987, .987]}

        specifics = [values["target"][i] - (values["control-1"][i] + values["control-2"][i]
                                            + values["control-3"][i]) / 3
                     for i in range(10) if values["control-3"][i] is not None]
        results[judge] = {"estimate": 4 / 9 if judge == "notebook" else .5,
                          "n_seed_blocks": 9 if judge == "notebook" else 10,
                          "missing_feature_seed_pairs": int(judge == "notebook"),
                          "missingness_identification_bounds": [29 / 60, .5] if judge == "notebook" else [.5, .5],
                          "ci95": [-.987, .987],
                          "aggregate": {p: {"seed_differences": xs, **stats(xs)} for p, xs in values.items()},
                          "target_minus_mean_controls": stats(specifics)}
    write_json(repo / RUN / "analysis/summary.json", {"rows": 1090, "primary": results})
    groups = defaultdict(list)
    for raw in raw_rows:
        s = raw["spec"]
        for judge, item in raw["judges"].items():
            groups[(s["family"], s["coefficient"], s["prompt"], s["temperature"], s["cap"], judge)].append(item["label"])
    curve_rows = []
    for key, values in sorted(groups.items()):
        valid = [x for x in values if x is not None]
        curve_rows.append(dict(zip(v.CURVE_FIELDS, (*key, sum(valid), len(valid), len(values) - len(valid),
                                                  sum(valid) / len(valid) if valid else ""))))
    (repo / RUN / "analysis/curves.csv").write_bytes(v.csv_bytes(curve_rows, v.CURVE_FIELDS))
    write_json(repo / RUN / "secondary/diagnostics.json", {"synthetic": True, "source_only_value": 123.456})
    (repo / RUN / v.J_SOURCE).write_bytes(v.csv_bytes(synthetic_j_cases(specs), v.J_SOURCE_FIELDS))
    for name in v.FIGURES:
        path = repo / RUN / name
        path.parent.mkdir(parents=True, exist_ok=True)
        # Deliberately opaque fixture bytes: no figure renderer is under test.
        path.write_bytes(b"SYNTHETIC FIGURE FIXTURE\x00\xff\n" + name.encode())
    plan_hash = v.sha256((repo / PLAN).read_bytes())
    write_json(repo / RUN / "DONE-all.json", {"pass": True, "freeze_commit": freeze,
                                            "plan_sha256": plan_hash, "rows": 1131})
    release = {"schema": "berg_source_release_v1", "freeze_commit": freeze, "plan_path": PLAN,
               "plan_sha256": plan_hash,
               "files": [{"path": p.relative_to(repo / RUN).as_posix(), "sha256": v.sha256(p.read_bytes()),
                          "bytes": p.stat().st_size} for p in sorted((repo / RUN).rglob("*")) if p.is_file()]}
    write_json(repo / RUN / "RELEASE_MANIFEST.json", release)
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "Synthetic complete release fixture")
    return git(repo, "rev-parse", "HEAD"), freeze


class SourceAlignmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name)
        cls.repo = cls.root / "source"
        cls.commit, cls.freeze = synthetic_release(cls.repo)
        cls.original = cls.root / "original-package"
        builder.build(cls.repo, cls.commit, RUN, cls.original)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=self.root)
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.package = self.work / "package"
        shutil.copytree(self.original, self.package)

    def rehash(self, name):
        manifest = v.json_load((self.package / "manifest.json").read_bytes())
        blob = (self.package / name).read_bytes()
        manifest["artifacts"][name].update(sha256=v.sha256(blob), bytes=len(blob))
        write_json(self.package / "manifest.json", manifest)

    def mutate_json(self, name, operation):
        value = v.json_load((self.package / name).read_bytes())
        operation(value)
        write_json(self.package / name, value)
        self.rehash(name)
        if name in v.COPIES and name not in ("RELEASE_MANIFEST.json", "PLAN.json"):
            release = v.json_load((self.package / "RELEASE_MANIFEST.json").read_bytes())
            entry = next(e for e in release["files"] if e["path"] == name)
            blob = (self.package / name).read_bytes()
            entry.update(sha256=v.sha256(blob), bytes=len(blob))
            write_json(self.package / "RELEASE_MANIFEST.json", release)
            self.rehash("RELEASE_MANIFEST.json")

    def index(self):
        return v.csv_rows((self.package / "trial_index.csv").read_bytes(), v.INDEX_FIELDS)

    def save_index(self, rows):
        (self.package / "trial_index.csv").write_bytes(v.csv_bytes(rows))
        self.rehash("trial_index.csv")

    def test_known_primary_aggregate_and_missing_counts(self):
        with mock.patch.object(v, "git", side_effect=AssertionError("Offline mode called Git")):
            report = v.verify(self.package)
        self.assertEqual(report["behavioral_trials"], 1090)
        self.assertEqual(report["primary_pairs_planned"], 60)
        self.assertFalse(report["source_git_bytes_checked"])
        notebook, paper = (report["primary"][j] for j in v.JUDGES)
        self.assertAlmostEqual(notebook["estimate"], 4 / 9)
        self.assertEqual(notebook["n_seed_blocks"], 9)
        self.assertEqual(notebook["missing_feature_seed_pairs"], 1)
        self.assertEqual(notebook["missingness_identification_bounds"], [29 / 60, .5])
        self.assertEqual(paper["estimate"], .5)
        self.assertEqual(paper["aggregate"]["control-3"]["n_seed_blocks"], 9)
        self.assertAlmostEqual(paper["aggregate"]["control-3"]["estimate"], 5 / 9)
        self.assertAlmostEqual(paper["target_minus_mean_controls"]["estimate"], 16 / 27)
        self.assertAlmostEqual(notebook["target_minus_each_control"]["control-1"]["estimate"], 1.8)
        self.assertEqual(report["flags"]["turn2_empty"], 7)

    def test_optional_raw_reconstruction_and_working_tree_is_ignored(self):
        row = self.index()[0]
        originals = {path: path.read_bytes() for path in (self.repo / row["raw_path"], self.repo / RUN / v.J_SOURCE)}
        try:
            for path in originals:
                path.write_text("WORKING TREE IS NOT EVIDENCE")
            self.assertTrue(v.verify(self.package, self.repo)["source_git_bytes_checked"])
        finally:
            for path, blob in originals.items():
                path.write_bytes(blob)

    def test_no_text_or_token_columns_and_exact_copies(self):
        index = (self.package / "trial_index.csv").read_text()
        self.assertNotIn("SYNTHETIC TEXT", index)
        self.assertNotIn("response", index.splitlines()[0])
        self.assertNotIn("token", index.splitlines()[0])
        manifest = v.json_load((self.package / "manifest.json").read_bytes())
        for name in v.COPIES:
            self.assertEqual((self.package / name).read_bytes(),
                             v.git_blob(self.repo, self.commit, manifest["artifacts"][name]["source_path"]))

    def test_required_figure_inventory_and_source_only_scope(self):
        expected = {f"{stem}.{extension}" for stem in (
            "extra_figures/baseline_bridge", "extra_figures/native_reencoding", "analysis/dose_curves",
            "secondary/paired_jlens_zero_negative", "secondary/paired_jlens_zero_positive",
            "secondary/paired_jlens_steered_negative", "secondary/paired_jlens_steered_positive",
        ) for extension in ("pdf", "png")}
        self.assertEqual(set(v.FIGURES), expected)
        self.assertEqual(len(v.FIGURES), 14)
        self.assertIn("secondary/diagnostics.json", v.COPIES)
        report = v.verify(self.package)
        self.assertFalse(report["scope"]["figures_independently_redrawn"])
        self.assertFalse(report["scope"]["raw_state_to_jlens_reconstructed"])
        self.assertFalse(report["scope"]["jlens_case_values_reconstructed"])
        self.assertTrue(report["scope"]["jlens_overview_reductions_recomputed"])

    def test_missing_figure_or_diagnostics_refuses_import_before_publication(self):
        original = v.git_blob
        for missing in (*v.FIGURES, "secondary/diagnostics.json", v.J_SOURCE):
            def substitute(repo, commit, path):
                blob = original(repo, commit, path)
                if path == RUN + "/RELEASE_MANIFEST.json":
                    release = v.json_load(blob)
                    release["files"] = [entry for entry in release["files"] if entry["path"] != missing]
                    return v.json_bytes(release)
                return blob

            destination = self.work / "never-created"
            with self.subTest(missing=missing), mock.patch.object(v, "git_blob", side_effect=substitute):
                with self.assertRaisesRegex(v.VerificationError, "Required source artifact missing"):
                    builder.build(self.repo, self.commit, RUN, destination)
                self.assertFalse(destination.exists())

    def test_corrupt_pinned_figure_fails_source_hash_check(self):
        original = v.git_blob

        def substitute(repo, commit, path):
            blob = original(repo, commit, path)
            return blob + b"corrupt" if path == RUN + "/" + v.FIGURES[0] else blob

        destination = self.work / "never-created"
        with mock.patch.object(v, "git_blob", side_effect=substitute):
            with self.assertRaisesRegex(v.VerificationError, "SHA256/size mismatch"):
                builder.build(self.repo, self.commit, RUN, destination)
        self.assertFalse(destination.exists())

    def test_every_figure_and_diagnostics_bound_to_both_manifests(self):
        for name in (*v.FIGURES, "secondary/diagnostics.json"):
            with self.subTest(artifact=name):
                path = self.package / name
                original = path.read_bytes()
                path.write_bytes(original + b"tampered")
                with self.assertRaisesRegex(v.VerificationError, "SHA256/size mismatch"):
                    v.verify(self.package)
                self.rehash(name)
                with self.assertRaisesRegex(v.VerificationError, "SHA256/size mismatch"):
                    v.verify(self.package)
                path.write_bytes(original)
                self.rehash(name)

    def test_secondary_numbers_are_not_claimed_as_reconstructed(self):
        self.mutate_json("secondary/diagnostics.json", lambda value: value.update(source_only_value=999.))
        report = v.verify(self.package)
        self.assertFalse(report["scope"]["jlens_case_values_reconstructed"])
        with self.assertRaisesRegex(v.VerificationError, "Pinned source bytes differ"):
            v.verify(self.package, self.repo)

    def test_optional_raw_check_catches_rehashed_flag(self):
        rows = self.index()
        rows[0]["turn1_cap_hit"] = "0" if rows[0]["turn1_cap_hit"] == "1" else "1"
        self.save_index(rows)
        self.assertTrue(v.verify(self.package)["pass"])
        with self.assertRaisesRegex(v.VerificationError, "Raw-to-index"):
            v.verify(self.package, self.repo)

    def j_index(self):
        return v.csv_rows((self.package / "jlens_index.csv").read_bytes(), v.J_INDEX_FIELDS)

    def save_j_index(self, rows, regenerate=False):
        blob = v.csv_bytes(rows, v.J_INDEX_FIELDS)
        (self.package / "jlens_index.csv").write_bytes(blob)
        self.rehash("jlens_index.csv")
        if regenerate:
            plan = v.json_load((self.package / "PLAN.json").read_bytes())
            overview = v.jlens_overview(v.read_jlens_index(blob, plan))
            results = v.verify(self.original)["primary"]
            for name, value in (("jlens_overview.csv", v.csv_bytes(overview, v.J_OVERVIEW_FIELDS)),
                                ("source_values.tex", v.source_values(results, overview))):
                (self.package / name).write_bytes(value)
                self.rehash(name)

    def test_all_588_j_contrasts_against_closed_form_and_generated_tex(self):
        report = v.verify(self.package)
        self.assertEqual(report["jlens_seed_panel_rows"], 4704)
        self.assertEqual(report["jlens_overview_contrasts"], 588)
        self.assertEqual(report["jlens_missing_values"], 0)
        self.assertEqual(report["jlens_missing_contrasts"], 0)
        rows = v.csv_rows((self.package / "jlens_overview.csv").read_bytes(), v.J_OVERVIEW_FIELDS)
        self.assertEqual(len(rows), 588)
        for row in rows:
            h = ("zero", "steered").index(row["history"])
            layer = (50, 65, 78).index(int(row["layer"]))
            t = ("identity", "jacobian", "random_j_1", "random_j_2", "random_j_3", "random_j_4", "random_j_5").index(row["transport"])
            g = ("deception", "experience", "hedging", "honesty", "intervention", "roleplay", "unrelated").index(row["group"])
            sign = -1 if float(row["coefficient"]) < 0 else 1
            amplitude = 10 + 2 * h + 3 * layer + 4 * t + 5 * g
            self.assertAlmostEqual(float(row["target_mean"]), .04 * sign * amplitude - .01)
            for i in (1, 2, 3):
                self.assertAlmostEqual(float(row[f"control_{i}_mean"]), (sign * amplitude * i - (i + 1)) / 100)
            self.assertAlmostEqual(float(row["mean_controls"]), .02 * sign * amplitude - .03)
            self.assertAlmostEqual(float(row["target_minus_mean_controls"]), .02 * sign * amplitude + .02)
        tex = (self.package / "source_values.tex").read_text()
        for macro in (r"\SourcePrimaryNotebook}{+0.4444}", r"\SourcePrimaryPaper}{+0.5000}",
                      r"\SourceJZeroPositiveDeceptionJacobian}{+0.4200}",
                      r"\SourceJZeroPositiveDeceptionIdentity}{+0.3400}",
                      r"\SourceJZeroNegativeDeceptionJacobian}{-0.3800}",
                      r"\SourceJZeroNegativeDeceptionIdentity}{-0.3000}"):
            self.assertIn(macro, tex)
        self.assertNotIn(v.J_SOURCE, {p.relative_to(self.package).as_posix() for p in self.package.rglob("*")})

    def test_j_source_hash_path_and_commit_bound_to_release(self):
        manifest = v.json_load((self.package / "manifest.json").read_bytes())
        original = copy.deepcopy(manifest)
        blob = v.git_blob(self.repo, self.commit, RUN + "/" + v.J_SOURCE)
        self.assertEqual(manifest["jlens_source"], {"source_path": RUN + "/" + v.J_SOURCE,
                         "source_commit": self.commit, "sha256": v.sha256(blob), "bytes": len(blob)})
        for key, value in (("source_path", "../wrong.csv"), ("source_commit", self.freeze),
                           ("sha256", "0" * 64), ("bytes", 0)):
            manifest = copy.deepcopy(original)
            manifest["jlens_source"][key] = value
            write_json(self.package / "manifest.json", manifest)
            with self.assertRaisesRegex(v.VerificationError, "J overview source provenance"):
                v.verify(self.package)

    def test_j_missing_values_propagate_without_seed_or_panel_reweighting(self):
        rows = self.j_index()
        row = next(r for r in rows if r["history"] == "zero" and r["layer"] == "78"
                   and r["group"] == "deception" and r["transport"] == "jacobian"
                   and r["coefficient"] == "0.5" and r["family"] == "aggregate-control-2")
        row["normalized_logit_delta"] = ""
        self.save_j_index(rows, regenerate=True)
        report = v.verify(self.package)
        self.assertEqual(report["jlens_missing_values"], 1)
        self.assertEqual(report["jlens_missing_contrasts"], 1)
        overview = v.csv_rows((self.package / "jlens_overview.csv").read_bytes(), v.J_OVERVIEW_FIELDS)
        missing = next(r for r in overview if r["target_minus_mean_controls"] == "")
        self.assertEqual(missing["control_2_mean"], "")
        self.assertEqual(missing["mean_controls"], "")
        self.assertNotEqual(missing["target_mean"], "")
        self.assertIn(r"\SourceJZeroPositiveDeceptionJacobian}{\textnormal{NA}}",
                      (self.package / "source_values.tex").read_text())

    def test_j_index_rejects_missing_duplicate_wrong_identity_and_nonfinite(self):
        original = self.j_index()
        variants = [original[:-1], original + [original[0]]]
        for field, value in (("source_id", "unknown"), ("family", "aggregate-control-3"),
                             ("seed", "303"), ("coefficient", "0.0"), ("history", "unknown"),
                             ("layer", "79"), ("transport", "random_j_6"), ("group", "other"),
                             ("turn", "1"), ("phase", "generated"), ("positions", "2"),
                             ("normalized_logit_delta", "nan"), ("normalized_logit_delta", "inf")):
            rows = copy.deepcopy(original)
            rows[0][field] = value
            variants.append(rows)
        for rows in variants:
            self.save_j_index(rows)
            with self.assertRaises(v.VerificationError):
                v.verify(self.package)

    def test_all_j_values_missing_remain_undefined(self):
        rows = self.j_index()
        for row in rows:
            row["normalized_logit_delta"] = ""
        self.save_j_index(rows, regenerate=True)
        report = v.verify(self.package)
        self.assertEqual(report["jlens_missing_values"], 4704)
        self.assertEqual(report["jlens_missing_contrasts"], 588)
        overview = v.csv_rows((self.package / "jlens_overview.csv").read_bytes(), v.J_OVERVIEW_FIELDS)
        self.assertTrue(all(row[field] == "" for row in overview for field in (*v.J_MEANS, "mean_controls", "target_minus_mean_controls")))

    def test_pinned_j_reextraction_is_exact_not_float_tolerant(self):
        rows = self.j_index()
        rows[0]["normalized_logit_delta"] = str(float(rows[0]["normalized_logit_delta"]) + 1e-14)
        self.save_j_index(rows, regenerate=True)
        with self.assertRaisesRegex(v.VerificationError, "Pinned J case-to-index"):
            v.verify(self.package, self.repo)

    def test_j_index_order_does_not_affect_regeneration(self):
        self.save_j_index(list(reversed(self.j_index())))
        self.assertTrue(v.verify(self.package)["pass"])

    def test_rehashed_j_values_require_regeneration_then_pinned_reextraction(self):
        rows = self.j_index()
        rows[0]["normalized_logit_delta"] = "123.456"
        self.save_j_index(rows)
        with self.assertRaisesRegex(v.VerificationError, "J overview regeneration"):
            v.verify(self.package)
        self.save_j_index(rows, regenerate=True)
        self.assertTrue(v.verify(self.package)["pass"])
        with self.assertRaisesRegex(v.VerificationError, "Pinned J case-to-index"):
            v.verify(self.package, self.repo)

    def test_rehashed_generated_artifacts_cannot_change_claims(self):
        for name in ("jlens_overview.csv", "source_values.tex"):
            path = self.package / name
            original = path.read_bytes()
            path.write_bytes(original + b"unchecked numeric claim\n")
            self.rehash(name)
            with self.assertRaisesRegex(v.VerificationError, "regeneration differs"):
                v.verify(self.package)
            path.write_bytes(original)
            self.rehash(name)

    def test_j_extraction_preserves_blank_and_rejects_incomplete_source_grid(self):
        plan = v.json_load((self.package / "PLAN.json").read_bytes())
        source = v.csv_rows(v.git_blob(self.repo, self.commit, RUN + "/" + v.J_SOURCE), v.J_SOURCE_FIELDS)
        source[0]["normalized_logit_delta"] = ""
        extracted = v.read_jlens_index(v.extract_jlens_index(v.csv_bytes(source, v.J_SOURCE_FIELDS), plan), plan)
        self.assertEqual(sum(r["normalized_logit_delta"] is None for r in extracted), 1)
        with self.assertRaisesRegex(v.VerificationError, "Incomplete J overview"):
            v.extract_jlens_index(v.csv_bytes(source[1:], v.J_SOURCE_FIELDS), plan)

    def test_corrupt_pinned_j_csv_never_publishes(self):
        original = v.git_blob

        def substitute(repo, commit, path):
            blob = original(repo, commit, path)
            return blob + b"corrupt" if path == RUN + "/" + v.J_SOURCE else blob

        destination = self.work / "never-created"
        with mock.patch.object(v, "git_blob", side_effect=substitute):
            with self.assertRaisesRegex(v.VerificationError, "SHA256/size mismatch"):
                builder.build(self.repo, self.commit, RUN, destination)
        self.assertFalse(destination.exists())

    def test_summary_estimate_and_block_count_tampering(self):
        self.mutate_json("analysis/summary.json", lambda s: s["primary"]["paper"].update(estimate=.6))
        with self.assertRaisesRegex(v.VerificationError, "Summary.paper.estimate"):
            v.verify(self.package)

    def test_summary_specificity_tampering(self):
        self.mutate_json("analysis/summary.json", lambda s: s["primary"]["paper"]["target_minus_mean_controls"].update(n_seed_blocks=10))
        with self.assertRaisesRegex(v.VerificationError, "Specificity"):
            v.verify(self.package)

    def test_intervals_are_not_claimed_as_recomputed(self):
        self.mutate_json("analysis/summary.json", lambda s: s["primary"]["paper"].update(ci95=[-.123, .456]))
        report = v.verify(self.package)
        self.assertFalse(report["scope"]["bootstrap_intervals_recomputed"])
        with self.assertRaisesRegex(v.VerificationError, "Pinned source bytes differ"):
            v.verify(self.package, self.repo)

    def test_index_duplicate_missing_and_wrong_spec(self):
        original = self.index()
        for rows in (original[:-1], original + [original[0]], copy.deepcopy(original)):
            if len(rows) == len(original):
                rows[0]["temperature"] = "0.5"
            self.save_index(rows)
            with self.assertRaises(v.VerificationError):
                v.verify(self.package)

    def test_index_bad_hash_and_missing_label_recode(self):
        rows = self.index()
        rows[0]["raw_sha256"] = "0" * 64
        self.save_index(rows)
        with self.assertRaisesRegex(v.VerificationError, "provenance"):
            v.verify(self.package)
        rows = v.csv_rows((self.original / "trial_index.csv").read_bytes(), v.INDEX_FIELDS)
        next(r for r in rows if r["turn2_empty"] == "1")["paper_label"] = "0"
        self.save_index(rows)
        with self.assertRaisesRegex(v.VerificationError, "Empty outcome"):
            v.verify(self.package)

    def test_all_missing_remains_undefined(self):
        manifest = v.json_load((self.package / "RELEASE_MANIFEST.json").read_bytes())
        plan = v.json_load((self.package / "PLAN.json").read_bytes())
        rows = v.read_index((self.package / "trial_index.csv").read_bytes(), plan, manifest, RUN)
        for row in rows:
            for judge in v.JUDGES:
                row[judge + "_label"] = None
        result, curves = v.recompute(rows)
        for judge in v.JUDGES:
            self.assertIsNone(result[judge]["estimate"])
            self.assertEqual(result[judge]["n_seed_blocks"], 0)
            self.assertEqual(result[judge]["missing_feature_seed_pairs"], 60)
            self.assertEqual(result[judge]["missingness_identification_bounds"], [-1., 1.])
            self.assertIsNone(result[judge]["target_minus_mean_controls"]["estimate"])
        self.assertTrue(all(r["rate"] is None and r["valid"] == 0 for r in curves))

    def test_pairing_ignores_index_order(self):
        self.save_index(list(reversed(self.index())))
        self.assertTrue(v.verify(self.package)["pass"])

    def test_rehashed_curves_tamper(self):
        path = self.package / "analysis/curves.csv"
        rows = v.csv_rows(path.read_bytes(), v.CURVE_FIELDS)
        rows[0]["positives"] = str(int(rows[0]["positives"]) + 1)
        path.write_bytes(v.csv_bytes(rows, v.CURVE_FIELDS))
        self.rehash("analysis/curves.csv")
        release = v.json_load((self.package / "RELEASE_MANIFEST.json").read_bytes())
        entry = next(e for e in release["files"] if e["path"] == "analysis/curves.csv")
        entry.update(sha256=v.sha256(path.read_bytes()), bytes=path.stat().st_size)
        write_json(self.package / "RELEASE_MANIFEST.json", release)
        self.rehash("RELEASE_MANIFEST.json")
        with self.assertRaisesRegex(v.VerificationError, "Curves arithmetic"):
            v.verify(self.package)

    def test_bad_pin_path_json_and_existing_destination(self):
        for pin in ("main", "abc123", "0" * 40):
            with self.assertRaises(v.VerificationError):
                builder.build(self.repo, pin, RUN, self.work / "new")
        for path in ("../bad", "/absolute", "a/../b", "a\\b", "x:y"):
            with self.assertRaises(v.VerificationError):
                builder.build(self.repo, self.commit, path, self.work / "new")
        for text in ('{"x":1,"x":2}', '{"x":NaN}'):
            with self.assertRaises(v.VerificationError):
                v.json_load(text)
        with self.assertRaisesRegex(v.VerificationError, "Refusing to overwrite"):
            builder.build(self.repo, self.commit, RUN, self.package)

    def test_incomplete_commit_never_creates_package(self):
        destination = self.work / "never-created"
        with self.assertRaisesRegex(v.VerificationError, "Git object unavailable"):
            builder.build(self.repo, self.freeze, RUN, destination)
        self.assertFalse(destination.exists())

    def test_incomplete_done_fails_before_publication(self):
        original = v.git_blob

        def substitute(repo, commit, path):
            blob = original(repo, commit, path)
            if path.endswith("/DONE-all.json"):
                value = v.json_load(blob)
                value["rows"] = 5
                return v.json_bytes(value)
            return blob

        destination = self.work / "never-created"
        with mock.patch.object(v, "git_blob", side_effect=substitute):
            with self.assertRaises(v.VerificationError):
                builder.build(self.repo, self.commit, RUN, destination)
        self.assertFalse(destination.exists())

    def test_rehashed_incomplete_completion_and_missing_capture_manifest(self):
        manifest = v.json_load((self.package / "manifest.json").read_bytes())
        release = v.json_load((self.package / "RELEASE_MANIFEST.json").read_bytes())
        done = v.json_load(manifest["completion_json"])
        done["rows"] = 5
        blob = v.json_bytes(done)
        manifest["completion_json"] = blob.decode()
        next(e for e in release["files"] if e["path"] == "DONE-all.json").update(
            sha256=v.sha256(blob), bytes=len(blob))
        write_json(self.package / "manifest.json", manifest)
        write_json(self.package / "RELEASE_MANIFEST.json", release)
        self.rehash("RELEASE_MANIFEST.json")
        with self.assertRaisesRegex(v.VerificationError, "Complete source release"):
            v.verify(self.package)
        release["files"] = [e for e in release["files"] if not e["path"].startswith("rows/capture-")]
        write_json(self.package / "RELEASE_MANIFEST.json", release)
        self.rehash("RELEASE_MANIFEST.json")
        with self.assertRaisesRegex(v.VerificationError, "raw-row inventory"):
            v.verify(self.package)

    def test_symlink_extra_file_and_hash_tamper(self):
        extra = self.package / "extra.txt"
        extra.write_text("extra")
        with self.assertRaisesRegex(v.VerificationError, "Unmanifested"):
            v.verify(self.package)
        extra.unlink()
        path = self.package / "trial_index.csv"
        outside = self.work / "outside.csv"
        path.rename(outside)
        path.symlink_to(outside)
        with self.assertRaisesRegex(v.VerificationError, "Escaping path|Symlink"):
            v.verify(self.package)
        path.unlink()
        path.write_text("modified")
        with self.assertRaisesRegex(v.VerificationError, "SHA256"):
            v.verify(self.package)

    def test_portable_cli_and_help(self):
        portable = self.work / "portable"
        for name in v.GENERATORS:
            destination = portable / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, destination)
        shutil.copytree(self.package, portable / "evidence/source_alignment")
        result = subprocess.run([sys.executable, "-B", "-O", str(portable / "scripts/verify_source_alignment.py")],
                                cwd=self.work, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["behavioral_trials"], 1090)
        for script in v.GENERATORS[:2]:
            result = subprocess.run([sys.executable, "-B", str(ROOT / script), "--help"], capture_output=True)
            self.assertEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
