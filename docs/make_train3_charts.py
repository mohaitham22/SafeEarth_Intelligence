"""
make_train3_charts.py — render charts for the notebook-07 (train3 impact-evaluation) deck.

Run:  py -3.12 docs/make_train3_charts.py
Out:  docs/train3_assets/*.png

Every number below is from the EXECUTED notebook
(notebooks/07_train3_impact_evaluation.ipynb, Optuna ON, run 2026-06-19) — the tuned
soft-voting ensemble + boosted per-type/drop-null regressors on the held-out 20% stratified
test split of data/train 3/disasters_8types_enriched.csv. The confusion matrix and SHAP
importances come from docs/_train3_extra.json (a curated-default reproduction; the class
structure and feature ranking are stable w.r.t. tuning).
"""
from __future__ import annotations
import json, warnings
from pathlib import Path
warnings.filterwarnings("ignore")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LinearSegmentedColormap

ASSETS = Path(__file__).resolve().parent / "train3_assets"
EXTRA = Path(__file__).resolve().parent / "_train3_extra.json"

DEEP = "#0B3D2E"; GREEN = "#16A34A"; AMBER = "#F59E0B"; RED = "#DC2626"
SLATE = "#334155"; GREY = "#94A3B8"; LIGHT = "#F1F5F9"; BLUE = "#2563EB"

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 12,
    "axes.titlesize": 14.5, "axes.titleweight": "bold", "axes.titlecolor": DEEP,
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


# ── 1. Class distribution / 21:1 imbalance ─────────────────────────────────────
def chart_imbalance():
    names = ["Flood", "Storm", "Earthquake", "Landslide", "Drought", "Extreme\ntemp", "Wildfire", "Volcanic"]
    n = [5551, 4496, 1544, 776, 770, 603, 471, 265]
    colors = [BLUE, BLUE, GREEN, AMBER, AMBER, AMBER, RED, RED]
    fig, ax = plt.subplots(figsize=(8.6, 4.3))
    bars = ax.bar(range(8), n, color=colors, width=0.66)
    ax.set_xticks(range(8)); ax.set_xticklabels(names, fontsize=10.5)
    ax.set_ylabel("events in dataset"); ax.set_ylim(0, 6100)
    ax.set_title("8 classes, 14,476 events — a 21:1 imbalance (Flood : Volcanic)", color=DEEP)
    for b, v in zip(bars, n):
        ax.text(b.get_x() + b.get_width() / 2, v + 90, f"{v:,}", ha="center",
                va="bottom", fontsize=10, color=SLATE, fontweight="bold")
    ax.annotate("21:1", xy=(7, 265), xytext=(6.3, 2300), fontsize=13, color=RED, fontweight="bold",
                ha="center", arrowprops=dict(arrowstyle="->", color=RED, lw=1.6))
    ax.grid(axis="x", alpha=0)
    _save(fig, "01_imbalance.png")


# ── 2. Classifier scoreboard — macro-F1 per model ──────────────────────────────
def chart_clf_scoreboard():
    names = ["CatBoost", "LightGBM", "XGBoost", "Ensemble\n(0.3·X 0.1·L 0.6·C) ✓"]
    macro = [0.6812, 0.6834, 0.6874, 0.6885]
    colors = [BLUE, BLUE, BLUE, GREEN]
    fig, ax = plt.subplots(figsize=(8.6, 4.3))
    bars = ax.bar(range(4), macro, color=colors, width=0.6)
    ax.set_xticks(range(4)); ax.set_xticklabels(names, fontsize=10.5)
    ax.set_ylim(0.66, 0.695); ax.set_ylabel("macro-F1 (held-out 20% test)")
    ax.set_title("Members cluster at 0.681–0.687 — ensemble nudges to 0.6885", color=DEEP)
    for b, v in zip(bars, macro):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.0004, f"{v:.4f}", ha="center",
                va="bottom", fontsize=11.5, color=SLATE, fontweight="bold")
    ax.axhline(0.6885, color=GREEN, ls=":", lw=1.3, alpha=0.7)
    ax.grid(axis="x", alpha=0)
    _save(fig, "02_clf_scoreboard.png")


