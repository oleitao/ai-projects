#!/usr/bin/env python3
import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

import sys


def _lazy_imports():
    try:
        import pandas as pd  # type: ignore
        import numpy as np  # type: ignore
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt  # type: ignore
    except Exception as e:
        print(
            "Missing dependencies. Please install pandas, numpy, matplotlib.\n"
            "e.g., pip install pandas numpy matplotlib",
            file=sys.stderr,
        )
        raise
    return pd, np, plt


DEFAULT_TS_CANDIDATES = [
    "timestamp",
    "date",
    "datetime",
    "created_at",
    "created_time",
    "published_at",
    "publishedAt",
    "time",
    "Date",
    "Timestamp",
]


SENTIMENT_CANDIDATES = [
    "sentiment_pred",
    "Sentiment",
    "sentiment",
]


@dataclass
class Config:
    input_csv: Path
    output_dir: Path
    timestamp_col: Optional[str]
    sentiment_col: Optional[str]
    resample_rule: str
    window: int
    z_threshold: float
    cohort_col: Optional[str]
    events_csv: Optional[Path]
    simulate_start: Optional[str]
    simulate_freq: str


def parse_args(argv: Optional[List[str]] = None) -> Config:
    here = Path(__file__).resolve().parent
    default_input = (here.parent / "YoutubeCommentsDataSet.csv").resolve()
    parser = argparse.ArgumentParser(
        description=(
            "Temporal analyses on YouTube comments: trends, alerts, cohorts.\n"
            "Requires a timestamp column; can simulate if not available."
        )
    )
    parser.add_argument(
        "--input-csv",
        type=Path,
        default=default_input,
        help="Path to input CSV (default: FIA/YoutubeCommentsDataSet.csv)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=(here / "output"),
        help="Directory for outputs (CSV and PNG)",
    )
    parser.add_argument(
        "--timestamp-col",
        type=str,
        default=None,
        help="Name of timestamp column (auto-detects if omitted)",
    )
    parser.add_argument(
        "--sentiment-col",
        type=str,
        default=None,
        help="Name of sentiment column (auto-detects if omitted)",
    )
    parser.add_argument(
        "--resample",
        type=str,
        default="W",
        help="Pandas resample rule: D (day), W (week), M (month), etc.",
    )
    parser.add_argument(
        "--window",
        type=int,
        default=4,
        help="Rolling window size (in resampled periods) for alerts",
    )
    parser.add_argument(
        "--z-threshold",
        type=float,
        default=2.0,
        help="Z-score threshold for negativity spikes",
    )
    parser.add_argument(
        "--cohort-col",
        type=str,
        default=None,
        help="Optional column to define cohorts (e.g., campaign, video_id)",
    )
    parser.add_argument(
        "--events-csv",
        type=Path,
        default=None,
        help="Optional CSV with events: name,date[,date_end]",
    )
    parser.add_argument(
        "--simulate-start",
        type=str,
        default=None,
        help=(
            "If no timestamp is present, simulate timestamps starting at this date"
            " (e.g., 2025-01-01). WARNING: for demo only, not analytical truth."
        ),
    )
    parser.add_argument(
        "--simulate-freq",
        type=str,
        default="D",
        help="Frequency for simulated timestamps when used (default: D)",
    )

    args = parser.parse_args(argv)
    return Config(
        input_csv=args.input_csv,
        output_dir=args.output_dir,
        timestamp_col=args.timestamp_col,
        sentiment_col=args.sentiment_col,
        resample_rule=args.resample,
        window=args.window,
        z_threshold=args.z_threshold,
        cohort_col=args.cohort_col,
        events_csv=args.events_csv,
        simulate_start=args.simulate_start,
        simulate_freq=args.simulate_freq,
    )


