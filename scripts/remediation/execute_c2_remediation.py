#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


if __package__ in {
    None,
    "",
}:
    repository_root = str(
        Path(__file__)
        .resolve()
        .parents[2]
    )

    if repository_root not in sys.path:
        sys.path.insert(
            0,
            repository_root,
        )

from jsonschema import (
    Draft202012Validator,
    FormatChecker,
)


class ExecutorError(RuntimeError):
    pass


RetryRunner = Callable[
    [
        dict[str, Any],
        dict[str, Any],
        int,
    ],
    bool,
]


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


def load_json(path: Path) -> Any:
    try:
        return json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )
    except FileNotFoundError as exc:
        raise ExecutorError(
            f"JSON file does not exist: {path}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise ExecutorError(
            f"Invalid JSON in {path}: {exc}"
        ) from exc


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as source:
        for block in iter(
            lambda: source.read(
                1024 * 1024
            ),
            b"",
        ):
            digest.update(block)

    return digest.hexdigest()


def validate_document(
    *,
    schema: dict[str, Any],
    document: dict[str, Any],
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
        validator.iter_errors(
            document
        ),
        key=lambda error: (
            list(error.absolute_path),
            error.message,
        ),
    )

    if not errors:
        return

    rendered = []

    for error in errors:
        path = ".".join(
            str(part)
            for part
            in error.absolute_path
        )

        rendered.append(
            f"{path or '<root>'}: "
            f"{error.message}"
        )

    raise ExecutorError(
        f"{label} validation failed: "
        + " | ".join(rendered)
    )


def safe_workspace_path(
    *,
    workspace_root: Path,
    relative_name: str,
) -> Path:
    relative = Path(
        relative_name
    )

    if relative.is_absolute():
        raise ExecutorError(
            "Absolute remediation paths "
            "are forbidden."
        )

    if ".." in relative.parts:
        raise ExecutorError(
            "Workspace parent traversal "
            "is forbidden."
        )

    root = workspace_root.resolve()

    candidate = (
        root
        / relative
    ).resolve()

    if (
        candidate != root
        and root not in candidate.parents
    ):
        raise ExecutorError(
            "Remediation path escapes "
            "the isolated workspace."
        )

    return candidate


def verify_identity(
    *,
    plan: dict[str, Any],
    context: dict[str, Any],
    plan_sha256: str,
    workspace_root: Path,
) -> None:
    if plan.get(
        "condition"
    ) != "C2":
        raise ExecutorError(
            "Executor accepts only C2 plans."
        )

    if context.get(
        "condition"
    ) != "C2":
        raise ExecutorError(
            "Executor accepts only C2 "
            "execution contexts."
        )

    for field in (
        "scenario_id",
        "run_key",
    ):
        if (
            plan.get(field)
            != context.get(field)
        ):
            raise ExecutorError(
                f"Plan/context {field} mismatch."
            )

    if (
        context.get(
            "remediation_plan_sha256"
        )
        != plan_sha256
    ):
        raise ExecutorError(
            "Execution context remediation "
            "plan fingerprint mismatch."
        )

    workspace = context.get(
        "workspace",
        {},
    )

    if workspace.get(
        "isolated"
    ) is not True:
        raise ExecutorError(
            "Execution requires an "
            "isolated workspace."
        )

    if workspace.get(
        "canonical_access_permitted"
    ) is not False:
        raise ExecutorError(
            "Canonical access must remain "
            "forbidden."
        )

    declared_root = workspace.get(
        "root"
    )

    if (
        not isinstance(
            declared_root,
            str,
        )
        or not declared_root.strip()
    ):
        raise ExecutorError(
            "Execution context requires "
            "a workspace root."
        )

    if (
        Path(
            declared_root
        )
        .expanduser()
        .resolve()
        != workspace_root.resolve()
    ):
        raise ExecutorError(
            "Runtime workspace does not "
            "match the execution context."
        )

    planned_action = plan[
        "plan"
    ][
        "primary_action"
    ]

    context_action = context[
        "action_context"
    ][
        "action"
    ]

    if planned_action != context_action:
        raise ExecutorError(
            "Execution-context action does "
            "not match remediation plan."
        )


