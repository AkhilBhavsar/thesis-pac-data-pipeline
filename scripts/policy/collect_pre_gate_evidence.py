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


EXPECTED_SILVER = {
    "silver_customer_contact",
    "silver_customers",
    "silver_geolocation",
    "silver_order_items",
    "silver_orders",
    "silver_payments",
    "silver_product_categories",
    "silver_products",
    "silver_reviews",
    "silver_sellers",
}

EXPECTED_GOLD_INTERNAL = {
    "gold_customer_order_summary",
    "gold_daily_sales",
    "gold_product_category_revenue",
    "gold_sales_by_state",
}

EXPECTED_GOLD_PUBLIC = {
    "gold_public_sales_dashboard",
}

EXPECTED_GOLD = (
    EXPECTED_GOLD_INTERNAL
    | EXPECTED_GOLD_PUBLIC
)

REQUIRED_MODEL_FIELDS = (
    "name",
    "resource_type",
    "original_file_path",
    "config",
    "tags",
    "depends_on",
)


def read_json(file_path: Path) -> dict[str, Any]:
    payload = json.loads(
        file_path.read_text(encoding="utf-8")
    )

    if not isinstance(payload, dict):
        raise ValueError(
            f"{file_path} must contain a JSON object."
        )

    return payload


def run_git(
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

    return completed.stdout


def relative_repo_path(
    repo_root: Path,
    target_file: Path,
) -> str:
    resolved_root = repo_root.resolve()
    resolved_file = target_file.resolve()

    return str(
        resolved_file.relative_to(
            resolved_root
        )
    )


def parse_contract(
    sql_text: str,
) -> dict[str, dict[str, Any]]:
    pattern = re.compile(
        r"""
        \(
        \s*'([^']+)'\s*,
        \s*'([^']+)'\s*,
        \s*(\d+)\s*,
        \s*'([^']+)'\s*
        \)
        """,
        re.VERBOSE,
    )

    contracts: dict[
        str,
        dict[str, Any],
    ] = {}

    for (
        table_schema,
        table_name,
        ordinal_text,
        column_name,
    ) in pattern.findall(sql_text):
        ordinal = int(ordinal_text)

        entry = contracts.setdefault(
            table_name,
            {
                "schema": table_schema,
                "columns": {},
            },
        )

        columns = entry["columns"]

        if ordinal in columns:
            raise ValueError(
                f"Duplicate ordinal {ordinal} "
                f"for {table_name}."
            )

        columns[ordinal] = column_name

    if not contracts:
        raise ValueError(
            "No Gold contract tuples were found."
        )

    for model_name, contract in contracts.items():
        ordered = contract["columns"]

        expected_ordinals = list(
            range(
                1,
                len(ordered) + 1,
            )
        )

        if sorted(ordered) != expected_ordinals:
            raise ValueError(
                f"Non-contiguous contract ordinals "
                f"for {model_name}: "
                f"{sorted(ordered)}"
            )

    return contracts


def contract_columns(
    contract: dict[str, Any],
) -> list[str]:
    return [
        contract["columns"][ordinal]
        for ordinal in sorted(
            contract["columns"]
        )
    ]


def contract_differences(
    expected_columns: list[str],
    current_columns: list[str],
) -> tuple[list[str], list[str]]:
    maximum = max(
        len(expected_columns),
        len(current_columns),
    )

    missing: list[str] = []
    unexpected: list[str] = []

    for index in range(maximum):
        expected = (
            expected_columns[index]
            if index < len(expected_columns)
            else None
        )

        current = (
            current_columns[index]
            if index < len(current_columns)
            else None
        )

        if expected == current:
            continue

        if expected is not None:
            missing.append(expected)

        if current is not None:
            unexpected.append(current)

    return (
        sorted(set(missing)),
        sorted(set(unexpected)),
    )


def parse_privacy_rule(
    sql_text: str,
) -> tuple[list[str], str]:
    in_match = re.search(
        r"""
        lower\s*\(\s*column_name\s*\)
        \s+in\s*
        \(
        (.*?)
        \)
        """,
        sql_text,
        re.IGNORECASE | re.DOTALL | re.VERBOSE,
    )

    if not in_match:
        raise ValueError(
            "Could not locate forbidden-column IN list."
        )

    forbidden = sorted(
        set(
            re.findall(
                r"'([^']+)'",
                in_match.group(1),
            )
        )
    )

    regexp_match = re.search(
        r"""
        regexp_like\s*
        \(
        \s*lower\s*\(\s*column_name\s*\)\s*,
        \s*'([^']+)'
        """,
        sql_text,
        re.IGNORECASE | re.DOTALL | re.VERBOSE,
    )

    pattern = (
        regexp_match.group(1)
        if regexp_match
        else ""
    )

    return forbidden, pattern


def select_model_nodes(
    manifest: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    return {
        node.get("name"): node
        for node in manifest.get(
            "nodes",
            {},
        ).values()
        if (
            node.get("resource_type")
            == "model"
            and node.get("name")
        )
    }


def changed_model_names(
    repo_root: Path,
    base_ref: str,
    manifest_models: set[str],
) -> tuple[list[str], list[str]]:
    changed_text = run_git(
        repo_root,
        "diff",
        "--name-only",
        base_ref,
        "HEAD",
        "--",
        "transformations/dbt/models",
    )

    changed: list[str] = []
    unapproved: list[str] = []

    for raw_line in changed_text.splitlines():
        candidate = raw_line.strip()

        if not candidate.endswith(".sql"):
            continue

        model_name = Path(candidate).stem

        changed.append(model_name)

        if model_name not in manifest_models:
            unapproved.append(model_name)

    return (
        sorted(set(changed)),
        sorted(set(unapproved)),
    )


def atomic_write(
    output_path: Path,
    payload: dict[str, Any],
) -> None:
    content = (
        json.dumps(
            payload,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")

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


def collect(
    *,
    repo_root: Path,
    base_ref: str,
    manifest_path: Path,
    contract_path: Path,
    privacy_path: Path,
) -> dict[str, Any]:
    manifest_raw = manifest_path.read_bytes()

    manifest_sha = hashlib.sha256(
        manifest_raw
    ).hexdigest()

    manifest = json.loads(
        manifest_raw.decode("utf-8")
    )

    model_nodes = select_model_nodes(
        manifest
    )

    expected_inventory = (
        EXPECTED_SILVER
        | EXPECTED_GOLD
    )

    current_inventory = (
        set(model_nodes)
        & expected_inventory
    )

    inventory_exact = (
        current_inventory
        == expected_inventory
    )

    required_fields_present = (
        inventory_exact
        and all(
            all(
                field in model_nodes[model_name]
                for field in REQUIRED_MODEL_FIELDS
            )
            for model_name
            in expected_inventory
        )
    )

    contract_relative = relative_repo_path(
        repo_root,
        contract_path,
    )

    baseline_contract_text = run_git(
        repo_root,
        "show",
        f"{base_ref}:{contract_relative}",
    )

    current_contract_text = (
        contract_path.read_text(
            encoding="utf-8"
        )
    )

    baseline_contracts = parse_contract(
        baseline_contract_text
    )

    current_contracts = parse_contract(
        current_contract_text
    )

    if set(baseline_contracts) != EXPECTED_GOLD:
        raise ValueError(
            "Baseline Gold contract does not contain "
            "the exact five governed Gold models."
        )

    governed_models = []

    for model_name in sorted(EXPECTED_GOLD):
        expected_contract = baseline_contracts[
            model_name
        ]

        current_contract = current_contracts.get(
            model_name,
            {
                "schema": None,
                "columns": {},
            },
        )

        expected_columns = contract_columns(
            expected_contract
        )

        current_columns = contract_columns(
            current_contract
        )

        missing, unexpected = (
            contract_differences(
                expected_columns,
                current_columns,
            )
        )

        node = model_nodes.get(
            model_name,
            {},
        )

        tags = set(
            node.get(
                "tags",
                [],
            )
        )

        if "public" in tags:
            exposure = "public"
        elif "internal" in tags:
            exposure = "internal"
        else:
            exposure = (
                "public"
                if model_name in EXPECTED_GOLD_PUBLIC
                else "internal"
            )

        governed_models.append(
            {
                "model": model_name,
                "exposure": exposure,
                "expected_column_count": len(
                    expected_columns
                ),
                "actual_column_count": len(
                    current_columns
                ),
                "missing_columns": missing,
                "unexpected_columns": (
                    unexpected
                ),
                "incompatible_type_changes": [],
            }
        )

    privacy_text = privacy_path.read_text(
        encoding="utf-8"
    )

    forbidden_columns, privacy_pattern = (
        parse_privacy_rule(
            privacy_text
        )
    )

    public_models = sorted(
        model_name
        for model_name in EXPECTED_GOLD_PUBLIC
        if model_name in model_nodes
    )

    detected_forbidden: set[str] = set()

    compiled_pattern = (
        re.compile(
            privacy_pattern,
            re.IGNORECASE,
        )
        if privacy_pattern
        else None
    )

    forbidden_set = {
        value.lower()
        for value in forbidden_columns
    }

    for model_name in public_models:
        current_contract = current_contracts.get(
            model_name,
            {
                "columns": {},
            },
        )

        for column in contract_columns(
            current_contract
        ):
            normalized = column.lower()

            if normalized in forbidden_set:
                detected_forbidden.add(column)
                continue

            if (
                compiled_pattern is not None
                and compiled_pattern.search(
                    normalized
                )
            ):
                detected_forbidden.add(column)

    changed_models, unapproved = (
        changed_model_names(
            repo_root,
            base_ref,
            set(model_nodes),
        )
    )

    evidence = {
        "metadata": {
            "required_fields_present": (
                required_fields_present
            ),
            "resource_count": len(
                current_inventory
            ),
        },
        "schema_contract": {
            "governed_models": governed_models,
        },
        "transformation": {
            "changed_models": changed_models,
            "unapproved_definitions": (
                unapproved
            ),
            "manifest_sha256": manifest_sha,
        },
        "privacy": {
            "public_models": public_models,
            "forbidden_columns": (
                forbidden_columns
            ),
            "detected_forbidden_columns": (
                sorted(detected_forbidden)
            ),
        },
        "quality": {
            "status": "NOT_EVALUATED",
            "total_tests": 0,
            "failed_tests": 0,
            "critical_failures": [],
        },
        "freshness": {
            "status": "NOT_EVALUATED",
            "sources": [],
        },
        "runtime": {
            "pipeline_status": "NOT_RUN",
            "canonical_unchanged": True,
            "isolated_output_tables": 0,
            "athena_failed_queries": 0,
        },
    }

    return evidence


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Collect normalized C1 pre-gate evidence "
            "from the current dbt manifest and repository."
        )
    )

    parser.add_argument(
        "--repo-root",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--base-ref",
        required=True,
    )

    parser.add_argument(
        "--manifest",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--contract-sql",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--privacy-sql",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--output",
        type=Path,
        required=True,
    )

    args = parser.parse_args()

    try:
        evidence = collect(
            repo_root=args.repo_root,
            base_ref=args.base_ref,
            manifest_path=args.manifest,
            contract_path=args.contract_sql,
            privacy_path=args.privacy_sql,
        )

        atomic_write(
            args.output,
            evidence,
        )

        output_sha = hashlib.sha256(
            args.output.read_bytes()
        ).hexdigest()

    except (
        OSError,
        ValueError,
        json.JSONDecodeError,
        subprocess.CalledProcessError,
        re.error,
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
                "output": str(args.output),
                "sha256": output_sha,
                "resource_count": (
                    evidence[
                        "metadata"
                    ][
                        "resource_count"
                    ]
                ),
                "governed_gold_models": len(
                    evidence[
                        "schema_contract"
                    ][
                        "governed_models"
                    ]
                ),
                "public_models": (
                    evidence[
                        "privacy"
                    ][
                        "public_models"
                    ]
                ),
                "detected_forbidden_columns": (
                    evidence[
                        "privacy"
                    ][
                        "detected_forbidden_columns"
                    ]
                ),
                "changed_models": (
                    evidence[
                        "transformation"
                    ][
                        "changed_models"
                    ]
                ),
            },
            indent=2,
            sort_keys=True,
        )
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