# ── 3. Per-class F1 (ensemble) ─────────────────────────────────────────────────
def chart_per_class_f1():
    data = [  # class, F1, support
        ("Volcanic activity", 0.412, 53), ("Landslide", 0.425, 155), ("Wildfire", 0.543, 94),
        ("Extreme temperature", 0.728, 121), ("Flood", 0.786, 1111), ("Storm", 0.790, 899),
        ("Drought", 0.838, 154), ("Earthquake", 0.987, 309),
    ]
    labels = [d[0] for d in data]; f1 = [d[1] for d in data]; sup = [d[2] for d in data]
    colors = [RED if v < 0.5 else (AMBER if v < 0.73 else GREEN) for v in f1]
    fig, ax = plt.subplots(figsize=(8.8, 4.8))
    bars = ax.barh(range(len(labels)), f1, color=colors)
    ax.set_yticks(range(len(labels))); ax.set_yticklabels(labels, fontsize=11)
    ax.set_xlim(0, 1.12); ax.set_xlabel("F1 (ensemble, held-out test)")
    ax.set_title("Earthquake near-perfect · minorities collapse (small support)", color=DEEP)
    for i, (v, s) in enumerate(zip(f1, sup)):
        ax.text(v + 0.012, i, f"{v:.3f}  (n={s})", va="center", fontsize=9.5, color=SLATE, fontweight="bold")
    ax.axvline(0.6885, color=GREEN, ls=":", lw=1.3, alpha=0.6)
    ax.text(0.6885, 7.6, " macro 0.689", color=GREEN, fontsize=9, fontweight="bold")
    ax.grid(axis="y", alpha=0)
    _save(fig, "03_per_class_f1.png")


# ── 4. Confusion matrix (row-normalized) ───────────────────────────────────────
def chart_confusion():
    extra = json.loads(EXTRA.read_text())
    classes = ["Drought", "Earthquake", "Ext. temp", "Flood", "Landslide", "Storm", "Volcanic", "Wildfire"]
    cm = np.array(extra["confusion"], dtype=float)
    row = cm / cm.sum(axis=1, keepdims=True)
    cmap = LinearSegmentedColormap.from_list("g", ["#FFFFFF", "#86EFAC", GREEN, DEEP])
    fig, ax = plt.subplots(figsize=(8.6, 5.9))
    ax.imshow(row, cmap=cmap, vmin=0, vmax=1, aspect="auto")
    ax.set_xticks(range(8)); ax.set_xticklabels(classes, rotation=40, ha="right", fontsize=10)
    ax.set_yticks(range(8)); ax.set_yticklabels(classes, fontsize=10)
    ax.set_xlabel("predicted"); ax.set_ylabel("true")
    ax.set_title("Confusion matrix — Earthquake clean, hydro-met cluster bleeds", color=DEEP, fontsize=13.5)
    for i in range(8):
        for j in range(8):
            v = int(cm[i, j])
            if v == 0:
                continue
            ax.text(j, i, f"{v:,}", ha="center", va="center", fontsize=9,
                    color="white" if row[i, j] > 0.5 else SLATE,
                    fontweight="bold" if i == j else "normal")
    ax.set_xticks(np.arange(-.5, 8, 1), minor=True)
    ax.set_yticks(np.arange(-.5, 8, 1), minor=True)
    ax.grid(which="minor", color="#E2E8F0", linewidth=0.8); ax.grid(which="major", alpha=0)
    ax.tick_params(which="minor", length=0)
    _save(fig, "04_confusion.png")


# ── 5. Regression error factors (boosted, final) ───────────────────────────────
def chart_reg_factors():
    targets = ["deaths", "damage", "uninsured", "injuries", "affected"]
    factor = [2.71, 5.02, 5.08, 3.89, 6.57]
    r2log = [0.429, 0.370, 0.368, 0.228, 0.421]
    order = np.argsort(factor)
    targets = [targets[i] for i in order]; factor = [factor[i] for i in order]; r2log = [r2log[i] for i in order]
    colors = [GREEN if f < 4 else (AMBER if f < 6 else RED) for f in factor]
    fig, ax = plt.subplots(figsize=(8.6, 4.4))
    bars = ax.barh(range(len(targets)), factor, color=colors)
    ax.set_yticks(range(len(targets))); ax.set_yticklabels(targets, fontsize=12)
    ax.set_xlim(0, 8); ax.set_xlabel("typical ×-error  (e^logMAE, lower = better)")
    ax.set_title("Impact accuracy — final boosted regressors (honest holdout)", color=DEEP)
    for i, (f, r) in enumerate(zip(factor, r2log)):
        ax.text(f + 0.1, i, f"{f:.2f}×   (R²_log={r:+.2f})", va="center", fontsize=10, color=SLATE, fontweight="bold")
    ax.grid(axis="y", alpha=0)
    _save(fig, "05_reg_factors.png")


