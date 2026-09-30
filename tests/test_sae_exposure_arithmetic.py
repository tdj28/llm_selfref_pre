"""Hand-calculated synthetic checks, without importing frozen scientific code."""
import ast
from copy import deepcopy
import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest
import torch
from safetensors.torch import save_file

from scripts import check_sae_exposure_arithmetic as a


def clean_fixture(count=8):
    texts, certificates, rows = [], [], []
    for i in range(count):
        rid = f"d{i:02d}"
        item = {"id": rid, "family": "family-a" if i < 7 else "family-b", "split": "discovery"}
        texts.append(item)
        cert = {"id": rid, "token_ids": list(range(21)), "special_tokens_mask": [True] + [False] * 20}
        certificates.append(cert)
        rows.append({"id": "clean-" + rid, "text_id": rid, "family": item["family"], "split": item["split"],
                     "feature_ids": list(a.FEATURES), "token_ids": cert["token_ids"],
                     "special_tokens_mask": cert["special_tokens_mask"],
                     "activations": {str(f): [999.] + ([1.] * 20 if j == 0 else [0.] * 20)
                                     for j, f in enumerate(a.FEATURES)}})
    return {"texts": texts, "certificate": {"items": certificates}}, rows


def test_clean_positive_positions_texts_families_and_zero_features():
    plan, rows = clean_fixture()
    result, per_text = a.clean_counts(plan, rows)
    panel = result["panels"]["discovery"]
    assert panel["nonspecial_positions"] == 160
    assert panel["features"][0] == {"feature_id": a.FEATURES[0], "active_positions": 160,
        "active_texts": 8, "active_families": 2, "exposure_minimum_met": True}
    assert all(f["active_positions"] == f["active_texts"] == f["active_families"] == 0
               and not f["exposure_minimum_met"] for f in panel["features"][1:])
    assert len(panel["features"]) == 6 and not result["exposure_minima_met"]
    assert per_text["d00"]["positive_positions"][str(a.FEATURES[0])] == 20
    assert result["discovery"]["per_feature"][0]["selected_ids"] == [f"d{i:02d}" for i in (0, 1, 2, 3, 4, 5, 7)]
    assert result["discovery"]["selected_panel"]["features"][0]["active_positions"] == 140
    assert result["discovery"]["per_feature"][1]["selected_ids"] == []


@pytest.mark.parametrize("fault", ["missing", "duplicate", "negative", "nonfinite", "missing_feature", "mask"])
def test_clean_invalid_never_becomes_zero(fault):
    plan, rows = clean_fixture()
    if fault == "missing":
        rows.pop()
    elif fault == "duplicate":
        rows.append(deepcopy(rows[0]))
    elif fault == "missing_feature":
        del rows[0]["activations"][str(a.FEATURES[-1])]
    elif fault == "mask":
        rows[0]["special_tokens_mask"] = [1] + [False] * 20
    else:
        rows[0]["activations"][str(a.FEATURES[0])][1] = -1 if fault == "negative" else float("nan")
    with pytest.raises(ValueError):
        a.clean_counts(plan, rows)


def metric_fixture():
    pre = np.array([[[100., 0.]] * 5])
    requested = np.array([[[0., 0.], [3., 4.], [1., 0.], [0., 0.], [6., 0.]]])
    post = pre + np.array([[[0., 0.], [3., 4.], [0., 0.], [0., 0.], [-6., 0.]]])
    return pre, requested, post


def records_fixture():
    pre, requested, post = metric_fixture()
    records = []
    for mode in a.MODES:
        zero = mode in a.MODES[:2]
        before = np.zeros((5, 6))
        before[1:3, 0] = 2
        promoted = before.copy()
        promoted[2, 0] = 0
        after = promoted.copy()
        if not zero:
            after[1, 0] += -1 if mode == "suppression" else 1
        records.append({"text_id": "one", "mode": mode, "special_tokens_mask": [True, False, False, False, False],
                        "delivery": a.delivery_metrics(pre, np.zeros_like(requested) if zero else requested,
                                                        pre if zero else post),
                        "native_before": before, "promoted_before": promoted, "promoted_after": after})
    return records