def detect_columns(df, ts_hint: Optional[str], sent_hint: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    cols = {c.lower(): c for c in df.columns}

    # Sentiment column
    sentiment_col = None
    if sent_hint and sent_hint in df.columns:
        sentiment_col = sent_hint
    else:
        for c in SENTIMENT_CANDIDATES:
            if c in df.columns:
                sentiment_col = c
                break
            if c.lower() in cols:
                sentiment_col = cols[c.lower()]
                break

    # Timestamp column
    ts_col = None
    if ts_hint and ts_hint in df.columns:
        ts_col = ts_hint
    else:
        for c in DEFAULT_TS_CANDIDATES:
            if c in df.columns:
                ts_col = c
                break
            if c.lower() in cols:
                ts_col = cols[c.lower()]
                break

    return ts_col, sentiment_col


def parse_timestamp_column(pd, df, ts_col: str):
    ts = pd.to_datetime(df[ts_col], errors="coerce", utc=True)
    if ts.isna().all():
        raise ValueError(
            f"Failed to parse any timestamps from column '{ts_col}'."
        )
    return ts


def ensure_timestamp(pd, np, df, cfg: Config) -> Tuple[object, str, bool]:
    ts_col, sentiment_col = detect_columns(df, cfg.timestamp_col, cfg.sentiment_col)
    simulated = False

    if ts_col is None:
        if cfg.simulate_start:
            n = len(df)
            start = pd.to_datetime(cfg.simulate_start, utc=True)
            # Assign monotonically increasing timestamps at the chosen frequency
            df["_simulated_ts"] = pd.date_range(start=start, periods=n, freq=cfg.simulate_freq)
            ts_col = "_simulated_ts"
            simulated = True
        else:
            msg = (
                "No timestamp column found. Provide --timestamp-col or add one of "
                f"{DEFAULT_TS_CANDIDATES}. Alternatively, use --simulate-start to "
                "simulate timestamps for demonstration only."
            )
            raise ValueError(msg)

    ts = parse_timestamp_column(pd, df, ts_col)
    df["_timestamp"] = ts

    if sentiment_col is None:
        raise ValueError(
            "No sentiment column found. Provide --sentiment-col or include one of "
            f"{SENTIMENT_CANDIDATES}."
        )
    df["_sentiment_raw"] = df[sentiment_col].astype(str).str.strip().str.lower()

    return df, sentiment_col, simulated


def map_sentiment_to_score(np, series):
    mapping = {
        "positive": 1.0,
        "pos": 1.0,
        "neg": -1.0,
        "negative": -1.0,
        "neu": 0.0,
        "neutral": 0.0,
        "0": 0.0,
        "1": 1.0,
        "-1": -1.0,
    }
    s = series.map(lambda x: mapping.get(str(x).lower(), np.nan))
    return s


def build_time_series(pd, np, df, cfg: Config):
    # Prepare sentiment flags
    df["_score"] = map_sentiment_to_score(np, df["_sentiment_raw"])  # may be NaN
    df["_is_pos"] = df["_sentiment_raw"].eq("positive") | df["_sentiment_raw"].eq("pos")
    df["_is_neg"] = df["_sentiment_raw"].eq("negative") | df["_sentiment_raw"].eq("neg")
    df["_is_neu"] = df["_sentiment_raw"].eq("neutral") | df["_sentiment_raw"].eq("neu")

    ts = df.set_index("_timestamp").sort_index()
    grp = ts.resample(cfg.resample_rule)

    agg = grp.agg(
        count=("_sentiment_raw", "size"),
        pos=("_is_pos", "sum"),
        neg=("_is_neg", "sum"),
        neu=("_is_neu", "sum"),
        avg_score=("_score", "mean"),
    )
    # Ratios
    agg["neg_ratio"] = agg["neg"].astype(float) / agg["count"].where(agg["count"] != 0, 1)
    agg["pos_ratio"] = agg["pos"].astype(float) / agg["count"].where(agg["count"] != 0, 1)

    return agg


def detect_spikes(pd, np, ts_df, cfg: Config):
    s = ts_df["neg_ratio"].fillna(0.0)
    roll_mean = s.rolling(window=cfg.window, min_periods=max(1, cfg.window // 2)).mean()
    roll_std = s.rolling(window=cfg.window, min_periods=max(1, cfg.window // 2)).std(ddof=0)
    z = (s - roll_mean) / roll_std.replace(0, np.nan)
    alerts = z >= cfg.z_threshold
    out = ts_df.copy()
    out["neg_ratio_z"] = z
    out["neg_spike_alert"] = alerts.fillna(False)
    return out


def cohort_analysis(pd, df, cfg: Config):
    if not cfg.cohort_col or cfg.cohort_col not in df.columns:
        return None
    # Aggregate sentiment by cohort
    df = df.copy()
    df["_score"] = map_sentiment_to_score(__import__("numpy"), df["_sentiment_raw"])  # quick import
    cohort_grp = (
        df.groupby(cfg.cohort_col)
        .agg(
            n=("_sentiment_raw", "size"),
            pos=("_sentiment_raw", lambda s: (s == "positive").sum()),
            neg=("_sentiment_raw", lambda s: (s == "negative").sum()),
            neu=("_sentiment_raw", lambda s: (s == "neutral").sum()),
            avg_score=("_score", "mean"),
        )
        .sort_values("n", ascending=False)
    )
    cohort_grp["neg_ratio"] = cohort_grp["neg"].astype(float) / cohort_grp["n"].where(cohort_grp["n"] != 0, 1)
    cohort_grp["pos_ratio"] = cohort_grp["pos"].astype(float) / cohort_grp["n"].where(cohort_grp["n"] != 0, 1)
    return cohort_grp


def plot_trends(plt, ts_df, out_dir: Path, title_suffix: str = ""):
    fig, ax1 = plt.subplots(figsize=(10, 5))
    ax1.plot(ts_df.index, ts_df["count"], label="total", color="#444")
    ax1.set_ylabel("Total comments", color="#444")
    ax1.tick_params(axis="y", labelcolor="#444")

    ax2 = ax1.twinx()
    ax2.plot(ts_df.index, ts_df["neg_ratio"], label="neg_ratio", color="#d62728")
    ax2.plot(ts_df.index, ts_df["pos_ratio"], label="pos_ratio", color="#2ca02c")
    ax2.set_ylabel("Ratios", color="#000")
    ax2.tick_params(axis="y", labelcolor="#000")

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left")
    ax1.set_title(f"Sentiment trends over time {title_suffix}")
    ax1.grid(True, linestyle=":", alpha=0.5)
    fig.tight_layout()
    out_path = out_dir / "trends.png"
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def plot_alerts(plt, ts_alerts, out_dir: Path):
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(ts_alerts.index, ts_alerts["neg_ratio"], color="#d62728", label="neg_ratio")
    spikes = ts_alerts[ts_alerts["neg_spike_alert"]]
    ax.scatter(spikes.index, spikes["neg_ratio"], color="#ff7f0e", label="alerts")
    ax.grid(True, linestyle=":", alpha=0.5)
    ax.set_title("Negativity spike alerts")
    ax.legend()
    fig.tight_layout()
    out_path = out_dir / "alerts.png"
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def maybe_overlay_events(pd, plt, ts_df, events_csv: Optional[Path], out_dir: Path):
    if not events_csv or not events_csv.exists():
        return
    try:
        ev = pd.read_csv(events_csv)
        if "date" not in ev.columns:
            return
        ev["date"] = pd.to_datetime(ev["date"], errors="coerce", utc=True)
        fig, ax = plt.subplots(figsize=(10, 4))
        ax.plot(ts_df.index, ts_df["neg_ratio"], color="#d62728", label="neg_ratio")
        for _, row in ev.iterrows():
            if pd.isna(row["date"]):
                continue
            label = str(row.get("name", "event"))
            ax.axvline(row["date"], color="#1f77b4", alpha=0.3)
            ax.text(row["date"], ax.get_ylim()[1], label, rotation=90, va="top", ha="right", fontsize=8)
        ax.set_title("Negativity with events overlay")
        ax.grid(True, linestyle=":", alpha=0.5)
        ax.legend()
        fig.tight_layout()
        out_path = out_dir / "neg_ratio_with_events.png"
        fig.savefig(out_path, dpi=150)
        plt.close(fig)
    except Exception:
        # Non-fatal if events overlay fails
        return


def main(argv: Optional[List[str]] = None) -> int:
    pd, np, plt = _lazy_imports()
    cfg = parse_args(argv)

    cfg.output_dir.mkdir(parents=True, exist_ok=True)

    if not cfg.input_csv.exists():
        print(f"Input CSV not found: {cfg.input_csv}", file=sys.stderr)
        return 2

    df = pd.read_csv(cfg.input_csv)

    # Ensure timestamp and sentiment
    try:
        df, sentiment_col, simulated = ensure_timestamp(pd, np, df, cfg)
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 3

    # Build resampled time series
    ts_df = build_time_series(pd, np, df, cfg)
    ts_df.to_csv(cfg.output_dir / "time_series.csv")

    # Alerts
    ts_alerts = detect_spikes(pd, np, ts_df, cfg)
    ts_alerts.to_csv(cfg.output_dir / "alerts.csv")

    # Plots
    title_suffix = "(simulated)" if simulated else ""
    plot_trends(plt, ts_df, cfg.output_dir, title_suffix)
    plot_alerts(plt, ts_alerts, cfg.output_dir)
    maybe_overlay_events(pd, plt, ts_df, cfg.events_csv, cfg.output_dir)

    # Cohorts (if available)
    cohort_df = cohort_analysis(pd, df, cfg)
    if cohort_df is not None:
        cohort_df.to_csv(cfg.output_dir / "cohorts.csv")

    # Brief console summary
    print("Output written to:", cfg.output_dir)
    if simulated:
        print("NOTE: timestamps were simulated; use real timestamps for valid temporal analyses.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

