"""Explicit POST-OUTCOME CPU FP64 portability check, not a new scientific gate.

Only pilot._metrics' delivery-dictionary comparison receives tolerance. Every
other check in the frozen pilot.validate_run still executes unchanged. Run in
an isolated Python process; do not use this process-global adapter concurrently.
The ordinary validator remains exact before and after each context/call.

Read-only audit (writes only a new report outside RUN):
  python -m scripts.sae_exposure_portability --run RUN --plan PLAN --freeze SHA \
      --audit-out out/portability.json --prior-exact-audit out/final-exact-audit.json

Explicit publication/reporting adapter, without changing either script:
  with publication_adapter("out/portability-copy", prior_exact_audit=exact_path) as receipts:
      release_sae_exposure.copy_release(base, destination, plan_path, freeze)
The context writes one numbered provenance report per pilot validation and
raises if a failed adapted check was swallowed by a reporting caller. Retain
these reports alongside the original exact failure; this is not a silent pass.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from copy import deepcopy
import json
import math
from pathlib import Path
import platform
import threading

from experiments.sae_assay_precision import pilot

ROOT = Path(__file__).resolve().parents[1]
PLAN_SHA256 = "52797a6836f8f80d58a68071ffbcf473c61c205cc82de514c230407ddd5d49e9"
FREEZE = "4635849ff374d2c389f2b785e97b8c736cb02876"
RTOL = ATOL = 1e-12
FLOAT_METRICS = ("requested_norm", "realized_norm", "clean_norm", "cosine",
                 "relative_error", "realized_clean_ratio")
BOOL_METRICS = ("nonzero_requested", "identity")
EXACT_ERROR = "Raw delivery reconstruction mismatch"
_FROZEN_VALIDATE, _FROZEN_METRICS = pilot.validate_run, pilot._metrics
_AUDIT_LOCK = threading.Lock()
_ADAPTER_LOCK = threading.Lock()


class PortabilityError(ValueError):
    """Fail-closed portability rule; never permits a different scientific gate."""


def require(condition, rule):
    if not condition:
        raise PortabilityError(rule)


def classifications(delivery, special):
    """Exact per-position predicates from frozen summarize, before aggregation."""
    valid = [not value for value in special]
    requested = [a and b for a, b in zip(valid, delivery["nonzero_requested"])]
    cosine = [v >= .95 for v in delivery["cosine"]]
    error = [v <= .20 for v in delivery["relative_error"]]
    realized = [v > 0 for v in delivery["realized_norm"]]
    norm = [v <= .05 for v in delivery["realized_clean_ratio"]]
    return {"nonspecial": valid, "cosine_threshold": cosine, "relative_error_threshold": error,
            "realized_nonzero": realized, "norm_threshold": norm, "fidelity_denominator": requested,
            "zero_requests": [a and not b for a, b in zip(valid, requested)],
            "fidelity_passing": [a and b and c for a, b, c in zip(requested, cosine, error)],
            "norm_denominator": [a and b for a, b in zip(valid, realized)],
            "norm_passing": [a and b and c for a, b, c in zip(valid, realized, norm)],
            "norm_all_nonspecial_passing": [a and b for a, b in zip(valid, norm)]}


def compare_delivery(recomputed, recorded, special):
    """Float-only tolerance; types, booleans, integers and all predicates exact."""
    require(type(recorded) is dict and type(recomputed) is dict
            and set(recorded) == set(recomputed) == set(FLOAT_METRICS + BOOL_METRICS), "delivery-schema-changed")
    require(type(special) is list and all(type(v) is bool for v in special), "invalid-position-mask")
    differences = []
    for key in FLOAT_METRICS + BOOL_METRICS:
        left, right = recomputed[key], recorded[key]
        require(type(left) is list and type(right) is list and len(left) == len(right) == len(special),
                "delivery-shape-changed")
        for position, (a, b) in enumerate(zip(left, right)):
            require(type(a) is type(b), "delivery-scalar-type-changed")
            if key in BOOL_METRICS:
                require(type(a) is bool and a == b, "delivery-boolean-changed")
                continue
            require(type(a) in (float, int) and math.isfinite(a) and math.isfinite(b), "invalid-delivery-number")
            if type(a) is int:
                require(a == b, "delivery-integer-changed")
            elif a != b:
                absolute = abs(a - b)
                relative = absolute / max(abs(a), abs(b)) if max(abs(a), abs(b)) else 0.
                differences.append({"metric": key, "position": position, "recorded": b, "recomputed": a,
                                    "absolute_difference": absolute, "relative_difference": relative})
                require(math.isclose(a, b, rel_tol=RTOL, abs_tol=ATOL), "delivery-float-tolerance-exceeded")
    expected, actual = classifications(recorded, special), classifications(recomputed, special)
    require(expected == actual, "delivery-threshold-or-denominator-flip")
    return differences, {"per_position_identical": True, "classifications_sha256": pilot._hash(actual),
                         "counts": {key: sum(values) for key, values in actual.items()}}


def _authenticate(plan, plan_hash, freeze):
    require(plan_hash == PLAN_SHA256 == pilot._hash(plan) and freeze == FREEZE, "unrecognized-plan-or-freeze")
    for group in ("source_hashes", "input_hashes"):
        for name, digest in plan[group].items():
            path = ROOT / name
            require(not path.is_symlink() and path.resolve().is_relative_to(ROOT)
                    and pilot.sha(path) == digest, "frozen-source-or-input-drift")
    paths = ("scripts/sae_exposure_portability.py", "scripts/release_sae_exposure.py",
             "scripts/report_sae_exposure.py", "tests/test_sae_exposure_portability.py")
    return {**plan["source_hashes"], **{name: pilot.sha(ROOT / name) for name in paths}}


def _inventory(run):
    require(not run.is_symlink() and run.is_dir(), "invalid-run-directory")
    records = {}
    for path in sorted(run.rglob("*")):
        require(not path.is_symlink(), "symlink-in-audit-input")
        if path.is_dir():
            continue
        require(path.is_file(), "nonregular-audit-input")
        records[path.relative_to(run).as_posix()] = {"bytes": path.stat().st_size, "sha256": pilot.sha(path)}
    return records


class _ComparedMetrics(dict):
    def __init__(self, values, compare):
        super().__init__(values)
        self.compare, self.compared = compare, False

    def __eq__(self, other):
        require(not self.compared, "unexpected-repeated-delivery-comparison")
        self.compared = True
        self.compare(dict(self), other)
        return True

    def __ne__(self, other):
        return not self.__eq__(other)


def validate_run(out, plan, plan_hash, freeze, *, audit_path, prior_exact_audit=None):
    """Return the frozen result only after full validation; always retain proof."""
    run, destination = Path(out), Path(audit_path)
    require(not destination.resolve().is_relative_to(run.resolve()), "audit-output-must-be-outside-raw-run")
    require(threading.current_thread() is threading.main_thread(), "isolated-main-thread-required")
    require(_AUDIT_LOCK.acquire(blocking=False), "concurrent-or-nested-portability-audit")
    report = {"schema": "sae_exposure_portability_v1", "post_outcome": True, "portability_pass": False,
              "scope": "CPU FP64 delivery equality only; unchanged frozen validation and scientific thresholds",
              "plan_sha256": plan_hash, "freeze_commit": freeze, "rtol": RTOL, "atol": ATOL,
              "float_comparison": "abs(a-b) <= max(atol, rtol * max(abs(a), abs(b)))",
              "platform": platform.system(), "machine": platform.machine(), "torch": pilot.torch.__version__,
              "torch_cpu_threads": pilot.torch.get_num_threads(), "numpy": pilot.np.__version__,
              "original_exact_audit": {"status": "not_run"}, "differences": [], "rows": []}
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("x") as output:
            try:
                require(pilot._metrics is _FROZEN_METRICS, "metrics-already-adapted")
                report["source_hashes"] = _authenticate(plan, plan_hash, freeze)
                before = _inventory(run)
                report["inputs"] = before
                if prior_exact_audit is not None:
                    path = Path(prior_exact_audit)
                    previous = json.loads(path.read_text())
                    require(previous.get("plan_sha256") == plan_hash and previous.get("freeze_commit") == freeze
                            and previous.get("pilot_exact_audit_pass") is False
                            and previous.get("error_type") == "ValueError" and previous.get("error_message") == EXACT_ERROR,
                            "unbound-prior-exact-failure")
                    report["prior_exact_failure"] = {"sha256": pilot.sha(path), "audit": previous}
                try:
                    _FROZEN_VALIDATE(run, plan, plan_hash, freeze)
                except Exception as exc:
                    report["original_exact_audit"] = {"status": "fail", "error_type": type(exc).__name__,
                        "error_message": EXACT_ERROR if type(exc) is ValueError and str(exc) == EXACT_ERROR else None}
                    if type(exc) is not ValueError or str(exc) != EXACT_ERROR:
                        raise
                else:
                    report["original_exact_audit"] = {"status": "pass"}
                rows = [json.loads((run / pilot.DIRECTORY / f"rows/{i:03d}.json").read_text()) for i in range(48)]
                recomputed_rows, comparisons = deepcopy(rows), []

                def metrics(*args):
                    ordinal = len(comparisons)
                    require(ordinal < 48, "unexpected-delivery-call-count")
                    row = rows[ordinal]
                    def compare(actual, recorded):
                        require(pilot.canonical(recorded) == pilot.canonical(row["delivery"]), "delivery-row-order-or-input-drift")
                        differences, classification = compare_delivery(actual, recorded, row["special_tokens_mask"])
                        report["differences"].extend({"row_id": row["row_id"], **item} for item in differences)
                        report["rows"].append({"row_id": row["row_id"], "difference_count": len(differences), **classification})
                        recomputed_rows[ordinal]["delivery"] = actual
                    value = _ComparedMetrics(_FROZEN_METRICS(*args), compare)
                    comparisons.append(value)
                    return value

                pilot._metrics = metrics
                try:
                    result = _FROZEN_VALIDATE(run, plan, plan_hash, freeze)
                finally:
                    pilot._metrics = _FROZEN_METRICS
                require(len(comparisons) == 48 and all(item.compared for item in comparisons), "incomplete-delivery-validation")
                expected, actual = pilot.summarize(rows), pilot.summarize(recomputed_rows)
                require(actual == expected, "recomputed-frozen-summary-changed")
                report["mode_gates"] = {mode: {key: value for key, value in summary.items() if key in
                    {"all_positions", "nonspecial_positions", "nonzero_requests", "zero_requests", "fidelity", "norm",
                     "norm_all_nonspecial_secondary"}} for mode, summary in actual["modes"].items()}
                report["metric_differences"] = {key: {"count": sum(d["metric"] == key for d in report["differences"]),
                    "max_absolute_difference": max((d["absolute_difference"] for d in report["differences"] if d["metric"] == key), default=0.),
                    "max_relative_difference": max((d["relative_difference"] for d in report["differences"] if d["metric"] == key), default=0.)}
                    for key in FLOAT_METRICS}
                require(_inventory(run) == before, "audit-inputs-changed")
                report.update(portability_pass=True, frozen_validator_result=result, rows_checked=48,
                              rows_with_differences=sum(bool(row["difference_count"]) for row in report["rows"]),
                              exact_per_position_classifications=True, exact_recomputed_frozen_summary=True,
                              raw_inputs_unchanged=True)
                return result
            except Exception as exc:
                report["failure"] = {"error_type": type(exc).__name__,
                                     "rule": str(exc) if isinstance(exc, PortabilityError) else "frozen-validation-error"}
                raise
            finally:
                output.write(pilot.canonical(report) + "\n")
    finally:
        _AUDIT_LOCK.release()


@contextmanager
def publication_adapter(audit_dir, *, prior_exact_audit=None):
    """Explicit isolated-process wrapper for unchanged publisher/reporter calls."""
    require(threading.current_thread() is threading.main_thread(), "isolated-main-thread-required")
    require(_ADAPTER_LOCK.acquire(blocking=False), "nested-publication-adapter")
    receipts, failures = [], []
    try:
        require(pilot.validate_run is _FROZEN_VALIDATE and pilot._metrics is _FROZEN_METRICS, "validator-already-adapted")
        directory = Path(audit_dir)
        require(not directory.exists() and not directory.is_symlink(), "audit-directory-already-exists")
        def adapted(out, plan, plan_hash, freeze):
            destination = directory / f"{len(receipts):03d}.json"
            receipts.append(destination)
            try:
                require(not directory.resolve().is_relative_to(Path(out).resolve()), "audit-output-must-be-outside-raw-run")
                if len(receipts) == 1:
                    directory.mkdir(parents=True, exist_ok=False)
                return validate_run(out, plan, plan_hash, freeze, audit_path=destination,
                                    prior_exact_audit=prior_exact_audit)
            except Exception:
                failures.append(destination)
                raise
        pilot.validate_run = adapted
        try:
            yield receipts
        finally:
            pilot.validate_run = _FROZEN_VALIDATE
        require(receipts and not failures, "publication-adapter-has-unvalidated-or-failed-calls")
    finally:
        _ADAPTER_LOCK.release()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ("run", "plan", "freeze", "audit-out"):
        parser.add_argument("--" + flag, required=True)
    parser.add_argument("--prior-exact-audit")
    args = parser.parse_args(argv)
    plan = json.loads(Path(args.plan).read_text())
    try:
        validate_run(args.run, plan, pilot.sha(Path(args.plan)), args.freeze,
                     audit_path=args.audit_out, prior_exact_audit=args.prior_exact_audit)
    except Exception as exc:
        parser.exit(1, "Portability audit failed: " + type(exc).__name__ + "; retain the provenance report.\n")
    print(pilot.canonical({"portability_pass": True, "audit_sha256": pilot.sha(Path(args.audit_out)),
                           "original_exact_result_preserved": True}))


if __name__ == "__main__":
    main()
