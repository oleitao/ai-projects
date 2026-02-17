FIA — Supervised Models (YouTube Comments)

This module trains and applies a sentiment classifier and, additionally, runs heuristic detectors for sarcasm, toxicity, intent, and need for escalation over a comments CSV (by default `FIA/YoutubeCommentsDataSet.csv`). It does not use LLMs or network; it is 100% local using scikit‑learn and rules.

Contents
- `FIA/supervised-models/analyze_comments.py` — CLI to train the sentiment model and enrich the CSV with all labels/flags.
- `FIA/supervised-models/lexicons.py` — PT/EN keyword lists for intent, insults, threats, and sarcasm cues.
- `FIA/supervised-models/requirements.txt` — dependencies: pandas, scikit‑learn, numpy, joblib.
- `FIA/supervised-models/YoutubeCommentsDataSet_enriched.csv` — example output.

Requirements
- Python 3.10+
- Install module dependencies:
  ```bash
  pip install -r FIA/supervised-models/requirements.txt
  ```

Expected dataset
- To train sentiment, the CSV must have at least:
  - a text column (default `Comment`, configurable via `--text-col`)
  - a sentiment label column (default `Sentiment`, configurable via `--label-col`)
- If it does not have sentiment labels, use `--no-train` to apply only heuristics.

How it works
- Pre‑processing: lowercase, replacement of URLs/emails with markers, punctuation removal, whitespace normalization.
- Sentiment (supervised):
  - TF‑IDF vectorization with n‑grams (1,2), `min_df=3`, `max_features=100000`, `sublinear_tf=True`.
  - Classifier `LogisticRegression` with `class_weight='balanced'` (via `compute_class_weight`), `solver='lbfgs'`, `max_iter=400`.
  - Stratified 80/20 `train_test_split`; prints `classification_report` on the holdout.
  - Applies `predict` to the full dataset and writes `sentiment_pred`. If `--no-train`, it remains empty.
- Heuristics:
  - Toxicity (`toxicity_score` 0–1): density of profanity, insult patterns, threats, ALL CAPS, and exclamation points.
  - Sarcasm (`sarcasm_flag`, `sarcasm_reason`): explicit cues, “polarity clash”, and ellipses after positive superlatives.
  - Intent (`intent_pred`: `praise`/`complaint`/`suggestion`/`support`): counts via PT/EN lexicons; tie‑break with sentiment cues; fallback to `support` when there is a “?”
  - Escalation (`needs_escalation`): `toxicity_score ≥ 0.5` OR intent `complaint/support` with urgency/negativity (e.g., “urgent”, “refund”, “não consigo”/“I can’t”, ≥2 “?”).

Commands (examples)
- Train sentiment and enrich CSV (use defaults):
  ```bash
  python FIA/supervised-models/analyze_comments.py \
    --csv FIA/YoutubeCommentsDataSet.csv --text-col Comment --label-col Sentiment
  ```
- Heuristics only (no training):
  ```bash
  python FIA/supervised-models/analyze_comments.py \
    --csv FIA/YoutubeCommentsDataSet.csv --no-train
  ```
- Custom columns and different output path:
  ```bash
  python FIA/supervised-models/analyze_comments.py \
    --csv data/comments.csv --text-col texto --label-col rotulo \
    --out results/enriched.csv
  ```

Parameters (CLI)
- `--csv` path to the CSV (default `FIA/YoutubeCommentsDataSet.csv`).
- `--text-col` text column name (default `Comment`).
- `--label-col` sentiment label column (default `Sentiment`).
- `--no-train` skip training; run heuristics only and leave `sentiment_pred` empty.
- `--out` output CSV path:
  - If omitted: saves to `…/FIA/supervised-models/YoutubeCommentsDataSet_enriched.csv` next to the input CSV.
  - If relative: resolved robustly (simple name → next to the CSV; paths starting with `FIA/...` resolved from the repo root; otherwise relative to CWD).

Generated output
- Enriched CSV with the columns:
  - `sentiment_pred`, `sarcasm_flag`, `sarcasm_reason`, `toxicity_score`, `intent_pred`, `needs_escalation`.
- Default path: `FIA/supervised-models/YoutubeCommentsDataSet_enriched.csv` (next to the input CSV).

Customization
- Adjust keywords and patterns in `FIA/supervised-models/lexicons.py` (PT + EN).
- To change vectorization/algorithm, edit the pipeline in `train_sentiment()`.

Performance and class imbalance
- Class weighting balances classes during training; if the dataset is highly imbalanced, consider more data or sampling techniques.
- You may reduce `max_features`/`min_df` in TF‑IDF to speed up.

Troubleshooting
- “CSV not found” → check `--csv` and relative paths.
- “Text/label column does not exist” → confirm `--text-col`/`--label-col` and the CSV header.
- “scikit‑learn not available” → install via `pip install -r FIA/supervised-models/requirements.txt`.
- Poor report (low F1) → noisy data, class imbalance, few examples; try `--no-train` to focus on heuristics.

Note
- This module does not use LLMs or internet access. For generative analyses with an LLM (summaries, zero/few‑shot classification, explanations, rewrites), see `FIA/generative-llm`.

