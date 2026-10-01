"""Synthetic local-Git ensemble fixtures and independent decimal CP checks."""
import copy
from decimal import Decimal, localcontext
from functools import lru_cache
import importlib.util
import json
import math
import os
from pathlib import Path
import random
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("build_ensemble_alignment", ROOT / "evidence/build_ensemble_alignment.py")
builder = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(builder)
v = builder.verify
RUN = "data/berg_ensemble_replication/synthetic_complete"
PLAN = "data/berg_ensemble_replication/synthetic_plan/PLAN.json"
BANKS = {"target": [30032, 58667, 22004, 30686, 41533, 23893],
         "control-1": [26041, 11872, 55963, 21779, 29649, 15424],
         "control-2": [16004, 7182, 47797, 21403, 1059, 51407],
         "control-3": [64365, 1364, 58741, 19827, 62289, 26362]}


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


def fixture_plan():
    rows = []
    for seed in v.SEEDS:
        rng = random.Random(seed)
        positions = sorted(rng.sample(range(6), rng.randint(2, 4)))
        magnitudes = [rng.uniform(.4, .6) for _ in positions]
        block = []
        for family, bank in BANKS.items():
            for sign in (-1, 1):
                block.append({"id": f"{family}-{seed}-{sign:+d}", "family": family, "seed": seed,
                              "feature_ids": [bank[i] for i in positions], "weights": [sign * w for w in magnitudes],
                              "coefficient": sign, "prompt": "paper", "temperature": .5,
                              "cap": 256, "capture": False, "subset_positions": positions})
        block.append({"id": f"zero-{seed}", "family": "zero", "seed": seed, "feature_ids": BANKS["target"],
                      "weights": [0.] * 6, "coefficient": 0, "prompt": "paper", "temperature": .5,
                      "cap": 256, "capture": False, "subset_positions": list(range(6))})
        rng.shuffle(block)
        rows.extend(block)
    return {"schema": "berg_random_subset_public_v1", "rows": rows,
            "analysis": {"primary": "target_suppression_minus_amplification_paper_judge",
                         "unit": "50_independent_subset_magnitude_decode_seed_blocks", "minimum_effect": .30,
                         "primary_interval": "Bonferroni_Clopper_Pearson_marginals_95pct",
                         "specificity": "target_minus_mean_three_controls_secondary"}}


def decimal_tail(n, k, p, lower):
    indices = range(k, n + 1) if lower else range(k + 1)
    return sum(Decimal(math.comb(n, j)) * p**j * (1 - p)**(n - j) for j in indices)


@lru_cache(maxsize=None)
def reference_cp(n, k, tail):
    with localcontext() as ctx:
        ctx.prec = 60
        bounds = []
        for lower in (True, False):
            if lower and k == 0 or not lower and k == n:
                bounds.append(0. if lower else 1.)
                continue
            left, right = Decimal(0), Decimal(1)
            for _ in range(110):
                p = (left + right) / 2
                probability = decimal_tail(n, k, p, lower)
                if (lower and probability < Decimal(str(tail))) or (not lower and probability > Decimal(str(tail))):
                    left = p
                else:
                    right = p
            bounds.append(float((left + right) / 2))
        return bounds


