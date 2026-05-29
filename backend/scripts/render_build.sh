#!/bin/bash
# Render build command — runs once per deploy before the service starts.
# Render clones the repo to /opt/render/project/src by default.
# Start command (set in render.yaml): cd backend && uvicorn main:app --host 0.0.0.0 --port $PORT
set -e

# Install Python dependencies
pip install -r backend/requirements.txt

# Generate precomputed EM-DAT JSON files (idempotent — fast if already present)
python scripts/generate_emdat_stats.py

# Extract PDF safety guidelines into chapters.json (fast, no ML deps — uses only PyMuPDF).
# Replaces the old ChromaDB+sentence-transformers pipeline which required PyTorch (~2 GB)
# and caused OOM on Render's 512 MB free tier.
python backend/rag/extract_chapters.py

# Apply any pending Alembic migrations
# alembic.ini lives in the project root — run from there, not from backend/
alembic upgrade head

# Seed recommendations table (idempotent — skips rows that already exist).
# Ensures all 8 disaster types x 4 severity levels have 6 fallback rows
# so the RAG DB fallback works for every prediction when Groq is unavailable.
python scripts/seed_recommendations.py
