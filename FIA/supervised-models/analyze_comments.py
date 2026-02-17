#!/usr/bin/env python3
import argparse
import os
import re
import string
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import classification_report
    from sklearn.pipeline import Pipeline
    from sklearn.utils.class_weight import compute_class_weight
except Exception as e:  # pragma: no cover
    TfidfVectorizer = None  # type: ignore
    LogisticRegression = None  # type: ignore
    train_test_split = None  # type: ignore
    classification_report = None  # type: ignore
    Pipeline = None  # type: ignore
    compute_class_weight = None  # type: ignore

from lexicons import INTENT_KEYWORDS, PROFANITY_WORDS, INSULT_PATTERNS, THREAT_WORDS, SARCASM_CUES


# ---------------------
# Text preprocessing
# ---------------------

PUNCT_TABLE = str.maketrans("", "", string.punctuation)


def normalize_whitespace(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def basic_clean(text: str) -> str:
    if not isinstance(text, str):
        return ""
    t = text.lower()
    # Replace URLs/emails
    t = re.sub(r"https?://\S+", " <url> ", t)
    t = re.sub(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b", " <email> ", t)
    # Remove punctuation (keep apostrophes for contractions)
    t = t.translate(PUNCT_TABLE)
    # Normalize whitespace
    return normalize_whitespace(t)


# ---------------------
# Heuristic detectors
# ---------------------

def toxicity_score(text: str) -> float:
    if not text:
        return 0.0
    t = basic_clean(text)
    tokens = t.split()

    if not tokens:
        return 0.0

    # Profanity density
    prof_count = sum(1 for tok in tokens if tok in PROFANITY_WORDS)
    prof_density = prof_count / max(1, len(tokens))

    # Insult patterns
    insult = any(pat in t for pat in INSULT_PATTERNS)

    # Threats
    threat = any(w in t for w in THREAT_WORDS)

    # All caps ratio (shouting)
    raw = text
    caps_chars = sum(1 for c in raw if c.isupper())
    letters = sum(1 for c in raw if c.isalpha())
    caps_ratio = (caps_chars / letters) if letters else 0.0

    # Emphasis via repeated punctuation
    exclaim = min(1.0, raw.count("!") / 3.0)

    # Weighted sum -> [0,1]
    score = (
        0.65 * min(1.0, 5 * prof_density)
        + 0.15 * (1.0 if insult else 0.0)
        + 0.1 * (1.0 if threat else 0.0)
        + 0.05 * min(1.0, caps_ratio * 2)
        + 0.05 * exclaim
    )
    return float(max(0.0, min(1.0, score)))


def sarcasm_flag(text: str) -> Tuple[bool, str]:
    t = basic_clean(text)
    cues = [cue for cue in SARCASM_CUES if cue in t]

    # Positive superlatives + negative emotive tokens pattern
    positive_cues = ["love", "great", "awesome", "amazing", "fantastic", "nice"]
    negative_feels = [":/", ":(", "smh", "ffs", "ugh", "lol", "lmao"]
    polarity_clash = any(p in t for p in positive_cues) and any(n in text.lower() for n in negative_feels)

    # Ellipsis after positive word is sometimes sarcastic
    ellipsis_sarcasm = bool(re.search(r"\b(great|awesome|amazing|nice)\s*\.\.\.", text.lower()))

    flagged = bool(cues) or polarity_clash or ellipsis_sarcasm
    reason = (
        f"cues={cues}" if cues else (
            "polarity_clash" if polarity_clash else (
                "ellipsis_positive" if ellipsis_sarcasm else ""
            )
        )
    )
    return flagged, reason


def detect_intent(text: str, sentiment_hint: Optional[str] = None) -> str:
    t = basic_clean(text)

    scores: Dict[str, int] = {k: 0 for k in ["elogio", "reclamacao", "sugestao", "suporte"]}

    # Count matches by language groups
    for intent, langs in INTENT_KEYWORDS.items():
        for words in langs.values():
            for w in words:
                if w in t:
                    scores[intent] += 1

    # Question markers can hint support
    if "?" in text:
        scores["suporte"] += 1

    # Tie-breakers using sentiment hint if provided
    if sentiment_hint:
        if sentiment_hint == "positive":
            scores["elogio"] += 1
        elif sentiment_hint == "negative":
            scores["reclamacao"] += 1

    # Choose max; default to 'suporte' if all zero and text looks like a question
    best = max(scores.items(), key=lambda kv: kv[1])
    if best[1] == 0:
        return "suporte" if "?" in text else "elogio"
    return best[0]


def needs_escalation(intent: str, toxicity: float, sentiment_pred: Optional[str], text: str) -> bool:
    if toxicity >= 0.5:
        return True
    if intent in {"reclamacao", "suporte"}:
        # Escalate on negative tone or urgency
        urgent = any(u in text.lower() for u in ["urgent", "asap", "refund", "help now", "não consigo", "nao consigo"])
        negative = (sentiment_pred == "negative") if sentiment_pred else False
        long_thread = text.count("?") >= 2
        return urgent or negative or long_thread
    return False


# ---------------------
# Sentiment model
# ---------------------

@dataclass
class SentimentResult:
    report: str
    model: Optional[Pipeline]


def train_sentiment(df: pd.DataFrame, text_col: str = "Comment", label_col: str = "Sentiment", test_size: float = 0.2, random_state: int = 42) -> SentimentResult:
    if TfidfVectorizer is None:
        return SentimentResult(report="scikit-learn is not available in this environment.", model=None)

    data = df[[text_col, label_col]].dropna()
    X = data[text_col].astype(str).tolist()
    y = data[label_col].astype(str).str.lower().tolist()

    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=test_size, random_state=random_state, stratify=y)

    # Handle class imbalance via class weights
    classes = np.unique(y_train)
    weights = compute_class_weight('balanced', classes=classes, y=y_train)
    class_weight = {c: w for c, w in zip(classes, weights)}

    pipe = Pipeline([
        ("tfidf", TfidfVectorizer(ngram_range=(1, 2), min_df=3, max_features=100_000, sublinear_tf=True)),
        # multi_class default avoids FutureWarning on sklearn>=1.5
        ("clf", LogisticRegression(max_iter=400, n_jobs=None, class_weight=class_weight, solver="lbfgs")),
    ])

    pipe.fit(X_train, y_train)
    preds = pipe.predict(X_test)
    rep = classification_report(y_test, preds)
    return SentimentResult(report=rep, model=pipe)


def apply_all(
    df: pd.DataFrame,
    model: Optional[Pipeline],
    text_col: str = "Comment",
    sentiment_col_out: str = "sentiment_pred",
    sarcasm_col_out: str = "sarcasm_flag",
    toxicity_col_out: str = "toxicity_score",
    intent_col_out: str = "intent_pred",
    escalation_col_out: str = "needs_escalation",
) -> pd.DataFrame:
    out = df.copy()
    texts = out[text_col].astype(str).tolist()

    # Sentiment predictions
    if model is not None:
        try:
            out[sentiment_col_out] = model.predict(texts)
        except Exception:
            out[sentiment_col_out] = ""
    else:
        out[sentiment_col_out] = ""

    # Heuristic features
    s_flags, s_reasons, tox_scores, intents, escalations = [], [], [], [], []
    for text, sent in zip(texts, out[sentiment_col_out].tolist()):
        flag, reason = sarcasm_flag(text)
        s_flags.append(flag)
        s_reasons.append(reason)

        tox = toxicity_score(text)
        tox_scores.append(round(float(tox), 3))

        intent = detect_intent(text, sentiment_hint=(sent if isinstance(sent, str) and sent else None))
        intents.append(intent)

        esc = needs_escalation(intent=intent, toxicity=tox, sentiment_pred=(sent if isinstance(sent, str) and sent else None), text=text)
        escalations.append(bool(esc))

    out[sarcasm_col_out] = s_flags
    out["sarcasm_reason"] = s_reasons
    out[toxicity_col_out] = tox_scores
    out[intent_col_out] = intents
    out[escalation_col_out] = escalations
    return out


def main():
    ap = argparse.ArgumentParser(description="FIA: YouTube comments multi-task analysis")
    ap.add_argument("--csv", default="/Users/oleitao/Documents/Repos/RUMOS/FIA/YoutubeCommentsDataSet.csv", help="Path to input CSV with columns [Comment, Sentiment]")
    ap.add_argument("--text-col", default="Comment", help="Name of the text column")
    ap.add_argument("--label-col", default="Sentiment", help="Name of the sentiment label column")
    ap.add_argument("--no-train", action="store_true", help="Skip training sentiment model (only heuristics)")
    ap.add_argument("--out", default=None, help="Output CSV path for enriched data. If omitted, saves next to the input CSV.")
    args = ap.parse_args()

    if not os.path.exists(args.csv):
        raise SystemExit(f"Input CSV not found: {args.csv}")

    df = pd.read_csv(args.csv)

    model = None
    report = None
    if not args.no_train:
        res = train_sentiment(df, text_col=args.text_col, label_col=args.label_col)
        report = res.report
        model = res.model
        if report:
            print("Sentiment evaluation (holdout):")
            print(report)
        else:
            print("Sentiment model unavailable; continuing with heuristics only.")

    enriched = apply_all(df, model=model, text_col=args.text_col)

    # Resolve output path robustly
    csv_dir = os.path.dirname(os.path.abspath(args.csv))
    repo_root = os.path.dirname(csv_dir)

    if args.out is None:
        out_path = os.path.join(csv_dir, "supervised-models/YoutubeCommentsDataSet_enriched.csv")
    else:
        candidate = os.path.normpath(args.out)
        if os.path.isabs(candidate):
            out_path = candidate
        else:
            out_dir_part = os.path.dirname(candidate)
            if out_dir_part == "":
                # Only a filename provided -> save next to CSV
                out_path = os.path.join(csv_dir, os.path.basename(candidate))
            else:
                # If first component equals the CSV dir name (e.g., 'FIA'), resolve from repo root
                first = out_dir_part.split(os.sep)[0]
                if first == os.path.basename(csv_dir):
                    out_path = os.path.join(repo_root, candidate)
                else:
                    # Fallback: relative to current working directory
                    out_path = os.path.abspath(candidate)

    out_parent = os.path.dirname(out_path)
    if out_parent and not os.path.exists(out_parent):
        os.makedirs(out_parent, exist_ok=True)

    enriched.to_csv(out_path, index=False)
    print(f"Saved enriched dataset to: {out_path}")


if __name__ == "__main__":
    main()