def atomic_replace_from_source(
    *,
    workspace_root: Path,
    source_relative: str,
    target_relative: str,
) -> dict[str, Any]:
    source = safe_workspace_path(
        workspace_root=workspace_root,
        relative_name=source_relative,
    )

    target = safe_workspace_path(
        workspace_root=workspace_root,
        relative_name=target_relative,
    )

    if source == target:
        raise ExecutorError(
            "Source and target must differ."
        )

    if not source.is_file():
        raise ExecutorError(
            f"Verified source does not exist: "
            f"{source_relative}"
        )

    source_sha_before = (
        sha256_file(source)
    )

    target_sha_before = (
        sha256_file(target)
        if target.is_file()
        else None
    )

    target.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary = target.with_name(
        f".{target.name}.c2-remediation.tmp"
    )

    temporary.unlink(
        missing_ok=True
    )

    try:
        shutil.copy2(
            source,
            temporary,
        )

        if (
            sha256_file(temporary)
            != source_sha_before
        ):
            raise ExecutorError(
                "Temporary remediation copy "
                "failed fingerprint validation."
            )

        os.replace(
            temporary,
            target,
        )

    finally:
        temporary.unlink(
            missing_ok=True
        )

    source_sha_after = (
        sha256_file(source)
    )

    target_sha_after = (
        sha256_file(target)
    )

    if source_sha_after != source_sha_before:
        raise ExecutorError(
            "Verified remediation source "
            "was mutated."
        )

    if target_sha_after != source_sha_before:
        raise ExecutorError(
            "Remediated target fingerprint "
            "does not match verified source."
        )

    return {
        "source_sha256": source_sha_before,
        "target_sha256_before": (
            target_sha_before
        ),
        "target_sha256_after": (
            target_sha_after
        ),
        "source_unchanged": True,
    }


def execute_rollback(
    *,
    workspace_root: Path,
    action_context: dict[str, Any],
) -> dict[str, Any]:
    result = atomic_replace_from_source(
        workspace_root=workspace_root,
        source_relative=(
            action_context[
                "verified_source_relative_path"
            ]
        ),
        target_relative=(
            action_context[
                "target_relative_path"
            ]
        ),
    )

    return {
        "operation": (
            "restore_verified_isolated_candidate"
        ),
        **result,
    }


def execute_redact_republish(
    *,
    workspace_root: Path,
    action_context: dict[str, Any],
) -> dict[str, Any]:
    result = atomic_replace_from_source(
        workspace_root=workspace_root,
        source_relative=(
            action_context[
                "sanitized_source_relative_path"
            ]
        ),
        target_relative=(
            action_context[
                "candidate_relative_path"
            ]
        ),
    )

    return {
        "operation": (
            "replace_with_sanitized_"
            "isolated_candidate"
        ),
        **result,
    }


def execute_quarantine(
    *,
    workspace_root: Path,
    action_context: dict[str, Any],
) -> dict[str, Any]:
    source = safe_workspace_path(
        workspace_root=workspace_root,
        relative_name=(
            action_context[
                "rejected_output_relative_path"
            ]
        ),
    )

    destination = safe_workspace_path(
        workspace_root=workspace_root,
        relative_name=(
            action_context[
                "quarantine_relative_path"
            ]
        ),
    )

    if source == destination:
        raise ExecutorError(
            "Rejected output and quarantine "
            "destination must differ."
        )

    if not source.is_file():
        raise ExecutorError(
            "Rejected isolated output "
            "does not exist."
        )

    rejected_sha = sha256_file(
        source
    )

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    if destination.exists():
        raise ExecutorError(
            "Quarantine destination "
            "already exists."
        )

    os.replace(
        source,
        destination,
    )

    if source.exists():
        raise ExecutorError(
            "Rejected output remained in "
            "its promotable isolated location."
        )

    if not destination.is_file():
        raise ExecutorError(
            "Quarantined output was not "
            "materialized."
        )

    quarantine_sha = sha256_file(
        destination
    )

    if quarantine_sha != rejected_sha:
        raise ExecutorError(
            "Quarantined output fingerprint "
            "changed unexpectedly."
        )

    return {
        "operation": (
            "move_isolated_output_to_quarantine"
        ),
        "quarantined_sha256": (
            quarantine_sha
        ),
        "source_removed": True,
    }


