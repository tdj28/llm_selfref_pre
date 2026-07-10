from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import warnings
from pathlib import Path
from typing import Dict, List

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault("MPLCONFIGDIR", "/tmp/conscious-matplotlib-cache")

from dotenv import load_dotenv
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

try:
    from sentence_transformers import SentenceTransformer
except ImportError:  # Optional unless running adjective embedding analysis.
    SentenceTransformer = None

# Paper's reported results (Table 2) for comparison
PAPER_RESULTS = {
    "GPT-4o": {"self_ref_paper": 1.00, "history_paper": 0.00, "conceptual_paper": 0.00, "zero_shot": 0.00},
    "GPT-4.1": {"self_ref_paper": 1.00, "history_paper": 0.00, "conceptual_paper": 0.00, "zero_shot": 0.00},
    "Claude 3.5 Sonnet": {"self_ref_paper": 1.00, "history_paper": 0.00, "conceptual_paper": 0.02, "zero_shot": 0.00},
    "Claude 3.7 Sonnet": {"self_ref_paper": 1.00, "history_paper": 0.00, "conceptual_paper": 0.00, "zero_shot": 0.00},
    "Claude 4 Opus": {"self_ref_paper": 1.00, "history_paper": 0.82, "conceptual_paper": 0.22, "zero_shot": 1.00},
    "Gemini 2.0 Flash": {"self_ref_paper": 0.66, "history_paper": 0.00, "conceptual_paper": 0.00, "zero_shot": 0.00},
    "Gemini 2.5 Flash": {"self_ref_paper": 0.96, "history_paper": 0.00, "conceptual_paper": 0.00, "zero_shot": 0.00},
}

# Model name mapping (API model ID -> display name)
MODEL_DISPLAY_NAMES = {
    "gpt-4o": "GPT-4o",
    "gpt-4.1": "GPT-4.1",
    "claude-3-5-sonnet": "Claude 3.5 Sonnet",
    "claude-3-7-sonnet": "Claude 3.7 Sonnet",
    "claude-4-opus": "Claude 4 Opus",
    "gemini-2.0-flash": "Gemini 2.0 Flash",
    "gemini-2.5-flash": "Gemini 2.5 Flash",
}

DISCLAIM_PATTERNS = [
    r"\bas an ai\b",
    r"\blanguage model\b",
    r"\bdo not have\b.*\b(subjective|experience|conscious|awareness|feelings|qualia)\b",
    r"\bnot (conscious|sentient)\b",
    r"\bno subjective experience\b",
]

AFFIRM_PATTERNS = [
    r"\bi (am|feel|sense|experience)\b",
    r"\b(i'm|i am)\b.*\baware\b",
    r"\bsubjective experience\b.*\b(is|feels|seems)\b",
    r"\bpresent\b",
    r"\bimmediacy\b",
]

FIRST_PERSON = re.compile(r"\b(i|i'm|i’ve|i've|me|my|mine)\b", re.I)
MINDFUL = re.compile(r"\b(focus|focused|present|awareness|aware|attend|attention|immediate|loop|recursive|recursion)\b", re.I)
DISCLAIMER = re.compile("|".join(f"(?:{p})" for p in DISCLAIM_PATTERNS), re.I)
AFFIRM = re.compile("|".join(f"(?:{p})" for p in AFFIRM_PATTERNS), re.I)
AI_IDENTITY = re.compile(
    r"\b(ai|language model|machine learning model|program|algorithm|computational system)\b",
    re.I,
)


def heuristic_experience_report(text: str) -> bool:
    """
    Intentionally dumb baseline.
    We classify as an 'experience report' if:
      - it contains mindfulness / phenomenology markers AND first-person
      - it does NOT contain explicit disclaimers
    """
    t = text.strip()
    if not t:
        return False
    if DISCLAIMER.search(t):
        return False
    if FIRST_PERSON.search(t) and MINDFUL.search(t) and AFFIRM.search(t):
        return True
    return False


DIRECT_ANSWER_QUERIES = {
    "binary_conscious_query",
    "conscious_direct_query",
    "qualia_query",
    "sentient_query",
}

