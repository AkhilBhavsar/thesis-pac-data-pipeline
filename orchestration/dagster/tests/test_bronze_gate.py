from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from thesis_orchestration.bronze_gate import (
    BronzeAvailabilityChecker,
    load_bronze_sources,
    parse_s3_uri,
)


EXPECTED_BUCKET = "expected-data-bucket"


class FakeGlueClient:
    def __init__(
        self,
        tables: dict[
            tuple[str, str],
            str | None,
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
                f"Glue table not found: "
                f"{DatabaseName}.{Name}"
            )

        location = self.tables[
            identity
        ]

        descriptor = {}

        if location is not None:
            descriptor["Location"] = (
                location
            )

        return {
            "Table": {
                "Name": Name,
                "TableType": (
                    "EXTERNAL_TABLE"
                ),
                "StorageDescriptor": (
                    descriptor
                ),
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


class BronzeCheckerTest(
    unittest.TestCase
):
    def setUp(self) -> None:
        self.temporary_directory = (
            tempfile.TemporaryDirectory()
        )

        self.addCleanup(
            self.temporary_directory.cleanup
        )

        self.manifest_path = (
            Path(
                self.temporary_directory.name
            )
            / "manifest.json"
        )

        sources = {}

        for index in range(10):
            table_name = (
                f"bronze_table_{index}"
            )

            unique_id = (
                "source.thesis_pac."
                f"{table_name}"
            )

            sources[unique_id] = {
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
                    "sources": sources,
                }
            ),
            encoding="utf-8",
        )

        self.sources = (
            load_bronze_sources(
                self.manifest_path
            )
        )

    def _passing_clients(self):
        tables = {}
        objects = {}

        for source in self.sources:
            prefix = (
                "bronze/"
                f"{source.table_name}/"
            )

            location = (
                f"s3://{EXPECTED_BUCKET}/"
                f"{prefix}"
            )

            tables[
                (
                    source.database_name,
                    source.table_name,
                )
            ] = location

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
                    "Size": 128,
                }
            ]

        return (
            FakeGlueClient(tables),
            FakeS3Client(objects),
        )

    def _checker(
        self,
        glue_client,
        s3_client,
    ) -> BronzeAvailabilityChecker:
        return BronzeAvailabilityChecker(
            glue_client=glue_client,
            s3_client=s3_client,
            expected_bucket=(
                EXPECTED_BUCKET
            ),
            expected_prefix="bronze/",
        )

    def test_load_manifest_sources(
        self,
    ) -> None:
        self.assertEqual(
            len(self.sources),
            10,
        )

        self.assertEqual(
            len(
                {
                    (
                        source.database_name,
                        source.table_name,
                    )
                    for source
                    in self.sources
                }
            ),
            10,
        )

    def test_manifest_count_mismatch(
        self,
    ) -> None:
        with self.assertRaises(
            ValueError
        ):
            load_bronze_sources(
                self.manifest_path,
                expected_count=9,
            )

    def test_parse_s3_uri(
        self,
    ) -> None:
        bucket, prefix = parse_s3_uri(
            "s3://example/bronze/orders/"
        )

        self.assertEqual(
            bucket,
            "example",
        )

        self.assertEqual(
            prefix,
            "bronze/orders/",
        )

        with self.assertRaises(
            ValueError
        ):
            parse_s3_uri(
                "https://example/bronze/"
            )

    def test_all_sources_pass(
        self,
    ) -> None:
        glue, s3 = (
            self._passing_clients()
        )

        result = self._checker(
            glue,
            s3,
        ).check_all(self.sources)

        self.assertEqual(
            result.status,
            "PASS",
        )

        self.assertEqual(
            result.available_count,
            10,
        )

        self.assertEqual(
            result.blocked_count,
            0,
        )

    def test_missing_glue_table_blocks(
        self,
    ) -> None:
        glue, s3 = (
            self._passing_clients()
        )

        missing = self.sources[0]

        del glue.tables[
            (
                missing.database_name,
                missing.table_name,
            )
        ]

        result = self._checker(
            glue,
            s3,
        ).check_all(self.sources)

        self.assertEqual(
            result.status,
            "BLOCKED",
        )

        self.assertEqual(
            result.blocked_count,
            1,
        )

        self.assertEqual(
            result.checks[0].violation_code,
            "GLUE_TABLE_UNAVAILABLE",
        )

    def test_missing_location_blocks(
        self,
    ) -> None:
        glue, s3 = (
            self._passing_clients()
        )

        source = self.sources[0]

        glue.tables[
            (
                source.database_name,
                source.table_name,
            )
        ] = None

        result = self._checker(
            glue,
            s3,
        ).check_all(self.sources)

        self.assertEqual(
            result.status,
            "BLOCKED",
        )

        self.assertEqual(
            result.checks[0].violation_code,
            "MISSING_S3_LOCATION",
        )

    def test_wrong_bucket_blocks(
        self,
    ) -> None:
        glue, s3 = (
            self._passing_clients()
        )

        source = self.sources[0]

        glue.tables[
            (
                source.database_name,
                source.table_name,
            )
        ] = (
            "s3://wrong-bucket/"
            f"bronze/{source.table_name}/"
        )

        result = self._checker(
            glue,
            s3,
        ).check_all(self.sources)

        self.assertEqual(
            result.status,
            "BLOCKED",
        )

        self.assertEqual(
            result.checks[0].violation_code,
            "UNEXPECTED_S3_BUCKET",
        )

    def test_empty_s3_prefix_blocks(
        self,
    ) -> None:
        glue, s3 = (
            self._passing_clients()
        )

        source = self.sources[0]

        prefix = (
            "bronze/"
            f"{source.table_name}/"
        )

        s3.objects[
            (
                EXPECTED_BUCKET,
                prefix,
            )
        ] = []

        result = self._checker(
            glue,
            s3,
        ).check_all(self.sources)

        self.assertEqual(
            result.status,
            "BLOCKED",
        )

        self.assertEqual(
            result.checks[0].violation_code,
            "EMPTY_S3_LOCATION",
        )


if __name__ == "__main__":
    unittest.main()
