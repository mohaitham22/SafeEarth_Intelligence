"""
Run-once offline chunking benchmark. NOT imported by the FastAPI application.
Usage: py -3.12 backend/rag/benchmark.py
Writes winner + raw scores to backend/rag/chunking_report.md.
"""
from __future__ import annotations

import re
import sys
import time
import uuid
from pathlib import Path

import chromadb
import fitz  # PyMuPDF
import numpy as np
from sentence_transformers import SentenceTransformer

_THIS_DIR   = Path(__file__).resolve().parent
PDF_PATH    = _THIS_DIR / "docs" / "Natural_Disaster_Safety_Guidelines.pdf"
REPORT_PATH = _THIS_DIR / "chunking_report.md"
EMBED_MODEL = "all-MiniLM-L6-v2"

# 30 test queries — 2 per disaster type (all 15 PDF chapters)
_TEST_QUERIES: list[tuple[str, str]] = [
    ("What should I do during an earthquake to stay safe?",                    "earthquake"),
    ("How do I prepare an emergency kit for earthquakes?",                     "earthquake"),
    ("What actions should I take during a flood event?",                       "flood"),
    ("How do I protect my home and family before a flood?",                    "flood"),
    ("What should I do if bitten or attacked by a dangerous animal?",          "animal"),
    ("How do I treat bite wounds and prevent infection from animal attacks?",  "animal"),
    ("What should I do during severe drought conditions?",                     "drought"),
    ("How do I conserve water and food supplies during a drought?",            "drought"),
    ("How do I protect myself during an epidemic outbreak?",                   "epidemic"),
    ("What hygiene and isolation measures prevent infectious disease spread?",  "epidemic"),
    ("What should I do during extreme heat to avoid heatstroke?",              "extreme temperature"),
    ("How do I prepare for a severe heatwave or extreme cold event?",          "extreme temperature"),
    ("What precautions should I take when driving in dense fog?",              "fog"),
    ("How do I stay safe when visibility is extremely low in fog?",            "fog"),
    ("What should I do during a glacial lake outburst flood?",                 "glacial lake"),
    ("How do I evacuate safely from a GLOF in mountain terrain?",              "glacial lake"),
    ("What should I do if a large meteorite or impact event occurs?",          "impact"),
    ("How do I prepare for an extraterrestrial impact emergency?",             "impact"),
    ("How do I protect my crops and family from locust infestation?",          "insect"),
    ("What are the public health risks during insect pest outbreaks?",         "insect"),
    ("What should I do if a landslide occurs near my home?",                   "landslide"),
    ("How do I identify landslide risk zones and plan evacuation routes?",     "landslide"),
    ("What should I do during a rock avalanche or dry mass movement?",         "mass movement"),
    ("How do I prepare for dust storms and dry rockfall hazards?",             "mass movement"),
    ("What should I do during a tropical storm or hurricane?",                 "storm"),
    ("How do I prepare my home and family for a tropical cyclone?",            "storm"),
    ("What should I do if a volcano erupts near where I live?",               "volcanic"),
    ("How do I protect myself from volcanic ash and pyroclastic flows?",       "volcanic"),
    ("What should I do if I am caught in a wildfire?",                        "wildfire"),
    ("How do I create a defensible space and evacuation plan for wildfire?",   "wildfire"),
]

# Keywords per disaster type for retrieval relevance scoring
_KEYWORDS: dict[str, list[str]] = {
    "earthquake":          ["earthquake", "seismic", "tremor", "aftershock", "shaking"],
    "flood":               ["flood", "inundation", "overflow", "flooding"],
    "animal":              ["animal", "bite", "sting", "attack", "wildlife", "venom"],
    "drought":             ["drought", "water deficit", "water insecurity"],
    "epidemic":            ["epidemic", "infectious", "disease", "pathogen", "quarantine"],
    "extreme temperature": ["extreme temperature", "heatwave", "hyperthermia", "hypothermia"],
    "fog":                 ["fog", "visibility", "atmospheric moisture"],
    "glacial lake":        ["glacial", "glof", "glacial lake", "outburst"],
    "impact":              ["impact", "meteorite", "bolide", "extraterrestrial"],
    "insect":              ["insect", "locust", "pest", "infestation", "swarm"],
    "landslide":           ["landslide", "debris", "slope failure", "mudslide"],
    "mass movement":       ["mass movement", "avalanche", "rockfall", "dust storm"],
    "storm":               ["storm", "hurricane", "cyclone", "typhoon", "tropical"],
    "volcanic":            ["volcanic", "volcano", "eruption", "pyroclastic", "ash"],
    "wildfire":            ["wildfire", "vegetation fire", "defensible", "fire spread"],
}

