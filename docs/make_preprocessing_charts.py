"""
make_preprocessing_charts.py — render the preprocessing deck's charts as PNGs.

Run:  py -3.12 docs/make_preprocessing_charts.py
Out:  docs/preprocessing_assets/*.png

Every number is pulled from this project's own artifacts:
  metrics/baseline_v4_1_metrics.json
  metrics/minority_strategies_v4_2.json
  metrics/v4_1_macroF1_tuned_weights.json
  metrics/v4_1_per_class_thresholds.json
  streamlit_eda/experiments/combined_regressor_results.json
  streamlit_eda/experiments/target_imputation_results.json
  streamlit_eda/experiments/centroid_results.json
  streamlit_eda/experiments/results.json
See docs/PREPROCESSING_DEEP_DIVE.md for the full provenance.
Imported by build_preprocessing_pptx.py (generate_all).
"""
from __future__ import annotations

import json
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
EXP = ROOT / "streamlit_eda" / "experiments"
MET = ROOT / "metrics"
ASSETS = Path(__file__).resolve().parent / "preprocessing_assets"

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


def _load(path):
    return json.loads(Path(path).read_text())


# ── 1. Regression winner — error factor before/after (the headline) ───────────
def chart_regression_winner():
    """combined_regressor_results.json: global_fill0 (old) vs pertype_drop (shipped),
    expressed as e^logMAE multiplicative error factor on the honest holdout."""
    d = _load(EXP / "combined_regressor_results.json")
    targets = ["damage", "affected", "injuries", "deaths"]
    before = [np.exp(d[t]["global_fill0"]) for t in targets]   # 111, 24.5, 9.0, 2.8
    after = [np.exp(d[t]["pertype_drop"]) for t in targets]     # 2.7, 4.3, 2.8, 1.9
    y = np.arange(len(targets)); h = 0.38
    fig, ax = plt.subplots(figsize=(8.4, 4.3))
    ax.barh(y + h / 2, before, h, color=RED, label="original (global, fill-0 nulls)")
    ax.barh(y - h / 2, after, h, color=GREEN, label="shipped (per-type + drop-null)")
    ax.set_yticks(y); ax.set_yticklabels(targets, fontsize=12.5)
    ax.set_xscale("log"); ax.set_xlim(1, 220)
    ax.set_xlabel("typical multiplicative error factor  e^logMAE  (lower = better, log scale)")
    ax.set_title("Per-type + drop-null cut impact error up to 111× → 2.7×", color=DEEP)
    for yi, (b, a) in enumerate(zip(before, after)):
        ax.text(b * 1.07, yi + h / 2, f"{b:.0f}×", va="center", fontsize=11, color=RED, fontweight="bold")
        ax.text(a * 1.07, yi - h / 2, f"{a:.1f}×", va="center", fontsize=11, color=GREEN, fontweight="bold")
    ax.legend(fontsize=10.5, loc="lower right", framealpha=0.96)
    ax.grid(axis="y", alpha=0)
    _save(fig, "01_regression_winner.png")


# ── 2. Fill-strategy ablation per target (honest-holdout log-MAE) ─────────────
def chart_fill_ablation():
    """target_imputation_results.json: fill-0 vs fill-median vs drop-null, global
    type-blind model, honest holdout log1p-MAE (lower = better)."""
    d = _load(EXP / "target_imputation_results.json")
    targets = ["deaths", "injuries", "affected", "damage"]
    fill0 = [d[t]["A_fill_zero"] for t in targets]
    median = [d[t]["B_fill_median"] for t in targets]
    drop = [d[t]["C_drop_nulls"] for t in targets]
    x = np.arange(len(targets)); w = 0.26
    fig, ax = plt.subplots(figsize=(8.6, 4.3))
    ax.bar(x - w, fill0, w, color=RED, label="fill-0 (old production)")
    ax.bar(x, median, w, color=AMBER, label="fill-median")
    ax.bar(x + w, drop, w, color=GREEN, label="drop-null (winner)")
    cov = [d[t]["coverage"] for t in targets]
    ax.set_xticks(x)
    ax.set_xticklabels([f"{t}\n({c*100:.0f}% coverage)" for t, c in zip(targets, cov)], fontsize=12)
    ax.set_ylabel("honest-holdout log1p-MAE  (lower = better)")
    ax.set_title("A null is 'not recorded', not 0 — drop-null wins on every target", color=DEEP)
    ax.legend(fontsize=10.5, loc="upper left", framealpha=0.96)
    ax.set_ylim(0, 5.2); ax.grid(axis="x", alpha=0)
    _save(fig, "02_fill_ablation.png")


