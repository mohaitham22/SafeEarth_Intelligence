"""Background watcher: poll the live prediction until the NEW per-type model is
serving (Flood est_damage_usd flips 15752 -> 114418). Safe to delete."""
import json
import time
import urllib.request
from datetime import datetime, timezone

BASE = "https://api.safeearth.tech/api/v1"
OLD_DMG, NEW_DMG = 15752, 114418


def _post(path, body, token=None, timeout=25):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(), method="POST")
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def probe():
    tok = _post("/auth/login", {"email": "subscriber@safeearth.dev", "password": "SafeEarth2026!"})["access_token"]
    r = _post("/predictions/predict", {
        "latitude": 30.0444, "longitude": 31.2357, "country": "Egypt",
        "continent": "Africa", "season": "summer", "disaster_type": "Flood"}, tok)
    return r["estimated_damage_usd"]


new_hits = 0
for i in range(40):  # ~20 min max at 30s cadence
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    try:
        dmg = probe()
        state = "NEW" if dmg == NEW_DMG else ("OLD" if dmg == OLD_DMG else f"OTHER({dmg})")
        print(f"{ts} {state} damage={dmg}", flush=True)
        if dmg == NEW_DMG:
            new_hits += 1
            if new_hits >= 2:
                print(f"{ts} NEW MODEL CONFIRMED LIVE", flush=True)
                break
        else:
            new_hits = 0
    except Exception as e:
        print(f"{ts} UNREACHABLE ({type(e).__name__})", flush=True)
        new_hits = 0
    time.sleep(30)
