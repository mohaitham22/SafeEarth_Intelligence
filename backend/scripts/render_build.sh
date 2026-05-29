#!/bin/bash
# Render build command — runs once per deploy before the service starts.
# Render clones the repo to /opt/render/project/src by default.
# Start command (set in render.yaml): cd backend && uvicorn main:app --host 0.0.0.0 --port $PORT
set -e

# Install Python dependencies
pip install -r backend/requirements.txt

# Generate precomputed EM-DAT JSON files (idempotent — fast if already present)
python scripts/generate_emdat_stats.py

# NOTE: RAG ingest (backend/rag/ingest.py) is NOT run here.
# Reason: it downloads ~80MB sentence-transformers model + generates 167 embeddings —
# too slow/memory-heavy for Render free-tier builds. The app starts with rag_loaded=false
# and automatically falls back to the seeded recommendations DB table (12 rows).
# To enable live RAG: SSH into the Render service and run:
#   python backend/rag/ingest.py
# or upgrade to a paid Render plan with more build resources.

# Apply any pending Alembic migrations
# alembic.ini lives in the project root — run from there, not from backend/
alembic upgrade head
