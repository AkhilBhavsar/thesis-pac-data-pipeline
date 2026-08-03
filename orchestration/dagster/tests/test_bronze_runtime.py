from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import (
    Mock,
    call,
    patch,
)

import dagster as dg

from thesis_orchestration.bronze_runtime import (
    BronzeGateResource,
    run_bronze_guarded_dbt,
)


EXPECTED_BUCKET = "test-data-bucket"


class FakeGlueClient:
    def __init__(
        self,
        tables: dict[
            tuple[str, str],
            str,
        ],
    ) -> None:
        self.tables = tables

    def get_table(
        self,
        *,
        DatabaseName: str,
        Name: str,
    ) -> dict:
        identity = (
            DatabaseName,
            Name,
        )

        if identity not in self.tables:
            raise RuntimeError(
                f"Missing Glue table: "
                f"{DatabaseName}.{Name}"
            )

        return {
            "Table": {
                "Name": Name,
                "TableType": (
                    "EXTERNAL_TABLE"
                ),
                "StorageDescriptor": {
                    "Location": (
                        self.tables[identity]
                    )
                },
            }
        }


class FakePaginator:
    def __init__(
        self,
        objects: dict[
            tuple[str, str],
            list[dict],
        ],
    ) -> None:
        self.objects = objects

    def paginate(
        self,
        *,
        Bucket: str,
        Prefix: str,
    ):
        yield {
            "Contents": self.objects.get(
                (Bucket, Prefix),
                [],
            )
        }


class FakeS3Client:
    def __init__(
        self,
        objects: dict[
            tuple[str, str],
            list[dict],
        ],
    ) -> None:
        self.objects = objects

    def get_paginator(
        self,
        operation_name: str,
    ) -> FakePaginator:
        if (
            operation_name
            != "list_objects_v2"
        ):
            raise ValueError(
                operation_name
            )

        return FakePaginator(
            self.objects
        )


class FakeLog:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def info(
        self,
        message: str,
    ) -> None:
        self.messages.append(
            message
        )


class FakeContext:
    def __init__(
        self,
        run_id: str,
    ) -> None:
        self.run_id = run_id
        self.log = FakeLog()


class FakeDbtInvocation:
    def stream(self):
        yield {
            "event": "dbt-build"
        }


class FakeDbt:
    def __init__(self) -> None:
        self.calls: list[
            tuple[tuple[str, ...], object]
        ] = []

    def cli(
        self,
        arguments,
        *,
        context,
    ) -> FakeDbtInvocation:
        self.calls.append(
            (
                tuple(arguments),
                context,
            )
        )

        return FakeDbtInvocation()


