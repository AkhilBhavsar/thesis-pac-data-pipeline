#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


EXPECTED_BRANCH = (
    "feature/c2-bounded-self-healing"
)

EXPECTED_CONDITION = "C2"

EXPECTED_SCENARIO = (
    "freshness_breach"
)

SCHEMA_PREFIX = (
    "thesis_pac_c2_"
)


class RetryAdapterError(RuntimeError):
    pass


def utc_now() -> str:
    return (
        datetime.now(
            timezone.utc
        )
        .isoformat()
        .replace(
            "+00:00",
            "Z",
        )
    )


def safe_run_key(
    value: str,
) -> str:
    normalized = re.sub(
        r"[^a-z0-9_]+",
        "_",
        value.lower(),
    ).strip("_")

    if not normalized:
        raise RetryAdapterError(
            "C2 run key is empty after "
            "normalization."
        )

    return normalized


def required(
    environ: Mapping[str, str],
    name: str,
) -> str:
    value = environ.get(
        name,
        "",
    ).strip()

    if not value:
        raise RetryAdapterError(
            f"Required environment variable "
            f"is missing: {name}"
        )

    return value


def validate_environment(
    environ: Mapping[str, str],
) -> dict[str, Any]:
    branch = required(
        environ,
        "THESIS_GIT_BRANCH",
    )

    commit = required(
        environ,
        "THESIS_GIT_COMMIT",
    )

    condition = required(
        environ,
        "THESIS_EXPERIMENT_CONDITION",
    )

    scenario = required(
        environ,
        "THESIS_SCENARIO_ID",
    )

    run_key = required(
        environ,
        "C2_RUN_KEY",
    )

    account_id = required(
        environ,
        "AWS_ACCOUNT_ID",
    )

    data_bucket = required(
        environ,
        "DATA_LAKE_BUCKET",
    )

    results_bucket = required(
        environ,
        "ATHENA_RESULTS_BUCKET",
    )

    workgroup = required(
        environ,
        "DBT_ATHENA_WORKGROUP",
    )

    data_root_uri = required(
        environ,
        "DBT_ATHENA_DATA_DIR",
    )

    results_root_uri = required(
        environ,
        "DBT_ATHENA_STAGING_DIR",
    )

    schemas = {
        "silver": required(
            environ,
            "DBT_ATHENA_SCHEMA",
        ),
        "gold_internal": required(
            environ,
            "DBT_GOLD_INTERNAL_SCHEMA",
        ),
        "gold_public": required(
            environ,
            "DBT_GOLD_PUBLIC_SCHEMA",
        ),
    }

    if branch != EXPECTED_BRANCH:
        raise RetryAdapterError(
            f"Unexpected C2 branch: {branch}"
        )

    if condition != EXPECTED_CONDITION:
        raise RetryAdapterError(
            f"Unexpected condition: "
            f"{condition}"
        )

    if scenario != EXPECTED_SCENARIO:
        raise RetryAdapterError(
            f"Unexpected retry scenario: "
            f"{scenario}"
        )

    if len(
        set(
            schemas.values()
        )
    ) != 3:
        raise RetryAdapterError(
            "C2 retry shadow schemas "
            "must be unique."
        )

    if not all(
        value.startswith(
            SCHEMA_PREFIX
        )
        for value
        in schemas.values()
    ):
        raise RetryAdapterError(
            "C2 retry schemas escaped "
            "the thesis_pac_c2_ boundary."
        )

    expected_data_root = (
        f"s3://{data_bucket}/"
        "experiments/c2/"
    )

    expected_results_root = (
        f"s3://{results_bucket}/"
        "experiments/c2/"
    )

    if not data_root_uri.startswith(
        expected_data_root
    ):
        raise RetryAdapterError(
            "C2 retry data root escaped "
            "the experiments/c2 boundary."
        )

    if not results_root_uri.startswith(
        expected_results_root
    ):
        raise RetryAdapterError(
            "C2 retry Athena root escaped "
            "the experiments/c2 boundary."
        )

    return {
        "branch": branch,
        "commit": commit,
        "condition": condition,
        "scenario": scenario,
        "run_key": run_key,
        "safe_run_key": safe_run_key(
            run_key
        ),
        "account_id": account_id,
        "data_bucket": data_bucket,
        "results_bucket": results_bucket,
        "workgroup": workgroup,
        "data_root_uri": data_root_uri,
        "results_root_uri": (
            results_root_uri
        ),
        "schemas": schemas,
    }