_ACTIONABLE_RE = re.compile(
    r"\b(should|must|do not|don't|prepare|evacuate|avoid|call|check|secure|"
    r"stay|move|use|store|follow|keep|ensure|never|always|wear|carry)\b",
    re.IGNORECASE,
)

# ── PDF text extraction ───────────────────────────────────────────────────────

_PAGE_HEADER_RE = re.compile(
    r"Global Natural Disaster Emergency Safety Guidelines[^\n]*Page \d+",
    re.IGNORECASE,
)


def _extract_pdf_text() -> str:
    doc = fitz.open(str(PDF_PATH))
    pages: list[str] = []
    for page in doc:
        text = page.get_text()
        text = _PAGE_HEADER_RE.sub("", text)
        pages.append(text.strip())
    doc.close()
    return "\n\n".join(p for p in pages if p)


# ── Strategy 1: Fixed-Size by word count (baseline) ──────────────────────────

def _fixed_size_chunks(text: str, window: int = 200, overlap: int = 50) -> list[dict]:
    words = text.split()
    step = window - overlap
    chunks: list[dict] = []
    for start in range(0, len(words), step):
        chunk_text = " ".join(words[start : start + window]).strip()
        if len(chunk_text) < 60:
            continue
        chunks.append({
            "text": chunk_text,
            "metadata": {"strategy": "fixed_size", "word_start": start},
        })
    return chunks


# ── Strategy 2: Recursive Character (separator hierarchy) ────────────────────

def _recursive_char_chunks(
    text: str, max_chars: int = 800, overlap_chars: int = 80
) -> list[dict]:
    separators = ["\n\n", "\n", ". ", "! ", "? ", " "]

    def _split(t: str, seps: list[str]) -> list[str]:
        if not seps or len(t) <= max_chars:
            return [t]
        sep = seps[0]
        parts = [p for p in t.split(sep) if p.strip()]
        merged: list[str] = []
        current = ""
        for part in parts:
            joiner = sep if current else ""
            candidate = (current + joiner + part).strip()
            if len(candidate) <= max_chars:
                current = candidate
            else:
                if current:
                    merged.append(current)
                if len(part) > max_chars:
                    merged.extend(_split(part, seps[1:]))
                    current = ""
                else:
                    current = part
        if current:
            merged.append(current)
        return merged

    raw = _split(text, separators)
    chunks: list[dict] = []
    for i, chunk_text in enumerate(raw):
        chunk_text = chunk_text.strip()
        if len(chunk_text) < 60:
            continue
        if i > 0 and chunks:
            tail = chunks[-1]["text"][-overlap_chars:].strip()
            chunk_text = tail + " " + chunk_text
        chunks.append({
            "text": chunk_text,
            "metadata": {"strategy": "recursive_char", "chunk_index": i},
        })
    return chunks


# ── Strategy 3: Semantic (cosine similarity boundary detection) ───────────────

_SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")


def _semantic_chunks(
    text: str,
    model: SentenceTransformer,
    threshold: float = 0.45,
    min_sents: int = 3,
    max_sents: int = 15,
) -> list[dict]:
    sentences = [s.strip() for s in _SENT_SPLIT_RE.split(text) if len(s.strip()) > 20]
    if len(sentences) < 2:
        return [{"text": text, "metadata": {"strategy": "semantic", "chunk_index": 0}}]

    embs = model.encode(
        sentences, batch_size=64, show_progress_bar=False, convert_to_numpy=True
    )

    sims: list[float] = []
    for i in range(len(embs) - 1):
        a, b = embs[i], embs[i + 1]
        denom = float(np.linalg.norm(a) * np.linalg.norm(b)) + 1e-9
        sims.append(float(np.dot(a, b)) / denom)

    chunks: list[dict] = []
    bucket: list[str] = [sentences[0]]

    for i, sim in enumerate(sims):
        next_sent = sentences[i + 1]
        force_split = len(bucket) >= max_sents
        topic_change = sim < threshold and len(bucket) >= min_sents
        if force_split or topic_change:
            chunks.append({
                "text": " ".join(bucket),
                "metadata": {"strategy": "semantic", "chunk_index": len(chunks)},
            })
            bucket = [next_sent]
        else:
            bucket.append(next_sent)

    if bucket:
        chunks.append({
            "text": " ".join(bucket),
            "metadata": {"strategy": "semantic", "chunk_index": len(chunks)},
        })

    return [c for c in chunks if len(c["text"].strip()) > 60]


