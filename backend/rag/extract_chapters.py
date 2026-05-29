"""
Run-once (or build-time) script that extracts the disaster-type chapters
from the PDF knowledge base into a plain JSON file.

Output: backend/rag/chapters.json
  {
    "flood": "<full chapter text>",
    "earthquake": "<full chapter text>",
    ...
  }

This replaces the need for ChromaDB + sentence-transformers + PyTorch at
runtime.  The JSON file is committed to the repo so that Render can load
it at startup without any heavy ML dependencies.

Usage:
    py -3.12 backend/rag/extract_chapters.py        # from project root
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# Allow running from project root without installing the package
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import fitz  # PyMuPDF — already in requirements.txt

from rag.constants import PDF_PATH

_THIS_DIR = Path(__file__).resolve().parent
CHAPTERS_PATH = _THIS_DIR / "chapters.json"

_PAGE_HEADER_RE = re.compile(
    r"Global Natural Disaster Emergency Safety Guidelines[^\n]*Page \d+",
    re.IGNORECASE,
)
_CHAPTER_RE = re.compile(r"DISASTER TYPE \d+\s*\n([^\n]+)", re.IGNORECASE)

# Map PDF chapter labels (lowercase) → EM-DAT canonical disaster type names.
# All 8 EM-DAT types must appear here.
_EMDAT_TO_CHAPTER: dict[str, str] = {
    "Flood":               "flood",
    "Storm":               "storm",
    "Earthquake":          "earthquake",
    "Wildfire":            "wildfire",
    "Volcanic activity":   "volcanic activity",
    "Landslide":           "landslide",
    "Drought":             "drought",
    "Extreme temperature": "extreme temperature",
}

# Reverse: PDF label → EM-DAT type
_CHAPTER_TO_EMDAT: dict[str, str] = {
    v: k for k, v in _EMDAT_TO_CHAPTER.items()
}


def _extract_pdf_text() -> str:
    doc = fitz.open(str(PDF_PATH))
    pages: list[str] = []
    for page in doc:
        text = page.get_text()
        text = _PAGE_HEADER_RE.sub("", text)
        pages.append(text.strip())
    doc.close()
    return "\n\n".join(p for p in pages if p)


def _split_chapters(full_text: str) -> dict[str, str]:
    """Return {chapter_label_lowercase: chapter_text} for all chapters."""
    boundaries: list[tuple[int, str]] = [
        (m.start(), m.group(1).strip().lower())
        for m in _CHAPTER_RE.finditer(full_text)
    ]
    if not boundaries:
        return {"general": full_text}

    result: dict[str, str] = {}
    for i, (pos, label) in enumerate(boundaries):
        end = boundaries[i + 1][0] if i + 1 < len(boundaries) else len(full_text)
        result[label] = full_text[pos:end].strip()
    return result


def build_chapters_json() -> dict[str, str]:
    """
    Extract chapters from the PDF and return a mapping
    {emdat_disaster_type: chapter_text} for all 8 EM-DAT types.
    """
    print(f"  Reading PDF: {PDF_PATH}")
    full_text = _extract_pdf_text()

    all_chapters = _split_chapters(full_text)
    print(f"  Found {len(all_chapters)} chapters: {list(all_chapters.keys())}")

    chapters: dict[str, str] = {}
    for emdat_type, chapter_label in _EMDAT_TO_CHAPTER.items():
        text = all_chapters.get(chapter_label)
        if text:
            chapters[emdat_type] = text
            print(f"  Mapped '{emdat_type}' <- '{chapter_label}' ({len(text):,} chars)")
        else:
            print(f"  WARNING: chapter '{chapter_label}' not found for '{emdat_type}'")

    return chapters


if __name__ == "__main__":
    print("Extracting disaster safety chapters from PDF...")
    chapters = build_chapters_json()
    CHAPTERS_PATH.write_text(json.dumps(chapters, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSaved {len(chapters)} chapters to {CHAPTERS_PATH}")
    print(f"File size: {CHAPTERS_PATH.stat().st_size / 1024:.0f} KB")