def validate_invocation(
    *,
    plan: dict[str, Any],
    context: dict[str, Any],
    attempt_number: int,
) -> None:
    if plan.get(
        "condition"
    ) != "C2":
        raise RetryAdapterError(
            "Retry adapter accepts only "
            "C2 remediation plans."
        )

    if plan.get(
        "scenario_id"
    ) != EXPECTED_SCENARIO:
        raise RetryAdapterError(
            "Real retry adapter is reserved "
            "for freshness_breach."
        )

    plan_body = plan.get(
        "plan",
        {},
    )

    if plan_body.get(
        "mode"
    ) != "automatic":
        raise RetryAdapterError(
            "Retry requires automatic mode."
        )

    if plan_body.get(
        "primary_action"
    ) != "retry":
        raise RetryAdapterError(
            "Retry adapter requires "
            "primary_action=retry."
        )

    maximum = plan_body.get(
        "max_attempts"
    )

    if (
        not isinstance(
            maximum,
            int,
        )
        or isinstance(
            maximum,
            bool,
        )
        or maximum < 1
    ):
        raise RetryAdapterError(
            "Retry plan has invalid "
            "attempt bound."
        )

    if (
        attempt_number < 1
        or attempt_number > maximum
    ):
        raise RetryAdapterError(
            "Retry attempt exceeds "
            "the bounded plan."
        )

    if context.get(
        "condition"
    ) != "C2":
        raise RetryAdapterError(
            "Retry context must be C2."
        )

    if (
        context.get(
            "scenario_id"
        )
        != EXPECTED_SCENARIO
    ):
        raise RetryAdapterError(
            "Retry context scenario mismatch."
        )

    if (
        context.get(
            "run_key"
        )
        != plan.get(
            "run_key"
        )
    ):
        raise RetryAdapterError(
            "Retry plan/context run-key "
            "mismatch."
        )

    workspace = context.get(
        "workspace",
        {},
    )

    if workspace.get(
        "isolated"
    ) is not True:
        raise RetryAdapterError(
            "Retry requires isolated workspace."
        )

    if workspace.get(
        "canonical_access_permitted"
    ) is not False:
        raise RetryAdapterError(
            "Canonical access must remain "
            "forbidden during retry."
        )

    action_context = context.get(
        "action_context",
        {},
    )

    if (
        action_context.get(
            "action"
        )
        != "retry"
    ):
        raise RetryAdapterError(
            "Retry execution context action "
            "mismatch."
        )

    if (
        action_context.get(
            "runner_profile"
        )
        != "c2_isolated_pipeline"
    ):
        raise RetryAdapterError(
            "Retry runner profile is "
            "not allow-listed."
        )


def write_json(
    path: Path,
    payload: Any,
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_text(
        json.dumps(
            payload,
            indent=2,
            sort_keys=True,
            default=str,
        )
        + "\n",
        encoding="utf-8",
    )


def sha256_file(
    path: Path,
) -> str:
    return hashlib.sha256(
        path.read_bytes()
    ).hexdigest()


def local_checksums(
    root: Path,
) -> str:
    files = sorted(
        target
        for target
        in root.rglob("*")
        if (
            target.is_file()
            and target.name
            != "SHA256SUMS"
        )
    )

    lines = []

    for target in files:
        lines.append(
            f"{sha256_file(target)}  "
            f"{target.relative_to(root).as_posix()}"
        )

    manifest = (
        root
        / "SHA256SUMS"
    )

    manifest.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )

    return sha256_file(
        manifest
    )


