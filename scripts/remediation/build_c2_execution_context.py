#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


class ContextBuilderError(RuntimeError):
    pass


def load_json(path: Path) -> Any:
    try:
        return json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )
    except FileNotFoundError as exc:
        raise ContextBuilderError(
            f"JSON file does not exist: {path}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise ContextBuilderError(
            f"Invalid JSON in {path}: {exc}"
        ) from exc


def sha256_file(path: Path) -> str:
    return hashlib.sha256(
        path.read_bytes()
    ).hexdigest()


def safe_relative_name(
    value: str,
) -> Path:
    candidate = Path(value)

    if candidate.is_absolute():
        raise ContextBuilderError(
            "Absolute workspace-relative "
            "paths are forbidden."
        )

    if ".." in candidate.parts:
        raise ContextBuilderError(
            "Parent traversal is forbidden."
        )

    return candidate


def copy_verified(
    *,
    source: Path,
    destination: Path,
) -> str:
    if not source.is_file():
        raise ContextBuilderError(
            f"Source file does not exist: "
            f"{source}"
        )

    source_sha = sha256_file(
        source
    )

    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    shutil.copy2(
        source,
        destination,
    )

    if (
        sha256_file(destination)
        != source_sha
    ):
        raise ContextBuilderError(
            "Prepared workspace copy "
            "failed fingerprint validation."
        )

    if (
        sha256_file(source)
        != source_sha
    ):
        raise ContextBuilderError(
            "Source changed during workspace "
            "preparation."
        )

    return source_sha


def build_context(
    *,
    plan: dict[str, Any],
    plan_sha256: str,
    workspace_root: Path,
    candidate_source: Path | None = None,
    verified_source: Path | None = None,
    sanitized_source: Path | None = None,
    rejected_output_source: Path | None = None,
    reason: str | None = None,
) -> tuple[
    dict[str, Any],
    dict[str, Any],
]:
    if plan.get(
        "condition"
    ) != "C2":
        raise ContextBuilderError(
            "Execution contexts may be built "
            "only from C2 plans."
        )

    workspace_root = (
        workspace_root
        .expanduser()
        .resolve()
    )

    workspace_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    if any(
        workspace_root.iterdir()
    ):
        raise ContextBuilderError(
            "Execution workspace must begin "
            "empty."
        )

    action = plan[
        "plan"
    ][
        "primary_action"
    ]

    scenario_id = plan[
        "scenario_id"
    ]

    preparation: dict[str, Any] = {
        "condition": "C2",
        "scenario_id": scenario_id,
        "action": action,
        "workspace_root": str(
            workspace_root
        ),
        "source_fingerprints": {},
    }

    if action == "rollback":
        if (
            candidate_source is None
            or verified_source is None
        ):
            raise ContextBuilderError(
                "Rollback requires candidate "
                "and verified sources."
            )

        candidate_relative = safe_relative_name(
            f"candidate/{scenario_id}/target"
            f"{candidate_source.suffix}"
        )

        verified_relative = safe_relative_name(
            f"verified/{scenario_id}/source"
            f"{verified_source.suffix}"
        )

        candidate_sha = copy_verified(
            source=candidate_source,
            destination=(
                workspace_root
                / candidate_relative
            ),
        )

        verified_sha = copy_verified(
            source=verified_source,
            destination=(
                workspace_root
                / verified_relative
            ),
        )

        preparation[
            "source_fingerprints"
        ] = {
            "candidate_sha256": candidate_sha,
            "verified_sha256": verified_sha,
        }

        action_context = {
            "action": "rollback",
            "target_relative_path": (
                candidate_relative.as_posix()
            ),
            "verified_source_relative_path": (
                verified_relative.as_posix()
            ),
        }

    elif action == "redact_republish":
        if (
            candidate_source is None
            or sanitized_source is None
        ):
            raise ContextBuilderError(
                "Redact/republish requires "
                "candidate and sanitized sources."
            )

        candidate_relative = safe_relative_name(
            f"public/{scenario_id}/candidate"
            f"{candidate_source.suffix}"
        )

        sanitized_relative = safe_relative_name(
            f"verified/{scenario_id}/sanitized"
            f"{sanitized_source.suffix}"
        )

        candidate_sha = copy_verified(
            source=candidate_source,
            destination=(
                workspace_root
                / candidate_relative
            ),
        )

        sanitized_sha = copy_verified(
            source=sanitized_source,
            destination=(
                workspace_root
                / sanitized_relative
            ),
        )

        preparation[
            "source_fingerprints"
        ] = {
            "candidate_sha256": candidate_sha,
            "sanitized_sha256": sanitized_sha,
        }

        action_context = {
            "action": "redact_republish",
            "candidate_relative_path": (
                candidate_relative.as_posix()
            ),
            "sanitized_source_relative_path": (
                sanitized_relative.as_posix()
            ),
        }

    elif action == "retry":
        action_context = {
            "action": "retry",
            "runner_profile": (
                "c2_isolated_pipeline"
            ),
        }

    elif action == "quarantine":
        if rejected_output_source is None:
            raise ContextBuilderError(
                "Quarantine requires a rejected "
                "isolated output source."
            )

        rejected_relative = safe_relative_name(
            f"output/{scenario_id}/rejected"
            f"{rejected_output_source.suffix}"
        )

        quarantine_relative = safe_relative_name(
            f"quarantine/{scenario_id}/rejected"
            f"{rejected_output_source.suffix}"
        )

        rejected_sha = copy_verified(
            source=rejected_output_source,
            destination=(
                workspace_root
                / rejected_relative
            ),
        )

        preparation[
            "source_fingerprints"
        ] = {
            "rejected_output_sha256": rejected_sha,
        }

        action_context = {
            "action": "quarantine",
            "rejected_output_relative_path": (
                rejected_relative.as_posix()
            ),
            "quarantine_relative_path": (
                quarantine_relative.as_posix()
            ),
        }

    elif action in {
        "manual_review",
        "stop_promotion",
    }:
        normalized_reason = (
            reason.strip()
            if isinstance(
                reason,
                str,
            )
            else ""
        )

        if not normalized_reason:
            raise ContextBuilderError(
                "Manual control requires "
                "a non-empty reason."
            )

        action_context = {
            "action": action,
            "reason": normalized_reason,
        }

    else:
        raise ContextBuilderError(
            f"Unsupported remediation action: "
            f"{action}"
        )

    context = {
        "schema_version": "1.0.0",
        "condition": "C2",
        "scenario_id": scenario_id,
        "run_key": plan[
            "run_key"
        ],
        "remediation_plan_sha256": (
            plan_sha256
        ),
        "workspace": {
            "root": str(
                workspace_root
            ),
            "isolated": True,
            "canonical_access_permitted": False,
        },
        "action_context": action_context,
    }

    return context, preparation


