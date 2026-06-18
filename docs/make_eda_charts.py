"""
make_eda_charts.py — render the EDA presentation's charts as PNGs from the real data.

Run:  py -3.12 docs/make_eda_charts.py
Out:  docs/eda_assets/*.png

Distribution charts load the train CSV; derived-metric charts use the verified numbers
from docs/EDA_DEEP_DIVE.md (extracted from the artifacts / computed by replaying the
production feature pipeline). Imported by build_eda_pptx.py (generate_all).
"""
from __future__ import annotations

import re
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import FuncFormatter

ROOT = Path(__file__).resolve().parent.parent
TRAIN_CSV = ROOT / "data" / "train" / "1900_2021_DISASTERS.xlsx - train data.csv"
ASSETS = Path(__file__).resolve().parent / "eda_assets"

# ── Palette (matches the deck) ────────────────────────────────────────────────
DEEP = "#0B3D2E"; GREEN = "#16A34A"; AMBER = "#F59E0B"; RED = "#DC2626"
SLATE = "#334155"; GREY = "#94A3B8"; LIGHT = "#F1F5F9"; BLUE = "#2563EB"
VALID = ["Flood", "Storm", "Earthquake", "Wildfire",
         "Volcanic activity", "Landslide", "Drought", "Extreme temperature"]

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 12,
    "axes.titlesize": 15, "axes.titleweight": "bold", "axes.titlecolor": DEEP,
    "axes.labelcolor": SLATE, "axes.edgecolor": "#CBD5E1",
    "xtick.color": SLATE, "ytick.color": SLATE,
    "axes.grid": True, "grid.alpha": 0.25, "grid.color": "#CBD5E1",
    "figure.facecolor": "white", "axes.facecolor": "white", "savefig.facecolor": "white",
})


def _load():
    df = pd.read_csv(TRAIN_CSV, encoding="latin-1", low_memory=False)
    df["Disaster Type"] = df["Disaster Type"].astype(str).str.strip()
    return df[df["Disaster Type"].isin(VALID)].copy()


def _save(fig, name):
    ASSETS.mkdir(parents=True, exist_ok=True)
    fig.savefig(ASSETS / name, dpi=150, bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)
    print("  wrote", name)


# ── 1. Class imbalance ────────────────────────────────────────────────────────
def chart_imbalance(df):
    counts = df["Disaster Type"].value_counts()
    fig, ax = plt.subplots(figsize=(8.2, 4.0))
    colors = [GREEN if c > 3000 else (BLUE if c > 700 else RED) for c in counts.values]
    bars = ax.bar(range(len(counts)), counts.values, color=colors)
    ax.set_xticks(range(len(counts)))
    ax.set_xticklabels(counts.index, rotation=30, ha="right", fontsize=11)
    ax.set_ylabel("training events")
    ax.set_title("8-class target distribution — 21:1 imbalance", color=DEEP)
    for b, v in zip(bars, counts.values):
        ax.text(b.get_x() + b.get_width() / 2, v + 60, f"{v:,}", ha="center",
                va="bottom", fontsize=10, color=SLATE, fontweight="bold")
    ax.annotate("Flood + Storm = 69%", xy=(0.5, 5000), xytext=(2.6, 5200),
                fontsize=11, color=DEEP, fontweight="bold")
    ax.margins(y=0.18); ax.grid(axis="x", alpha=0)
    _save(fig, "01_imbalance.png")


# ── 2. Impact skew (deaths) ───────────────────────────────────────────────────
def chart_skew(df):
    v = pd.to_numeric(df["Total Deaths"], errors="coerce"); v = v[v > 0]
    fig, ax = plt.subplots(figsize=(8.2, 4.0))
    ax.hist(np.log10(v + 1), bins=42, color=BLUE, alpha=0.85, edgecolor="white", linewidth=0.4)
    med, mean = np.median(v), v.mean()
    ax.axvline(np.log10(med + 1), color=GREEN, ls="--", lw=2.4, label=f"median = {med:,.0f}")
    ax.axvline(np.log10(mean + 1), color=RED, ls="--", lw=2.4, label=f"mean = {mean:,.0f}")
    ax.set_xlabel("log10(Total Deaths + 1)"); ax.set_ylabel("events")
    ax.set_title("Impact is right-skewed 263× (deaths) — why median, never mean", color=DEEP)
    ax.legend(fontsize=11, framealpha=0.95)
    ax.grid(axis="x", alpha=0)
    _save(fig, "02_skew.png")