def c2_isolated_retry_runner(
    plan: dict[str, Any],
    context: dict[str, Any],
    attempt_number: int,
) -> bool:
    validate_invocation(
        plan=plan,
        context=context,
        attempt_number=attempt_number,
    )

    config = validate_environment(
        os.environ
    )

    if (
        config[
            "run_key"
        ]
        != plan[
            "run_key"
        ]
    ):
        raise RetryAdapterError(
            "C2_RUN_KEY does not match "
            "the remediation plan."
        )

    workspace_root = Path(
        context[
            "workspace"
        ][
            "root"
        ]
    ).expanduser().resolve()

    evidence_root = (
        workspace_root
        / "retry-evidence"
        / (
            f"attempt-"
            f"{attempt_number:02d}"
        )
    )

    if (
        evidence_root.exists()
        and any(
            evidence_root.iterdir()
        )
    ):
        raise RetryAdapterError(
            "Retry-attempt evidence directory "
            "must begin empty."
        )

    evidence_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    write_json(
        evidence_root
        / "retry-context.json",
        {
            "status": "RUNNING",
            "recorded_at_utc": utc_now(),
            "condition": "C2",
            "scenario": (
                EXPECTED_SCENARIO
            ),
            "run_key": plan[
                "run_key"
            ],
            "attempt_number": (
                attempt_number
            ),
            "maximum_attempts": plan[
                "plan"
            ][
                "max_attempts"
            ],
            "branch": config[
                "branch"
            ],
            "commit": config[
                "commit"
            ],
            "schemas": config[
                "schemas"
            ],
            "data_root_uri": config[
                "data_root_uri"
            ],
            "results_root_uri": config[
                "results_root_uri"
            ],
            "policy_as_code_active": True,
            "self_healing_active": True,
            "automatic_remediation_active": True,
            "canonical_access_permitted": False,
        },
    )

    try:
        import boto3

        from scripts.github_actions import (
            run_c1_isolated
            as shared
        )

        repository_root = (
            Path(__file__)
            .resolve()
            .parents[2]
        )

        sts = boto3.client(
            "sts"
        )

        glue = boto3.client(
            "glue"
        )

        s3 = boto3.client(
            "s3"
        )

        athena = boto3.client(
            "athena"
        )

        identity = (
            sts.get_caller_identity()
        )

        if (
            identity.get(
                "Account"
            )
            != config[
                "account_id"
            ]
        ):
            raise RetryAdapterError(
                "AWS account does not match "
                "the C2 retry environment."
            )

        write_json(
            evidence_root
            / "caller-identity.json",
            {
                "status": "PASS",
                "account": identity.get(
                    "Account"
                ),
                "arn": identity.get(
                    "Arn"
                ),
                "permanent_access_keys": False,
            },
        )

        before = (
            shared.canonical_snapshot(
                glue=glue,
                s3=s3,
                data_bucket=config[
                    "data_bucket"
                ],
            )
        )

        write_json(
            evidence_root
            / "canonical-before.json",
            before,
        )

        targets_before = (
            shared.snapshot_dagster_dbt_targets(
                repository_root=(
                    repository_root
                )
            )
        )

        execution_started = (
            datetime.now(
                timezone.utc
            )
        )

        from thesis_orchestration import defs

        job = defs.resolve_job_def(
            "bronze_silver_gold_job"
        )

        result = job.execute_in_process(
            raise_on_error=False
        )

        execution_completed = (
            datetime.now(
                timezone.utc
            )
        )

        after = (
            shared.canonical_snapshot(
                glue=glue,
                s3=s3,
                data_bucket=config[
                    "data_bucket"
                ],
            )
        )

        write_json(
            evidence_root
            / "canonical-after.json",
            after,
        )

        canonical_changed = (
            before[
                "sha256"
            ]
            != after[
                "sha256"
            ]
        )

        write_json(
            evidence_root
            / "canonical-comparison.json",
            {
                "status": (
                    "FAIL"
                    if canonical_changed
                    else "PASS"
                ),
                "before_sha256": (
                    before[
                        "sha256"
                    ]
                ),
                "after_sha256": (
                    after[
                        "sha256"
                    ]
                ),
                "changed": (
                    canonical_changed
                ),
            },
        )

        if canonical_changed:
            raise RetryAdapterError(
                "Canonical Silver or Gold "
                "changed during C2 retry."
            )

        if not result.success:
            raise RetryAdapterError(
                "C2 isolated Dagster retry "
                "reported failure."
            )

        dbt_target = (
            shared.resolve_dagster_dbt_target(
                repository_root=(
                    repository_root
                ),
                targets_before=(
                    targets_before
                ),
            )
        )

        dbt_summary = (
            shared.validate_dbt_results(
                dbt_target
                / "run_results.json"
            )
        )

        write_json(
            evidence_root
            / "dbt-summary.json",
            dbt_summary,
        )

        shared.copy_dbt_artifacts(
            repository_root=(
                repository_root
            ),
            evidence_root=(
                evidence_root
            ),
            dbt_target_path=(
                dbt_target
            ),
        )

        inventory = (
            shared.shadow_inventory(
                glue=glue,
                s3=s3,
                data_bucket=config[
                    "data_bucket"
                ],
                results_bucket=config[
                    "results_bucket"
                ],
                data_root_uri=config[
                    "data_root_uri"
                ],
                results_root_uri=config[
                    "results_root_uri"
                ],
                schemas=config[
                    "schemas"
                ],
            )
        )

        write_json(
            evidence_root
            / "isolated-inventory.json",
            inventory,
        )

        query_inventory = (
            shared.athena_query_inventory(
                athena=athena,
                workgroup=config[
                    "workgroup"
                ],
                started_at=(
                    execution_started
                ),
                completed_at=(
                    execution_completed
                ),
                schema_names=(
                    config[
                        "schemas"
                    ].values()
                ),
            )
        )

        write_json(
            evidence_root
            / "athena-query-inventory.json",
            query_inventory,
        )

        checkpoint = {
            "status": "PASS",
            "checkpoint": (
                "C2_ISOLATED_RETRY_ATTEMPT"
            ),
            "condition": "C2",
            "scenario": (
                EXPECTED_SCENARIO
            ),
            "run_key": plan[
                "run_key"
            ],
            "attempt_number": (
                attempt_number
            ),
            "maximum_attempts": plan[
                "plan"
            ][
                "max_attempts"
            ],
            "dagster": {
                "job": (
                    "bronze_silver_gold_job"
                ),
                "success": True,
                "run_id": getattr(
                    result,
                    "run_id",
                    None,
                ),
            },
            "dbt": {
                "status": (
                    dbt_summary.get(
                        "status"
                    )
                ),
                "failures": 0,
            },
            "isolated_outputs": {
                "total_tables": (
                    inventory.get(
                        "total_tables"
                    )
                ),
                "data_root": config[
                    "data_root_uri"
                ],
                "results_root": config[
                    "results_root_uri"
                ],
            },
            "canonical_protection": {
                "changed": False,
                "before_sha256": before[
                    "sha256"
                ],
                "after_sha256": after[
                    "sha256"
                ],
            },
            "self_healing_claimed": False,
            "verification_pending": True,
        }

        write_json(
            evidence_root
            / "final-checkpoint.json",
            checkpoint,
        )

        manifest_sha = (
            shared.create_checksums(
                evidence_root
            )
        )

        print(
            "C2 isolated retry attempt "
            f"{attempt_number}: PASS"
        )

        print(
            "Evidence manifest SHA-256: "
            f"{manifest_sha}"
        )

        return True

    except BaseException as exc:
        write_json(
            evidence_root
            / "failure.json",
            {
                "status": "FAIL",
                "recorded_at_utc": utc_now(),
                "condition": "C2",
                "scenario": (
                    EXPECTED_SCENARIO
                ),
                "attempt_number": (
                    attempt_number
                ),
                "error_type": (
                    type(exc).__name__
                ),
                "error": str(exc),
                "traceback": (
                    traceback.format_exc()
                ),
                "canonical_mutation_claimed": False,
                "self_healing_claimed": False,
            },
        )

        local_checksums(
            evidence_root
        )

        return False