# ── 6. Raw R² ≈ 0 vs log R² — the signal ceiling ───────────────────────────────
def chart_reg_r2():
    targets = ["deaths", "injuries", "affected", "damage", "uninsured"]
    r2_raw = [0.314, -0.001, 0.046, 0.047, 0.050]
    r2_log = [0.429, 0.228, 0.421, 0.370, 0.368]
    y = np.arange(len(targets)); h = 0.38
    fig, ax = plt.subplots(figsize=(8.6, 4.4))
    ax.barh(y + h / 2, r2_raw, h, color=RED, label="raw-unit R² (magnitude)")
    ax.barh(y - h / 2, r2_log, h, color=GREEN, label="log-space R² (order of magnitude)")
    ax.set_yticks(y); ax.set_yticklabels(targets, fontsize=12)
    ax.set_xlim(-0.05, 0.6); ax.set_xlabel("R²")
    ax.set_title("Raw magnitude is unpredictable (R²≈0); log-scale tendency is learnable", color=DEEP, fontsize=13)
    for yi, (rr, rl) in enumerate(zip(r2_raw, r2_log)):
        ax.text(rr + 0.008, yi + h / 2, f"{rr:.2f}", va="center", fontsize=9, color=RED, fontweight="bold")
        ax.text(rl + 0.008, yi - h / 2, f"{rl:.2f}", va="center", fontsize=9, color=GREEN, fontweight="bold")
    ax.axvline(0, color="#94A3B8", lw=1)
    ax.legend(fontsize=9.5, loc="lower right", framealpha=0.95)
    ax.grid(axis="y", alpha=0)
    _save(fig, "06_reg_r2.png")


# ── 7. SHAP feature importance (top 12) ────────────────────────────────────────
def chart_shap():
    extra = json.loads(EXTRA.read_text())
    pairs = extra["shap_importance_pct"][:12][::-1]
    feats = [p[0] for p in pairs]; vals = [p[1] for p in pairs]
    colors = [AMBER if v >= 10 else (BLUE if v >= 7 else SLATE) for v in vals]
    fig, ax = plt.subplots(figsize=(8.6, 5.0))
    ax.barh(range(len(vals)), vals, color=colors)
    ax.set_yticks(range(len(vals))); ax.set_yticklabels(feats, fontsize=10.5)
    ax.set_xlim(0, 15); ax.set_xlabel("mean |SHAP|  (% of total)")
    ax.set_title("Signal is distributed — no single dominant feature (top: duration, coords, magnitude)", color=DEEP, fontsize=12.5)
    for i, v in enumerate(vals):
        ax.text(v + 0.2, i, f"{v:.1f}%", va="center", fontsize=9.5, color=SLATE, fontweight="bold")
    ax.grid(axis="y", alpha=0)
    _save(fig, "07_shap.png")


# ── 8. Target coverage — why nulls ≠ zeros ─────────────────────────────────────
def chart_coverage():
    targets = ["deaths", "injuries", "affected", "damage"]
    cov = [69.8, 26.0, 71.1, 36.1]
    test_n = [2015, 724, 2052, 1057]
    colors = [GREEN if c >= 50 else RED for c in cov]
    fig, ax = plt.subplots(figsize=(8.6, 4.3))
    bars = ax.bar(range(4), cov, color=colors, width=0.58)
    ax.set_xticks(range(4)); ax.set_xticklabels(targets, fontsize=12)
    ax.set_ylim(0, 100); ax.set_ylabel("% of events with the value recorded")
    ax.set_title("EM-DAT coverage: a null means 'not recorded', not zero", color=DEEP)
    for b, c, n in zip(bars, cov, test_n):
        ax.text(b.get_x() + b.get_width() / 2, c + 1.5, f"{c:.0f}%\nn={n:,}", ha="center",
                va="bottom", fontsize=10, color=SLATE, fontweight="bold")
    ax.axhline(50, color=GREY, ls="--", lw=1.3)
    ax.text(3.45, 52, "train drop-null on observed rows only", ha="right", fontsize=8.5, color=GREY)
    ax.grid(axis="x", alpha=0)
    _save(fig, "08_coverage.png")


def generate_all():
    chart_imbalance(); chart_clf_scoreboard(); chart_per_class_f1(); chart_confusion()
    chart_reg_factors(); chart_reg_r2(); chart_shap(); chart_coverage()
    print(f"All train3 charts -> {ASSETS}")


if __name__ == "__main__":
    print("Rendering train3 charts...")
    generate_all()