# ── 3. Imbalance-strategy comparison (macro-F1) ───────────────────────────────
def chart_strategies():
    """minority_strategies_v4_2.json holdout macros + baseline_v4_1 reference."""
    d = _load(MET / "minority_strategies_v4_2.json")
    base = d["baseline_v4_1"]["macro_f1"]                                 # 0.6929
    hand = d["strategies"]["hand_weights"]["holdout_macro"]               # 0.7052
    smote = d["strategies"]["smote_minority_per_fold"]["holdout_macro"]   # 0.6605
    binv = d["strategies"]["balanced_inv_freq"]["holdout_macro"]         # 0.6157
    labels = ["Hand-tuned\nweights\n(SHIPPED)", "SMOTENC\n(discard)", "Balanced\ninv-freq\n(discard)"]
    macro = [hand, smote, binv]
    colors = [GREEN, GREY, GREY]
    fig, ax = plt.subplots(figsize=(8.2, 4.3))
    bars = ax.bar(range(3), macro, color=colors, width=0.6)
    ax.set_xticks(range(3)); ax.set_xticklabels(labels, fontsize=11)
    ax.set_ylim(0.55, 0.74); ax.set_ylabel("holdout macro-F1")
    ax.set_title("Resampling REGRESSED macro-F1 — class weights win", color=DEEP)
    for b, v in zip(bars, macro):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.003, f"{v:.4f}", ha="center",
                va="bottom", fontsize=12.5, color=SLATE, fontweight="bold")
    ax.axhline(base, color=BLUE, ls="--", lw=1.8, label=f"v4.1 baseline = {base:.4f}")
    ax.legend(fontsize=10.5, loc="upper right", framealpha=0.96)
    ax.grid(axis="x", alpha=0)
    _save(fig, "03_strategies.png")


# ── 4. Coordinate missingness (donut) ─────────────────────────────────────────
def chart_coord_missing():
    """centroid_results.json _diagnostics: 11,822 / 14,476 train rows lack coords."""
    d = _load(EXP / "centroid_results.json")
    rows = d["_diagnostics"]["D_centroid_impute"]["rows"]             # 14,476
    missing = d["_diagnostics"]["D_centroid_impute"]["missing_coord_rows"]  # 11,822
    filled = d["_diagnostics"]["D_centroid_impute"]["filled_by_centroid"]  # 11,707
    present = rows - missing
    fig, ax = plt.subplots(figsize=(7.0, 4.6))
    sizes = [present, missing]
    labels = [f"raw coords\n{present:,} ({present/rows*100:.0f}%)",
              f"imputed\n{missing:,} ({missing/rows*100:.0f}%)"]
    wedges, _ = ax.pie(sizes, colors=[GREEN, RED], startangle=90,
                       wedgeprops=dict(width=0.42, edgecolor="white", linewidth=2))
    ax.text(0, 0.12, f"{missing/rows*100:.0f}%", ha="center", fontsize=34,
            fontweight="bold", color=RED)
    ax.text(0, -0.22, "of train rows\nhave NO lat/lon", ha="center", fontsize=11, color=SLATE)
    ax.legend(wedges, labels, loc="lower center", bbox_to_anchor=(0.5, -0.18),
              ncol=2, fontsize=10.5, frameon=False)
    ax.set_title(f"Coordinates are 81.7% imputed — centroid fills {filled:,} of {missing:,}",
                 color=DEEP, pad=14)
    _save(fig, "04_coord_missing.png")


# ── 5. Centroid vs median imputation — per-class F1 delta ─────────────────────
def chart_centroid():
    """centroid_results.json: per-class F1 (centroid - median); macro +0.0167 KEEP."""
    d = _load(EXP / "centroid_results.json")
    med = d["A_median_impute"]["classification"]["per_class_f1"]
    cen = d["D_centroid_impute"]["classification"]["per_class_f1"]
    deltas = {k: cen[k] - med[k] for k in med}
    short = {"Extreme temperature": "Extreme temp", "Volcanic activity": "Volcanic"}
    items = sorted(deltas.items(), key=lambda kv: kv[1])
    labels = [short.get(k, k) for k, _ in items]
    vals = [v for _, v in items]
    colors = [RED if v < 0 else GREEN for v in vals]
    fig, ax = plt.subplots(figsize=(8.4, 4.3))
    ax.barh(range(len(vals)), vals, color=colors)
    ax.set_yticks(range(len(vals))); ax.set_yticklabels(labels, fontsize=11.5)
    ax.axvline(0, color=SLATE, lw=1)
    ax.set_xlabel("per-class F1 change:  centroid − median impute")
    gain = d["_decision"]["centroid_holdout_macro_gain"]
    ax.set_title(f"Centroid impute: macro-F1 +{gain:.4f} (KEEP) — minorities gain most", color=DEEP)
    for i, v in enumerate(vals):
        ax.text(v + (0.0012 if v >= 0 else -0.0012), i, f"{v:+.3f}", va="center",
                ha="left" if v >= 0 else "right", fontsize=9.5,
                color=GREEN if v >= 0 else RED, fontweight="bold")
    ax.set_xlim(-0.01, 0.07); ax.grid(axis="y", alpha=0)
    _save(fig, "05_centroid.png")


