import sys
from pathlib import Path

# When backend/ is imported as a package from the project root
# (e.g. `from backend.services.auth_service import *` in tests or the verify command),
# bare intra-backend imports like `from config import get_settings` won't resolve
# unless backend/ is on sys.path. Add it here so it runs once on first package import.
_backend_dir = str(Path(__file__).resolve().parent)
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)
