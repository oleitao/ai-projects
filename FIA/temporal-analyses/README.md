Temporal Analyses (Trends and Alerts) — YouTube Comments

This module generates sentiment time series, detects spikes in negativity, and (optionally) aggregates by cohorts. It works with real timestamps or, for demonstration, with simulated timestamps.

Directory contents
- `FIA/temporal-analyses/temporal_analysis.py` — CLI with logic for trends, alerts, cohorts, and charts.
- `FIA/temporal-analyses/requirements.txt` — dependencies: pandas, numpy, matplotlib.
- `FIA/temporal-analyses/events_example.csv` — example events CSV for overlay.
- `FIA/temporal-analyses/output/` — folder where outputs (CSV/PNG) are saved.

What it does
- Trends: resamples by day/week/month and computes:
  - `count`, `pos`, `neg`, `neu`, `avg_score` (mean score) and ratios `pos_ratio`, `neg_ratio`.
  - Score maps `positive→+1`, `negative→-1`, `neutral→0` (also accepts `pos/neg/neu` or numeric `1/0/-1`).
- Alerts: applies rolling z‑score to `neg_ratio` and flags spikes above a threshold.
- Cohorts: aggregates by a column (e.g., `campaign`, `video_id`) when specified.
- Charts: generates `trends.png` and `alerts.png`; optionally `neg_ratio_with_events.png` if an events CSV is provided.

Inputs
- Default dataset: `FIA/YoutubeCommentsDataSet.csv`.
  - Requires a timestamp column for real analysis. Auto‑detects common names: `timestamp`, `date`, `datetime`, `created_at`, `published_at`, `time`, …
  - Sentiment column auto‑detected among: `sentiment_pred`, `Sentiment`, `sentiment`.
- Events CSV (optional): `name,date[,date_end]` — draws vertical lines on charts (`date` is required).

No timestamps in the CSV?
- Options:
  1) Add a real timestamp column (recommended), e.g., `published_at` with ISO datetimes.
  2) Simulate for demos: use `--simulate-start YYYY-MM-DD` (and `--simulate-freq`, default `D`). Images and titles will be marked as “(simulated)”.

How it works (pipeline)
1) Load CSV and try to detect timestamp and sentiment columns (or use the provided flags).
2) Convert the timestamp column to `datetime` (UTC). If missing and requested, simulate sequential timestamps.
3) Map sentiment to score and binary flags (`_is_pos`, `_is_neg`, `_is_neu`).
4) Resample (`--resample`) and aggregate metrics; compute ratios.
5) Compute rolling z‑scores for `neg_ratio` (window `--window`) and flag `neg_spike_alert` when `z ≥ --z-threshold`.
6) Generate CSVs and charts; if `--events-csv` is present, overlay events.

Parameters (CLI)
- `--input-csv` input CSV (default: `FIA/YoutubeCommentsDataSet.csv`).
- `--output-dir` output folder (default: `FIA/temporal-analyses/output`).
- `--timestamp-col` timestamp column name (auto‑detected if omitted).
- `--sentiment-col` sentiment column name (auto‑detected if omitted).
- `--resample` pandas rule (`D`, `W`, `M`, …). Default: `W`.
- `--window` rolling window size. Default: 4 resampled periods.
- `--z-threshold` threshold for negativity spikes. Default: 2.0.
- `--cohort-col` column for cohort aggregation (optional).
- `--events-csv` events CSV with columns `name,date[,date_end]` (optional; uses `date` only).
- `--simulate-start` start date to simulate timestamps (for demo, when no timestamp column).
- `--simulate-freq` simulation frequency (default `D`).

Outputs (in `FIA/temporal-analyses/output`)
- `time_series.csv` — resampled time index with columns: `count`, `pos`, `neg`, `neu`, `avg_score`, `neg_ratio`, `pos_ratio`.
- `alerts.csv` — `neg_ratio`, `neg_ratio_z` and `neg_spike_alert` (boolean) per period.
- `trends.png` — lines of `count`, `pos_ratio` and `neg_ratio` over time.
- `alerts.png` — `neg_ratio` with markers on flagged periods.
- `neg_ratio_with_events.png` — `neg_ratio` with vertical event lines (if `--events-csv`).
- `cohorts.csv` — aggregates by cohort when `--cohort-col` is provided (includes `n`, `pos`, `neg`, `neu`, `avg_score`, `pos_ratio`, `neg_ratio`).

Examples (repo root)
- No timestamps (simulated) with weekly base:
  - `python FIA/temporal-analyses/temporal_analysis.py --simulate-start 2025-01-01 --resample W`
- With a real timestamp column (e.g., `published_at`):
  - `python FIA/temporal-analyses/temporal_analysis.py --timestamp-col published_at --resample W`
- Events overlay:
  - `python FIA/temporal-analyses/temporal_analysis.py --simulate-start 2025-01-01 --events-csv FIA/temporal-analyses/events_example.csv`
- Cohorts by campaign:
  - `python FIA/temporal-analyses/temporal_analysis.py --timestamp-col published_at --cohort-col campaign --resample W`
- Use enriched dataset (with `sentiment_pred`):
  - `python FIA/temporal-analyses/temporal_analysis.py --input-csv FIA/supervised-models/YoutubeCommentsDataSet_enriched.csv --simulate-start 2025-01-01`

Quick install
- Activate venv and install dependencies:
  - `source .venv/bin/activate`
  - `pip install -r FIA/temporal-analyses/requirements.txt`

Notes and best practices
- The spike detector uses a rolling window and z‑score; adjust `--window` and `--z-threshold` according to seasonality/noise.
- Use real timestamps for decisions; simulation is for tests/demos only and may distort seasonality.
- Matplotlib uses the `Agg` backend (no GUI window; only saves PNGs).
- For large datasets, resampling to `W`/`M` reduces noise and plotting cost.

Troubleshooting
- “Input CSV not found” → check `--input-csv`.
- “No timestamp column found …” → provide `--timestamp-col` or use `--simulate-start` (demo only).
- “No sentiment column found …” → confirm that `sentiment_pred`, `Sentiment` exists or pass `--sentiment-col`.
- “Failed to parse any timestamps …” → validate the timestamp format (use ISO 8601; the parser uses `errors='coerce'`).

