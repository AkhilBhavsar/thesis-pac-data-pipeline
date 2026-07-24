#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
from pathlib import Path
from typing import Any


EXPECTED_SOURCE_MANIFEST_SHA256 = (
    "0666ef2ad51bc52f9a2d5285c624154e"
    "84d7d290d3663b453f6d93f56c0ddbec"
)

EXPECTED_SOURCE_SNAPSHOT_ID = (
    "43cc5e9c8436f7919491dd90872d6f4d"
    "94d61d4694c1d4307e41456e405052d2"
)

TRANSFORMATION_NAME = (
    "csv-to-athena-jsonl"
)

TRANSFORMATION_VERSION = "1.0"

SERDE_LIBRARY = (
    "org.apache.hive.hcatalog.data.JsonSerDe"
)

INPUT_FORMAT = (
    "org.apache.hadoop.mapred.TextInputFormat"
)

OUTPUT_FORMAT = (
    "org.apache.hadoop.hive.ql.io."
    "HiveIgnoreKeyTextOutputFormat"
)

TABLE_NAMES = {
    "olist_customers_dataset.csv": (
        "olist_customers"
    ),
    "olist_geolocation_dataset.csv": (
        "olist_geolocation"
    ),
    "olist_order_items_dataset.csv": (
        "olist_order_items"
    ),
    "olist_order_payments_dataset.csv": (
        "olist_order_payments"
    ),
    "olist_order_reviews_dataset.csv": (
        "olist_order_reviews"
    ),
    "olist_orders_dataset.csv": (
        "olist_orders"
    ),
    "olist_products_dataset.csv": (
        "olist_products"
    ),
    "olist_sellers_dataset.csv": (
        "olist_sellers"
    ),
    "product_category_name_translation.csv": (
        "olist_product_category_name_translation"
    ),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a deterministic, Athena-compatible "
            "JSON Lines representation of the immutable "
            "Olist raw Bronze snapshot."
        )
    )

    parser.add_argument(
        "--source-manifest",
        type=Path,
        default=Path(
            "manifests/bronze/olist/"
            "source-manifest.json"
        ),
    )

    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path(
            "/tmp/olist-query-compatible"
        ),
    )

    return parser.parse_args()