# ── Strategy 4: Section-Aware (header detection + disaster-type tagging) ──────

_SECTION_HEADERS: list[tuple[str, re.Pattern]] = [
    ("quickfacts",  re.compile(r"Quick Facts[^\n]*",                    re.IGNORECASE)),
    ("before",      re.compile(r"Before:\s*Preparedness Actions",       re.IGNORECASE)),
    ("during",      re.compile(r"During:\s*Immediate Response Actions", re.IGNORECASE)),
    ("after",       re.compile(r"After:\s*Recovery Actions",            re.IGNORECASE)),
    ("medical",     re.compile(r"Medical Guidance",                     re.IGNORECASE)),
    ("evacuation",  re.compile(r"Evacuation Procedures",                re.IGNORECASE)),
    ("contacts",    re.compile(r"Emergency Contacts",                   re.IGNORECASE)),
    ("chapter",     re.compile(r"DISASTER TYPE \d+",                    re.IGNORECASE)),
]

_CHAPTER_NAME_RE = re.compile(r"DISASTER TYPE \d+\s*\n([^\n]+)", re.IGNORECASE)


def _section_aware_chunks(text: str, max_section_chars: int = 1200) -> list[dict]:
    markers: list[tuple[int, str]] = []
    for section_name, pattern in _SECTION_HEADERS:
        for m in pattern.finditer(text):
            markers.append((m.start(), section_name))
    markers.sort(key=lambda x: x[0])

    if not markers:
        return [{"text": text, "metadata": {"strategy": "section_aware", "section": "full"}}]

    chunks: list[dict] = []
    for idx, (pos, section_name) in enumerate(markers):
        end = markers[idx + 1][0] if idx + 1 < len(markers) else len(text)
        section_text = text[pos:end].strip()
        if len(section_text) < 60:
            continue

        preceding = text[:pos]
        chapter_matches = list(_CHAPTER_NAME_RE.finditer(preceding))
        disaster_label = (
            chapter_matches[-1].group(1).strip().lower()
            if chapter_matches
            else "general"
        )

        meta_base: dict = {
            "strategy": "section_aware",
            "section": section_name,
            "disaster_type": disaster_label,
        }

        if len(section_text) <= max_section_chars:
            chunks.append({"text": section_text, "metadata": meta_base})
        else:
            paragraphs = [p.strip() for p in section_text.split("\n\n") if p.strip()]
            current = ""
            sub_idx = 0
            for para in paragraphs:
                if len(current) + len(para) + 2 <= max_section_chars:
                    current = (current + "\n\n" + para).strip() if current else para
                else:
                    if current:
                        m = {**meta_base, "sub_index": sub_idx}
                        chunks.append({"text": current, "metadata": m})
                        sub_idx += 1
                    current = para
            if current:
                chunks.append({"text": current, "metadata": {**meta_base, "sub_index": sub_idx}})

    return chunks


# ── Embedding + ChromaDB ──────────────────────────────────────────────────────

def _embed(texts: list[str], model: SentenceTransformer) -> list[list[float]]:
    return model.encode(
        texts, batch_size=32, show_progress_bar=False, convert_to_numpy=True
    ).tolist()


def _build_collection(
    chunks: list[dict], model: SentenceTransformer, col_name: str
) -> chromadb.Collection:
    client = chromadb.EphemeralClient()
    col = client.create_collection(col_name)
    texts = [c["text"] for c in chunks]
    metas = [c["metadata"] for c in chunks]
    ids = [str(uuid.uuid4()) for _ in chunks]

    batch_size = 256
    for start in range(0, len(texts), batch_size):
        sl = slice(start, start + batch_size)
        col.add(
            documents=texts[sl],
            embeddings=_embed(texts[sl], model),
            ids=ids[sl],
            metadatas=metas[sl],
        )
    return col


# ── Scoring ───────────────────────────────────────────────────────────────────

def _is_relevant(text: str, keyword: str) -> bool:
    tl = text.lower()
    return any(kw in tl for kw in _KEYWORDS.get(keyword, [keyword]))