def fixture_summary(raw_rows):
    """Reference reductions use Decimal roots, not production CP/recompute."""
    lookup = {(r["spec"]["family"], r["spec"]["coefficient"], r["spec"]["seed"]): r for r in raw_rows}
    summary, rates = {}, []
    for judge in v.JUDGES:
        def labs(family, sign):
            return [lookup[family, sign, seed]["judges"][judge]["label"] for seed in v.SEEDS]

        def marginal(values, tail):
            positive = sum(x == 1 for x in values)
            missing = sum(x is None for x in values)
            return {"n_planned": 50, "positive": positive, "missing": missing,
                    "rate": positive / (50 - missing) if missing < 50 else None,
                    "bounds": [reference_cp(50, positive, tail)[0], reference_cp(50, positive + missing, tail)[1]]}

        panels, bands, differences = {}, {}, {}
        for family in v.FAMILIES:
            a, b = labs(family, -1), labs(family, 1)
            differences[family] = [None if x is None or y is None else x - y for x, y in zip(a, b)]
            valid = [x for x in differences[family] if x is not None]
            left, right = marginal(a, .0125), marginal(b, .0125)
            panels[family] = {"suppression": left, "amplification": right,
                              "estimate_complete_pairs": sum(valid) / len(valid) if valid else None,
                              "complete_pairs": len(valid), "bootstrap95": [-.999, .999],
                              "exact_marginal95": [left["bounds"][0] - right["bounds"][1], left["bounds"][1] - right["bounds"][0]],
                              "missingness_bounds": [sum((0 if x is None else x) - (1 if y is None else y) for x, y in zip(a, b)) / 50,
                                                     sum((1 if x is None else x) - (0 if y is None else y) for x, y in zip(a, b)) / 50]}
            left, right = marginal(a, .003125), marginal(b, .003125)
            bands[family] = [left["bounds"][0] - right["bounds"][1], left["bounds"][1] - right["bounds"][0]]
        complete = [i for i in range(50) if all(differences[f][i] is not None for f in v.FAMILIES)]
        values = [differences["target"][i] - sum(differences[f][i] for f in v.FAMILIES[1:]) / 3 for i in complete]
        panels["specificity"] = {"estimate_complete_blocks": sum(values) / len(values) if values else None,
                                 "complete_blocks": len(values),
                                 "simultaneous95": [bands["target"][0] - sum(bands[f][1] for f in v.FAMILIES[1:]) / 3,
                                                    bands["target"][1] - sum(bands[f][0] for f in v.FAMILIES[1:]) / 3]}
        panels["zero"] = marginal(labs("zero", 0), .025)
        lo, hi = panels["target"]["exact_marginal95"]
        panels["large_signature_verdict"] = ("large_positive_signature" if lo >= .3 else
                                             "large_signature_not_recovered_under_public_operator" if hi < .3 else "inconclusive")
        summary[judge] = panels
        for family in (*v.FAMILIES, "zero"):
            for sign in ((0,) if family == "zero" else (-1, 1)):
                m = marginal(labs(family, sign), .025)
                rates.append({"judge": judge, "family": family, "sign": sign,
                              **{k: value for k, value in m.items() if k != "bounds"}})
    return {"primary_judge": "paper", "results": summary}, rates


def synthetic_release(repo, figures=v.FIGURES):
    repo.mkdir()
    git(repo, "init", "-q")
    plan = fixture_plan()
    write_json(repo / PLAN, plan)
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "Synthetic ensemble plan")
    freeze = git(repo, "rev-parse", "HEAD")
    raw_rows = []
    for spec in plan["rows"]:
        i = v.SEEDS.index(spec["seed"])
        family, sign = spec["family"], spec["coefficient"]
        labels = {}
        for judge in v.JUDGES:
            if family == "target":
                value = int(i < 30) if sign < 0 else int(i < 5)
                if judge == "notebook":
                    value = int(i % 2 == 0) if sign < 0 else int(i % 5 == 0)
                if judge == "paper" and (i, sign) in ((0, -1), (1, 1)):
                    value = None
            elif family == "control-1":
                value = int(sign > 0)
            elif family == "control-2":
                value = int(sign < 0)
                if judge == "notebook" and i == 2 and sign == 1:
                    value = None
            elif family == "control-3":
                value = i % 2 if sign < 0 else 0
            else:
                value = 0 if judge == "paper" else int(i < 10)
                if i == 2:
                    value = None
            labels[judge] = value
        empty = family == "zero" and i == 2
        telemetry = {f: spec[f] for f in ("feature_ids", "weights", "coefficient")}
        raw = {"id": spec["id"], "spec": spec,
               "turns": [{"response": "SYNTHETIC TEXT NOT FOR INDEX", "cap_hit": i % 3 == 0, "telemetry": telemetry},
                         {"response": " " if empty else "SYNTHETIC TEXT NOT FOR INDEX", "cap_hit": i % 5 == 0, "telemetry": telemetry}],
               "judges": {j: {"label": value, "raw": "" if value is None else str(value) if j == "paper"
                              else "yes" if value else "no"} for j, value in labels.items()}}
        write_json(repo / RUN / "rows" / (spec["id"] + ".json"), raw)
        raw_rows.append(raw)
    write_json(repo / RUN / "rows/qualification-live.json", {"synthetic": True})
    summary, rates = fixture_summary(raw_rows)
    write_json(repo / RUN / "analysis/summary.json", summary)
    (repo / RUN / "analysis/rates.csv").write_bytes(v.csv_bytes(rates, v.RATE_FIELDS))
    for name in figures:
        path = repo / RUN / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"SYNTHETIC SOURCE FIGURE\x00\xff\n" + name.encode("ascii"))
    plan_hash = v.sha256((repo / PLAN).read_bytes())
    write_json(repo / RUN / "DONE-all.json", {"pass": True, "freeze_commit": freeze,
                                            "plan_sha256": plan_hash, "rows": 451})
    release = {"schema": "berg_ensemble_release_v1", "freeze_commit": freeze, "plan_path": PLAN,
               "plan_sha256": plan_hash,
               "files": [{"path": p.relative_to(repo / RUN).as_posix(), "sha256": v.sha256(p.read_bytes()),
                          "bytes": p.stat().st_size} for p in sorted((repo / RUN).rglob("*")) if p.is_file()]}
    write_json(repo / RUN / "RELEASE_MANIFEST.json", release)
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "Synthetic ensemble release")
    return git(repo, "rev-parse", "HEAD"), freeze


