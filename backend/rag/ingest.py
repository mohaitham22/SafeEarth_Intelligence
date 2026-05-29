"""
Run-once offline ingestion script. NOT imported by the FastAPI application.
Usage: py -3.12 backend/rag/ingest.py
Idempotent: deletes and recreates the collection on each run (no duplicate chunks).

Winning strategy: Semantic (cosine-similarity boundary detection)
  similarity_threshold = 0.45
  min_sentences = 3 / max_sentences = 15
  embedding_model = all-MiniLM-L6-v2
  source: backend/rag/chunking_report.md
"""
from __future__ import annotations

import re
import sys
import uuid
from pathlib import Path

import chromadb
import fitz  # PyMuPDF
import numpy as np
from sentence_transformers import SentenceTransformer

from rag.constants import CHROMA_PATH, COLLECTION_NAME, EMBED_MODEL, PDF_PATH

# ── PDF extraction ────────────────────────────────────────────────────────────

_PAGE_HEADER_RE = re.compile(
    r"Global Natural Disaster Emergency Safety Guidelines[^\n]*Page \d+",
    re.IGNORECASE,
)
_CHAPTER_RE = re.compile(r"DISASTER TYPE \d+\s*\n([^\n]+)", re.IGNORECASE)


def _extract_pdf_text() -> str:
    doc = fitz.open(str(PDF_PATH))
    pages: list[str] = []
    for page in doc:
        text = page.get_text()
        text = _PAGE_HEADER_RE.sub("", text)
        pages.append(text.strip())
    doc.close()
    return "\n\n".join(p for p in pages if p)


def _split_chapters(full_text: str) -> list[tuple[str, str]]:
    """Split the full PDF text into (chapter_text, disaster_type_label) pairs."""
    boundaries = [
        (m.start(), m.group(1).strip().lower())
        for m in _CHAPTER_RE.finditer(full_text)
    ]
    if not boundaries:
        return [(full_text, "general")]
    chapters: list[tuple[str, str]] = []
    for i, (pos, label) in enumerate(boundaries):
        end = boundaries[i + 1][0] if i + 1 < len(boundaries) else len(full_text)
        chapters.append((full_text[pos:end].strip(), label))
    return chapters


# ── Semantic chunking (winning strategy from chunking_report.md) ──────────────

_SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")


def _semantic_chunks_for_chapter(
    chapter_text: str,
    disaster_type: str,
    model: SentenceTransformer,
    threshold: float = 0.45,
    min_sents: int = 3,
    max_sents: int = 15,
) -> list[dict]:
    sentences = [
        s.strip()
        for s in _SENT_SPLIT_RE.split(chapter_text)
        if len(s.strip()) > 20
    ]
    if len(sentences) < 2:
        if len(chapter_text.strip()) > 60:
            return [{
                "text": chapter_text.strip(),
                "metadata": {
                    "strategy": "semantic",
                    "disaster_type": disaster_type,
                    "chunk_index": 0,
                },
            }]
        return []

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
                "metadata": {
                    "strategy": "semantic",
                    "disaster_type": disaster_type,
                    "chunk_index": len(chunks),
                },
            })
            bucket = [next_sent]
        else:
            bucket.append(next_sent)

    if bucket:
        chunks.append({
            "text": " ".join(bucket),
            "metadata": {
                "strategy": "semantic",
                "disaster_type": disaster_type,
                "chunk_index": len(chunks),
            },
        })

    return [c for c in chunks if len(c["text"].strip()) > 60]


# ── Embedding + ChromaDB persistence ─────────────────────────────────────────

def _embed_batch(texts: list[str], model: SentenceTransformer) -> list[list[float]]:
    return model.encode(
        texts, batch_size=32, show_progress_bar=False, convert_to_numpy=True
    ).tolist()


def _persist(chunks: list[dict], model: SentenceTransformer) -> chromadb.Collection:
    CHROMA_PATH.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(CHROMA_PATH))

    # Idempotent: drop existing collection so re-runs never duplicate chunks
    existing = [c.name for c in client.list_collections()]
    if COLLECTION_NAME in existing:
        client.delete_collection(COLLECTION_NAME)
        print(f"  Deleted existing collection '{COLLECTION_NAME}' (clean rebuild)")

    col = client.create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )

    texts = [c["text"] for c in chunks]
    metas = [c["metadata"] for c in chunks]
    ids   = [str(uuid.uuid4()) for _ in chunks]

    batch_size = 128
    for start in range(0, len(texts), batch_size):
        sl = slice(start, start + batch_size)
        col.add(
            documents=texts[sl],
            embeddings=_embed_batch(texts[sl], model),
            ids=ids[sl],
            metadatas=metas[sl],
        )
        end_idx = min(start + batch_size, len(texts))
        print(f"  Ingested {end_idx}/{len(texts)} chunks...")

    return col


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
    print(f"Extracted {len(full_text):,} characters.\n")

    print("Splitting into disaster-type chapters...")
    chapters = _split_chapters(full_text)
    print(f"Found {len(chapters)} chapters: {[label for _, label in chapters]}\n")

    print("Generating semantic chunks per chapter...")
    all_chunks: list[dict] = []
    for chapter_text, disaster_type in chapters:
        ch_chunks = _semantic_chunks_for_chapter(chapter_text, disaster_type, model)
        print(f"  {disaster_type:40s} -> {len(ch_chunks)} chunks")
        all_chunks.extend(ch_chunks)
    print(f"\nTotal chunks: {len(all_chunks)}\n")

    print(f"Persisting to ChromaDB at: {CHROMA_PATH}")
    col = _persist(all_chunks, model)

    print(f"\nCollection '{COLLECTION_NAME}' ready.")
    print(f"Total documents in collection: {col.count()}")

    # Spot-check: show a sample chunk with its metadata
    sample = col.query(
        query_texts=["What should I do during an earthquake to stay safe?"],
        n_results=1,
    )
    print("\n-- Sample retrieval (earthquake safety query) --")
    print(f"  metadata : {sample['metadatas'][0][0]}")
    print(f"  text     : {sample['documents'][0][0][:200]}...")

    print(f"\nChromaDB directory: {CHROMA_PATH}")
    print("Ingestion complete.")
