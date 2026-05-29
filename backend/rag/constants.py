from pathlib import Path

_THIS_DIR = Path(__file__).resolve().parent

COLLECTION_NAME = "safety_guidelines"
EMBED_MODEL     = "all-MiniLM-L6-v2"
CHROMA_PATH     = _THIS_DIR / "chroma_db"
PDF_PATH        = _THIS_DIR / "docs" / "Natural_Disaster_Safety_Guidelines.pdf"
