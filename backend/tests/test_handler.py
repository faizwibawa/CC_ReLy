"""Unit tests for the ReLy Lambda handler (no AWS access needed).

Run from the repository root:
    python -m unittest discover -s backend/tests -v
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import handler  # noqa: E402
from repository import InMemorySignalRepository  # noqa: E402

VALID = {
    "signal_id": "YK-TEST-01",
    "location": "Test Junction, Yogyakarta",
    "latitude": -7.7829,
    "longitude": 110.3671,
    "current_phase": "RED",
    "remaining_seconds": 30,
    "confidence_score": 0.9,
    "congestion_level": "HEAVY",
    "detour": {"label": "Turn left via side street", "lat": -7.789, "lng": 110.361},
    "data_source": "MANUAL",
}


def event(method, path, body=None, query=None):
    return {
        "rawPath": path,
        "requestContext": {"http": {"method": method, "path": path}},
        "body": None if body is None else json.dumps(body),
        "queryStringParameters": query,
        "isBase64Encoded": False,
    }


def call(method, path, body=None, query=None):
    res = handler.lambda_handler(event(method, path, body, query), None)
    return res["statusCode"], json.loads(res["body"]) if res.get("body") else None


class HandlerTests(unittest.TestCase):
    def setUp(self):
        handler.set_repo(InMemorySignalRepository())

    # ---- health / routing
    def test_health(self):
        status, body = call("GET", "/")
        self.assertEqual(status, 200)
        self.assertEqual(body["status"], "ok")

    def test_unknown_route(self):
        self.assertEqual(call("GET", "/nope")[0], 404)

    def test_method_not_allowed(self):
        self.assertEqual(call("PATCH", "/signals")[0], 405)

    # ---- create
    def test_create_and_read(self):
        status, body = call("POST", "/signals", VALID)
        self.assertEqual(status, 201)
        self.assertEqual(body["signal_id"], "YK-TEST-01")
        self.assertIn("phase_ends_at", body)
        self.assertIn("updated_at", body)
        self.assertTrue(29 <= body["remaining_seconds"] <= 30)

        status, body = call("GET", "/signals/YK-TEST-01")
        self.assertEqual(status, 200)
        self.assertEqual(body["detour"]["label"], "Turn left via side street")

    def test_create_duplicate_returns_409(self):
        call("POST", "/signals", VALID)
        status, body = call("POST", "/signals", VALID)
        self.assertEqual(status, 409)
        self.assertEqual(body["error"]["code"], "ALREADY_EXISTS")

    def test_create_missing_fields(self):
        status, body = call("POST", "/signals", {"signal_id": "X"})
        self.assertEqual(status, 400)
        self.assertTrue(any("missing required" in d for d in body["error"]["details"]))

    def test_create_rejects_invalid_values(self):
        bad = dict(
            VALID,
            current_phase="BLUE",
            remaining_seconds=-5,
            confidence_score=1.5,
            latitude=200,
            data_source="ROBOT",
            congestion_level="JAMMED",
        )
        status, body = call("POST", "/signals", bad)
        self.assertEqual(status, 400)
        self.assertEqual(len(body["error"]["details"]), 6)

    def test_create_rejects_bad_json(self):
        res = handler.lambda_handler(
            {"rawPath": "/signals", "requestContext": {"http": {"method": "POST"}}, "body": "{oops"},
            None,
        )
        self.assertEqual(res["statusCode"], 400)

    def test_boolean_is_not_a_number(self):
        status, _ = call("POST", "/signals", dict(VALID, confidence_score=True))
        self.assertEqual(status, 400)

    # ---- list
    def test_list(self):
        call("POST", "/signals", VALID)
        call("POST", "/signals", dict(VALID, signal_id="YK-TEST-02"))
        status, body = call("GET", "/signals")
        self.assertEqual(status, 200)
        self.assertEqual(body["count"], 2)
        self.assertEqual([i["signal_id"] for i in body["items"]], ["YK-TEST-01", "YK-TEST-02"])

    # ---- update
    def test_partial_update(self):
        call("POST", "/signals", VALID)
        status, body = call(
            "PUT", "/signals/YK-TEST-01", {"current_phase": "GREEN", "remaining_seconds": 25}
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["current_phase"], "GREEN")
        self.assertEqual(body["location"], VALID["location"])  # untouched field kept

    def test_update_missing_returns_404(self):
        self.assertEqual(call("PUT", "/signals/NOPE", {"current_phase": "RED"})[0], 404)

    def test_update_id_mismatch(self):
        call("POST", "/signals", VALID)
        status, _ = call("PUT", "/signals/YK-TEST-01", {"signal_id": "OTHER", "current_phase": "RED"})
        self.assertEqual(status, 400)

    def test_simulator_cannot_override_manual(self):
        call("POST", "/signals", VALID)  # data_source MANUAL
        status, body = call(
            "PUT", "/signals/YK-TEST-01", {"current_phase": "GREEN"}, {"if_source": "SIMULATOR"}
        )
        self.assertEqual(status, 409)
        self.assertEqual(body["error"]["details"]["data_source"], "MANUAL")

    def test_simulator_updates_its_own_signal(self):
        call("POST", "/signals", dict(VALID, data_source="SIMULATOR"))
        status, _ = call(
            "PUT", "/signals/YK-TEST-01", {"current_phase": "GREEN"}, {"if_source": "SIMULATOR"}
        )
        self.assertEqual(status, 200)

    # ---- delete
    def test_delete(self):
        call("POST", "/signals", VALID)
        self.assertEqual(call("DELETE", "/signals/YK-TEST-01")[0], 200)
        self.assertEqual(call("GET", "/signals/YK-TEST-01")[0], 404)
        self.assertEqual(call("DELETE", "/signals/YK-TEST-01")[0], 404)

    def test_invalid_signal_id_in_path(self):
        self.assertEqual(call("GET", "/signals/bad%20id")[0], 400)

    # ---- remaining time logic
    def test_remaining_seconds_never_negative(self):
        call("POST", "/signals", dict(VALID, remaining_seconds=0))
        _, body = call("GET", "/signals/YK-TEST-01")
        self.assertEqual(body["remaining_seconds"], 0)


if __name__ == "__main__":
    unittest.main()
