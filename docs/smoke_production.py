"""
Production smoke test — run after every Render deployment.

Usage:
    py -3.12 docs/smoke_production.py --base-url https://api.safeearth.tech
    py -3.12 docs/smoke_production.py --base-url http://localhost:8000   # local

Exits 0 if all checks pass, 1 if any fail.
"""

import argparse
import sys
import time
import urllib.request
import urllib.error
import json


def get(url: str, timeout: int = 15) -> tuple[int, dict]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, {}
    except Exception as e:
        return 0, {"error": str(e)}


def check(label: str, url: str, expected_status: int = 200, assertions: list = None) -> bool:
    print(f"  {label} ... ", end="", flush=True)
    status, body = get(url)
    if status != expected_status:
        print(f"FAIL  (HTTP {status}, expected {expected_status})")
        print(f"         URL: {url}")
        if body:
            print(f"         Body: {str(body)[:200]}")
        return False

    if assertions:
        for key, expected_value in assertions:
            actual = body
            for part in key.split("."):
                actual = actual.get(part, None) if isinstance(actual, dict) else None
            if actual != expected_value:
                print(f"FAIL  ({key} = {actual!r}, expected {expected_value!r})")
                return False

    print("OK")
    return True


def main():
    parser = argparse.ArgumentParser(description="SafeEarth production smoke test")
    parser.add_argument(
        "--base-url",
        default="https://api.safeearth.tech",
        help="Backend base URL (no trailing slash)",
    )
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    print(f"\nSafeEarth Production Smoke Test")
    print(f"Target: {base}")
    print(f"{'-' * 50}")

    results = []

    # ── 1. Health endpoint ────────────────────────────────────────────────────
    print("\n[1/6] Health check")
    ok = check(
        "GET /api/v1/health",
        f"{base}/api/v1/health",
        assertions=[("status", "ok"), ("models_loaded", True)],
    )
    results.append(("health", ok))
    if ok:
        # also check rag_loaded (non-fatal)
        _, body = get(f"{base}/api/v1/health")
        rag = body.get("rag_loaded", False)
        tag = "OK" if rag else "WARN (rag_loaded=false — GROQ_API_KEY may be missing)"
        print(f"  rag_loaded ... {tag}")

    # ── 2–6. Static region endpoints ─────────────────────────────────────────
    print("\n[2/6] Regions: trends")
    ok = check("GET /api/v1/regions/trends", f"{base}/api/v1/regions/trends")
    results.append(("regions/trends", ok))

    print("\n[3/6] Regions: continent-stats")
    ok = check("GET /api/v1/regions/continent-stats", f"{base}/api/v1/regions/continent-stats")
    results.append(("regions/continent-stats", ok))

    print("\n[4/6] Regions: seasonal-peaks")
    ok = check("GET /api/v1/regions/seasonal-peaks", f"{base}/api/v1/regions/seasonal-peaks")
    results.append(("regions/seasonal-peaks", ok))

    print("\n[5/6] Regions: secondary-disasters")
    ok = check("GET /api/v1/regions/secondary-disasters", f"{base}/api/v1/regions/secondary-disasters")
    results.append(("regions/secondary-disasters", ok))

    print("\n[6/6] Regions: risk-map")
    ok = check("GET /api/v1/regions/risk-map", f"{base}/api/v1/regions/risk-map")
    results.append(("regions/risk-map", ok))

    # ── Summary ───────────────────────────────────────────────────────────────
    passed = sum(1 for _, ok in results if ok)
    total  = len(results)
    print(f"\n{'-' * 50}")
    print(f"Result: {passed}/{total} checks passed")

    if passed == total:
        print("All checks PASSED. Backend is healthy.")
        sys.exit(0)
    else:
        failed = [name for name, ok in results if not ok]
        print(f"FAILED checks: {', '.join(failed)}")
        print("Check Render logs for details.")
        sys.exit(1)


if __name__ == "__main__":
    main()
