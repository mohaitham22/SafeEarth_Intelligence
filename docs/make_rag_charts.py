"""
make_rag_charts.py — render the RAG-deep-dive presentation's charts as PNGs.

Run:  py -3.12 docs/make_rag_charts.py
Out:  docs/rag_assets/*.png

Every number is from docs/RAG_AND_RECSYS_DEEP_DIVE.md, which was extracted from this
project's own source: backend/rag/recommender.py, ingest.py, extract_chapters.py,
benchmark.py, chunking_report.md, services/recommendation_service.py, and the live
backend/rag/chapters.json (re-measured 2026-06-15). Imported by build_rag_pptx.py
(generate_all). No data file is required — all values are hard-coded from the verified
deep-dive so the deck is reproducible offline.
"""
from __future__ import annotations

import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ASSETS = Path(__file__).resolve().parent / "rag_assets"

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


# ── 1. Chunking benchmark — the headline result ───────────────────────────────
def chart_chunking_benchmark():
    # chunking_report.md: 30 queries, weights 50/30/20
    strategies = ["Semantic\n(winner)", "Section-\nAware", "Fixed-Size\n(words)", "Recursive\nCharacter"]
    relevance  = [0.8867, 0.8867, 0.9600, 0.9267]   # Precision@5 (50%)
    coherence  = [0.9940, 0.8540, 0.1604, 0.0570]   # structural   (30%)
    llm        = [0.5389, 0.5233, 0.4987, 0.5100]   # proxy        (20%)
    total      = [0.8493, 0.8042, 0.6278, 0.5824]

    x = np.arange(len(strategies)); w = 0.25
    fig, ax = plt.subplots(figsize=(9.0, 4.6))
    ax.bar(x - w, relevance, w, color=BLUE,  label="Retrieval relevance (50%)")
    ax.bar(x,     coherence, w, color=AMBER, label="Chunk coherence (30%)")
    ax.bar(x + w, llm,       w, color=GREY,  label="LLM-quality proxy (20%)")

    ax.plot(x, total, "D", color=GREEN, markersize=11, zorder=5)
    for xi, t in zip(x, total):
        ax.text(xi, t + 0.04, f"{t:.3f}", ha="center", fontsize=11.5,
                color=GREEN, fontweight="bold")
    ax.text(0.02, 0.965, "◆ = total weighted score", transform=ax.transAxes,
            fontsize=10, color=GREEN, fontweight="bold")

    ax.set_xticks(x); ax.set_xticklabels(strategies, fontsize=11)
    ax.set_ylim(0, 1.12); ax.set_ylabel("score")
    ax.set_title("Semantic wins on coherence — Fixed/Recursive split mid-sentence", color=DEEP, fontsize=13.5)
    ax.legend(fontsize=9.5, loc="upper right", framealpha=0.95, ncol=1)
    ax.grid(axis="x", alpha=0)
    _save(fig, "01_chunking_benchmark.png")


# ── 2. Runtime memory footprint — the deployment pivot ────────────────────────
def chart_memory_footprint():
    labels = ["Legacy\nChromaDB +\nsentence-transformers\n(PyTorch + CUDA)",
              "Production\nchapters.json +\nGroq SDK"]
    mem = [2000, 5]   # added RAG dependency footprint, MB
    colors = [RED, GREEN]
    fig, ax = plt.subplots(figsize=(8.0, 4.6))
    bars = ax.bar([0, 1], mem, color=colors, width=0.55)
    ax.set_xticks([0, 1]); ax.set_xticklabels(labels, fontsize=11)
    ax.set_yscale("log"); ax.set_ylim(1, 4000)
    ax.set_ylabel("added RAG memory footprint (MB, log scale)")
    ax.set_title("Why the pipeline was rebuilt: PyTorch OOMs on Render's 512 MB free tier", color=DEEP, fontsize=13)

    ax.axhline(512, color=AMBER, ls="--", lw=1.8)
    ax.text(1.45, 560, "Render free tier 512 MB", ha="right", fontsize=10.5,
            color=AMBER, fontweight="bold")
    for b, v in zip(bars, mem):
        label = "~2 GB" if v >= 1000 else "~5 MB"
        ax.text(b.get_x() + b.get_width() / 2, v * 1.15, label, ha="center",
                va="bottom", fontsize=13, color=SLATE, fontweight="bold")
    ax.annotate("OOM", xy=(0, 2000), xytext=(0.42, 2600),
                fontsize=13, color=RED, fontweight="bold",
                arrowprops=dict(arrowstyle="->", color=RED, lw=1.8))
    ax.text(1, 14, "400× smaller", ha="center", fontsize=10.5, color=GREEN, fontweight="bold")
    ax.grid(axis="x", alpha=0)
    _save(fig, "02_memory_footprint.png")


