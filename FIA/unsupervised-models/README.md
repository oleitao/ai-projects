Unsupervised semantic analysis of YouTube comments

This script groups semantically similar comments, removes duplicates/near‑duplicates, and flags anomalous comments that may indicate potential crises.

Directory overview
- `FIA/unsupervised-models/unsupervised_analyze_comments.py` — main CLI/pipeline.
- `FIA/unsupervised-models/requirements.txt` — minimal deps (sklearn, pandas, numpy, scipy; optional sentence-transformers).
- `FIA/unsupervised-models/cache` and `FIA/unsupervised-models/hf` — default local caches for HF models (can override).
- Outputs written to this folder (see below).

What it does
- Clustering (semantic): builds embeddings and clusters comments (`MiniBatchKMeans`).
- Deduplication: exact duplicates and near‑duplicates via SimHash with small Hamming distance.
- Anomalies: isolation‑based outlier detection over embeddings.

How it works (pipeline)
1) Clean text (lowercase, URL/email masking, punctuation removal, whitespace normalization).
2) Embeddings
   - `tfidf` (default): TF‑IDF → `TruncatedSVD` → L2 normalize.
   - `sentence`: Sentence‑Transformers encode (CPU) → L2 normalize.
   - `torch`: HF `AutoModel` + mean‑pooling → L2 normalize.
   - `auto`: tries `sentence` then falls back to `tfidf` if unavailable/offline.
   Also retains a TF‑IDF matrix to extract cluster keywords even when using sentence embeddings.
3) Cluster embeddings with `MiniBatchKMeans` (auto‑k heuristic if `--k` not set). Write top TF‑IDF terms per cluster.
4) Deduplicate
   - Exact duplicates (case/space/punct normalized) → `dup_exact_group` (>0 when part of a group).
   - Near‑duplicates (SimHash + Hamming distance within bucket) → `dup_near_group`, `is_near_duplicate`, and a reference id `near_duplicate_of`.
5) Anomalies: `IsolationForest` over embeddings; fallback to distance‑from‑mean if sklearn’s IF is missing.
6) Join back with original rows and write enriched CSV + summaries.

Inputs
- CSV: `FIA/YoutubeCommentsDataSet.csv` (default)
- Column: `Comment` (default)

Outputs (written to this folder)
- `YoutubeComments_unsupervised_enriched.csv` — original rows + analysis columns:
  - `orig_index` (position in the original CSV), `clean_text`, `cluster` (−1 if `--skip-cluster`),
  - `dup_exact_group`, `dup_near_group`, `is_near_duplicate`, `near_duplicate_of` (reference `orig_index`),
  - `anomaly_score`, `is_anomaly`.
- `clusters_summary.csv` — top terms (by mean TF‑IDF) per cluster.
- `near_duplicates.csv` — list of items flagged as near‑duplicates (if any).
- `anomalies.csv` — items flagged as anomalies (if any).

Quick start
```bash
# Optionally create/activate a venv, then install deps
pip install -r FIA/unsupervised-models/requirements.txt

# Run with defaults (TF–IDF+SVD embeddings, heuristic k)
python FIA/unsupervised-models/unsupervised_analyze_comments.py --csv FIA/YoutubeCommentsDataSet.csv --text-col Comment

# Example: force 10 clusters, sample to iterate faster
python FIA/unsupervised-models/unsupervised_analyze_comments.py --k 10 --sample 5000

# Example: try sentence embeddings (requires sentence-transformers)
python FIA/unsupervised-models/unsupervised_analyze_comments.py --embedding sentence

# Example: PyTorch + transformers embeddings (mean pooling)
python FIA/unsupervised-models/unsupervised_analyze_comments.py --embedding torch --sentence-model sentence-transformers/all-MiniLM-L6-v2
```

Notes
- If `sentence-transformers` cannot download a model (no network), the script automatically falls back to TF–IDF + SVD embeddings.
- SimHash parameters (`--dedup-hamming`, `--bucket-prefix-bits`) can be tuned for stricter/looser near-duplicate detection.
- Anomaly contamination (`--contamination`) controls the fraction flagged as anomalies (default 2%).
- Default CPU execution; no GPU required. Threading is reduced by default (`TOKENIZERS_PARALLELISM=false`, low BLAS threads) for stability.

Performance tuning
- Use sampling during iteration: `--sample 3000`
- Speed up TF‑IDF by limiting features and n‑grams: `--max-features 30000 --ngram-max 1 --min-df 3`
- Skip steps when not needed: `--skip-dedup`, `--skip-anomaly`, `--skip-cluster`
- Control MiniBatchKMeans batch size: `--kmeans-batch-size 4096`
- Control SimHash comparison explosion: `--max-bucket-size 2000` and increase `--bucket-prefix-bits`
- Lower SVD dimensionality: `--svd-components 50` (trade detail for speed).
- For TF‑IDF stop words: `--stop-words english` (built‑in). For other languages, provide a custom list via code.

