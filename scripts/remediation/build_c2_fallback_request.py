#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema import FormatChecker


EXPECTED_DATA_BUCKET = (
    "thesis-pac-dev-data-lake-"
    "522814714524-eu-west-1"
)

QUARANTINE_SCENARIOS = {
    "pii_exposure": {
        "fallback_action": "quarantine",
        "policy_id": "PAC-PRIVACY-001",
        "policy_category": "privacy",
    },
    "freshness_breach": {
        "fallback_action": "quarantine",
        "policy_id": "PAC-FRESH-001",
        "policy_category": "freshness",
    },
    "quality_regression": {
        "fallback_action": "quarantine",
        "policy_id": "PAC-QUALITY-001",
        "policy_category": "quality",
    },
}

NON_QUARANTINE_SCENARIOS = {
    "schema_break": {
        "fallback_action": "manual_review",
    },
    "policy_false_positive": {
        "fallback_action": "stop_promotion",
    },
}

ALL_SCENARIOS = {
    **QUARANTINE_SCENARIOS,
    **NON_QUARANTINE_SCENARIOS,
}


class FallbackRequestError(RuntimeError):
    pass


def canonical_bytes(
    value: Any,
) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        + "\n"
    ).encode(
        "utf-8"
    )


def canonical_text(
    value: Any,
) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def sha256_file(
    path: Path,
) -> str:
    digest = hashlib.sha256()

    with path.open(
        "rb"
    ) as handle:
        for chunk in iter(
            lambda: handle.read(
                1024 * 1024
            ),
            b"",
        ):
            digest.update(
                chunk
            )

    return digest.hexdigest()


def load_json(
    path: Path,
) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )
    except (
        OSError,
        json.JSONDecodeError,
    ) as error:
        raise FallbackRequestError(
            f"Unable to load JSON from {path}: {error}"
        ) from error

    if not isinstance(
        value,
        dict,
    ):
        raise FallbackRequestError(
            f"Expected JSON object in {path}."
        )

    return value


def write_json_atomic(
    path: Path,
    value: dict[str, Any],
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    payload = canonical_bytes(
        value
    )

    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(
            path.parent
        ),
    )

    temporary_path = Path(
        temporary
    )

    try:
        with os.fdopen(
            descriptor,
            "wb",
        ) as handle:
            handle.write(
                payload
            )

            handle.flush()

            os.fsync(
                handle.fileno()
            )

        os.replace(
            temporary_path,
            path,
        )

    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def validate_output(
    value: dict[str, Any],
    schema: dict[str, Any],
) -> None:
    validator = Draft202012Validator(
        schema,
        format_checker=FormatChecker(),
    )

    errors = sorted(
        validator.iter_errors(
            value
        ),
        key=lambda error: list(
            error.absolute_path
        ),
    )

    if errors:
        rendered = []

        for error in errors:
            path = "/".join(
                str(component)
                for component
                in error.absolute_path
            )

            rendered.append(
                f"{path or '$'}: {error.message}"
            )

        raise FallbackRequestError(
            "Fallback request failed schema validation: "
            + "; ".join(
                rendered
            )
        )


def require_identity(
    *,
    plan: dict[str, Any],
    result: dict[str, Any],
    verification: dict[str, Any],
) -> tuple[
    str,
    str,
]:
    documents = {
        "plan": plan,
        "result": result,
        "verification": verification,
    }

    for name, document in documents.items():
        if document.get(
            "condition"
        ) != "C2":
            raise FallbackRequestError(
                f"{name} condition must equal C2."
            )

    scenario_id = plan.get(
        "scenario_id"
    )

    run_key = plan.get(
        "run_key"
    )

    if scenario_id not in ALL_SCENARIOS:
        raise FallbackRequestError(
            f"Unsupported C2 scenario: {scenario_id!r}."
        )

    if (
        not isinstance(
            run_key,
            str,
        )
        or not run_key
    ):
        raise FallbackRequestError(
            "Plan run_key must be a non-empty string."
        )

    for name, document in (
        (
            "result",
            result,
        ),
        (
            "verification",
            verification,
        ),
    ):
        if (
            document.get(
                "scenario_id"
            )
            != scenario_id
        ):
            raise FallbackRequestError(
                f"{name} scenario_id does not match plan."
            )

        if (
            document.get(
                "run_key"
            )
            != run_key
        ):
            raise FallbackRequestError(
                f"{name} run_key does not match plan."
            )

    return (
        scenario_id,
        run_key,
    )