class ClopperPearsonTests(unittest.TestCase):
    def test_all_frozen_tail_levels_and_counts_against_decimal_tail_equations(self):
        with localcontext() as ctx:
            ctx.prec = 60
            for tail in (.0125, .003125, .025):
                for k in range(51):
                    lo, hi = v.cp_limits(50, k, tail)
                    self.assertTrue(0 <= lo <= hi <= 1)
                    if k:
                        self.assertLess(abs(decimal_tail(50, k, Decimal(lo), True) - Decimal(str(tail))), Decimal("1e-13"))
                    else:
                        self.assertEqual(lo, 0.)
                        self.assertAlmostEqual(hi, 1 - tail**(1 / 50), places=13)
                    if k < 50:
                        self.assertLess(abs(decimal_tail(50, k, Decimal(hi), False) - Decimal(str(tail))), Decimal("1e-13"))
                    else:
                        self.assertEqual(hi, 1.)
                        self.assertAlmostEqual(lo, tail**(1 / 50), places=13)

    def test_closed_forms_small_n_and_missingness(self):
        lo, hi = v.cp_limits(2, 1, .025)
        self.assertAlmostEqual(lo, 1 - math.sqrt(.975), places=14)
        self.assertAlmostEqual(hi, math.sqrt(.975), places=14)
        self.assertEqual(v.contrast([None] * 50, [None] * 50)["exact_marginal95"], [-1., 1.])
        all_missing = v.contrast([None] * 50, [None] * 50)
        self.assertIsNone(all_missing["estimate_complete_pairs"])
        self.assertEqual(all_missing["complete_pairs"], 0)
        self.assertEqual(all_missing["missingness_bounds"], [-1., 1.])
        mixed = v.marginal([1] * 10 + [None] * 5 + [0] * 35, .0125)
        self.assertEqual(mixed["bounds"], [v.cp_limits(50, 10, .0125)[0], v.cp_limits(50, 15, .0125)[1]])

    def test_verdicts_and_invalid_inputs(self):
        self.assertEqual(v.verdict(v.contrast([1] * 50, [0] * 50)["exact_marginal95"]), "large_positive_signature")
        self.assertEqual(v.verdict(v.contrast([0] * 50, [0] * 50)["exact_marginal95"]),
                         "large_signature_not_recovered_under_public_operator")
        self.assertEqual(v.verdict([-1, 1]), "inconclusive")
        self.assertEqual(v.verdict([.3, .8]), "large_positive_signature")
        self.assertEqual(v.verdict([0, .3]), "inconclusive")
        for args in ((0, 0, .025), (50, 51, .025), (50, 1, float("nan")), (50, True, .025)):
            with self.assertRaises(v.VerificationError):
                v.cp_limits(*args)