Heavy libraries (torch/sentence-transformers/transformers)

If you want sentence embeddings, install torch + sentence-transformers.

```bash
# CPU-only (cross-platform)
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install sentence-transformers transformers

# Quick check (imports heavy libs, does not run analysis)
python FIA/unsupervised-models/unsupervised_analyze_comments.py --check-heavy --embedding sentence

# Run with sentence embeddings (downloads model if not cached)
python FIA/unsupervised-models/unsupervised_analyze_comments.py --embedding sentence --sentence-model all-MiniLM-L6-v2
```

Base installations
```bash
pip install -r FIA/unsupervised-models/requirements.txt

# Optional (for PyTorch embeddings)
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install transformers
```

Cache notes (defaults set in the script — you can override via env/CLI)
- `HF_HOME=/Users/oleitao/Documents/Repos/RUMOS/FIA/unsupervised-models/hf`
- `TRANSFORMERS_CACHE=/Users/oleitao/Documents/Repos/RUMOS/FIA/unsupervised-models/cache`

Main CLI parameters
- `--csv` CSV path (default `FIA/YoutubeCommentsDataSet.csv`).
- `--text-col` text column (default `Comment`).
- `--k` number of clusters (heuristic if omitted).
- `--embedding` `tfidf|sentence|torch|auto` (default `tfidf`).
- TF‑IDF: `--svd-components`, `--max-features`, `--min-df`, `--max-df`, `--ngram-max`, `--stop-words`.
- Sentence/HF: `--sentence-model`, `--hf-home`, `--hf-offline`, `--st-batch-size`.
- KMeans: `--kmeans-batch-size`.
- Dedup: `--dedup-hamming`, `--bucket-prefix-bits`, `--max-bucket-size`.
- Anomalies: `--contamination`.
- General: `--sample`, `--out-dir`, `--seed`, `--skip-cluster`, `--skip-dedup`, `--skip-anomaly`, `--check-heavy`, `--download-model`.

Run with TF‑IDF (no downloads)
```bash
.venv/bin/python FIA/unsupervised-models/unsupervised_analyze_comments.py \
  --csv FIA/YoutubeCommentsDataSet.csv --text-col Comment
```

Run with Sentence‑Transformers (offline in 2 steps)
1. Download the model to cache once (with internet):
   ```bash
   .venv/bin/python FIA/unsupervised-models/unsupervised_analyze_comments.py \
     --embedding sentence \
     --sentence-model all-MiniLM-L6-v2 \
     --hf-home FIA/unsupervised-models/cache \
     --download-model
   ```
2. Run offline (use the model name, not a directory):
   ```bash
   .venv/bin/python FIA/unsupervised-models/unsupervised_analyze_comments.py \
     --csv FIA/YoutubeCommentsDataSet.csv --text-col Comment \
     --embedding sentence \
     --sentence-model all-MiniLM-L6-v2 \
     --hf-home FIA/unsupervised-models/cache --hf-offline
   ```

Run with PyTorch + Transformers (offline in 2 steps)
1. Install libs and download the model (full repo id):
   ```bash
   pip install torch --index-url https://download.pytorch.org/whl/cpu
   pip install transformers
   .venv/bin/python FIA/unsupervised-models/unsupervised_analyze_comments.py \
     --embedding torch \
     --sentence-model sentence-transformers/all-MiniLM-L6-v2 \
     --hf-home FIA/unsupervised-models/cache \
     --download-model
   ```
2. Run offline:
   ```bash
   .venv/bin/python FIA/unsupervised-models/unsupervised_analyze_comments.py \
     --csv FIA/YoutubeCommentsDataSet.csv --text-col Comment \
     --embedding torch \
     --sentence-model sentence-transformers/all-MiniLM-L6-v2 \
     --hf-home FIA/unsupervised-models/cache --hf-offline
   ```

Generated outputs
- `FIA/unsupervised-models/YoutubeComments_unsupervised_enriched.csv`
- `FIA/unsupervised-models/clusters_summary.csv`
- `FIA/unsupervised-models/near_duplicates.csv`
- `FIA/unsupervised-models/anomalies.csv`

Notes
- Even with `--embedding sentence` or `--embedding torch`, `clusters_summary.csv` is produced (the script builds a local TF‑IDF to extract per‑cluster keywords).
- Use `--sample` to speed up iterations, and `--check-heavy` to validate `torch`/`sentence-transformers`/`transformers` installations without running the analysis.
- The cluster label is `-1` when `--skip-cluster` is active; in that case, per‑cluster keyword columns may be empty.