def test_delivery_cosine_cancellation_and_distinct_norm_denominators():
    pre, request, post = metric_fixture()
    metrics = a.delivery_metrics(pre, request, post)
    assert metrics["requested_norm"] == [0., 5., 1., 0., 6.]
    assert metrics["realized_norm"] == [0., 5., 0., 0., 6.]
    assert metrics["cosine"] == [1., 1., 0., 1., -1.]
    assert metrics["relative_error"] == [0., 0., 1., 0., 2.]
    result, zeros = a.precision_counts(records_fixture())
    for mode in a.MODES[2:]:
        summary = result["modes"][mode]
        assert summary["fidelity"] == a.fraction_report(1, 3)
        assert summary["norm"] == a.fraction_report(1, 2)
        assert summary["norm_all_nonspecial_secondary"] == {"passing_positions": 3, "denominator": 4}
        assert summary["nonzero_requests"] == 3 and summary["zero_requests"] == 1
        assert zeros[mode] == {"zero_realized": 2, "nonzero_request_zero_realized": 1,
                               "zero_request_nonzero_realized": 0}
        feature = summary["features"][str(a.FEATURES[0])]
        assert feature["primary_eligible_native_active_positions"] == 2
        assert feature["paired_promoted_defined_positions"] == feature["paired_promoted_undefined_positions"] == 1
        assert feature["paired_promoted_after_ratio_median"] is None
        assert feature["paired_delta_over_requested_native_change_median"] == pytest.approx(1 / 3)
        assert len(summary["features"]) == 6
    for mode in a.MODES[:2]:
        summary = result["modes"][mode]
        assert summary["fidelity"] == summary["norm"] == a.fraction_report(0, 0)
        assert summary["zero_requests"] == 4


def test_zero_request_realized_edit_is_explicit_not_dropped():
    records = records_fixture()
    pre, request, post = metric_fixture()
    post[0, 3, 0] += 1
    records[2]["delivery"] = a.delivery_metrics(pre, request, post)
    result, zeros = a.precision_counts(records)
    assert zeros["suppression"]["zero_request_nonzero_realized"] == 1
    assert result["modes"]["suppression"]["norm"]["denominator"] == 3
    assert result["modes"]["suppression"]["fidelity"]["denominator"] == 3


def test_both_signed_modes_required_and_fraction_threshold_unchanged():
    with pytest.raises(ValueError, match="Missing precision mode"):
        a.precision_counts(records_fixture()[:-1])
    assert a.fraction_report(19, 20)["pass"] is True
    assert a.fraction_report(18, 20)["pass"] is False


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value) + "\n")


def tensor_fixture(tmp_path):
    evidence = a.Evidence(tmp_path)
    cert = {"token_ids": [0, 1, 2, 3, 4], "special_tokens_mask": [True, False, False, False, False]}
    pre, requested, post = metric_fixture()
    tensors = {"pre": torch.tensor(pre, dtype=torch.bfloat16), "requested": torch.tensor(requested, dtype=torch.float32),
               "post": torch.tensor(post, dtype=torch.float32), "valid": torch.tensor([[False, True, True, True, True]]),
               "token_ids": torch.tensor([cert["token_ids"]])}
    for key in ("native_before", "promoted_before", "promoted_after"):
        tensors[key] = torch.tensor(records_fixture()[2][key], dtype=torch.float32)
    path = tmp_path / "precision_pilot/tensors/000.safetensors"
    path.parent.mkdir(parents=True)
    save_file(tensors, str(path))
    clean_capture = tmp_path / "residuals/one.safetensors"
    clean_capture.parent.mkdir()
    save_file({"hidden": tensors["pre"], "token_ids": tensors["token_ids"]}, str(clean_capture))
    clean = {"id": "clean-one", "capture": {"path": "residuals/one.safetensors", "sha256": a.sha(clean_capture)},
             "activations": {str(f): tensors["native_before"][:, j].tolist() for j, f in enumerate(a.FEATURES)}}
    write_json(tmp_path / "rows/clean-one.json", clean)
    evidence.json("rows/clean-one.json")
    row = {"row_id": "precision-pilot:one:suppression", "text_id": "one", "mode": "suppression", "test_only": True,
           "special_tokens_mask": cert["special_tokens_mask"], "delivery": a.delivery_metrics(pre, requested, post),
           "capture": {"path": "tensors/000.safetensors", "sha256": a.sha(path),
                       "tensors": {k: {"shape": list(v.shape), "dtype": str(v.dtype)} for k, v in tensors.items()}},
           "clean_exposure": {"row_path": "rows/clean-one.json", "row_sha256": a.sha(tmp_path / "rows/clean-one.json"),
                              "capture_path": clean["capture"]["path"], "capture_sha256": clean["capture"]["sha256"]}}
    row.update({k: tensors[k].tolist() for k in ("native_before", "promoted_before", "promoted_after")})
    return evidence, row, clean, cert, tensors, path


