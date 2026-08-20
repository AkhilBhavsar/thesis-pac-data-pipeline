import json
import unittest
from pathlib import Path

from jsonschema import (
    Draft202012Validator,
    FormatChecker,
)

import importlib

quarantine_runtime = importlib.import_module(
    "runtime.lambda.quarantine.lambda_handler"
)

QuarantineRuntimeError = (
    quarantine_runtime.QuarantineRuntimeError
)
build_event = quarantine_runtime.build_event
build_insert_sql = quarantine_runtime.build_insert_sql
destination_key = quarantine_runtime.destination_key
run_quarantine = quarantine_runtime.run_quarantine
validate_request = quarantine_runtime.validate_request


ROOT = Path(__file__).resolve().parents[2]

SCHEMA_PATH = (
    ROOT
    / "policies/contracts/"
    "c2-quarantine-event.schema.json"
)


class FakeS3:

    def __init__(self):
        self.objects = {
            (
                "bucket",
                "experiments/c2/run/"
                "rejected.parquet",
            ): {
                "ContentLength": 8,
                "ETag": '"abc"',
            }
        }

    def head_object(
        self,
        *,
        Bucket,
        Key,
    ):
        return dict(
            self.objects[
                (
                    Bucket,
                    Key,
                )
            ]
        )

    def copy_object(
        self,
        *,
        Bucket,
        Key,
        CopySource,
    ):
        source = (
            CopySource["Bucket"],
            CopySource["Key"],
        )

        self.objects[
            (
                Bucket,
                Key,
            )
        ] = dict(
            self.objects[source]
        )

        return {}

    def delete_object(
        self,
        *,
        Bucket,
        Key,
    ):
        del self.objects[
            (
                Bucket,
                Key,
            )
        ]

        return {}


class FakeAthena:

    def __init__(self):
        self.query = None

    def start_query_execution(
        self,
        **kwargs,
    ):
        self.query = kwargs

        return {
            "QueryExecutionId": (
                "query-123"
            )
        }

    def get_query_execution(
        self,
        *,
        QueryExecutionId,
    ):
        return {
            "QueryExecution": {
                "Status": {
                    "State": (
                        "SUCCEEDED"
                    )
                }
            }
        }


class C2QuarantineRuntimeTest(
    unittest.TestCase
):

    @classmethod
    def setUpClass(cls):
        cls.schema = json.loads(
            SCHEMA_PATH.read_text(
                encoding="utf-8"
            )
        )

        Draft202012Validator.check_schema(
            cls.schema
        )

        cls.validator = (
            Draft202012Validator(
                cls.schema,
                format_checker=(
                    FormatChecker()
                ),
            )
        )

    def payload(self):
        return {
            "condition": "C2",
            "run_id": "c2-run-001",
            "scenario_id": (
                "quality_regression"
            ),
            "source_bucket": "bucket",
            "source_key": (
                "experiments/c2/run/"
                "rejected.parquet"
            ),
            "source_dataset": (
                "gold_financial"
            ),
            "source_relation": (
                "gold_internal."
                "gold_financial"
            ),
            "policy_category": (
                "quality"
            ),
            "policy_id": (
                "PAC-QUALITY-001"
            ),
            "violation_code": (
                "GOLD_TEST_FAILED"
            ),
            "violation_details": (
                "Governed Gold validation "
                "failed."
            ),
            "data_classification": (
                "internal"
            ),
            "detected_at": (
                "2026-08-20T01:00:00Z"
            ),
            "retry_count": 1,
            "max_retries": 1,
            "evidence_uri": (
                "s3://bucket/evidence/"
                "c2-run-001/"
            ),
        }

    def test_event_matches_contract(self):
        payload = self.payload()

        event = build_event(
            payload=payload,
            destination_uri=(
                "s3://bucket/quarantine/"
                "objects/quality_regression/"
                "c2-run-001/"
                "rejected.parquet"
            ),
            quarantined_at=(
                "2026-08-20T01:01:00Z"
            ),
        )

        self.validator.validate(
            event
        )

        self.assertEqual(
            len(event),
            23,
        )

    def test_rejects_c1_condition(self):
        payload = self.payload()
        payload["condition"] = "C1"

        with self.assertRaises(
            QuarantineRuntimeError
        ):
            validate_request(
                payload,
                data_bucket="bucket",
            )

    def test_rejects_canonical_source(self):
        payload = self.payload()

        payload["source_key"] = (
            "gold/internal/"
            "canonical.parquet"
        )

        with self.assertRaises(
            QuarantineRuntimeError
        ):
            validate_request(
                payload,
                data_bucket="bucket",
            )

    def test_rejects_false_positive(self):
        payload = self.payload()

        payload["scenario_id"] = (
            "policy_false_positive"
        )

        with self.assertRaises(
            QuarantineRuntimeError
        ):
            validate_request(
                payload,
                data_bucket="bucket",
            )

    def test_destination_is_quarantine_only(self):
        key = destination_key(
            self.payload()
        )

        self.assertTrue(
            key.startswith(
                "quarantine/objects/"
            )
        )

        self.assertNotIn(
            "experiments/c2/",
            key,
        )

    def test_sql_escapes_violation_details(self):
        payload = self.payload()

        payload[
            "violation_details"
        ] = "customer's output"

        event = build_event(
            payload=payload,
            destination_uri=(
                "s3://bucket/quarantine/"
                "objects/quality_regression/"
                "c2-run-001/"
                "rejected.parquet"
            ),
            quarantined_at=(
                "2026-08-20T01:01:00Z"
            ),
        )

        sql = build_insert_sql(
            event=event,
            database_name=(
                "thesis_pac_dev_quarantine"
            ),
            table_name=(
                "quarantine_events"
            ),
        )

        self.assertIn(
            "customer''s output",
            sql,
        )

        self.assertIn(
            "CAST(NULL AS TIMESTAMP)",
            sql,
        )

    def test_runtime_moves_then_records_event(self):
        s3 = FakeS3()
        athena = FakeAthena()

        result = run_quarantine(
            payload=self.payload(),
            s3_client=s3,
            athena_client=athena,
            data_bucket="bucket",
            database_name=(
                "thesis_pac_dev_quarantine"
            ),
            table_name=(
                "quarantine_events"
            ),
            workgroup="workgroup",
            quarantined_at=(
                "2026-08-20T01:01:00Z"
            ),
        )

        self.assertEqual(
            result["status"],
            "PASS",
        )

        self.assertEqual(
            result[
                "terminal_state"
            ],
            "QUARANTINED",
        )

        self.assertFalse(
            result[
                "self_healing_performed"
            ]
        )

        self.assertTrue(
            result[
                "promotion_blocked"
            ]
        )

        self.assertNotIn(
            (
                "bucket",
                "experiments/c2/run/"
                "rejected.parquet",
            ),
            s3.objects,
        )

        destination = result[
            "quarantine_object"
        ][
            "uri"
        ]

        self.assertTrue(
            destination.startswith(
                "s3://bucket/"
                "quarantine/objects/"
            )
        )

        self.assertIsNotNone(
            athena.query
        )

        self.validator.validate(
            result[
                "quarantine_event"
            ]
        )


if __name__ == "__main__":
    unittest.main()
