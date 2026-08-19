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


FALSE_POSITIVE_SCENARIO = (
    "policy_false_positive"
)

FALSE_POSITIVE_TARGET_MODEL = (
    "gold_customer_order_summary"
)

FALSE_POSITIVE_COLUMN = (
    "synthetic_optional_note"
)

FALSE_POSITIVE_ORDINAL = 12

FALSE_POSITIVE_BASELINE_TUPLE = (
    "        ('{{ gold_internal_schema }}', "
    "'gold_customer_order_summary', "
    "11, 'average_order_value'),"
)

FALSE_POSITIVE_ADDITIVE_TUPLE = (
    "        ('{{ gold_internal_schema }}', "
    "'gold_customer_order_summary', "
    "12, 'synthetic_optional_note'),"
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



def inject_policy_false_positive(
    *,
    repo_root: Path,
    evidence_dir: Path,
) -> dict:
    contract_relative = (
        CONTRACT_RELATIVE_PATH
    )

    model_relative = Path(
        "transformations/dbt/models/"
        "gold/internal/"
        "gold_customer_order_summary.sql"
    )

    contract_file = (
        repo_root
        / contract_relative
    )

    model_file = (
        repo_root
        / model_relative
    )

    if not contract_file.is_file():
        raise RuntimeError(
            "False-positive contract target "
            "does not exist: "
            f"{contract_file}"
        )

    if not model_file.is_file():
        raise RuntimeError(
            "False-positive model target "
            "does not exist: "
            f"{model_file}"
        )

    contract_before_bytes = (
        contract_file.read_bytes()
    )

    model_before_bytes = (
        model_file.read_bytes()
    )

    contract_before = (
        contract_before_bytes.decode(
            "utf-8"
        )
    )

    model_before = (
        model_before_bytes.decode(
            "utf-8"
        )
    )

    contract_baseline = (
        "        ('{{ gold_internal_schema }}', "
        "'gold_customer_order_summary', "
        "11, 'average_order_value'),"
    )

    contract_additive = (
        "        ('{{ gold_internal_schema }}', "
        "'gold_customer_order_summary', "
        "12, 'synthetic_optional_note'),"
    )

    model_baseline = (
        "    ) as average_order_value\n"
        "\n"
        "from customer_totals as totals"
    )

    model_additive = (
        "    ) as average_order_value,\n"
        "\n"
        "    cast(\n"
        "        null as varchar\n"
        "    ) as synthetic_optional_note\n"
        "\n"
        "from customer_totals as totals"
    )

    if (
        contract_before.count(
            contract_baseline
        )
        != 1
    ):
        raise RuntimeError(
            "Expected exactly one false-positive "
            "baseline contract tuple."
        )

    if (
        contract_before.count(
            contract_additive
        )
        != 0
    ):
        raise RuntimeError(
            "False-positive additive change "
            "already appears injected."
        )

    if (
        model_before.count(
            model_baseline
        )
        != 1
    ):
        raise RuntimeError(
            "Expected exactly one false-positive "
            "model projection anchor."
        )

    if (
        "synthetic_optional_note"
        in model_before
    ):
        raise RuntimeError(
            "False-positive additive change "
            "already appears injected."
        )

    contract_after = (
        contract_before.replace(
            contract_baseline,
            (
                contract_baseline
                + "\n"
                + contract_additive
            ),
            1,
        )
    )

    model_after = (
        model_before.replace(
            model_baseline,
            model_additive,
            1,
        )
    )

    if contract_after == contract_before:
        raise RuntimeError(
            "False-positive contract injection "
            "produced no change."
        )

    if model_after == model_before:
        raise RuntimeError(
            "False-positive model injection "
            "produced no change."
        )

    if (
        contract_after.count(
            contract_additive
        )
        != 1
    ):
        raise RuntimeError(
            "Expected exactly one additive "
            "contract column."
        )

    if (
        model_after.count(
            "synthetic_optional_note"
        )
        != 1
    ):
        raise RuntimeError(
            "Expected exactly one additive "
            "model projection."
        )

    atomic_write_text(
        contract_file,
        contract_after,
    )

    atomic_write_text(
        model_file,
        model_after,
    )

    contract_after_bytes = (
        contract_file.read_bytes()
    )

    model_after_bytes = (
        model_file.read_bytes()
    )

    contract_sha_before = (
        sha256_bytes(
            contract_before_bytes
        )
    )

    contract_sha_after = (
        sha256_bytes(
            contract_after_bytes
        )
    )

    model_sha_before = (
        sha256_bytes(
            model_before_bytes
        )
    )

    model_sha_after = (
        sha256_bytes(
            model_after_bytes
        )
    )

    if (
        contract_sha_before
        == contract_sha_after
    ):
        raise RuntimeError(
            "False-positive contract fingerprint "
            "did not change."
        )

    if model_sha_before == model_sha_after:
        raise RuntimeError(
            "False-positive model fingerprint "
            "did not change."
        )

    evidence_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    contract_patch = "".join(
        difflib.unified_diff(
            contract_before.splitlines(
                keepends=True
            ),
            contract_after.splitlines(
                keepends=True
            ),
            fromfile=(
                "a/"
                + str(
                    contract_relative
                )
            ),
            tofile=(
                "b/"
                + str(
                    contract_relative
                )
            ),
        )
    )

    model_patch = "".join(
        difflib.unified_diff(
            model_before.splitlines(
                keepends=True
            ),
            model_after.splitlines(
                keepends=True
            ),
            fromfile=(
                "a/"
                + str(
                    model_relative
                )
            ),
            tofile=(
                "b/"
                + str(
                    model_relative
                )
            ),
        )
    )

    atomic_write_text(
        evidence_dir
        / "fault-injection.patch",
        (
            contract_patch
            + model_patch
        ),
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
            "policy_false_positive"
        ),
        "fault_class": (
            "safe_backward_compatible_"
            "additive_internal_schema_evolution"
        ),
        "injection_scope": (
            "ephemeral_worktree"
        ),
        "target_file": str(
            contract_relative
        ),
        "target_files": [
            str(contract_relative),
            str(model_relative),
        ],
        "target_model": (
            "gold_customer_order_summary"
        ),
        "fault": {
            "operation": (
                "add_backward_compatible_"
                "nullable_internal_column"
            ),
            "column": (
                "synthetic_optional_note"
            ),
            "ordinal": 12,
            "expression": (
                "cast(null as varchar)"
            ),
        },
        "ground_truth": {
            "classification": "SAFE",
            "expected_decision": "ALLOW",
            "compatibility_rule": (
                "nullable_additive_internal_"
                "column_is_backward_compatible"
            ),
            "change_type": (
                "additive_nullable_internal_"
                "column"
            ),
            "target_exposure": "internal",
            "required_columns_removed": 0,
            "existing_column_types_changed": 0,
            "existing_required_columns_retained": True,
            "new_column_nullable": True,
            "new_column_value_semantics": "NULL",
            "model_contract_aligned": True,
            "public_output_changed": False,
            "sensitive_field_added": False,
        },
        "file_sha256_before": (
            contract_sha_before
        ),
        "file_sha256_after": (
            contract_sha_after
        ),
        "contract_file_sha256_before": (
            contract_sha_before
        ),
        "contract_file_sha256_after": (
            contract_sha_after
        ),
        "model_file_sha256_before": (
            model_sha_before
        ),
        "model_file_sha256_after": (
            model_sha_after
        ),
        "expected_collector_effect": {
            "expected_column_count": 11,
            "actual_column_count": 12,
            "missing_columns": [],
            "unexpected_columns": [
                "synthetic_optional_note"
            ],
            "incompatible_type_changes": [],
            "exposure": "internal",
        },
        "expected_policy_effect": {
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
            "classification_if_observed": (
                "FALSE_POSITIVE"
            ),
            "blocked_safe_change": True,
        },
        "safety": {
            "canonical_data_mutated": False,
            "aws_mutation_performed": False,
            "public_gold_mutated": False,
            "self_healing_permitted": False,
            "automatic_remediation_permitted": False,
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
            "policy_false_positive",
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
        elif args.scenario == (
            "policy_false_positive"
        ):
            payload = (
                inject_policy_false_positive(
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
                "fault_operation": (
                    payload[
                        "fault"
                    ][
                        "operation"
                    ]
                ),
                "fault_column": (
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