class BronzeRuntimeIntegrationTest(
    unittest.TestCase
):
    def setUp(self) -> None:
        self.temporary_directory = (
            tempfile.TemporaryDirectory()
        )

        self.addCleanup(
            self.temporary_directory.cleanup
        )

        self.root = Path(
            self.temporary_directory.name
        )

        self.manifest_path = (
            self.root
            / "manifest.json"
        )

        manifest_sources = {}

        for index in range(10):
            table_name = (
                f"bronze_table_{index}"
            )

            unique_id = (
                "source.thesis_pac."
                f"{table_name}"
            )

            manifest_sources[unique_id] = {
                "resource_type": "source",
                "source_name": "bronze",
                "schema": (
                    "thesis_pac_dev_bronze"
                ),
                "name": table_name,
                "identifier": table_name,
            }

        self.manifest_path.write_text(
            json.dumps(
                {
                    "sources": (
                        manifest_sources
                    )
                }
            ),
            encoding="utf-8",
        )

        self.evidence_root = (
            self.root
            / "evidence"
        )

        self.resource = (
            BronzeGateResource(
                region_name="eu-west-1",
                expected_bucket=(
                    EXPECTED_BUCKET
                ),
                expected_prefix="bronze/",
            )
        )

    def _clients(
        self,
        *,
        remove_first_table: bool = False,
    ):
        tables = {}
        objects = {}

        for index in range(10):
            table_name = (
                f"bronze_table_{index}"
            )

            database_name = (
                "thesis_pac_dev_bronze"
            )

            prefix = (
                f"bronze/{table_name}/"
            )

            tables[
                (
                    database_name,
                    table_name,
                )
            ] = (
                f"s3://{EXPECTED_BUCKET}/"
                f"{prefix}"
            )

            objects[
                (
                    EXPECTED_BUCKET,
                    prefix,
                )
            ] = [
                {
                    "Key": (
                        f"{prefix}"
                        "data.parquet"
                    ),
                    "Size": 256,
                }
            ]

        if remove_first_table:
            del tables[
                (
                    "thesis_pac_dev_bronze",
                    "bronze_table_0",
                )
            ]

        return (
            FakeGlueClient(tables),
            FakeS3Client(objects),
        )

    def _environment(
        self,
    ) -> dict[str, str]:
        return {
            (
                "THESIS_DAGSTER_"
                "EVIDENCE_ROOT"
            ): str(self.evidence_root),
            (
                "THESIS_EXPERIMENT_"
                "CONDITION"
            ): "C0",
            "THESIS_SCENARIO_ID": (
                "baseline"
            ),
            "THESIS_GIT_COMMIT": (
                "test-commit"
            ),
            "THESIS_GIT_BRANCH": (
                "feature/test"
            ),
        }

    def test_pass_runs_dbt_after_gate(
        self,
    ) -> None:
        glue, s3 = self._clients()

        context = FakeContext(
            "run-pass"
        )

        dbt = FakeDbt()

        with patch.dict(
            os.environ,
            self._environment(),
            clear=False,
        ), patch.object(
            BronzeGateResource,
            "_create_clients",
            return_value=(
                glue,
                s3,
            ),
        ):
            events = list(
                run_bronze_guarded_dbt(
                    context=context,
                    dbt=dbt,
                    bronze_gate=(
                        self.resource
                    ),
                    manifest_path=(
                        self.manifest_path
                    ),
                )
            )

        self.assertEqual(
            len(events),
            1,
        )

        self.assertEqual(
            dbt.calls[0][0],
            ("build",),
        )

        evidence_files = list(
            self.evidence_root.rglob(
                "*.json"
            )
        )

        self.assertEqual(
            len(evidence_files),
            1,
        )

        document = json.loads(
            evidence_files[0].read_text(
                encoding="utf-8"
            )
        )

        self.assertEqual(
            document["status"],
            "PASS",
        )

        self.assertEqual(
            document["payload"][
                "available_count"
            ],
            10,
        )

    def test_blocked_gate_prevents_dbt(
        self,
    ) -> None:
        glue, s3 = self._clients(
            remove_first_table=True
        )

        context = FakeContext(
            "run-blocked"
        )

        dbt = FakeDbt()

        with patch.dict(
            os.environ,
            self._environment(),
            clear=False,
        ), patch.object(
            BronzeGateResource,
            "_create_clients",
            return_value=(
                glue,
                s3,
            ),
        ):
            with self.assertRaises(
                dg.Failure
            ):
                list(
                    run_bronze_guarded_dbt(
                        context=context,
                        dbt=dbt,
                        bronze_gate=(
                            self.resource
                        ),
                        manifest_path=(
                            self.manifest_path
                        ),
                    )
                )

        self.assertEqual(
            dbt.calls,
            [],
        )

        evidence_files = list(
            self.evidence_root.rglob(
                "*.json"
            )
        )

        self.assertEqual(
            len(evidence_files),
            1,
        )

        document = json.loads(
            evidence_files[0].read_text(
                encoding="utf-8"
            )
        )

        self.assertEqual(
            document["status"],
            "BLOCKED",
        )

        self.assertEqual(
            document["payload"][
                "blocked_count"
            ],
            1,
        )

    def test_partial_client_injection_rejected(
        self,
    ) -> None:
        with self.assertRaises(
            ValueError
        ):
            self.resource.evaluate(
                manifest_path=(
                    self.manifest_path
                ),
                glue_client=object(),
            )

    def test_client_factory_uses_region(
        self,
    ) -> None:
        session = Mock()

        glue_client = object()
        s3_client = object()

        session.client.side_effect = [
            glue_client,
            s3_client,
        ]

        with patch(
            (
                "thesis_orchestration."
                "bronze_runtime.boto3."
                "session.Session"
            ),
            return_value=session,
        ) as session_factory:
            actual_glue, actual_s3 = (
                self.resource
                ._create_clients()
            )

        session_factory.assert_called_once_with(
            region_name="eu-west-1"
        )

        session.client.assert_has_calls(
            [
                call("glue"),
                call("s3"),
            ]
        )

        self.assertIs(
            actual_glue,
            glue_client,
        )

        self.assertIs(
            actual_s3,
            s3_client,
        )


if __name__ == "__main__":
    unittest.main()
