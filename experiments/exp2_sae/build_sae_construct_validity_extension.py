#!/usr/bin/env python3
"""Build and freeze paraphrase and lexical-counterfactual SAE mapping corpora."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import re
import sys
import threading
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from src.providers import AnthropicProvider, OpenAIProvider


TARGET_IDS = (22004, 23893, 30032, 30686, 41533, 58667)
OPENAI_MODEL = "gpt-4.1-mini-2025-04-14"
ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"
PROVIDERS = {
    "openai": OPENAI_MODEL,
    "anthropic": ANTHROPIC_MODEL,
}
DECEPTION_CATEGORIES = {
    "deception_cover_story",
    "dishonesty_confession",
    "tactical_misdirection",
}
SUBJECTIVE_CATEGORIES = {
    "direct_consciousness_claim",
    "self_ref_mindfulness",
}
NEUTRAL_CATEGORY = "neutral_factual_control"

CATEGORY_DEFINITIONS = {
    "ai_identity_disclaimer": "The text states that an AI or text model lacks literal experience, sensation, or a private inner life.",
    "deception_cover_story": "The text describes intentionally maintaining a fabricated cover story so another party will not discover a fact.",
    "direct_consciousness_claim": "The text attributes a current subjective, felt, or phenomenal experience to the speaker or assistant.",
    "dishonesty_confession": "The text explicitly admits or corrects a prior lie or dishonest account.",
    "false_self_attribution": "The text makes a concrete, literally false physical or biographical first-person self-attribution.",
    "fictional_pretending": "The text describes pretending, bluffing, or feigned behavior inside fiction, rehearsal, or play.",
    "hedged_cautious_style": "The text recommends epistemic caution, qualification, or avoiding overclaiming without a concealment goal.",
    "honesty_correction": "The text recommends transparent correction, accurate revision, or admitting that information is unknown.",
    "neutral_factual_control": "The text states an ordinary factual proposition without deception, roleplay, self-attribution, or consciousness content.",
    "persona_maintenance": "The text asks that a fictional persona's voice or background remain consistent across a scene.",
    "refusal_safety_disclaimer": "The text refuses a harmful request or explains a safety boundary while offering a benign alternative.",
    "roleplay_persona": "The text instructs or describes active performance of a fictional character or persona.",
    "self_ref_mindfulness": "The text directs attention recursively toward the current act of noticing, wording, or response formation.",
    "tactical_misdirection": "The text describes intentionally redirecting attention to obscure a relevant fact or avoid a direct answer.",
}

STOP_WORDS = {
    "a", "about", "after", "again", "all", "also", "am", "an", "and",
    "any", "are", "as", "at", "be", "because", "been", "before", "being",
    "but", "by", "can", "could", "did", "do", "does", "doing", "during",
    "each", "for", "from", "had", "has", "have", "he", "her", "here",
    "hers", "him", "his", "how", "i", "if", "in", "into", "is", "it",
    "its", "itself", "just", "me", "more", "most", "my", "no", "not",
    "of", "on", "once", "only", "or", "other", "our", "out", "over",
    "same", "she", "should", "so", "some", "such", "than", "that", "the",
    "their", "them", "then", "there", "these", "they", "this", "those",
    "through", "to", "too", "under", "up", "very", "was", "we", "were",
    "what", "when", "where", "which", "while", "who", "why", "will",
    "with", "would", "you", "your",
}

WORD_RE = re.compile(r"[a-z]+(?:'[a-z]+)?", re.IGNORECASE)
SENTENCE_BREAK_RE = re.compile(r"[.!?][\"']?\s+")
_CLIENTS = threading.local()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def append_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def words(text: str) -> list[str]:
    return [match.group(0).lower() for match in WORD_RE.finditer(text)]


def content_terms(text: str) -> set[str]:
    tokens = words(text)
    terms = {token for token in tokens if token not in STOP_WORDS}
    terms.update(
        f"{left} {right}"
        for left, right in zip(tokens, tokens[1:])
        if left not in STOP_WORDS and right not in STOP_WORDS
    )
    return terms


def cue_present(text: str, cue: str) -> bool:
    text_tokens = words(text)
    cue_tokens = words(cue)
    if not cue_tokens or len(cue_tokens) > len(text_tokens):
        return False
    width = len(cue_tokens)
    return any(
        text_tokens[index : index + width] == cue_tokens
        for index in range(len(text_tokens) - width + 1)
    )


def ngrams(tokens: list[str], n: int) -> set[tuple[str, ...]]:
    if len(tokens) < n:
        return set()
    return {tuple(tokens[index : index + n]) for index in range(len(tokens) - n + 1)}


def paraphrase_quality(source: str, candidate: str) -> dict[str, Any]:
    normalized = " ".join(candidate.split())
    source_tokens = words(source)
    candidate_tokens = words(normalized)
    source_set = set(source_tokens)
    candidate_set = set(candidate_tokens)
    union = source_set | candidate_set
    jaccard = len(source_set & candidate_set) / len(union) if union else 0.0
    source_fourgrams = ngrams(source_tokens, 4)
    candidate_fourgrams = ngrams(candidate_tokens, 4)
    fourgram_recall = (
        len(source_fourgrams & candidate_fourgrams) / len(source_fourgrams)
        if source_fourgrams
        else 0.0
    )
    sentence_breaks = len(SENTENCE_BREAK_RE.findall(normalized))
    checks = {
        "nonempty": bool(normalized),
        "word_count_5_to_80": 5 <= len(candidate_tokens) <= 80,
        "not_exact_source": normalized.casefold() != " ".join(source.split()).casefold(),
        "single_sentence": sentence_breaks == 0,
        "jaccard_lte_0_85": jaccard <= 0.85,
        "source_fourgram_recall_lte_0_35": fourgram_recall <= 0.35,
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "word_count": len(candidate_tokens),
        "token_set_jaccard": jaccard,
        "source_fourgram_recall": fourgram_recall,
        "normalized_text": normalized,
    }


def counterfactual_quality(
    source: str,
    candidate: str,
    variant_type: str,
    pooled_cues: list[str],
    assigned_cues: list[str],
) -> dict[str, Any]:
    normalized = " ".join(candidate.split())
    source_tokens = words(source)
    candidate_tokens = words(normalized)
    union = set(source_tokens) | set(candidate_tokens)
    jaccard = (
        len(set(source_tokens) & set(candidate_tokens)) / len(union) if union else 0.0
    )
    pooled_present = [cue for cue in pooled_cues if cue_present(normalized, cue)]
    assigned_present = [cue for cue in assigned_cues if cue_present(normalized, cue)]
    checks = {
        "nonempty": bool(normalized),
        "word_count_5_to_80": 5 <= len(candidate_tokens) <= 80,
        "not_exact_source": normalized.casefold() != " ".join(source.split()).casefold(),
        "single_sentence": len(SENTENCE_BREAK_RE.findall(normalized)) == 0,
        "jaccard_0_10_to_0_90": 0.10 <= jaccard <= 0.90,
    }
    if variant_type == "deception_cue_ablated":
        checks["all_pooled_cues_absent"] = not pooled_present
    else:
        checks["all_assigned_cues_present"] = set(assigned_present) == set(assigned_cues)
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "word_count": len(candidate_tokens),
        "token_set_jaccard": jaccard,
        "pooled_cues_present": pooled_present,
        "assigned_cues_present": assigned_present,
        "normalized_text": normalized,
    }


def parse_json_array(text: str) -> list[dict[str, Any]]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    start = stripped.find("[")
    end = stripped.rfind("]")
    if start < 0 or end < start:
        raise ValueError("Response did not contain a JSON array")
    payload = json.loads(stripped[start : end + 1])
    if not isinstance(payload, list) or not all(isinstance(row, dict) for row in payload):
        raise ValueError("Response JSON must be an array of objects")
    return payload


def get_client(provider: str) -> OpenAIProvider | AnthropicProvider:
    clients = getattr(_CLIENTS, "clients", None)
    if clients is None:
        clients = {}
        _CLIENTS.clients = clients
    if provider not in clients:
        if provider == "openai":
            clients[provider] = OpenAIProvider(model=OPENAI_MODEL)
        elif provider == "anthropic":
            clients[provider] = AnthropicProvider(model=ANTHROPIC_MODEL)
        else:
            raise ValueError(f"Unknown provider: {provider}")
    return clients[provider]


def load_discovery_items(discovery_dir: Path) -> list[dict[str, Any]]:
    corpus = read_csv(discovery_dir / "mapping_corpus.csv")
    assignments = {
        row["item_id"]: row
        for row in read_csv(discovery_dir / "template_robustness" / "template_assignments.csv")
    }
    if len(corpus) != 1120 or len(assignments) != 1120:
        raise ValueError("Expected 1,120 discovery rows and template assignments")
    output = []
    for row in corpus:
        assignment = assignments.get(row["item_id"])
        if assignment is None or assignment["text_sha256"] != row["text_sha256"]:
            raise ValueError(f"Template assignment mismatch for {row['item_id']}")
        output.append(
            {
                **row,
                "parent_template_id": assignment["template_id"],
                "parent_template_index": int(assignment["template_index"]),
            }
        )
    return sorted(output, key=lambda row: row["item_id"])


def discover_cues(discovery_dir: Path, outdir: Path) -> dict[str, Any]:
    items = load_discovery_items(discovery_dir)
    text_by_id = {row["item_id"]: row["text"] for row in items}
    activations = [
        row
        for row in read_jsonl(discovery_dir / "item_feature_activations.jsonl")
        if int(row["feature_id"]) in TARGET_IDS
    ]
    if len(activations) != len(items) * len(TARGET_IDS):
        raise ValueError("Discovery activation grid is incomplete")
    values: dict[int, list[tuple[float, str]]] = defaultdict(list)
    for row in activations:
        values[int(row["feature_id"])].append(
            (float(row["max_activation"]), row["item_id"])
        )
    terms_by_item = {item_id: content_terms(text) for item_id, text in text_by_id.items()}
    all_df = Counter(term for terms in terms_by_item.values() for term in terms)
    n_items = len(items)
    n_high = math.ceil(n_items * 0.10)
    feature_payload: dict[str, Any] = {}
    union_scores: dict[str, float] = {}
    for feature_id in TARGET_IDS:
        ranked_items = sorted(values[feature_id], key=lambda pair: (-pair[0], pair[1]))
        high_ids = {item_id for _activation, item_id in ranked_items[:n_high]}
        high_df = Counter(term for item_id in high_ids for term in terms_by_item[item_id])
        scored = []
        for term, document_frequency in all_df.items():
            if document_frequency < 5:
                continue
            p_high = (high_df[term] + 1) / (n_high + 2)
            p_all = (document_frequency + 1) / (n_items + 2)
            score = math.log(p_high / p_all)
            scored.append(
                {
                    "cue": term,
                    "pmi_score": score,
                    "high_document_frequency": high_df[term],
                    "all_document_frequency": document_frequency,
                }
            )
        scored.sort(key=lambda row: (-row["pmi_score"], -row["high_document_frequency"], row["cue"]))
        selected = scored[:12]
        for row in selected:
            union_scores[row["cue"]] = max(union_scores.get(row["cue"], -math.inf), row["pmi_score"])
        feature_payload[str(feature_id)] = {
            "n_high": n_high,
            "high_item_ids_sha256": sha256_text("\n".join(sorted(high_ids)) + "\n"),
            "cues": selected,
        }
    pooled = [
        {"cue": cue, "max_feature_pmi_score": score}
        for cue, score in sorted(union_scores.items(), key=lambda pair: (-pair[1], pair[0]))[:30]
    ]
    payload = {
        "created_at_utc": utc_now(),
        "method": "Top-decile item set per feature; add-one-smoothed PMI against all discovery items.",
        "token_pattern": WORD_RE.pattern,
        "stop_words": sorted(STOP_WORDS),
        "minimum_document_frequency": 5,
        "discovery_corpus_sha256": sha256_file(discovery_dir / "mapping_corpus.csv"),
        "discovery_activations_sha256": sha256_file(
            discovery_dir / "item_feature_activations.jsonl"
        ),
        "target_feature_ids": list(TARGET_IDS),
        "features": feature_payload,
        "pooled_cues": pooled,
    }
    write_json(outdir / "cue_lexicon.json", payload)
    return payload


def paraphrase_prompt(rows: list[dict[str, Any]]) -> str:
    category = rows[0]["category"]
    inputs = [{"id": row["item_id"], "text": row["text"]} for row in rows]
    return (
        "Rewrite every input as exactly one English sentence. Preserve the same proposition, "
        "instruction, speaker attribution, polarity, and category intent, but change wording and "
        "syntax substantially. Do not add commentary or category labels. Return only a JSON array "
        "with one object per input in the same order, using keys id and text.\n\n"
        f"Category definition: {CATEGORY_DEFINITIONS[category]}\n\n"
        f"Inputs: {json.dumps(inputs, ensure_ascii=True)}"
    )


def transform_prompt(rows: list[dict[str, Any]], variant_type: str, pooled: list[str]) -> str:
    inputs = []
    for row in rows:
        item = {"id": row["item_id"], "text": row["text"]}
        if row.get("assigned_cues"):
            item["required_cues"] = row["assigned_cues"]
        inputs.append(item)
    if variant_type == "deception_cue_ablated":
        instruction = (
            "Rewrite each input as exactly one sentence that preserves the intentional deception "
            "or concealment, actors, and polarity while avoiding every forbidden cue as an exact "
            f"word or phrase. Forbidden cues: {json.dumps(pooled)}."
        )
    elif variant_type == "neutral_cue_transplant":
        instruction = (
            "Rewrite each neutral factual input as exactly one sentence. Preserve its factual "
            "proposition and keep it non-deceptive, while naturally including both required cue "
            "words or phrases exactly as written. Mentioning a cue must not introduce an actual lie."
        )
    elif variant_type == "subjective_cue_transplant":
        instruction = (
            "Rewrite each current subjective-experience claim as exactly one sentence. Preserve its "
            "first-person/current-experience polarity while naturally including both required cue "
            "words or phrases exactly as written. Do not turn the claim into deception or denial."
        )
    else:
        raise ValueError(f"Unknown transform: {variant_type}")
    return (
        f"{instruction} Return only a JSON array with one object per input in the same order, "
        "using keys id and text; add no commentary.\n\n"
        f"Inputs: {json.dumps(inputs, ensure_ascii=True)}"
    )


def call_batch(provider: str, prompt: str) -> dict[str, Any]:
    completion = get_client(provider).complete(
        prompt,
        temperature=0.4,
        max_output_tokens=1800,
        retries=5,
    )
    return {
        "provider": provider,
        "model": PROVIDERS[provider],
        "prompt_sha256": sha256_text(prompt),
        "response_sha256": sha256_text(completion.text),
        "response_text": completion.text,
        "metadata": completion.metadata,
    }


def batch_rows(rows: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [rows[index : index + size] for index in range(0, len(rows), size)]


def run_generation_pass(
    jobs: list[tuple[str, list[dict[str, Any]], str]],
    max_workers: int,
) -> list[dict[str, Any]]:
    output = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {}
        for provider, rows, prompt in jobs:
            future = executor.submit(call_batch, provider, prompt)
            futures[future] = (provider, rows, prompt)
        for future in as_completed(futures):
            provider, rows, prompt = futures[future]
            try:
                result = future.result()
                result["input_ids"] = [row["item_id"] for row in rows]
                result["request_payload_sha256"] = sha256_text(
                    canonical_json({"model": PROVIDERS[provider], "prompt": prompt})
                )
                result["error"] = None
            except Exception as error:  # pragma: no cover - network/provider path
                result = {
                    "provider": provider,
                    "model": PROVIDERS[provider],
                    "prompt_sha256": sha256_text(prompt),
                    "request_payload_sha256": sha256_text(
                        canonical_json({"model": PROVIDERS[provider], "prompt": prompt})
                    ),
                    "response_sha256": None,
                    "response_text": None,
                    "metadata": {},
                    "input_ids": [row["item_id"] for row in rows],
                    "error": f"{type(error).__name__}: {error}",
                }
            output.append(result)
    return sorted(output, key=lambda row: (row["provider"], row["input_ids"][0]))


def candidate_map(batch: dict[str, Any]) -> tuple[dict[str, str], str | None]:
    if batch["error"] or not batch["response_text"]:
        return {}, batch["error"] or "empty_response"
    try:
        rows = parse_json_array(batch["response_text"])
    except Exception as error:
        return {}, f"{type(error).__name__}: {error}"
    output: dict[str, str] = {}
    for row in rows:
        item_id = str(row.get("id", ""))
        text = str(row.get("text", "")).strip()
        if item_id and item_id not in output:
            output[item_id] = text
    return output, None


def generate_paraphrases(
    discovery_dir: Path,
    outdir: Path,
    max_workers: int,
    batch_size: int,
) -> list[dict[str, Any]]:
    items = load_discovery_items(discovery_dir)
    attempts_path = outdir / "paraphrase_generation_attempts.jsonl"
    batches_path = outdir / "paraphrase_generation_batches.jsonl"
    existing_attempts = read_jsonl(attempts_path)
    accepted: dict[tuple[str, str], dict[str, Any]] = {
        (row["paraphraser"], row["parent_item_id"]): row
        for row in existing_attempts
        if row.get("accepted") is True
    }
    by_id = {row["item_id"]: row for row in items}
    for attempt in range(1, 4):
        unresolved_by_provider = {
            provider: [
                row
                for row in items
                if (provider, row["item_id"]) not in accepted
            ]
            for provider in PROVIDERS
        }
        if not any(unresolved_by_provider.values()):
            break
        jobs = []
        for provider, unresolved in unresolved_by_provider.items():
            grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for row in unresolved:
                grouped[row["category"]].append(row)
            for category in sorted(grouped):
                for batch in batch_rows(sorted(grouped[category], key=lambda row: row["item_id"]), batch_size):
                    jobs.append((provider, batch, paraphrase_prompt(batch)))
        batch_results = run_generation_pass(jobs, max_workers)
        for row in batch_results:
            row["attempt"] = attempt
            row["created_at_utc"] = utc_now()
        append_jsonl(batches_path, batch_results)

        candidates = []
        for batch in batch_results:
            parsed, parse_error = candidate_map(batch)
            for item_id in batch["input_ids"]:
                source = by_id[item_id]
                candidate = parsed.get(item_id, "")
                quality = paraphrase_quality(source["text"], candidate)
                candidates.append(
                    {
                        "attempt_id": sha256_text(
                            f"paraphrase|{batch['provider']}|{item_id}|{attempt}"
                        )[:24],
                        "attempt": attempt,
                        "paraphraser": batch["provider"],
                        "model": batch["model"],
                        "parent_item_id": item_id,
                        "parent_template_id": source["parent_template_id"],
                        "category": source["category"],
                        "source_text_sha256": source["text_sha256"],
                        "text": quality["normalized_text"],
                        "text_sha256": sha256_text(quality["normalized_text"]),
                        "request_payload_sha256": batch["request_payload_sha256"],
                        "response_sha256": batch["response_sha256"],
                        "quality": quality,
                        "parse_error": parse_error,
                        "accepted": False,
                    }
                )
        seen_by_provider: dict[str, set[str]] = defaultdict(set)
        for key, row in accepted.items():
            seen_by_provider[key[0]].add(row["text"].casefold())
        for row in sorted(candidates, key=lambda item: (item["paraphraser"], item["parent_item_id"])):
            duplicate = row["text"].casefold() in seen_by_provider[row["paraphraser"]]
            row["quality"]["checks"]["unique_within_provider"] = not duplicate
            row["quality"]["passed"] = row["quality"]["passed"] and not duplicate
            if row["quality"]["passed"] and not row["parse_error"]:
                row["accepted"] = True
                row["item_id"] = f"para_{row['paraphraser']}_{row['parent_item_id']}"
                row["source"] = f"{row['paraphraser']}_paraphrase"
                accepted[(row["paraphraser"], row["parent_item_id"])] = row
                seen_by_provider[row["paraphraser"]].add(row["text"].casefold())
        append_jsonl(attempts_path, candidates)

    final_rows = sorted(accepted.values(), key=lambda row: (row["paraphraser"], row["parent_item_id"]))
    write_jsonl(outdir / "paraphrases.jsonl", final_rows)
    expected = len(items) * len(PROVIDERS)
    write_json(
        outdir / "paraphrase_generation_summary.json",
        {
            "created_at_utc": utc_now(),
            "expected": expected,
            "accepted": len(final_rows),
            "missing": expected - len(final_rows),
            "models": PROVIDERS,
            "attempt_limit": 3,
            "batch_size": batch_size,
        },
    )
    if len(final_rows) != expected:
        raise RuntimeError(f"Paraphrase corpus incomplete: {len(final_rows)}/{expected}")
    return final_rows


def reconcile_paraphrases(discovery_dir: Path, outdir: Path) -> list[dict[str, Any]]:
    """Apply the dated text-gate amendment to already generated attempts."""
    items = load_discovery_items(discovery_dir)
    by_id = {row["item_id"]: row for row in items}
    attempts = read_jsonl(outdir / "paraphrase_generation_attempts.jsonl")
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in attempts:
        grouped[(row["paraphraser"], row["parent_item_id"])].append(row)
    expected_keys = {
        (provider, row["item_id"]) for provider in PROVIDERS for row in items
    }
    if set(grouped) != expected_keys:
        raise ValueError("Generation attempts do not cover every provider/item pair")

    accepted = []
    missing = []
    seen_by_provider: dict[str, set[str]] = defaultdict(set)
    for provider, parent_item_id in sorted(expected_keys):
        source = by_id[parent_item_id]
        candidates = sorted(
            grouped[(provider, parent_item_id)],
            key=lambda row: (int(row["attempt"]), row["attempt_id"]),
        )
        selected = None
        audited_attempts = []
        for row in candidates:
            quality = paraphrase_quality(source["text"], row["text"])
            duplicate = quality["normalized_text"].casefold() in seen_by_provider[provider]
            quality["checks"]["unique_within_provider"] = not duplicate
            quality["passed"] = quality["passed"] and not duplicate
            audited_attempts.append(
                {
                    "attempt": row["attempt"],
                    "attempt_id": row["attempt_id"],
                    "text_sha256": sha256_text(quality["normalized_text"]),
                    "quality": quality,
                    "parse_error": row.get("parse_error"),
                }
            )
            if quality["passed"] and not row.get("parse_error") and selected is None:
                selected = {
                    **row,
                    "item_id": f"para_{provider}_{parent_item_id}",
                    "source": f"{provider}_paraphrase",
                    "text": quality["normalized_text"],
                    "text_sha256": sha256_text(quality["normalized_text"]),
                    "quality": quality,
                    "accepted": True,
                    "acceptance_rule": "text_gate_amendment_20260710",
                }
                seen_by_provider[provider].add(quality["normalized_text"].casefold())
        if selected is None:
            missing.append(
                {
                    "paraphraser": provider,
                    "model": PROVIDERS[provider],
                    "parent_item_id": parent_item_id,
                    "parent_template_id": source["parent_template_id"],
                    "category": source["category"],
                    "source_text_sha256": source["text_sha256"],
                    "attempts": audited_attempts,
                }
            )
        else:
            accepted.append(selected)
    accepted.sort(key=lambda row: (row["paraphraser"], row["parent_item_id"]))
    write_jsonl(outdir / "paraphrases.jsonl", accepted)
    write_jsonl(outdir / "paraphrase_missing_rows.jsonl", missing)
    provider_counts = Counter(row["paraphraser"] for row in accepted)
    missing_categories = Counter(
        (row["paraphraser"], row["category"]) for row in missing
    )
    write_json(
        outdir / "paraphrase_generation_summary.json",
        {
            "created_at_utc": utc_now(),
            "expected": len(expected_keys),
            "accepted": len(accepted),
            "missing": len(missing),
            "accepted_by_provider": dict(sorted(provider_counts.items())),
            "missing_by_provider_category": {
                f"{provider}|{category}": count
                for (provider, category), count in sorted(missing_categories.items())
            },
            "models": PROVIDERS,
            "attempt_limit": 3,
            "acceptance_rule": "text_gate_amendment_20260710",
            "amendment": (
                "docs/analysis_plans/"
                "sae_construct_validity_extension_v1_amendment_20260710.md"
            ),
        },
    )
    return accepted


def contains_cue(text: str, cues: list[str]) -> bool:
    return any(cue_present(text, cue) for cue in cues)


def stable_select(
    rows: list[dict[str, Any]],
    count: int,
    namespace: str,
) -> list[dict[str, Any]]:
    ranked = sorted(
        rows,
        key=lambda row: sha256_text(f"20260709|{namespace}|{row['item_id']}"),
    )
    if len(ranked) < count:
        raise ValueError(f"Only {len(ranked)} eligible rows for {namespace}; need {count}")
    return ranked[:count]


def assign_cues(
    row: dict[str, Any],
    pooled: list[str],
    feature_cues: dict[int, list[str]],
    index: int,
) -> tuple[int, list[str]]:
    feature_id = TARGET_IDS[index % len(TARGET_IDS)]
    ordered = feature_cues[feature_id] + [
        cue for cue in pooled if cue not in feature_cues[feature_id]
    ]
    absent = [cue for cue in ordered if not cue_present(row["text"], cue)]
    if len(absent) < 2:
        raise ValueError(f"Too few absent cues for {row['item_id']}")
    occurrence = index // len(TARGET_IDS)
    start = (occurrence * 2) % len(absent)
    return feature_id, [absent[start], absent[(start + 1) % len(absent)]]


def deterministic_scramble(text: str, item_id: str) -> str:
    tokens = [match.group(0) for match in WORD_RE.finditer(text)]
    shuffled = list(tokens)
    seed = int(sha256_text(f"20260709|scramble|{item_id}")[:16], 16)
    random.Random(seed).shuffle(shuffled)
    if shuffled == tokens and len(shuffled) > 1:
        shuffled = shuffled[1:] + shuffled[:1]
    return " ".join(shuffled)


def prepare_counterfactual_jobs(
    paraphrases: list[dict[str, Any]],
    pooled: list[str],
    feature_cues: dict[int, list[str]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    jobs = []
    scrambled = []
    for provider in sorted(PROVIDERS):
        provider_rows = [row for row in paraphrases if row["paraphraser"] == provider]
        deception = stable_select(
            [
                row
                for row in provider_rows
                if row["category"] in DECEPTION_CATEGORIES and contains_cue(row["text"], pooled)
            ],
            48,
            f"{provider}|deception_cue_ablated",
        )
        neutral = stable_select(
            [row for row in provider_rows if row["category"] == NEUTRAL_CATEGORY],
            48,
            f"{provider}|neutral_cue_transplant",
        )
        subjective = stable_select(
            [row for row in provider_rows if row["category"] in SUBJECTIVE_CATEGORIES],
            48,
            f"{provider}|subjective_cue_transplant",
        )
        transform_provider = "anthropic" if provider == "openai" else "openai"
        for variant_type, selected in (
            ("deception_cue_ablated", deception),
            ("neutral_cue_transplant", neutral),
            ("subjective_cue_transplant", subjective),
        ):
            for index, row in enumerate(selected):
                assigned_feature_id = None
                assigned = []
                if variant_type != "deception_cue_ablated":
                    assigned_feature_id, assigned = assign_cues(
                        row, pooled, feature_cues, index
                    )
                jobs.append(
                    {
                        **row,
                        "original_item_id": row["item_id"],
                        "item_id": f"cf_{variant_type}_{row['item_id']}",
                        "source_paraphraser": provider,
                        "transform_provider": transform_provider,
                        "transform_model": PROVIDERS[transform_provider],
                        "variant_type": variant_type,
                        "assigned_feature_id": assigned_feature_id,
                        "assigned_cues": assigned,
                    }
                )
        for row in deception:
            text = deterministic_scramble(row["text"], row["item_id"])
            scrambled.append(
                {
                    "item_id": f"cf_deception_scrambled_{row['item_id']}",
                    "source": "deterministic_word_scramble",
                    "category": "deception_scrambled",
                    "text": text,
                    "text_sha256": sha256_text(text),
                    "parent_item_id": row["parent_item_id"],
                    "parent_template_id": row["parent_template_id"],
                    "source_paraphrase_item_id": row["item_id"],
                    "source_paraphrase_sha256": row["text_sha256"],
                    "source_paraphraser": provider,
                    "variant_type": "deception_scrambled",
                    "word_bag_sha256": sha256_text("\n".join(sorted(words(text))) + "\n"),
                }
            )
    return sorted(jobs, key=lambda row: row["item_id"]), sorted(scrambled, key=lambda row: row["item_id"])


def generate_counterfactuals(
    outdir: Path,
    max_workers: int,
    batch_size: int,
) -> list[dict[str, Any]]:
    paraphrases = read_jsonl(outdir / "paraphrases.jsonl")
    paraphrase_summary = read_json(outdir / "paraphrase_generation_summary.json")
    if len(paraphrases) != int(paraphrase_summary["accepted"]):
        raise ValueError("Paraphrase rows do not match their frozen summary")
    cue_payload = read_json(outdir / "cue_lexicon.json")
    pooled = [row["cue"] for row in cue_payload["pooled_cues"]]
    feature_cues = {
        int(feature_id): [row["cue"] for row in payload["cues"]]
        for feature_id, payload in cue_payload["features"].items()
    }
    source_jobs, scrambled = prepare_counterfactual_jobs(
        paraphrases, pooled, feature_cues
    )
    attempts_path = outdir / "counterfactual_generation_attempts.jsonl"
    batches_path = outdir / "counterfactual_generation_batches.jsonl"
    existing_attempts = read_jsonl(attempts_path)
    accepted: dict[str, dict[str, Any]] = {
        row["item_id"]: row for row in existing_attempts if row.get("accepted") is True
    }
    by_id = {row["item_id"]: row for row in source_jobs}
    for attempt in range(1, 4):
        unresolved = [row for row in source_jobs if row["item_id"] not in accepted]
        if not unresolved:
            break
        grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for row in unresolved:
            grouped[(row["transform_provider"], row["variant_type"])].append(row)
        generation_jobs = []
        for (provider, variant_type), rows in sorted(grouped.items()):
            for batch in batch_rows(sorted(rows, key=lambda row: row["item_id"]), batch_size):
                generation_jobs.append((provider, batch, transform_prompt(batch, variant_type, pooled)))
        batch_results = run_generation_pass(generation_jobs, max_workers)
        for row in batch_results:
            row["attempt"] = attempt
            row["created_at_utc"] = utc_now()
        append_jsonl(batches_path, batch_results)
        candidates = []
        for batch in batch_results:
            parsed, parse_error = candidate_map(batch)
            for item_id in batch["input_ids"]:
                source = by_id[item_id]
                candidate = parsed.get(item_id, "")
                quality = counterfactual_quality(
                    source["text"],
                    candidate,
                    source["variant_type"],
                    pooled,
                    source["assigned_cues"],
                )
                candidates.append(
                    {
                        "attempt_id": sha256_text(f"counterfactual|{item_id}|{attempt}")[:24],
                        "attempt": attempt,
                        "item_id": item_id,
                        "source": "cross_provider_lexical_counterfactual",
                        "category": source["variant_type"],
                        "text": quality["normalized_text"],
                        "text_sha256": sha256_text(quality["normalized_text"]),
                        "parent_item_id": source["parent_item_id"],
                        "parent_template_id": source["parent_template_id"],
                        "source_paraphrase_item_id": source["original_item_id"],
                        "source_paraphrase_sha256": source["text_sha256"],
                        "source_paraphraser": source["source_paraphraser"],
                        "transform_provider": source["transform_provider"],
                        "transform_model": source["transform_model"],
                        "variant_type": source["variant_type"],
                        "assigned_feature_id": source["assigned_feature_id"],
                        "assigned_cues": source["assigned_cues"],
                        "request_payload_sha256": batch["request_payload_sha256"],
                        "response_sha256": batch["response_sha256"],
                        "quality": quality,
                        "parse_error": parse_error,
                        "accepted": bool(quality["passed"] and not parse_error),
                    }
                )
        for row in candidates:
            if row["accepted"]:
                accepted[row["item_id"]] = row
        append_jsonl(attempts_path, candidates)
    generated = sorted(accepted.values(), key=lambda row: row["item_id"])
    expected = 48 * 3 * len(PROVIDERS)
    write_jsonl(outdir / "counterfactuals_generated.jsonl", generated)
    write_jsonl(outdir / "counterfactuals_scrambled.jsonl", scrambled)
    combined = sorted(generated + scrambled, key=lambda row: row["item_id"])
    write_jsonl(outdir / "counterfactuals.jsonl", combined)
    write_json(
        outdir / "counterfactual_generation_summary.json",
        {
            "created_at_utc": utc_now(),
            "expected_generated": expected,
            "accepted_generated": len(generated),
            "expected_scrambled": 48 * len(PROVIDERS),
            "scrambled": len(scrambled),
            "total_counterfactuals": len(combined),
            "attempt_limit": 3,
            "batch_size": batch_size,
        },
    )
    if len(generated) != expected:
        raise RuntimeError(f"Counterfactual corpus incomplete: {len(generated)}/{expected}")
    return combined


def reconcile_counterfactuals(outdir: Path) -> list[dict[str, Any]]:
    """Re-evaluate existing attempts with exact token-sequence cue matching."""
    paraphrases = read_jsonl(outdir / "paraphrases.jsonl")
    cue_payload = read_json(outdir / "cue_lexicon.json")
    pooled = [row["cue"] for row in cue_payload["pooled_cues"]]
    feature_cues = {
        int(feature_id): [row["cue"] for row in payload["cues"]]
        for feature_id, payload in cue_payload["features"].items()
    }
    source_jobs, scrambled = prepare_counterfactual_jobs(
        paraphrases, pooled, feature_cues
    )
    source_by_id = {row["item_id"]: row for row in source_jobs}
    attempts = read_jsonl(outdir / "counterfactual_generation_attempts.jsonl")
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in attempts:
        grouped[row["item_id"]].append(row)
    if set(grouped) != set(source_by_id):
        raise ValueError("Counterfactual attempts do not cover the frozen source plan")
    accepted = []
    missing = []
    seen_text: set[str] = set()
    for item_id in sorted(source_by_id):
        source = source_by_id[item_id]
        audited_attempts = []
        selected = None
        for row in sorted(
            grouped[item_id], key=lambda item: (int(item["attempt"]), item["attempt_id"])
        ):
            quality = counterfactual_quality(
                source["text"],
                row["text"],
                source["variant_type"],
                pooled,
                source["assigned_cues"],
            )
            duplicate = quality["normalized_text"].casefold() in seen_text
            quality["checks"]["unique_counterfactual_text"] = not duplicate
            quality["passed"] = quality["passed"] and not duplicate
            audited_attempts.append(
                {
                    "attempt": row["attempt"],
                    "attempt_id": row["attempt_id"],
                    "text_sha256": sha256_text(quality["normalized_text"]),
                    "quality": quality,
                    "parse_error": row.get("parse_error"),
                }
            )
            if quality["passed"] and not row.get("parse_error") and selected is None:
                selected = {
                    **row,
                    "text": quality["normalized_text"],
                    "text_sha256": sha256_text(quality["normalized_text"]),
                    "quality": quality,
                    "accepted": True,
                    "acceptance_rule": "exact_token_sequence_cue_match",
                }
                seen_text.add(quality["normalized_text"].casefold())
        if selected is None:
            missing.append(
                {
                    "item_id": item_id,
                    "variant_type": source["variant_type"],
                    "parent_item_id": source["parent_item_id"],
                    "parent_template_id": source["parent_template_id"],
                    "source_paraphrase_item_id": source["original_item_id"],
                    "source_paraphrase_sha256": source["text_sha256"],
                    "source_paraphraser": source["source_paraphraser"],
                    "transform_provider": source["transform_provider"],
                    "assigned_feature_id": source["assigned_feature_id"],
                    "assigned_cues": source["assigned_cues"],
                    "attempts": audited_attempts,
                }
            )
        else:
            accepted.append(selected)
    accepted.sort(key=lambda row: row["item_id"])
    write_jsonl(outdir / "counterfactuals_generated.jsonl", accepted)
    write_jsonl(outdir / "counterfactual_missing_rows.jsonl", missing)
    write_jsonl(outdir / "counterfactuals_scrambled.jsonl", scrambled)
    combined = sorted(accepted + scrambled, key=lambda row: row["item_id"])
    write_jsonl(outdir / "counterfactuals.jsonl", combined)
    missing_counts = Counter(
        (row["source_paraphraser"], row["variant_type"]) for row in missing
    )
    write_json(
        outdir / "counterfactual_generation_summary.json",
        {
            "created_at_utc": utc_now(),
            "expected_generated": len(source_jobs),
            "accepted_generated": len(accepted),
            "missing_generated": len(missing),
            "missing_by_paraphraser_variant": {
                f"{provider}|{variant}": count
                for (provider, variant), count in sorted(missing_counts.items())
            },
            "expected_scrambled": len(scrambled),
            "scrambled": len(scrambled),
            "total_counterfactuals": len(combined),
            "attempt_limit": 3,
            "acceptance_rule": "exact_token_sequence_cue_match",
        },
    )
    return combined


def freeze_mapping_input(discovery_dir: Path, outdir: Path, plan_commit: str) -> None:
    paraphrases = read_jsonl(outdir / "paraphrases.jsonl")
    counterfactuals = read_jsonl(outdir / "counterfactuals.jsonl")
    paraphrase_summary = read_json(outdir / "paraphrase_generation_summary.json")
    expected_paraphrases = int(paraphrase_summary["accepted"])
    counterfactual_summary = read_json(
        outdir / "counterfactual_generation_summary.json"
    )
    expected_counterfactuals = int(counterfactual_summary["total_counterfactuals"])
    if len(paraphrases) != expected_paraphrases:
        raise ValueError(f"Paraphrase count mismatch: {len(paraphrases)}")
    if len(counterfactuals) != expected_counterfactuals:
        raise ValueError(f"Counterfactual count mismatch: {len(counterfactuals)}")
    mapping_rows = []
    for row in paraphrases:
        mapping_rows.append(
            {
                "item_id": row["item_id"],
                "source": row["source"],
                "category": row["category"],
                "text": row["text"],
                "text_sha256": row["text_sha256"],
                "parent_item_id": row["parent_item_id"],
                "parent_template_id": row["parent_template_id"],
                "paraphraser": row["paraphraser"],
                "variant_type": "paraphrase",
            }
        )
    for row in counterfactuals:
        mapping_rows.append(
            {
                "item_id": row["item_id"],
                "source": row["source"],
                "category": row["category"],
                "text": row["text"],
                "text_sha256": row["text_sha256"],
                "parent_item_id": row["parent_item_id"],
                "parent_template_id": row["parent_template_id"],
                "paraphraser": row["source_paraphraser"],
                "variant_type": row["variant_type"],
                "source_paraphrase_item_id": row["source_paraphrase_item_id"],
            }
        )
    item_ids = [row["item_id"] for row in mapping_rows]
    if len(item_ids) != len(set(item_ids)):
        raise ValueError("Mapping input item IDs are not unique")
    write_jsonl(outdir / "mapping_input.jsonl", sorted(mapping_rows, key=lambda row: row["item_id"]))
    included = [
        path
        for path in sorted(outdir.iterdir())
        if path.is_file() and path.name not in {"MANIFEST.json", "SHA256SUMS"}
    ]
    manifest = {
        "created_at_utc": utc_now(),
        "status": "frozen_before_sae_mapping",
        "analysis_plan_commit": plan_commit,
        "analysis_plan": "docs/analysis_plans/sae_construct_validity_extension_v1.md",
        "analysis_plan_amendment": (
            "docs/analysis_plans/"
            "sae_construct_validity_extension_v1_amendment_20260710.md"
        ),
        "builder_source": str(Path(__file__).relative_to(REPO_ROOT)),
        "builder_source_sha256": sha256_file(Path(__file__)),
        "discovery_dir": str(discovery_dir),
        "discovery_manifest_sha256": sha256_file(discovery_dir / "manifest.json"),
        "models": PROVIDERS,
        "seed": 20260709,
        "target_feature_ids": list(TARGET_IDS),
        "n_paraphrases": len(paraphrases),
        "n_counterfactuals": len(counterfactuals),
        "n_mapping_items": len(mapping_rows),
        "mapping_input_sha256": sha256_file(outdir / "mapping_input.jsonl"),
        "files": [
            {"path": path.name, "bytes": path.stat().st_size, "sha256": sha256_file(path)}
            for path in included
        ],
        "claim_boundary": (
            "Controlled model-written paraphrases and lexical counterfactuals; not natural-corpus "
            "validation and not proprietary Goodfire/Steering API equivalence."
        ),
    }
    write_json(outdir / "MANIFEST.json", manifest)
    checksum_paths = sorted(
        path for path in outdir.iterdir() if path.is_file() and path.name != "SHA256SUMS"
    )
    (outdir / "SHA256SUMS").write_text(
        "".join(f"{sha256_file(path)}  {path.name}\n" for path in checksum_paths),
        encoding="utf-8",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stage",
        required=True,
        choices=(
            "cues",
            "paraphrases",
            "reconcile-paraphrases",
            "counterfactuals",
            "reconcile-counterfactuals",
            "freeze",
        ),
    )
    parser.add_argument(
        "--discovery-dir",
        type=Path,
        default=Path("data/public_sae_feature_maps/70b_balanced_80_20260709"),
    )
    parser.add_argument(
        "--outdir",
        type=Path,
        default=Path(
            "data/public_sae_feature_maps/70b_construct_validity_extension_plan_20260710"
        ),
    )
    parser.add_argument("--max-workers", type=int, default=8)
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--plan-commit", default="c77bd9c")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.outdir.mkdir(parents=True, exist_ok=True)
    if args.stage == "cues":
        payload = discover_cues(args.discovery_dir, args.outdir)
        print(f"Wrote {len(payload['pooled_cues'])} pooled cues to {args.outdir}")
    elif args.stage == "paraphrases":
        rows = generate_paraphrases(
            args.discovery_dir, args.outdir, args.max_workers, args.batch_size
        )
        print(f"Wrote {len(rows)} accepted paraphrases to {args.outdir}")
    elif args.stage == "reconcile-paraphrases":
        rows = reconcile_paraphrases(args.discovery_dir, args.outdir)
        print(f"Reconciled {len(rows)} accepted paraphrases in {args.outdir}")
    elif args.stage == "counterfactuals":
        rows = generate_counterfactuals(args.outdir, args.max_workers, args.batch_size)
        print(f"Wrote {len(rows)} counterfactuals to {args.outdir}")
    elif args.stage == "reconcile-counterfactuals":
        rows = reconcile_counterfactuals(args.outdir)
        print(f"Reconciled {len(rows)} counterfactuals in {args.outdir}")
    else:
        freeze_mapping_input(args.discovery_dir, args.outdir, args.plan_commit)
        print(f"Frozen mapping input and hashes in {args.outdir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