def _score_retrieval_relevance(
    col: chromadb.Collection, model: SentenceTransformer
) -> float:
    """Mean Precision@5 over all 30 test queries."""
    k = min(5, col.count())
    scores: list[float] = []
    for query_text, keyword in _TEST_QUERIES:
        q_emb = model.encode([query_text], convert_to_numpy=True).tolist()
        results = col.query(query_embeddings=q_emb, n_results=k)
        docs = results.get("documents", [[]])[0]
        hits = sum(1 for d in docs if _is_relevant(d, keyword))
        scores.append(hits / max(len(docs), 1))
    return float(np.mean(scores))


def _score_chunk_coherence(chunks: list[dict]) -> float:
    """Fraction of chunks that pass structural quality checks."""
    if not chunks:
        return 0.0
    good = 0
    for c in chunks:
        text = c["text"].strip()
        words = text.split()
        if not (20 <= len(words) <= 500):
            continue
        if not re.match(r"^[A-Z•●\-\d'\"]", text):
            continue
        # Reject chunks ending mid-word with a hyphen (hard-wrapped line break)
        if re.search(r"-\s*$", text):
            continue
        good += 1
    return good / len(chunks)


def _score_llm_quality(
    col: chromadb.Collection, model: SentenceTransformer
) -> float:
    """
    Proxy for LLM output quality (no Groq call — measures context quality).
    Relevance density (40%) + actionability (30%) + chunk diversity (30%).
    """
    k = min(3, col.count())
    query_scores: list[float] = []

    for query_text, keyword in _TEST_QUERIES:
        q_emb = model.encode([query_text], convert_to_numpy=True).tolist()
        results = col.query(query_embeddings=q_emb, n_results=k)
        docs = results.get("documents", [[]])[0]
        if not docs:
            query_scores.append(0.0)
            continue

        combined = " ".join(docs)
        sentences = [s.strip() for s in re.split(r"[.!?]+", combined) if s.strip()]

        rel_density = (
            sum(1 for s in sentences if _is_relevant(s, keyword))
            / max(len(sentences), 1)
        )
        actionability = (
            sum(1 for s in sentences if _ACTIONABLE_RE.search(s))
            / max(len(sentences), 1)
        )

        if len(docs) > 1:
            def _jaccard(a: str, b: str) -> float:
                sa, sb = set(a.lower().split()), set(b.lower().split())
                return len(sa & sb) / max(len(sa | sb), 1)
            pairs = [
                _jaccard(docs[i], docs[j])
                for i in range(len(docs))
                for j in range(i + 1, len(docs))
            ]
            diversity = 1.0 - float(np.mean(pairs))
        else:
            diversity = 0.7

        query_scores.append(0.40 * rel_density + 0.30 * actionability + 0.30 * diversity)

    return float(np.mean(query_scores))


# ── Result container ──────────────────────────────────────────────────────────

class _Result:
    def __init__(
        self,
        name: str,
        n_chunks: int,
        relevance: float,
        coherence: float,
        llm_quality: float,
    ) -> None:
        self.name        = name
        self.n_chunks    = n_chunks
        self.relevance   = relevance
        self.coherence   = coherence
        self.llm_quality = llm_quality
        self.total       = 0.50 * relevance + 0.30 * coherence + 0.20 * llm_quality

    def __repr__(self) -> str:
        return (
            f"{self.name}: total={self.total:.4f} "
            f"(rel={self.relevance:.4f}, coh={self.coherence:.4f}, "
            f"llm={self.llm_quality:.4f}, chunks={self.n_chunks})"
        )


def _run_strategy(
    name: str, chunks: list[dict], model: SentenceTransformer, index: int = 0
) -> _Result:
    # ChromaDB name: 3-512 chars, [a-zA-Z0-9._-], must start/end with [a-zA-Z0-9]
    safe_name = f"bm{index}"
    print(f"    Building collection ({len(chunks)} chunks)...")
    col = _build_collection(chunks, model, safe_name)
    print(f"    Scoring retrieval relevance (Precision@5, 30 queries)...")
    rel = _score_retrieval_relevance(col, model)
    print(f"    Scoring chunk coherence...")
    coh = _score_chunk_coherence(chunks)
    print(f"    Scoring LLM quality proxy...")
    llm = _score_llm_quality(col, model)
    return _Result(name, len(chunks), rel, coh, llm)


# ── Report writer ─────────────────────────────────────────────────────────────

