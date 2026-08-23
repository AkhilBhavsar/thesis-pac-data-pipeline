#!/usr/bin/env python3
"""
Run one deterministic C2 bounded self-healing execution.

This wrapper orchestrates already validated C2 components:
- policy decision projection
- remediation planning
- execution context preparation
- bounded remediation execution
- recovery verification
- fallback request preparation

No direct canonical data mutation is permitted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


EXPECTED_BRANCH = "feature/c2-bounded-self-healing"
EXPECTED_CONDITION = "C2"

VERIFICATION_PASS_EXIT_CODE = 0
VERIFICATION_CONTROLLED_EXIT_CODE = 2

CONTROLLED_VERIFICATION_STATUSES = {
    "FAIL",
    "MANUAL_REQUIRED",
}

ALLOWED_SCENARIOS = {
    "schema_break",
    "pii_exposure",
    "freshness_breach",
    "quality_regression",
    "policy_false_positive",
}

QUARANTINE_FALLBACK_SCENARIOS = {
    "pii_exposure",
    "freshness_breach",
    "quality_regression",
}


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def require_environment(name: str) -> str:
    value = os.getenv(name, "").strip()

    if not value:
        raise RuntimeError(
            f"Required environment variable missing: {name}"
        )

    return value


def canonical_json(
    payload: Any,
) -> str:
    return json.dumps(
        payload,
        indent=2,
        sort_keys=True,
    ) + "\n"


def write_json(
    path: Path,
    payload: Any,
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_text(
        canonical_json(payload),
        encoding="utf-8",
    )


def sha256_file(
    path: Path,
) -> str:
    return hashlib.sha256(
        path.read_bytes()
    ).hexdigest()


def run_command(
    command: list[str],
    *,
    allowed_returncodes: tuple[int, ...] = (0,),
) -> int:
    print(
        "Executing:",
        " ".join(command),
        flush=True,
    )

    result = subprocess.run(
        command,
        check=False,
    )

    if result.returncode not in allowed_returncodes:
        raise RuntimeError(
            "Command failed with exit code "
            f"{result.returncode}: {' '.join(command)}"
        )

    return result.returncode


def run_python_script(
    script: str,
    arguments: list[str],
    *,
    allowed_returncodes: tuple[int, ...] = (0,),
) -> int:
    script_path = Path(script)

    if not script_path.is_file():
        raise RuntimeError(
            f"Required C2 component does not exist: {script}"
        )

    command = [
        sys.executable,
        script,
        *arguments,
    ]

    return run_command(
        command,
        allowed_returncodes=(
            allowed_returncodes
        ),
    )


def load_json_object(
    path: Path,
    *,
    label: str,
) -> dict[str, Any]:
    try:
        payload = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )
    except FileNotFoundError as error:
        raise RuntimeError(
            f"{label} was not created: {path}"
        ) from error
    except json.JSONDecodeError as error:
        raise RuntimeError(
            f"{label} is invalid JSON: {path}"
        ) from error

    if not isinstance(payload, dict):
        raise RuntimeError(
            f"{label} must be a JSON object: {path}"
        )

    return payload


def validate_verification_outcome(
    *,
    returncode: int,
    verification_output: Path,
    verified_result_output: Path,
) -> dict[str, Any]:
    artifact = load_json_object(
        verification_output,
        label="C2 recovery verification",
    )

    verification_status = artifact.get(
        "verification_status"
    )

    if verification_status == "PASS":
        expected_returncode = (
            VERIFICATION_PASS_EXIT_CODE
        )

        if artifact.get(
            "verified_result_emitted"
        ) is not True:
            raise RuntimeError(
                "PASS verification did not declare "
                "a verified result."
            )

        if not verified_result_output.is_file():
            raise RuntimeError(
                "PASS verification did not create "
                "the verified-result artifact."
            )

        if artifact.get(
            "promotion_blocked"
        ) is not False:
            raise RuntimeError(
                "PASS verification must release "
                "the promotion block."
            )

    elif verification_status in (
        CONTROLLED_VERIFICATION_STATUSES
    ):
        expected_returncode = (
            VERIFICATION_CONTROLLED_EXIT_CODE
        )

        if artifact.get(
            "verified_result_emitted"
        ) is not False:
            raise RuntimeError(
                "Controlled non-PASS verification "
                "declared a verified result."
            )

        if verified_result_output.exists():
            raise RuntimeError(
                "Controlled non-PASS verification "
                "created an unexpected verified result."
            )

        if artifact.get(
            "promotion_blocked"
        ) is not True:
            raise RuntimeError(
                "Controlled non-PASS verification "
                "must keep promotion blocked."
            )

        fallback = artifact.get(
            "recommended_fallback_action"
        )

        if (
            not isinstance(fallback, str)
            or not fallback
        ):
            raise RuntimeError(
                "Controlled non-PASS verification "
                "requires a fallback action."
            )

    else:
        raise RuntimeError(
            "Unexpected C2 verification status: "
            f"{verification_status!r}"
        )

    if returncode != expected_returncode:
        raise RuntimeError(
            "C2 verifier exit/status mismatch: "
            f"exit={returncode}, "
            f"status={verification_status}"
        )

    return artifact


def validate_environment() -> dict[str, str]:
    branch = require_environment(
        "THESIS_GIT_BRANCH"
    )

    condition = require_environment(
        "THESIS_EXPERIMENT_CONDITION"
    )

    scenario = require_environment(
        "THESIS_SCENARIO_ID"
    )

    commit = require_environment(
        "THESIS_GIT_COMMIT"
    )

    run_key = require_environment(
        "C2_RUN_KEY"
    )

    target_layer = require_environment(
        "C2_TARGET_LAYER"
    )

    data_bucket = require_environment(
        "DATA_LAKE_BUCKET"
    )

    data_root_uri = require_environment(
        "DBT_ATHENA_DATA_DIR"
    )

    github_server_url = require_environment(
        "GITHUB_SERVER_URL"
    )

    github_repository = require_environment(
        "GITHUB_REPOSITORY"
    )

    github_run_id = require_environment(
        "GITHUB_RUN_ID"
    )

    github_run_attempt = require_environment(
        "GITHUB_RUN_ATTEMPT"
    )

    if branch != EXPECTED_BRANCH:
        raise RuntimeError(
            f"Unexpected branch: {branch}"
        )

    if condition != EXPECTED_CONDITION:
        raise RuntimeError(
            f"Unexpected condition: {condition}"
        )

    if scenario not in ALLOWED_SCENARIOS:
        raise RuntimeError(
            f"Unexpected C2 scenario: {scenario}"
        )

    if (
        len(commit) != 40
        or any(
            character not in "0123456789abcdef"
            for character in commit
        )
    ):
        raise RuntimeError(
            f"Invalid C2 Git commit: {commit}"
        )

    if not run_key:
        raise RuntimeError(
            "C2 run key must not be empty"
        )

    if not target_layer:
        raise RuntimeError(
            "C2 target layer must not be empty"
        )

    expected_run_key = (
        f"gha_{github_run_id}_"
        f"{github_run_attempt}"
    )

    if run_key != expected_run_key:
        raise RuntimeError(
            "C2 run key does not match the "
            "current GitHub run identity."
        )

    expected_data_root = (
        f"s3://{data_bucket}/"
        "experiments/c2/github-actions/"
        f"{run_key}/"
    )

    if not data_root_uri.startswith(
        expected_data_root
    ):
        raise RuntimeError(
            "C2 data root escaped the "
            "experiments/c2 boundary."
        )

    return {
        "branch": branch,
        "condition": condition,
        "scenario": scenario,
        "commit": commit,
        "run_key": run_key,
        "target_layer": target_layer,
        "data_bucket": data_bucket,
        "data_root_uri": data_root_uri,
        "github_server_url": (
            github_server_url
        ),
        "github_repository": (
            github_repository
        ),
        "github_run_id": github_run_id,
        "github_run_attempt": (
            github_run_attempt
        ),
    }


def build_quarantine_fallback_context(
    *,
    environment: dict[str, str],
) -> dict[str, str] | None:
    scenario = environment[
        "scenario"
    ]

    if scenario not in (
        QUARANTINE_FALLBACK_SCENARIOS
    ):
        return None

    data_bucket = environment[
        "data_bucket"
    ]

    data_root_uri = environment[
        "data_root_uri"
    ]

    bucket_uri = (
        f"s3://{data_bucket}/"
    )

    if not data_root_uri.startswith(
        bucket_uri
    ):
        raise RuntimeError(
            "C2 quarantine source does not "
            "belong to the data-lake bucket."
        )

    source_key = data_root_uri[
        len(bucket_uri):
    ]

    if not source_key.startswith(
        (
            "experiments/c2/github-actions/"
            + environment["run_key"]
            + "/"
        )
    ):
        raise RuntimeError(
            "C2 quarantine source does not "
            "belong to the current run."
        )

    evidence_uri = (
        environment[
            "github_server_url"
        ].rstrip("/")
        + "/"
        + environment[
            "github_repository"
        ]
        + "/actions/runs/"
        + environment[
            "github_run_id"
        ]
    )

    return {
        "data_classification": "synthetic",
        "evidence_uri": evidence_uri,
        "source_bucket": data_bucket,
        "source_dataset": (
            f"synthetic_{scenario}"
        ),
        "source_key": source_key,
        "source_relation": environment[
            "target_layer"
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run deterministic C2 bounded "
            "self-healing orchestration."
        )
    )

    parser.add_argument(
        "--decision",
        required=True,
    )

    parser.add_argument(
        "--catalog",
        required=True,
    )

    parser.add_argument(
        "--decision-schema",
        required=True,
    )

    parser.add_argument(
        "--plan-schema",
        required=True,
    )

    parser.add_argument(
        "--context-schema",
        required=True,
    )

    parser.add_argument(
        "--result-schema",
        required=True,
    )

    parser.add_argument(
        "--pre-evidence",
        required=True,
    )

    parser.add_argument(
        "--opa-bin",
        required=True,
    )

    parser.add_argument(
        "--evidence-root",
        required=True,
    )

    return parser.parse_args()


def build_c2_decision(
    *,
    decision: str,
    catalog: str,
    schema: str,
    output: str,
) -> None:
    run_python_script(
        "scripts/policy/build_c2_policy_decision.py",
        [
            "--decision",
            decision,
            "--catalog",
            catalog,
            "--schema",
            schema,
            "--output",
            output,
        ],
    )


def build_c2_plan(
    *,
    decision: str,
    catalog: str,
    schema: str,
    output: str,
) -> None:
    run_python_script(
        "scripts/policy/build_c2_remediation_plan.py",
        [
            "--decision",
            decision,
            "--catalog",
            catalog,
            "--schema",
            schema,
            "--output",
            output,
        ],
    )


def prepare_context_fixtures(
    *,
    plan_payload: dict[str, Any],
    workspace_root: str,
) -> list[str]:
    action = plan_payload.get(
        "plan",
        {},
    ).get(
        "primary_action"
    )

    scenario = plan_payload.get(
        "scenario_id"
    )

    if not isinstance(
        scenario,
        str,
    ) or not scenario:
        raise RuntimeError(
            "C2 plan is missing scenario_id."
        )

    if action not in {
        "rollback",
        "redact_republish",
    }:
        return []

    workspace = Path(
        workspace_root
    )

    fixture_root = (
        workspace.parent
        / "fixtures"
    )

    if fixture_root.exists():
        raise RuntimeError(
            "C2 fixture directory must not "
            "already exist."
        )

    fixture_root.mkdir(
        parents=True,
        exist_ok=False,
    )

    common = {
        "schema_version": "1.0.0",
        "condition": "C2",
        "scenario_id": scenario,
        "synthetic_fixture": True,
        "canonical_data": False,
    }

    fixture_arguments: list[str]
    fixture_files: dict[str, Path]

    if action == "rollback":
        candidate = (
            fixture_root
            / "candidate.json"
        )
        verified = (
            fixture_root
            / "verified.json"
        )

        write_json(
            candidate,
            {
                **common,
                "fixture_role": "candidate",
                "trusted": False,
                "state": "faulted_candidate",
            },
        )
        write_json(
            verified,
            {
                **common,
                "fixture_role": "verified_source",
                "trusted": True,
                "state": "verified_safe",
            },
        )

        fixture_arguments = [
            "--candidate-source",
            str(candidate),
            "--verified-source",
            str(verified),
        ]
        fixture_files = {
            "candidate": candidate,
            "verified_source": verified,
        }

    else:
        candidate = (
            fixture_root
            / "candidate.json"
        )
        sanitized = (
            fixture_root
            / "sanitized.json"
        )

        write_json(
            candidate,
            {
                **common,
                "fixture_role": "candidate",
                "trusted": False,
                "state": "pii_exposed",
                "synthetic_email": (
                    "c2-fixture@example.invalid"
                ),
            },
        )
        write_json(
            sanitized,
            {
                **common,
                "fixture_role": "sanitized_source",
                "trusted": True,
                "state": "redacted_safe",
            },
        )

        fixture_arguments = [
            "--candidate-source",
            str(candidate),
            "--sanitized-source",
            str(sanitized),
        ]
        fixture_files = {
            "candidate": candidate,
            "sanitized_source": sanitized,
        }

    write_json(
        fixture_root
        / "fixture-manifest.json",
        {
            **common,
            "action": action,
            "isolated": True,
            "files": {
                role: {
                    "path": path.name,
                    "sha256": sha256_file(
                        path
                    ),
                }
                for role, path
                in fixture_files.items()
            },
        },
    )

    return fixture_arguments


def build_c2_context(
    *,
    plan: str,
    schema: str,
    workspace_root: str,
    context_output: str,
    preparation_output: str,
) -> None:
    import json

    plan_payload = json.loads(
        Path(plan).read_text()
    )

    reason = None

    if (
        plan_payload.get("plan", {}).get("mode")
        == "manual"
    ):
        reason = (
            "Manual control required: "
            f"{plan_payload['plan']['primary_action']}"
        )

    command = [
        "--plan",
        plan,
        "--schema",
        schema,
        "--workspace-root",
        workspace_root,
        "--context-output",
        context_output,
        "--preparation-output",
        preparation_output,
    ]

    command.extend(
        prepare_context_fixtures(
            plan_payload=plan_payload,
            workspace_root=workspace_root,
        )
    )

    if reason:
        command.extend(
            [
                "--reason",
                reason,
            ]
        )

    run_python_script(
        "scripts/remediation/build_c2_execution_context.py",
        command,
    )


def execute_c2_remediation(
    *,
    plan: str,
    context: str,
    plan_schema: str,
    context_schema: str,
    result_schema: str,
    workspace_root: str,
    result_output: str,
    details_output: str,
) -> None:
    run_python_script(
        "scripts/remediation/execute_c2_remediation.py",
        [
            "--plan",
            plan,
            "--context",
            context,
            "--plan-schema",
            plan_schema,
            "--context-schema",
            context_schema,
            "--result-schema",
            result_schema,
            "--workspace-root",
            workspace_root,
            "--result-output",
            result_output,
            "--details-output",
            details_output,
        ],
    )

def build_c2_recovery_evidence(
    *,
    plan: str,
    context: str,
    workspace_root: str,
    result: str,
    details: str,
    pre_evidence: str,
    output: str,
) -> None:
    run_python_script(
        "scripts/remediation/build_c2_recovery_evidence.py",
        [
            "--plan",
            plan,
            "--context",
            context,
            "--workspace-root",
            workspace_root,
            "--result",
            result,
            "--details",
            details,
            "--pre-evidence",
            pre_evidence,
            "--output",
            output,
        ],
    )

def verify_c2_recovery(
    *,
    plan: str,
    result: str,
    evidence: str,
    opa_bin: str,
    git_branch: str,
    git_commit: str,
    target_layer: str,
    verification_output: str,
    verified_result_output: str,
) -> int:
    return run_python_script(
        "scripts/remediation/verify_c2_recovery.py",
        [
            "--plan",
            plan,
            "--result",
            result,
            "--evidence",
            evidence,
            "--opa-bin",
            opa_bin,
            "--git-branch",
            git_branch,
            "--git-commit",
            git_commit,
            "--target-layer",
            target_layer,
            "--verification-output",
            verification_output,
            "--verified-result-output",
            verified_result_output,
        ],
        allowed_returncodes=(
            VERIFICATION_PASS_EXIT_CODE,
            VERIFICATION_CONTROLLED_EXIT_CODE,
        ),
    )


def build_c2_fallback_request(
    *,
    plan: str,
    result: str,
    verification: str,
    catalog: str,
    schema: str,
    output: str,
    fallback_context: (
        dict[str, str] | None
    ) = None,
) -> None:
    command = [
        "--plan",
        plan,
        "--result",
        result,
        "--verification",
        verification,
        "--catalog",
        catalog,
        "--schema",
        schema,
        "--output",
        output,
    ]

    if fallback_context is not None:
        argument_names = {
            "data_classification": (
                "--data-classification"
            ),
            "evidence_uri": "--evidence-uri",
            "source_bucket": "--source-bucket",
            "source_dataset": "--source-dataset",
            "source_key": "--source-key",
            "source_relation": "--source-relation",
        }

        if set(
            fallback_context
        ) != set(argument_names):
            raise RuntimeError(
                "C2 quarantine fallback context "
                "is incomplete or contains "
                "unexpected fields."
            )

        for field, option in (
            argument_names.items()
        ):
            command.extend(
                [
                    option,
                    fallback_context[field],
                ]
            )

    run_python_script(
        "scripts/remediation/build_c2_fallback_request.py",
        command,
    )


def prepare_c2_fallback_request(
    *,
    verification_artifact: dict[str, Any],
    plan: str,
    result: str,
    verification: str,
    catalog: str,
    schema: str,
    output: str,
    fallback_context: (
        dict[str, str] | None
    ) = None,
) -> str | None:
    verification_status = (
        verification_artifact.get(
            "verification_status"
        )
    )

    fallback_output = Path(output)

    if fallback_output.exists():
        raise RuntimeError(
            "Fallback request output already exists: "
            f"{fallback_output}"
        )

    if verification_status == "PASS":
        print(
            "C2 stage: fallback request skipped "
            "after verified recovery",
            flush=True,
        )
        return None

    if verification_status not in (
        CONTROLLED_VERIFICATION_STATUSES
    ):
        raise RuntimeError(
            "Fallback request received unexpected "
            "verification status: "
            f"{verification_status!r}"
        )

    print(
        "C2 stage: fallback request preparation",
        flush=True,
    )

    build_c2_fallback_request(
        plan=plan,
        result=result,
        verification=verification,
        catalog=catalog,
        schema=schema,
        output=output,
        fallback_context=(
            fallback_context
        ),
    )

    if not fallback_output.is_file():
        raise RuntimeError(
            "Controlled verification did not create "
            "the fallback request: "
            f"{fallback_output}"
        )

    return str(fallback_output)


def main() -> int:
    args = parse_args()

    environment = validate_environment()

    evidence_root = Path(
        args.evidence_root
    )

    evidence_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    print(
        "C2 evidence root:",
        evidence_root.resolve(),
        flush=True,
    )

    runtime = {
        "timestamp": utc_now(),
        "environment": environment,
        "condition": "C2",
    }

    runtime_start_output = (
        evidence_root
        / "c2-runtime-start.json"
    )

    write_json(
        runtime_start_output,
        runtime,
    )

    decision_output = (
        evidence_root
        / "c2-policy-decision.json"
    )

    plan_output = (
        evidence_root
        / "remediation-plan.json"
    )

    context_output = (
        evidence_root
        / "execution-context.json"
    )

    preparation_output = (
        evidence_root
        / "execution-preparation.json"
    )

    workspace_root = (
        evidence_root
        / "workspace"
    )

    result_output = (
        evidence_root
        / "remediation-result.json"
    )

    details_output = (
        evidence_root
        / "remediation-details.json"
    )

    verification_output = (
        evidence_root
        / "recovery-verification.json"
    )

    verified_result_output = (
        evidence_root
        / "verified-result.json"
    )

    fallback_output = (
        evidence_root
        / "fallback-request.json"
    )

    recovery_evidence_output = (
        evidence_root
        / "recovery-evidence.json"
    )

    completion_output = (
        evidence_root
        / "c2-runtime-complete.json"
    )

    print(
        "C2 stage: policy decision projection",
        flush=True,
    )

    build_c2_decision(
        decision=args.decision,
        catalog=args.catalog,
        schema=args.decision_schema,
        output=str(decision_output),
    )

    print(
        "C2 stage: remediation planning",
        flush=True,
    )

    build_c2_plan(
        decision=str(decision_output),
        catalog=args.catalog,
        schema=args.plan_schema,
        output=str(plan_output),
    )

    print(
        "C2 stage: execution context preparation",
        flush=True,
    )

    build_c2_context(
        plan=str(plan_output),
        schema=args.context_schema,
        workspace_root=str(workspace_root),
        context_output=str(context_output),
        preparation_output=str(preparation_output),
    )

    print(
        "C2 stage: bounded remediation execution",
        flush=True,
    )

    execute_c2_remediation(
        plan=str(plan_output),
        context=str(context_output),
        plan_schema=args.plan_schema,
        context_schema=args.context_schema,
        result_schema=args.result_schema,
        workspace_root=str(workspace_root),
        result_output=str(result_output),
        details_output=str(details_output),
    )

    print(
        "C2 stage: recovery evidence preparation",
        flush=True,
    )

    build_c2_recovery_evidence(
        plan=str(plan_output),
        context=str(context_output),
        workspace_root=str(workspace_root),
        result=str(result_output),
        details=str(details_output),
        pre_evidence=args.pre_evidence,
        output=str(
            recovery_evidence_output
        ),
    )


    print(
        "C2 stage: recovery verification",
        flush=True,
    )

    verification_returncode = verify_c2_recovery(
        plan=str(plan_output),
        result=str(result_output),
        evidence=str(
            recovery_evidence_output
        ),
        opa_bin=args.opa_bin,
        git_branch=environment["branch"],
        git_commit=environment["commit"],
        target_layer=environment["target_layer"],
        verification_output=str(verification_output),
        verified_result_output=str(verified_result_output),
    )

    verification_artifact = (
        validate_verification_outcome(
            returncode=(
                verification_returncode
            ),
            verification_output=(
                verification_output
            ),
            verified_result_output=(
                verified_result_output
            ),
        )
    )

    fallback_context = (
        build_quarantine_fallback_context(
            environment=environment
        )
        if verification_artifact.get(
            "recommended_fallback_action"
        ) == "quarantine"
        else None
    )

    fallback_request = prepare_c2_fallback_request(
        verification_artifact=(
            verification_artifact
        ),
        plan=str(plan_output),
        result=str(result_output),
        verification=str(verification_output),
        catalog=args.catalog,
        schema=(
            "policies/contracts/"
            "c2-fallback-request-input.schema.json"
        ),
        output=str(fallback_output),
        fallback_context=fallback_context,
    )

    completion_payload = {
        "status": "PASS",
        "condition": "C2",
        "scenario_id": environment["scenario"],
        "run_key": environment["run_key"],
        "git_branch": environment["branch"],
        "git_commit": environment["commit"],
        "decision": str(decision_output),
        "plan": str(plan_output),
        "result": str(result_output),
        "recovery_evidence": str(
            recovery_evidence_output
        ),
        "verification": str(verification_output),
        "verification_status": (
            verification_artifact[
                "verification_status"
            ]
        ),
        "verification_exit_code": (
            verification_returncode
        ),
        "promotion_blocked": (
            verification_artifact[
                "promotion_blocked"
            ]
        ),
        "recommended_fallback_action": (
            verification_artifact[
                "recommended_fallback_action"
            ]
        ),
        "verified_result": (
            str(verified_result_output)
            if verified_result_output.is_file()
            else None
        ),
        "fallback_request": fallback_request,
        "completed_at_utc": utc_now(),
    }

    write_json(
        completion_output,
        completion_payload,
    )

    if not completion_output.is_file():
        raise RuntimeError(
            "C2 completion evidence was not created: "
            f"{completion_output}"
        )

    completion_check = json.loads(
        completion_output.read_text(
            encoding="utf-8"
        )
    )

    if completion_check.get("status") != "PASS":
        raise RuntimeError(
            "C2 completion evidence status is not PASS"
        )

    if completion_check.get("condition") != "C2":
        raise RuntimeError(
            "C2 completion evidence condition is not C2"
        )

    print(
        "C2 completion evidence created:",
        completion_output,
        flush=True,
    )

    print(
        "C2 bounded self-healing orchestration: PASS",
        flush=True,
    )

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(
            "C2 bounded self-healing orchestration: FAIL:",
            str(exc),
            file=sys.stderr,
            flush=True,
        )
        raise
