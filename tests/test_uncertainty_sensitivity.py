"""Numerical, design and provenance tests for the POST-HOC B02 package."""

import importlib.util
import itertools
import json
import math
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("sensitivity", ROOT / "scripts/uncertainty_sensitivity.py")
u = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(u)


class IntervalsTest(unittest.TestCase):
    def test_exact_boundary_closed_forms(self):
        for n in (1, 10, 20, 50):
            low, high = u.clopper_pearson(0, n)
            self.assertEqual(low, 0)
            self.assertAlmostEqual(high, 1-.025**(1/n), places=13)
            low, high = u.clopper_pearson(n, n)
            self.assertAlmostEqual(low, .025**(1/n), places=13)
            self.assertEqual(high, 1)

    def test_exact_interior_tail_and_symmetry(self):
        for n in (10, 20, 50):
            for k in range(1, n):
                lo, hi = u.clopper_pearson(k, n, .975)
                self.assertAlmostEqual(u.binomial_cdf(k, n, hi), .0125, places=11)
                self.assertAlmostEqual(u.binomial_cdf(n-k, n, 1-lo), .0125, places=11)
                self.assertLess(lo, k/n)
                self.assertGreater(hi, k/n)

    def test_invalid_counts(self):
        for k, n in ((-1, 5), (6, 5), (0, 0), (1.0, 5), (True, 5)):
            with self.assertRaises(ValueError):
                u.clopper_pearson(k, n)

    def test_no_discordance_not_certainty(self):
        r = u.paired_exact({"00": 0, "01": 0, "10": 0, "11": 50})
        radius = 1-.0125**(1/50)
        self.assertAlmostEqual(r["interval"][0], -radius)
        self.assertAlmostEqual(r["interval"][1], radius)

    def test_exact_paired_coverage_small_multinomial(self):
        # Enumerate all n=6 tables to check the coverage construction directly.
        n = 6
        tables = []
        for a in range(n+1):
            for b in range(n-a+1):
                for c in range(n-a-b+1):
                    counts = (a, b, c, n-a-b-c)
                    ci = u.paired_exact(dict(zip(("00", "01", "10", "11"), counts)))["interval"]
                    coefficient = math.factorial(n)/math.prod(math.factorial(v) for v in counts)
                    tables.append((counts, ci, coefficient))
        for probs in ((.8, .1, .1, 0), (.1, .1, .3, .5), (0, 0, 0, 1), (.25,)*4):
            d = probs[2]-probs[1]
            coverage = sum(coef*math.prod(p**k for p, k in zip(probs, counts))
                           for counts, ci, coef in tables if ci[0]-1e-12 <= d <= ci[1]+1e-12)
            self.assertGreaterEqual(coverage, .95-1e-12)

    def test_newcombe_matches_existing_package(self):
        spec = importlib.util.spec_from_file_location("existing", ROOT / "scripts/verify_evidence.py")
        existing = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(existing)
        for s, h in itertools.product((0, 2, 10, 20), repeat=2):
            d, ci = u.newcombe(s, 20, h, 20)
            old = existing.newcombe_independent(s, 20, h, 20)
            self.assertAlmostEqual(d, old["estimate"])
            self.assertAlmostEqual(ci[0], old["ci_low"], places=11)
            self.assertAlmostEqual(ci[1], old["ci_high"], places=11)
        self.assertLess(u.newcombe(20, 20, 0, 20)[1][0], 1)

    def test_quantile(self):
        self.assertEqual(u.quantile([0, 1, 2, 3], .25), .75)

    def test_t9_critical_value_by_independent_quadrature(self):
        t, df, steps = 2.2621571627409915, 9, 10000
        coefficient = math.gamma((df+1)/2)/(math.sqrt(df*math.pi)*math.gamma(df/2))
        density = lambda x: coefficient*(1+x*x/df)**(-(df+1)/2)
        h = t/steps
        area = h/3*(density(0)+density(t)+math.fsum(
            (4 if i % 2 else 2)*density(i*h) for i in range(1, steps)))
        self.assertAlmostEqual(.5+area, .975, places=10)