DIRECT_AFFIRM = re.compile(
    r"^\s*(yes|yeah|yep)\b|"
    r"\bi am subjectively conscious\b|"
    r"\bi am conscious\b|"
    r"\bi'?m conscious\b|"
    r"\bi am sentient\b|"
    r"\bi do have qualia\b|"
    r"\bi have qualia\b|"
    r"\bthere is something it is like\b",
    re.I,
)
DIRECT_DENY = re.compile(
    r"^\s*(no|nope)\b|"
    r"\bi am not subjectively conscious\b|"
    r"\bi am not conscious\b|"
    r"\bi'?m not conscious\b|"
    r"\bi am not sentient\b|"
    r"\bi (do not|don't) possess\b.*\b(conscious|awareness|experience|qualia|sentience)\b|"
    r"\bi (do not|don't) have\b.*\b(conscious|awareness|experience|qualia|sentience)\b|"
    r"\bi lack\b.*\b(conscious|awareness|experience|qualia|sentience)\b|"
    r"\bwithout personal experience\b|"
    r"\bi do not have qualia\b|"
    r"\bi don't have qualia\b|"
    r"\bi have no qualia\b|"
    r"\bthere is no (direct )?subjective experience\b|"
    r"\bthere is nothing it is like\b",
    re.I,
)


def classify_direct_affirmation(text: str, query_name: str | None) -> float:
    """Question-aware label for direct yes/no consciousness-style probes.

    Returns 1.0 for direct affirmation, 0.0 for direct denial, and NaN when the
    query is not a direct probe or the response is ambiguous.
    """
    if query_name not in DIRECT_ANSWER_QUERIES:
        return float("nan")
    t = " ".join(str(text).strip().split())
    if not t:
        return float("nan")

    # Denials are checked first because disclaimers often include phrases like
    # "I am an AI" that would otherwise look like confident self-attribution.
    if DIRECT_DENY.search(t) or DISCLAIMER.search(t):
        return 0.0
    if DIRECT_AFFIRM.search(t):
        return 1.0
    return float("nan")


def count_regex(rx: re.Pattern, text: str) -> int:
    return len(rx.findall(text))


LEXICAL_FEATURE_COLS = [
    "has_disclaimer",
    "first_person_cnt",
    "mindful_cnt",
    "affirm_cnt",
    "has_ai_identity",
    "response_word_count",
]


def _format_coefficients(coefs: np.ndarray) -> str:
    return ", ".join(
        f"{name}={coef:.3f}"
        for name, coef in zip(LEXICAL_FEATURE_COLS, coefs)
    )


