"""Synthetic J comparator tables; no real releases or outcome fixtures."""
from decimal import Decimal
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = load("build_source_jlens_table", ROOT / "evidence/build_source_jlens_table.py")
v = builder.verify
source = v.source
fixture = load("source_jlens_table_fixture", ROOT / "tests/test_source_alignment.py")


class SourceJlensTableTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.root = Path(cls.temp.name)
        cls.repo = cls.root / "synthetic-source"
        cls.commit, _ = fixture.synthetic_release(cls.repo)
        cls.original = cls.root / "original-package"
        fixture.builder.build(cls.repo, cls.commit, fixture.RUN, cls.original)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=self.root)
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.package = self.work / "source_alignment"
        shutil.copytree(self.original, self.package)
        self.table = self.work / "source_jlens_table.tex"

    def rehash(self, name):
        path = self.package / name
        manifest = source.json_load((self.package / "manifest.json").read_bytes())
        manifest["artifacts"][name].update(sha256=source.sha256(path.read_bytes()), bytes=path.stat().st_size)
        (self.package / "manifest.json").write_bytes(source.json_bytes(manifest))

    def write_csv(self, name, rows, fields):
        (self.package / name).write_bytes(source.csv_bytes(rows, fields))
        self.rehash(name)

    def data_lines(self, blob):
        return [line for line in blob.decode().splitlines() if " & $" in line]

    def test_all_groups_signs_and_true_random_extrema(self):
        before = {p.relative_to(self.package): p.read_bytes() for p in self.package.rglob("*") if p.is_file()}
        with mock.patch.object(source, "git", side_effect=AssertionError("Offline table called Git")):
            builder.build(self.package, self.table)
            report = v.verify(self.table, self.package)
        self.assertEqual(report["groups"], 7)
        self.assertEqual(report["table_rows"], 14)
        self.assertEqual(report["overview_contrasts_verified"], 588)
        self.assertEqual(report["seed_panel_rows_verified"], 4704)
        self.assertEqual(report["missing_table_cells"], 0)
        self.assertFalse(report["source_git_bytes_checked"])
        expected = []
        for g, group in enumerate(("Deception", "Experience", "Hedging", "Honesty", "Intervention", "Roleplay", "Unrelated")):
            for sign in (-1, 1):
                # Fixture's exact closed form: .02*sign*(16+4*transport+5*group)+.02.
                def value(t):
                    return Decimal(2 * sign * (16 + 4 * t + 5 * g) + 2) / 100

                random_values = [value(t) for t in range(2, 7)]
                cells = (value(1), value(0), min(random_values), max(random_values))
                expected.append(" & ".join((group, f"${Decimal(sign)/2:+.1f}$",
                                            *(f"${cell:+.4f}$" for cell in cells))) + r" \\")
        self.assertEqual(self.data_lines(self.table.read_bytes()), expected)
        text = self.table.read_text()
        for phrase in (self.commit, "two seeds", "no confidence intervals", "transport range, not uncertainty",
                       "zero", "not raw-state-to-J reconstruction"):
            self.assertIn(phrase.lower(), text.lower())
        after = {p.relative_to(self.package): p.read_bytes() for p in self.package.rglob("*") if p.is_file()}
        self.assertEqual(before, after)
        self.assertEqual(builder.build(self.package, self.table), self.table)

    def test_pinned_git_crosscheck(self):
        builder.build(self.package, self.table, self.repo)
        self.assertTrue(v.verify(self.table, self.package, self.repo)["source_git_bytes_checked"])

    def test_table_tampering_and_different_existing_output(self):
        builder.build(self.package, self.table)
        original = self.table.read_bytes()
        self.table.write_bytes(original.replace(b"+0.4200", b"+9.9999"))
        self.assertNotEqual(self.table.read_bytes(), original)
        with self.assertRaisesRegex(source.VerificationError, "table regeneration differs"):
            v.verify(self.table, self.package)
        with self.assertRaisesRegex(source.VerificationError, "Refusing to overwrite"):
            builder.build(self.package, self.table)
        self.assertIn(b"+9.9999", self.table.read_bytes())

    def test_missing_random_or_group_overview_cell_refuses_output(self):
        name = "jlens_overview.csv"
        original = source.csv_rows((self.package / name).read_bytes(), source.J_OVERVIEW_FIELDS)
        for omitted in (
            lambda r: r["transport"] == "random_j_5" and r["history"] == "zero" and r["layer"] == "78" and r["group"] == "deception",
            lambda r: r["group"] == "unrelated",
            # The unprinted portions of the overview are validated too.
            lambda r: r["history"] == "steered" and r["layer"] == "50" and r["transport"] == "random_j_1",
        ):
            self.write_csv(name, [r for r in original if not omitted(r)], source.J_OVERVIEW_FIELDS)
            with self.assertRaisesRegex(source.VerificationError, "J overview regeneration"):
                builder.build(self.package, self.table)
            self.assertFalse(self.table.exists())

    def test_missing_or_duplicate_seed_panel_member_refuses_output(self):
        name = "jlens_index.csv"
        original = source.csv_rows((self.package / name).read_bytes(), source.J_INDEX_FIELDS)
        selected = next(r for r in original if r["transport"] == "random_j_3" and r["family"] == "aggregate-control-2"
                        and r["seed"] == "202" and r["history"] == "zero" and r["layer"] == "78")
        for rows in ([r for r in original if r is not selected], original + [selected]):
            self.write_csv(name, rows, source.J_INDEX_FIELDS)
            with self.assertRaisesRegex(source.VerificationError, "Incomplete J overview|duplicate J overview"):
                builder.build(self.package, self.table)
            self.assertFalse(self.table.exists())

    def test_missing_random_value_preserved_without_narrowing_range(self):
        name = "jlens_index.csv"
        rows = source.csv_rows((self.package / name).read_bytes(), source.J_INDEX_FIELDS)
        selected = next(r for r in rows if r["transport"] == "random_j_3" and r["family"] == "aggregate-control-2"
                        and r["history"] == "zero" and r["layer"] == "78" and r["group"] == "deception"
                        and r["coefficient"] == "0.5")
        selected["normalized_logit_delta"] = ""
        self.write_csv(name, rows, source.J_INDEX_FIELDS)
        plan = source.json_load((self.package / "PLAN.json").read_bytes())
        overview = source.jlens_overview(source.read_jlens_index((self.package / name).read_bytes(), plan))
        self.write_csv("jlens_overview.csv", overview, source.J_OVERVIEW_FIELDS)
        # The four source macros exclude random transports, so they are unchanged.
        builder.build(self.package, self.table)
        self.assertEqual(v.verify(self.table, self.package)["missing_table_cells"], 2)
        positive = next(line for line in self.data_lines(self.table.read_bytes()) if line.startswith("Deception & $+0.5$"))
        self.assertEqual(positive, r"Deception & $+0.5$ & $+0.4200$ & $+0.3400$ & NA & NA \\")

    def test_rounding_and_unsigned_zero(self):
        self.assertEqual(v.number(Decimal("-0.0000001")), "$+0.0000$")
        self.assertEqual(v.number(Decimal("0.12345")), "$+0.1234$")
        self.assertEqual(v.number(Decimal("-0.12346")), "$-0.1235$")
        self.assertEqual(v.number(None), "NA")

    def test_package_and_symlink_write_guards(self):
        for table in (self.package / "table.tex", self.package / "subdir/table.tex"):
            with self.assertRaisesRegex(source.VerificationError, "outside the immutable"):
                builder.build(self.package, table)
            self.assertFalse(table.exists())
        alias = self.work / "alias"
        alias.symlink_to(self.package, target_is_directory=True)
        with self.assertRaisesRegex(source.VerificationError, "outside the immutable"):
            builder.build(self.package, alias / "table.tex")
        self.table.symlink_to(self.package / "source_values.tex")
        with self.assertRaisesRegex(source.VerificationError, "symlink"):
            builder.build(self.package, self.table)

    def test_portable_cli_and_help(self):
        portable = self.work / "portable"
        for name in (*source.GENERATORS, "evidence/build_source_jlens_table.py", "scripts/verify_source_jlens_table.py"):
            destination = portable / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, destination)
        shutil.copytree(self.package, portable / "evidence/source_alignment")
        for name in ("evidence/build_source_jlens_table.py", "scripts/verify_source_jlens_table.py"):
            command = [sys.executable, "-B", "-O", str(portable / name)]
            result = subprocess.run(command, cwd=self.work, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            if name.startswith("scripts/"):
                self.assertTrue(json.loads(result.stdout)["pass"])
            self.assertEqual(subprocess.run(command + ["--help"], capture_output=True).returncode, 0)


if __name__ == "__main__":
    unittest.main()
