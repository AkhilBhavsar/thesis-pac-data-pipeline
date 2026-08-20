import json
import unittest
from datetime import datetime, timezone
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
QuarantinePersistenceError = (
    quarantine_runtime.QuarantinePersistenceError
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


class FakeS3NotFound(Exception):

    def __init__(self):
        super().__init__("not found")
        self.response = {
            "Error": {
                "Code": "NoSuchKey",
            },
            "ResponseMetadata": {
                "HTTPStatusCode": 404,
            },
        }


class FakeS3:

    def __init__(
        self,
        *,
        include_source=True,
        calls=None,
    ):
        self.calls = (
            calls
            if calls is not None
            else []
        )
        self.fail_source_delete_once = False
        self.fail_target_delete = False
        self.version_counter = 0
        self.objects = {}

        if include_source:
            self.objects[
                (
                    "bucket",
                    "experiments/c2/run/"
                    "rejected.parquet",
                )
            ] = {
                "ContentLength": 8,
                "ETag": '"abc"',
                "ContentType": (
                    "application/octet-stream"
                ),
                "Metadata": {
                    "fixture": "synthetic",
                },
                "LastModified": datetime(
                    2026,
                    8,
                    20,
                    1,
                    0,
                    tzinfo=timezone.utc,
                ),
                "VersionId": "source-v1",
            }

    def head_object(
        self,
        *,
        Bucket,
        Key,
    ):
        self.calls.append(
            f"s3:head:{Key}"
        )

        try:
            return dict(
                self.objects[
                    (
                        Bucket,
                        Key,
                    )
                ]
            )
        except KeyError as error:
            raise FakeS3NotFound() from error

    def copy_object(
        self,
        *,
        Bucket,
        Key,
        CopySource,
        MetadataDirective=None,
        Metadata=None,
        **kwargs,
    ):
        self.calls.append(
            f"s3:copy:{Key}"
        )

        source = (
            CopySource["Bucket"],
            CopySource["Key"],
        )

        self.version_counter += 1

        copied = dict(
            self.objects[source]
        )

        copied.update(kwargs)
        copied["Metadata"] = dict(
            Metadata or {}
        )
        copied["LastModified"] = datetime(
            2026,
            8,
            20,
            1,
            self.version_counter,
            tzinfo=timezone.utc,
        )
        copied["VersionId"] = (
            f"target-v{self.version_counter}"
        )

        self.objects[
            (
                Bucket,
                Key,
            )
        ] = copied

        return {}

    def delete_object(
        self,
        *,
        Bucket,
        Key,
    ):
        self.calls.append(
            f"s3:delete:{Key}"
        )

        is_source = Key.startswith(
            "experiments/c2/"
        )

        if (
            is_source
            and self.fail_source_delete_once
        ):
            self.fail_source_delete_once = False
            raise RuntimeError(
                "injected source delete failure"
            )

        if (
            not is_source
            and self.fail_target_delete
        ):
            raise RuntimeError(
                "injected target delete failure"
            )

        self.objects.pop(
            (
                Bucket,
                Key,
            ),
            None,
        )

        return {}


class FakeAthena:

    def __init__(
        self,
        *,
        states=None,
        settled_state=None,
        calls=None,
    ):
        self.query = None
        self.states = list(
            states or ["SUCCEEDED"]
        )
        self.settled_state = settled_state
        self.calls = (
            calls
            if calls is not None
            else []
        )
        self.stopped = False
        self.queries_by_token = {}
        self.created_query_count = 0

    def start_query_execution(
        self,
        **kwargs,
    ):
        self.query = kwargs

        self.calls.append(
            "athena:start"
        )

        token = kwargs[
            "ClientRequestToken"
        ]

        if token not in self.queries_by_token:
            self.created_query_count += 1
            self.queries_by_token[token] = (
                f"query-{self.created_query_count}"
            )

        return {
            "QueryExecutionId": (
                self.queries_by_token[token]
            )
        }

    def get_query_execution(
        self,
        *,
        QueryExecutionId,
    ):
        self.calls.append(
            "athena:get"
        )

        if self.stopped and (
            self.settled_state is not None
        ):
            state = self.settled_state
        elif len(self.states) > 1:
            state = self.states.pop(0)
        else:
            state = self.states[0]

        return {
            "QueryExecution": {
                "Status": {
                    "State": state,
                    "StateChangeReason": (
                        "injected test state"
                    ),
                }
            }
        }

    def stop_query_execution(
        self,
        *,
        QueryExecutionId,
    ):
        self.calls.append(
            "athena:stop"
        )
        self.stopped = True
        return {}


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

    def test_runtime_records_event_before_source_removal(self):
        calls = []
        s3 = FakeS3(calls=calls)
        athena = FakeAthena(calls=calls)

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

        self.assertEqual(
            len(
                athena.query[
                    "ClientRequestToken"
                ]
            ),
            64,
        )

        self.assertLess(
            calls.index("athena:start"),
            calls.index(
                "s3:delete:experiments/c2/run/"
                "rejected.parquet"
            ),
        )

        self.validator.validate(
            result[
                "quarantine_event"
            ]
        )

    def test_athena_failed_and_cancelled_compensate_copy(self):
        for state in (
            "FAILED",
            "CANCELLED",
        ):
            with self.subTest(state=state):
                s3 = FakeS3()
                athena = FakeAthena(
                    states=[state]
                )

                with self.assertRaises(
                    QuarantinePersistenceError
                ):
                    run_quarantine(
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

                self.assertIn(
                    (
                        "bucket",
                        "experiments/c2/run/"
                        "rejected.parquet",
                    ),
                    s3.objects,
                )

                self.assertNotIn(
                    (
                        "bucket",
                        "quarantine/objects/"
                        "quality_regression/"
                        "c2-run-001/"
                        "rejected.parquet",
                    ),
                    s3.objects,
                )

    def test_athena_timeout_preserves_ambiguous_copy_and_source(self):
        s3 = FakeS3()
        athena = FakeAthena(
            states=["RUNNING"],
            settled_state="RUNNING",
        )

        with self.assertRaisesRegex(
            QuarantinePersistenceError,
            "timed out with final state RUNNING",
        ):
            run_quarantine(
                payload=self.payload(),
                s3_client=s3,
                athena_client=athena,
                data_bucket="bucket",
                database_name=(
                    "thesis_pac_dev_quarantine"
                ),
                table_name="quarantine_events",
                workgroup="workgroup",
                quarantined_at=(
                    "2026-08-20T01:01:00Z"
                ),
                athena_timeout_seconds=0.0,
            )

        self.assertTrue(athena.stopped)

        self.assertIn(
            (
                "bucket",
                "experiments/c2/run/"
                "rejected.parquet",
            ),
            s3.objects,
        )

        self.assertIn(
            (
                "bucket",
                "quarantine/objects/"
                "quality_regression/"
                "c2-run-001/"
                "rejected.parquet",
            ),
            s3.objects,
        )

    def test_missing_source_without_owned_destination_fails_closed(self):
        s3 = FakeS3(
            include_source=False
        )

        with self.assertRaisesRegex(
            QuarantineRuntimeError,
            "source object does not exist",
        ):
            run_quarantine(
                payload=self.payload(),
                s3_client=s3,
                athena_client=FakeAthena(),
                data_bucket="bucket",
                database_name=(
                    "thesis_pac_dev_quarantine"
                ),
                table_name="quarantine_events",
                workgroup="workgroup",
            )

    def test_unowned_preexisting_destination_is_never_overwritten(self):
        s3 = FakeS3()
        target = (
            "bucket",
            "quarantine/objects/"
            "quality_regression/"
            "c2-run-001/"
            "rejected.parquet",
        )

        s3.objects[target] = {
            "ContentLength": 8,
            "ETag": '"abc"',
            "Metadata": {},
            "LastModified": datetime(
                2026,
                8,
                20,
                1,
                1,
                tzinfo=timezone.utc,
            ),
            "VersionId": "foreign-v1",
        }

        before = dict(s3.objects[target])

        with self.assertRaisesRegex(
            QuarantineRuntimeError,
            "without matching C2 ownership",
        ):
            run_quarantine(
                payload=self.payload(),
                s3_client=s3,
                athena_client=FakeAthena(),
                data_bucket="bucket",
                database_name=(
                    "thesis_pac_dev_quarantine"
                ),
                table_name="quarantine_events",
                workgroup="workgroup",
            )

        self.assertEqual(
            s3.objects[target],
            before,
        )

    def test_duplicate_invocation_reuses_copy_and_athena_query(self):
        s3 = FakeS3()
        athena = FakeAthena()

        first = run_quarantine(
            payload=self.payload(),
            s3_client=s3,
            athena_client=athena,
            data_bucket="bucket",
            database_name=(
                "thesis_pac_dev_quarantine"
            ),
            table_name="quarantine_events",
            workgroup="workgroup",
        )

        second = run_quarantine(
            payload=self.payload(),
            s3_client=s3,
            athena_client=athena,
            data_bucket="bucket",
            database_name=(
                "thesis_pac_dev_quarantine"
            ),
            table_name="quarantine_events",
            workgroup="workgroup",
        )

        self.assertEqual(
            athena.created_query_count,
            1,
        )

        self.assertEqual(
            first[
                "athena_query_execution_id"
            ],
            second[
                "athena_query_execution_id"
            ],
        )

        self.assertTrue(
            second[
                "quarantine_object"
            ][
                "idempotent_replay"
            ]
        )

    def test_source_delete_failure_can_resume_without_duplicate_event(self):
        s3 = FakeS3()
        s3.fail_source_delete_once = True
        athena = FakeAthena()

        with self.assertRaisesRegex(
            QuarantineRuntimeError,
            "source removal failed",
        ):
            run_quarantine(
                payload=self.payload(),
                s3_client=s3,
                athena_client=athena,
                data_bucket="bucket",
                database_name=(
                    "thesis_pac_dev_quarantine"
                ),
                table_name="quarantine_events",
                workgroup="workgroup",
            )

        result = run_quarantine(
            payload=self.payload(),
            s3_client=s3,
            athena_client=athena,
            data_bucket="bucket",
            database_name=(
                "thesis_pac_dev_quarantine"
            ),
            table_name="quarantine_events",
            workgroup="workgroup",
        )

        self.assertEqual(
            athena.created_query_count,
            1,
        )

        self.assertFalse(
            result[
                "quarantine_object"
            ][
                "idempotent_replay"
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

    def test_compensation_failure_preserves_source_and_copy(self):
        s3 = FakeS3()
        s3.fail_target_delete = True

        with self.assertRaisesRegex(
            QuarantineRuntimeError,
            "compensation failed",
        ):
            run_quarantine(
                payload=self.payload(),
                s3_client=s3,
                athena_client=FakeAthena(
                    states=["FAILED"]
                ),
                data_bucket="bucket",
                database_name=(
                    "thesis_pac_dev_quarantine"
                ),
                table_name="quarantine_events",
                workgroup="workgroup",
            )

        self.assertIn(
            (
                "bucket",
                "experiments/c2/run/"
                "rejected.parquet",
            ),
            s3.objects,
        )

        self.assertIn(
            (
                "bucket",
                "quarantine/objects/"
                "quality_regression/"
                "c2-run-001/"
                "rejected.parquet",
            ),
            s3.objects,
        )


if __name__ == "__main__":
    unittest.main()