# ── 3. Missingness ────────────────────────────────────────────────────────────
def chart_missingness(df):
    fields = [
        ("Country", "Country"), ("Start Month", "Start month"),
        ("Total Affected", "Total affected"), ("Total Deaths", "Deaths"),
        ("No Affected", "No. affected"), ("Total Damages ('000 US$)", "Damage"),
        ("Dis Mag Value", "Magnitude"), ("No Injured", "Injuries"),
        ("Latitude", "Latitude"), ("Insured Damages ('000 US$)", "Insured damage"),
    ]
    pres = [(lab, df[col].notna().mean() * 100) for col, lab in fields]
    pres.sort(key=lambda x: x[1])
    labels = [p[0] for p in pres]; vals = [p[1] for p in pres]
    colors = [RED if v < 40 else (AMBER if v < 75 else GREEN) for v in vals]
    fig, ax = plt.subplots(figsize=(8.0, 4.4))
    ax.barh(range(len(vals)), vals, color=colors)
    ax.set_yticks(range(len(vals))); ax.set_yticklabels(labels, fontsize=11)
    ax.set_xlim(0, 108); ax.set_xlabel("% present (8-type modeled subset, n = 14,476)")
    ax.set_title("Missingness — only ~19% have coordinates", color=DEEP)
    for i, v in enumerate(vals):
        ax.text(v + 1.5, i, f"{v:.1f}%", va="center", fontsize=10, color=SLATE, fontweight="bold")
    ax.grid(axis="y", alpha=0)
    _save(fig, "03_missingness.png")


# ── 4. Magnitude coverage by type ─────────────────────────────────────────────
def chart_magcov(df):
    rows = [(t, df[df["Disaster Type"] == t]["Dis Mag Value"].notna().mean() * 100) for t in VALID]
    rows.sort(key=lambda x: -x[1])
    labels = [r[0] for r in rows]; vals = [r[1] for r in rows]
    colors = [GREEN if v > 60 else (AMBER if v > 20 else RED) for v in vals]
    fig, ax = plt.subplots(figsize=(8.2, 4.0))
    bars = ax.bar(range(len(vals)), vals, color=colors)
    ax.set_xticks(range(len(vals)))
    ax.set_xticklabels(labels, rotation=30, ha="right", fontsize=10.5)
    ax.set_ylabel("% of events with a magnitude reading"); ax.set_ylim(0, 108)
    ax.set_title("Magnitude coverage is class-conditional (94% vs ~1%)", color=DEEP)
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v + 2, f"{v:.0f}%", ha="center",
                va="bottom", fontsize=10, color=SLATE, fontweight="bold")
    ax.grid(axis="x", alpha=0)
    _save(fig, "04_magcoverage.png")