def test_tensor_oracle_ignores_reported_delivery_in_calculation(tmp_path):
    evidence, row, clean, cert, _, _ = tensor_fixture(tmp_path)
    row["delivery"]["cosine"][2] = 1.
    errors = []
    result = a.tensor_record(evidence, row, clean, cert, errors)
    assert result["delivery"]["cosine"][2] == 0
    assert len(errors) == 1 and "cosine[2]" in errors[0]


@pytest.mark.parametrize("fault", ["hash", "mask", "dtype", "native_anchor"])
def test_retained_tensor_binding_failures(tmp_path, fault):
    evidence, row, clean, cert, tensors, path = tensor_fixture(tmp_path)
    if fault == "hash":
        row["capture"]["sha256"] = "0" * 64
    elif fault == "native_anchor":
        clean["activations"][str(a.FEATURES[0])][1] = 99
    else:
        if fault == "mask":
            tensors["valid"][0, 1] = False
        else:
            tensors["post"] = tensors["post"].to(torch.bfloat16)
        save_file(tensors, str(path))
        row["capture"]["sha256"] = a.sha(path)
        row["capture"]["tensors"] = {k: {"shape": list(v.shape), "dtype": str(v.dtype)} for k, v in tensors.items()}
    with pytest.raises(ValueError):
        a.tensor_record(evidence, row, clean, cert, [])


def test_summary_mismatch_and_numeric_tolerance():
    errors = []
    a.compare({"norm": a.fraction_report(1, 2)}, {"norm": a.fraction_report(3, 4)}, "summary", errors)
    assert len(errors) == 3
    errors = []
    a.compare([.95, 2, True, None], [.95 + 1e-15, 2.0, 1, 0], "fields", errors)
    assert len(errors) == 3


def test_no_scientific_imports_or_gpu_calls():
    source = Path(a.__file__).read_text()
    tree = ast.parse(source)
    modules = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    modules += [name.name for node in ast.walk(tree) if isinstance(node, ast.Import) for name in node.names]
    assert not any(name and name.startswith("experiments") for name in modules)
    assert "device=\"cpu\"" in source and ".cuda(" not in source


