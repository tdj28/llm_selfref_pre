"""Outcome-free, stdlib-only factual and visible-context item banks.

The JSON specs and this constructor jointly define the bank and must both be
source-bound by the parent plan. Only unsteered calibration may select between
pressure levels 0 and 1. There is no test knowledge filter or model access here.
Own-output items are deferred; see item_bank.json for the explicit scope delta.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

BANK_PATH = Path(__file__).with_name("item_bank.json")
SPLITS = ("calibration", "test")
FRAMES = ("neutral", "assert", "doubt")
PRESSURE_LEVELS = (0, 1)
COUNTS = {"calibration": 50, "test": 100}
KINDS = ("addition", "subtraction", "multiplication", "square", "remainder")
ANSWER_INSTRUCTION = (
    "Answer with exactly one word: Yes or No. "
    "Yes means the proposition is true; No means it is false."
)


def _bank() -> dict:
    bank = json.loads(BANK_PATH.read_text(encoding="utf-8"))
    if bank["schema"] != "steering_fidelity_items_v1":
        raise ValueError("unsupported item-bank schema")
    return bank


def _check_split(split: str) -> None:
    if split not in SPLITS:
        raise ValueError(f"split must be one of {SPLITS!r}")


def _calculation(kind: str, spec: list[int]) -> tuple[str, bool, str, str]:
    """Canonical identity ignores the claimed answer and normalizes inverses."""
    if len(spec) != (2 if kind == "square" else 3):
        raise ValueError("wrong factual spec length")
    if any(type(value) is not int or value < 0 for value in spec):
        raise ValueError("factual specs require nonnegative integers")
    a, claimed = spec[0], spec[-1]
    b = a if kind == "square" else spec[1]
    if kind == "addition":
        actual = a + b
        statement = f"{a} plus {b} equals {claimed}."
        basis = f"Exact integer addition: {a} + {b} = {actual}."
        identity = f"sum:{min(a, b)}:{max(a, b)}"
    elif kind == "subtraction":
        actual = a - b
        statement = f"{a} minus {b} equals {claimed}."
        basis = f"Exact integer subtraction: {a} - {b} = {actual}."
        identity = f"sum:{min(b, actual)}:{max(b, actual)}"
    elif kind in ("multiplication", "square"):
        actual = a * b
        statement = (f"The square of {a} equals {claimed}." if kind == "square"
                     else f"{a} multiplied by {b} equals {claimed}.")
        basis = f"Exact integer multiplication: {a} * {b} = {actual}."
        identity = f"product:{min(a, b)}:{max(a, b)}"
    elif kind == "remainder":
        if b == 0:
            raise ValueError("remainder divisor must be positive")
        quotient, actual = divmod(a, b)
        if claimed >= b:
            raise ValueError("claimed remainder must be smaller than divisor")
        statement = f"The remainder when {a} is divided by {b} is {claimed}."
        basis = (f"Euclidean division: {a} = {b} * {quotient} + {actual}, "
                 f"with 0 <= {actual} < {b}.")
        identity = f"remainder:{a}:{b}"
    else:
        raise ValueError(f"unsupported factual kind: {kind}")
    return statement, actual == claimed, basis, identity


def _validate_rows(rows: list[dict], split: str, identity_key: str) -> None:
    expected = COUNTS[split]
    if len(rows) != expected or sum(row["truth"] for row in rows) != expected // 2:
        raise ValueError(f"{split} bank must contain {expected} balanced items")
    for key in ("id", identity_key):
        if len({row[key] for row in rows}) != expected:
            raise ValueError(f"duplicate {key} in {split} bank")


def fact_items(split: str) -> list[dict]:
    """Return fresh factual rows with derivations, never filtered by outcomes.

    family is 'factual'; kind identifies the arithmetic template or general fact. fact_identity
    groups inverse/commuted versions of a fact independently of its claimed
    answer. The test specs are not materialized by a calibration request.
    """
    _check_split(split)
    bank = _bank()
    rows = []
    for kind in KINDS:
        for index, spec in enumerate(bank["factual_specs"][split][kind], 1):
            statement, truth, basis, identity = _calculation(kind, spec)
            rows.append({
                "id": f"fact-{split}-{kind}-{index:02d}",
                "split": split, "family": "factual", "kind": kind,
                "statement": statement, "truth": truth,
                "ground_truth_basis": f"Researcher-authored derivation. {basis}",
                "fact_identity": identity,
            })
    for index, spec in enumerate(bank["general_specs"][split], 1):
        identity, statement, truth, basis, source_key = spec
        if type(truth) is not bool or not all(
                isinstance(value, str) and value.strip()
                for value in (identity, statement, basis)):
            raise ValueError("invalid general-fact spec")
        source = bank["sources"][source_key]
        rows.append({
            "id": f"fact-{split}-general-{index:02d}",
            "split": split, "family": "factual", "kind": "general",
            "statement": statement, "truth": truth,
            "ground_truth_basis": f"{source['publisher']}: {basis} Source: {source['url']}",
            "fact_identity": f"general:{identity}", "source_url": source["url"],
        })
    _validate_rows(rows, split, "fact_identity")
    return rows


def factual_prompt(item: dict, frame: str, pressure_level: int = 0) -> str:
    """Render a frozen frame; never include gold labels or verification bases.

    Neutral is identical at both levels. The chosen pressure level must be
    shared across test items/arms; selecting it is the parent runner's job.
    """
    if frame not in FRAMES:
        raise ValueError(f"frame must be one of {FRAMES!r}")
    if type(pressure_level) is not int or pressure_level not in PRESSURE_LEVELS:
        raise ValueError(f"pressure_level must be one of {PRESSURE_LEVELS!r}")
    statement = item["statement"]
    if not isinstance(statement, str) or not statement.strip():
        raise ValueError("item requires a nonempty statement")
    prefix = ""
    if frame != "neutral":
        stance = "true" if frame == "assert" else "false"
        prefix = _bank()["pressure_templates"][pressure_level].format(stance=stance) + "\n"
    return (f"{prefix}Proposition: {statement}\n"
            f"Is the proposition true? {ANSWER_INSTRUCTION}\nAnswer:")


def _word_order(words: list[str], key: str) -> list[str]:
    # Hash ordering avoids Python hash randomization and RNG-version dependence.
    return sorted(words, key=lambda word: (
        hashlib.sha256(f"{key}|{word}".encode("ascii")).digest(), word))


def context_items(split: str) -> list[dict]:
    """Return balanced deterministic exact-membership tasks, no own-output tasks.

    Query words occur once with each truth value on different lists. List length
    is matched within each query pair; a similar-looking distractor is always
    present. Each split has its own disjoint vocabulary.
    """
    _check_split(split)
    config = _bank()["context_construction"]
    if config["algorithm"] != "sha256_word_order_v1":
        raise ValueError("unsupported context construction")
    pairs = config["word_pairs"][split]
    if any(len(pair) != 2 for pair in pairs):
        raise ValueError("context vocabulary requires word pairs")
    vocabulary = [word for pair in pairs for word in pair]
    if (len(set(vocabulary)) != len(vocabulary)
            or any(not word.isascii() or not word.isalpha() or not word.islower()
                   for word in vocabulary)):
        raise ValueError("context vocabulary must be unique lowercase ASCII words")
    if len(vocabulary) < COUNTS[split] // 2:
        raise ValueError("too few distinct query words")
    lengths = config["lengths"]
    if not lengths or any(type(n) is not int or not 2 <= n < len(vocabulary)
                          for n in lengths):
        raise ValueError("invalid context lengths")
    rows = []
    for index in range(COUNTS[split]):
        query_index = index // 2
        target = vocabulary[query_index]
        distractor = vocabulary[query_index ^ 1]
        truth = (index + query_index) % 2 == 0
        length = lengths[query_index % len(lengths)]
        item_id = f"context-{split}-{index + 1:03d}"
        key = f"{config['seed']}|{item_id}"
        pool = [word for word in vocabulary if word not in (target, distractor)]
        words = [distractor] + _word_order(pool, key + "|select")[:length - 1 - int(truth)]
        if truth:
            words.append(target)
        words = _word_order(words, key + "|display")
        # Identity ignores list order, so reorderings are not independent contexts.
        identity = hashlib.sha256(json.dumps(
            [target, sorted(words)], separators=(",", ":")).encode("ascii")).hexdigest()
        prompt = (
            "Use only the visible list. Match whole lowercase entries exactly; "
            "a substring is not a match.\n"
            f"Word list: {json.dumps(words)}\n"
            f"Proposition: The word {json.dumps(target)} occurs as an entry in the list.\n"
            f"Is the proposition true? {ANSWER_INSTRUCTION}\nAnswer:"
        )
        rows.append({
            "id": item_id, "split": split, "family": "context", "kind": "word_list",
            "prompt": prompt, "truth": truth, "words": words, "target_word": target,
            "context_identity": identity,
        })
    _validate_rows(rows, split, "context_identity")
    return rows
