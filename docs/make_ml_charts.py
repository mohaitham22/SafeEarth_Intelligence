"""
make_ml_charts.py — render the ML-deep-dive presentation's charts as PNGs.

Run:  py -3.12 docs/make_ml_charts.py
Out:  docs/ml_assets/*.png

Every number is from docs/ML_DEEP_DIVE.md, which was extracted from this project's own
metric files (metrics/*.json), saved bundles (backend/saved_models/*.pkl), and reproducible
runs (benchmark_models.py, print_confusion.py) re-run 2026-06-15. Imported by
build_ml_pptx.py (generate_all). No data file is required — all values are hard-coded from
the verified deep-dive so the deck is reproducible offline.
"""
from __future__ import annotations

import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap

ASSETS = Path(__file__).resolve().parent / "ml_assets"

# ── Palette (matches the deck) ────────────────────────────────────────────────
DEEP = "#0B3D2E"; GREEN = "#16A34A"; AMBER = "#F59E0B"; RED = "#DC2626"
SLATE = "#334155"; GREY = "#94A3B8"; LIGHT = "#F1F5F9"; BLUE = "#2563EB"; PURPLE = "#9333EA"

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 12,
    "axes.titlesize": 15, "axes.titleweight": "bold", "axes.titlecolor": DEEP,
    "axes.labelcolor": SLATE, "axes.edgecolor": "#CBD5E1",
    "xtick.color": SLATE, "ytick.color": SLATE,
    "axes.grid": True, "grid.alpha": 0.25, "grid.color": "#CBD5E1",
    "figure.facecolor": "white", "axes.facecolor": "white", "savefig.facecolor": "white",
})


def _save(fig, name):
    ASSETS.mkdir(parents=True, exist_ok=True)
    fig.savefig(ASSETS / name, dpi=150, bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)
    print("  wrote", name)


# ── 1. Candidate classifier sweep — model family is the lever ─────────────────
def chart_candidates():
    # benchmark_models.py, 10-feature set, no weights, resub holdout n=13,070
    names = ["Logistic\nRegression", "Random\nForest", "XGBoost\n(300,d6)", "XGBoost\n(500,d8,reg)"]
    macro = [0.1374, 0.7000, 0.7020, 0.7038]
    colors = [RED, BLUE, BLUE, GREEN]
    fig, ax = plt.subplots(figsize=(8.4, 4.3))
    bars = ax.bar(range(4), macro, color=colors, width=0.62)
    ax.set_xticks(range(4)); ax.set_xticklabels(names, fontsize=11)
    ax.set_ylim(0, 0.82); ax.set_ylabel("macro-F1 (resub holdout)")
    ax.set_title("Model FAMILY is the lever: linear collapses, trees cluster at ~0.70", color=DEEP)
    for b, v in zip(bars, macro):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.012, f"{v:.3f}", ha="center",
                va="bottom", fontsize=12, color=SLATE, fontweight="bold")
    ax.axhline(0.1292, color=GREY, ls="--", lw=1.6)
    ax.text(3.45, 0.145, "stratified dummy 0.129", ha="right", fontsize=9.5, color=GREY)
    ax.annotate("≈ dummy", xy=(0, 0.1374), xytext=(0.55, 0.30),
                fontsize=11, color=RED, fontweight="bold",
                arrowprops=dict(arrowstyle="->", color=RED, lw=1.6))
    ax.grid(axis="x", alpha=0)
    _save(fig, "01_candidates.png")


