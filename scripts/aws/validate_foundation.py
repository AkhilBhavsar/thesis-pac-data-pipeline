#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ACCOUNT = "522814714524"
REGION = "eu-west-1"
EXPECTED_MANAGED_RESOURCES = 40

PREFIX_MARKERS = [
    "bronze/generated/",
    "bronze/raw/olist/",
    "evidence/",
    "gold/internal/",
    "gold/public/",
    "logs/",
    "quarantine/",
    "scripts/",
    "silver/",
]

COST_ALLOCATION_TAG_KEYS = [
    "Project",
    "Environment",
    "Application",
    "Purpose",
]


def run(
    args: list[str],
    allowed_return_codes: tuple[int, ...] = (0,),
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["AWS_PAGER"] = ""
    environment["TF_IN_AUTOMATION"] = "1"

    result = subprocess.run(
        args,
        text=True,
        capture_output=True,
        env=environment,
        check=False,
    )

    if result.returncode not in allowed_return_codes:
        raise RuntimeError(
            f"Command failed with exit code {result.returncode}:\n"
            f"{' '.join(args)}\n\n"
            f"STDOUT:\n{result.stdout}\n\n"
            f"STDERR:\n{result.stderr}"
        )

    return result


def run_json(args: list[str]) -> Any:
    result = run(args)

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Command did not return valid JSON:\n"
            f"{' '.join(args)}\n\n"
            f"{result.stdout}"
        ) from exc


def terraform_output_value(
    outputs: dict[str, Any],
    key: str,
) -> Any:
    try:
        return outputs[key]["value"]
    except KeyError as exc:
        raise RuntimeError(
            f"Required Terraform output is missing: {key}"
        ) from exc


def lifecycle_matches(
    lifecycle: dict[str, Any],
    *,
    expiration_days: int | None = None,
    noncurrent_days: int | None = None,
    abort_days: int | None = None,
) -> bool:
    enabled_rules = [
        rule
        for rule in lifecycle.get("Rules", [])
        if rule.get("Status") == "Enabled"
    ]

    if not enabled_rules:
        return False

    if expiration_days is not None:
        found = any(
            rule.get("Expiration", {}).get("Days") == expiration_days
            for rule in enabled_rules
        )

        if not found:
            return False

    if noncurrent_days is not None:
        found = any(
            rule.get(
                "NoncurrentVersionExpiration",
                {},
            ).get("NoncurrentDays") == noncurrent_days
            for rule in enabled_rules
        )

        if not found:
            return False

    if abort_days is not None:
        found = any(
            rule.get(
                "AbortIncompleteMultipartUpload",
                {},
            ).get("DaysAfterInitiation") == abort_days
            for rule in enabled_rules
        )

        if not found:
            return False

    return True


def has_https_only_policy(
    policy_wrapper: dict[str, Any],
) -> bool:
    policy = json.loads(policy_wrapper["Policy"])
    statements = policy.get("Statement", [])

    if isinstance(statements, dict):
        statements = [statements]

    for statement in statements:
        if statement.get("Effect") != "Deny":
            continue

        secure_transport = (
            statement
            .get("Condition", {})
            .get("Bool", {})
            .get("aws:SecureTransport")
        )

        if str(secure_transport).lower() == "false":
            return True

    return False