# ── 5. THE THESIS — magnitude% vs F1 (r = 0.847) ──────────────────────────────
def chart_thesis(df):
    # verified per-class numbers (EDA_DEEP_DIVE §10)
    data = {  # type: (mag%, train_n, F1)
        "Earthquake": (94.2, 1544, 0.976), "Extreme temperature": (46.1, 603, 0.749),
        "Wildfire": (39.7, 471, 0.628), "Flood": (32.0, 5551, 0.778),
        "Storm": (25.0, 4496, 0.771), "Drought": (6.6, 770, 0.589),
        "Landslide": (1.2, 776, 0.482), "Volcanic activity": (1.1, 265, 0.668),
    }
    mag = np.array([v[0] for v in data.values()])
    n = np.array([v[1] for v in data.values()])
    f1 = np.array([v[2] for v in data.values()])
    r = np.corrcoef(mag, f1)[0, 1]
    fig, ax = plt.subplots(figsize=(8.6, 4.7))
    sizes = 120 + (n / n.max()) * 900
    ax.scatter(mag, f1, s=sizes, c=BLUE, alpha=0.55, edgecolors=DEEP, linewidths=1.2, zorder=3)
    z = np.polyfit(mag, f1, 1); xs = np.linspace(0, 100, 50)
    ax.plot(xs, z[0] * xs + z[1], "--", color=GREY, lw=2, zorder=2)
    # per-label offsets (dx, dy, ha) to avoid collisions
    off = {
        "Earthquake": (-2, 0.030, "right"), "Flood": (3.5, 0.020, "left"),
        "Storm": (3.5, -0.050, "left"), "Extreme temperature": (3, 0.022, "left"),
        "Wildfire": (3.5, 0.024, "left"), "Drought": (4.5, -0.012, "left"),
        "Landslide": (3.5, -0.050, "left"), "Volcanic activity": (3.5, 0.030, "left"),
    }
    for name, (m, nn, ff) in data.items():
        short = {"Extreme temperature": "Ext. temp", "Volcanic activity": "Volcanic"}.get(name, name)
        dx, dy, ha = off[name]
        ax.annotate(short, (m, ff), xytext=(m + dx, ff + dy), fontsize=10,
                    color=DEEP, fontweight="bold", ha=ha)
    ax.set_xlabel("% of events with a magnitude reading")
    ax.set_ylabel("per-class F1 (production v4.2)")
    ax.set_title("Data quality predicts accuracy", color=DEEP)
    ax.set_xlim(-8, 108); ax.set_ylim(0.4, 1.05)
    ax.text(0.03, 0.95, "bubble size = training volume", transform=ax.transAxes,
            ha="left", va="top", fontsize=9, color=GREY)
    ax.text(0.97, 0.10, f"r = {r:.3f}", transform=ax.transAxes, ha="right",
            fontsize=20, fontweight="bold", color=GREEN,
            bbox=dict(boxstyle="round,pad=0.4", fc=LIGHT, ec=GREEN, lw=1.5))
    _save(fig, "05_thesis_scatter.png")


# ── 6. Imbalance handling: strategy comparison ────────────────────────────────
def chart_strategies():
    strats = ["Hand-tuned\nweights (KEEP)", "SMOTE\n(discard)", "Balanced\ninv-freq (discard)"]
    macro = [0.7052, 0.6605, 0.6157]
    colors = [GREEN, GREY, GREY]
    fig, ax = plt.subplots(figsize=(8.0, 4.2))
    bars = ax.bar(range(3), macro, color=colors, width=0.6)
    ax.set_xticks(range(3)); ax.set_xticklabels(strats, fontsize=11)
    ax.set_ylim(0.5, 0.74); ax.set_ylabel("holdout macro-F1")
    ax.set_title("Resampling REGRESSED macro-F1 — weights win", color=DEEP)
    for b, v in zip(bars, macro):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.004, f"{v:.4f}", ha="center",
                va="bottom", fontsize=12, color=SLATE, fontweight="bold")
    ax.axhline(0.7052, color=GREEN, ls=":", lw=1.4, alpha=0.7)
    ax.grid(axis="x", alpha=0)
    _save(fig, "06_strategies.png")


# ── 7. Regressor fix: error-factor before/after (log scale) ───────────────────
def chart_regressors():
    targets = ["damage", "affected", "injuries", "deaths"]
    before = [111, 24, 9, 3]; after = [2.7, 4.3, 2.8, 1.9]
    y = np.arange(len(targets)); h = 0.38
    fig, ax = plt.subplots(figsize=(8.2, 4.2))
    ax.barh(y + h / 2, before, h, color=RED, label="original (global, fill-0)")
    ax.barh(y - h / 2, after, h, color=GREEN, label="per-type + drop-null")
    ax.set_yticks(y); ax.set_yticklabels(targets, fontsize=12)
    ax.set_xscale("log"); ax.set_xlim(1, 200)
    ax.set_xlabel("multiplicative error factor  (e^logMAE, lower = better, log scale)")
    ax.set_title("Per-type + drop-null cut impact error up to 111× → 2.7×", color=DEEP)
    for yi, (b, a) in enumerate(zip(before, after)):
        ax.text(b * 1.06, yi + h / 2, f"{b:g}×", va="center", fontsize=10, color=RED, fontweight="bold")
        ax.text(a * 1.06, yi - h / 2, f"{a:g}×", va="center", fontsize=10, color=GREEN, fontweight="bold")
    ax.legend(fontsize=10, loc="lower right", framealpha=0.95)
    ax.grid(axis="y", alpha=0)
    _save(fig, "07_regressors.png")