def execute_retry(
    *,
    plan: dict[str, Any],
    context: dict[str, Any],
    retry_runner: RetryRunner | None,
) -> dict[str, Any]:
    runner_profile = context[
        "action_context"
    ][
        "runner_profile"
    ]

    if (
        runner_profile
        != "c2_isolated_pipeline"
    ):
        raise ExecutorError(
            "Retry runner profile is "
            "not allow-listed."
        )

    if retry_runner is None:
        raise ExecutorError(
            "C2 isolated retry runner "
            "has not been wired."
        )

    maximum_attempts = plan[
        "plan"
    ][
        "max_attempts"
    ]

    if (
        not isinstance(
            maximum_attempts,
            int,
        )
        or isinstance(
            maximum_attempts,
            bool,
        )
        or maximum_attempts < 1
    ):
        raise ExecutorError(
            "Retry plan has invalid "
            "bounded attempts."
        )

    attempts = []

    for attempt_number in range(
        1,
        maximum_attempts + 1,
    ):
        success = retry_runner(
            plan,
            context,
            attempt_number,
        )

        attempts.append(
            {
                "attempt_number": (
                    attempt_number
                ),
                "success": (
                    success is True
                ),
            }
        )

        if success is True:
            return {
                "operation": (
                    "invoke_allowlisted_"
                    "c2_isolated_pipeline"
                ),
                "runner_profile": (
                    runner_profile
                ),
                "runner_reported_success": True,
                "attempt_count": (
                    attempt_number
                ),
                "maximum_attempts": (
                    maximum_attempts
                ),
                "attempts": attempts,
                "bounded_attempts_exhausted": False,
                "fallback_required": False,
            }

    return {
        "operation": (
            "invoke_allowlisted_"
            "c2_isolated_pipeline"
        ),
        "runner_profile": (
            runner_profile
        ),
        "runner_reported_success": False,
        "attempt_count": (
            maximum_attempts
        ),
        "maximum_attempts": (
            maximum_attempts
        ),
        "attempts": attempts,
        "bounded_attempts_exhausted": True,
        "fallback_required": True,
        "fallback_action": plan[
            "plan"
        ][
            "fallback_action"
        ],
    }

def execute_manual_control(
    *,
    action_context: dict[str, Any],
) -> dict[str, Any]:
    action = action_context[
        "action"
    ]

    return {
        "operation": action,
        "reason": action_context[
            "reason"
        ],
        "automatic_mutation": False,
    }


def build_result(
    *,
    plan: dict[str, Any],
    plan_sha256: str,
    started_at: str,
    completed_at: str,
    duration_ms: float,
    attempt_count: int,
    execution_status: str,
    terminal_state: str,
    automatic_performed: bool,
) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "condition": "C2",
        "scenario_id": plan[
            "scenario_id"
        ],
        "run_key": plan[
            "run_key"
        ],
        "source_remediation_plan_sha256": (
            plan_sha256
        ),
        "mode": plan[
            "plan"
        ][
            "mode"
        ],
        "action": plan[
            "plan"
        ][
            "primary_action"
        ],
        "attempt_count": attempt_count,
        "execution_status": (
            execution_status
        ),
        "verification": {
            "required": True,
            "status": "NOT_RUN",
            "evidence_sha256": None,
        },
        "terminal_state": terminal_state,
        "fault_detected_at_utc": plan[
            "fault_detected_at_utc"
        ],
        "remediation_started_at_utc": (
            started_at
        ),
        "remediation_completed_at_utc": (
            completed_at
        ),
        "action_duration_ms": (
            duration_ms
        ),
        "recovery_time_ms": None,
        "promotion_recheck_required": True,
        "canonical_mutation_performed": False,
        "self_healing_performed": False,
        "automatic_remediation_performed": (
            automatic_performed
        ),
    }


