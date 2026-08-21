from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


EXPECTED_BRONZE_SOURCE_COUNT = 10
EXPECTED_GLUE_TABLE_TYPE = "EXTERNAL_TABLE"


@dataclass(frozen=True)
class BronzeSource:
    unique_id: str
    source_name: str
    database_name: str
    table_name: str


@dataclass(frozen=True)
class BronzeSourceCheck:
    unique_id: str
    source_name: str
    database_name: str
    table_name: str
    status: str
    table_type: str | None
    location: str | None
    bucket: str | None
    prefix: str | None
    first_non_empty_object: str | None
    violation_code: str | None
    details: str | None


@dataclass(frozen=True)
class BronzeGateResult:
    status: str
    expected_count: int
    available_count: int
    blocked_count: int
    checks: tuple[BronzeSourceCheck, ...]

    def to_payload(self) -> dict[str, Any]:
        return asdict(self)


def load_bronze_sources(
    manifest_path: Path,
    *,
    expected_count: int = (
        EXPECTED_BRONZE_SOURCE_COUNT
    ),
) -> tuple[BronzeSource, ...]:
    manifest = json.loads(
        manifest_path.read_text(
            encoding="utf-8"
        )
    )

    manifest_sources = manifest.get(
        "sources",
        {},
    )

    sources: list[BronzeSource] = []

    for unique_id, node in sorted(
        manifest_sources.items()
    ):
        if (
            node.get("resource_type")
            not in {None, "source"}
        ):
            continue

        source_name = str(
            node.get("source_name")
            or ""
        ).strip()

        database_name = str(
            node.get("schema")
            or ""
        ).strip()

        table_name = str(
            node.get("identifier")
            or node.get("name")
            or ""
        ).strip()

        if not source_name:
            raise ValueError(
                f"Source {unique_id} has no "
                "source_name."
            )

        if not database_name:
            raise ValueError(
                f"Source {unique_id} has no "
                "Glue database/schema."
            )

        if not table_name:
            raise ValueError(
                f"Source {unique_id} has no "
                "table identifier."
            )

        sources.append(
            BronzeSource(
                unique_id=unique_id,
                source_name=source_name,
                database_name=database_name,
                table_name=table_name,
            )
        )

    if len(sources) != expected_count:
        raise ValueError(
            "Expected "
            f"{expected_count} Bronze sources, "
            f"found {len(sources)}."
        )

    identities = {
        (
            source.database_name,
            source.table_name,
        )
        for source in sources
    }

    if len(identities) != len(sources):
        raise ValueError(
            "Duplicate Bronze Glue table "
            "identities were found."
        )

    return tuple(sources)


def parse_s3_uri(
    location: str,
) -> tuple[str, str]:
    parsed = urlparse(location)

    if parsed.scheme != "s3":
        raise ValueError(
            f"Location is not an S3 URI: "
            f"{location}"
        )

    bucket = parsed.netloc.strip()
    prefix = parsed.path.lstrip("/")

    if not bucket:
        raise ValueError(
            f"S3 URI has no bucket: {location}"
        )

    return bucket, prefix