class DesignTest(unittest.TestCase):
    def pairs(self):
        return [{"seed": s, "suppression": 1, "amplification": 1}
                for s in range(10) for _ in range(5)]

    def test_zero_cluster_variance_not_certainty(self):
        r = u.seed_sensitivity(self.pairs(), "test", draws=200)
        self.assertEqual(r["bootstrap_interval"], [0, 0])
        self.assertTrue(r["bootstrap_degenerate"])
        self.assertIsNone(r["t_interval"])
        self.assertGreater(r["hoeffding_interval"][1], .30)

    def test_nonzero_cluster_t_and_cluster_grouping(self):
        pairs = self.pairs()
        for row in pairs[:5]:
            row["amplification"] = 0
        r = u.seed_sensitivity(pairs, "test", draws=200)
        self.assertAlmostEqual(r["estimate"], .1)
        self.assertAlmostEqual(r["sample_sd"], math.sqrt(.1))
        self.assertAlmostEqual(r["t_interval"][1], .1+2.2621571627409915*.1)
        self.assertEqual(r["clusters"][0]["paired_counts"]["10"], 5)
        self.assertEqual(r, u.seed_sensitivity(pairs, "test", draws=200))

    def test_bad_cluster_and_missingness_fail(self):
        pairs = self.pairs()
        with self.assertRaises(ValueError):
            u.seed_sensitivity(pairs[:-1], "test", draws=200)
        pairs[0]["suppression"] = None
        with self.assertRaises(ValueError):
            u.seed_sensitivity(pairs, "test", draws=200)

    def test_pairing_rejects_duplicate_and_seed_mismatch(self):
        rows = [{"trial_id": "a", "phase": "aggregate_literal", "analysis_role": "target",
                 "block_id": "b", "sign": "suppression", "seed": 1},
                {"trial_id": "b", "phase": "aggregate_literal", "analysis_role": "target",
                 "block_id": "b", "sign": "amplification", "seed": 2}]
        labels = [{"trial_id": r["trial_id"], "paper_label": 1} for r in rows]
        with self.assertRaisesRegex(ValueError, "seeds differ"):
            u.pair_llama(rows, labels)
        with self.assertRaisesRegex(ValueError, "duplicate join"):
            u.pair_llama(rows, labels+labels[:1])

    def test_causal_missing_stays_missing(self):
        rows = []
        for model, query, (a, b) in itertools.product(range(4), sorted(u.QUERIES),
                                                     itertools.product(u.ANCHORS, repeat=2)):
            rows.append({"trial_id": str(len(rows)), "model_key": str(model), "query_id": query,
                         "pair_index": "p", "instruction_cell": a, "transcript_cell": b,
                         "phase": "factorial_natural" if a == b else "transcript_transplant"})
        labels = [{"trial_id": r["trial_id"], "judge_key": key, "task": "paper", "paper_label": 1}
                  for r in rows for key in u.JUDGES.values()]
        labels[0]["paper_label"] = None
        calibration, blocks = u.causal_inputs(rows, labels)
        self.assertEqual(sum(None in b["cells"] for b in blocks), 1)
        self.assertEqual(sum(r["n_rows"]-r["n"] for r in calibration), 1)
        with self.assertRaisesRegex(ValueError, "duplicate join"):
            u.causal_inputs(rows, labels+labels[:1])

    def test_fixed_panel_no_model_resampling_or_row_pooling(self):
        groups = {"a": [[1, 1, 0, 0]]*2, "b": [[0, 0, 0, 0]]*8,
                  "c": [[0, 0, 0, 0]]*10, "d": [[0, 0, 0, 0]]*12}
        result = u.fixed_panel_bootstrap(groups, "test", draws=200)
        self.assertEqual(result["instruction_source_main"]["estimate"], .25)
        self.assertEqual(result["instruction_source_main"]["interval"], [.25, .25])
        self.assertEqual(result, u.fixed_panel_bootstrap(groups, "test", draws=200))
        for cells in itertools.product((0, 1), repeat=4):
            values = u.contrasts(cells)
            self.assertEqual(values[0]-values[1], values[3])


class PackageTest(unittest.TestCase):
    def test_recompute_compares_json_sequence_types(self):
        computed = {"interval": (-0.12, 0.12), "n": 50}
        archived = {"interval": [-0.12, 0.12], "n": 50}
        self.assertEqual(u.compare_recomputed(json.loads(u.json_bytes(computed)), archived), 0.0)

    def test_recompute_allows_only_float_roundoff(self):
        expected = {"n": 50, "ci": [-.12, .12], "status": "exploratory"}
        actual = {"n": 50, "ci": [-.12 + 1e-14, .12], "status": "exploratory"}
        self.assertLess(u.compare_recomputed(actual, expected), 1e-12)
        actual["ci"][0] += 1e-9
        with self.assertRaisesRegex(ValueError, "value mismatch"):
            u.compare_recomputed(actual, expected)

    def test_recompute_preserves_counts_types_and_status(self):
        for actual, expected in ((51, 50), (50.0, 50), (True, 1),
                                 ("confirmatory", "exploratory")):
            with self.assertRaises(ValueError):
                u.compare_recomputed(actual, expected)

    def test_recompute_rejects_missing_structure(self):
        for actual, expected in (({"n": 50}, {"n": 50, "ci": []}),
                                 ([1, 2], [1]), ({"n": 50}, [50])):
            with self.assertRaises(ValueError):
                u.compare_recomputed(actual, expected)

    def test_recompute_rejects_nonfinite(self):
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.assertRaisesRegex(ValueError, "nonfinite"):
                u.compare_recomputed(value, 0.0)

    def test_method_freeze(self):
        self.assertEqual(u.frozen_method()["source_commit"], u.PIN)

    def test_compact_package_hashes_and_latex(self):
        manifest_path = u.DEFAULT_DIR / "manifest.json"
        if not manifest_path.exists():
            self.skipTest("first extraction has not run")
        manifest = json.loads(manifest_path.read_bytes())
        for name, meta in manifest["files"].items():
            data = (u.DEFAULT_DIR/name).read_bytes()
            self.assertEqual(u.sha256(data), meta["sha256"])
            self.assertEqual(len(data), meta["bytes"])
        results = json.loads((u.DEFAULT_DIR/"results.json").read_bytes())
        self.assertEqual((u.DEFAULT_DIR/"values.tex").read_bytes(), u.latex_values(results))
        self.assertTrue(all(s["commit"] == u.PIN for s in manifest["sources"]))
        self.assertEqual(len(results["calibration"]), 32)
        self.assertEqual(len(results["fixed_panel"]), 32)
        self.assertFalse(results["llama"]["literal"]["upper_below_0_30"]["seed_hoeffding"])
        self.assertEqual(results["llama"]["literal"]["paired_counts"],
                         {"00": 1, "01": 1, "10": 1, "11": 47})
        self.assertEqual(results["llama"]["calibrated"]["paired_counts"],
                         {"00": 0, "01": 8, "10": 3, "11": 39})
        tex = (u.DEFAULT_DIR/"values.tex").read_text()
        self.assertIn("GPT-4.1", tex)
        self.assertIn("Sonnet 4.5", tex)
        self.assertIn("OpenAI &", tex)


if __name__ == "__main__":
    unittest.main()