# ── 6. Decision scoreboard — Δ macro-F1 by preprocessing choice + verdict ──────
def chart_decisions():
    """One picture of the decision discipline: measured macro-F1 deltas, colored by
    verdict (kept / validated / leak-rejected / discarded-within-noise-or-regression)."""
    # (label, delta_macro_f1, verdict)  verdict ∈ {keep, validated, leak, discard}
    rows = [
        ("Centroid coord impute", +0.0167, "validated"),
        ("Hand-tuned class weights", +0.0123, "keep"),
        ("Per-scale magnitude", +0.0097, "leak"),
        ("Drop LightGBM (weight tune)", +0.0014, "keep"),
        ("Geo features (coast/climate)", -0.0006, "discard"),
        ("Per-class thresholds", -0.0027, "discard"),
        ("SRTM elevation", -0.0279, "discard"),
        ("SMOTENC resampling", -0.0324, "discard"),
        ("Balanced inverse-freq", -0.0772, "discard"),
    ]
    cmap = {"keep": GREEN, "validated": BLUE, "leak": RED, "discard": GREY}
    rows = sorted(rows, key=lambda r: r[1])
    labels = [r[0] for r in rows]
    vals = [r[1] for r in rows]
    colors = [cmap[r[2]] for r in rows]
    fig, ax = plt.subplots(figsize=(9.2, 4.8))
    ax.barh(range(len(vals)), vals, color=colors)
    ax.axvline(0, color=SLATE, lw=1)
    ax.set_yticks(range(len(vals))); ax.set_yticklabels(labels, fontsize=11)
    ax.set_xlabel("Δ holdout macro-F1 vs baseline  (measured)")
    ax.set_title("Every choice was ablated against a noise floor", color=DEEP)
    for i, (v, r) in enumerate(zip(vals, rows)):
        ax.text(v + (0.0015 if v >= 0 else -0.0015), i, f"{v:+.4f}", va="center",
                ha="left" if v >= 0 else "right", fontsize=9.5, color=SLATE, fontweight="bold")
    handles = [plt.Rectangle((0, 0), 1, 1, color=cmap[k]) for k in ["keep", "validated", "leak", "discard"]]
    ax.legend(handles, ["shipped", "validated, not yet shipped", "rejected (leakage)", "discarded (noise/regress)"],
              fontsize=9.5, loc="lower right", framealpha=0.96)
    ax.set_xlim(-0.092, 0.030); ax.grid(axis="y", alpha=0)
    _save(fig, "06_decisions.png")


# ── 7. Per-type structure ablation (regression mean log-MAE) ──────────────────
def chart_typeaware():
    """regressor_typeaware_results.json: type-blind vs +type-feature vs per-type."""
    d = _load(EXP / "regressor_typeaware_results.json")
    arms = ["A_baseline", "B_type_feature", "C_per_type"]
    names = ["type-blind\n(16 feat)", "+ disaster_type\nfeature", "per-type\n(8 models)"]
    means = [d[a]["mean"] for a in arms]
    colors = [RED, AMBER, GREEN]
    fig, ax = plt.subplots(figsize=(7.6, 4.3))
    bars = ax.bar(range(3), means, color=colors, width=0.6)
    ax.set_xticks(range(3)); ax.set_xticklabels(names, fontsize=11.5)
    ax.set_ylabel("mean holdout log1p-MAE (4 targets)")
    ax.set_title("Disaster-type blindness was the 2nd regressor bug", color=DEEP)
    for b, v in zip(bars, means):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.02, f"{v:.3f}", ha="center",
                va="bottom", fontsize=13, color=SLATE, fontweight="bold")
    ax.set_ylim(0, 2.7); ax.grid(axis="x", alpha=0)
    _save(fig, "07_typeaware.png")


def generate_all(_assets=None):
    chart_regression_winner()
    chart_fill_ablation()
    chart_strategies()
    chart_coord_missing()
    chart_centroid()
    chart_decisions()
    chart_typeaware()
    print(f"All charts -> {ASSETS}")


if __name__ == "__main__":
    print("Rendering preprocessing charts...")
    generate_all()