# ── 3. Corpus & the 6,000-char truncation ─────────────────────────────────────
def chart_chapter_truncation():
    # chapters.json char counts (re-measured 2026-06-15)
    data = [
        ("Wildfire", 8461), ("Flood", 7880), ("Storm", 7760), ("Drought", 7613),
        ("Earthquake", 7587), ("Volcanic activity", 7302), ("Extreme temperature", 6853),
        ("Landslide", 6094),
    ]
    data.sort(key=lambda d: d[1])
    labels = [d[0] for d in data]
    sizes = np.array([d[1] for d in data])
    cutoff = 6000
    kept = np.minimum(sizes, cutoff)
    dropped = sizes - kept

    y = np.arange(len(labels))
    fig, ax = plt.subplots(figsize=(8.8, 4.8))
    ax.barh(y, kept, color=GREEN, label="kept (sent to Groq)")
    ax.barh(y, dropped, left=kept, color=RED, alpha=0.85, label="dropped by [:6000] tail-cut")
    ax.axvline(cutoff, color=SLATE, ls="--", lw=1.6)
    ax.text(cutoff + 100, len(labels) - 0.35, "6,000-char cap", fontsize=10,
            color=SLATE, fontweight="bold", va="center")

    ax.set_yticks(y); ax.set_yticklabels(labels, fontsize=11)
    ax.set_xlim(0, 9200); ax.set_ylim(-0.7, len(labels) - 0.1)
    ax.set_xlabel("chapter length (characters)")
    ax.set_title("All 8 chapters exceed the cap → Emergency Contacts tail is always cut", color=DEEP, fontsize=13)
    for yi, d in zip(y, dropped):
        if d > 0:
            ax.text(sizes[yi] + 90, yi, f"−{d:,}", va="center", fontsize=9, color=RED, fontweight="bold")
    ax.legend(fontsize=10, loc="upper center", bbox_to_anchor=(0.5, -0.16),
              ncol=2, frameon=False)
    ax.grid(axis="y", alpha=0)
    _save(fig, "03_chapter_truncation.png")


# ── 4. Per-call Groq token budget (production) ────────────────────────────────
def chart_token_budget():
    parts  = ["System prompt", "User overhead\n(metadata+schema)", "Chapter context ([:6000])", "Output (6 recs)"]
    toks   = [100, 100, 1500, 360]
    colors = [GREY, BLUE, GREEN, AMBER]
    inside = [False, False, True, True]   # wide segments get inline labels
    total  = sum(toks)
    fig, ax = plt.subplots(figsize=(9.2, 3.2))
    left = 0
    for p, t, c, ins in zip(parts, toks, colors, inside):
        ax.barh(0, t, left=left, color=c, edgecolor="white", height=0.5)
        pct = f"~{t} ({t/total*100:.0f}%)"
        if ins:
            ax.text(left + t / 2, 0, f"{p}\n{pct}", ha="center", va="center",
                    fontsize=10.5, color="white", fontweight="bold")
        left += t
    # Narrow segments → labels above with connector lines
    ax.annotate(f"System prompt  ~100 (5%)", xy=(50, 0.26), xytext=(60, 0.62),
                fontsize=9.5, color=GREY, fontweight="bold", ha="left",
                arrowprops=dict(arrowstyle="-", color=GREY, lw=1.2))
    ax.annotate(f"User overhead  ~100 (5%)", xy=(150, 0.26), xytext=(300, 0.90),
                fontsize=9.5, color=BLUE, fontweight="bold", ha="left",
                arrowprops=dict(arrowstyle="-", color=BLUE, lw=1.2))

    ax.set_xlim(0, total); ax.set_ylim(-0.45, 1.15)
    ax.set_yticks([]); ax.set_xlabel("tokens per /recommendations call")
    ax.set_title(f"~{total:,} tokens/call · context is 73% of spend → the lever for cost", color=DEEP, fontsize=13)
    ax.grid(False)
    for sp in ax.spines.values():
        sp.set_visible(False)
    _save(fig, "04_token_budget.png")