def verify_artifact_hashes(
    *,
    plan_path: Path,
    result_path: Path,
    result: dict[str, Any],
    verification: dict[str, Any],
) -> None:
    plan_sha = sha256_file(
        plan_path
    )

    result_sha = sha256_file(
        result_path
    )

    if (
        result.get(
            "source_remediation_plan_sha256"
        )
        != plan_sha
    ):
        raise FallbackRequestError(
            "Result remediation-plan SHA-256 mismatch."
        )

    if (
        verification.get(
            "source_remediation_plan_sha256"
        )
        != plan_sha
    ):
        raise FallbackRequestError(
            "Verification remediation-plan SHA-256 mismatch."
        )

    if (
        verification.get(
            "source_remediation_result_sha256"
        )
        != result_sha
    ):
        raise FallbackRequestError(
            "Verification remediation-result SHA-256 mismatch."
        )


def validate_catalog_alignment(
    *,
    catalog: dict[str, Any],
    scenario_id: str,
    plan: dict[str, Any],
    verification: dict[str, Any],
) -> dict[str, Any]:
    if catalog.get(
        "condition"
    ) != "C2":
        raise FallbackRequestError(
            "Remediation catalog condition must equal C2."
        )

    scenarios = catalog.get(
        "scenarios"
    )

    if not isinstance(
        scenarios,
        dict,
    ):
        raise FallbackRequestError(
            "Catalog scenarios must be an object."
        )

    scenario = scenarios.get(
        scenario_id
    )

    if not isinstance(
        scenario,
        dict,
    ):
        raise FallbackRequestError(
            f"Catalog scenario missing: {scenario_id}."
        )

    plan_body = plan.get(
        "plan"
    )

    if not isinstance(
        plan_body,
        dict,
    ):
        raise FallbackRequestError(
            "Remediation plan.plan must be an object."
        )

    expected_fallback = scenario.get(
        "fallback_action"
    )

    if (
        expected_fallback
        != ALL_SCENARIOS[
            scenario_id
        ][
            "fallback_action"
        ]
    ):
        raise FallbackRequestError(
            "Catalog fallback action differs from "
            "locked C2 fallback architecture."
        )

    checks = {
        "primary_action":
            scenario.get(
                "primary_action"
            ),

        "fallback_action":
            expected_fallback,

        "max_attempts":
            scenario.get(
                "max_attempts"
            ),
    }

    for field, expected in checks.items():
        if (
            plan_body.get(
                field
            )
            != expected
        ):
            raise FallbackRequestError(
                f"Plan {field} does not match catalog."
            )

    recommended = verification.get(
        "recommended_fallback_action"
    )

    if recommended != expected_fallback:
        raise FallbackRequestError(
            "Verifier recommended fallback action "
            "does not match catalog."
        )

    if (
        verification.get(
            "promotion_blocked"
        )
        is not True
    ):
        raise FallbackRequestError(
            "Fallback requires promotion_blocked=true."
        )

    if (
        verification.get(
            "verified_result_emitted"
        )
        is True
    ):
        raise FallbackRequestError(
            "Fallback is forbidden after a verified "
            "recovery result has been emitted."
        )

    if (
        verification.get(
            "verification_status"
        )
        == "PASS"
    ):
        raise FallbackRequestError(
            "Fallback is forbidden after verification PASS."
        )

    return scenario


def value_contains(
    value: Any,
    expected: str,
) -> bool:
    if value == expected:
        return True

    if isinstance(
        value,
        dict,
    ):
        return any(
            value_contains(
                child,
                expected,
            )
            for child in value.values()
        )

    if isinstance(
        value,
        list,
    ):
        return any(
            value_contains(
                child,
                expected,
            )
            for child in value
        )

    return False