# ── 2. Ensemble members + why LightGBM was dropped ────────────────────────────
def chart_ensemble():
    names = ["LightGBM\n(dropped)", "CatBoost", "XGBoost", "Ensemble\nv4.1\n(X·L·C)", "Ensemble\nv4.2\n(X·C) ✓"]
    macro = [0.6540, 0.6817, 0.6939, 0.6929, 0.7052]
    colors = [RED, BLUE, BLUE, GREY, GREEN]
    fig, ax = plt.subplots(figsize=(8.6, 4.3))
    bars = ax.bar(range(5), macro, color=colors, width=0.62)
    ax.set_xticks(range(5)); ax.set_xticklabels(names, fontsize=10.5)
    ax.set_ylim(0.62, 0.72); ax.set_ylabel("macro-F1 (resub holdout)")
    ax.set_title("LightGBM is the weakest member → weight 0.00 → dropped (v4.2 = XGB·0.6 + CAT·0.4)", color=DEEP, fontsize=13.5)
    for b, v in zip(bars, macro):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.0015, f"{v:.4f}", ha="center",
                va="bottom", fontsize=11.5, color=SLATE, fontweight="bold")
    ax.axhline(0.7052, color=GREEN, ls=":", lw=1.4, alpha=0.7)
    ax.grid(axis="x", alpha=0)
    _save(fig, "02_ensemble.png")


# ── 3. Per-class F1 — resub vs honest CV (the memorization gap) ────────────────
def chart_resub_vs_cv():
    # ML_DEEP_DIVE §6a per-class table
    data = [  # class, resub F1, CV F1
        ("Earthquake", 0.976, 0.964), ("Flood", 0.778, 0.708),
        ("Storm", 0.771, 0.736), ("Extreme temp", 0.749, 0.656),
        ("Volcanic", 0.668, 0.413), ("Wildfire", 0.628, 0.470),
        ("Drought", 0.589, 0.419), ("Landslide", 0.482, 0.320),
    ]
    data.sort(key=lambda d: d[2])  # by CV ascending
    labels = [d[0] for d in data]
    resub = np.array([d[1] for d in data]); cv = np.array([d[2] for d in data])
    y = np.arange(len(labels)); h = 0.38
    fig, ax = plt.subplots(figsize=(8.8, 4.8))
    ax.barh(y + h / 2, resub, h, color=RED, alpha=0.85, label="resub (test ⊂ train)")
    ax.barh(y - h / 2, cv, h, color=GREEN, label="honest 5-fold CV")
    ax.set_yticks(y); ax.set_yticklabels(labels, fontsize=11.5)
    ax.set_xlim(0, 1.08); ax.set_xlabel("per-class F1")
    ax.set_title("The memorization gap: minority classes are far weaker out-of-fold", color=DEEP)
    for yi, (r, c) in enumerate(zip(resub, cv)):
        ax.text(r + 0.012, yi + h / 2, f"{r:.2f}", va="center", fontsize=9, color=RED, fontweight="bold")
        ax.text(c + 0.012, yi - h / 2, f"{c:.2f}", va="center", fontsize=9, color=GREEN, fontweight="bold")
    ax.axvline(0.705, color=RED, ls=":", lw=1.3, alpha=0.6)
    ax.axvline(0.586, color=GREEN, ls=":", lw=1.3, alpha=0.6)
    ax.legend(fontsize=10, loc="lower right", framealpha=0.95)
    ax.grid(axis="y", alpha=0)
    _save(fig, "03_resub_vs_cv.png")


# ── 4. Floor & ceiling — dummy → honest CV → contaminated holdout ─────────────
def chart_floor_ceiling():
    labels = ["Majority\ndummy", "Stratified\ndummy", "Honest\n5-fold CV", "Contaminated\nholdout"]
    vals = [0.0719, 0.1292, 0.586, 0.705]
    colors = [GREY, GREY, GREEN, RED]
    fig, ax = plt.subplots(figsize=(8.4, 4.3))
    bars = ax.bar(range(4), vals, color=colors, width=0.6)
    ax.set_xticks(range(4)); ax.set_xticklabels(labels, fontsize=11)
    ax.set_ylim(0, 0.82); ax.set_ylabel("macro-F1")
    ax.set_title("Floor (dummy 0.07–0.13) · honest estimate (0.586) · inflated ceiling (0.705)", color=DEEP, fontsize=13.5)
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.012, f"{v:.3f}", ha="center",
                va="bottom", fontsize=12.5, color=SLATE, fontweight="bold")
    ax.annotate("", xy=(3, 0.705), xytext=(2, 0.586),
                arrowprops=dict(arrowstyle="<->", color=AMBER, lw=2.2))
    ax.text(2.5, 0.665, "+0.12\nmemorization", ha="center", fontsize=10.5, color=AMBER, fontweight="bold")
    ax.grid(axis="x", alpha=0)
    _save(fig, "04_floor_ceiling.png")