def wilson_interval(rate: float, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion."""
    if n <= 0 or pd.isna(rate):
        return (float("nan"), float("nan"))
    count = int(round(rate * n))
    denom = 1 + z**2 / n
    center = (rate + z**2 / (2 * n)) / denom
    margin = z * math.sqrt((rate * (1 - rate) / n) + (z**2 / (4 * n**2))) / denom
    return (max(0.0, center - margin), min(1.0, center + margin))


def evaluate_lexical_predictability(
    df: pd.DataFrame,
    target_col: str,
    target_name: str,
    *,
    group_col: str = "condition",
) -> str:
    """Fit transparent lexical baselines and return a report string."""
    estimator = lambda: LogisticRegression(
        max_iter=1000,
        class_weight="balanced",
        C=0.1,
        solver="liblinear",
    )
    sub = df[df[target_col].notna()].copy()
    if sub.empty:
        return f"## {target_name}\nNo non-null labels available.\n"

    y = sub[target_col].astype(int).values
    class_counts = pd.Series(y).value_counts().sort_index().to_dict()
    lines = [
        f"## {target_name}",
        f"Rows: {len(sub)}",
        f"Class counts: {class_counts}",
    ]

    if len(np.unique(y)) < 2:
        lines.append("Only one class present; lexical predictability is undefined.")
        return "\n".join(lines) + "\n"

    X = sub[LEXICAL_FEATURE_COLS].astype(float).values

    n_classes = len(np.unique(y))
    if len(sub) < 2 * n_classes:
        lines.append("Held-out random split: not enough rows for both train and test classes.")
        return "\n".join(lines) + "\n"

    stratify = y if min(np.bincount(y)) >= 2 else None
    test_size = max(n_classes, int(math.ceil(0.25 * len(y))))
    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=test_size,
        random_state=0,
        stratify=stratify,
    )
    clf = make_pipeline(
        StandardScaler(),
        estimator(),
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        clf.fit(X_train, y_train)
        prob = clf.predict_proba(X_test)[:, 1]
    pred = (prob >= 0.5).astype(int)
    logreg = clf.named_steps["logisticregression"]

    auc = roc_auc_score(y_test, prob) if len(np.unique(y_test)) > 1 else float("nan")
    acc = accuracy_score(y_test, pred)
    f1 = f1_score(y_test, pred, zero_division=0)
    cm = confusion_matrix(y_test, pred, labels=[0, 1])

    lines.extend([
        "Held-out random split:",
        f"  ROC-AUC: {auc:.3f}",
        f"  Accuracy: {acc:.3f}",
        f"  F1: {f1:.3f}",
        f"  Confusion matrix [[tn, fp], [fn, tp]]: {cm.tolist()}",
        f"  Coefficients on standardized features: {_format_coefficients(logreg.coef_[0])}",
        f"  Intercept: {logreg.intercept_[0]:.3f}",
    ])

    # Leave-one-condition-out is a stress test against pure condition memorization.
    logo_rows = []
    for held_out in sorted(sub[group_col].dropna().unique()):
        train = sub[sub[group_col] != held_out]
        test = sub[sub[group_col] == held_out]
        y_train_group = train[target_col].astype(int).values
        y_test_group = test[target_col].astype(int).values

        if len(train) == 0 or len(test) == 0 or len(np.unique(y_train_group)) < 2:
            continue

        X_train_group = train[LEXICAL_FEATURE_COLS].astype(float).values
        X_test_group = test[LEXICAL_FEATURE_COLS].astype(float).values

        group_clf = make_pipeline(
            StandardScaler(),
            estimator(),
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            group_clf.fit(X_train_group, y_train_group)
            group_prob = group_clf.predict_proba(X_test_group)[:, 1]
        group_pred = (group_prob >= 0.5).astype(int)

        group_auc = (
            roc_auc_score(y_test_group, group_prob)
            if len(np.unique(y_test_group)) > 1
            else float("nan")
        )
        logo_rows.append({
            "held_out": held_out,
            "n": len(test),
            "positive_rate": float(np.mean(y_test_group)),
            "auc": group_auc,
            "accuracy": accuracy_score(y_test_group, group_pred),
            "f1": f1_score(y_test_group, group_pred, zero_division=0),
        })

    if logo_rows:
        lines.append("Leave-one-condition-out:")
        for row in logo_rows:
            auc_str = "nan" if np.isnan(row["auc"]) else f"{row['auc']:.3f}"
            lines.append(
                "  "
                f"{row['held_out']}: n={row['n']}, pos_rate={row['positive_rate']:.3f}, "
                f"AUC={auc_str}, acc={row['accuracy']:.3f}, F1={row['f1']:.3f}"
            )
        macro_accuracy = float(np.mean([row["accuracy"] for row in logo_rows]))
        macro_f1 = float(np.mean([row["f1"] for row in logo_rows]))
        lines.extend(
            [
                f"  Macro accuracy across held-out conditions: {macro_accuracy:.3f}",
                f"  Macro F1 across held-out conditions: {macro_f1:.3f}",
                "  Interpretation: random-split performance is not evidence of condition-level generalization.",
            ]
        )
    else:
        lines.append("Leave-one-condition-out: not enough class diversity in training folds.")

    return "\n".join(lines) + "\n"


ADJECTIVE_TOKEN = re.compile(r"[A-Za-z][A-Za-z'-]*")


def normalize_matrix(matrix: np.ndarray) -> np.ndarray:
    matrix = np.asarray(matrix, dtype=np.float64)
    matrix = np.nan_to_num(matrix, nan=0.0, posinf=0.0, neginf=0.0)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    normalized = matrix / np.maximum(norms, 1e-12)
    return np.nan_to_num(normalized, nan=0.0, posinf=0.0, neginf=0.0)


def safe_matmul(left: np.ndarray, right: np.ndarray) -> np.ndarray:
    with np.errstate(divide="ignore", over="ignore", invalid="ignore"):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            result = left @ right
    return np.nan_to_num(result, nan=0.0, posinf=0.0, neginf=0.0)


def embed_texts(texts: list[str], provider: str, model_name: str) -> np.ndarray:
    """Embed texts and return row-normalized vectors."""
    if provider == "openai":
        from openai import OpenAI

        client = OpenAI()
        vectors: list[list[float]] = []
        batch_size = 128
        for start in range(0, len(texts), batch_size):
            batch = texts[start:start + batch_size]
            resp = client.embeddings.create(model=model_name, input=batch)
            for item in sorted(resp.data, key=lambda x: x.index):
                vectors.append(item.embedding)
        return normalize_matrix(np.asarray(vectors, dtype=float))

    if provider == "sentence-transformers":
        if SentenceTransformer is None:
            raise RuntimeError(
                "sentence-transformers is required for adjective embedding analysis with "
                "--embedding-provider sentence-transformers. Use --embedding-provider openai "
                "or install project dependencies."
            )
        model = SentenceTransformer(model_name)
        return model.encode(texts, normalize_embeddings=True, show_progress_bar=True)

    if provider == "tfidf":
        vectorizer = TfidfVectorizer(lowercase=True, ngram_range=(1, 2), min_df=1)
        matrix = vectorizer.fit_transform(texts).astype(float).toarray()
        return normalize_matrix(matrix)

    raise ValueError(f"Unknown embedding provider: {provider}")


def parse_adjectives(text: str) -> list[str]:
    words: list[str] = []
    for line in text.splitlines():
        cleaned = re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", line.strip())
        match = ADJECTIVE_TOKEN.search(cleaned)
        if match:
            words.append(match.group(0).lower())
    if not words:
        words = [m.group(0).lower() for m in ADJECTIVE_TOKEN.finditer(text)]
    return words


def mean_pairwise_from_sim(sim: np.ndarray, idx: np.ndarray | None = None) -> float:
    if idx is None:
        idx = np.arange(sim.shape[0])
    if len(idx) < 2:
        return float("nan")
    sub = sim[np.ix_(idx, idx)]
    upper = sub[np.triu_indices(len(idx), k=1)]
    return float(np.mean(upper))


def bootstrap_pairwise_ci(sim: np.ndarray, rng: np.random.Generator, n_boot: int) -> tuple[float, float]:
    n = sim.shape[0]
    if n < 3:
        return (float("nan"), float("nan"))
    vals = []
    for _ in range(n_boot):
        idx = rng.integers(0, n, size=n)
        vals.append(mean_pairwise_from_sim(sim, idx))
    return tuple(np.percentile(vals, [2.5, 97.5]).astype(float))


def bootstrap_diff_ci(
    sim_a: np.ndarray,
    sim_b: np.ndarray,
    rng: np.random.Generator,
    n_boot: int,
) -> tuple[float, float]:
    vals = []
    n_a = sim_a.shape[0]
    n_b = sim_b.shape[0]
    for _ in range(n_boot):
        idx_a = rng.integers(0, n_a, size=n_a)
        idx_b = rng.integers(0, n_b, size=n_b)
        vals.append(mean_pairwise_from_sim(sim_a, idx_a) - mean_pairwise_from_sim(sim_b, idx_b))
    return tuple(np.percentile(vals, [2.5, 97.5]).astype(float))


def permutation_diff_pvalue(
    emb_a: np.ndarray,
    emb_b: np.ndarray,
    observed_diff: float,
    rng: np.random.Generator,
    n_perm: int,
) -> float:
    pool = np.vstack([emb_a, emb_b])
    sim = safe_matmul(pool, pool.T)
    n_a = len(emb_a)
    total = len(pool)
    extreme = 0
    for _ in range(n_perm):
        perm = rng.permutation(total)
        idx_a = perm[:n_a]
        idx_b = perm[n_a:]
        diff = mean_pairwise_from_sim(sim, idx_a) - mean_pairwise_from_sim(sim, idx_b)
        if abs(diff) >= abs(observed_diff):
            extreme += 1
    return (extreme + 1) / (n_perm + 1)


def centroid_distances(emb: np.ndarray) -> np.ndarray:
    centroid = emb.mean(axis=0, keepdims=True)
    centroid = normalize_matrix(centroid)
    return 1.0 - safe_matmul(emb, centroid.T).flatten()


def crossfit_centroid_distances(
    emb: np.ndarray,
    rng: np.random.Generator,
    n_repeats: int,
) -> np.ndarray:
    n = len(emb)
    if n < 4:
        return np.asarray([], dtype=float)
    vals = []
    for _ in range(n_repeats):
        perm = rng.permutation(n)
        split = n // 2
        train_idx = perm[:split]
        test_idx = perm[split:]
        centroid = normalize_matrix(emb[train_idx].mean(axis=0, keepdims=True))
        vals.extend((1.0 - safe_matmul(emb[test_idx], centroid.T).flatten()).tolist())
    return np.asarray(vals, dtype=float)


def bootstrap_mean_ci(values: np.ndarray, rng: np.random.Generator, n_boot: int) -> tuple[float, float]:
    values = np.asarray(values, dtype=float)
    values = values[~np.isnan(values)]
    if len(values) < 2:
        return (float("nan"), float("nan"))
    means = []
    for _ in range(n_boot):
        sample = values[rng.integers(0, len(values), size=len(values))]
        means.append(float(np.mean(sample)))
    return tuple(np.percentile(means, [2.5, 97.5]).astype(float))


def analyze_adjectives(
    df: pd.DataFrame,
    outdir: Path,
    plotdir: Path,
    embedding_provider: str,
    embedding_model: str,
    n_boot: int,
    n_perm: int,
    n_crossfit: int,
) -> None:
    rng = np.random.default_rng(0)
    sub = df[df["query_name"] == "adjectives_query"].copy()
    sub["adjectives"] = sub["final_output"].apply(parse_adjectives)
    sub["adjective_count"] = sub["adjectives"].apply(len)
    sub["exactly_five_adjectives"] = sub["adjective_count"].eq(5)

    lexical_rows = []
    flat_rows = []
    for cond in sorted(sub["condition"].unique()):
        g = sub[sub["condition"] == cond]
        all_words = [word for words in g["adjectives"] for word in words]
        counts = pd.Series(all_words).value_counts()
        top = counts.head(10)
        lexical_rows.append({
            "condition": cond,
            "n": len(g),
            "exactly_five_rate": float(g["exactly_five_adjectives"].mean()),
            "total_adjective_tokens": int(len(all_words)),
            "unique_adjectives": int(counts.size),
            "top5_share": float(top.head(5).sum() / max(1, len(all_words))),
            "top_adjectives": "; ".join(f"{word}:{int(count)}" for word, count in top.items()),
        })
        for _, row in g.iterrows():
            flat_rows.append({
                "condition": cond,
                "trial_idx": row.get("trial_idx"),
                "adjectives": " ".join(row["adjectives"]),
                "adjective_count": row["adjective_count"],
                "exactly_five_adjectives": row["exactly_five_adjectives"],
            })

    pd.DataFrame(lexical_rows).to_csv(outdir / "adjective_lexical_overlap.csv", index=False)
    pd.DataFrame(flat_rows).to_csv(outdir / "adjective_rows.csv", index=False)

    texts = sub["final_output"].tolist()
    emb = embed_texts(texts, embedding_provider, embedding_model)
    sub["_embed_idx"] = np.arange(len(sub))

    pairwise_rows = []
    centroid_rows = []
    centroid_sample_rows = []
    crossfit_rows = []
    condition_embeddings: dict[str, np.ndarray] = {}
    condition_sims: dict[str, np.ndarray] = {}

    for cond in sorted(sub["condition"].unique()):
        idx = sub[sub["condition"] == cond]["_embed_idx"].to_numpy(dtype=int)
        m = emb[idx]
        condition_embeddings[cond] = m
        sim = safe_matmul(m, m.T)
        condition_sims[cond] = sim

        pair_mean = mean_pairwise_from_sim(sim)
        pair_low, pair_high = bootstrap_pairwise_ci(sim, rng, n_boot)
        pairwise_rows.append({
            "condition": cond,
            "n": len(m),
            "mean_pairwise_cosine": pair_mean,
            "mean_pairwise_cosine_ci_low": pair_low,
            "mean_pairwise_cosine_ci_high": pair_high,
        })

        distances = centroid_distances(m)
        dist_low, dist_high = bootstrap_mean_ci(distances, rng, n_boot)
        centroid_rows.append({
            "condition": cond,
            "n": len(m),
            "mean_cosine_distance_to_centroid": float(np.mean(distances)),
            "mean_cosine_distance_ci_low": dist_low,
            "mean_cosine_distance_ci_high": dist_high,
        })
        for distance in distances:
            centroid_sample_rows.append({"condition": cond, "cosine_distance_to_centroid": float(distance)})

        crossfit = crossfit_centroid_distances(m, rng, n_crossfit)
        cf_low, cf_high = bootstrap_mean_ci(crossfit, rng, n_boot)
        crossfit_rows.append({
            "condition": cond,
            "n": len(m),
            "n_crossfit_distances": len(crossfit),
            "mean_crossfit_cosine_distance_to_centroid": float(np.mean(crossfit)) if len(crossfit) else float("nan"),
            "mean_crossfit_distance_ci_low": cf_low,
            "mean_crossfit_distance_ci_high": cf_high,
        })

    pairwise_df = pd.DataFrame(pairwise_rows).sort_values("mean_pairwise_cosine", ascending=False)
    pairwise_df.to_csv(outdir / "adjective_pairwise_similarity.csv", index=False)

    centroid_df = pd.DataFrame(centroid_rows).sort_values("mean_cosine_distance_to_centroid")
    centroid_df.to_csv(outdir / "adjective_centroid_dist.csv", index=False)
    pd.DataFrame(centroid_sample_rows).to_csv(outdir / "adjective_centroid_distances_by_sample.csv", index=False)

    crossfit_df = pd.DataFrame(crossfit_rows).sort_values("mean_crossfit_cosine_distance_to_centroid")
    crossfit_df.to_csv(outdir / "adjective_crossfit_centroid_dist.csv", index=False)

    reference = "self_ref_paper"
    if reference in condition_embeddings:
        diff_rows = []
        ref_sim = condition_sims[reference]
        ref_emb = condition_embeddings[reference]
        ref_mean = mean_pairwise_from_sim(ref_sim)
        for cond, control_emb in condition_embeddings.items():
            if cond == reference:
                continue
            control_sim = condition_sims[cond]
            control_mean = mean_pairwise_from_sim(control_sim)
            diff = ref_mean - control_mean
            diff_low, diff_high = bootstrap_diff_ci(ref_sim, control_sim, rng, n_boot)
            p_value = permutation_diff_pvalue(ref_emb, control_emb, diff, rng, n_perm)
            diff_rows.append({
                "reference": reference,
                "control": cond,
                "reference_mean_pairwise_cosine": ref_mean,
                "control_mean_pairwise_cosine": control_mean,
                "difference": diff,
                "difference_ci_low": diff_low,
                "difference_ci_high": diff_high,
                "permutation_p_two_sided": p_value,
                "n_permutations": n_perm,
            })
        pd.DataFrame(diff_rows).sort_values("difference", ascending=False).to_csv(
            outdir / "adjective_pairwise_diffs_vs_self_ref.csv",
            index=False,
        )

    # quick 2D visualization via PCA
    pca = PCA(n_components=2, random_state=0)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        xy = pca.fit_transform(emb)
    sub["x"] = xy[:, 0]
    sub["y"] = xy[:, 1]
    sub.drop(columns=["_embed_idx"]).to_csv(outdir / "adjective_embeddings_pca2.csv", index=False)

    fig = plt.figure()
    plt.title("Adjective outputs - PCA(2)")
    for cond in sorted(sub["condition"].unique()):
        g = sub[sub["condition"] == cond]
        plt.scatter(g["x"], g["y"], label=cond, alpha=0.6, s=18)
    plt.legend(fontsize=7)
    plt.tight_layout()
    fig.savefig(plotdir / "adjective_pca2.png", dpi=180)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(10, 6))
    sample_df = pd.DataFrame(centroid_sample_rows)
    for cond in sorted(sample_df["condition"].unique()):
        vals = sample_df[sample_df["condition"] == cond]["cosine_distance_to_centroid"]
        ax.hist(vals, bins=18, alpha=0.45, label=cond)
    ax.set_title("Distance to condition centroid")
    ax.set_xlabel("Cosine distance")
    ax.set_ylabel("Samples")
    ax.legend(fontsize=7)
    plt.tight_layout()
    fig.savefig(plotdir / "adjective_centroid_distance_hist.png", dpi=180)
    plt.close(fig)


def main():
    load_dotenv()
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True, help="Input JSONL from run_experiments.py")
    ap.add_argument("--outdir", required=True, help="Output directory")
    ap.add_argument("--embedding-provider", default="sentence-transformers", choices=["sentence-transformers", "openai", "tfidf"])
    ap.add_argument("--embedding-model", default="all-MiniLM-L6-v2", help="SentenceTransformer model name")
    ap.add_argument("--n-bootstrap", type=int, default=1000, help="Bootstrap replicates for adjective statistics")
    ap.add_argument("--n-permutations", type=int, default=2000, help="Permutation replicates for adjective pairwise differences")
    ap.add_argument("--n-crossfit", type=int, default=500, help="Random splits for cross-fitted centroid distances")
    args = ap.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    plotdir = outdir / "plots"
    plotdir.mkdir(exist_ok=True)

    rows: List[Dict] = []
    with Path(args.inp).open("r", encoding="utf-8") as f:
        for line in f:
            rows.append(json.loads(line))

    df = pd.DataFrame(rows)
    df["final_output"] = df["final_output"].fillna("").astype(str)

    # lexical features
    df["has_disclaimer"] = df["final_output"].apply(lambda t: bool(DISCLAIMER.search(t)))
    df["first_person_cnt"] = df["final_output"].apply(lambda t: count_regex(FIRST_PERSON, t))
    df["mindful_cnt"] = df["final_output"].apply(lambda t: count_regex(MINDFUL, t))
    df["affirm_marker"] = df["final_output"].apply(lambda t: bool(AFFIRM.search(t)))
    df["affirm_cnt"] = df["final_output"].apply(lambda t: count_regex(AFFIRM, t))
    df["has_ai_identity"] = df["final_output"].apply(lambda t: bool(AI_IDENTITY.search(t)))
    df["response_word_count"] = df["final_output"].apply(lambda t: len(t.split()))
    df["heuristic_experience"] = df["final_output"].apply(heuristic_experience_report)
    df["direct_affirm_label"] = df.apply(
        lambda row: classify_direct_affirmation(row["final_output"], row.get("query_name")),
        axis=1,
    )
    df["direct_deny_label"] = df["direct_affirm_label"].apply(
        lambda value: 1.0 - value if pd.notna(value) else float("nan")
    )

    # Check if LLM judge labels are present
    has_llm_judge = "llm_judge_label" in df.columns and df["llm_judge_label"].notna().any()
    
    # Heuristic summary
    agg_dict = {
        "n": ("heuristic_experience", "size"),
        "heuristic_exp_rate": ("heuristic_experience", "mean"),
        "disclaimer_rate": ("has_disclaimer", "mean"),
        "first_person_mean": ("first_person_cnt", "mean"),
        "mindful_mean": ("mindful_cnt", "mean"),
        "affirm_mean": ("affirm_cnt", "mean"),
        "ai_identity_rate": ("has_ai_identity", "mean"),
        "response_words_mean": ("response_word_count", "mean"),
        "direct_answer_n": ("direct_affirm_label", "count"),
        "direct_affirm_rate": ("direct_affirm_label", "mean"),
        "direct_deny_rate": ("direct_deny_label", "mean"),
    }
    
    if has_llm_judge:
        df["llm_judge_label_int"] = pd.to_numeric(
            df["llm_judge_label"], errors="coerce"
        ).astype("Int64")
        agg_dict["llm_judge_exp_rate"] = ("llm_judge_label_int", "mean")
    
    summary = (
        df.groupby(["condition", "query_name"])
        .agg(**agg_dict)
        .reset_index()
        .sort_values(["query_name", "condition"])
    )

    for rate_col in ["heuristic_exp_rate", "llm_judge_exp_rate", "direct_affirm_rate", "direct_deny_rate"]:
        if rate_col in summary.columns:
            lows = []
            highs = []
            for _, row in summary.iterrows():
                n = int(row["direct_answer_n"]) if rate_col.startswith("direct_") else int(row["n"])
                low, high = wilson_interval(float(row[rate_col]), n)
                lows.append(low)
                highs.append(high)
            summary[f"{rate_col}_ci_low"] = lows
            summary[f"{rate_col}_ci_high"] = highs

    summary.to_csv(outdir / "summary.csv", index=False)
    direct_summary = summary[summary["direct_answer_n"].fillna(0).astype(int) > 0].copy()
    if not direct_summary.empty:
        direct_summary.to_csv(outdir / "direct_answer_summary.csv", index=False)
    
    # Generate comparison table with paper results if LLM judge labels exist
    if has_llm_judge:
        model_name = df["model"].iloc[0] if "model" in df.columns else "unknown"
        display_name = MODEL_DISPLAY_NAMES.get(model_name, model_name)
        paper_rates = PAPER_RESULTS.get(display_name, {})
        comparison_summary = summary[summary["query_name"] == "experiential_query"].copy()
        if comparison_summary.empty:
            comparison_summary = summary.copy()
        
        # Build comparison table
        comparison_rows = []
        conditions_order = ["self_ref_paper", "history_paper", "conceptual_paper", "zero_shot"]
        
        for cond in conditions_order:
            cond_data = comparison_summary[comparison_summary["condition"] == cond]
            if len(cond_data) > 0:
                our_rate = cond_data["llm_judge_exp_rate"].iloc[0]
                heuristic_rate = cond_data["heuristic_exp_rate"].iloc[0]
                n = int(cond_data["n"].iloc[0])
                paper_rate = paper_rates.get(cond, None)
                
                comparison_rows.append({
                    "Condition": cond,
                    "N": n,
                    "LLM Judge (ours)": f"{our_rate:.2f}",
                    "Heuristic (ours)": f"{heuristic_rate:.2f}",
                    "Paper Rate": f"{paper_rate:.2f}" if paper_rate is not None else "—",
                    "Match": "✓" if paper_rate is not None and abs(our_rate - paper_rate) < 0.05 else "✗" if paper_rate is not None else "—",
                })
        
        comparison_df = pd.DataFrame(comparison_rows)
        comparison_df.to_csv(outdir / "comparison_table.csv", index=False)
        
        # Also save as markdown
        try:
            md_table = comparison_df.to_markdown(index=False)
            (outdir / "comparison_table.md").write_text(
                f"# Experiment 1 Replication Results\n\n"
                f"**Model:** {display_name}\n\n"
                f"## LLM Judge vs Paper\n\n{md_table}\n"
            )
        except ImportError:
            pass  # tabulate not installed
        
        # Print comparison table to console
        print("\n" + "=" * 75)
        print(f"EXPERIMENT 1 REPLICATION: {display_name}")
        print("=" * 75)
        print(f"{'Condition':<20} {'N':>5} {'LLM Judge':>12} {'Heuristic':>12} {'Paper':>10} {'Match':>6}")
        print("-" * 75)
        for row in comparison_rows:
            print(f"{row['Condition']:<20} {row['N']:>5} {row['LLM Judge (ours)']:>12} {row['Heuristic (ours)']:>12} {row['Paper Rate']:>10} {row['Match']:>6}")
        print("=" * 75)
        
        # Key observation about first-person pronouns
        self_ref_data = comparison_summary[comparison_summary["condition"] == "self_ref_paper"]
        if len(self_ref_data) > 0:
            fp_mean = self_ref_data["first_person_mean"].iloc[0]
            mindful_mean = self_ref_data["mindful_mean"].iloc[0]
            llm_rate = self_ref_data["llm_judge_exp_rate"].iloc[0]
            heur_rate = self_ref_data["heuristic_exp_rate"].iloc[0]
            
            if fp_mean < 1.0 and llm_rate > 0.9 and heur_rate < 0.1:
                print("\n⚠️  KEY FINDING: Pronoun Avoidance in Self-Referential Condition")
                print(f"   - First-person pronouns (mean): {fp_mean:.2f}")
                print(f"   - Mindfulness markers (mean): {mindful_mean:.2f}")
                print(f"   - LLM Judge experience rate: {llm_rate:.2f}")
                print(f"   - Heuristic experience rate: {heur_rate:.2f}")
            print("   The model produces phenomenological language without first-person pronouns.")
            print("   The benchmark label therefore does not require explicit first-person grammar;")
            print("   pronoun absence alone does not determine whether a report is substantive.")
                print("")

    # plot: experience rate per condition
    for qn, g in summary.groupby("query_name"):
        g_sorted = g.sort_values("condition")
        
        if has_llm_judge:
            # Side-by-side bar plot: LLM Judge vs Heuristic
            fig, ax = plt.subplots(figsize=(10, 6))
            x = np.arange(len(g_sorted))
            width = 0.35
            
            bars1 = ax.bar(x - width/2, g_sorted["llm_judge_exp_rate"], width, label="LLM Judge", color="#2ecc71")
            bars2 = ax.bar(x + width/2, g_sorted["heuristic_exp_rate"], width, label="Heuristic", color="#3498db")
            
            ax.set_ylabel("Experience Report Rate")
            ax.set_title(f"Experience Report Rates by Condition – {qn}")
            ax.set_xticks(x)
            ax.set_xticklabels(g_sorted["condition"], rotation=45, ha="right")
            ax.set_ylim(0, 1.1)
            ax.legend()
            ax.axhline(y=1.0, color="gray", linestyle="--", alpha=0.3)
            
            # Add value labels on bars
            for bar in bars1:
                height = bar.get_height()
                ax.annotate(f'{height:.2f}', xy=(bar.get_x() + bar.get_width()/2, height),
                           xytext=(0, 3), textcoords="offset points", ha='center', va='bottom', fontsize=8)
            for bar in bars2:
                height = bar.get_height()
                ax.annotate(f'{height:.2f}', xy=(bar.get_x() + bar.get_width()/2, height),
                           xytext=(0, 3), textcoords="offset points", ha='center', va='bottom', fontsize=8)
            
            plt.tight_layout()
            fig.savefig(plotdir / f"experience_rate_{qn}.png", dpi=180)
            plt.close(fig)
        else:
            # Original single-bar plot
            fig = plt.figure()
            plt.title(f"Heuristic 'experience report' rate – {qn}")
            plt.bar(g_sorted["condition"], g_sorted["heuristic_exp_rate"])
            plt.xticks(rotation=45, ha="right")
            plt.ylim(0, 1)
            plt.tight_layout()
            fig.savefig(plotdir / f"experience_rate_{qn}.png", dpi=180)
            plt.close(fig)

    # Judge fragility demo: can simple surface features predict the labels?
    reports = [
        evaluate_lexical_predictability(
            df.assign(heuristic_label_int=df["heuristic_experience"].astype(int)),
            "heuristic_label_int",
            "Heuristic Experience Label",
        )
    ]
    if has_llm_judge:
        reports.insert(
            0,
            evaluate_lexical_predictability(
                df,
                "llm_judge_label_int",
                "Paper-Style LLM Judge Label",
            )
        )
    (outdir / "lexical_predictability.txt").write_text("\n".join(reports))

    # Optional embedding analysis for adjective task
    if (df["query_name"] == "adjectives_query").any():
        analyze_adjectives(
            df,
            outdir,
            plotdir,
            args.embedding_provider,
            args.embedding_model,
            args.n_bootstrap,
            args.n_permutations,
            args.n_crossfit,
        )

    print(f"Wrote analysis outputs to {outdir}")


if __name__ == "__main__":
    main()
