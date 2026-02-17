FIA — Generative LLM for Comment Analyses

This module uses an LLM (OpenAI by default) to produce summaries, zero/few‑shot classifications, sentiment explanations, and rewritten support replies over the dataset `FIA/YoutubeCommentsDataSet.csv` (or another CSV with a text column).

Sections below cover architecture, setup, commands, parameters, outputs, caching, offline mode, and troubleshooting.

Directory contents
- `FIA/generative-llm/generative_analyze_comments.py` — CLI with 4 tasks: `summarize`, `classify`, `explain-sentiment`, `rewrite-replies`.
- `FIA/generative-llm/requirements.txt` — dependencies (OpenAI SDK, pandas, tqdm, tenacity, dotenv).
- `FIA/generative-llm/output/` — generated outputs.
- `FIA/generative-llm/.cache.jsonl` — local cache of LLM responses (JSONL).
- `FIA/generative-llm/.env` — optional, with `OPENAI_API_KEY=` (not auto‑loaded by the script; see Setup).

Requirements
- Python 3.10+
- LLM API key (OpenAI recommended).
- Install packages:
  ```bash
  pip install -r FIA/generative-llm/requirements.txt
  ```

Setup
- Set `OPENAI_API_KEY` in your environment. Examples:
  - Bash: `export OPENAI_API_KEY=sk-...`
  - If your shell/IDE does NOT auto‑load `.env`, you may run:
    ```bash
    set -a; source FIA/generative-llm/.env; set +a
    # or
    export $(grep -v '^#' FIA/generative-llm/.env | xargs)
    ```
- Model: `OPENAI_MODEL` (default `gpt-4o-mini`) or the `--openai-model` flag.
- Force offline mode (no network calls): use `--offline` on the CLI.

Overview (architecture)
- Minimal OpenAI client with caching (`OpenAIClient`):
  - Uses Chat Completions (configurable `model`), 3 retries with exponential backoff (tenacity).
  - Extracts and validates JSON from the response; if parsing fails, tries the first `{...}` block.
  - Cache (`.cache.jsonl`) keyed by SHA‑256 of the task+payload (includes `system`, `user`, `schema_hint`, `model`). Prevents repeat calls with the same request.
- Offline fallback: simple heuristics return JSON‑compatible structures when `OPENAI_API_KEY` is missing or `--offline` is active.

Commands and examples
1) Summaries by an existing group
```bash
python FIA/generative-llm/generative_analyze_comments.py summarize \
  --csv FIA/YoutubeCommentsDataSet.csv --text-col Comment \
  --group-col Sentiment
```

2) Summaries with automatic topic discovery (auto‑topic)
```bash
python FIA/generative-llm/generative_analyze_comments.py summarize \
  --csv FIA/YoutubeCommentsDataSet.csv --text-col Comment \
  --auto-topic --topic-labels "praise,complaint,suggestion,comparison,off-topic"
```
How it works:
- The LLM assigns 1–2 topics per comment from `--topic-labels` and writes them to `AutoTopic`.
- Then, it produces per‑topic summaries in 2 stages (micro‑summaries per block of `--chunk-size` comments → final synthesis).

3) Zero‑shot/few‑shot classification
```bash
python FIA/generative-llm/generative_analyze_comments.py classify \
  --csv FIA/YoutubeCommentsDataSet.csv --text-col Comment \
  --labels "positive,neutral,negative" \
  --few-shot 6 --few-shot-col Sentiment
```
Notes:
- `--labels` defines the closed set of labels.
- `--few-shot N` injects up to ~N balanced examples per label drawn from `--few-shot-col` (when available).
- If the LLM response lacks a valid label, a keyword heuristic fallback is applied.

4) Sentiment explanations
```bash
python FIA/generative-llm/generative_analyze_comments.py explain-sentiment \
  --csv FIA/YoutubeCommentsDataSet.csv --text-col Comment \
  --label-col Sentiment --target-label negative
```
Generates per comment: `polarity`, `severity`, `reasons`, `quoted_spans`, `brief` into CSV.

