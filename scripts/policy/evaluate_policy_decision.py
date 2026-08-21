#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


CORE_VIOLATION_FIELDS = {
    "policy_id",
    "category",
    "severity",
    "reason",
}


class EvaluationError(RuntimeError):
    pass


def load_json(path: Path) -> Any:
    return json.loads(
        path.read_text(
            encoding="utf-8",
        )
    )


def sha256_file(path: Path) -> str:
    return hashlib.sha256(
        path.read_bytes()
    ).hexdigest()


def validate_document(
    schema: dict[str, Any],
    document: Any,
    label: str,
) -> None:
    Draft202012Validator.check_schema(
        schema
    )

    validator = Draft202012Validator(
        schema,
        format_checker=FormatChecker(),
    )

    errors = sorted(
        validator.iter_errors(document),
        key=lambda error: list(
            error.absolute_path
        ),
    )

    if not errors:
        return

    formatted = []

    for error in errors:
        location = "/".join(
            str(part)
            for part in error.absolute_path
        )

        formatted.append(
            f"{location or '$'}: "
            f"{error.message}"
        )

    raise EvaluationError(
        f"{label} validation failed: "
        + " | ".join(formatted)
    )


def policy_records(
    catalog: Any,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            policy_id = value.get(
                "policy_id"
            )

            if isinstance(
                policy_id,
                str,
            ):
                records.append(value)

            for child in value.values():
                walk(child)

        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(catalog)

    return sorted(
        records,
        key=lambda item: item[
            "policy_id"
        ],
    )


def rego_files(
    policy_dir: Path,
) -> list[Path]:
    files = sorted(
        policy_dir.glob("*.rego"),
        key=lambda path: path.name,
    )

    if not files:
        raise EvaluationError(
            "No Rego policy files found"
        )

    return files


def relative_path(
    path: Path,
    repo_root: Path,
) -> str:
    return path.resolve().relative_to(
        repo_root.resolve()
    ).as_posix()


def policy_bundle_sha256(
    repo_root: Path,
    catalog_path: Path,
    input_schema_path: Path,
    policies: list[Path],
) -> str:
    components = [
        catalog_path,
        input_schema_path,
        *policies,
    ]

    lines = []

    for path in components:
        lines.append(
            f"{sha256_file(path)}  "
            f"{relative_path(path, repo_root)}"
            "\n"
        )

    payload = "".join(lines).encode(
        "utf-8"
    )

    return hashlib.sha256(
        payload
    ).hexdigest()


def opa_value(
    payload: dict[str, Any],
) -> Any:
    try:
        return payload[
            "result"
        ][0][
            "expressions"
        ][0][
            "value"
        ]
    except (
        KeyError,
        IndexError,
        TypeError,
    ) as exc:
        raise EvaluationError(
            "OPA result did not contain "
            "a query value"
        ) from exc


def evaluate_opa(
    opa_bin: Path,
    input_path: Path,
    policies: list[Path],
) -> tuple[
    bool,
    list[dict[str, Any]],
    float,
]:
    query = (
        '{"allow": data.thesis.pac.allow, '
        '"violations": data.thesis.pac.violations}'
    )

    command = [
        str(opa_bin),
        "eval",
        "--format=json",
    ]

    for policy in policies:
        command.extend(
            [
                "--data",
                str(policy),
            ]
        )

    command.extend(
        [
            "--input",
            str(input_path),
            query,
        ]
    )

    started = time.perf_counter_ns()

    process = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
    )

    finished = time.perf_counter_ns()

    evaluation_ms = round(
        (
            finished
            - started
        )
        / 1_000_000,
        3,
    )

    if process.returncode != 0:
        raise EvaluationError(
            "OPA evaluation failed: "
            + process.stderr.strip()
        )

    payload = json.loads(
        process.stdout
    )

    result = opa_value(payload)

    if not isinstance(
        result,
        dict,
    ):
        raise EvaluationError(
            "OPA combined result is not "
            "an object"
        )

    allow = result.get("allow")
    violations = result.get(
        "violations"
    )

    if not isinstance(
        allow,
        bool,
    ):
        raise EvaluationError(
            "OPA allow result is not boolean"
        )

    if not isinstance(
        violations,
        list,
    ):
        raise EvaluationError(
            "OPA violations result is not "
            "an array"
        )

    for violation in violations:
        if not isinstance(
            violation,
            dict,
        ):
            raise EvaluationError(
                "OPA violation is not "
                "an object"
            )

    return (
        allow,
        violations,
        evaluation_ms,
    )


