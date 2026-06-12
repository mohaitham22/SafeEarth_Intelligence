"""Local reproduction of the live predict() path with the NEW pkl, to prove the
live deploy matches working-tree code+model. Safe to delete."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import config  # noqa: E402
from ml import emdat_lookup, predictor  # noqa: E402

settings = config.get_settings()
emdat_lookup.load_all(settings.data_generated_dir)
predictor.load_models(settings.saved_models_dir)

fields = ["disaster_type", "probability_score", "severity_level", "risk_score",
          "estimated_deaths", "estimated_injuries", "estimated_affected",
          "estimated_damage_usd", "uninsured_loss_usd", "data_source"]
out = {}
for dt in ["Flood", "Earthquake"]:
    r = predictor.predict(
        lat=30.0444, lon=31.2357, disaster_type=dt,
        magnitude=None, season="summer", continent="Africa",
        country="Egypt", region=None,
    )
    out[dt] = {k: r.get(k) for k in fields}
print(json.dumps(out, indent=2))