def select_policy_violation(
    *,
    scenario_id: str,
    verification: dict[str, Any],
) -> tuple[
    str,
    str,
    str,
    str,
]:
    contract = QUARANTINE_SCENARIOS[
        scenario_id
    ]

    policy_id = contract[
        "policy_id"
    ]

    policy_category = contract[
        "policy_category"
    ]

    triggered = verification.get(
        "triggered_policy_ids"
    )

    if not isinstance(
        triggered,
        list,
    ):
        raise FallbackRequestError(
            "Verification triggered_policy_ids "
            "must be an array."
        )

    if policy_id not in triggered:
        raise FallbackRequestError(
            f"Expected blocking policy {policy_id} "
            "is absent from verification."
        )

    violations = verification.get(
        "violations"
    )

    if not isinstance(
        violations,
        list,
    ):
        raise FallbackRequestError(
            "Verification violations must be an array."
        )

    matching = [
        violation
        for violation in violations
        if (
            isinstance(
                violation,
                dict,
            )
            and value_contains(
                violation,
                policy_id,
            )
        )
    ]

    if len(
        matching
    ) != 1:
        raise FallbackRequestError(
            "Expected exactly one verification "
            f"violation associated with {policy_id}; "
            f"observed {len(matching)}."
        )

    violation = matching[
        0
    ]

    return (
        policy_id,
        policy_category,
        policy_id,
        canonical_text(
            violation
        ),
    )


def validate_source_context(
    context: dict[str, Any],
) -> None:
    required = {
        "data_classification",
        "evidence_uri",
        "source_bucket",
        "source_dataset",
        "source_key",
        "source_relation",
    }

    missing = sorted(
        required
        - context.keys()
    )

    if missing:
        raise FallbackRequestError(
            "Missing quarantine context fields: "
            + ", ".join(
                missing
            )
        )

    for field in (
        "data_classification",
        "evidence_uri",
        "source_dataset",
        "source_relation",
    ):
        value = context.get(
            field
        )

        if (
            not isinstance(
                value,
                str,
            )
            or not value.strip()
        ):
            raise FallbackRequestError(
                f"{field} must be a non-empty string."
            )

    if (
        context.get(
            "source_bucket"
        )
        != EXPECTED_DATA_BUCKET
    ):
        raise FallbackRequestError(
            "source_bucket must equal the dedicated "
            "thesis development data-lake bucket."
        )

    source_key = context.get(
        "source_key"
    )

    if (
        not isinstance(
            source_key,
            str,
        )
        or not source_key.startswith(
            "experiments/c2/"
        )
    ):
        raise FallbackRequestError(
            "source_key must remain under experiments/c2/."
        )

    if ".." in Path(
        source_key
    ).parts:
        raise FallbackRequestError(
            "source_key parent traversal is forbidden."
        )