def normalize_violations(
    violations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    normalized = []

    for violation in violations:
        missing = (
            CORE_VIOLATION_FIELDS
            - set(violation)
        )

        if missing:
            raise EvaluationError(
                "Violation missing common "
                f"fields: {sorted(missing)}"
            )

        details = {
            key: value
            for key, value
            in violation.items()
            if key
            not in CORE_VIOLATION_FIELDS
        }

        normalized.append(
            {
                "policy_id": violation[
                    "policy_id"
                ],
                "category": violation[
                    "category"
                ],
                "severity": violation[
                    "severity"
                ],
                "reason": violation[
                    "reason"
                ],
                "details": details,
            }
        )

    return sorted(
        normalized,
        key=lambda item: (
            item["policy_id"],
            item["reason"],
            json.dumps(
                item["details"],
                sort_keys=True,
                separators=(",", ":"),
            ),
        ),
    )


def build_policy_outcomes(
    records: list[dict[str, Any]],
    normalized_violations: list[
        dict[str, Any]
    ],
    evaluation_stage: str,
) -> tuple[
    list[dict[str, Any]],
    list[str],
    list[str],
]:
    implemented = [
        record
        for record in records
        if record.get(
            "implemented"
        ) is True
    ]

    unimplemented = [
        record
        for record in records
        if record.get(
            "implemented"
        ) is False
    ]

    by_policy: dict[
        str,
        list[dict[str, Any]],
    ] = {}

    for violation in normalized_violations:
        policy_id = violation[
            "policy_id"
        ]

        by_policy.setdefault(
            policy_id,
            [],
        ).append(violation)

    implemented_ids = {
        record["policy_id"]
        for record in implemented
    }

    unknown = (
        set(by_policy)
        - implemented_ids
    )

    if unknown:
        raise EvaluationError(
            "OPA emitted violations for "
            "non-implemented or unknown "
            f"policies: {sorted(unknown)}"
        )

    outcomes = []

    for record in implemented:
        policy_id = record["policy_id"]

        stages = record.get(
            "evaluation_stages"
        ) or []

        applicable = (
            evaluation_stage
            in stages
        )

        policy_violations = by_policy.get(
            policy_id,
            [],
        )

        if (
            policy_violations
            and not applicable
        ):
            raise EvaluationError(
                f"{policy_id} emitted a "
                "violation outside its "
                "catalog evaluation stage"
            )

        if not applicable:
            outcome = "NOT_APPLICABLE"
        elif policy_violations:
            outcome = "DENY"
        else:
            outcome = "PASS"

        reasons = sorted({
            item["reason"]
            for item
            in policy_violations
        })

        outcomes.append(
            {
                "policy_id": policy_id,
                "title": record["title"],
                "category": record[
                    "category"
                ],
                "severity": record[
                    "severity"
                ],
                "applicable": applicable,
                "outcome": outcome,
                "violation_count": len(
                    policy_violations
                ),
                "reasons": reasons,
            }
        )

    return (
        outcomes,
        sorted(
            record["policy_id"]
            for record in implemented
        ),
        sorted(
            record["policy_id"]
            for record
            in unimplemented
        ),
    )


def build_decision(
    input_document: dict[str, Any],
    allow: bool,
    normalized_violations: list[
        dict[str, Any]
    ],
    outcomes: list[dict[str, Any]],
    implemented_policy_ids: list[str],
    unimplemented_policy_ids: list[str],
    evaluation_ms: float,
    input_sha256: str,
    bundle_sha256: str,
) -> dict[str, Any]:
    decision = (
        "ALLOW"
        if allow
        else "DENY"
    )

    if allow != (
        len(normalized_violations) == 0
    ):
        raise EvaluationError(
            "OPA allow/violation state is "
            "internally inconsistent"
        )

    triggered_policy_ids = sorted({
        item["policy_id"]
        for item
        in normalized_violations
    })

    applicable_policy_count = sum(
        1
        for outcome in outcomes
        if outcome["applicable"]
    )

    denied_policy_count = sum(
        1
        for outcome in outcomes
        if outcome["outcome"]
        == "DENY"
    )

    promotion_requested = (
        input_document[
            "release"
        ][
            "promotion_requested"
        ]
    )

    promotion_blocked = bool(
        promotion_requested
        and not allow
    )

    return {
        "schema_version": "1.0.0",
        "recorded_at_utc": (
            datetime.now(
                timezone.utc
            )
            .isoformat()
            .replace(
                "+00:00",
                "Z",
            )
        ),
        "condition": input_document[
            "experiment"
        ][
            "condition"
        ],
        "run_key": input_document[
            "experiment"
        ][
            "run_key"
        ],
        "scenario_id": input_document[
            "experiment"
        ][
            "scenario_id"
        ],
        "evaluation_stage": (
            input_document[
                "evaluation_stage"
            ]
        ),
        "git": {
            "branch": input_document[
                "git"
            ][
                "branch"
            ],
            "commit": input_document[
                "git"
            ][
                "commit"
            ],
        },
        "controls": {
            "policy_as_code_required": (
                input_document[
                    "controls"
                ][
                    "policy_as_code_required"
                ]
            ),
            "self_healing_permitted": (
                input_document[
                    "controls"
                ][
                    "self_healing_permitted"
                ]
            ),
            "automatic_remediation_permitted": (
                input_document[
                    "controls"
                ][
                    "automatic_remediation_permitted"
                ]
            ),
        },
        "promotion_requested": (
            promotion_requested
        ),
        "decision": decision,
        "allow": allow,
        "violation_count": len(
            normalized_violations
        ),
        "triggered_policy_ids": (
            triggered_policy_ids
        ),
        "violations": (
            normalized_violations
        ),
        "policy_outcomes": outcomes,
        "implemented_policy_ids": (
            implemented_policy_ids
        ),
        "unimplemented_policy_ids": (
            unimplemented_policy_ids
        ),
        "evaluation_ms": evaluation_ms,
        "input_sha256": input_sha256,
        "policy_bundle_sha256": (
            bundle_sha256
        ),
        "measurement": {
            "policy_evaluation_ms": (
                evaluation_ms
            ),
            "violation_count": len(
                normalized_violations
            ),
            "applicable_policy_count": (
                applicable_policy_count
            ),
            "denied_policy_count": (
                denied_policy_count
            ),
            "promotion_requested": (
                promotion_requested
            ),
            "promotion_blocked": (
                promotion_blocked
            ),
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Evaluate normalized C1 policy "
            "input and emit one durable "
            "policy decision artifact."
        )
    )

    parser.add_argument(
        "--input",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--output",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--opa-bin",
        required=True,
        type=Path,
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    repo_root = (
        Path(__file__)
        .resolve()
        .parents[2]
    )

    catalog_path = (
        repo_root
        / "policies/catalog/policy-catalog.json"
    )

    input_schema_path = (
        repo_root
        / "policies/contracts/policy-input.schema.json"
    )

    decision_schema_path = (
        repo_root
        / "policies/contracts/policy-decision.schema.json"
    )

    policy_dir = (
        repo_root
        / "policies/rego"
    )

    try:
        if not args.opa_bin.is_file():
            raise EvaluationError(
                "OPA binary does not exist: "
                f"{args.opa_bin}"
            )

        input_document = load_json(
            args.input
        )

        input_schema = load_json(
            input_schema_path
        )

        decision_schema = load_json(
            decision_schema_path
        )

        catalog = load_json(
            catalog_path
        )

        validate_document(
            input_schema,
            input_document,
            "Policy input",
        )

        records = policy_records(
            catalog
        )

        policies = rego_files(
            policy_dir
        )

        bundle_sha = (
            policy_bundle_sha256(
                repo_root,
                catalog_path,
                input_schema_path,
                policies,
            )
        )

        (
            allow,
            raw_violations,
            evaluation_ms,
        ) = evaluate_opa(
            args.opa_bin,
            args.input,
            policies,
        )

        normalized = (
            normalize_violations(
                raw_violations
            )
        )

        (
            outcomes,
            implemented_ids,
            unimplemented_ids,
        ) = build_policy_outcomes(
            records,
            normalized,
            input_document[
                "evaluation_stage"
            ],
        )

        decision = build_decision(
            input_document,
            allow,
            normalized,
            outcomes,
            implemented_ids,
            unimplemented_ids,
            evaluation_ms,
            sha256_file(
                args.input
            ),
            bundle_sha,
        )

        validate_document(
            decision_schema,
            decision,
            "Policy decision",
        )

        args.output.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        rendered = json.dumps(
            decision,
            indent=2,
            sort_keys=True,
        ) + "\n"

        args.output.write_text(
            rendered,
            encoding="utf-8",
        )

        sys.stdout.write(
            rendered
        )

        return (
            0
            if allow
            else 2
        )

    except (
        EvaluationError,
        json.JSONDecodeError,
        OSError,
        ValueError,
    ) as exc:
        print(
            f"ERROR: {exc}",
            file=sys.stderr,
        )

        return 1


if __name__ == "__main__":
    raise SystemExit(main())
