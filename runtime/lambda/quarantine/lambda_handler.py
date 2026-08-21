from __future__ import annotations

import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ALLOWED_SCENARIOS = {
    "pii_exposure",
    "freshness_breach",
    "quality_regression",
}

SOURCE_PREFIX = "experiments/c2/"
QUARANTINE_PREFIX = "quarantine/objects/"

TERMINAL_STATE = "QUARANTINED"

OWNERSHIP_METADATA_KEY = (
    "thesis-c2-event-id"
)


class QuarantineRuntimeError(RuntimeError):
    pass


class QuarantinePersistenceError(
    QuarantineRuntimeError
):

    def __init__(
        self,
        message: str,
        *,
        query_id: str,
        state: str,
        compensation_safe: bool,
    ) -> None:
        super().__init__(message)
        self.query_id = query_id
        self.state = state
        self.compensation_safe = (
            compensation_safe
        )


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def safe_token(value: str) -> str:
    normalized = re.sub(
        r"[^a-zA-Z0-9._-]+",
        "-",
        value,
    ).strip("-")

    if not normalized:
        raise QuarantineRuntimeError(
            "Identifier is empty after normalization."
        )

    return normalized


def sql_string(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def sql_timestamp(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )
    except ValueError as error:
        raise QuarantineRuntimeError(
            f"Invalid UTC timestamp: {value}"
        ) from error

    if parsed.tzinfo is None:
        raise QuarantineRuntimeError(
            "Timestamp must include timezone."
        )

    rendered = (
        parsed.astimezone(timezone.utc)
        .replace(tzinfo=None)
        .strftime("%Y-%m-%d %H:%M:%S.%f")
    )

    return f"TIMESTAMP '{rendered}'"


def validate_request(
    payload: dict[str, Any],
    *,
    data_bucket: str,
) -> None:
    required = {
        "condition",
        "run_id",
        "scenario_id",
        "source_bucket",
        "source_key",
        "source_dataset",
        "source_relation",
        "policy_category",
        "policy_id",
        "violation_code",
        "violation_details",
        "data_classification",
        "detected_at",
        "retry_count",
        "max_retries",
        "evidence_uri",
    }

    missing = sorted(
        required - payload.keys()
    )

    if missing:
        raise QuarantineRuntimeError(
            f"Missing quarantine fields: {missing}"
        )

    if payload["condition"] != "C2":
        raise QuarantineRuntimeError(
            "Quarantine runtime accepts only C2."
        )

    if (
        payload["scenario_id"]
        not in ALLOWED_SCENARIOS
    ):
        raise QuarantineRuntimeError(
            "Scenario is not quarantine-eligible."
        )

    if payload["source_bucket"] != data_bucket:
        raise QuarantineRuntimeError(
            "Rejected output must be in the "
            "configured thesis data-lake bucket."
        )

    source_key = str(
        payload["source_key"]
    )

    if not source_key.startswith(
        SOURCE_PREFIX
    ):
        raise QuarantineRuntimeError(
            "Rejected output escaped the "
            "experiments/c2 source boundary."
        )

    if ".." in Path(source_key).parts:
        raise QuarantineRuntimeError(
            "S3 source traversal is forbidden."
        )

    retry_count = payload["retry_count"]
    max_retries = payload["max_retries"]

    if (
        not isinstance(retry_count, int)
        or isinstance(retry_count, bool)
        or retry_count < 0
        or retry_count > 2
    ):
        raise QuarantineRuntimeError(
            "retry_count must be between 0 and 2."
        )

    if (
        not isinstance(max_retries, int)
        or isinstance(max_retries, bool)
        or max_retries < 0
        or max_retries > 2
    ):
        raise QuarantineRuntimeError(
            "max_retries must be between 0 and 2."
        )

    if retry_count > max_retries:
        raise QuarantineRuntimeError(
            "retry_count exceeds max_retries."
        )

    sql_timestamp(
        str(payload["detected_at"])
    )


def destination_key(
    payload: dict[str, Any],
) -> str:
    source_name = Path(
        payload["source_key"]
    ).name

    if not source_name:
        raise QuarantineRuntimeError(
            "Rejected source key has no object name."
        )

    scenario = safe_token(
        payload["scenario_id"]
    )

    run_id = safe_token(
        payload["run_id"]
    )

    object_name = safe_token(
        source_name
    )

    return (
        f"{QUARANTINE_PREFIX}"
        f"{scenario}/"
        f"{run_id}/"
        f"{object_name}"
    )


def event_identifier(
    *,
    payload: dict[str, Any],
    destination_uri: str,
) -> str:
    material = "|".join(
        [
            payload["run_id"],
            payload["scenario_id"],
            payload["source_key"],
            destination_uri,
            payload["detected_at"],
        ]
    )

    digest = hashlib.sha256(
        material.encode("utf-8")
    ).hexdigest()

    return f"c2-q-{digest[:24]}"


def build_event(
    *,
    payload: dict[str, Any],
    destination_uri: str,
    quarantined_at: str,
) -> dict[str, Any]:
    return {
        "quarantine_event_id": event_identifier(
            payload=payload,
            destination_uri=destination_uri,
        ),
        "run_id": payload["run_id"],
        "scenario_id": payload["scenario_id"],
        "source_dataset": payload[
            "source_dataset"
        ],
        "source_relation": payload[
            "source_relation"
        ],
        "rejected_output_location": (
            destination_uri
        ),
        "policy_category": payload[
            "policy_category"
        ],
        "policy_id": payload["policy_id"],
        "violation_code": payload[
            "violation_code"
        ],
        "violation_details": payload[
            "violation_details"
        ],
        "data_classification": payload[
            "data_classification"
        ],
        "detected_at": payload[
            "detected_at"
        ],
        "quarantined_at": quarantined_at,
        "remediation_action": "quarantine",
        "remediation_status": "SUCCEEDED",
        "retry_count": payload[
            "retry_count"
        ],
        "max_retries": payload[
            "max_retries"
        ],
        "manual_review_required": False,
        "manual_review_status": (
            "NOT_REQUIRED"
        ),
        "release_status": "BLOCKED",
        "released_at": None,
        "final_state": TERMINAL_STATE,
        "evidence_uri": payload[
            "evidence_uri"
        ],
    }


def build_insert_sql(
    *,
    event: dict[str, Any],
    database_name: str,
    table_name: str,
) -> str:
    database = safe_token(
        database_name
    )

    table = safe_token(
        table_name
    )

    values = [
        sql_string(
            event["quarantine_event_id"]
        ),
        sql_string(event["run_id"]),
        sql_string(event["scenario_id"]),
        sql_string(
            event["source_dataset"]
        ),
        sql_string(
            event["source_relation"]
        ),
        sql_string(
            event[
                "rejected_output_location"
            ]
        ),
        sql_string(
            event["policy_category"]
        ),
        sql_string(event["policy_id"]),
        sql_string(
            event["violation_code"]
        ),
        sql_string(
            event["violation_details"]
        ),
        sql_string(
            event["data_classification"]
        ),
        sql_timestamp(
            event["detected_at"]
        ),
        sql_timestamp(
            event["quarantined_at"]
        ),
        sql_string(
            event["remediation_action"]
        ),
        sql_string(
            event["remediation_status"]
        ),
        str(event["retry_count"]),
        str(event["max_retries"]),
        "FALSE",
        sql_string(
            event["manual_review_status"]
        ),
        sql_string(
            event["release_status"]
        ),
        "CAST(NULL AS TIMESTAMP)",
        sql_string(
            event["final_state"]
        ),
        sql_string(
            event["evidence_uri"]
        ),
    ]

    return (
        f'INSERT INTO "{database}".'
        f'"{table}" '
        "SELECT "
        + ", ".join(values)
    )


def is_missing_object_error(
    error: Exception,
) -> bool:
    response = getattr(
        error,
        "response",
        {},
    )

    code = str(
        response.get(
            "Error",
            {},
        ).get(
            "Code",
            "",
        )
    )

    http_status = response.get(
        "ResponseMetadata",
        {},
    ).get(
        "HTTPStatusCode"
    )

    return (
        code in {
            "404",
            "NoSuchKey",
            "NotFound",
        }
        or http_status == 404
    )


def head_object_or_none(
    *,
    s3_client: Any,
    bucket: str,
    key: str,
) -> dict[str, Any] | None:
    try:
        return s3_client.head_object(
            Bucket=bucket,
            Key=key,
        )
    except Exception as error:
        if is_missing_object_error(
            error
        ):
            return None

        raise QuarantineRuntimeError(
            "Unable to inspect S3 quarantine state."
        ) from error


def validate_copy_fingerprint(
    *,
    source: dict[str, Any],
    target: dict[str, Any],
) -> None:
    if (
        source.get("ContentLength")
        != target.get("ContentLength")
    ):
        raise QuarantineRuntimeError(
            "Quarantine copy size validation failed."
        )

    source_etag = source.get("ETag")
    target_etag = target.get("ETag")

    if (
        source_etag is not None
        and target_etag is not None
        and source_etag != target_etag
    ):
        raise QuarantineRuntimeError(
            "Quarantine copy ETag validation failed."
        )


def object_timestamp(
    *,
    target: dict[str, Any],
    override: str | None,
) -> str:
    if override is not None:
        sql_timestamp(override)
        return override

    last_modified = target.get(
        "LastModified"
    )

    if isinstance(
        last_modified,
        datetime,
    ):
        if last_modified.tzinfo is None:
            last_modified = (
                last_modified.replace(
                    tzinfo=timezone.utc
                )
            )

        return (
            last_modified
            .astimezone(timezone.utc)
            .isoformat()
            .replace("+00:00", "Z")
        )

    raise QuarantineRuntimeError(
        "Quarantine destination has no stable "
        "LastModified timestamp."
    )


def object_identity(
    target: dict[str, Any],
) -> str:
    version_id = target.get(
        "VersionId"
    )

    if version_id:
        return f"version:{version_id}"

    last_modified = target.get(
        "LastModified"
    )

    etag = target.get(
        "ETag",
        "",
    )

    if last_modified and etag:
        return (
            f"last-modified:{last_modified}|"
            f"etag:{etag}"
        )

    raise QuarantineRuntimeError(
        "Quarantine destination has no stable "
        "object identity."
    )


def prepare_destination(
    *,
    s3_client: Any,
    bucket: str,
    source_key: str,
    target_key: str,
    expected_event_id: str,
) -> dict[str, Any]:
    source = head_object_or_none(
        s3_client=s3_client,
        bucket=bucket,
        key=source_key,
    )

    target = head_object_or_none(
        s3_client=s3_client,
        bucket=bucket,
        key=target_key,
    )

    if target is not None:
        owner = target.get(
            "Metadata",
            {},
        ).get(
            OWNERSHIP_METADATA_KEY
        )

        if owner != expected_event_id:
            raise QuarantineRuntimeError(
                "Quarantine destination already exists "
                "without matching C2 ownership."
            )

        if source is not None:
            validate_copy_fingerprint(
                source=source,
                target=target,
            )

        return {
            "source": source,
            "target": target,
            "destination_created": False,
            "resumed_owned_destination": True,
        }

    if source is None:
        raise QuarantineRuntimeError(
            "Rejected source object does not exist "
            "and no owned quarantine copy was found."
        )

    metadata = dict(
        source.get(
            "Metadata",
            {},
        )
    )

    metadata[
        OWNERSHIP_METADATA_KEY
    ] = expected_event_id

    copy_arguments: dict[str, Any] = {
        "Bucket": bucket,
        "Key": target_key,
        "CopySource": {
            "Bucket": bucket,
            "Key": source_key,
        },
        "MetadataDirective": "REPLACE",
        "Metadata": metadata,
    }

    for field in (
        "CacheControl",
        "ContentDisposition",
        "ContentEncoding",
        "ContentLanguage",
        "ContentType",
        "Expires",
    ):
        if source.get(field) is not None:
            copy_arguments[field] = source[field]

    s3_client.copy_object(
        **copy_arguments
    )

    target = head_object_or_none(
        s3_client=s3_client,
        bucket=bucket,
        key=target_key,
    )

    if target is None:
        raise QuarantineRuntimeError(
            "Quarantine copy was not materialized."
        )

    validate_copy_fingerprint(
        source=source,
        target=target,
    )

    if target.get(
        "Metadata",
        {},
    ).get(
        OWNERSHIP_METADATA_KEY
    ) != expected_event_id:
        raise QuarantineRuntimeError(
            "Quarantine copy ownership validation failed."
        )

    return {
        "source": source,
        "target": target,
        "destination_created": True,
        "resumed_owned_destination": False,
    }


def remove_source(
    *,
    s3_client: Any,
    bucket: str,
    source_key: str,
) -> None:
    try:
        s3_client.delete_object(
            Bucket=bucket,
            Key=source_key,
        )
    except Exception as error:
        raise QuarantineRuntimeError(
            "Quarantine event was persisted but "
            "source removal failed."
        ) from error

    if head_object_or_none(
        s3_client=s3_client,
        bucket=bucket,
        key=source_key,
    ) is not None:
        raise QuarantineRuntimeError(
            "Quarantine event was persisted but "
            "the source object remains current."
        )


def compensate_destination(
    *,
    s3_client: Any,
    bucket: str,
    target_key: str,
) -> None:
    try:
        s3_client.delete_object(
            Bucket=bucket,
            Key=target_key,
        )
    except Exception as error:
        raise QuarantineRuntimeError(
            "Athena persistence failed and "
            "quarantine-copy compensation failed; "
            "the source remains protected."
        ) from error

    if head_object_or_none(
        s3_client=s3_client,
        bucket=bucket,
        key=target_key,
    ) is not None:
        raise QuarantineRuntimeError(
            "Athena persistence failed and the "
            "compensating quarantine-copy deletion "
            "did not complete."
        )


def athena_request_token(
    *,
    event_id: str,
    target_identity: str,
) -> str:
    material = (
        f"{event_id}|{target_identity}|"
        "athena-insert-v1"
    )

    return hashlib.sha256(
        material.encode("utf-8")
    ).hexdigest()


def persist_event(
    *,
    athena_client: Any,
    event: dict[str, Any],
    database_name: str,
    table_name: str,
    workgroup: str,
    client_request_token: str,
    timeout_seconds: float = 30.0,
) -> str:
    query = build_insert_sql(
        event=event,
        database_name=database_name,
        table_name=table_name,
    )

    response = (
        athena_client.start_query_execution(
            QueryString=query,
            ClientRequestToken=(
                client_request_token
            ),
            QueryExecutionContext={
                "Database": database_name,
            },
            WorkGroup=workgroup,
        )
    )

    query_id = response[
        "QueryExecutionId"
    ]

    started = time.monotonic()

    while True:
        status = (
            athena_client
            .get_query_execution(
                QueryExecutionId=query_id
            )[
                "QueryExecution"
            ][
                "Status"
            ]
        )

        state = status["State"]

        if state == "SUCCEEDED":
            return query_id

        if state in {
            "FAILED",
            "CANCELLED",
        }:
            raise QuarantinePersistenceError(
                "Quarantine event Athena write "
                f"{state}: "
                f"{status.get('StateChangeReason', '')}",
                query_id=query_id,
                state=state,
                compensation_safe=True,
            )

        if (
            time.monotonic()
            - started
            > timeout_seconds
        ):
            try:
                athena_client.stop_query_execution(
                    QueryExecutionId=query_id
                )

                settled_status = (
                    athena_client
                    .get_query_execution(
                        QueryExecutionId=query_id
                    )[
                        "QueryExecution"
                    ][
                        "Status"
                    ]
                )
            except Exception as error:
                raise QuarantinePersistenceError(
                    "Quarantine event Athena write "
                    "timed out and its final state "
                    "could not be confirmed.",
                    query_id=query_id,
                    state="UNKNOWN",
                    compensation_safe=False,
                ) from error

            settled_state = settled_status[
                "State"
            ]

            if settled_state == "SUCCEEDED":
                return query_id

            compensation_safe = (
                settled_state
                in {
                    "FAILED",
                    "CANCELLED",
                }
            )

            raise QuarantinePersistenceError(
                "Quarantine event Athena write "
                "timed out with final state "
                f"{settled_state}.",
                query_id=query_id,
                state=settled_state,
                compensation_safe=(
                    compensation_safe
                ),
            )

        time.sleep(0.2)


def run_quarantine(
    *,
    payload: dict[str, Any],
    s3_client: Any,
    athena_client: Any,
    data_bucket: str,
    database_name: str,
    table_name: str,
    workgroup: str,
    quarantined_at: str | None = None,
    athena_timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    validate_request(
        payload,
        data_bucket=data_bucket,
    )

    target_key = destination_key(
        payload
    )

    destination_uri = (
        f"s3://{data_bucket}/"
        f"{target_key}"
    )

    expected_event_id = event_identifier(
        payload=payload,
        destination_uri=destination_uri,
    )

    prepared = prepare_destination(
        s3_client=s3_client,
        bucket=data_bucket,
        source_key=payload[
            "source_key"
        ],
        target_key=target_key,
        expected_event_id=(
            expected_event_id
        ),
    )

    target = prepared["target"]

    event = build_event(
        payload=payload,
        destination_uri=destination_uri,
        quarantined_at=object_timestamp(
            target=target,
            override=quarantined_at,
        ),
    )

    request_token = athena_request_token(
        event_id=expected_event_id,
        target_identity=object_identity(
            target
        ),
    )

    try:
        query_id = persist_event(
            athena_client=athena_client,
            event=event,
            database_name=database_name,
            table_name=table_name,
            workgroup=workgroup,
            client_request_token=(
                request_token
            ),
            timeout_seconds=(
                athena_timeout_seconds
            ),
        )
    except QuarantinePersistenceError as error:
        if (
            error.compensation_safe
            and prepared["source"]
            is not None
        ):
            compensate_destination(
                s3_client=s3_client,
                bucket=data_bucket,
                target_key=target_key,
            )

        raise

    source_was_present = (
        prepared["source"] is not None
    )

    if source_was_present:
        remove_source(
            s3_client=s3_client,
            bucket=data_bucket,
            source_key=payload[
                "source_key"
            ],
        )

    return {
        "status": "PASS",
        "condition": "C2",
        "terminal_state": (
            "QUARANTINED"
        ),
        "promotion_blocked": True,
        "self_healing_performed": False,
        "automatic_remediation_performed": True,
        "quarantine_event": event,
        "quarantine_object": {
            "uri": destination_uri,
            "content_length": target.get(
                "ContentLength"
            ),
            "etag": target.get("ETag"),
            "source_removed": True,
            "destination_created": (
                prepared[
                    "destination_created"
                ]
            ),
            "idempotent_replay": (
                not source_was_present
            ),
        },
        "athena_query_execution_id": (
            query_id
        ),
    }


def lambda_handler(
    event: dict[str, Any],
    context: Any,
) -> dict[str, Any]:
    import boto3

    data_bucket = os.environ[
        "DATA_LAKE_BUCKET"
    ]

    database_name = os.environ[
        "QUARANTINE_DATABASE"
    ]

    table_name = os.environ.get(
        "QUARANTINE_TABLE",
        "quarantine_events",
    )

    workgroup = os.environ[
        "ATHENA_WORKGROUP"
    ]

    return run_quarantine(
        payload=event,
        s3_client=boto3.client("s3"),
        athena_client=boto3.client(
            "athena"
        ),
        data_bucket=data_bucket,
        database_name=database_name,
        table_name=table_name,
        workgroup=workgroup,
    )
