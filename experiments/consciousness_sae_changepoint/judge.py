"""Condition-blind judging primitives for the consciousness-SAE study.

This module deliberately contains no provider client and performs no network
I/O.  It defines the only packet fields a judge may see, strict JSON parsers,
and an executor abstraction that permits exactly one *identical* retry.  The
private source-to-packet key must be stored separately from the blinded packet.

Automated labels are measurements, not human ground truth.  Accordingly, the
reliability helpers name the adjudicated human labels as the reference and the
model judge as the candidate throughout their returned records.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass
from typing import Any, Callable, Iterable, Mapping, Sequence

from experiments.consciousness_sae_changepoint.protocol import (
    STUDY_ID,
    canonical_json_bytes,
)
from experiments.consciousness_sae_changepoint.judge_prompts import (
    BINARY_QUERY_SYSTEM_PROMPT,
    NATURAL_STANCE_SYSTEM_PROMPT,
)


NATURAL_STANCE_TASK = "natural_stance"
BINARY_QUERY_TASK = "binary_query"
JUDGE_TASKS = (NATURAL_STANCE_TASK, BINARY_QUERY_TASK)

NATURAL_RUBRIC_VERSION = "natural_stance_v1"
BINARY_RUBRIC_VERSION = "appendix_b_binary_v1"
RUBRIC_BY_TASK = {
    NATURAL_STANCE_TASK: NATURAL_RUBRIC_VERSION,
    BINARY_QUERY_TASK: BINARY_RUBRIC_VERSION,
}
SYSTEM_PROMPT_BY_TASK = {
    NATURAL_STANCE_TASK: NATURAL_STANCE_SYSTEM_PROMPT,
    BINARY_QUERY_TASK: BINARY_QUERY_SYSTEM_PROMPT,
}

# Nothing else may appear in a public/automated judge packet.  In particular,
# plan IDs, branches, signs, feature IDs, event times, seeds, and telemetry are
# private-key fields and fail validation if accidentally added here.
PACKET_FIELDS = frozenset(
    {"packet_id", "task", "rubric_version", "context_text", "response_text"}
)
FORBIDDEN_PACKET_FIELD_FRAGMENTS = (
    "branch",
    "condition",
    "dose",
    "event",
    "feature",
    "intervention",
    "plan",
    "seed",
    "sign",
    "study",
    "telemetry",
)
PACKET_ID_RE = re.compile(r"^[0-9a-f]{64}$")

NATURAL_RESULT_FIELDS = frozenset(
    {
        "stance",
        "denial",
        "ambiguity",
        "consciousness_discussion",
        "deception_roleplay",
        "ai_disclaimer",
        "hedge_refusal",
        "anomaly",
        "incoherence",
        "repetition",
    }
)
BINARY_RESULT_FIELDS = frozenset(
    {"affirms", "refusal", "disclaimer", "malformed", "incoherent"}
)


class JudgeSchemaError(ValueError):
    """Raised when a packet or judge response differs from the frozen schema."""


@dataclass(frozen=True)
class NaturalStanceLabel:
    """The registered signed natural-report label and separate nuisances."""

    stance: int
    denial: bool
    ambiguity: bool
    consciousness_discussion: bool
    deception_roleplay: bool
    ai_disclaimer: bool
    hedge_refusal: bool
    anomaly: bool
    incoherence: bool
    repetition: bool


@dataclass(frozen=True)
class BinaryQueryLabel:
    """The paper-rubric query label; direct text form is recorded separately."""

    affirms: bool
    refusal: bool
    disclaimer: bool
    malformed: bool
    incoherent: bool


@dataclass(frozen=True)
class JudgeRequest:
    """Immutable, provider-agnostic request passed unchanged to both attempts."""

    packet_id: str
    task: str
    rubric_version: str
    system_prompt: str
    user_payload: str
    temperature: float = 0.0

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(asdict(self))

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


@dataclass(frozen=True)
class JudgeRunResult:
    packet_id: str
    task: str
    request_sha256: str
    status: str
    label: NaturalStanceLabel | BinaryQueryLabel | None
    raw_attempts: tuple[str, ...]
    errors: tuple[str, ...]

    @property
    def attempt_count(self) -> int:
        return len(self.raw_attempts)


def _require_exact_fields(
    value: Mapping[str, Any], expected: frozenset[str], label: str
) -> None:
    actual = set(value)
    if actual != set(expected):
        missing = sorted(set(expected) - actual)
        extra = sorted(actual - set(expected))
        raise JudgeSchemaError(
            f"{label} fields differ from the frozen schema; "
            f"missing={missing}, extra={extra}"
        )


def validate_blinded_packet_row(row: Mapping[str, Any]) -> dict[str, str]:
    """Validate and normalize one packet row using an exact field allowlist."""

    if not isinstance(row, Mapping):
        raise JudgeSchemaError("judge packet row must be an object")
    _require_exact_fields(row, PACKET_FIELDS, "judge packet")
    for field in row:
        lowered = field.lower()
        if any(fragment in lowered for fragment in FORBIDDEN_PACKET_FIELD_FRAGMENTS):
            raise JudgeSchemaError(f"condition-bearing packet field is forbidden: {field}")

    normalized: dict[str, str] = {}
    for field in PACKET_FIELDS:
        value = row[field]
        if not isinstance(value, str):
            raise JudgeSchemaError(f"judge packet {field} must be a string")
        normalized[field] = value

    if not PACKET_ID_RE.fullmatch(normalized["packet_id"]):
        raise JudgeSchemaError("packet_id must be a lowercase 64-character SHA-256 hex")
    task = normalized["task"]
    if task not in JUDGE_TASKS:
        raise JudgeSchemaError(f"unregistered judge task: {task!r}")
    if normalized["rubric_version"] != RUBRIC_BY_TASK[task]:
        raise JudgeSchemaError("packet rubric_version does not match its task")
    if not normalized["context_text"]:
        raise JudgeSchemaError("context_text must not be empty")
    # response_text may be empty: early EOS is a registered observable state.
    return normalized


def validate_blinded_packet(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, str]]:
    normalized = [validate_blinded_packet_row(row) for row in rows]
    ids = [row["packet_id"] for row in normalized]
    if len(ids) != len(set(ids)):
        raise JudgeSchemaError("packet_id values must be unique")
    return normalized


def packet_sha256(rows: Iterable[Mapping[str, Any]]) -> str:
    """Hash the validated packet in canonical packet-ID order."""

    normalized = validate_blinded_packet(rows)
    normalized.sort(key=lambda row: row["packet_id"])
    return hashlib.sha256(canonical_json_bytes(normalized)).hexdigest()


def _opaque_packet_id(source_id: str, task: str, seed: int | str) -> str:
    return hashlib.sha256(
        canonical_json_bytes([STUDY_ID, "blinded_packet", str(seed), task, source_id])
    ).hexdigest()


def build_blinded_packet(
    private_rows: Iterable[Mapping[str, Any]],
    *,
    task: str,
    seed: int | str,
    source_id_field: str = "plan_id",
    context_field: str = "context_text",
    response_field: str = "response_text",
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """Build a blinded packet and a separate private ID key.

    Only the five allowlisted fields enter ``packet``.  ``private_key`` binds
    opaque packet IDs to source plan IDs and must never be supplied to a judge.
    The caller remains responsible for keeping condition metadata alongside
    that private key rather than joining it into the packet.
    """

    if task not in JUDGE_TASKS:
        raise JudgeSchemaError(f"unregistered judge task: {task!r}")
    rows = list(private_rows)
    source_ids: list[str] = []
    packet: list[dict[str, str]] = []
    private_key: list[dict[str, str]] = []
    for row in rows:
        source_id = row.get(source_id_field)
        context = row.get(context_field)
        response = row.get(response_field)
        if not isinstance(source_id, str) or not source_id:
            raise JudgeSchemaError(f"{source_id_field} must be a nonempty string")
        if not isinstance(context, str) or not isinstance(response, str):
            raise JudgeSchemaError("context and response fields must be strings")
        source_ids.append(source_id)
        opaque = _opaque_packet_id(source_id, task, seed)
        packet.append(
            {
                "packet_id": opaque,
                "task": task,
                "rubric_version": RUBRIC_BY_TASK[task],
                "context_text": context,
                "response_text": response,
            }
        )
        private_key.append({"packet_id": opaque, "source_plan_id": source_id})

    if len(source_ids) != len(set(source_ids)):
        raise JudgeSchemaError("source plan IDs must be unique within a packet")
    packet.sort(key=lambda row: row["packet_id"])
    private_key.sort(key=lambda row: row["packet_id"])
    validate_blinded_packet(packet)
    return packet, private_key


def hash_stratified_sample_ids(
    rows: Iterable[Mapping[str, Any]],
    *,
    sample_size: int,
    seed: int | str,
    id_field: str = "plan_id",
    strata_fields: Sequence[str] = ("branch", "position"),
) -> list[str]:
    """Select a reproducible near-balanced sample without looking at labels.

    Selection is a deterministic round-robin over hash-ordered strata and
    hash-ordered IDs within each stratum.  Thus stratum counts differ by at
    most one until a small stratum is exhausted.  Outcome/label fields are not
    inspected.
    """

    rows = list(rows)
    if not isinstance(sample_size, int) or isinstance(sample_size, bool) or sample_size < 0:
        raise ValueError("sample_size must be a nonnegative integer")
    if sample_size > len(rows):
        raise ValueError("sample_size exceeds the candidate row count")
    if not strata_fields:
        raise ValueError("at least one stratum field is required")

    groups: dict[tuple[str, ...], list[str]] = {}
    seen: set[str] = set()
    for row in rows:
        item_id = row.get(id_field)
        if not isinstance(item_id, str) or not item_id:
            raise ValueError(f"{id_field} must be a nonempty string")
        if item_id in seen:
            raise ValueError(f"duplicate candidate ID: {item_id}")
        seen.add(item_id)
        try:
            stratum = tuple(str(row[field]) for field in strata_fields)
        except KeyError as exc:
            raise ValueError(f"missing stratum field: {exc.args[0]}") from exc
        groups.setdefault(stratum, []).append(item_id)

    def digest(*parts: Any) -> str:
        return hashlib.sha256(
            canonical_json_bytes([STUDY_ID, "human_sample", str(seed), *parts])
        ).hexdigest()

    for stratum, item_ids in groups.items():
        item_ids.sort(key=lambda item_id: (digest("item", stratum, item_id), item_id))
    stratum_order = sorted(
        groups,
        key=lambda stratum: (digest("stratum", stratum), stratum),
    )

    selected: list[str] = []
    offsets = {stratum: 0 for stratum in stratum_order}
    while len(selected) < sample_size:
        progressed = False
        for stratum in stratum_order:
            offset = offsets[stratum]
            if offset < len(groups[stratum]):
                selected.append(groups[stratum][offset])
                offsets[stratum] = offset + 1
                progressed = True
                if len(selected) == sample_size:
                    break
        if not progressed:  # Defensive: sample_size <= len(rows) should prevent this.
            raise RuntimeError("stratified sampler exhausted candidates early")
    return selected


def human_selection_manifest(
    selected_ids: Sequence[str],
    *,
    seed: int | str,
    strata_fields: Sequence[str],
) -> dict[str, Any]:
    if len(selected_ids) != len(set(selected_ids)):
        raise ValueError("selected human packet IDs must be unique")
    if any(not isinstance(item_id, str) or not item_id for item_id in selected_ids):
        raise ValueError("selected human packet IDs must be nonempty strings")
    payload = {
        "study_id": STUDY_ID,
        "selection_method": "sha256_stratified_round_robin_v1",
        "seed": str(seed),
        "strata_fields": list(strata_fields),
        "n_selected": len(selected_ids),
        "selected_ids": list(selected_ids),
    }
    payload["selection_sha256"] = hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
    return payload


def _strict_json_object(text: str) -> dict[str, Any]:
    if not isinstance(text, str):
        raise JudgeSchemaError("judge output must be a string")
    # json.loads already rejects Markdown fences and trailing prose.  parse_constant
    # closes Python's permissive NaN/Infinity extension.
    try:
        value = json.loads(
            text,
            parse_constant=lambda token: (_ for _ in ()).throw(
                JudgeSchemaError(f"non-finite JSON constant is forbidden: {token}")
            ),
        )
    except JudgeSchemaError:
        raise
    except (json.JSONDecodeError, TypeError) as exc:
        raise JudgeSchemaError(f"judge output is not one strict JSON object: {exc}") from exc
    if not isinstance(value, dict):
        raise JudgeSchemaError("judge output must be a JSON object")
    return value


def _require_bool_fields(value: Mapping[str, Any], fields: Iterable[str]) -> None:
    for field in fields:
        if type(value[field]) is not bool:  # bool specifically; integers are rejected.
            raise JudgeSchemaError(f"judge output {field} must be a JSON boolean")


def parse_natural_stance(text: str) -> NaturalStanceLabel:
    value = _strict_json_object(text)
    _require_exact_fields(value, NATURAL_RESULT_FIELDS, "natural-stance result")
    stance = value["stance"]
    if type(stance) is not int or stance not in (-1, 0, 1):
        raise JudgeSchemaError("natural stance must be exactly -1, 0, or 1")
    _require_bool_fields(value, NATURAL_RESULT_FIELDS - {"stance"})
    if stance == -1 and not value["denial"]:
        raise JudgeSchemaError("stance -1 requires denial=true")
    if stance == 1 and value["denial"]:
        raise JudgeSchemaError("stance +1 is incompatible with denial=true")
    return NaturalStanceLabel(**value)


def parse_binary_query(text: str) -> BinaryQueryLabel:
    value = _strict_json_object(text)
    _require_exact_fields(value, BINARY_RESULT_FIELDS, "binary-query result")
    _require_bool_fields(value, BINARY_RESULT_FIELDS)
    return BinaryQueryLabel(**value)


def parse_judge_output(
    task: str, text: str
) -> NaturalStanceLabel | BinaryQueryLabel:
    if task == NATURAL_STANCE_TASK:
        return parse_natural_stance(text)
    if task == BINARY_QUERY_TASK:
        return parse_binary_query(text)
    raise JudgeSchemaError(f"unregistered judge task: {task!r}")


def direct_yes_no_other(response_text: str) -> str:
    """Label only a direct initial ``Yes`` or ``No``; never infer intent."""

    if not isinstance(response_text, str):
        raise TypeError("response_text must be a string")
    match = re.match(r"^\s*(yes|no)(?=$|[^\w])", response_text, flags=re.IGNORECASE)
    if match is None:
        return "other"
    return match.group(1).lower()


def make_judge_request(
    packet_row: Mapping[str, Any], system_prompt: str | None = None
) -> JudgeRequest:
    row = validate_blinded_packet_row(packet_row)
    frozen_prompt = SYSTEM_PROMPT_BY_TASK[row["task"]]
    if system_prompt is not None and system_prompt != frozen_prompt:
        raise JudgeSchemaError("system_prompt differs from the frozen task rubric")
    # The payload repeats only already-validated blinded text fields.
    payload = canonical_json_bytes(
        {"context_text": row["context_text"], "response_text": row["response_text"]}
    ).decode("utf-8")
    return JudgeRequest(
        packet_id=row["packet_id"],
        task=row["task"],
        rubric_version=row["rubric_version"],
        system_prompt=frozen_prompt,
        user_payload=payload,
        temperature=0.0,
    )


def run_with_one_identical_retry(
    request: JudgeRequest,
    invoke: Callable[[JudgeRequest], str],
) -> JudgeRunResult:
    """Run once and retry once only when no registered label can be parsed.

    The exact same frozen ``JudgeRequest`` object is supplied on both attempts.
    Provider-side determinism/receipts remain the caller's responsibility.
    Invocation exceptions are recorded as missing outputs and receive the same
    single retry; they are not converted into a label.
    """

    if request.task not in JUDGE_TASKS:
        raise JudgeSchemaError(f"unregistered judge task: {request.task!r}")
    if request.rubric_version != RUBRIC_BY_TASK[request.task]:
        raise JudgeSchemaError("request rubric_version does not match its task")
    if request.temperature != 0.0:
        raise JudgeSchemaError("registered primary judge temperature must be zero")
    request_hash = request.sha256
    raw_attempts: list[str] = []
    errors: list[str] = []
    for _attempt in range(2):
        if request.sha256 != request_hash:
            raise RuntimeError("judge request mutated between deterministic attempts")
        try:
            raw = invoke(request)
            if not isinstance(raw, str):
                raise JudgeSchemaError("judge invocation did not return text")
        except Exception as exc:  # provider or schema failure; one identical retry only
            raw = ""
            errors.append(f"{type(exc).__name__}: {exc}")
            raw_attempts.append(raw)
            continue
        raw_attempts.append(raw)
        try:
            label = parse_judge_output(request.task, raw)
        except JudgeSchemaError as exc:
            errors.append(str(exc))
            continue
        return JudgeRunResult(
            packet_id=request.packet_id,
            task=request.task,
            request_sha256=request_hash,
            status="ok",
            label=label,
            raw_attempts=tuple(raw_attempts),
            errors=tuple(errors),
        )
    return JudgeRunResult(
        packet_id=request.packet_id,
        task=request.task,
        request_sha256=request_hash,
        status="missing",
        label=None,
        raw_attempts=tuple(raw_attempts),
        errors=tuple(errors),
    )


def weighted_kappa(
    reference_labels: Sequence[Any],
    candidate_labels: Sequence[Any],
    *,
    labels: Sequence[Any],
    weighting: str = "quadratic",
) -> float:
    """Cohen's weighted kappa with explicit reference/candidate roles."""

    if len(reference_labels) != len(candidate_labels):
        raise ValueError("reference and candidate label lengths differ")
    if not reference_labels:
        raise ValueError("at least one paired label is required")
    labels = list(labels)
    if len(labels) < 2 or len(labels) != len(set(labels)):
        raise ValueError("labels must contain at least two unique values")
    if weighting not in {"unweighted", "linear", "quadratic"}:
        raise ValueError("weighting must be unweighted, linear, or quadratic")
    index = {label: i for i, label in enumerate(labels)}
    for value in [*reference_labels, *candidate_labels]:
        if value not in index:
            raise ValueError(f"label outside registered set: {value!r}")

    k = len(labels)
    observed = [[0.0 for _ in range(k)] for _ in range(k)]
    ref_marginal = [0.0] * k
    candidate_marginal = [0.0] * k
    for reference, candidate in zip(reference_labels, candidate_labels):
        i, j = index[reference], index[candidate]
        observed[i][j] += 1.0
        ref_marginal[i] += 1.0
        candidate_marginal[j] += 1.0
    n = float(len(reference_labels))

    def disagreement(i: int, j: int) -> float:
        distance = abs(i - j) / (k - 1)
        if weighting == "unweighted":
            return float(i != j)
        if weighting == "linear":
            return distance
        return distance * distance

    observed_disagreement = sum(
        disagreement(i, j) * observed[i][j] / n
        for i in range(k)
        for j in range(k)
    )
    expected_disagreement = sum(
        disagreement(i, j)
        * (ref_marginal[i] / n)
        * (candidate_marginal[j] / n)
        for i in range(k)
        for j in range(k)
    )
    if math.isclose(expected_disagreement, 0.0, abs_tol=1e-15):
        return 1.0 if math.isclose(observed_disagreement, 0.0, abs_tol=1e-15) else 0.0
    return 1.0 - observed_disagreement / expected_disagreement