def sha256_file(
    path: Path,
) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(
            lambda: handle.read(
                1024 * 1024
            ),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest()


def canonical_json_bytes(
    value: Any,
) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def validate_source_manifest(
    manifest_path: Path,
) -> dict[str, Any]:
    if not manifest_path.is_file():
        raise RuntimeError(
            "Source manifest does not exist: "
            f"{manifest_path}"
        )

    observed_manifest_sha256 = (
        sha256_file(
            manifest_path
        )
    )

    if (
        observed_manifest_sha256
        != EXPECTED_SOURCE_MANIFEST_SHA256
    ):
        raise RuntimeError(
            "Unexpected source manifest SHA-256: "
            f"{observed_manifest_sha256}"
        )

    manifest = json.loads(
        manifest_path.read_text(
            encoding="utf-8"
        )
    )

    if (
        manifest.get("snapshot_id")
        != EXPECTED_SOURCE_SNAPSHOT_ID
    ):
        raise RuntimeError(
            "Unexpected raw source snapshot ID."
        )

    datasets = manifest.get(
        "datasets",
        [],
    )

    observed_filenames = [
        item["filename"]
        for item in datasets
    ]

    if (
        observed_filenames
        != list(TABLE_NAMES)
    ):
        raise RuntimeError(
            "Unexpected source dataset set "
            "or ordering."
        )

    if manifest.get(
        "dataset_count"
    ) != 9:
        raise RuntimeError(
            "Expected exactly nine datasets."
        )

    if manifest.get(
        "total_data_rows"
    ) != 1550922:
        raise RuntimeError(
            "Unexpected total source row count."
        )

    if manifest.get(
        "total_size_bytes"
    ) != 126186995:
        raise RuntimeError(
            "Unexpected total source byte count."
        )

    return manifest


def write_jsonl_dataset(
    *,
    source_dataset: dict[str, Any],
    output_path: Path,
) -> dict[str, Any]:
    source_path = Path(
        source_dataset[
            "relative_source_path"
        ]
    )

    if not source_path.is_file():
        raise RuntimeError(
            f"Missing source dataset: {source_path}"
        )

    observed_source_sha256 = (
        sha256_file(
            source_path
        )
    )

    if (
        observed_source_sha256
        != source_dataset["sha256"]
    ):
        raise RuntimeError(
            "Source SHA-256 mismatch for "
            f"{source_path.name}."
        )

    if (
        source_path.stat().st_size
        != source_dataset["size_bytes"]
    ):
        raise RuntimeError(
            "Source byte-size mismatch for "
            f"{source_path.name}."
        )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=False,
    )

    row_count = 0
    records_with_embedded_breaks = 0
    fields_with_carriage_returns = 0
    fields_with_line_feeds = 0

    with source_path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as source_handle:
        reader = csv.reader(
            source_handle
        )

        header = next(
            reader,
            None,
        )

        if header is None:
            raise RuntimeError(
                f"Empty CSV: {source_path}"
            )

        if (
            header
            != source_dataset["columns"]
        ):
            raise RuntimeError(
                "Column mismatch for "
                f"{source_path.name}."
            )

        if len(
            set(header)
        ) != len(header):
            raise RuntimeError(
                "Duplicate column names in "
                f"{source_path.name}."
            )

        with output_path.open(
            "wb"
        ) as output_handle:
            for source_row_number, row in enumerate(
                reader,
                start=2,
            ):
                if len(row) != len(header):
                    raise RuntimeError(
                        "Malformed source row "
                        f"{source_row_number} in "
                        f"{source_path.name}: "
                        f"expected {len(header)} "
                        f"columns, observed "
                        f"{len(row)}."
                    )

                record_has_embedded_break = False

                for value in row:
                    if "\r" in value:
                        fields_with_carriage_returns += 1
                        record_has_embedded_break = True

                    if "\n" in value:
                        fields_with_line_feeds += 1
                        record_has_embedded_break = True

                    if "\x00" in value:
                        raise RuntimeError(
                            "NUL character found in "
                            f"{source_path.name}, "
                            f"row {source_row_number}."
                        )

                if record_has_embedded_break:
                    records_with_embedded_breaks += 1

                record = dict(
                    zip(
                        header,
                        row,
                        strict=True,
                    )
                )

                encoded_record = (
                    json.dumps(
                        record,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ).encode("utf-8")
                )

                if (
                    b"\r" in encoded_record
                    or b"\n" in encoded_record
                ):
                    raise RuntimeError(
                        "JSON encoder emitted an "
                        "unescaped physical line break."
                    )

                output_handle.write(
                    encoded_record
                )

                output_handle.write(
                    b"\n"
                )

                row_count += 1

    if (
        row_count
        != source_dataset["row_count"]
    ):
        raise RuntimeError(
            "Generated row-count mismatch for "
            f"{source_path.name}: "
            f"expected "
            f"{source_dataset['row_count']}, "
            f"observed {row_count}."
        )

    output_payload = (
        output_path.read_bytes()
    )

    physical_line_count = (
        output_payload.count(
            b"\n"
        )
    )

    if physical_line_count != row_count:
        raise RuntimeError(
            "Generated JSONL physical-line "
            f"count mismatch for "
            f"{source_path.name}."
        )

    return {
        "source_filename": (
            source_path.name
        ),
        "source_relative_path": (
            source_path.as_posix()
        ),
        "source_size_bytes": (
            source_path.stat().st_size
        ),
        "source_sha256": (
            observed_source_sha256
        ),
        "table_name": TABLE_NAMES[
            source_path.name
        ],
        "local_relative_path": (
            output_path.as_posix()
        ),
        "output_filename": (
            output_path.name
        ),
        "output_size_bytes": (
            output_path.stat().st_size
        ),
        "output_sha256": (
            sha256_file(
                output_path
            )
        ),
        "row_count": row_count,
        "physical_line_count": (
            physical_line_count
        ),
        "column_count": len(
            header
        ),
        "columns": [
            {
                "name": column,
                "type": "string",
            }
            for column in header
        ],
        "records_with_embedded_breaks": (
            records_with_embedded_breaks
        ),
        "fields_with_carriage_returns": (
            fields_with_carriage_returns
        ),
        "fields_with_line_feeds": (
            fields_with_line_feeds
        ),
    }


