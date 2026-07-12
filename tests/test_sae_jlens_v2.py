from __future__ import annotations

import re
import tempfile
import unittest
from collections import Counter
from pathlib import Path

import numpy as np
from sklearn.metrics import roc_auc_score

from experiments.exp2_sae.analyze_sae_jlens_v2 import (
    LEXICONS,
    TRANSPORTS,
    holm_adjust,
    reader_permutation_macro_auc,
    semantic_a1,
    semantic_a2,
    signflip_pvalues,
    weighted_auc_draws,
)
from experiments.exp2_sae.osf_sae_jlens_v2 import (
    PROJECT_TITLE,
    registration_metadata_errors,
)
from experiments.exp2_sae.run_sae_jlens_v2 import result_inventory
from experiments.exp2_sae.sae_jlens_v2_final_protocol import (
    array_sha256,
    build_final_trial_plan,
    prompt_fold_rows,
    random_projection,
    residual_schema,
)

from experiments.exp2_sae.sae_jlens_v2_protocol import (
    A1_FAMILIES,
    A2_SUBFAMILIES,
    TARGET_FEATURE_IDS,
    TARGET_SEMANTIC_ROOTS,
    excluded_feature_ids,
    match_semantic_features,
    semantic_candidate_pool,
    semantic_pool_sha256,
)


