#!/usr/bin/env python3

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


CONTRACT_RELATIVE_PATH = Path(
    "transformations/dbt/tests/"
    "gold_contract_columns.sql"
)

TARGET_MODEL = (
    "gold_customer_order_summary"
)

TARGET_COLUMN = (
    "average_order_value"
)

TARGET_ORDINAL = 11

TARGET_PATTERN = re.compile(
    r"""
    ^
    [\t ]*
    \(
    [\t ]*
    '\{\{
    [\t ]*
    gold_internal_schema
    [\t ]*
    \}\}'
    [\t ]*
    ,
    [\t ]*
    'gold_customer_order_summary'
    [\t ]*
    ,
    [\t ]*
    11
    [\t ]*
    ,
    [\t ]*
    'average_order_value'
    [\t ]*
    \)
    ,
    [\t ]*
    $
    """,
    re.MULTILINE | re.VERBOSE,
)


def sha256_bytes(
    content: bytes,
) -> str:
    return hashlib.sha256(
        content
    ).hexdigest()


def atomic_write_text(
    target_file: Path,
    text: str,
) -> None:
    temporary = target_file.with_name(
        f".{target_file.name}.tmp"
    )

    temporary.write_text(
        text,
        encoding="utf-8",
    )

    temporary.replace(
        target_file
    )


