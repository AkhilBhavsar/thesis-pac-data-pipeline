#!/usr/bin/env python3
"""Build deterministic synthetic customer-contact Bronze data."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any, Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[2]

SOURCE_MANIFEST_PATH = (
    PROJECT_ROOT
    / "manifests"
    / "bronze"
    / "olist"
    / "source-manifest.json"
)

SOURCE_CUSTOMERS_PATH = (
    PROJECT_ROOT
    / "data"
    / "bronze"
    / "raw"
    / "olist"
    / "olist_customers_dataset.csv"
)

EXPECTED_SOURCE_MANIFEST_SHA256 = (
    "0666ef2ad51bc52f9a2d5285c624154e"
    "84d7d290d3663b453f6d93f56c0ddbec"
)

EXPECTED_SOURCE_SNAPSHOT_ID = (
    "43cc5e9c8436f7919491dd90872d6f4d"
    "94d61d4694c1d4307e41456e405052d2"
)

EXPECTED_CUSTOMERS_SHA256 = (
    "983a422239e1712ded753b3bf9ecf47dc"
    "73f144d306029dcfa99e70a226883d2"
)

EXPECTED_CUSTOMERS_SIZE_BYTES = 9_033_957
EXPECTED_CUSTOMER_ROWS = 99_441

EXPECTED_SOURCE_COLUMNS = [
    "customer_id",
    "customer_unique_id",
    "customer_zip_code_prefix",
    "customer_city",
    "customer_state",
]

OUTPUT_COLUMNS = [
    {"name": "customer_id", "type": "string"},
    {"name": "synthetic_email", "type": "string"},
    {"name": "synthetic_phone", "type": "string"},
    {"name": "marketing_consent", "type": "boolean"},
    {"name": "pii_classification", "type": "string"},
]

OUTPUT_COLUMN_NAMES = [
    column["name"]
    for column in OUTPUT_COLUMNS
]

ALGORITHM_NAME = (
    "sha256-customer-id-derived-synthetic-contact"
)

ALGORITHM_VERSION = "1.0"
ALGORITHM_NAMESPACE = "synthetic-customer-contact-v1"

CONSENT_SCALE = 10_000
CONSENT_THRESHOLD = 7_500

EXPECTED_CONSENT_TRUE = 74_553
EXPECTED_CONSENT_FALSE = 24_888

EXPECTED_CSV_SHA256 = (
    "06f3d4d7fe3511e90e511abbb2c04a72"
    "d01309009a8c3cf239a116a7781cac65"
)

EXPECTED_CSV_SIZE_BYTES = 10_466_274

S3_DESTINATION_BASE = (
    "bronze/generated/supporting/"
    "synthetic-customer-contact/snapshots"
)

TABLE_NAME = "synthetic_customer_contact"

SERDE = {
    "library": (
        "org.apache.hive.hcatalog.data.JsonSerDe"
    ),
    "input_format": (
        "org.apache.hadoop.mapred.TextInputFormat"
    ),
    "output_format": (
        "org.apache.hadoop.hive.ql.io."
        "HiveIgnoreKeyTextOutputFormat"
    ),
}


def sha256_file(file_name: Path) -> str:
    digest = hashlib.sha256()

    with file_name.open("rb") as stream:
        for chunk in iter(
            lambda: stream.read(1024 * 1024),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest()


def canonical_object_sha256(
    value: Any,
) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")

    return hashlib.sha256(payload).hexdigest()


def stable_digest(
    namespace: str,
    customer_id: str,
) -> bytes:
    value = (
        f"{ALGORITHM_NAMESPACE}|"
        f"{namespace}|"
        f"{customer_id}"
    )

    return hashlib.sha256(
        value.encode("utf-8")
    ).digest()


def synthetic_email(
    customer_id: str,
) -> str:
    token = hashlib.sha256(
        (
            f"{ALGORITHM_NAMESPACE}|"
            f"email|{customer_id}"
        ).encode("utf-8")
    ).hexdigest()[:24]

    return f"{token}@synthetic-example.com"


def synthetic_phone(
    customer_id: str,
) -> str:
    digest = stable_digest(
        "phone",
        customer_id,
    )

    number = (
        int.from_bytes(
            digest[:8],
            "big",
        )
        % 10_000_000_000
    )

    return f"+3538{number:010d}"


def marketing_consent(
    customer_id: str,
) -> bool:
    digest = stable_digest(
        "marketing-consent",
        customer_id,
    )

    bucket = (
        int.from_bytes(
            digest[:8],
            "big",
        )
        % CONSENT_SCALE
    )

    return bucket < CONSENT_THRESHOLD


def validate_source_manifest() -> None:
    observed_sha256 = sha256_file(
        SOURCE_MANIFEST_PATH
    )

    if (
        observed_sha256
        != EXPECTED_SOURCE_MANIFEST_SHA256
    ):
        raise RuntimeError(
            "Unexpected source-manifest SHA-256: "
            f"{observed_sha256}"
        )

    manifest = json.loads(
        SOURCE_MANIFEST_PATH.read_text(
            encoding="utf-8"
        )
    )

    if (
        manifest.get("snapshot_id")
        != EXPECTED_SOURCE_SNAPSHOT_ID
    ):
        raise RuntimeError(
            "Unexpected source snapshot ID."
        )

    records = [
        record
        for record in manifest["datasets"]
        if record["filename"]
        == "olist_customers_dataset.csv"
    ]

    if len(records) != 1:
        raise RuntimeError(
            "Expected exactly one customer record."
        )

    record = records[0]

    expected = {
        "row_count": EXPECTED_CUSTOMER_ROWS,
        "size_bytes": EXPECTED_CUSTOMERS_SIZE_BYTES,
        "sha256": EXPECTED_CUSTOMERS_SHA256,
        "columns": EXPECTED_SOURCE_COLUMNS,
    }

    for field_name, expected_value in expected.items():
        if record.get(field_name) != expected_value:
            raise RuntimeError(
                "Unexpected customer manifest "
                f"{field_name}: "
                f"{record.get(field_name)}"
            )


def load_customer_ids() -> list[str]:
    if not SOURCE_CUSTOMERS_PATH.is_file():
        raise FileNotFoundError(
            f"Missing: {SOURCE_CUSTOMERS_PATH}"
        )

    if (
        SOURCE_CUSTOMERS_PATH.stat().st_size
        != EXPECTED_CUSTOMERS_SIZE_BYTES
    ):
        raise RuntimeError(
            "Unexpected customer file size."
        )

    observed_sha256 = sha256_file(
        SOURCE_CUSTOMERS_PATH
    )

    if observed_sha256 != EXPECTED_CUSTOMERS_SHA256:
        raise RuntimeError(
            "Unexpected customer-file SHA-256: "
            f"{observed_sha256}"
        )

    customer_ids: list[str] = []

    with SOURCE_CUSTOMERS_PATH.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as stream:
        reader = csv.DictReader(stream)

        if reader.fieldnames != EXPECTED_SOURCE_COLUMNS:
            raise RuntimeError(
                "Unexpected customer columns."
            )

        for row in reader:
            customer_id = (
                row["customer_id"].strip()
            )

            if not customer_id:
                raise RuntimeError(
                    "Empty customer_id found."
                )

            customer_ids.append(customer_id)

    if len(customer_ids) != EXPECTED_CUSTOMER_ROWS:
        raise RuntimeError(
            "Unexpected source row count."
        )

    unique_ids = sorted(set(customer_ids))

    if len(unique_ids) != EXPECTED_CUSTOMER_ROWS:
        raise RuntimeError(
            "Customer IDs are not unique."
        )

    return unique_ids


def build_records(
    customer_ids: Iterable[str],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    records: list[dict[str, Any]] = []

    emails: set[str] = set()
    phones: set[str] = set()
    consent_true = 0

    for customer_id in customer_ids:
        email = synthetic_email(
            customer_id
        )

        phone = synthetic_phone(
            customer_id
        )

        consent = marketing_consent(
            customer_id
        )

        if email in emails:
            raise RuntimeError(
                "Synthetic-email collision."
            )

        if phone in phones:
            raise RuntimeError(
                "Synthetic-phone collision."
            )

        emails.add(email)
        phones.add(phone)

        if consent:
            consent_true += 1

        records.append(
            {
                "customer_id": customer_id,
                "synthetic_email": email,
                "synthetic_phone": phone,
                "marketing_consent": consent,
                "pii_classification": "PII",
            }
        )

    consent_false = (
        len(records) - consent_true
    )

    if len(records) != EXPECTED_CUSTOMER_ROWS:
        raise RuntimeError(
            "Unexpected generated row count."
        )

    if consent_true != EXPECTED_CONSENT_TRUE:
        raise RuntimeError(
            "Unexpected true-consent count: "
            f"{consent_true}"
        )

    if consent_false != EXPECTED_CONSENT_FALSE:
        raise RuntimeError(
            "Unexpected false-consent count: "
            f"{consent_false}"
        )

    statistics = {
        "row_count": len(records),
        "unique_customer_ids": len(records),
        "unique_emails": len(emails),
        "unique_phones": len(phones),
        "consent_true": consent_true,
        "consent_false": consent_false,
    }

    return records, statistics


def write_csv(
    records: list[dict[str, Any]],
    output_file: Path,
) -> None:
    output_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with output_file.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=OUTPUT_COLUMN_NAMES,
            lineterminator="\n",
        )

        writer.writeheader()
        writer.writerows(records)


def write_jsonl(
    records: list[dict[str, Any]],
    output_file: Path,
) -> None:
    output_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with output_file.open(
        "w",
        encoding="utf-8",
        newline="",
    ) as stream:
        for record in records:
            stream.write(
                json.dumps(
                    record,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            )
            stream.write("\n")


def validate_csv(
    output_file: Path,
) -> None:
    observed_size = (
        output_file.stat().st_size
    )

    observed_sha256 = sha256_file(
        output_file
    )

    if observed_size != EXPECTED_CSV_SIZE_BYTES:
        raise RuntimeError(
            "Unexpected generated CSV size: "
            f"{observed_size}"
        )

    if observed_sha256 != EXPECTED_CSV_SHA256:
        raise RuntimeError(
            "Unexpected generated CSV SHA-256: "
            f"{observed_sha256}"
        )


def validate_jsonl(
    output_file: Path,
) -> None:
    row_count = 0
    customer_ids: set[str] = set()
    emails: set[str] = set()
    phones: set[str] = set()
    consent_true = 0

    with output_file.open(
        "r",
        encoding="utf-8",
    ) as stream:
        for line_number, line in enumerate(
            stream,
            start=1,
        ):
            if not line.endswith("\n"):
                raise RuntimeError(
                    "JSONL line missing LF: "
                    f"{line_number}"
                )

            record = json.loads(line)

            if list(record) != OUTPUT_COLUMN_NAMES:
                raise RuntimeError(
                    "Unexpected JSONL columns."
                )

            if not isinstance(
                record["marketing_consent"],
                bool,
            ):
                raise RuntimeError(
                    "Consent is not boolean."
                )

            for column in [
                "customer_id",
                "synthetic_email",
                "synthetic_phone",
                "pii_classification",
            ]:
                if not isinstance(
                    record[column],
                    str,
                ):
                    raise RuntimeError(
                        f"{column} is not string."
                    )

            if record["pii_classification"] != "PII":
                raise RuntimeError(
                    "Invalid PII classification."
                )

            row_count += 1

            customer_ids.add(
                record["customer_id"]
            )

            emails.add(
                record["synthetic_email"]
            )

            phones.add(
                record["synthetic_phone"]
            )

            if record["marketing_consent"]:
                consent_true += 1

    if row_count != EXPECTED_CUSTOMER_ROWS:
        raise RuntimeError(
            "Unexpected JSONL rows."
        )

    if len(customer_ids) != row_count:
        raise RuntimeError(
            "Duplicate JSONL customer IDs."
        )

    if len(emails) != row_count:
        raise RuntimeError(
            "Duplicate JSONL emails."
        )

    if len(phones) != row_count:
        raise RuntimeError(
            "Duplicate JSONL phones."
        )

    if consent_true != EXPECTED_CONSENT_TRUE:
        raise RuntimeError(
            "Unexpected JSONL consent count."
        )


def install_file(
    temporary_file: Path,
    final_file: Path,
) -> None:
    expected_sha256 = sha256_file(
        temporary_file
    )

    final_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    if final_file.exists():
        if (
            sha256_file(final_file)
            != expected_sha256
        ):
            raise RuntimeError(
                "Existing generated file differs: "
                f"{final_file}"
            )

        return

    shutil.copyfile(
        temporary_file,
        final_file,
    )

    if sha256_file(final_file) != expected_sha256:
        raise RuntimeError(
            "Installed checksum mismatch."
        )


def write_manifest(
    manifest: dict[str, Any],
    output_file: Path,
) -> None:
    output_file.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_file.write_text(
        json.dumps(
            manifest,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def build_manifest(
    snapshot_id: str,
    csv_file: Path,
    jsonl_file: Path,
    statistics: dict[str, int],
) -> dict[str, Any]:
    destination_prefix = (
        f"{S3_DESTINATION_BASE}/"
        f"{snapshot_id}"
    )

    return {
        "schema_version": "1.0",
        "dataset_class": (
            "generated_supporting_data"
        ),
        "source_system": (
            "olist-derived-synthetic-supporting"
        ),
        "dataset_count": 1,
        "generated_snapshot_id": snapshot_id,
        "destination_prefix": (
            destination_prefix
        ),
        "manifest_destination_key": (
            f"{destination_prefix}/"
            "synthetic-customer-contact-manifest.json"
        ),
        "representation": (
            "athena-json-lines"
        ),
        "serde": SERDE,
        "source_manifest_path": (
            "manifests/bronze/olist/"
            "source-manifest.json"
        ),
        "source_manifest_sha256": (
            EXPECTED_SOURCE_MANIFEST_SHA256
        ),
        "source_snapshot_id": (
            EXPECTED_SOURCE_SNAPSHOT_ID
        ),
        "source_dataset": {
            "table_name": "olist_customers",
            "filename": (
                "olist_customers_dataset.csv"
            ),
            "relative_source_path": (
                "data/bronze/raw/olist/"
                "olist_customers_dataset.csv"
            ),
            "row_count": (
                EXPECTED_CUSTOMER_ROWS
            ),
            "size_bytes": (
                EXPECTED_CUSTOMERS_SIZE_BYTES
            ),
            "sha256": (
                EXPECTED_CUSTOMERS_SHA256
            ),
            "columns": (
                EXPECTED_SOURCE_COLUMNS
            ),
        },
        "generator": {
            "relative_path": (
                "scripts/bronze/"
                "build_synthetic_customer_contact.py"
            ),
            "sha256": sha256_file(
                Path(__file__).resolve()
            ),
            "algorithm_name": (
                ALGORITHM_NAME
            ),
            "algorithm_version": (
                ALGORITHM_VERSION
            ),
            "algorithm_namespace": (
                ALGORITHM_NAMESPACE
            ),
            "row_order": (
                "customer_id ascending"
            ),
            "consent_scale": (
                CONSENT_SCALE
            ),
            "consent_threshold": (
                CONSENT_THRESHOLD
            ),
        },
        "governance": {
            "synthetic": True,
            "contains_real_pii": False,
            "contains_simulated_pii": True,
            "classification": (
                "Confidential-Synthetic"
            ),
            "purpose": (
                "Controlled PII, consent, "
                "quarantine and remediation "
                "policy experiments."
            ),
        },
        "constraints": {
            "expected_rows": (
                statistics["row_count"]
            ),
            "null_rows": 0,
            "unique_customer_ids": (
                statistics[
                    "unique_customer_ids"
                ]
            ),
            "unique_synthetic_emails": (
                statistics[
                    "unique_emails"
                ]
            ),
            "unique_synthetic_phones": (
                statistics[
                    "unique_phones"
                ]
            ),
            "marketing_consent_true": (
                statistics[
                    "consent_true"
                ]
            ),
            "marketing_consent_false": (
                statistics[
                    "consent_false"
                ]
            ),
            "marketing_consent_true_percent": (
                round(
                    statistics[
                        "consent_true"
                    ]
                    / statistics[
                        "row_count"
                    ]
                    * 100,
                    4,
                )
            ),
        },
        "source_artifact": {
            "format": "csv",
            "output_filename": (
                "synthetic_customer_contact.csv"
            ),
            "local_relative_path": (
                "source/"
                "synthetic_customer_contact.csv"
            ),
            "destination_key": (
                f"{destination_prefix}/source/"
                "synthetic_customer_contact.csv"
            ),
            "row_count": (
                statistics["row_count"]
            ),
            "column_count": (
                len(OUTPUT_COLUMNS)
            ),
            "columns": OUTPUT_COLUMNS,
            "output_size_bytes": (
                csv_file.stat().st_size
            ),
            "output_sha256": (
                sha256_file(csv_file)
            ),
        },
        "datasets": [
            {
                "table_name": TABLE_NAME,
                "output_filename": "data.jsonl",
                "local_relative_path": (
                    "tables/"
                    "synthetic_customer_contact/"
                    "data.jsonl"
                ),
                "destination_key": (
                    f"{destination_prefix}/tables/"
                    "synthetic_customer_contact/"
                    "data.jsonl"
                ),
                "destination_location": (
                    "s3://${data_lake_bucket}/"
                    f"{destination_prefix}/tables/"
                    "synthetic_customer_contact/"
                ),
                "row_count": (
                    statistics["row_count"]
                ),
                "physical_line_count": (
                    statistics["row_count"]
                ),
                "column_count": (
                    len(OUTPUT_COLUMNS)
                ),
                "columns": OUTPUT_COLUMNS,
                "output_size_bytes": (
                    jsonl_file.stat().st_size
                ),
                "output_sha256": (
                    sha256_file(jsonl_file)
                ),
                "primary_key": [
                    "customer_id"
                ],
            }
        ],
        "total_data_rows": (
            statistics["row_count"]
        ),
        "total_output_size_bytes": (
            csv_file.stat().st_size
            + jsonl_file.stat().st_size
        ),
    }


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--output-root",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--manifest-output",
        type=Path,
        required=True,
    )

    return parser.parse_args()


def main() -> None:
    arguments = parse_arguments()

    output_root = (
        arguments.output_root
        .expanduser()
        .resolve()
    )

    manifest_output = (
        arguments.manifest_output
        .expanduser()
        .resolve()
    )

    validate_source_manifest()

    customer_ids = load_customer_ids()

    records, statistics = build_records(
        customer_ids
    )

    output_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    with tempfile.TemporaryDirectory(
        prefix="synthetic-contact-",
        dir=output_root,
    ) as temporary_directory:
        temporary_root = Path(
            temporary_directory
        )

        temporary_csv = (
            temporary_root
            / "synthetic_customer_contact.csv"
        )

        temporary_jsonl = (
            temporary_root
            / "data.jsonl"
        )

        write_csv(
            records,
            temporary_csv,
        )

        write_jsonl(
            records,
            temporary_jsonl,
        )

        validate_csv(
            temporary_csv
        )

        validate_jsonl(
            temporary_jsonl
        )

        csv_sha256 = sha256_file(
            temporary_csv
        )

        jsonl_sha256 = sha256_file(
            temporary_jsonl
        )

        snapshot_material = {
            "algorithm_name": (
                ALGORITHM_NAME
            ),
            "algorithm_version": (
                ALGORITHM_VERSION
            ),
            "algorithm_namespace": (
                ALGORITHM_NAMESPACE
            ),
            "source_snapshot_id": (
                EXPECTED_SOURCE_SNAPSHOT_ID
            ),
            "source_customer_sha256": (
                EXPECTED_CUSTOMERS_SHA256
            ),
            "source_rows": (
                EXPECTED_CUSTOMER_ROWS
            ),
            "schema": OUTPUT_COLUMNS,
            "csv_sha256": csv_sha256,
            "jsonl_sha256": jsonl_sha256,
        }

        snapshot_id = (
            canonical_object_sha256(
                snapshot_material
            )
        )

        snapshot_root = (
            output_root
            / snapshot_id
        )

        final_csv = (
            snapshot_root
            / "source"
            / "synthetic_customer_contact.csv"
        )

        final_jsonl = (
            snapshot_root
            / "tables"
            / TABLE_NAME
            / "data.jsonl"
        )

        install_file(
            temporary_csv,
            final_csv,
        )

        install_file(
            temporary_jsonl,
            final_jsonl,
        )

    manifest = build_manifest(
        snapshot_id,
        final_csv,
        final_jsonl,
        statistics,
    )

    snapshot_manifest = (
        snapshot_root
        / "synthetic-customer-contact-"
        "manifest.json"
    )

    write_manifest(
        manifest,
        snapshot_manifest,
    )

    write_manifest(
        manifest,
        manifest_output,
    )

    if (
        sha256_file(snapshot_manifest)
        != sha256_file(manifest_output)
    ):
        raise RuntimeError(
            "Generated manifests differ."
        )

    print(
        "Synthetic customer-contact "
        "Bronze build: PASS"
    )

    print(
        "Generated snapshot ID:",
        snapshot_id,
    )

    print(
        "Rows:",
        statistics["row_count"],
    )

    print(
        "Consent true:",
        statistics["consent_true"],
    )

    print(
        "Consent false:",
        statistics["consent_false"],
    )

    print(
        "Canonical CSV SHA-256:",
        sha256_file(final_csv),
    )

    print(
        "JSONL SHA-256:",
        sha256_file(final_jsonl),
    )

    print(
        "Manifest SHA-256:",
        sha256_file(manifest_output),
    )

    print(
        "Snapshot root:",
        snapshot_root,
    )

    print(
        "Manifest:",
        manifest_output,
    )


if __name__ == "__main__":
    main()