class BronzeAvailabilityChecker:
    def __init__(
        self,
        *,
        glue_client: Any,
        s3_client: Any,
        expected_bucket: str,
        expected_prefix: str = "bronze/",
    ) -> None:
        self.glue_client = glue_client
        self.s3_client = s3_client
        self.expected_bucket = (
            expected_bucket.strip()
        )
        self.expected_prefix = (
            expected_prefix
            .strip()
            .lstrip("/")
        )

        if not self.expected_bucket:
            raise ValueError(
                "Expected Bronze S3 bucket "
                "cannot be empty."
            )

    def _blocked_check(
        self,
        source: BronzeSource,
        *,
        violation_code: str,
        details: str,
        table_type: str | None = None,
        location: str | None = None,
        bucket: str | None = None,
        prefix: str | None = None,
    ) -> BronzeSourceCheck:
        return BronzeSourceCheck(
            unique_id=source.unique_id,
            source_name=source.source_name,
            database_name=(
                source.database_name
            ),
            table_name=source.table_name,
            status="BLOCKED",
            table_type=table_type,
            location=location,
            bucket=bucket,
            prefix=prefix,
            first_non_empty_object=None,
            violation_code=violation_code,
            details=details,
        )

    def check_source(
        self,
        source: BronzeSource,
    ) -> BronzeSourceCheck:
        try:
            response = (
                self.glue_client.get_table(
                    DatabaseName=(
                        source.database_name
                    ),
                    Name=source.table_name,
                )
            )
        except Exception as error:
            return self._blocked_check(
                source,
                violation_code=(
                    "GLUE_TABLE_UNAVAILABLE"
                ),
                details=(
                    f"{type(error).__name__}: "
                    f"{error}"
                ),
            )

        table = response.get(
            "Table",
            {},
        )

        table_type = table.get(
            "TableType"
        )

        if (
            table_type
            != EXPECTED_GLUE_TABLE_TYPE
        ):
            return self._blocked_check(
                source,
                violation_code=(
                    "UNEXPECTED_GLUE_TABLE_TYPE"
                ),
                details=(
                    "Expected table type "
                    f"{EXPECTED_GLUE_TABLE_TYPE}, "
                    f"found {table_type!r}."
                ),
                table_type=table_type,
            )

        storage_descriptor = table.get(
            "StorageDescriptor",
            {},
        )

        location = storage_descriptor.get(
            "Location"
        )

        if not location:
            return self._blocked_check(
                source,
                violation_code=(
                    "MISSING_S3_LOCATION"
                ),
                details=(
                    "Glue table has no "
                    "StorageDescriptor.Location."
                ),
                table_type=table_type,
            )

        try:
            bucket, prefix = parse_s3_uri(
                str(location)
            )
        except ValueError as error:
            return self._blocked_check(
                source,
                violation_code=(
                    "INVALID_S3_LOCATION"
                ),
                details=str(error),
                table_type=table_type,
                location=str(location),
            )

        if bucket != self.expected_bucket:
            return self._blocked_check(
                source,
                violation_code=(
                    "UNEXPECTED_S3_BUCKET"
                ),
                details=(
                    f"Expected bucket "
                    f"{self.expected_bucket}, "
                    f"found {bucket}."
                ),
                table_type=table_type,
                location=str(location),
                bucket=bucket,
                prefix=prefix,
            )

        if (
            self.expected_prefix
            and not prefix.startswith(
                self.expected_prefix
            )
        ):
            return self._blocked_check(
                source,
                violation_code=(
                    "UNEXPECTED_S3_PREFIX"
                ),
                details=(
                    f"Expected prefix beginning "
                    f"with {self.expected_prefix}, "
                    f"found {prefix}."
                ),
                table_type=table_type,
                location=str(location),
                bucket=bucket,
                prefix=prefix,
            )

        try:
            paginator = (
                self.s3_client.get_paginator(
                    "list_objects_v2"
                )
            )

            first_non_empty_object = None

            for page in paginator.paginate(
                Bucket=bucket,
                Prefix=prefix,
            ):
                for item in page.get(
                    "Contents",
                    [],
                ):
                    if int(
                        item.get("Size", 0)
                    ) > 0:
                        first_non_empty_object = (
                            str(item["Key"])
                        )
                        break

                if first_non_empty_object:
                    break
        except Exception as error:
            return self._blocked_check(
                source,
                violation_code=(
                    "S3_LIST_FAILED"
                ),
                details=(
                    f"{type(error).__name__}: "
                    f"{error}"
                ),
                table_type=table_type,
                location=str(location),
                bucket=bucket,
                prefix=prefix,
            )

        if not first_non_empty_object:
            return self._blocked_check(
                source,
                violation_code=(
                    "EMPTY_S3_LOCATION"
                ),
                details=(
                    "No non-empty object was "
                    "found under the Glue table "
                    "location."
                ),
                table_type=table_type,
                location=str(location),
                bucket=bucket,
                prefix=prefix,
            )

        return BronzeSourceCheck(
            unique_id=source.unique_id,
            source_name=source.source_name,
            database_name=(
                source.database_name
            ),
            table_name=source.table_name,
            status="PASS",
            table_type=table_type,
            location=str(location),
            bucket=bucket,
            prefix=prefix,
            first_non_empty_object=(
                first_non_empty_object
            ),
            violation_code=None,
            details=None,
        )

    def check_all(
        self,
        sources: tuple[BronzeSource, ...],
    ) -> BronzeGateResult:
        checks = tuple(
            self.check_source(source)
            for source in sources
        )

        available_count = sum(
            check.status == "PASS"
            for check in checks
        )

        blocked_count = (
            len(checks)
            - available_count
        )

        return BronzeGateResult(
            status=(
                "PASS"
                if blocked_count == 0
                else "BLOCKED"
            ),
            expected_count=len(sources),
            available_count=available_count,
            blocked_count=blocked_count,
            checks=checks,
        )
