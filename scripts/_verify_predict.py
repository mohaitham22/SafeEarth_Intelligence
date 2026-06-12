"""Temp deploy-verification helper. Logs in as the seeded subscriber and runs
two predictions at identical Cairo coords (Flood vs Earthquake) so we can
compare impact numbers before/after a deploy. Safe to delete."""
import json
import sys
import urllib.request

BASE = "https://api.safeearth.tech/api/v1"
EMAIL = "subscriber@safeearth.dev"
PASSWORD = "SafeEarth2026!"


def _post(path, body, token=None):
    data = json.dumps(body).encode()
    req = urllib.request.Request(BASE + path, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


def main():
    tok = _post("/auth/login", {"email": EMAIL, "password": PASSWORD})["access_token"]
    base = {"latitude": 30.0444, "longitude": 31.2357,
            "country": "Egypt", "continent": "Africa", "season": "summer"}
    fields = ["disaster_type", "probability_score", "severity_level", "risk_score",
              "estimated_deaths", "estimated_injuries", "estimated_affected",
              "estimated_damage_usd", "uninsured_loss_usd", "data_source", "model_version"]
    out = {}
    for dt in ["Flood", "Earthquake"]:
        r = _post("/predictions/predict", {**base, "disaster_type": dt}, tok)
        out[dt] = {k: r.get(k) for k in fields}
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    sys.exit(main())