def validate_context(
    *,
    schema: dict[str, Any],
    context: dict[str, Any],
) -> None:
    Draft202012Validator.check_schema(
        schema
    )

    validator = Draft202012Validator(
        schema
    )

    errors = list(
        validator.iter_errors(
            context
        )
    )

    if errors:
        raise ContextBuilderError(
            "Execution context validation "
            f"failed: {errors[0].message}"
        )


def write_json_atomic(
    path: Path,
    payload: dict[str, Any],
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    rendered = (
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
            rendered
        )

    temporary.replace(
        path
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare an isolated C2 "
            "scenario remediation context."
        )
    )

    parser.add_argument(
        "--plan",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--schema",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--workspace-root",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--context-output",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--preparation-output",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--candidate-source",
        type=Path,
    )

    parser.add_argument(
        "--verified-source",
        type=Path,
    )

    parser.add_argument(
        "--sanitized-source",
        type=Path,
    )

    parser.add_argument(
        "--rejected-output-source",
        type=Path,
    )

    parser.add_argument(
        "--reason",
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        plan = load_json(
            args.plan
        )

        schema = load_json(
            args.schema
        )

        context, preparation = (
            build_context(
                plan=plan,
                plan_sha256=sha256_file(
                    args.plan
                ),
                workspace_root=(
                    args.workspace_root
                ),
                candidate_source=(
                    args.candidate_source
                ),
                verified_source=(
                    args.verified_source
                ),
                sanitized_source=(
                    args.sanitized_source
                ),
                rejected_output_source=(
                    args.rejected_output_source
                ),
                reason=args.reason,
            )
        )

        validate_context(
            schema=schema,
            context=context,
        )

        write_json_atomic(
            args.context_output,
            context,
        )

        write_json_atomic(
            args.preparation_output,
            preparation,
        )

        print(
            json.dumps(
                context,
                indent=2,
                sort_keys=True,
            )
        )

        return 0

    except (
        ContextBuilderError,
        KeyError,
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
