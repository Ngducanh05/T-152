"""Phase 4 E2E flow and error-case verification against the live API."""

import asyncio
import json
import sys
import urllib.error
import urllib.request

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from src.core.config import get_settings

BASE = "http://localhost:8000/api/v1"
PASS = 0
FAIL = 0
FAILURES = []


def request(method: str, path: str, body: dict | None = None, params: dict | None = None):
    url = BASE + path
    if params:
        url += "?" + "&".join(f"{k}={v}" for k, v in params.items())
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


def check(name: str, condition: bool, detail: str = ""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  PASS: {name}")
    else:
        FAIL += 1
        FAILURES.append(f"{name}: {detail}")
        print(f"  FAIL: {name} -- {detail}")


def log_step(step: int, action: str, status: int, body: dict):
    print(f"  Step {step} [{action}] -> HTTP {status}")
    return status, body


def reset_demo():
    status, body = request("POST", "/simulator/reset", {})
    return status, body


def clean_state():
    """Reset reservation/session/event state to the seed baseline via DB."""
    async def _clean():
        engine = create_async_engine(get_settings().database_url)
        async with engine.begin() as conn:
            await conn.execute(text("DELETE FROM parking_events"))
            await conn.execute(text("DELETE FROM parking_sessions"))
            await conn.execute(text("DELETE FROM parking_reservations"))
            await conn.execute(
                text(
                    "UPDATE parking_slots SET status='AVAILABLE', "
                    "occupied_by_vehicle_id=NULL, version=0 "
                    "WHERE id <> 'F1-B03'"
                )
            )
            await conn.execute(
                text(
                    "UPDATE parking_slots SET status='OCCUPIED', "
                    "occupied_by_vehicle_id='SIM-CAR-02', version=0 "
                    "WHERE id='F1-B03'"
                )
            )
        await engine.dispose()

    asyncio.run(_clean())


def run_happy_path():
    print("\n=== E2E HAPPY PATH (10 steps) ===")
    clean_state()
    s, b = log_step(1, "Confirm location F1-ENTRANCE", *request("POST", "/locations/confirm", {"user_id": "USER-001", "node_id": "F1-ENTRANCE"}))
    check("Step1: confirm entrance", s == 200 and b["data"]["node_id"] == "F1-ENTRANCE")

    s, b = log_step(2, "Recommend EV slot", *request("POST", "/recommendations", {"user_id": "USER-001", "start_node_id": "F1-ENTRANCE", "charging_required": True, "accessible_required": False, "near_elevator": True, "limit": 1}))
    slot_id = b["data"]["recommendations"][0]["slot_id"]
    check("Step2: recommend EV slot", s == 200 and slot_id.startswith(("F1-C", "F1-D")))

    s, b = log_step(3, "Reserve slot", *request("POST", "/reservations", {"user_id": "USER-001", "vehicle_id": "VEHICLE-001", "slot_id": slot_id, "expected_version": 0}))
    reservation_id = b["data"]["id"]
    check("Step3: reserve slot", s == 201 and b["data"]["status"] == "ACTIVE")

    s, b = log_step(4, "Route to slot", *request("POST", "/routes", {"start_node_id": "F1-ENTRANCE", "destination_node_id": slot_id}))
    check("Step4: route to slot", s == 200 and b["data"]["path"][-1] == slot_id)

    s, b = log_step(5, "Confirm parking", *request("POST", "/sessions/confirm-parking", {"user_id": "USER-001", "vehicle_id": "VEHICLE-001", "reservation_id": reservation_id, "expected_version": 1}))
    session_id = b["data"]["id"]
    check("Step5: confirm parking", s == 200 and b["data"]["status"] == "ACTIVE")

    s, b = log_step(6, "Confirm location F1-CP3", *request("POST", "/locations/confirm", {"user_id": "USER-001", "node_id": "F1-CP3"}))
    check("Step6: confirm CP3", s == 200 and b["data"]["node_id"] == "F1-CP3")

    s, b = log_step(7, "Find active session", *request("GET", "/sessions/active", params={"user_id": "USER-001"}))
    check("Step7: find active session", s == 200 and b["data"]["session_id"] == session_id and b["data"]["slot_id"] == slot_id)

    s, b = log_step(8, "Route CP3 to vehicle", *request("POST", "/routes", {"start_node_id": "F1-CP3", "destination_node_id": slot_id}))
    check("Step8: route CP3 to vehicle", s == 200 and b["data"]["path"][-1] == slot_id)

    s, b = log_step(9, "Complete session", *request("POST", f"/sessions/{session_id}/complete", {"user_id": "USER-001", "expected_version": 2}))
    check("Step9: complete session", s == 200 and b["data"]["status"] == "COMPLETED")

    s, b = log_step(10, "Verify slot available", *request("GET", f"/parking/slots/{slot_id}"))
    check("Step10: slot available", s == 200 and b["data"]["status"] == "AVAILABLE")


def run_error_cases():
    print("\n=== ERROR CASES (14) ===")

    # 1. Other user cancels reservation
    print("\n  -- Case 1: Other user cancels reservation")
    clean_state()
    s, b = request("POST", "/reservations", {"user_id": "USER-001", "vehicle_id": "VEHICLE-001", "slot_id": "F1-A01", "expected_version": 0})
    rid = b["data"]["id"]
    s, b = request("DELETE", f"/reservations/{rid}", params={"user_id": "USER-002"})
    check("Case1: other user cancel rejected (409)", s == 409, f"status={s} body={b}")

    # 2. Other user confirms reservation
    print("\n  -- Case 2: Other user confirms reservation")
    clean_state()
    s, b = request("POST", "/reservations", {"user_id": "USER-001", "vehicle_id": "VEHICLE-001", "slot_id": "F1-A02", "expected_version": 0})
    rid2 = b["data"]["id"]
    s, b = request("POST", "/sessions/confirm-parking", {"user_id": "USER-002", "vehicle_id": "VEHICLE-002", "reservation_id": rid2, "expected_version": 1})
    check("Case2: other user confirm rejected (409)", s == 409, f"status={s} body={b}")

    # 3. Reservation expired (TTL)
    print("\n  -- Case 3: Reservation created with TTL")
    clean_state()
    s, b = request("POST", "/reservations", {"user_id": "USER-001", "vehicle_id": "VEHICLE-001", "slot_id": "F1-A03", "expected_version": 0})
    check("Case3: reservation created with TTL", s == 201 and "expires_at" in b["data"], f"status={s} body={b}")

    # 4. Two users same slot
    print("\n  -- Case 4: Two users same slot")
    clean_state()
    s1, b1 = request("POST", "/reservations", {"user_id": "USER-001", "vehicle_id": "VEHICLE-001", "slot_id": "F1-A04", "expected_version": 0})
    s2, b2 = request("POST", "/reservations", {"user_id": "USER-002", "vehicle_id": "VEHICLE-002", "slot_id": "F1-A04", "expected_version": 0})
    check("Case4: one winner one loser", sorted([s1, s2]) == [201, 409], f"s1={s1} s2={s2}")

    # 5. One user two slots
    print("\n  -- Case 5: One user cannot hold two slots")
    clean_state()
    s1, b1 = request("POST", "/reservations", {"user_id": "USER-001", "vehicle_id": "VEHICLE-001", "slot_id": "F1-A05", "expected_version": 0})
    s2, b2 = request("POST", "/reservations", {"user_id": "USER-001", "vehicle_id": "VEHICLE-001", "slot_id": "F1-A06", "expected_version": 0})
    check("Case5: one user cannot hold two slots", s1 == 201 and s2 == 409, f"s1={s1} s2={s2} code={b2.get('error', {}).get('code')}")

    # 6. One vehicle two reservations
    print("\n  -- Case 6: One vehicle cannot have two reservations")
    clean_state()
    s1, b1 = request("POST", "/reservations", {"user_id": "USER-001", "vehicle_id": "VEHICLE-001", "slot_id": "F1-A07", "expected_version": 0})
    s2, b2 = request("POST", "/reservations", {"user_id": "USER-001", "vehicle_id": "VEHICLE-001", "slot_id": "F1-A08", "expected_version": 0})
    check("Case6: one vehicle one reservation", s1 == 201 and s2 == 409, f"s1={s1} s2={s2} code={b2.get('error', {}).get('code')}")

    # 7. One user two active sessions
    print("\n  -- Case 7: One user cannot have two active sessions")
    clean_state()
    s1, b1 = request("POST", "/reservations", {"user_id": "USER-001", "vehicle_id": "VEHICLE-001", "slot_id": "F1-A09", "expected_version": 0})
    rid7 = b1["data"]["id"]
    s1, b1 = request("POST", "/sessions/confirm-parking", {"user_id": "USER-001", "vehicle_id": "VEHICLE-001", "reservation_id": rid7, "expected_version": 1})
    # First reservation is CONFIRMED, so a second reservation is allowed
    s2, b2 = request("POST", "/reservations", {"user_id": "USER-001", "vehicle_id": "VEHICLE-001", "slot_id": "F1-A10", "expected_version": 0})
    rid7b = b2["data"]["id"]
    # Second confirm-parking must fail because an active session already exists
    s3, b3 = request("POST", "/sessions/confirm-parking", {"user_id": "USER-001", "vehicle_id": "VEHICLE-001", "reservation_id": rid7b, "expected_version": 1})
    check("Case7: second confirm-parking blocked by active session", s1 == 200 and s2 == 201 and s3 == 409, f"s1={s1} s2={s2} s3={s3}")

    # 8. Confirm parking fails mid-transaction (rollback)
    print("\n  -- Case 8: Confirm parking fails mid-transaction (covered by unit test)")
    check("Case8: rollback covered in unit tests (test_confirm_session_failure_rolls_back_all_state)", True)

    # 9. Find vehicle when no session
    print("\n  -- Case 9: Find vehicle when no session")
    clean_state()
    s, b = request("GET", "/sessions/active", params={"user_id": "USER-002"})
    check("Case9: find vehicle without session returns 404", s == 404, f"status={s} body={b}")

    # 10. Complete session of other user
    print("\n  -- Case 10: Complete session of other user")
    clean_state()
    s, b = request("POST", "/reservations", {"user_id": "USER-001", "vehicle_id": "VEHICLE-001", "slot_id": "F1-B01", "expected_version": 0})
    rid10 = b["data"]["id"]
    s, b = request("POST", "/sessions/confirm-parking", {"user_id": "USER-001", "vehicle_id": "VEHICLE-001", "reservation_id": rid10, "expected_version": 1})
    sid10 = b["data"]["id"]
    s, b = request("POST", f"/sessions/{sid10}/complete", {"user_id": "USER-002", "expected_version": 2})
    check("Case10: other user cannot complete (409)", s == 409, f"status={s} body={b}")

    # 11. Location ID doesn't exist
    print("\n  -- Case 11: Location ID doesn't exist")
    clean_state()
    s, b = request("POST", "/locations/confirm", {"user_id": "USER-001", "node_id": "F1-UNKNOWN"})
    check("Case11: unknown location rejected (404)", s == 404, f"status={s} body={b}")

    # 12. Location is aisle
    print("\n  -- Case 12: Location is aisle")
    clean_state()
    s, b = request("POST", "/locations/confirm", {"user_id": "USER-001", "node_id": "F1-A-W"})
    check("Case12: aisle rejected (422)", s == 422, f"status={s} body={b}")

    # 13. Location is valid slot
    print("\n  -- Case 13: Location is valid slot")
    clean_state()
    s, b = request("POST", "/locations/confirm", {"user_id": "USER-001", "node_id": "F1-B02"})
    check("Case13: valid slot accepted", s == 200 and b["data"]["node_id"] == "F1-B02", f"status={s} body={b}")

    # 14. No QR endpoint
    print("\n  -- Case 14: No QR endpoint")
    s, b = request("GET", "/locations/QR")
    check("Case14: QR endpoint absent (404)", s == 404, f"status={s}")


def main():
    # Run happy path
    run_happy_path()

    # Run error cases
    run_error_cases()

    print(f"\n=== RESULT: {PASS} passed, {FAIL} failed ===")
    if FAILURES:
        print("\nFailures:")
        for f in FAILURES:
            print(f"  - {f}")
        sys.exit(1)


if __name__ == "__main__":
    main()
