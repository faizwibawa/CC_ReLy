"""Integration-style tests of the DynamoDB repository against a mocked DynamoDB (moto).

Skipped automatically if boto3/moto are not installed:
    pip install -r backend/requirements-dev.txt
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

try:
    import boto3
    from moto import mock_aws
except ImportError:  # pragma: no cover
    boto3 = None

from repository import (  # noqa: E402
    AlreadyExists,
    DynamoSignalRepository,
    NotFound,
    SourceConflict,
)

TABLE = "ReLy-TrafficSignals"


@unittest.skipIf(boto3 is None, "boto3/moto not installed")
class DynamoRepositoryTests(unittest.TestCase):
    def setUp(self):
        os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
        os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
        os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
        self.mock = mock_aws()
        self.mock.start()
        boto3.client("dynamodb").create_table(
            TableName=TABLE,
            BillingMode="PAY_PER_REQUEST",
            AttributeDefinitions=[{"AttributeName": "signal_id", "AttributeType": "S"}],
            KeySchema=[{"AttributeName": "signal_id", "KeyType": "HASH"}],
        )
        self.repo = DynamoSignalRepository(TABLE)
        self.item = {
            "signal_id": "S1",
            "location": "Somewhere",
            "latitude": -7.78,
            "longitude": 110.36,
            "current_phase": "RED",
            "confidence_score": 0.85,
            "data_source": "SIMULATOR",
            "detour": {"label": "via side street", "lat": -7.7, "lng": 110.3},
        }

    def tearDown(self):
        self.mock.stop()

    def test_crud_round_trip(self):
        self.repo.create(self.item)
        with self.assertRaises(AlreadyExists):
            self.repo.create(self.item)

        got = self.repo.get("S1")
        self.assertEqual(got["latitude"], -7.78)        # Decimal converted back to float
        self.assertEqual(got["detour"]["lat"], -7.7)

        updated = self.repo.update("S1", {"current_phase": "GREEN"}, required_source="SIMULATOR")
        self.assertEqual(updated["current_phase"], "GREEN")

        self.repo.update("S1", {"data_source": "MANUAL"})
        with self.assertRaises(SourceConflict) as ctx:
            self.repo.update("S1", {"current_phase": "RED"}, required_source="SIMULATOR")
        self.assertEqual(ctx.exception.actual_source, "MANUAL")

        self.assertEqual(len(self.repo.list()), 1)
        self.repo.delete("S1")
        with self.assertRaises(NotFound):
            self.repo.get("S1")
        with self.assertRaises(NotFound):
            self.repo.delete("S1")
        with self.assertRaises(NotFound):
            self.repo.update("S1", {"current_phase": "RED"})


if __name__ == "__main__":
    unittest.main()