def build_fallback_request(
    *,
    plan_path: Path,
    result_path: Path,
    verification_path: Path,
    catalog_path: Path,
    schema_path: Path,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    plan = load_json(
        plan_path
    )

    result = load_json(
        result_path
    )

    verification = load_json(
        verification_path
    )

    catalog = load_json(
        catalog_path
    )

    schema = load_json(
        schema_path
    )

    (
        scenario_id,
        run_key,
    ) = require_identity(
        plan=plan,
        result=result,
        verification=verification,
    )

    verify_artifact_hashes(
        plan_path=plan_path,
        result_path=result_path,
        result=result,
        verification=verification,
    )

    scenario = validate_catalog_alignment(
        catalog=catalog,
        scenario_id=scenario_id,
        plan=plan,
        verification=verification,
    )

    fallback_action = scenario[
        "fallback_action"
    ]

    output: dict[str, Any] = {
        "condition": "C2",
        "scenario_id": scenario_id,
        "fallback_action": fallback_action,
        "run_key": run_key,
    }

    if fallback_action != "quarantine":
        validate_output(
            output,
            schema,
        )

        return output

    if scenario_id not in QUARANTINE_SCENARIOS:
        raise FallbackRequestError(
            "Quarantine fallback is not permitted "
            f"for scenario {scenario_id}."
        )

    if context is None:
        raise FallbackRequestError(
            "Quarantine fallback requires "
            "controlled current-run context."
        )

    validate_source_context(
        context
    )

    plan_body = plan[
        "plan"
    ]

    max_retries = plan_body.get(
        "max_attempts"
    )

    retry_count = result.get(
        "attempt_count"
    )

    if (
        not isinstance(
            max_retries,
            int,
        )
        or isinstance(
            max_retries,
            bool,
        )
        or not (
            1
            <= max_retries
            <= 2
        )
    ):
        raise FallbackRequestError(
            "Quarantine max_retries must be "
            "a primary-remediation budget of 1..2."
        )

    if (
        not isinstance(
            retry_count,
            int,
        )
        or isinstance(
            retry_count,
            bool,
        )
        or not (
            1
            <= retry_count
            <= max_retries
        )
    ):
        raise FallbackRequestError(
            "Quarantine retry_count must represent "
            "1..max_retries primary-remediation attempts "
            "consumed before fallback."
        )

    if (
        result.get(
            "automatic_remediation_performed"
        )
        is not True
    ):
        raise FallbackRequestError(
            "Quarantine workflow fallback requires "
            "an attempted automatic primary remediation."
        )

    (
        policy_id,
        policy_category,
        violation_code,
        violation_details,
    ) = select_policy_violation(
        scenario_id=scenario_id,
        verification=verification,
    )

    detected_at = plan.get(
        "fault_detected_at_utc"
    )

    if (
        not isinstance(
            detected_at,
            str,
        )
        or not detected_at
    ):
        raise FallbackRequestError(
            "Plan fault_detected_at_utc is missing."
        )

    output[
        "quarantine_request"
    ] = {
        "data_classification":
            context[
                "data_classification"
            ],

        "detected_at":
            detected_at,

        "evidence_uri":
            context[
                "evidence_uri"
            ],

        "max_retries":
            max_retries,

        "policy_category":
            policy_category,

        "policy_id":
            policy_id,

        "retry_count":
            retry_count,

        "source_bucket":
            context[
                "source_bucket"
            ],

        "source_dataset":
            context[
                "source_dataset"
            ],

        "source_key":
            context[
                "source_key"
            ],

        "source_relation":
            context[
                "source_relation"
            ],

        "violation_code":
            violation_code,

        "violation_details":
            violation_details,
    }

    validate_output(
        output,
        schema,
    )

    return output


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build deterministic C2 Step Functions "
            "fallback execution input."
        )
    )

    parser.add_argument(
        "--plan",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--result",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--verification",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--catalog",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--schema",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--output",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--data-classification",
    )

    parser.add_argument(
        "--evidence-uri",
    )

    parser.add_argument(
        "--source-bucket",
    )

    parser.add_argument(
        "--source-dataset",
    )

    parser.add_argument(
        "--source-key",
    )

    parser.add_argument(
        "--source-relation",
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    values = {
        "data_classification":
            args.data_classification,

        "evidence_uri":
            args.evidence_uri,

        "source_bucket":
            args.source_bucket,

        "source_dataset":
            args.source_dataset,

        "source_key":
            args.source_key,

        "source_relation":
            args.source_relation,
    }

    context = {
        key: value
        for key, value in values.items()
        if value is not None
    }

    try:
        output = build_fallback_request(
            plan_path=args.plan,
            result_path=args.result,
            verification_path=args.verification,
            catalog_path=args.catalog,
            schema_path=args.schema,
            context=(
                context
                if context
                else None
            ),
        )

        write_json_atomic(
            args.output,
            output,
        )

    except FallbackRequestError as error:
        print(
            f"ERROR: {error}"
        )

        return 1

    print(
        json.dumps(
            output,
            indent=2,
            sort_keys=True,
        )
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