def main() -> int:
    repository_root = Path(__file__).resolve().parents[2]
    os.chdir(repository_root)

    terraform_directory = (
        repository_root
        / "infrastructure"
        / "terraform"
        / "environments"
        / "dev"
    )

    started_at = datetime.now(timezone.utc)
    run_id = (
        "aws-foundation-"
        f"{started_at.strftime('%Y%m%dT%H%M%SZ')}"
    )

    evidence_directory = (
        repository_root
        / "evidence"
        / "aws-foundation"
        / run_id
    )

    evidence_directory.mkdir(
        parents=True,
        exist_ok=False,
    )

    checks: list[dict[str, Any]] = []
    raw_evidence: dict[str, Any] = {}

    def record(
        name: str,
        passed: bool | None,
        details: str,
        evidence: Any | None = None,
    ) -> None:
        if passed is None:
            status = "PENDING"
        elif passed:
            status = "PASS"
        else:
            status = "FAIL"

        check_result = {
            "name": name,
            "status": status,
            "details": details,
            "evidence": evidence,
        }

        checks.append(check_result)

        print(
            f"[{status:<7}] "
            f"{name}: {details}"
        )

    identity = run_json(
        [
            "aws",
            "sts",
            "get-caller-identity",
            "--output",
            "json",
        ]
    )

    terraform_outputs = run_json(
        [
            "terraform",
            f"-chdir={terraform_directory}",
            "output",
            "-json",
        ]
    )

    raw_evidence["identity"] = identity
    raw_evidence["terraform_outputs"] = terraform_outputs

    actual_account = identity["Account"]
    actual_region = terraform_output_value(
        terraform_outputs,
        "aws_region",
    )

    record(
        "AWS account",
        actual_account == ACCOUNT,
        f"Resolved account {actual_account}; expected {ACCOUNT}.",
        identity,
    )

    record(
        "AWS region",
        actual_region == REGION,
        f"Resolved region {actual_region}; expected {REGION}.",
    )

    terraform_validate_result = run(
        [
            "terraform",
            f"-chdir={terraform_directory}",
            "validate",
            "-json",
        ],
        allowed_return_codes=(0, 1),
    )

    terraform_validate = json.loads(
        terraform_validate_result.stdout
    )

    raw_evidence["terraform_validate"] = terraform_validate

    record(
        "Terraform validation",
        terraform_validate.get("valid") is True,
        (
            "Terraform configuration is valid."
            if terraform_validate.get("valid") is True
            else "Terraform validation reported errors."
        ),
        terraform_validate,
    )

    terraform_plan_binary_path = (
        evidence_directory
        / "terraform-drift.tfplan"
    )

    terraform_plan_result = run(
        [
            "terraform",
            f"-chdir={terraform_directory}",
            "plan",
            "-detailed-exitcode",
            "-no-color",
            f"-out={terraform_plan_binary_path}",
        ],
        allowed_return_codes=(0, 1, 2),
    )

    terraform_plan_path = (
        evidence_directory
        / "terraform-drift-plan.txt"
    )

    terraform_plan_text = (
        terraform_plan_result.stdout
        + terraform_plan_result.stderr
    )

    managed_changes: list[dict[str, Any]] = []
    output_change_names: list[str] = []

    if terraform_plan_result.returncode in (0, 2):
        terraform_plan_json = run_json(
            [
                "terraform",
                f"-chdir={terraform_directory}",
                "show",
                "-json",
                str(terraform_plan_binary_path),
            ]
        )

        terraform_plan_text = run(
            [
                "terraform",
                f"-chdir={terraform_directory}",
                "show",
                "-no-color",
                str(terraform_plan_binary_path),
            ]
        ).stdout

        managed_changes = [
            {
                "address": item.get("address"),
                "actions": item.get(
                    "change",
                    {},
                ).get(
                    "actions",
                    [],
                ),
            }
            for item in terraform_plan_json.get(
                "resource_changes",
                [],
            )
            if item.get("mode") == "managed"
            and item.get(
                "change",
                {},
            ).get(
                "actions",
                [],
            ) != ["no-op"]
        ]

        output_change_names = sorted(
            output_name
            for output_name, output_change
            in terraform_plan_json.get(
                "output_changes",
                {},
            ).items()
            if output_change.get(
                "actions",
                [],
            ) != ["no-op"]
        )

    terraform_plan_path.write_text(
        terraform_plan_text,
        encoding="utf-8",
    )

    terraform_plan_binary_path.unlink(
        missing_ok=True,
    )

    terraform_plan_ok = (
        terraform_plan_result.returncode in (0, 2)
        and not managed_changes
    )

    if terraform_plan_result.returncode == 1:
        terraform_plan_details = (
            "Terraform plan failed."
        )
    elif managed_changes:
        terraform_plan_details = (
            "Managed-resource changes detected: "
            f"{managed_changes}."
        )
    elif output_change_names:
        terraform_plan_details = (
            "No managed-resource drift; "
            "output-only changes detected: "
            f"{output_change_names}."
        )
    else:
        terraform_plan_details = (
            "No managed-resource or output "
            "changes detected."
        )

    raw_evidence["terraform_plan"] = {
        "exit_code": terraform_plan_result.returncode,
        "managed_changes": managed_changes,
        "output_changes": output_change_names,
    }

    record(
        "Terraform drift",
        terraform_plan_ok,
        terraform_plan_details,
        {
            "exit_code": terraform_plan_result.returncode,
            "managed_changes": managed_changes,
            "output_changes": output_change_names,
            "plan_file": terraform_plan_path.name,
        },
    )

    terraform_state_result = run(
        [
            "terraform",
            f"-chdir={terraform_directory}",
            "state",
            "list",
        ]
    )

    state_addresses = [
        line.strip()
        for line in terraform_state_result.stdout.splitlines()
        if line.strip()
    ]

    managed_addresses = [
        address
        for address in state_addresses
        if not address.startswith("data.")
        and ".data." not in address
    ]

    raw_evidence["terraform_state"] = state_addresses

    record(
        "Terraform managed-resource count",
        len(managed_addresses)
        == EXPECTED_MANAGED_RESOURCES,
        (
            f"Found {len(managed_addresses)} managed resources; "
            f"expected {EXPECTED_MANAGED_RESOURCES}."
        ),
        {
            "actual": len(managed_addresses),
            "expected": EXPECTED_MANAGED_RESOURCES,
        },
    )

    state_bucket = (
        f"thesis-pac-terraform-state-"
        f"{ACCOUNT}-{REGION}"
    )

    data_lake_bucket = terraform_output_value(
        terraform_outputs,
        "data_lake_bucket_name",
    )

    athena_results_bucket = terraform_output_value(
        terraform_outputs,
        "athena_results_bucket_name",
    )

    bucket_expectations = {
        "Terraform state": {
            "name": state_bucket,
            "noncurrent_days": 90,
            "abort_days": 7,
        },
        "Data lake": {
            "name": data_lake_bucket,
            "noncurrent_days": 90,
            "abort_days": 7,
        },
        "Athena results": {
            "name": athena_results_bucket,
            "expiration_days": 30,
        },
    }

    raw_evidence["s3"] = {}

    for label, expectation in bucket_expectations.items():
        bucket_name = expectation["name"]

        public_access = run_json(
            [
                "aws",
                "s3api",
                "get-public-access-block",
                "--bucket",
                bucket_name,
                "--output",
                "json",
            ]
        )

        encryption = run_json(
            [
                "aws",
                "s3api",
                "get-bucket-encryption",
                "--bucket",
                bucket_name,
                "--output",
                "json",
            ]
        )

        versioning = run_json(
            [
                "aws",
                "s3api",
                "get-bucket-versioning",
                "--bucket",
                bucket_name,
                "--output",
                "json",
            ]
        )

        ownership = run_json(
            [
                "aws",
                "s3api",
                "get-bucket-ownership-controls",
                "--bucket",
                bucket_name,
                "--output",
                "json",
            ]
        )

        lifecycle = run_json(
            [
                "aws",
                "s3api",
                "get-bucket-lifecycle-configuration",
                "--bucket",
                bucket_name,
                "--output",
                "json",
            ]
        )

        bucket_policy = run_json(
            [
                "aws",
                "s3api",
                "get-bucket-policy",
                "--bucket",
                bucket_name,
                "--output",
                "json",
            ]
        )

        raw_evidence["s3"][label] = {
            "bucket": bucket_name,
            "public_access": public_access,
            "encryption": encryption,
            "versioning": versioning,
            "ownership": ownership,
            "lifecycle": lifecycle,
            "policy": bucket_policy,
        }

        public_access_configuration = (
            public_access[
                "PublicAccessBlockConfiguration"
            ]
        )

        public_access_ok = all(
            public_access_configuration.get(key) is True
            for key in (
                "BlockPublicAcls",
                "IgnorePublicAcls",
                "BlockPublicPolicy",
                "RestrictPublicBuckets",
            )
        )

        record(
            f"{label} public-access block",
            public_access_ok,
            (
                "All four public-access controls are enabled "
                f"for {bucket_name}."
            ),
            public_access_configuration,
        )

        encryption_algorithm = (
            encryption[
                "ServerSideEncryptionConfiguration"
            ]["Rules"][0][
                "ApplyServerSideEncryptionByDefault"
            ]["SSEAlgorithm"]
        )

        record(
            f"{label} encryption",
            encryption_algorithm == "AES256",
            (
                f"Encryption algorithm is "
                f"{encryption_algorithm}; expected AES256."
            ),
            encryption,
        )

        record(
            f"{label} versioning",
            versioning.get("Status") == "Enabled",
            (
                f"Versioning status is "
                f"{versioning.get('Status')}."
            ),
            versioning,
        )

        ownership_mode = (
            ownership[
                "OwnershipControls"
            ]["Rules"][0]["ObjectOwnership"]
        )

        record(
            f"{label} ownership",
            ownership_mode == "BucketOwnerEnforced",
            f"Ownership mode is {ownership_mode}.",
            ownership,
        )

        record(
            f"{label} HTTPS-only policy",
            has_https_only_policy(bucket_policy),
            (
                "Bucket policy denies requests when "
                "aws:SecureTransport is false."
            ),
            bucket_policy,
        )

        lifecycle_passed = lifecycle_matches(
            lifecycle,
            expiration_days=expectation.get(
                "expiration_days"
            ),
            noncurrent_days=expectation.get(
                "noncurrent_days"
            ),
            abort_days=expectation.get(
                "abort_days"
            ),
        )

        record(
            f"{label} lifecycle",
            lifecycle_passed,
            json.dumps(
                {
                    key: value
                    for key, value in expectation.items()
                    if key != "name"
                },
                sort_keys=True,
            ),
            lifecycle,
        )

    state_object = run_json(
        [
            "aws",
            "s3api",
            "head-object",
            "--bucket",
            state_bucket,
            "--key",
            "environments/dev/terraform.tfstate",
            "--output",
            "json",
        ]
    )

    raw_evidence["terraform_state_object"] = (
        state_object
    )

    state_object_ok = (
        state_object.get("ContentLength", 0) > 0
        and state_object.get(
            "ServerSideEncryption"
        ) == "AES256"
        and bool(state_object.get("VersionId"))
    )

    record(
        "Remote development-state object",
        state_object_ok,
        (
            f"size={state_object.get('ContentLength')} bytes, "
            f"encryption="
            f"{state_object.get('ServerSideEncryption')}, "
            f"versioned="
            f"{bool(state_object.get('VersionId'))}."
        ),
        state_object,
    )

    raw_evidence["prefix_markers"] = {}

    for prefix_key in PREFIX_MARKERS:
        marker = run_json(
            [
                "aws",
                "s3api",
                "head-object",
                "--bucket",
                data_lake_bucket,
                "--key",
                prefix_key,
                "--output",
                "json",
            ]
        )

        raw_evidence[
            "prefix_markers"
        ][prefix_key] = marker

        record(
            f"S3 prefix marker {prefix_key}",
            marker.get("ContentLength") == 0,
            (
                f"Marker exists with size "
                f"{marker.get('ContentLength')} bytes."
            ),
            marker,
        )

    glue_database_names = terraform_output_value(
        terraform_outputs,
        "glue_database_names",
    )

    raw_evidence["glue_databases"] = {}

    for zone, database_name in sorted(
        glue_database_names.items()
    ):
        database = run_json(
            [
                "aws",
                "glue",
                "get-database",
                "--name",
                database_name,
                "--output",
                "json",
            ]
        )

        raw_evidence[
            "glue_databases"
        ][zone] = database

        actual_name = database["Database"]["Name"]

        record(
            f"Glue database {zone}",
            actual_name == database_name,
            f"Resolved database {actual_name}.",
            database,
        )

    workgroup_name = terraform_output_value(
        terraform_outputs,
        "athena_workgroup_name",
    )

    workgroup = run_json(
        [
            "aws",
            "athena",
            "get-work-group",
            "--work-group",
            workgroup_name,
            "--output",
            "json",
        ]
    )

    raw_evidence["athena_workgroup"] = workgroup

    workgroup_data = workgroup["WorkGroup"]
    workgroup_configuration = (
        workgroup_data["Configuration"]
    )

    result_configuration = (
        workgroup_configuration[
            "ResultConfiguration"
        ]
    )

    encryption_option = (
        result_configuration
        .get(
            "EncryptionConfiguration",
            {},
        )
        .get("EncryptionOption")
    )

    expected_results_location = (
        terraform_output_value(
            terraform_outputs,
            "athena_results_location",
        )
    )

    workgroup_ok = all(
        (
            workgroup_data.get("State")
            == "ENABLED",
            workgroup_configuration.get(
                "EnforceWorkGroupConfiguration"
            ) is True,
            workgroup_configuration.get(
                "PublishCloudWatchMetricsEnabled"
            ) is True,
            workgroup_configuration.get(
                "BytesScannedCutoffPerQuery"
            ) == 1073741824,
            result_configuration.get(
                "OutputLocation"
            ) == expected_results_location,
            encryption_option == "SSE_S3",
            result_configuration.get(
                "ExpectedBucketOwner"
            ) == ACCOUNT,
        )
    )

    record(
        "Athena governed workgroup",
        workgroup_ok,
        (
            f"state={workgroup_data.get('State')}, "
            f"enforced="
            f"{workgroup_configuration.get('EnforceWorkGroupConfiguration')}, "
            f"metrics="
            f"{workgroup_configuration.get('PublishCloudWatchMetricsEnabled')}, "
            f"cutoff="
            f"{workgroup_configuration.get('BytesScannedCutoffPerQuery')}, "
            f"encryption={encryption_option}."
        ),
        workgroup,
    )

    budget_expectations = {
        "My Monthly Cost Budget": {
            "limit": 2.0,
            "notifications": {
                ("ACTUAL", 85.0),
                ("ACTUAL", 100.0),
                ("FORECASTED", 100.0),
            },
        },
        "My Zero-Spend Budget": {
            "limit": 0.01,
            "notifications": {
                ("ACTUAL", 0.01),
            },
        },
    }

    raw_evidence["budgets"] = {}

    for budget_name, expectation in (
        budget_expectations.items()
    ):
        budget_response = run_json(
            [
                "aws",
                "budgets",
                "describe-budget",
                "--account-id",
                ACCOUNT,
                "--budget-name",
                budget_name,
                "--output",
                "json",
            ]
        )

        notifications_response = run_json(
            [
                "aws",
                "budgets",
                "describe-notifications-for-budget",
                "--account-id",
                ACCOUNT,
                "--budget-name",
                budget_name,
                "--output",
                "json",
            ]
        )

        raw_evidence[
            "budgets"
        ][budget_name] = {
            "budget": budget_response,
            "notifications": notifications_response,
        }

        budget = budget_response["Budget"]

        actual_limit = float(
            budget["BudgetLimit"]["Amount"]
        )

        budget_ok = all(
            (
                budget.get("BudgetType") == "COST",
                budget.get("TimeUnit") == "MONTHLY",
                budget[
                    "BudgetLimit"
                ].get("Unit") == "USD",
                abs(
                    actual_limit
                    - expectation["limit"]
                ) < 1e-9,
            )
        )

        record(
            f"Budget configuration: {budget_name}",
            budget_ok,
            f"limit={actual_limit} USD.",
            budget_response,
        )

        observed_notifications = {
            (
                notification[
                    "NotificationType"
                ],
                float(
                    notification["Threshold"]
                ),
            )
            for notification in (
                notifications_response.get(
                    "Notifications",
                    [],
                )
            )
        }

        notifications_ok = (
            expectation["notifications"]
            .issubset(observed_notifications)
        )

        record(
            f"Budget notifications: {budget_name}",
            notifications_ok,
            (
                f"Observed "
                f"{len(observed_notifications)} rules."
            ),
            notifications_response,
        )

    project_budget_summary = terraform_output_value(
        terraform_outputs,
        "project_budget_summary",
    )

    project_budget_name = project_budget_summary[
        "name"
    ]

    project_budget_limit = float(
        project_budget_summary[
            "monthly_limit_usd"
        ]
    )

    project_budget_scope = project_budget_summary[
        "cost_scope"
    ]

    expected_project_scope = {
        "Project": "thesis-pac",
        "Environment": "dev",
    }

    project_budget_response = run_json(
        [
            "aws",
            "budgets",
            "describe-budget",
            "--account-id",
            ACCOUNT,
            "--budget-name",
            project_budget_name,
            "--output",
            "json",
        ]
    )

    project_notifications_response = run_json(
        [
            "aws",
            "budgets",
            "describe-notifications-for-budget",
            "--account-id",
            ACCOUNT,
            "--budget-name",
            project_budget_name,
            "--output",
            "json",
        ]
    )

    raw_evidence["project_budget"] = {
        "budget": project_budget_response,
        "notifications": (
            project_notifications_response
        ),
    }

    project_budget = project_budget_response[
        "Budget"
    ]

    filter_terms = (
        project_budget
        .get(
            "FilterExpression",
            {},
        )
        .get(
            "And",
            [],
        )
    )

    observed_project_filters: dict[
        str,
        dict[str, list[str]],
    ] = {}

    for filter_term in filter_terms:
        tag_filter = filter_term.get("Tags")

        if not tag_filter:
            continue

        tag_key = tag_filter.get("Key")

        observed_project_filters[tag_key] = {
            "values": sorted(
                tag_filter.get(
                    "Values",
                    [],
                )
            ),
            "match_options": sorted(
                tag_filter.get(
                    "MatchOptions",
                    [],
                )
            ),
        }

    project_filter_ok = all(
        observed_project_filters
        .get(
            tag_key,
            {},
        )
        .get(
            "values",
        )
        == [tag_value]
        and observed_project_filters
        .get(
            tag_key,
            {},
        )
        .get(
            "match_options",
        )
        == ["EQUALS"]
        for tag_key, tag_value
        in expected_project_scope.items()
    )

    project_budget_ok = all(
        (
            project_budget.get(
                "BudgetName"
            ) == project_budget_name,
            project_budget.get(
                "BudgetType"
            ) == "COST",
            project_budget.get(
                "TimeUnit"
            ) == "MONTHLY",
            project_budget.get(
                "Metrics"
            ) == ["UnblendedCost"],
            project_budget[
                "BudgetLimit"
            ].get(
                "Unit"
            ) == "USD",
            abs(
                float(
                    project_budget[
                        "BudgetLimit"
                    ][
                        "Amount"
                    ]
                )
                - project_budget_limit
            )
            < 1e-9,
            project_budget_scope
            == expected_project_scope,
            project_filter_ok,
        )
    )

    record(
        "Project budget configuration",
        project_budget_ok,
        (
            f"name={project_budget_name}, "
            f"limit={project_budget_limit:.2f} USD, "
            f"scope={project_budget_scope}."
        ),
        project_budget_response,
    )

    observed_project_notifications = {
        (
            notification[
                "NotificationType"
            ],
            float(
                notification[
                    "Threshold"
                ]
            ),
        )
        for notification in (
            project_notifications_response.get(
                "Notifications",
                [],
            )
        )
    }

    expected_project_notifications = {
        ("ACTUAL", 0.10),
        ("ACTUAL", 50.0),
        ("ACTUAL", 80.0),
        ("ACTUAL", 100.0),
        ("FORECASTED", 100.0),
    }

    project_absolute_alert_ok = any(
        notification.get(
            "NotificationType"
        ) == "ACTUAL"
        and abs(
            float(
                notification.get(
                    "Threshold",
                    0,
                )
            )
            - 0.10
        )
        < 1e-9
        and notification.get(
            "ThresholdType"
        )
        == "ABSOLUTE_VALUE"
        for notification in (
            project_notifications_response.get(
                "Notifications",
                [],
            )
        )
    )

    project_comparison_operators_ok = all(
        notification.get(
            "ComparisonOperator"
        )
        == "GREATER_THAN"
        for notification in (
            project_notifications_response.get(
                "Notifications",
                [],
            )
        )
    )

    project_notifications_ok = all(
        (
            observed_project_notifications
            == expected_project_notifications,
            len(
                project_notifications_response.get(
                    "Notifications",
                    [],
                )
            )
            == 5,
            project_absolute_alert_ok,
            project_comparison_operators_ok,
        )
    )

    record(
        "Project budget notifications",
        project_notifications_ok,
        (
            "Observed the expected five "
            "project-budget alert rules."
        ),
        project_notifications_response,
    )

    cost_allocation_tags = run_json(
        [
            "aws",
            "ce",
            "list-cost-allocation-tags",
            "--tag-keys",
            *COST_ALLOCATION_TAG_KEYS,
            "--output",
            "json",
        ]
    )

    raw_evidence[
        "cost_allocation_tags"
    ] = cost_allocation_tags

    tag_statuses = {
        tag["TagKey"]: tag["Status"]
        for tag in (
            cost_allocation_tags.get(
                "CostAllocationTags",
                [],
            )
        )
    }

    all_tags_active = all(
        tag_statuses.get(tag_key) == "Active"
        for tag_key in (
            COST_ALLOCATION_TAG_KEYS
        )
    )

    record(
        "Cost-allocation tags",
        True if all_tags_active else None,
        (
            "All four tags are active."
            if all_tags_active
            else (
                "AWS Billing propagation pending; "
                f"observed={tag_statuses}."
            )
        ),
        cost_allocation_tags,
    )

    today = datetime.now(
        timezone.utc
    ).date()

    start_date = today.replace(
        day=1
    ).isoformat()

    end_date = (
        today
        + timedelta(days=1)
    ).isoformat()

    account_cost_response = run_json(
        [
            "aws",
            "ce",
            "get-cost-and-usage",
            "--time-period",
            (
                f"Start={start_date},"
                f"End={end_date}"
            ),
            "--granularity",
            "MONTHLY",
            "--metrics",
            "UnblendedCost",
            "--group-by",
            "Type=DIMENSION,Key=SERVICE",
            "--output",
            "json",
        ]
    )

    raw_evidence[
        "monthly_account_cost"
    ] = account_cost_response

    account_result_groups = (
        account_cost_response
        .get(
            "ResultsByTime",
            [{}],
        )[0]
        .get(
            "Groups",
            [],
        )
    )

    account_service_costs = {
        group["Keys"][0]: float(
            group[
                "Metrics"
            ][
                "UnblendedCost"
            ][
                "Amount"
            ]
        )
        for group in account_result_groups
    }

    account_total_cost = sum(
        account_service_costs.values()
    )

    account_monthly_limit = float(
        budget_expectations[
            "My Monthly Cost Budget"
        ][
            "limit"
        ]
    )

    zero_spend_threshold = float(
        budget_expectations[
            "My Zero-Spend Budget"
        ][
            "limit"
        ]
    )

    zero_spend_threshold_crossed = (
        account_total_cost
        > zero_spend_threshold
    )

    record(
        "Current-month account AWS cost",
        account_total_cost
        < account_monthly_limit,
        (
            f"Account cost is "
            f"USD {account_total_cost:.10f}; "
            f"monthly account limit is "
            f"USD {account_monthly_limit:.2f}. "
            f"Zero-spend threshold "
            f"USD {zero_spend_threshold:.2f} has "
            f"{'been crossed' if zero_spend_threshold_crossed else 'not been crossed'}."
        ),
        {
            "total_cost_usd": account_total_cost,
            "monthly_limit_usd": (
                account_monthly_limit
            ),
            "zero_spend_threshold_usd": (
                zero_spend_threshold
            ),
            "zero_spend_threshold_crossed": (
                zero_spend_threshold_crossed
            ),
            "service_costs": (
                account_service_costs
            ),
        },
    )

    project_cost_filter = {
        "And": [
            {
                "Tags": {
                    "Key": "Project",
                    "Values": [
                        project_budget_scope[
                            "Project"
                        ]
                    ],
                    "MatchOptions": [
                        "EQUALS"
                    ],
                }
            },
            {
                "Tags": {
                    "Key": "Environment",
                    "Values": [
                        project_budget_scope[
                            "Environment"
                        ]
                    ],
                    "MatchOptions": [
                        "EQUALS"
                    ],
                }
            },
        ]
    }

    project_cost_response = run_json(
        [
            "aws",
            "ce",
            "get-cost-and-usage",
            "--time-period",
            (
                f"Start={start_date},"
                f"End={end_date}"
            ),
            "--granularity",
            "MONTHLY",
            "--metrics",
            "UnblendedCost",
            "--filter",
            json.dumps(
                project_cost_filter,
                separators=(",", ":"),
            ),
            "--group-by",
            "Type=DIMENSION,Key=SERVICE",
            "--output",
            "json",
        ]
    )

    raw_evidence[
        "monthly_project_cost"
    ] = {
        "filter": project_cost_filter,
        "response": project_cost_response,
    }

    project_result_groups = (
        project_cost_response
        .get(
            "ResultsByTime",
            [{}],
        )[0]
        .get(
            "Groups",
            [],
        )
    )

    project_service_costs = {
        group["Keys"][0]: float(
            group[
                "Metrics"
            ][
                "UnblendedCost"
            ][
                "Amount"
            ]
        )
        for group in project_result_groups
    }

    project_total_cost = sum(
        project_service_costs.values()
    )

    record(
        "Current-month project AWS cost",
        project_total_cost
        < project_budget_limit,
        (
            f"Tagged project cost is "
            f"USD {project_total_cost:.10f}; "
            f"project budget limit is "
            f"USD {project_budget_limit:.2f}."
        ),
        {
            "total_cost_usd": project_total_cost,
            "monthly_limit_usd": (
                project_budget_limit
            ),
            "scope": project_budget_scope,
            "service_costs": (
                project_service_costs
            ),
        },
    )

    runtime_role_names = terraform_output_value(
        terraform_outputs,
        "runtime_iam_role_names",
    )

    role_expectations = {
        "glue": {
            "principal": "glue.amazonaws.com",
            "policies": {
                "thesis-pac-dev-glue-runtime",
            },
        },
        "lambda": {
            "principal": "lambda.amazonaws.com",
            "policies": {
                "thesis-pac-dev-lambda-runtime",
                "AWSLambdaBasicExecutionRole",
            },
        },
        "step_functions": {
            "principal": "states.amazonaws.com",
            "policies": {
                "thesis-pac-dev-step-functions-runtime",
            },
        },
    }

    raw_evidence["iam"] = {}

    for service, expectation in (
        role_expectations.items()
    ):
        role_name = runtime_role_names[
            service
        ]

        role = run_json(
            [
                "aws",
                "iam",
                "get-role",
                "--role-name",
                role_name,
                "--output",
                "json",
            ]
        )

        attached_policies = run_json(
            [
                "aws",
                "iam",
                "list-attached-role-policies",
                "--role-name",
                role_name,
                "--output",
                "json",
            ]
        )

        raw_evidence["iam"][service] = {
            "role": role,
            "attached_policies": attached_policies,
        }

        trust_document = (
            role[
                "Role"
            ][
                "AssumeRolePolicyDocument"
            ]
        )

        statements = trust_document.get(
            "Statement",
            [],
        )

        if isinstance(statements, dict):
            statements = [statements]

        expected_principal = (
            expectation["principal"]
        )

        trust_ok = any(
            statement
            .get("Principal", {})
            .get("Service")
            == expected_principal
            for statement in statements
        )

        if service == "step_functions":
            expected_source_arn = (
                f"arn:aws:states:{REGION}:"
                f"{ACCOUNT}:stateMachine:"
                "thesis-pac-dev-*"
            )

            trust_ok = trust_ok and any(
                statement
                .get("Condition", {})
                .get("StringEquals", {})
                .get("aws:SourceAccount")
                == ACCOUNT
                and statement
                .get("Condition", {})
                .get("ArnLike", {})
                .get("aws:SourceArn")
                == expected_source_arn
                for statement in statements
            )

        record(
            f"IAM trust policy: {service}",
            trust_ok,
            f"Role {role_name}.",
            trust_document,
        )

        attached_policy_names = {
            policy["PolicyName"]
            for policy in (
                attached_policies.get(
                    "AttachedPolicies",
                    [],
                )
            )
        }

        expected_policy_names = (
            expectation["policies"]
        )

        record(
            f"IAM policy attachments: {service}",
            expected_policy_names.issubset(
                attached_policy_names
            ),
            (
                f"Attached policies="
                f"{sorted(attached_policy_names)}."
            ),
            attached_policies,
        )

    passed_count = sum(
        check_result["status"] == "PASS"
        for check_result in checks
    )

    failed_count = sum(
        check_result["status"] == "FAIL"
        for check_result in checks
    )

    pending_count = sum(
        check_result["status"] == "PENDING"
        for check_result in checks
    )

    if failed_count:
        overall_status = "FAIL"
    elif pending_count:
        overall_status = "PASS_WITH_PENDING"
    else:
        overall_status = "PASS"

    git_branch = run(
        [
            "git",
            "branch",
            "--show-current",
        ]
    ).stdout.strip()

    git_commit = run(
        [
            "git",
            "rev-parse",
            "HEAD",
        ]
    ).stdout.strip()

    report = {
        "metadata": {
            "run_id": run_id,
            "generated_at_utc": (
                started_at.isoformat()
            ),
            "git_branch": git_branch,
            "git_commit": git_commit,
            "aws_account": ACCOUNT,
            "aws_region": REGION,
        },
        "summary": {
            "overall_status": overall_status,
            "passed": passed_count,
            "failed": failed_count,
            "pending": pending_count,
            "total": len(checks),
        },
        "checks": checks,
        "raw_evidence": raw_evidence,
    }

    json_report_path = (
        evidence_directory
        / "aws-foundation-validation.json"
    )

    json_report_path.write_text(
        json.dumps(
            report,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    markdown_lines = [
        "# AWS Foundation Validation",
        "",
        f"- Run ID: `{run_id}`",
        f"- Generated: `{started_at.isoformat()}`",
        f"- Git branch: `{git_branch}`",
        f"- Git commit: `{git_commit}`",
        f"- AWS account: `{ACCOUNT}`",
        f"- AWS region: `{REGION}`",
        f"- Overall status: **{overall_status}**",
        f"- PASS: **{passed_count}**",
        f"- FAIL: **{failed_count}**",
        f"- PENDING: **{pending_count}**",
        "",
        "## Validation checks",
        "",
        "| Status | Check | Details |",
        "|---|---|---|",
    ]

    for check_result in checks:
        check_name = str(
            check_result["name"]
        ).replace(
            "|",
            "\\|",
        )

        details = str(
            check_result["details"]
        ).replace(
            "|",
            "\\|",
        ).replace(
            "\n",
            " ",
        )

        markdown_lines.append(
            f"| {check_result['status']} "
            f"| {check_name} "
            f"| {details} |"
        )

    markdown_lines.extend(
        [
            "",
            "## Interpretation",
            "",
            (
                "The AWS foundation passes when no checks "
                "are marked `FAIL`. Cost-allocation tags "
                "may remain `PENDING` while AWS Billing "
                "propagates recently applied tag keys."
            ),
            "",
            "## Supporting evidence",
            "",
            "- `aws-foundation-validation.json`",
            "- `terraform-drift-plan.txt`",
            "",
        ]
    )

    markdown_report_path = (
        evidence_directory
        / "aws-foundation-validation.md"
    )

    markdown_report_path.write_text(
        "\n".join(markdown_lines),
        encoding="utf-8",
    )

    print()
    print("=" * 72)
    print(
        f"Overall status: {overall_status}"
    )
    print(
        f"PASS={passed_count} "
        f"FAIL={failed_count} "
        f"PENDING={pending_count}"
    )
    print(
        f"Evidence directory: "
        f"{evidence_directory}"
    )
    print("=" * 72)

    return 1 if failed_count else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(
            f"FATAL: {exc}",
            file=sys.stderr,
        )
        raise SystemExit(2)