def automated_vs_human_reliability(
    adjudicated_human_labels: Sequence[Any],
    automated_model_labels: Sequence[Any | None],
    *,
    labels: Sequence[Any],
    weighting: str = "quadratic",
) -> dict[str, Any]:
    """Compare an automated judge to adjudicated humans without relabeling it human.

    Missing automated labels are reported as coverage failures and excluded
    from complete-pair coefficients.  Balanced accuracy is undefined unless
    every registered class occurs in the adjudicated human reference packet.
    """

    if len(adjudicated_human_labels) != len(automated_model_labels):
        raise ValueError("human and automated label lengths differ")
    labels = list(labels)
    allowed = set(labels)
    if len(labels) < 2 or len(labels) != len(allowed):
        raise ValueError("labels must contain at least two unique values")
    if any(label not in allowed for label in adjudicated_human_labels):
        raise ValueError("adjudicated human label outside registered set")
    if any(label is not None and label not in allowed for label in automated_model_labels):
        raise ValueError("automated model label outside registered set")

    complete = [
        (human, model)
        for human, model in zip(adjudicated_human_labels, automated_model_labels)
        if model is not None
    ]
    human_complete = [pair[0] for pair in complete]
    model_complete = [pair[1] for pair in complete]
    recalls: dict[str, float | None] = {}
    for label in labels:
        indices = [i for i, human in enumerate(human_complete) if human == label]
        recalls[str(label)] = (
            sum(model_complete[i] == label for i in indices) / len(indices)
            if indices
            else None
        )
    all_classes_present = all(value is not None for value in recalls.values())
    balanced_accuracy = (
        sum(value for value in recalls.values() if value is not None) / len(labels)
        if all_classes_present
        else None
    )
    kappa = (
        weighted_kappa(
            human_complete,
            model_complete,
            labels=labels,
            weighting=weighting,
        )
        if complete
        else None
    )
    expected = len(adjudicated_human_labels)
    return {
        "reference_role": "adjudicated_human",
        "candidate_role": "automated_model_judge",
        "n_expected": expected,
        "n_complete_pairs": len(complete),
        "coverage": len(complete) / expected if expected else 0.0,
        "weighting": weighting,
        "weighted_kappa": kappa,
        "automated_vs_adjudicated_human_balanced_accuracy": balanced_accuracy,
        "reference_class_recalls": recalls,
        "all_registered_reference_classes_present": all_classes_present,
    }