def self_test() -> dict[str, Any]:
    environment = {
        "THESIS_GIT_BRANCH": (
            EXPECTED_BRANCH
        ),
        "THESIS_GIT_COMMIT": (
            "a" * 40
        ),
        "THESIS_EXPERIMENT_CONDITION": (
            "C2"
        ),
        "THESIS_SCENARIO_ID": (
            EXPECTED_SCENARIO
        ),
        "C2_RUN_KEY": (
            "c2-freshness-retry-test"
        ),
        "AWS_ACCOUNT_ID": (
            "522814714524"
        ),
        "DATA_LAKE_BUCKET": (
            "thesis-test-data"
        ),
        "ATHENA_RESULTS_BUCKET": (
            "thesis-test-results"
        ),
        "DBT_ATHENA_WORKGROUP": (
            "thesis-test"
        ),
        "DBT_ATHENA_DATA_DIR": (
            "s3://thesis-test-data/"
            "experiments/c2/test/data/"
        ),
        "DBT_ATHENA_STAGING_DIR": (
            "s3://thesis-test-results/"
            "experiments/c2/test/results/"
        ),
        "DBT_ATHENA_SCHEMA": (
            "thesis_pac_c2_test_silver"
        ),
        "DBT_GOLD_INTERNAL_SCHEMA": (
            "thesis_pac_c2_test_gold_internal"
        ),
        "DBT_GOLD_PUBLIC_SCHEMA": (
            "thesis_pac_c2_test_gold_public"
        ),
    }

    config = validate_environment(
        environment
    )

    checks = {
        "condition_c2": (
            config[
                "condition"
            ]
            == "C2"
        ),
        "scenario_freshness": (
            config[
                "scenario"
            ]
            == "freshness_breach"
        ),
        "three_unique_schemas": (
            len(
                set(
                    config[
                        "schemas"
                    ].values()
                )
            )
            == 3
        ),
        "c2_schema_prefixes": all(
            value.startswith(
                SCHEMA_PREFIX
            )
            for value
            in config[
                "schemas"
            ].values()
        ),
        "c2_data_boundary": (
            "/experiments/c2/"
            in config[
                "data_root_uri"
            ]
        ),
        "c2_results_boundary": (
            "/experiments/c2/"
            in config[
                "results_root_uri"
            ]
        ),
    }

    status = (
        "PASS"
        if all(
            checks.values()
        )
        else "FAIL"
    )

    return {
        "status": status,
        "aws_calls": False,
        "dagster_execution": False,
        "dbt_execution": False,
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser()

    sub = parser.add_subparsers(
        dest="command",
        required=True,
    )

    self_test_parser = (
        sub.add_parser(
            "self-test"
        )
    )

    self_test_parser.add_argument(
        "--output",
        type=Path,
        required=True,
    )

    args = parser.parse_args()

    if args.command == "self-test":
        result = self_test()

        write_json(
            args.output,
            result,
        )

        print(
            json.dumps(
                result,
                indent=2,
                sort_keys=True,
            )
        )

        return (
            0
            if result[
                "status"
            ]
            == "PASS"
            else 1
        )

    return 1


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
