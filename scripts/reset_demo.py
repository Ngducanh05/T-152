"""Reset the demo through public HTTP APIs and verify its canonical baseline."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

DEMO_USER_ID = "USER-001"
DEMO_START_NODE_ID = "F1-ENTRANCE"
BASELINE_SLOT_ID = "F1-B03"
BASELINE_VEHICLE_ID = "SIM-CAR-02"


def request_json(
    base_url: str,
    method: str,
    path: str,
    *,
    query: dict[str, str] | None = None,
) -> tuple[int, dict[str, Any]]:
    url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
    if query:
        url = f"{url}?{urlencode(query)}"
    body = b"{}" if method == "POST" else None
    request = Request(
        url,
        data=body,
        method=method,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=15) as response:  # noqa: S310 - operator URL
            return response.status, json.load(response)
    except HTTPError as error:
        try:
            payload = json.load(error)
        except (json.JSONDecodeError, UnicodeDecodeError):
            payload = {"error": {"message": error.reason}}
        return error.code, payload


def require_success(status: int, payload: dict[str, Any], operation: str) -> Any:
    if status != 200 or payload.get("success") is not True:
        raise RuntimeError(f"{operation} failed ({status}): {json.dumps(payload)}")
    return payload["data"]


def verify_baseline(base_url: str) -> None:
    status_code, payload = request_json(base_url, "GET", "/parking/status")
    status = require_success(status_code, payload, "parking status verification")
    expected_counts = {"total": 40, "available": 39, "reserved": 0, "occupied": 1}
    actual_counts = {key: status.get(key) for key in expected_counts}
    if actual_counts != expected_counts:
        raise RuntimeError(f"Unexpected parking counts: {actual_counts}")

    status_code, payload = request_json(base_url, "GET", "/parking/slots")
    slots = require_success(status_code, payload, "parking slot verification")
    occupied = [slot for slot in slots if slot["status"] == "OCCUPIED"]
    if len(occupied) != 1 or (
        occupied[0]["id"], occupied[0]["occupied_by_vehicle_id"]
    ) != (BASELINE_SLOT_ID, BASELINE_VEHICLE_ID):
        raise RuntimeError(f"Unexpected occupied slots: {occupied}")

    status_code, payload = request_json(
        base_url,
        "GET",
        "/locations/current",
        query={"user_id": DEMO_USER_ID},
    )
    location = require_success(status_code, payload, "location verification")
    if location.get("node_id") != DEMO_START_NODE_ID:
        raise RuntimeError(f"Unexpected demo-user location: {location}")

    for path, label in (
        ("/reservations/active", "reservation"),
        ("/sessions/active", "parking session"),
    ):
        status_code, payload = request_json(
            base_url,
            "GET",
            path,
            query={"user_id": DEMO_USER_ID},
        )
        if status_code != 404:
            raise RuntimeError(f"Expected no active {label}, got ({status_code}): {payload}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default=os.getenv("PARKSMART_API_BASE_URL", "http://127.0.0.1:8000/api/v1"),
        help="Public API v1 base URL",
    )
    args = parser.parse_args()

    try:
        status, payload = request_json(args.base_url, "POST", "/simulator/reset")
        require_success(status, payload, "demo reset")
        verify_baseline(args.base_url)
    except (RuntimeError, URLError, TimeoutError) as error:
        print(f"Demo reset failed: {error}", file=sys.stderr)
        return 1

    print("Demo reset verified: 40 total, 39 available, 0 reserved, 1 occupied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
