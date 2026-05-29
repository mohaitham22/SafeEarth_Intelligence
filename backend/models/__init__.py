import sys
from pathlib import Path

# Ensure backend/ is on sys.path so bare `from database import Base` works
# both when uvicorn runs from backend/ and when the package is imported from project root.
_backend_dir = str(Path(__file__).resolve().parent.parent)
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from .alert import Alert
from .payment import Payment
from .prediction import Prediction
from .premium_email_log import PremiumEmailLog
from .premium_plan import PremiumPlan
from .recommendation import Recommendation
from .subscription import Subscription
from .user import User

__all__ = [
    "User",
    "Subscription",
    "Prediction",
    "Alert",
    "Recommendation",
    "PremiumPlan",
    "Payment",
    "PremiumEmailLog",
]
