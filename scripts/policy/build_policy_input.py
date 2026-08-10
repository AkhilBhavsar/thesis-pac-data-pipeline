from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError


REQUIRED_EVIDENCE_SECTIONS = (
    "metadata",
    "schema_contract",
    "transformation",
    "privacy",
    "quality",
    "freshness",
    "runtime",
)

SCENARIOS = (
    "baseline",
    "schema_break",
    "pii_exposure",
    "freshness_breach",
    "quality_regression",
    "policy_false_positive",
)

TARGET_LAYERS = (
    "silver",
    "gold_internal",
    "gold_public",
)

STAGES = (
    "pre",
    "post",
)


def load_json(file_path: Path) -> Any:
    return json.loads(
        file_path.read_text(encoding="utf-8")
    )


def git_value(
    repo_root: Path,
    *arguments: str,
) -> str:
    completed = subprocess.run(
        [
            "git",
            "-C",
            str(repo_root),
            *arguments,
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    return completed.stdout.strip()


def resolve_git_metadata(
    repo_root: Path,
    branch_override: str | None,
    commit_override: str | None,
) -> tuple[str, str]:
    if branch_override:
        branch = branch_override
    else:
        branch = git_value(
            repo_root,
            "rev-parse",
            "--abbrev-ref",
            "HEAD",
        )

        if branch == "HEAD":
            raise ValueError(
                "Repository is in detached HEAD state. "
                "Provide --git-branch explicitly."
            )

    if commit_override:
        commit = commit_override
    else:
        commit = git_value(
            repo_root,
            "rev-parse",
            "HEAD",
        )

    if not branch.strip():
        raise ValueError(
            "Git branch must not be empty."
        )

    if not re.fullmatch(
        r"[0-9a-f]{40}",
        commit,
    ):
        raise ValueError(
            f"Git commit is not a 40-character SHA: {commit}"
        )

    return branch, commit


def parse_bool(value: str) -> bool:
    normalized = value.strip().lower()

    if normalized == "true":
        return True

    if normalized == "false":
        return False

    raise argparse.ArgumentTypeError(
        "Expected true or false."
    )


def validate_evidence_shape(
    evidence: dict[str, Any],
) -> None:
    expected = set(
        REQUIRED_EVIDENCE_SECTIONS
    )

    actual = set(evidence)

    missing = sorted(
        expected - actual
    )

    unexpected = sorted(
        actual - expected
    )

    if missing or unexpected:
        raise ValueError(
            "Evidence section mismatch. "
            f"missing={missing}, "
            f"unexpected={unexpected}"
        )


def validate_policy_input(
    schema: dict[str, Any],
    payload: dict[str, Any],
) -> None:
    Draft202012Validator.check_schema(
        schema
    )

    validator = Draft202012Validator(
        schema
    )

    errors = sorted(
        validator.iter_errors(payload),
        key=lambda error: (
            list(error.absolute_path),
            error.message,
        ),
    )

    if not errors:
        return

    details = []

    for error in errors:
        path = "/".join(
            str(part)
            for part in error.absolute_path
        )

        details.append(
            {
                "path": path,
                "message": error.message,
                "validator": error.validator,
            }
        )

    raise ValueError(
        "Generated policy input failed "
        "JSON Schema validation: "
        + json.dumps(
            details,
            sort_keys=True,
        )
    )


def canonical_bytes(
    payload: dict[str, Any],
) -> bytes:
    return (
        json.dumps(
            payload,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def write_atomic(
    output_path: Path,
    content: bytes,
) -> None:
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with tempfile.NamedTemporaryFile(
        mode="wb",
        dir=output_path.parent,
        prefix=f".{output_path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
        handle.write(content)
        handle.flush()

    temporary.replace(output_path)


def build_payload(
    *,
    stage: str,
    scenario: str,
    run_key: str,
    branch: str,
    commit: str,
    target_layer: str,
    promotion_requested: bool,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": "1.0.0",
        "evaluation_stage": stage,
        "experiment": {
            "condition": "C1",
            "scenario_id": scenario,
            "run_key": run_key,
        },
        "controls": {
            "policy_as_code_required": True,
            "self_healing_permitted": False,
            "automatic_remediation_permitted": False,
        },
        "git": {
            "branch": branch,
            "commit": commit,
        },
        "release": {
            "target_layer": target_layer,
            "promotion_requested": promotion_requested,
        },
    }

    for section in REQUIRED_EVIDENCE_SECTIONS:
        payload[section] = evidence[section]

    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Build a normalized C1 Policy-as-Code "
            "input from current Git metadata and "
            "collector-produced evidence."
        )
    )

    parser.add_argument(
        "--repo-root",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--schema",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--evidence",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--stage",
        required=True,
        choices=STAGES,
    )

    parser.add_argument(
        "--scenario",
        required=True,
        choices=SCENARIOS,
    )

    parser.add_argument(
        "--run-key",
        required=True,
    )

    parser.add_argument(
        "--target-layer",
        required=True,
        choices=TARGET_LAYERS,
    )

    parser.add_argument(
        "--promotion-requested",
        required=True,
        type=parse_bool,
    )

    parser.add_argument(
        "--git-branch",
    )

    parser.add_argument(
        "--git-commit",
    )

    parser.add_argument(
        "--output",
        required=True,
        type=Path,
    )

    args = parser.parse_args()

    try:
        if not args.run_key.strip():
            raise ValueError(
                "run-key must not be empty."
            )

        evidence = load_json(
            args.evidence
        )

        if not isinstance(
            evidence,
            dict,
        ):
            raise ValueError(
                "Evidence document must be "
                "a JSON object."
            )

        validate_evidence_shape(
            evidence
        )

        schema = load_json(
            args.schema
        )

        branch, commit = resolve_git_metadata(
            args.repo_root,
            args.git_branch,
            args.git_commit,
        )

        payload = build_payload(
            stage=args.stage,
            scenario=args.scenario,
            run_key=args.run_key,
            branch=branch,
            commit=commit,
            target_layer=args.target_layer,
            promotion_requested=(
                args.promotion_requested
            ),
            evidence=evidence,
        )

        validate_policy_input(
            schema,
            payload,
        )

        content = canonical_bytes(
            payload
        )

        write_atomic(
            args.output,
            content,
        )

        digest = hashlib.sha256(
            content
        ).hexdigest()

    except (
        OSError,
        json.JSONDecodeError,
        subprocess.CalledProcessError,
        SchemaError,
        ValueError,
    ) as error:
        print(
            json.dumps(
                {
                    "status": "ERROR",
                    "error": str(error),
                },
                indent=2,
                sort_keys=True,
            ),
            file=sys.stderr,
        )

        return 1

    print(
        json.dumps(
            {
                "status": "PASS",
                "output": str(
                    args.output
                ),
                "sha256": digest,
                "evaluation_stage": (
                    args.stage
                ),
                "scenario_id": (
                    args.scenario
                ),
                "git_branch": branch,
                "git_commit": commit,
                "target_layer": (
                    args.target_layer
                ),
                "promotion_requested": (
                    args.promotion_requested
                ),
            },
            indent=2,
            sort_keys=True,
        )
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