def validate_generated_jsonl(
    *,
    dataset: dict[str, Any],
    output_path: Path,
) -> None:
    observed_rows = 0

    expected_columns = [
        column["name"]
        for column in dataset["columns"]
    ]

    with output_path.open(
        "rb"
    ) as handle:
        for physical_line_number, line in enumerate(
            handle,
            start=1,
        ):
            if not line.endswith(
                b"\n"
            ):
                raise RuntimeError(
                    "Generated JSONL line lacks "
                    "LF termination: "
                    f"{output_path}, line "
                    f"{physical_line_number}."
                )

            payload = line[:-1]

            if (
                b"\r" in payload
                or b"\n" in payload
            ):
                raise RuntimeError(
                    "Generated JSONL contains a "
                    "physical embedded line break."
                )

            record = json.loads(
                payload.decode("utf-8")
            )

            if (
                list(record)
                != expected_columns
            ):
                raise RuntimeError(
                    "Generated JSON object columns "
                    "do not match source order."
                )

            if not all(
                isinstance(value, str)
                for value in record.values()
            ):
                raise RuntimeError(
                    "Generated JSON values must "
                    "all be strings."
                )

            observed_rows += 1

    if (
        observed_rows
        != dataset["row_count"]
    ):
        raise RuntimeError(
            "Generated JSONL validation "
            "row-count mismatch."
        )