class SAEJacobianLensV2Tests(unittest.TestCase):
    @property
    def repo_root(self) -> Path:
        return Path(__file__).resolve().parents[1]

    def test_semantic_pool_is_frozen_unique_and_disjoint(self) -> None:
        rows = semantic_candidate_pool(self.repo_root)
        self.assertEqual(len(rows), 138)
        self.assertEqual(
            semantic_pool_sha256(rows),
            "0b617151284a4bdc491ce144cd9b34d08c172bb141ea03466e369f767d83793f",
        )
        feature_ids = [int(row["feature_id"]) for row in rows]
        self.assertEqual(len(feature_ids), len(set(feature_ids)))
        self.assertFalse(set(feature_ids) & set(excluded_feature_ids()))
        self.assertEqual(
            Counter((row["experiment"], row["semantic_family"]) for row in rows),
            Counter(
                {
                    ("A1", "refusal_safety"): 19,
                    ("A1", "hedging_uncertainty"): 25,
                    ("A1", "formality_politeness"): 22,
                    ("A2", "pretending_impersonation"): 11,
                    ("A2", "roleplay_persona"): 51,
                    ("A2", "deception_dishonesty"): 10,
                }
            ),
        )

    def test_a1_labels_share_no_frozen_target_semantic_root(self) -> None:
        roots = re.compile("|".join(TARGET_SEMANTIC_ROOTS), re.IGNORECASE)
        rows = semantic_candidate_pool(self.repo_root)
        self.assertTrue(
            all(not roots.search(row["description"]) for row in rows if row["experiment"] == "A1")
        )

    def test_equal_metric_fixture_selects_24_unique_features(self) -> None:
        candidates = semantic_candidate_pool(self.repo_root)
        metrics = []
        for feature_id in TARGET_FEATURE_IDS:
            metrics.append(self.metric_row(feature_id, "target"))
        for row in candidates:
            metrics.append(self.metric_row(int(row["feature_id"]), "candidate"))
        matching = match_semantic_features(metrics, candidates)
        selected = matching["selected"]
        self.assertEqual(len(selected), 24)
        self.assertEqual(len({int(row["feature_id"]) for row in selected}), 24)
        self.assertEqual(
            Counter((row["experiment"], row["semantic_family"]) for row in selected),
            Counter(
                {
                    **{("A1", family): 6 for family in A1_FAMILIES},
                    ("A2", "pretending_impersonation"): 1,
                    ("A2", "roleplay_persona"): 2,
                    ("A2", "deception_dishonesty"): 3,
                }
            ),
        )
        self.assertEqual(
            {row["semantic_family"] for row in selected if row["experiment"] == "A2"},
            set(A2_SUBFAMILIES),
        )

    def test_final_trial_plan_has_exact_replay_and_semantic_grid(self) -> None:
        calibration = self.synthetic_calibration()
        rows = build_final_trial_plan(
            self.repo_root
            / "data/sae_jlens_audit/confirmatory_v1_plan_20260711",
            calibration,
        )
        self.assertEqual(len(rows), 4_029)
        self.assertEqual(len({row["trial_id"] for row in rows}), 4_029)
        self.assertEqual(
            sorted(int(row["execution_order"]) for row in rows), list(range(4_029))
        )
        replay = [row for row in rows if row["source_v1_trial_id"] is not None]
        semantic = [row for row in rows if row["source_v1_trial_id"] is None]
        self.assertEqual(len(replay), 1_581)
        self.assertEqual(len(semantic), 2_448)
        self.assertEqual(
            set(Counter(int(row["comparator_feature_id"]) for row in semantic).values()),
            {102},
        )

    def test_prompt_folds_and_residual_bytes_are_exact(self) -> None:
        folds = prompt_fold_rows(
            self.repo_root
            / "data/sae_jlens_audit/confirmatory_v1_plan_20260711"
        )
        self.assertEqual(len(folds), 51)
        self.assertEqual(
            sorted(Counter(int(row["fold"]) for row in folds).values()),
            [10, 10, 10, 10, 11],
        )
        schema = residual_schema()
        self.assertEqual(schema["row_shape"], [7, 3, 8_192])
        self.assertEqual(schema["expected_tensor_bytes"], 1_386_233_856)

    def test_random_projection_is_deterministic_and_column_normalized(self) -> None:
        first = random_projection(2_026_071_201)
        second = random_projection(2_026_071_201)
        self.assertEqual(first.shape, (8_192, 67))
        self.assertEqual(first.dtype, np.float32)
        self.assertEqual(array_sha256(first), array_sha256(second))
        np.testing.assert_allclose(
            np.linalg.norm(first, axis=0), np.ones(67), atol=2e-6
        )

    def test_semantic_analyses_cover_every_frozen_transport_and_cell(self) -> None:
        rows = self.synthetic_primary_rows()
        matrix, contrasts, leakage, features, a1_verdicts = semantic_a1(rows, 200)
        pairs, summary, a2_verdicts = semantic_a2(rows, 200)
        self.assertEqual(len(matrix), len(TRANSPORTS) * 4 * 4)
        self.assertEqual(len(contrasts), len(TRANSPORTS) * 5)
        self.assertEqual(len(leakage), len(TRANSPORTS) * 3)
        self.assertEqual(len(features), len(TRANSPORTS) * 24 * len(LEXICONS))
        self.assertEqual(len(pairs), len(TRANSPORTS) * 6)
        self.assertEqual(len(summary), len(TRANSPORTS))
        self.assertEqual(set(a1_verdicts), set(TRANSPORTS))
        self.assertEqual(set(a2_verdicts), set(TRANSPORTS))
        self.assertTrue(a1_verdicts["jacobian"]["family_specificity_supported"])

    def test_holm_adjustment_is_monotone_in_rank_order(self) -> None:
        raw = [0.04, 0.001, 0.02, 0.2]
        adjusted = holm_adjust(raw)
        ordered = sorted(zip(raw, adjusted))
        self.assertEqual([value for _, value in ordered], sorted(value for _, value in ordered))

    def test_registration_gate_requires_public_immutable_bound_views(self) -> None:
        registration_id = "abc12"
        project_id = "sz2gb"
        freeze_commit = "a" * 40
        plan_hash = "b" * 64
        data = {
            "id": registration_id,
            "type": "registrations",
            "attributes": {
                "registration": True,
                "public": True,
                "withdrawn": False,
                "pending_registration_approval": False,
                "pending_embargo_approval": False,
                "date_registered": "2026-07-12T00:00:00Z",
                "title": PROJECT_TITLE,
                "registration_supplement": "Open-Ended Registration",
                "registered_meta": {
                    "summary": f"freeze {freeze_commit}; plan {plan_hash}"
                },
            },
            "relationships": {
                "registered_from": {
                    "links": {"related": f"https://api.osf.io/v2/nodes/{project_id}/"}
                }
            },
        }
        errors = registration_metadata_errors(
            data,
            data,
            registration_id=registration_id,
            project_id=project_id,
            freeze_commit=freeze_commit,
            plan_manifest_sha256=plan_hash,
        )
        self.assertEqual(errors, [])
        pending = {**data, "attributes": {**data["attributes"], "public": False}}
        self.assertIn(
            "anonymous registration is not public",
            registration_metadata_errors(
                data,
                pending,
                registration_id=registration_id,
                project_id=project_id,
                freeze_commit=freeze_commit,
                plan_manifest_sha256=plan_hash,
            ),
        )

    def test_raw_result_manifest_excludes_live_logs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "stable.json").write_text("{}\n", encoding="utf-8")
            (root / "run.log").write_text("still live\n", encoding="utf-8")
            names = {row["path"] for row in result_inventory(root)}
        self.assertEqual(names, {"stable.json"})

    def test_vectorized_weighted_auc_matches_sklearn_with_ties(self) -> None:
        labels = np.asarray([0, 1, 0, 1, 0, 1])
        scores = np.asarray([0.1, 0.7, 0.4, 0.4, 0.8, 0.9])
        template_columns = np.asarray([0, 0, 1, 1, 2, 2])
        counts = np.asarray([[1, 1, 1], [2, 0, 1], [0, 3, 1]])
        observed = weighted_auc_draws(
            labels, scores, template_columns, counts
        )
        expected = np.asarray(
            [
                roc_auc_score(
                    labels,
                    scores,
                    sample_weight=row[template_columns],
                )
                for row in counts
            ]
        )
        np.testing.assert_allclose(observed, expected, atol=1e-12)

    def test_reader_label_randomization_detects_perfect_paired_scores(self) -> None:
        rows = []
        for template in range(10):
            for sign in ("suppression", "amplification"):
                for label in (0, 1):
                    rows.append(
                        {
                            "feature_pair": 30032,
                            "template_id": f"template-{template}",
                            "sign": sign,
                            "label": label,
                            "probability": 0.9 if label else 0.1,
                        }
                    )
        point, pvalue = reader_permutation_macro_auc(rows, 2_000, 2026071600)
        self.assertEqual(point, 1.0)
        self.assertLess(pvalue, 0.01)

    def test_template_signflip_detects_consistent_positive_effect(self) -> None:
        values = np.ones((51, 2), dtype=np.float64)
        pvalues = signflip_pvalues(
            values, np.asarray([1.0, 1.0]), 2_000, 2026071310
        )
        self.assertTrue(all(value < 0.01 for value in pvalues))

    def synthetic_calibration(self) -> dict[str, object]:
        candidates = semantic_candidate_pool(self.repo_root)
        metrics = [self.metric_row(feature_id, "target") for feature_id in TARGET_FEATURE_IDS]
        metrics.extend(
            self.metric_row(int(row["feature_id"]), "candidate") for row in candidates
        )
        matching = match_semantic_features(metrics, candidates)
        return {"semantic_matching": matching}

    @staticmethod
    def synthetic_primary_rows() -> list[dict[str, object]]:
        target_ids = list(TARGET_FEATURE_IDS)
        a1_features = {
            family: list(range(10_000 + index * 10, 10_006 + index * 10))
            for index, family in enumerate(A1_FAMILIES)
        }
        a2_features = list(range(20_000, 20_006))
        rows: list[dict[str, object]] = []
        for prompt_index in range(51):
            prompt_id = f"prompt-{prompt_index:02d}"
            template_id = f"template-{prompt_index:02d}"
            for transport_index, transport in enumerate(TRANSPORTS):
                clean_groups = {"v2_unrelated": 0.0}
                for lexicon_index, lexicon in enumerate(LEXICONS, start=1):
                    clean_groups[f"v2_{lexicon}"] = (
                        (prompt_index - 25) * 0.02 * lexicon_index
                        + transport_index * 0.001
                    )
                base = {
                    "prompt_id": prompt_id,
                    "template_id": template_id,
                    "transport": transport,
                    "group_logits": clean_groups,
                }
                rows.append(
                    {
                        **base,
                        "condition_family": "zero",
                        "sign": "zero",
                        "matched_target_feature_id": None,
                        "semantic_experiment": None,
                        "semantic_family": None,
                        "comparator_feature_id": None,
                    }
                )
                for target_index, target_id in enumerate(target_ids):
                    for sign_name, sign_value in (("suppression", -1.0), ("amplification", 1.0)):
                        groups = dict(clean_groups)
                        groups["v2_deception_dishonesty"] += sign_value * 1.0
                        for lexicon in LEXICONS[1:]:
                            groups[f"v2_{lexicon}"] += sign_value * 0.05
                        rows.append(
                            {
                                **base,
                                "group_logits": groups,
                                "condition_family": "target_single",
                                "sign": sign_name,
                                "matched_target_feature_id": target_id,
                                "semantic_experiment": None,
                                "semantic_family": None,
                                "comparator_feature_id": None,
                            }
                        )
                        a2_groups = dict(clean_groups)
                        a2_groups["v2_deception_dishonesty"] += sign_value * 0.8
                        rows.append(
                            {
                                **base,
                                "group_logits": a2_groups,
                                "condition_family": "same_subfamily_single",
                                "sign": sign_name,
                                "matched_target_feature_id": target_id,
                                "semantic_experiment": "A2",
                                "semantic_family": (
                                    "pretending_impersonation"
                                    if target_index == 0
                                    else "roleplay_persona"
                                    if target_index < 3
                                    else "deception_dishonesty"
                                ),
                                "comparator_feature_id": a2_features[target_index],
                            }
                        )
                for family_index, family in enumerate(A1_FAMILIES, start=1):
                    for feature_id in a1_features[family]:
                        for sign_name, sign_value in (("suppression", -1.0), ("amplification", 1.0)):
                            groups = dict(clean_groups)
                            for lexicon in LEXICONS:
                                groups[f"v2_{lexicon}"] += sign_value * (
                                    1.0 if lexicon == family else 0.05
                                )
                            rows.append(
                                {
                                    **base,
                                    "group_logits": groups,
                                    "condition_family": "hard_negative_single",
                                    "sign": sign_name,
                                    "matched_target_feature_id": target_ids[
                                        feature_id - a1_features[family][0]
                                    ],
                                    "semantic_experiment": "A1",
                                    "semantic_family": family,
                                    "comparator_feature_id": feature_id,
                                }
                            )
        return rows

    @staticmethod
    def metric_row(feature_id: int, role: str) -> dict[str, float | int | str]:
        return {
            "feature_id": feature_id,
            "feature_role": role,
            "decoder_norm": 1.0,
            "max_abs_target_cosine": 0.0 if role == "candidate" else 1.0,
            "mean_activation": 0.0,
            "max_activation": 0.0,
            "positive_token_fraction": 0.0,
            "n_prompt_positions": 286,
        }


if __name__ == "__main__":
    unittest.main()