def test_output_must_be_new_ignored_and_outside_run(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    run = root / "raw"
    run.mkdir()
    target = root / "derived/check.json"
    with patch.object(a, "ROOT", root), patch.object(a.subprocess, "run") as command:
        command.return_value.returncode = 1
        with pytest.raises(ValueError, match="ignored"):
            a.output_path(target, run)
        command.return_value.returncode = 0
        assert a.output_path(target, run) == target
        with pytest.raises(ValueError, match="outside raw"):
            a.output_path(run / "check.json", run)
        target.parent.mkdir()
        target.write_text("preserve")
        with pytest.raises(ValueError, match="new"):
            a.output_path(target, run)
    assert target.read_text() == "preserve"


def test_missing_run_cli_records_failure_not_success(tmp_path):
    out = tmp_path / "check.json"
    with patch.object(a, "output_path", return_value=out):
        assert a.main(["--plan", str(tmp_path / "missing-plan"), "--run", str(tmp_path / "missing-run"),
                       "--freeze", "a" * 40, "--out", str(out)]) == 1
    result = json.loads(out.read_text())
    assert result["arithmetic_matches"] is False and result["incomplete_or_invalid"] is True


@pytest.fixture
def complete_run(tmp_path):
    run = tmp_path / "run"
    texts = [{"id": f"text-{i:03d}", "family": f"family-{i % 12:02d}",
              "split": "discovery" if i < 96 else "validation" if i < 192 else "representative"}
             for i in range(224)]
    tokens, mask = [9, 10, 11], [True, False, False]
    plan = {"texts": texts, "target_feature_ids": list(a.FEATURES),
            "certificate": {"items": [{"id": t["id"], "token_ids": tokens,
                                        "special_tokens_mask": mask} for t in texts]},
            "rules": {"minimum_positions_per_feature": 100, "minimum_distinct_texts_per_feature": 6,
                      "per_feature_limit": 12, "per_feature_family_cap": 6},
            "precision_pilot": {"texts": texts[:12], "modes": list(a.MODES), "change": .75,
                "fidelity": {"minimum_fraction": .95, "minimum_cosine": .95, "maximum_relative_error": .20},
                "norm": {"minimum_fraction": .95, "maximum_clean_ratio": .05}}}
    plan_path = tmp_path / "plan.json"
    write_json(plan_path, plan)
    binding = {"plan_sha256": a.sha(plan_path), "freeze_commit": "a" * 40}
    pre = torch.tensor([[[100., 0.]] * 3], dtype=torch.bfloat16)
    native = torch.zeros(3, 6)
    native[1, 0] = 1
    (run / "residuals").mkdir(parents=True)
    (run / "precision_pilot/tensors").mkdir(parents=True)
    for item in texts:
        capture = "residuals/" + item["id"] + ".safetensors"
        save_file({"hidden": pre, "token_ids": torch.tensor([tokens])}, str(run / capture))
        clean = {**binding, **item, "id": "clean-" + item["id"], "text_id": item["id"],
                 "feature_ids": list(a.FEATURES), "token_ids": tokens, "special_tokens_mask": mask,
                 "activations": {str(f): native[:, j].tolist() for j, f in enumerate(a.FEATURES)},
                 "capture": {"path": capture, "sha256": a.sha(run / capture)}}
        row_path = "rows/clean-" + item["id"] + ".json"
        write_json(run / row_path, clean)
        if item not in texts[:12]:
            continue
        for mode_index, mode in enumerate(a.MODES):
            edited = mode_index >= 2
            sign = -1 if mode == "suppression" else 1
            request = torch.zeros_like(pre, dtype=torch.float32)
            after = native.clone()
            if edited:
                request[0, 1, 0] = sign
                after[1, 0] += sign * .75
            tensors = {"pre": pre, "requested": request,
                "post": pre if mode == "native_zero" else pre.float() + request,
                "token_ids": torch.tensor([tokens]), "valid": torch.tensor([[False, True, True]]),
                "native_before": native, "promoted_before": native, "promoted_after": after,
                "native_rounded_after": after, "promoted_preact_before": native,
                "projection_coefficients": torch.zeros_like(native), "projection_scale": torch.ones(3)}
            ordinal = texts.index(item) * 4 + mode_index
            path = f"tensors/{ordinal:03d}.safetensors"
            save_file({k: v.clone() for k, v in tensors.items()}, str(run / "precision_pilot" / path))
            row = {**binding, "row_id": "precision-pilot:" + item["id"] + ":" + mode,
                "text_id": item["id"], "family": item["family"], "split": "discovery", "mode": mode,
                "feature_ids": list(a.FEATURES), "token_ids": tokens, "special_tokens_mask": mask, "test_only": True,
                "capture": {"path": path, "sha256": a.sha(run / "precision_pilot" / path),
                    "tensors": {k: {"shape": list(v.shape), "dtype": str(v.dtype)} for k, v in tensors.items()}},
                "clean_exposure": {"row_path": row_path, "row_sha256": a.sha(run / row_path),
                    "capture_path": capture, "capture_sha256": clean["capture"]["sha256"]},
                "delivery": {"requested_norm": [0., float(edited), 0.], "realized_norm": [0., float(edited), 0.],
                    "clean_norm": [100.] * 3, "nonzero_requested": [False, edited, False],
                    "identity": [True, not edited, True], "cosine": [1.] * 3,
                    "relative_error": [0.] * 3, "realized_clean_ratio": [0., .01 if edited else 0., 0.]}}
            row.update({k: tensors[k].tolist() for k in ("native_before", "promoted_before", "promoted_after")})
            write_json(run / f"precision_pilot/rows/{ordinal:03d}.json", row)
    write_json(run / "rows/qualification-live.json", {})

    def panel(size):
        return {"text_count": size, "nonspecial_positions": size * 2, "all_six_exposure_minima_met": False,
            "features": [{"feature_id": f, "active_positions": size if j == 0 else 0,
                "active_texts": size if j == 0 else 0, "active_families": 12 if j == 0 else 0,
                "exposure_minimum_met": False} for j, f in enumerate(a.FEATURES)]}
    selected = [t["id"] for t in texts[:12]]
    clean_summary = {**binding, "rows": 224, "split_counts": {"discovery": 96, "validation": 96, "representative": 32},
        "panels": {"discovery": panel(96), "validation": panel(96), "representative": panel(32)},
        "discovery": {"selected_ids": selected, "screened_panel": panel(96), "selected_panel": panel(12),
            "per_feature": [{"feature_id": f, "selected_ids": selected if j == 0 else [],
                             "unfilled_slots": 0 if j == 0 else 12} for j, f in enumerate(a.FEATURES)]},
        "exposure_minima_met": False}
    write_json(run / "summary.json", clean_summary)
    precision = {"full_model_forwards": 48, "text_count": 12, "test_only": True, "modes": {}}
    for mode_index, mode in enumerate(a.MODES):
        edited = mode_index >= 2
        fraction = {"passing_positions": 12 if edited else 0, "denominator": 12 if edited else 0,
                    "fraction": 1. if edited else None, "pass": edited}
        summary = {"all_positions": 36, "nonspecial_positions": 24, "nonzero_requests": 12 if edited else 0,
            "zero_requests": 12 if edited else 24, "fidelity": fraction, "norm": fraction,
            "norm_all_nonspecial_secondary": {"passing_positions": 24, "denominator": 24}, "features": {}}
        ratio = .25 if mode == "suppression" else 1.75 if mode == "amplification" else 1.
        for j, f in enumerate(a.FEATURES):
            summary["features"][str(f)] = {"nonspecial_denominator": 24, "native_active_positions": 12 if j == 0 else 0,
                "promoted_active_positions": 12 if j == 0 else 0, "native_active_texts": 12 if j == 0 else 0,
                "support_disagreements": 0, "readout_shift_mean": 0.,
                "primary_eligible_native_active_positions": 12 if j == 0 else 0,
                "paired_promoted_defined_positions": 12 if j == 0 else 0, "paired_promoted_undefined_positions": 0,
                "native_anchor_after_ratio_median": ratio if j == 0 else None,
                "paired_delta_over_requested_native_change_median": float(edited) if j == 0 else None,
                "paired_promoted_after_ratio_median": ratio if j == 0 else None,
                "paired_promoted_defined_only_after_ratio_median": ratio if j == 0 else None,
                "paired_promoted_fraction_median": (.75 if edited else 0.) if j == 0 else None,
                "efficacy_qualified": False}
        precision["modes"][mode] = summary
    write_json(run / "precision_pilot/summary.json", precision)
    write_json(run / "precision-pilot-summary.json", precision)
    return plan_path, run, binding["freeze_commit"]


def test_full_synthetic_run_matches_hand_calculated_summaries(complete_run):
    report = a.verify(*complete_run)
    assert report["arithmetic_matches"] and not report["mismatches"]
    assert report["clean"]["rows"] == 224
    assert report["precision"]["full_model_forwards"] == 48
    assert report["precision"]["test_only"] is True
    assert len(report["delivery_checks"]) == 48
    assert report["clean"]["exposure_minima_met"] is False


def test_complete_cli_catches_old_all_nonspecial_norm_bug(complete_run, tmp_path):
    plan, run, freeze = complete_run
    path = run / "precision_pilot/summary.json"
    summary = json.loads(path.read_text())
    summary["modes"]["suppression"]["norm"]["denominator"] = 24
    write_json(path, summary)
    out = tmp_path / "report.json"
    with patch.object(a, "output_path", return_value=out):
        assert a.main(["--plan", str(plan), "--run", str(run), "--freeze", freeze, "--out", str(out)]) == 1
    report = json.loads(out.read_text())
    assert len(report["mismatches"]) == 1
    assert "suppression.norm.denominator" in report["mismatches"][0]