def _write_report(results: list[_Result]) -> None:
    ranked = sorted(results, key=lambda r: r.total, reverse=True)
    winner = ranked[0]
    rank_labels = ["1st", "2nd", "3rd", "4th"]

    lines = [
        "# RAG Chunking Benchmark Report",
        "",
        f"**Winner: {winner.name}**",
        f"Total weighted score: {winner.total:.4f}",
        "",
        "## Scoring Weights",
        "| Metric | Weight | Method |",
        "|---|---|---|",
        "| Retrieval Relevance | 50% | Mean Precision@5 over 30 test queries |",
        "| Chunk Coherence | 30% | Fraction of chunks passing structural checks |",
        "| LLM Output Quality | 20% | Proxy: relevance density + actionability + diversity |",
        "",
        "## Full Results (ranked by total score)",
        "| Rank | Strategy | Chunks | Relevance (50%) | Coherence (30%) | LLM Quality (20%) | Total |",
        "|---|---|---|---|---|---|---|",
    ]
    for i, r in enumerate(ranked):
        lines.append(
            f"| {rank_labels[i]} | {r.name} | {r.n_chunks} "
            f"| {r.relevance:.4f} | {r.coherence:.4f} "
            f"| {r.llm_quality:.4f} | **{r.total:.4f}** |"
        )

    lines += [
        "",
        "## Winner Configuration",
        f"**Strategy**: {winner.name}",
        f"**Chunk count**: {winner.n_chunks}",
        "",
        "### Parameters used in ingest.py",
    ]

    if "Fixed" in winner.name:
        lines += [
            "- window_words: 200",
            "- overlap_words: 50",
        ]
    elif "Recursive" in winner.name:
        lines += [
            "- max_chars: 800",
            "- overlap_chars: 80",
            r"- separator hierarchy: `\n\n` → `\n` → `'. '` → `'! '` → `'? '` → `' '`",
        ]
    elif "Semantic" in winner.name:
        lines += [
            "- embedding_model: all-MiniLM-L6-v2",
            "- similarity_threshold: 0.45",
            "- min_sentences_per_chunk: 3",
            "- max_sentences_per_chunk: 15",
        ]
    else:
        lines += [
            "- sections_detected: Before, During, After, Medical, Evacuation, Contacts, Quick Facts",
            "- metadata_tags: {disaster_type, section_name}",
            "- max_section_chars: 1200 (split at paragraph boundaries if exceeded)",
        ]

    lines += [
        "",
        "## Ranking Summary",
    ]
    for i, r in enumerate(ranked):
        lines.append(f"{i + 1}. {r.name} — {r.total:.4f}")

    lines += [
        "",
        "---",
        "*Generated by `backend/rag/benchmark.py` — run-once offline script.*",
        "*Implement the winning strategy in `backend/rag/ingest.py`.*",
    ]

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nReport written to: {REPORT_PATH}")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if not PDF_PATH.exists():
        print(f"ERROR: PDF not found at {PDF_PATH}", file=sys.stderr)
        sys.exit(1)

    print(f"Loading embedding model: {EMBED_MODEL}")
    model = SentenceTransformer(EMBED_MODEL)
    print("Model loaded.\n")

    print("Extracting PDF text...")
    full_text = _extract_pdf_text()
    print(f"Extracted {len(full_text):,} characters from {PDF_PATH.name}\n")

    print("Building chunk sets for all 4 strategies...")
    strategies: list[tuple[str, list[dict]]] = [
        ("Fixed-Size (word count)", _fixed_size_chunks(full_text)),
        ("Recursive Character",     _recursive_char_chunks(full_text)),
        ("Semantic",                _semantic_chunks(full_text, model)),
        ("Section-Aware",           _section_aware_chunks(full_text)),
    ]
    for name, chunks in strategies:
        print(f"  {name}: {len(chunks)} chunks")

    print()
    results: list[_Result] = []
    for idx, (name, chunks) in enumerate(strategies):
        print(f"[{name}]")
        t0 = time.time()
        r = _run_strategy(name, chunks, model, index=idx)
        elapsed = time.time() - t0
        print(f"    => {r}  [{elapsed:.1f}s]\n")
        results.append(r)

    print("-- Final Rankings --")
    for r in sorted(results, key=lambda r: r.total, reverse=True):
        print(f"  {r}")

    _write_report(results)

    winner = max(results, key=lambda r: r.total)
    print(f"\nWINNER: {winner.name}  (total={winner.total:.4f})")
    print("Implement this strategy in backend/rag/ingest.py")