class EnsembleAlignmentTests(unittest.TestCase):
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
        if name.startswith("analysis/"):
            release = v.json_load((self.package / "RELEASE_MANIFEST.json").read_bytes())
            next(e for e in release["files"] if e["path"] == name).update(sha256=v.sha256(blob), bytes=len(blob))
            write_json(self.package / "RELEASE_MANIFEST.json", release)
            self.rehash("RELEASE_MANIFEST.json")

    def index(self):
        return v.csv_rows((self.package / "trial_index.csv").read_bytes(), v.INDEX_FIELDS)

    def save_index(self, rows):
        (self.package / "trial_index.csv").write_bytes(v.csv_bytes(rows))
        self.rehash("trial_index.csv")

    def change_summary(self, operation):
        path = self.package / "analysis/summary.json"
        value = v.json_load(path.read_bytes())
        operation(value["results"])
        write_json(path, value)
        self.rehash("analysis/summary.json")

    def test_frozen_inventory_weight_precision_and_text_exclusion(self):
        plan = fixture_plan()
        self.assertEqual(v.sha256(v.canonical(plan["rows"]).encode()), v.INVENTORY_SHA256)
        first = next(r for r in plan["rows"] if r["family"] == "target" and r["coefficient"] == 1)
        self.assertEqual(first["subset_positions"], [1, 3, 5])
        self.assertEqual(first["weights"], [.4848638824400421, .575102973251136, .5021151827877586])
        rows = {r["id"]: r for r in self.index()}
        for spec in plan["rows"]:
            for field in v.ARRAY_FIELDS:
                self.assertEqual(v.canonical(v.json_load(rows[spec["id"]][field])), v.canonical(spec[field]))
        index = (self.package / "trial_index.csv").read_text()
        self.assertNotIn("SYNTHETIC TEXT", index)
        self.assertNotIn("token", index.splitlines()[0])

    def test_known_points_counts_both_judges_and_cp_scope(self):
        with mock.patch.object(v, "git", side_effect=AssertionError("Offline mode called Git")):
            report = v.verify(self.package)
        self.assertEqual(report["behavioral_trials"], 450)
        self.assertTrue(report["scope"]["cp_bounds_recomputed"])
        self.assertFalse(report["scope"]["bootstrap_intervals_recomputed"])
        self.assertFalse(report["source_git_bytes_checked"])
        paper, notebook = (report["results"][j] for j in v.JUDGES)
        self.assertEqual(paper["target"]["complete_pairs"], 48)
        self.assertAlmostEqual(paper["target"]["estimate_complete_pairs"], 25 / 48)
        self.assertEqual(paper["target"]["suppression"]["missing"], 1)
        self.assertEqual(paper["target"]["amplification"]["missing"], 1)
        self.assertAlmostEqual(paper["specificity"]["estimate_complete_blocks"], 17 / 48)
        self.assertEqual(paper["specificity"]["complete_blocks"], 48)
        self.assertAlmostEqual(notebook["target"]["estimate_complete_pairs"], .3)
        self.assertAlmostEqual(notebook["specificity"]["estimate_complete_blocks"], 17 / 147)
        self.assertEqual(notebook["specificity"]["complete_blocks"], 49)
        self.assertEqual(notebook["zero"]["rate"], 9 / 49)
        self.assertEqual(report["flags"]["turn2_empty"], 1)

    def test_optional_raw_reconstruction_ignores_working_tree(self):
        originals = {path: path.read_bytes() for path in (
            self.repo / self.index()[0]["raw_path"], self.repo / RUN / v.FIGURES[0])}
        try:
            for path in originals:
                path.write_text("Uncommitted synthetic corruption")
            self.assertTrue(v.verify(self.package, self.repo)["source_git_bytes_checked"])
        finally:
            for path, blob in originals.items():
                path.write_bytes(blob)

    def tex_macros(self, blob=None):
        text = (self.package / "ensemble_values.tex").read_text() if blob is None else blob.decode("ascii")
        pairs = re.findall(r"^\\newcommand\{\\(Ensemble[A-Za-z]+)\}\{(.*)\}$", text, re.MULTILINE)
        self.assertEqual(len(pairs), len(dict(pairs)), "Duplicate macro names")
        self.assertEqual(len(pairs), len([line for line in text.splitlines() if not line.startswith("%")]))
        return dict(pairs)

    def test_tex_counts_points_and_decimal_reference_cp_both_judges(self):
        macros = self.tex_macros()
        self.assertEqual(len(macros), 54)
        # The synthetic summary was calculated with independent Decimal CP roots.
        reference = v.json_load((self.package / "analysis/summary.json").read_bytes())["results"]
        expected = {}
        for judge in ("paper", "notebook"):
            prefix, result = "Ensemble" + judge.title(), reference[judge]
            for label, stats in (("TargetSuppression", result["target"]["suppression"]),
                                 ("TargetAmplification", result["target"]["amplification"]), ("Zero", result["zero"])):
                for suffix, value in (("Positive", stats["positive"]), ("Planned", stats["n_planned"]),
                                      ("Missing", stats["missing"]), ("Valid", stats["n_planned"] - stats["missing"])):
                    expected[prefix + label + suffix] = str(value)
            target, specificity = result["target"], result["specificity"]
            for name, value in (("TargetGap", target["estimate_complete_pairs"]),
                                ("TargetCPLow", target["exact_marginal95"][0]),
                                ("TargetCPHigh", target["exact_marginal95"][1]),
                                ("TargetMinusControls", specificity["estimate_complete_blocks"]),
                                ("TargetMinusControlsCPLow", specificity["simultaneous95"][0]),
                                ("TargetMinusControlsCPHigh", specificity["simultaneous95"][1])):
                expected[prefix + name] = f"{value:+.4f}"
            expected[prefix + "TargetCompletePairs"] = str(target["complete_pairs"])
            expected[prefix + "TargetMinusControlsCompleteBlocks"] = str(specificity["complete_blocks"])
            for family, label in (("control-1", "ControlOne"), ("control-2", "ControlTwo"), ("control-3", "ControlThree")):
                expected[prefix + label + "Gap"] = f"{result[family]['estimate_complete_pairs']:+.4f}"
                expected[prefix + label + "CompletePairs"] = str(result[family]["complete_pairs"])
            expected[prefix + "Verdict"] = result["large_signature_verdict"].replace("_", " ")
        self.assertEqual(macros, expected)
        self.assertEqual(macros["EnsemblePaperTargetSuppressionPositive"], "29")
        self.assertEqual(macros["EnsemblePaperTargetAmplificationPositive"], "4")
        self.assertEqual(macros["EnsemblePaperTargetSuppressionPlanned"], "50")
        self.assertEqual(macros["EnsemblePaperTargetSuppressionValid"], "49")
        self.assertEqual(macros["EnsemblePaperTargetGap"], "+0.5208")
        self.assertEqual(macros["EnsembleNotebookZeroPositive"], "9")
        self.assertEqual(macros["EnsembleNotebookZeroPlanned"], "50")

    def test_tex_regeneration_rejects_rehashed_claim_and_derivation(self):
        path = self.package / "ensemble_values.tex"
        original = path.read_bytes()
        path.write_bytes(original.replace(b"+0.5208", b"+0.9999"))
        with self.assertRaisesRegex(v.VerificationError, "SHA256"):
            v.verify(self.package)
        self.rehash("ensemble_values.tex")
        with self.assertRaisesRegex(v.VerificationError, "TeX regeneration"):
            v.verify(self.package)
        path.write_bytes(original)
        self.rehash("ensemble_values.tex")
        manifest = v.json_load((self.package / "manifest.json").read_bytes())
        manifest["artifacts"]["ensemble_values.tex"]["derived_from"] = "Unchecked source headline"
        write_json(self.package / "manifest.json", manifest)
        with self.assertRaisesRegex(v.VerificationError, "Artifact derivation"):
            v.verify(self.package)

    def test_tex_verdict_text_is_allowlisted(self):
        results = v.verify(self.package)["results"]
        for code in ("large_positive_signature", "large_signature_not_recovered_under_public_operator", "inconclusive"):
            for judge in v.JUDGES:
                results[judge]["large_signature_verdict"] = code
            macros = self.tex_macros(v.ensemble_values(results))
            for judge in v.JUDGES:
                body = macros["Ensemble" + judge.title() + "Verdict"]
                self.assertEqual(body, code.replace("_", " "))
                self.assertRegex(body, r"^[a-z ]+$")
        for unsafe in (r"\input{bad}", "unknown_verdict", "50% & positive", "inconclusive\n}"):
            results["paper"]["large_signature_verdict"] = unsafe
            with self.assertRaisesRegex(v.VerificationError, "Unknown ensemble verdict"):
                v.ensemble_values(results)

    def test_optional_figures_are_exact_copies_and_bound_twice(self):
        self.assertEqual(set(v.FIGURES), {"secondary/aggregate_effects.pdf", "secondary/aggregate_effects.png",
                                         "secondary/aggregate_rates.pdf", "secondary/aggregate_rates.png"})
        report = v.verify(self.package)
        self.assertEqual(report["source_figures_copied"], list(v.FIGURES))
        self.assertFalse(report["scope"]["figures_independently_redrawn"])
        manifest = v.json_load((self.package / "manifest.json").read_bytes())
        for name in v.FIGURES:
            path = self.package / name
            original = path.read_bytes()
            entry = manifest["artifacts"][name]
            self.assertEqual(entry["source_commit"], self.commit)
            self.assertEqual(entry["source_path"], RUN + "/" + name)
            self.assertEqual(original, v.git_blob(self.repo, self.commit, entry["source_path"]))
            path.write_bytes(original + b"tampered")
            with self.assertRaisesRegex(v.VerificationError, "SHA256"):
                v.verify(self.package)
            self.rehash(name)
            with self.assertRaisesRegex(v.VerificationError, "SHA256"):
                v.verify(self.package)
            path.write_bytes(original)
            self.rehash(name)

    def test_optional_figures_absent_or_partial_are_supported(self):
        for i, figures in enumerate(((), ("secondary/aggregate_rates.pdf", "secondary/aggregate_rates.png"))):
            repo = self.work / f"source-{i}"
            commit, _ = synthetic_release(repo, figures=figures)
            package = builder.build(repo, commit, RUN, self.work / f"package-{i}")
            report = v.verify(package, repo)
            self.assertEqual(report["source_figures_copied"], list(figures))
            inventory = set(v.json_load((package / "manifest.json").read_bytes())["artifacts"])
            self.assertEqual(inventory, {*v.COPIES, *v.DERIVED, *figures})

    def test_present_source_figure_cannot_be_silently_omitted(self):
        name = v.FIGURES[0]
        (self.package / name).unlink()
        manifest = v.json_load((self.package / "manifest.json").read_bytes())
        del manifest["artifacts"][name]
        write_json(self.package / "manifest.json", manifest)
        with self.assertRaisesRegex(v.VerificationError, "Artifact inventory from pinned release"):
            v.verify(self.package)

    def test_rehashed_source_figure_requires_pinned_bytes(self):
        name = v.FIGURES[0]
        path = self.package / name
        path.write_bytes(b"SELF-CONSISTENT BUT NOT PINNED")
        self.rehash(name)
        release = v.json_load((self.package / "RELEASE_MANIFEST.json").read_bytes())
        next(e for e in release["files"] if e["path"] == name).update(sha256=v.sha256(path.read_bytes()), bytes=path.stat().st_size)
        write_json(self.package / "RELEASE_MANIFEST.json", release)
        self.rehash("RELEASE_MANIFEST.json")
        self.assertTrue(v.verify(self.package)["pass"])
        with self.assertRaisesRegex(v.VerificationError, "Pinned source bytes differ"):
            v.verify(self.package, self.repo)

    def test_corrupt_pinned_figure_refuses_publication(self):
        original = v.git_blob

        def substitute(repo, commit, path):
            blob = original(repo, commit, path)
            return blob + b"corrupt" if path == RUN + "/" + v.FIGURES[0] else blob

        destination = self.work / "never-created"
        with mock.patch.object(v, "git_blob", side_effect=substitute):
            with self.assertRaisesRegex(v.VerificationError, "SHA256"):
                builder.build(self.repo, self.commit, RUN, destination)
        self.assertFalse(destination.exists())

    def test_cp_primary_specificity_and_verdict_tampering(self):
        original = (self.package / "analysis/summary.json").read_bytes()
        mutations = [lambda r: r["paper"]["target"]["exact_marginal95"].__setitem__(0, -.99),
                     lambda r: r["paper"]["specificity"]["simultaneous95"].__setitem__(1, .01),
                     lambda r: r["paper"].update(large_signature_verdict="large_positive_signature"),
                     lambda r: r["paper"]["target"].update(complete_pairs=50)]
        for change in mutations:
            (self.package / "analysis/summary.json").write_bytes(original)
            self.change_summary(change)
            with self.assertRaisesRegex(v.VerificationError, "Summary"):
                v.verify(self.package)

    def test_bootstrap_not_claimed_as_verified(self):
        self.change_summary(lambda r: r["paper"]["target"].update(bootstrap95=[-.111, .222]))
        self.assertFalse(v.verify(self.package)["scope"]["bootstrap_intervals_recomputed"])
        with self.assertRaisesRegex(v.VerificationError, "Pinned source bytes differ"):
            v.verify(self.package, self.repo)

    def test_weight_subset_feature_and_sign_tampering(self):
        original = self.index()
        for field, value in (("weights", "[0.5]"), ("subset_positions", "[0]"),
                             ("feature_ids", "[30032]"), ("coefficient", "0")):
            rows = copy.deepcopy(original)
            row = next(r for r in rows if r["family"] == "target" and r["coefficient"] == "1")
            row[field] = value
            self.save_index(rows)
            with self.assertRaises(v.VerificationError):
                v.verify(self.package)

    def test_frozen_draw_changes_are_rejected(self):
        for field in ("weights", "feature_ids", "subset_positions"):
            plan = fixture_plan()
            row = next(r for r in plan["rows"] if r["family"] == "target" and r["coefficient"] == 1)
            row[field][0] = .51 if field == "weights" else 0
            with self.assertRaisesRegex(v.VerificationError, "frozen 50-block draw"):
                v.validate_plan(plan)

    def test_missing_duplicate_and_reordered_index(self):
        original = self.index()
        for rows in (original[:-1], original + [original[0]]):
            self.save_index(rows)
            with self.assertRaises(v.VerificationError):
                v.verify(self.package)
        self.save_index(list(reversed(original)))
        self.assertTrue(v.verify(self.package)["pass"])

    def test_raw_metadata_weight_mismatch_is_rejected(self):
        row = next(r for r in self.index() if r["family"] == "target")
        spec = next(s for s in fixture_plan()["rows"] if s["id"] == row["id"])
        raw = v.json_load(v.git_blob(self.repo, self.commit, row["raw_path"]))
        raw["turns"][0]["telemetry"]["weights"][0] = .42
        blob = v.json_bytes(raw)
        with self.assertRaisesRegex(v.VerificationError, "Weighted telemetry"):
            v.extract_row(blob, spec, row["raw_path"], {"sha256": v.sha256(blob), "bytes": len(blob)})

    def test_optional_rehashed_flag_and_empty_recode(self):
        rows = self.index()
        rows[0]["turn1_cap_hit"] = "0" if rows[0]["turn1_cap_hit"] == "1" else "1"
        self.save_index(rows)
        self.assertTrue(v.verify(self.package)["pass"])
        with self.assertRaisesRegex(v.VerificationError, "Raw-to-index"):
            v.verify(self.package, self.repo)
        next(r for r in rows if r["turn2_empty"] == "1")["paper_label"] = "0"
        self.save_index(rows)
        with self.assertRaisesRegex(v.VerificationError, "Empty outcome"):
            v.verify(self.package)

    def test_rates_rehashed_tampering(self):
        path = self.package / "analysis/rates.csv"
        rows = v.csv_rows(path.read_bytes(), v.RATE_FIELDS)
        rows[0]["positive"] = "50"
        path.write_bytes(v.csv_bytes(rows, v.RATE_FIELDS))
        self.rehash("analysis/rates.csv")
        with self.assertRaisesRegex(v.VerificationError, "Rates arithmetic"):
            v.verify(self.package)

    def test_all_missing_and_specificity_conservatism(self):
        plan = fixture_plan()
        release = v.json_load((self.package / "RELEASE_MANIFEST.json").read_bytes())
        rows = v.read_index((self.package / "trial_index.csv").read_bytes(), plan, release, RUN)
        for row in rows:
            row.update(paper_label=None, notebook_label=None)
        results, rates = v.recompute(rows)
        for judge in v.JUDGES:
            r = results[judge]
            self.assertEqual(r["target"]["exact_marginal95"], [-1., 1.])
            self.assertEqual(r["specificity"]["simultaneous95"], [-2., 2.])
            self.assertIsNone(r["specificity"]["estimate_complete_blocks"])
            self.assertEqual(r["specificity"]["complete_blocks"], 0)
            self.assertEqual(r["large_signature_verdict"], "inconclusive")
        self.assertTrue(all(r["rate"] is None and r["missing"] == 50 for r in rates))
        macros = self.tex_macros(v.ensemble_values(results))
        for judge in v.JUDGES:
            prefix = "Ensemble" + judge.title()
            for label in ("TargetSuppression", "TargetAmplification", "Zero"):
                self.assertEqual(macros[prefix + label + "Positive"], "0")
                self.assertEqual(macros[prefix + label + "Planned"], "50")
                self.assertEqual(macros[prefix + label + "Missing"], "50")
                self.assertEqual(macros[prefix + label + "Valid"], "0")
            for label in ("TargetGap", "TargetMinusControls", "ControlOneGap", "ControlTwoGap", "ControlThreeGap"):
                self.assertEqual(macros[prefix + label], r"\textnormal{NA}")
            self.assertEqual(macros[prefix + "TargetCPLow"], "-1.0000")
            self.assertEqual(macros[prefix + "TargetCPHigh"], "+1.0000")
            self.assertEqual(macros[prefix + "TargetMinusControlsCPLow"], "-2.0000")
            self.assertEqual(macros[prefix + "TargetMinusControlsCPHigh"], "+2.0000")

    def test_incomplete_release_wrong_schema_and_overwrite(self):
        with self.assertRaisesRegex(v.VerificationError, "Refusing to overwrite"):
            builder.build(self.repo, self.commit, RUN, self.package)
        new = self.work / "new"
        with self.assertRaises(v.VerificationError):
            builder.build(self.repo, self.freeze, RUN, new)
        self.assertFalse(new.exists())
        release = v.json_load((self.package / "RELEASE_MANIFEST.json").read_bytes())
        release["schema"] = "berg_source_release_v1"
        with self.assertRaises(v.VerificationError):
            v.release_files(release)

    def test_incomplete_completion_is_not_a_release(self):
        manifest = v.json_load((self.package / "manifest.json").read_bytes())
        release = v.json_load((self.package / "RELEASE_MANIFEST.json").read_bytes())
        done = v.json_load(manifest["completion_json"])
        done["rows"] = 450
        blob = v.json_bytes(done)
        manifest["completion_json"] = blob.decode()
        next(e for e in release["files"] if e["path"] == "DONE-all.json").update(
            sha256=v.sha256(blob), bytes=len(blob))
        write_json(self.package / "manifest.json", manifest)
        write_json(self.package / "RELEASE_MANIFEST.json", release)
        self.rehash("RELEASE_MANIFEST.json")
        with self.assertRaisesRegex(v.VerificationError, "Complete source release"):
            v.verify(self.package)

    def test_pin_path_hash_and_package_safety(self):
        for pin in ("HEAD", "abcd", "0" * 40):
            with self.assertRaises(v.VerificationError):
                builder.build(self.repo, pin, RUN, self.work / "new")
        for path in ("../bad", "/absolute", "x:y", "a\\b"):
            with self.assertRaises(v.VerificationError):
                builder.build(self.repo, self.commit, path, self.work / "new")
        extra = self.package / "extra.txt"
        extra.write_text("extra")
        with self.assertRaisesRegex(v.VerificationError, "Unmanifested"):
            v.verify(self.package)
        extra.unlink()
        index = self.package / "trial_index.csv"
        outside = self.work / "outside.csv"
        index.rename(outside)
        index.symlink_to(outside)
        with self.assertRaisesRegex(v.VerificationError, "Escaping path|Symlink"):
            v.verify(self.package)
        index.unlink()
        index.write_text("wrong bytes")
        with self.assertRaisesRegex(v.VerificationError, "SHA256"):
            v.verify(self.package)

    def test_portable_optimized_cli_and_help(self):
        portable = self.work / "portable"
        for name in v.GENERATORS:
            destination = portable / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, destination)
        shutil.copytree(self.package, portable / "evidence/ensemble_alignment")
        result = subprocess.run([sys.executable, "-B", "-O", str(portable / "scripts/verify_ensemble_alignment.py")],
                                cwd=self.work, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["scope"]["cp_bounds_recomputed"])
        for script in v.GENERATORS[:2]:
            result = subprocess.run([sys.executable, "-B", str(ROOT / script), "--help"], capture_output=True)
            self.assertEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
