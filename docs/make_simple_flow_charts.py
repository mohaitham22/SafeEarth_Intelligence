"""
make_simple_flow_charts.py — render the SIMPLE-flow presentation's charts as PNGs.

Run:  py -3.12 docs/make_simple_flow_charts.py
Out:  docs/simple_flow_assets/*.png

Plain-language, low-clutter charts for a non-expert audience. Every number is
taken from this project's own source / the simple-flow write-up:
  - chapters.json: 8 disaster types, ~60 KB committed JSON  (backend/rag/chapters.json)
  - legacy embeddings + ChromaDB ≈ 2 GB (PyTorch+CUDA); Render free tier = 512 MB
  - recommendation contract: exactly 6 items, 5 categories in fixed order
    evacuation -> kit -> shelter -> medical -> contact  (rag/recommender.py)
  - chunking benchmark totals (chunking_report.md): Semantic 0.8493 wins
No data file is required — values are hard-coded so the deck is reproducible offline.
"""
from __future__ import annotations

import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ASSETS = Path(__file__).resolve().parent / "simple_flow_assets"

# ── Palette (matches the deck) ────────────────────────────────────────────────
DEEP = "#0B3D2E"; GREEN = "#16A34A"; AMBER = "#F59E0B"; RED = "#DC2626"
SLATE = "#334155"; GREY = "#94A3B8"; LIGHT = "#F1F5F9"; BLUE = "#2563EB"; PURPLE = "#9333EA"

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 13,
    "axes.titlesize": 15, "axes.titleweight": "bold", "axes.titlecolor": DEEP,
    "axes.labelcolor": SLATE, "axes.edgecolor": "#CBD5E1",
    "xtick.color": SLATE, "ytick.color": SLATE,
    "axes.grid": True, "grid.alpha": 0.25, "grid.color": "#CBD5E1",
    "figure.facecolor": "white", "axes.facecolor": "white", "savefig.facecolor": "white",
})


def _save(fig, name):
    ASSETS.mkdir(parents=True, exist_ok=True)
    fig.savefig(ASSETS / name, dpi=150, bbox_inches="tight", pad_inches=0.18)
    plt.close(fig)
    print("  wrote", name)


# ── 1. Why chapters, not a vector database (the memory story) ─────────────────
def chart_why_chapters():
    labels = ["Vector database way\n(embeddings + ChromaDB,\nneeds PyTorch)",
              "Our way\n(chapters.json +\nGroq)"]
    mem = [2000, 5]   # added memory footprint, MB
    colors = [RED, GREEN]
    fig, ax = plt.subplots(figsize=(8.2, 4.7))
    bars = ax.bar([0, 1], mem, color=colors, width=0.55)
    ax.set_xticks([0, 1]); ax.set_xticklabels(labels, fontsize=12)
    ax.set_yscale("log"); ax.set_ylim(1, 4000)
    ax.set_ylabel("memory needed (MB, log scale)")
    ax.set_title("Why we look up chapters instead of using a vector database",
                 color=DEEP, fontsize=13.5)

    # The hard limit of the free server.
    ax.axhline(512, color=AMBER, ls="--", lw=1.9)
    ax.text(1.46, 560, "Free server limit: 512 MB", ha="right", fontsize=11,
            color=AMBER, fontweight="bold")

    for b, v in zip(bars, mem):
        label = "~2 GB" if v >= 1000 else "~5 MB"
        ax.text(b.get_x() + b.get_width() / 2, v * 1.18, label, ha="center",
                va="bottom", fontsize=14, color=SLATE, fontweight="bold")
    ax.annotate("too big — crashes", xy=(0, 2000), xytext=(0.34, 2700),
                fontsize=12, color=RED, fontweight="bold",
                arrowprops=dict(arrowstyle="->", color=RED, lw=1.9))
    ax.text(1, 13, "fits easily", ha="center", fontsize=11.5, color=GREEN, fontweight="bold")
    ax.grid(axis="x", alpha=0)
    _save(fig, "01_why_chapters.png")


# ── 2. What the recommender returns: 6 items, 5 categories, in order ──────────
def chart_recommendation_contract():
    cats = ["Evacuation", "Kit", "Shelter", "Medical", "Contact"]
    colors = [RED, AMBER, BLUE, GREEN, PURPLE]
    x = np.arange(len(cats))
    fig, ax = plt.subplots(figsize=(9.4, 3.9))

    # One rounded "card" per category, left-to-right = the fixed sort order.
    for xi, (c, col) in enumerate(zip(cats, colors)):
        ax.scatter(xi, 0, s=2600, color=col, zorder=3, edgecolors="white", linewidths=2)
        ax.text(xi, 0, str(xi + 1), ha="center", va="center", color="white",
                fontsize=16, fontweight="bold")
        ax.text(xi, -0.62, c, ha="center", va="center", color=SLATE,
                fontsize=13, fontweight="bold")
        if xi < len(cats) - 1:
            ax.annotate("", xy=(xi + 0.62, 0), xytext=(xi + 0.38, 0),
                        arrowprops=dict(arrowstyle="->", color=GREY, lw=2))

    ax.text(2, 1.15, "Always exactly 6 recommendations, sorted in this fixed order",
            ha="center", fontsize=13, color=DEEP, fontweight="bold")
    ax.set_xlim(-0.7, len(cats) - 0.3); ax.set_ylim(-1.2, 1.6)
    ax.axis("off")
    _save(fig, "02_recommendation_contract.png")


# ── 3. We tested how to split the document (simple, totals only) ──────────────
def chart_chunking_pick():
    # chunking_report.md total weighted scores (50% relevance / 30% coherence / 20% proxy)
    strategies = ["Semantic\n(we picked this)", "Section-\nAware", "Fixed-Size", "Recursive\nCharacter"]
    total = [0.8493, 0.8042, 0.6278, 0.5824]
    colors = [GREEN, SLATE, GREY, GREY]
    x = np.arange(len(strategies))
    fig, ax = plt.subplots(figsize=(8.8, 4.5))
    bars = ax.bar(x, total, color=colors, width=0.62)
    for b, v in zip(bars, total):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.02, f"{v:.2f}",
                ha="center", va="bottom", fontsize=13, color=SLATE, fontweight="bold")
    ax.set_xticks(x); ax.set_xticklabels(strategies, fontsize=12)
    ax.set_ylim(0, 1.0); ax.set_ylabel("overall score (higher is better)")
    ax.set_title("We tested 4 ways to split the document — the one that keeps\nwhole sentences won",
                 color=DEEP, fontsize=13)
    ax.grid(axis="x", alpha=0)
    _save(fig, "03_chunking_pick.png")


def generate_all(_assets=None):
    chart_why_chapters()
    chart_recommendation_contract()
    chart_chunking_pick()
    print(f"All simple-flow charts -> {ASSETS}")


if __name__ == "__main__":
    print("Rendering simple-flow charts...")
    generate_all()