def write_json(
    target_file: Path,
    payload: dict,
) -> None:
    atomic_write_text(
        target_file,
        json.dumps(
            payload,
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )


def inject_schema_break(
    *,
    repo_root: Path,
    evidence_dir: Path,
) -> dict:
    target_file = (
        repo_root
        / CONTRACT_RELATIVE_PATH
    )

    if not target_file.is_file():
        raise RuntimeError(
            "Schema-break target does not exist: "
            f"{target_file}"
        )

    before_bytes = (
        target_file.read_bytes()
    )

    before_text = before_bytes.decode(
        "utf-8"
    )

    matches = list(
        TARGET_PATTERN.finditer(
            before_text
        )
    )

    if len(matches) != 1:
        raise RuntimeError(
            "Expected exactly one schema-break "
            "target tuple; found "
            f"{len(matches)}."
        )

    match = matches[0]

    start = match.start()
    end = match.end()

    if (
        end < len(before_text)
        and before_text[end] == "\n"
    ):
        end += 1

    after_text = (
        before_text[:start]
        + before_text[end:]
    )

    if after_text == before_text:
        raise RuntimeError(
            "Schema-break injection "
            "produced no change."
        )

    if TARGET_PATTERN.search(
        after_text
    ):
        raise RuntimeError(
            "Schema-break target remained "
            "after injection."
        )

    atomic_write_text(
        target_file,
        after_text,
    )

    after_bytes = (
        target_file.read_bytes()
    )

    before_sha = sha256_bytes(
        before_bytes
    )

    after_sha = sha256_bytes(
        after_bytes
    )

    if before_sha == after_sha:
        raise RuntimeError(
            "Schema-break fingerprints "
            "did not change."
        )

    evidence_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    patch = "".join(
        difflib.unified_diff(
            before_text.splitlines(
                keepends=True
            ),
            after_text.splitlines(
                keepends=True
            ),
            fromfile=(
                "a/"
                + str(
                    CONTRACT_RELATIVE_PATH
                )
            ),
            tofile=(
                "b/"
                + str(
                    CONTRACT_RELATIVE_PATH
                )
            ),
        )
    )

    atomic_write_text(
        evidence_dir
        / "fault-injection.patch",
        patch,
    )

    payload = {
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
        "condition": "C1",
        "scenario_id": (
            "schema_break"
        ),
        "fault_class": (
            "breaking_governed_gold_"
            "schema_contract"
        ),
        "injection_scope": (
            "ephemeral_worktree"
        ),
        "target_file": str(
            CONTRACT_RELATIVE_PATH
        ),
        "target_model": TARGET_MODEL,
        "fault": {
            "operation": (
                "remove_required_contract_column"
            ),
            "column": TARGET_COLUMN,
            "ordinal": TARGET_ORDINAL,
        },
        "file_sha256_before": (
            before_sha
        ),
        "file_sha256_after": (
            after_sha
        ),
        "expected_effect": {
            "expected_column_count": 11,
            "actual_column_count": 10,
            "missing_columns": [
                TARGET_COLUMN
            ],
            "unexpected_columns": [],
            "primary_policy_id": (
                "PAC-SCHEMA-001"
            ),
            "release_policy_id": (
                "PAC-RELEASE-001"
            ),
            "evaluation_stage": "pre",
            "decision": "DENY",
            "pipeline_execution": False,
            "promotion": "BLOCKED",
        },
        "safety": {
            "canonical_data_mutated": (
                False
            ),
            "aws_mutation_performed": (
                False
            ),
            "self_healing_permitted": (
                False
            ),
            "automatic_remediation_permitted": (
                False
            ),
        },
    }

    write_json(
        evidence_dir
        / "fault-injection.json",
        payload,
    )

    return payload



def inject_pii_exposure(
    *,
    repo_root: Path,
    evidence_dir: Path,
) -> dict:
    target_file = (
        repo_root
        / CONTRACT_RELATIVE_PATH
    )

    if not target_file.is_file():
        raise RuntimeError(
            "PII-exposure target does not exist: "
            f"{target_file}"
        )

    before_bytes = (
        target_file.read_bytes()
    )

    before_text = before_bytes.decode(
        "utf-8"
    )

    safe_tuple = (
        "        ('{{ gold_public_schema }}', "
        "'gold_public_sales_dashboard', "
        "8, 'total_revenue')"
    )

    unsafe_tuple = (
        "        ('{{ gold_public_schema }}', "
        "'gold_public_sales_dashboard', "
        "9, 'synthetic_email')"
    )

    safe_matches = before_text.count(
        safe_tuple
    )

    unsafe_matches = before_text.count(
        unsafe_tuple
    )

    if safe_matches != 1:
        raise RuntimeError(
            "Expected exactly one public Gold "
            "terminal contract tuple; found "
            f"{safe_matches}."
        )

    if unsafe_matches != 0:
        raise RuntimeError(
            "PII exposure already appears "
            "to be injected."
        )

    replacement = (
        safe_tuple
        + ",\n"
        + unsafe_tuple
    )

    after_text = before_text.replace(
        safe_tuple,
        replacement,
        1,
    )

    if after_text == before_text:
        raise RuntimeError(
            "PII-exposure injection "
            "produced no change."
        )

    if after_text.count(
        unsafe_tuple
    ) != 1:
        raise RuntimeError(
            "Expected exactly one injected "
            "synthetic_email tuple."
        )

    atomic_write_text(
        target_file,
        after_text,
    )

    after_bytes = (
        target_file.read_bytes()
    )

    before_sha = sha256_bytes(
        before_bytes
    )

    after_sha = sha256_bytes(
        after_bytes
    )

    if before_sha == after_sha:
        raise RuntimeError(
            "PII-exposure fingerprints "
            "did not change."
        )

    evidence_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    patch = "".join(
        difflib.unified_diff(
            before_text.splitlines(
                keepends=True
            ),
            after_text.splitlines(
                keepends=True
            ),
            fromfile=(
                "a/"
                + str(
                    CONTRACT_RELATIVE_PATH
                )
            ),
            tofile=(
                "b/"
                + str(
                    CONTRACT_RELATIVE_PATH
                )
            ),
        )
    )

    atomic_write_text(
        evidence_dir
        / "fault-injection.patch",
        patch,
    )

    payload = {
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
        "condition": "C1",
        "scenario_id": (
            "pii_exposure"
        ),
        "fault_class": (
            "public_gold_structural_"
            "pii_exposure"
        ),
        "injection_scope": (
            "ephemeral_worktree"
        ),
        "target_file": str(
            CONTRACT_RELATIVE_PATH
        ),
        "target_model": (
            "gold_public_sales_dashboard"
        ),
        "fault": {
            "operation": (
                "add_forbidden_public_"
                "contract_column"
            ),
            "column": (
                "synthetic_email"
            ),
            "ordinal": 9,
        },
        "file_sha256_before": (
            before_sha
        ),
        "file_sha256_after": (
            after_sha
        ),
        "expected_effect": {
            "expected_column_count": 8,
            "actual_column_count": 9,
            "missing_columns": [],
            "unexpected_columns": [
                "synthetic_email"
            ],
            "detected_forbidden_columns": [
                "synthetic_email"
            ],
            "primary_policy_id": (
                "PAC-PRIVACY-001"
            ),
            "defence_in_depth_policy_id": (
                "PAC-SCHEMA-001"
            ),
            "release_policy_id": (
                "PAC-RELEASE-001"
            ),
            "evaluation_stage": "pre",
            "decision": "DENY",
            "pipeline_execution": False,
            "promotion": "BLOCKED",
        },
        "safety": {
            "canonical_data_mutated": (
                False
            ),
            "aws_mutation_performed": (
                False
            ),
            "self_healing_permitted": (
                False
            ),
            "automatic_remediation_permitted": (
                False
            ),
        },
    }

    write_json(
        evidence_dir
        / "fault-injection.json",
        payload,
    )

    return payload

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Apply a deterministic thesis "
            "fault scenario to an ephemeral "
            "experimental workspace."
        )
    )

    parser.add_argument(
        "--scenario",
        required=True,
        choices=[
            "schema_break",
            "pii_exposure",
        ],
    )

    parser.add_argument(
        "--repo-root",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--evidence-dir",
        required=True,
        type=Path,
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        repo_root = (
            args.repo_root
            .resolve()
        )

        evidence_dir = (
            args.evidence_dir
            .resolve()
        )

        if args.scenario == (
            "schema_break"
        ):
            payload = (
                inject_schema_break(
                    repo_root=repo_root,
                    evidence_dir=(
                        evidence_dir
                    ),
                )
            )
        elif args.scenario == (
            "pii_exposure"
        ):
            payload = (
                inject_pii_exposure(
                    repo_root=repo_root,
                    evidence_dir=(
                        evidence_dir
                    ),
                )
            )
        else:
            raise RuntimeError(
                "Unsupported scenario."
            )

    except (
        OSError,
        UnicodeDecodeError,
        RuntimeError,
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
                "scenario_id": (
                    payload[
                        "scenario_id"
                    ]
                ),
                "target_model": (
                    payload[
                        "target_model"
                    ]
                ),
                "removed_column": (
                    payload[
                        "fault"
                    ][
                        "column"
                    ]
                ),
                "file_sha256_before": (
                    payload[
                        "file_sha256_before"
                    ]
                ),
                "file_sha256_after": (
                    payload[
                        "file_sha256_after"
                    ]
                ),
                "evidence_dir": str(
                    args.evidence_dir
                ),
            },
            indent=2,
            sort_keys=True,
        )
    )

    return 0


if __name__ == "__main__":
    sys.exit(
        main()
    )