# ── 8. Contamination: CV vs contaminated holdout ──────────────────────────────
def chart_contamination():
    fig, ax = plt.subplots(figsize=(8.0, 4.2))
    labels = ["Honest 5-fold CV\n(within train)", "Contaminated holdout\n(100% overlap)"]
    vals = [0.586, 0.705]; colors = [GREEN, RED]
    bars = ax.bar(range(2), vals, color=colors, width=0.55)
    ax.set_xticks(range(2)); ax.set_xticklabels(labels, fontsize=11.5)
    ax.set_ylim(0, 0.85); ax.set_ylabel("macro-F1")
    ax.set_title("The reported 0.705 is an upper bound (~0.12 inflation)", color=DEEP)
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.012, f"{v:.3f}", ha="center",
                va="bottom", fontsize=14, color=SLATE, fontweight="bold")
    ax.annotate("", xy=(1, 0.705), xytext=(0, 0.586),
                arrowprops=dict(arrowstyle="<->", color=AMBER, lw=2.2))
    ax.text(0.5, 0.665, "+0.12\ngap", ha="center", fontsize=12, color=AMBER, fontweight="bold")
    ax.grid(axis="x", alpha=0)
    _save(fig, "08_contamination.png")


# ── 9. Model 1 per-class F1 scoreboard ────────────────────────────────────────
def chart_perclass_f1():
    data = [("Earthquake", 0.976), ("Flood", 0.778), ("Storm", 0.771),
            ("Extreme temp", 0.749), ("Volcanic", 0.668), ("Wildfire", 0.628),
            ("Drought", 0.589), ("Landslide", 0.482)]
    data.sort(key=lambda x: x[1])
    labels = [d[0] for d in data]; vals = [d[1] for d in data]
    colors = [RED if v < 0.6 else (AMBER if v < 0.72 else GREEN) for v in vals]
    fig, ax = plt.subplots(figsize=(8.2, 4.2))
    ax.barh(range(len(vals)), vals, color=colors)
    ax.set_yticks(range(len(vals))); ax.set_yticklabels(labels, fontsize=11.5)
    ax.set_xlim(0, 1.05); ax.set_xlabel("per-class F1 (holdout)")
    ax.set_title("Model 1 — per-class F1 (macro 0.705 vs weighted 0.759)", color=DEEP)
    ax.axvline(0.7052, color=BLUE, ls="--", lw=2, label="macro-F1 = 0.705")
    ax.axvline(0.7587, color="#9333EA", ls=":", lw=2, label="weighted-F1 = 0.759")
    for i, v in enumerate(vals):
        ax.text(v + 0.012, i, f"{v:.3f}", va="center", fontsize=10, color=SLATE, fontweight="bold")
    ax.legend(fontsize=10, loc="lower right", framealpha=0.95)
    ax.grid(axis="y", alpha=0)
    _save(fig, "09_perclass_f1.png")


# ── 10. Risk-level extreme imbalance (Model 3) ────────────────────────────────
def chart_risklevel():
    levels = ["Low", "Medium", "High", "Critical"]
    counts = [13994, 389, 65, 28]
    colors = ["#16A34A", "#FACC15", "#F97316", "#DC2626"]
    fig, ax = plt.subplots(figsize=(8.0, 4.0))
    bars = ax.bar(range(4), counts, color=colors, width=0.62)
    ax.set_yscale("log"); ax.set_ylim(10, 30000)
    ax.set_xticks(range(4)); ax.set_xticklabels(levels, fontsize=12)
    ax.set_ylabel("training events (log scale)")
    ax.set_title("Model 3 risk level — 96.7% 'Low' (≈510:1)", color=DEEP)
    for b, v in zip(bars, counts):
        ax.text(b.get_x() + b.get_width() / 2, v * 1.15, f"{v:,}", ha="center",
                va="bottom", fontsize=11, color=SLATE, fontweight="bold")
    ax.grid(axis="x", alpha=0)
    _save(fig, "10_risklevel.png")


def generate_all(_assets=None):
    df = _load()
    chart_imbalance(df); chart_skew(df); chart_missingness(df); chart_magcov(df)
    chart_thesis(df); chart_strategies(); chart_regressors(); chart_contamination()
    chart_perclass_f1(); chart_risklevel()
    print(f"All charts -> {ASSETS}")


if __name__ == "__main__":
    print("Rendering EDA charts...")
    generate_all()