# ── 5. Confusion matrix (deployed v4.2, real counts, row-normalized colour) ────
def chart_confusion():
    classes = ["Drought", "Earthquake", "Ext. temp", "Flood", "Landslide", "Storm", "Volcanic", "Wildfire"]
    cm = np.array([
        [520, 0, 3, 76, 21, 52, 5, 8],
        [1, 1110, 2, 12, 3, 5, 4, 0],
        [21, 2, 404, 48, 23, 71, 1, 14],
        [299, 14, 38, 3919, 328, 565, 52, 57],
        [30, 1, 3, 168, 395, 103, 9, 4],
        [171, 0, 39, 518, 131, 3074, 14, 58],
        [7, 2, 2, 17, 18, 17, 157, 2],
        [31, 8, 4, 47, 6, 78, 6, 272],
    ], dtype=float)
    row_norm = cm / cm.sum(axis=1, keepdims=True)
    cmap = LinearSegmentedColormap.from_list("g", ["#FFFFFF", "#86EFAC", GREEN, DEEP])
    fig, ax = plt.subplots(figsize=(8.8, 6.0))
    ax.imshow(row_norm, cmap=cmap, vmin=0, vmax=1, aspect="auto")
    ax.set_xticks(range(8)); ax.set_xticklabels(classes, rotation=40, ha="right", fontsize=10)
    ax.set_yticks(range(8)); ax.set_yticklabels(classes, fontsize=10)
    ax.set_xlabel("predicted"); ax.set_ylabel("true")
    ax.set_title("Confusion matrix (v4.2) — Earthquake clean, hydro-met cluster bleeds", color=DEEP, fontsize=13.5)
    for i in range(8):
        for j in range(8):
            v = int(cm[i, j])
            if v == 0:
                continue
            ax.text(j, i, f"{v:,}", ha="center", va="center", fontsize=8.5,
                    color="white" if row_norm[i, j] > 0.5 else SLATE,
                    fontweight="bold" if i == j else "normal")
    ax.set_xticks(np.arange(-.5, 8, 1), minor=True)
    ax.set_yticks(np.arange(-.5, 8, 1), minor=True)
    ax.grid(which="minor", color="#E2E8F0", linewidth=0.8); ax.grid(which="major", alpha=0)
    ax.tick_params(which="minor", length=0)
    _save(fig, "05_confusion.png")


# ── 6. Regression — per-type + drop-null error-factor cut (log scale) ──────────
def chart_reg_factors():
    targets = ["damage", "affected", "injuries", "deaths"]
    before = [111, 24.5, 8.95, 2.84]   # global + fill-0  (e^logMAE)
    after = [2.66, 4.29, 2.77, 1.88]   # per-type + drop-null
    y = np.arange(len(targets)); h = 0.38
    fig, ax = plt.subplots(figsize=(8.4, 4.3))
    ax.barh(y + h / 2, before, h, color=RED, label="original (global, fill-0)")
    ax.barh(y - h / 2, after, h, color=GREEN, label="per-type + drop-null (deployed)")
    ax.set_yticks(y); ax.set_yticklabels(targets, fontsize=12)
    ax.set_xscale("log"); ax.set_xlim(1, 220)
    ax.set_xlabel("multiplicative error factor  (e^logMAE, lower = better, log scale)")
    ax.set_title("Un-poisoning the targets: impact error cut up to 111× → 2.7×", color=DEEP)
    for yi, (b, a) in enumerate(zip(before, after)):
        ax.text(b * 1.07, yi + h / 2, f"{b:g}×", va="center", fontsize=10, color=RED, fontweight="bold")
        ax.text(a * 1.07, yi - h / 2, f"{a:g}×", va="center", fontsize=10, color=GREEN, fontweight="bold")
    ax.legend(fontsize=10, loc="lower right", framealpha=0.95)
    ax.grid(axis="y", alpha=0)
    _save(fig, "06_reg_factors.png")