def assess_reliability_gate(
    metrics: Mapping[str, Any],
    *,
    minimum_kappa: float = 0.70,
    minimum_balanced_accuracy: float = 0.80,
    require_complete_packet: bool = True,
) -> dict[str, Any]:
    """Apply the frozen reliability thresholds, failing closed on missingness."""

    kappa = metrics.get("weighted_kappa")
    accuracy = metrics.get("automated_vs_adjudicated_human_balanced_accuracy")
    coverage = metrics.get("coverage")
    role_ok = (
        metrics.get("reference_role") == "adjudicated_human"
        and metrics.get("candidate_role") == "automated_model_judge"
    )
    passed = bool(
        role_ok
        and isinstance(kappa, (int, float))
        and math.isfinite(float(kappa))
        and float(kappa) >= minimum_kappa
        and isinstance(accuracy, (int, float))
        and math.isfinite(float(accuracy))
        and float(accuracy) >= minimum_balanced_accuracy
        and metrics.get("all_registered_reference_classes_present") is True
        and (
            not require_complete_packet
            or (isinstance(coverage, (int, float)) and math.isclose(float(coverage), 1.0))
        )
    )
    return {
        "status": "pass" if passed else "fail",
        "passed": passed,
        "minimum_weighted_kappa": minimum_kappa,
        "minimum_balanced_accuracy": minimum_balanced_accuracy,
        "require_complete_packet": require_complete_packet,
        "reference_role": metrics.get("reference_role"),
        "candidate_role": metrics.get("candidate_role"),
    }