def execute_plan(
    *,
    plan: dict[str, Any],
    context: dict[str, Any],
    workspace_root: Path,
    plan_sha256: str,
    retry_runner: RetryRunner | None = None,
) -> tuple[
    dict[str, Any],
    dict[str, Any],
]:
    verify_identity(
        plan=plan,
        context=context,
        plan_sha256=plan_sha256,
        workspace_root=workspace_root,
    )

    action = plan[
        "plan"
    ][
        "primary_action"
    ]

    mode = plan[
        "plan"
    ][
        "mode"
    ]

    max_attempts = plan[
        "plan"
    ][
        "max_attempts"
    ]

    started_at = utc_now()
    started_ns = time.perf_counter_ns()

    automatic = (
        mode == "automatic"
    )

    if not automatic:
        if max_attempts != 0:
            raise ExecutorError(
                "Manual remediation plan must "
                "have zero attempts."
            )

        details = execute_manual_control(
            action_context=context[
                "action_context"
            ]
        )

        completed_at = utc_now()

        duration_ms = round(
            (
                time.perf_counter_ns()
                - started_ns
            )
            / 1_000_000,
            3,
        )

        terminal_state = (
            "MANUAL_REVIEW"
            if action == "manual_review"
            else "FAILED_SAFE"
        )

        result = build_result(
            plan=plan,
            plan_sha256=plan_sha256,
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=duration_ms,
            attempt_count=0,
            execution_status="NOT_RUN",
            terminal_state=terminal_state,
            automatic_performed=False,
        )

        return result, details

    if max_attempts < 1:
        raise ExecutorError(
            "Automatic remediation requires "
            "at least one bounded attempt."
        )

    if action == "rollback":
        details = execute_rollback(
            workspace_root=workspace_root,
            action_context=context[
                "action_context"
            ],
        )

    elif action == "redact_republish":
        details = execute_redact_republish(
            workspace_root=workspace_root,
            action_context=context[
                "action_context"
            ],
        )

    elif action == "retry":
        details = execute_retry(
            plan=plan,
            context=context,
            retry_runner=retry_runner,
        )

    elif action == "quarantine":
        details = execute_quarantine(
            workspace_root=workspace_root,
            action_context=context[
                "action_context"
            ],
        )

    else:
        raise ExecutorError(
            "Unsupported automatic "
            f"remediation action: {action}"
        )

    completed_at = utc_now()

    duration_ms = round(
        (
            time.perf_counter_ns()
            - started_ns
        )
        / 1_000_000,
        3,
    )

    result = build_result(
        plan=plan,
        plan_sha256=plan_sha256,
        started_at=started_at,
        completed_at=completed_at,
        duration_ms=duration_ms,
        attempt_count=int(
            details.get(
                "attempt_count",
                1,
            )
        ),
        execution_status=(
            "FAILED"
            if details.get(
                "runner_reported_success"
            ) is False
            else "SUCCEEDED"
        ),
        terminal_state=(
            "PENDING_VERIFICATION"
        ),
        automatic_performed=True,
    )

    return result, details


def write_json_atomic(
    path: Path,
    payload: dict[str, Any],
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    content = (
        json.dumps(
            payload,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )

    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temporary = Path(
            handle.name
        )

        handle.write(
            content
        )

        handle.flush()

    temporary.replace(
        path
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Execute one bounded C2 "
            "remediation plan inside an "
            "isolated workspace."
        )
    )

    parser.add_argument(
        "--plan",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--context",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--plan-schema",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--context-schema",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--result-schema",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--workspace-root",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--result-output",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--details-output",
        required=True,
        type=Path,
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        plan = load_json(
            args.plan
        )

        context = load_json(
            args.context
        )

        plan_schema = load_json(
            args.plan_schema
        )

        context_schema = load_json(
            args.context_schema
        )

        result_schema = load_json(
            args.result_schema
        )

        validate_document(
            schema=plan_schema,
            document=plan,
            label="Remediation plan",
        )

        validate_document(
            schema=context_schema,
            document=context,
            label="Execution context",
        )

        plan_sha = sha256_file(
            args.plan
        )

        action = plan[
            "plan"
        ][
            "primary_action"
        ]

        retry_runner = None

        if action == "retry":
            from scripts.remediation.run_c2_isolated_retry import (
                c2_isolated_retry_runner,
            )

            retry_runner = (
                c2_isolated_retry_runner
            )

        result, details = execute_plan(
            plan=plan,
            context=context,
            workspace_root=(
                args.workspace_root
            ),
            plan_sha256=plan_sha,
            retry_runner=(
                retry_runner
            ),
        )

        validate_document(
            schema=result_schema,
            document=result,
            label="Remediation result",
        )

        write_json_atomic(
            args.result_output,
            result,
        )

        write_json_atomic(
            args.details_output,
            details,
        )

        print(
            json.dumps(
                result,
                indent=2,
                sort_keys=True,
            )
        )

        return 0

    except (
        ExecutorError,
        OSError,
        ValueError,
    ) as exc:
        print(
            f"ERROR: {exc}",
            file=sys.stderr,
        )

        return 1


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