# ── 7. Regression raw-unit R² ≈ 0 — the signal ceiling ─────────────────────────
def chart_reg_r2():
    targets = ["deaths", "injuries", "affected", "damage"]
    r2 = [0.0202, 0.0151, 0.0158, 0.0142]   # best model per target (XGB), raw units, resub
    fig, ax = plt.subplots(figsize=(8.4, 4.2))
    bars = ax.bar(range(4), r2, color=RED, width=0.55)
    ax.set_xticks(range(4)); ax.set_xticklabels(targets, fontsize=12)
    ax.set_ylim(0, 1.0); ax.set_ylabel("raw-unit R²  (best model, in-sample)")
    ax.set_title("Impact magnitude is unpredictable from these features: raw R² ≈ 0.01–0.02", color=DEEP, fontsize=13)
    for b, v in zip(bars, r2):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.02, f"{v:.3f}", ha="center",
                va="bottom", fontsize=12, color=SLATE, fontweight="bold")
    ax.axhline(1.0, color=GREEN, ls="--", lw=1.4, alpha=0.6)
    ax.text(3.45, 0.93, "perfect fit = 1.0", ha="right", fontsize=10, color=GREEN)
    ax.annotate("signal ceiling:\nfeatures don't determine magnitude\n(exposure / GDP / population missing)",
                xy=(1.5, 0.05), xytext=(1.2, 0.55), fontsize=10.5, color=DEEP, fontweight="bold",
                ha="center")
    ax.grid(axis="x", alpha=0)
    _save(fig, "07_reg_r2.png")


# ── 8. Feature importance (deployed v4.2 XGBoost gain) ─────────────────────────
def chart_importance():
    feats = ["dis_mag_value", "has_magnitude", "continent_enc", "abs_latitude", "latitude",
             "historical_freq", "lon_cos", "region_enc", "log_hist_freq", "longitude",
             "lon_sin", "month_cos", "month_sin", "decade", "country_enc", "day_offset"]
    gain = [25.6, 20.1, 10.5, 4.5, 4.3, 4.2, 4.1, 4.0, 3.7, 3.5, 3.5, 3.3, 3.1, 2.9, 2.7, 0.0]
    order = np.argsort(gain)
    feats = [feats[i] for i in order]; gain = [gain[i] for i in order]
    colors = [AMBER if g >= 20 else (BLUE if g >= 10 else (RED if g == 0 else SLATE)) for g in gain]
    fig, ax = plt.subplots(figsize=(8.6, 5.2))
    ax.barh(range(len(gain)), gain, color=colors)
    ax.set_yticks(range(len(gain))); ax.set_yticklabels(feats, fontsize=10.5)
    ax.set_xlim(0, 30); ax.set_xlabel("XGBoost gain importance (%)")
    ax.set_title("Two magnitude features = 45.7% of gain · day_offset = 0.0% (dead)", color=DEEP, fontsize=13.5)
    for i, v in enumerate(gain):
        ax.text(v + 0.4, i, f"{v:.1f}%", va="center", fontsize=9.5, color=SLATE, fontweight="bold")
    ax.grid(axis="y", alpha=0)
    _save(fig, "08_importance.png")


def generate_all(_assets=None):
    chart_candidates(); chart_ensemble(); chart_resub_vs_cv(); chart_floor_ceiling()
    chart_confusion(); chart_reg_factors(); chart_reg_r2(); chart_importance()
    print(f"All ML charts -> {ASSETS}")


if __name__ == "__main__":
    print("Rendering ML charts...")
    generate_all()