# ── 5. Forecast severity-dedup — the latency/cost lever ───────────────────────
def chart_forecast_dedup():
    labels = ["Naive\n(1 RAG call / day)", "Severity-dedup\n(≤4 distinct severities)"]
    calls = [30, 4]
    colors = [RED, GREEN]
    fig, ax = plt.subplots(figsize=(7.6, 4.4))
    bars = ax.bar([0, 1], calls, color=colors, width=0.5)
    ax.set_xticks([0, 1]); ax.set_xticklabels(labels, fontsize=12)
    ax.set_ylim(0, 34); ax.set_ylabel("Groq calls per 30-day forecast batch")
    ax.set_title("Deduplicate by severity → up to 7.5× fewer LLM calls", color=DEEP, fontsize=13.5)
    for b, v in zip(bars, calls):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.6, f"{v}", ha="center",
                va="bottom", fontsize=15, color=SLATE, fontweight="bold")
    ax.annotate("", xy=(1, 4), xytext=(0, 30),
                arrowprops=dict(arrowstyle="->", color=AMBER, lw=2.2, connectionstyle="arc3,rad=-0.25"))
    ax.text(0.5, 20, "≤4 distinct\n{Low,Med,High,Crit}", ha="center", fontsize=10.5,
            color=AMBER, fontweight="bold")
    ax.grid(axis="x", alpha=0)
    _save(fig, "05_forecast_dedup.png")


# ── 6. Evaluation coverage — what was / was not measured ──────────────────────
def chart_eval_coverage():
    measured = ["Chunk coherence (structural)", "Precision@5 (keyword proxy)", "LLM-quality proxy"]
    notmeasured = ["Recall@k / MRR / NDCG", "Faithfulness / groundedness",
                   "Hallucination rate", "Answer relevance (RAGAS)",
                   "Recsys precision@k / NDCG", "Coverage / diversity / novelty"]
    fig, ax = plt.subplots(figsize=(9.0, 5.0))
    # Lay out not-measured at the bottom, a gap, then measured on top.
    GAP = 1.0
    rows = []  # (y, text, ok)
    for i, n in enumerate(notmeasured[::-1]):
        rows.append((i, n, False))
    base = len(notmeasured) + GAP
    for i, m in enumerate(measured[::-1]):
        rows.append((base + i, m, True))

    for y, txt, ok in rows:
        c = GREEN if ok else RED
        mark = "✓" if ok else "✗"
        ax.scatter(0.04, y, s=420, color=c, zorder=3)
        ax.text(0.04, y, mark, ha="center", va="center", fontsize=13, color="white", fontweight="bold")
        ax.text(0.10, y, txt, va="center", fontsize=12.5,
                color=SLATE if ok else GREY, fontweight="bold" if ok else "normal")

    top = base + len(measured) - 1
    ax.text(0.80, top, "MEASURED · 3", fontsize=11, color=GREEN, fontweight="bold", va="center")
    ax.text(0.80, len(notmeasured) - 1, "NOT MEASURED · 6", fontsize=11, color=RED,
            fontweight="bold", va="center")
    ax.text(0.80, len(notmeasured) - 2, "→ recommendations §20", fontsize=9.5, color=GREY, va="center")

    ax.set_xlim(0, 1.0); ax.set_ylim(-0.8, top + 1.4)
    ax.axis("off")
    ax.set_title("Only the chunking benchmark was measured — no RAG/recsys eval yet",
                 color=DEEP, fontsize=13.5, loc="left", x=0.02, pad=14)
    _save(fig, "06_eval_coverage.png")


def generate_all(_assets=None):
    chart_chunking_benchmark(); chart_memory_footprint(); chart_chapter_truncation()
    chart_token_budget(); chart_forecast_dedup(); chart_eval_coverage()
    print(f"All RAG charts -> {ASSETS}")


if __name__ == "__main__":
    print("Rendering RAG charts...")
    generate_all()