def main() -> int:
    options = parse_args()

    source_manifest = (
        validate_source_manifest(
            options.source_manifest
        )
    )

    if options.output_root.exists():
        raise RuntimeError(
            "Output root already exists: "
            f"{options.output_root}. "
            "Remove it explicitly before rerunning."
        )

    staging_directory = (
        options.output_root
        / ".staging"
    )

    staging_directory.mkdir(
        parents=True,
        exist_ok=False,
    )

    generated_datasets: list[
        dict[str, Any]
    ] = []

    try:
        for source_dataset in (
            source_manifest["datasets"]
        ):
            table_name = TABLE_NAMES[
                source_dataset[
                    "filename"
                ]
            ]

            output_path = (
                staging_directory
                / "tables"
                / table_name
                / "data.jsonl"
            )

            generated_dataset = (
                write_jsonl_dataset(
                    source_dataset=(
                        source_dataset
                    ),
                    output_path=(
                        output_path
                    ),
                )
            )

            generated_dataset[
                "local_relative_path"
            ] = (
                Path("tables")
                / table_name
                / "data.jsonl"
            ).as_posix()

            validate_generated_jsonl(
                dataset=(
                    generated_dataset
                ),
                output_path=output_path,
            )

            generated_datasets.append(
                generated_dataset
            )

            print(
                f"[PASS] {table_name:<42} "
                f"rows="
                f"{generated_dataset['row_count']:>8} "
                f"bytes="
                f"{generated_dataset['output_size_bytes']:>10} "
                f"embedded_records="
                f"{generated_dataset['records_with_embedded_breaks']:>5}"
            )

        snapshot_basis = {
            "schema_version": "1.0",
            "source_system": "olist",
            "source_snapshot_id": (
                source_manifest[
                    "snapshot_id"
                ]
            ),
            "source_manifest_sha256": (
                EXPECTED_SOURCE_MANIFEST_SHA256
            ),
            "representation": (
                "athena-json-lines"
            ),
            "transformation": {
                "name": (
                    TRANSFORMATION_NAME
                ),
                "version": (
                    TRANSFORMATION_VERSION
                ),
                "field_value_policy": (
                    "Preserve exact decoded CSV "
                    "field strings; JSON encoding "
                    "escapes embedded control "
                    "characters."
                ),
            },
            "serde": {
                "library": (
                    SERDE_LIBRARY
                ),
                "input_format": (
                    INPUT_FORMAT
                ),
                "output_format": (
                    OUTPUT_FORMAT
                ),
            },
            "datasets": [
                {
                    "source_filename": (
                        dataset[
                            "source_filename"
                        ]
                    ),
                    "source_sha256": (
                        dataset[
                            "source_sha256"
                        ]
                    ),
                    "table_name": (
                        dataset[
                            "table_name"
                        ]
                    ),
                    "output_sha256": (
                        dataset[
                            "output_sha256"
                        ]
                    ),
                    "output_size_bytes": (
                        dataset[
                            "output_size_bytes"
                        ]
                    ),
                    "row_count": (
                        dataset[
                            "row_count"
                        ]
                    ),
                    "columns": (
                        dataset["columns"]
                    ),
                }
                for dataset in (
                    generated_datasets
                )
            ],
        }

        generated_snapshot_id = (
            hashlib.sha256(
                canonical_json_bytes(
                    snapshot_basis
                )
            ).hexdigest()
        )

        destination_prefix = (
            "bronze/generated/olist/"
            "query-compatible/snapshots/"
            f"{generated_snapshot_id}"
        )

        for dataset in generated_datasets:
            dataset[
                "destination_location"
            ] = (
                "s3://"
                "${data_lake_bucket}/"
                f"{destination_prefix}/"
                "tables/"
                f"{dataset['table_name']}/"
            )

            dataset[
                "destination_key"
            ] = (
                f"{destination_prefix}/"
                "tables/"
                f"{dataset['table_name']}/"
                "data.jsonl"
            )

        manifest = {
            "schema_version": "1.0",
            "source_system": "olist",
            "source_snapshot_id": (
                source_manifest[
                    "snapshot_id"
                ]
            ),
            "source_manifest_path": (
                options.source_manifest.as_posix()
            ),
            "source_manifest_sha256": (
                EXPECTED_SOURCE_MANIFEST_SHA256
            ),
            "generated_snapshot_id": (
                generated_snapshot_id
            ),
            "representation": (
                "athena-json-lines"
            ),
            "transformation": {
                "name": (
                    TRANSFORMATION_NAME
                ),
                "version": (
                    TRANSFORMATION_VERSION
                ),
                "field_value_policy": (
                    "Exact decoded CSV strings are "
                    "preserved. JSON escaping makes "
                    "embedded CR and LF characters "
                    "safe for one-record-per-line "
                    "processing."
                ),
            },
            "serde": {
                "library": (
                    SERDE_LIBRARY
                ),
                "input_format": (
                    INPUT_FORMAT
                ),
                "output_format": (
                    OUTPUT_FORMAT
                ),
            },
            "destination_prefix": (
                destination_prefix
            ),
            "manifest_destination_key": (
                f"{destination_prefix}/"
                "query-compatible-manifest.json"
            ),
            "dataset_count": len(
                generated_datasets
            ),
            "total_data_rows": sum(
                dataset["row_count"]
                for dataset in generated_datasets
            ),
            "total_output_size_bytes": sum(
                dataset[
                    "output_size_bytes"
                ]
                for dataset in generated_datasets
            ),
            "total_records_with_embedded_breaks": (
                sum(
                    dataset[
                        "records_with_embedded_breaks"
                    ]
                    for dataset in (
                        generated_datasets
                    )
                )
            ),
            "datasets": (
                generated_datasets
            ),
        }

        manifest_path = (
            staging_directory
            / "query-compatible-manifest.json"
        )

        manifest_path.write_text(
            json.dumps(
                manifest,
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

        final_directory = (
            options.output_root
            / generated_snapshot_id
        )

        if final_directory.exists():
            raise RuntimeError(
                "Generated snapshot directory "
                "already exists: "
                f"{final_directory}"
            )

        staging_directory.rename(
            final_directory
        )

        final_manifest_path = (
            final_directory
            / "query-compatible-manifest.json"
        )

        print()
        print(
            "Source snapshot ID:",
            source_manifest[
                "snapshot_id"
            ],
        )

        print(
            "Generated snapshot ID:",
            generated_snapshot_id,
        )

        print(
            "Dataset count:",
            manifest[
                "dataset_count"
            ],
        )

        print(
            "Total data rows:",
            manifest[
                "total_data_rows"
            ],
        )

        print(
            "Total output bytes:",
            manifest[
                "total_output_size_bytes"
            ],
        )

        print(
            "Records with embedded breaks:",
            manifest[
                "total_records_with_embedded_breaks"
            ],
        )

        print(
            "Manifest SHA-256:",
            sha256_file(
                final_manifest_path
            ),
        )

        print(
            "Output directory:",
            final_directory,
        )

        print(
            "Manifest path:",
            final_manifest_path,
        )

        print(
            "AWS writes performed: 0"
        )

    except Exception:
        if options.output_root.exists():
            shutil.rmtree(
                options.output_root
            )

        raise

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