5) Rewrite/generate support replies
```bash
# Rewrite existing replies (column, e.g., SupportReply)
python FIA/generative-llm/generative_analyze_comments.py rewrite-replies \
  --csv FIA/YoutubeCommentsDataSet.csv --text-col Comment --reply-col SupportReply \
  --locale pt-PT --tone cordial

# Generate a reply when there is no replies column
python FIA/generative-llm/generative_analyze_comments.py rewrite-replies \
  --csv FIA/YoutubeCommentsDataSet.csv --text-col Comment \
  --locale pt-PT --tone cordial
```

Main parameters (CLI)
- `--csv` input CSV path (default: `FIA/YoutubeCommentsDataSet.csv`).
- `--text-col` text column name (default: `Comment`).
- `--output-dir` output folder (default: `FIA/generative-llm/output`).
- `--openai-model` OpenAI model (default: `gpt-4o-mini`).
- `--offline` force offline heuristics.
- `--sample N` process only N rows (faster iteration/cost control).
- Summarize:
  - `--group-col`, `--auto-topic`, `--topic-labels`, `--chunk-size` (default 40), `--max-items-per-group` (default 600).
- Classify:
  - `--labels`, `--few-shot`, `--few-shot-col`.
- Explain‑sentiment:
  - `--label-col`, `--target-label`.
- Rewrite‑replies:
  - `--reply-col`, `--locale` (default `pt-PT`), `--tone` (default `cordial`).

Generated outputs (by default in `FIA/generative-llm/output/`)
- `summaries_by_<group>.md` and `summaries_by_<group>.json` — bullets and summary per group (includes final synthesis and key points by group).
- `zero_few_shot_classification.csv` — copy of the processed dataset + columns `pred_label`, `pred_confidence`.
- `sentiment_explanations.csv` — columns: `Comment`, `polarity`, `severity`, `reasons`, `quoted_spans`, `brief`.
- `support_rewrites.csv` — columns: `Comment`, `OriginalReply` (if present), `PolishedReply`.

Cache and reproducibility
- File `FIA/generative-llm/.cache.jsonl` stores `{key, value}` pairs per line.
- The key is a SHA‑256 of a payload with `system`, `user`, `schema_hint`, `model` and the task name.
- Whenever the same request is repeated, the result is served from cache (reduces costs/latency and smooths rate limits).

Offline mode (no API key or no network)
- Activated automatically when `OPENAI_API_KEY` is absent or when `--offline` is used.
- Fallbacks:
  - Classification: simple keyword rule.
  - Summaries: synthetic/heuristic key points.
  - Explanations: sets `polarity`/`severity` and typical reasons.
  - Rewrite: short polite template response.
- Results are valid but less expressive than with a real LLM.

Performance and costs
- `--sample` limits the number of processed rows.
- Summarize uses 2 stages: micro‑summaries of blocks (`--chunk-size`) and a final synthesis (up to 50 micro‑summaries per group).
- `--max-items-per-group` limits items per group (default 600). Reduces tokens/cost.
- Few‑shot sampling is balanced per label when possible.
- Automatic retries (up to 3) with exponential backoff; the cache reduces repetition.

Best practices (privacy and keys)
- Avoid sending PII/sensitive data in prompts. Anonymize when possible.
- Do not commit `.env` files with keys to remote/public repos.
- In environments that don’t auto‑load `.env`, export variables before running the CLI.

Troubleshooting
- "CSV not found" → check `--csv` and relative path.
- "Text column does not exist" → confirm `--text-col` and the CSV header.
- "OPENAI_API_KEY not set" → export the variable or load `.env` manually.
- Empty/raw output → the model may have responded without valid JSON; the extractor tries the first `{...}` block; as a last resort it stores `raw`.

Additional notes
- This module is “generative”: it uses the LLM to produce/rewrite text and to decide labels. For non‑supervised analyses (clustering/dedup/anomalies without an LLM), see `FIA/unsupervised-models`.

