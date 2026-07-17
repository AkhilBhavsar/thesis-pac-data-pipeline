from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import yaml


ROOT = Path(__file__).resolve().parents[1]

CONTRACT_DIR = ROOT / "governance" / "contracts"
RESULTS_DIR = ROOT / "experiments" / "results"
LOG_DIR = ROOT / "logs"

RESULTS_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)


DATASET_PATHS = {
    "gold_daily_sales": (
        ROOT
        / "data"
        / "gold"
        / "internal"
        / "gold_daily_sales.csv"
    ),
    "gold_sales_by_state": (
        ROOT
        / "data"
        / "gold"
        / "internal"
        / "gold_sales_by_state.csv"
    ),
    "gold_product_category_revenue": (
        ROOT
        / "data"
        / "gold"
        / "internal"
        / "gold_product_category_revenue.csv"
    ),
    "gold_customer_order_summary": (
        ROOT
        / "data"
        / "gold"
        / "internal"
        / "gold_customer_order_summary.csv"
    ),
    "gold_public_sales_dashboard": (
        ROOT
        / "data"
        / "gold"
        / "public"
        / "gold_public_sales_dashboard.csv"
    ),
}


DATASET_DESTINATIONS = {
    "gold_daily_sales": "gold/internal",
    "gold_sales_by_state": "gold/internal",
    "gold_product_category_revenue": "gold/internal",
    "gold_customer_order_summary": "gold/internal",
    "gold_public_sales_dashboard": "gold/public",
}


REQUIRED_CONTRACT_FIELDS = [
    "dataset",
    "version",
    "owner",
    "classification",
    "grain",
    "freshness_slo_hours",
    "allowed_destinations",
    "primary_key",
    "columns",
    "compatibility",
]


def record_check(
    results: list[dict[str, Any]],
    dataset: str,
    check_name: str,
    passed: bool,
    observed_value: Any,
    expected_value: Any,
    details: str = "",
    severity: str = "critical",
) -> None:
    """Append one contract-validation result."""
    results.append(
        {
            "dataset": dataset,
            "check_name": check_name,
            "status": "PASS" if passed else "FAIL",
            "severity": severity,
            "observed_value": observed_value,
            "expected_value": expected_value,
            "details": details,
        }
    )


def load_contract(path: Path) -> dict[str, Any]:
    """Load and validate the basic YAML document shape."""
    with path.open(
        "r",
        encoding="utf-8",
    ) as file:
        contract = yaml.safe_load(file)

    if not isinstance(contract, dict):
        raise ValueError(
            f"Contract must contain a YAML mapping: {path}"
        )

    return contract


def count_type_violations(
    series: pd.Series,
    declared_type: str,
) -> int:
    """Count values that do not match a contract data type."""
    non_null = series.dropna()

    if non_null.empty:
        return 0

    if declared_type == "string":
        return int(
            (
                ~non_null.map(
                    lambda value: isinstance(value, str)
                )
            ).sum()
        )

    if declared_type == "integer":
        numeric = pd.to_numeric(
            non_null,
            errors="coerce",
        )

        invalid_numeric = int(
            numeric.isna().sum()
        )

        valid_numeric = numeric.dropna()

        invalid_fractional = int(
            (
                valid_numeric.mod(1) != 0
            ).sum()
        )

        return (
            invalid_numeric
            + invalid_fractional
        )

    if declared_type == "decimal":
        numeric = pd.to_numeric(
            non_null,
            errors="coerce",
        )

        return int(
            numeric.isna().sum()
        )

    if declared_type == "date":
        parsed = pd.to_datetime(
            non_null,
            format="%Y-%m-%d",
            errors="coerce",
        )

        return int(
            parsed.isna().sum()
        )

    if declared_type == "boolean":
        accepted_values = {
            "true",
            "false",
            "1",
            "0",
            "yes",
            "no",
        }

        normalised = (
            non_null
            .astype("string")
            .str.lower()
        )

        return int(
            (
                ~normalised.isin(
                    accepted_values
                )
            ).sum()
        )

    return len(non_null)


def validate_contract(
    contract_path: Path,
    results: list[dict[str, Any]],
) -> None:
    """Validate one YAML contract against one generated dataset."""
    contract = load_contract(contract_path)

    dataset = str(
        contract.get(
            "dataset",
            contract_path.stem,
        )
    )

    expected_dataset_name = contract_path.stem

    record_check(
        results,
        dataset,
        "contract_dataset_matches_filename",
        dataset == expected_dataset_name,
        dataset,
        expected_dataset_name,
    )

    missing_top_level_fields = [
        field
        for field in REQUIRED_CONTRACT_FIELDS
        if field not in contract
    ]

    record_check(
        results,
        dataset,
        "required_contract_metadata_present",
        not missing_top_level_fields,
        (
            ", ".join(
                missing_top_level_fields
            )
            if missing_top_level_fields
            else "none"
        ),
        "none missing",
    )

    if dataset not in DATASET_PATHS:
        record_check(
            results,
            dataset,
            "known_gold_dataset",
            False,
            dataset,
            ", ".join(
                sorted(DATASET_PATHS)
            ),
        )
        return

    dataset_path = DATASET_PATHS[dataset]

    record_check(
        results,
        dataset,
        "gold_output_exists",
        dataset_path.exists(),
        str(
            dataset_path.relative_to(ROOT)
        ),
        "file exists",
    )

    if not dataset_path.exists():
        return

    dataframe = pd.read_csv(
        dataset_path,
        low_memory=False,
    )

    actual_destination = (
        DATASET_DESTINATIONS[dataset]
    )

    allowed_destinations = (
        contract.get(
            "allowed_destinations",
            [],
        )
        or []
    )

    forbidden_destinations = (
        contract.get(
            "forbidden_destinations",
            [],
        )
        or []
    )

    record_check(
        results,
        dataset,
        "destination_allowed",
        (
            actual_destination
            in allowed_destinations
        ),
        actual_destination,
        json.dumps(
            allowed_destinations
        ),
    )

    record_check(
        results,
        dataset,
        "destination_not_forbidden",
        (
            actual_destination
            not in forbidden_destinations
        ),
        actual_destination,
        json.dumps(
            forbidden_destinations
        ),
    )

    freshness = contract.get(
        "freshness_slo_hours"
    )

    freshness_valid = (
        isinstance(
            freshness,
            (int, float),
        )
        and freshness > 0
    )

    record_check(
        results,
        dataset,
        "freshness_slo_positive",
        freshness_valid,
        freshness,
        "> 0",
    )

    contract_columns = (
        contract.get(
            "columns",
            {},
        )
        or {}
    )

    if not isinstance(
        contract_columns,
        dict,
    ):
        record_check(
            results,
            dataset,
            "columns_mapping_valid",
            False,
            type(
                contract_columns
            ).__name__,
            "mapping",
        )
        return

    actual_columns = (
        dataframe.columns.tolist()
    )

    declared_columns = list(
        contract_columns.keys()
    )

    missing_declared_columns = [
        column
        for column in declared_columns
        if column not in actual_columns
    ]

    unexpected_columns = [
        column
        for column in actual_columns
        if column not in declared_columns
    ]

    record_check(
        results,
        dataset,
        "all_declared_columns_present",
        not missing_declared_columns,
        (
            ", ".join(
                missing_declared_columns
            )
            if missing_declared_columns
            else "none"
        ),
        "none missing",
    )

    compatibility = (
        contract.get(
            "compatibility",
            {},
        )
        or {}
    )

    allow_optional_columns = bool(
        compatibility.get(
            "allow_add_optional_column",
            False,
        )
    )

    unexpected_columns_valid = (
        not unexpected_columns
        or allow_optional_columns
    )

    record_check(
        results,
        dataset,
        "unexpected_columns_compatible",
        unexpected_columns_valid,
        (
            ", ".join(
                unexpected_columns
            )
            if unexpected_columns
            else "none"
        ),
        (
            "allowed"
            if allow_optional_columns
            else "none"
        ),
    )

    actual_declared_order = [
        column
        for column in actual_columns
        if column in declared_columns
    ]

    record_check(
        results,
        dataset,
        "declared_column_order_matches",
        (
            actual_declared_order
            == declared_columns
        ),
        json.dumps(
            actual_declared_order
        ),
        json.dumps(
            declared_columns
        ),
    )

    for column_name, rules in (
        contract_columns.items()
    ):
        if column_name not in dataframe.columns:
            continue

        if not isinstance(rules, dict):
            record_check(
                results,
                dataset,
                (
                    f"{column_name}_"
                    "column_rules_valid"
                ),
                False,
                type(rules).__name__,
                "mapping",
            )
            continue

        required = bool(
            rules.get(
                "required",
                False,
            )
        )

        declared_type = str(
            rules.get(
                "type",
                "",
            )
        ).lower()

        pii = bool(
            rules.get(
                "pii",
                False,
            )
        )

        null_count = int(
            dataframe[
                column_name
            ].isna().sum()
        )

        record_check(
            results,
            dataset,
            f"{column_name}_required_not_null",
            (
                null_count == 0
                if required
                else True
            ),
            null_count,
            (
                0
                if required
                else "nullable"
            ),
        )

        type_violations = (
            count_type_violations(
                dataframe[column_name],
                declared_type,
            )
        )

        record_check(
            results,
            dataset,
            f"{column_name}_type_{declared_type}",
            type_violations == 0,
            type_violations,
            0,
        )

        public_pii_valid = not (
            actual_destination
            == "gold/public"
            and pii
        )

        record_check(
            results,
            dataset,
            f"{column_name}_pii_destination_valid",
            public_pii_valid,
            pii,
            (
                False
                if actual_destination
                == "gold/public"
                else "internal permitted"
            ),
        )

    primary_key = (
        contract.get(
            "primary_key",
            [],
        )
        or []
    )

    missing_key_columns = [
        column
        for column in primary_key
        if column not in dataframe.columns
    ]

    record_check(
        results,
        dataset,
        "primary_key_columns_present",
        not missing_key_columns,
        (
            ", ".join(
                missing_key_columns
            )
            if missing_key_columns
            else "none"
        ),
        "none missing",
    )

    if not missing_key_columns:
        null_key_rows = int(
            dataframe[
                primary_key
            ]
            .isna()
            .any(axis=1)
            .sum()
        )

        duplicate_key_rows = int(
            dataframe.duplicated(
                subset=primary_key,
                keep=False,
            ).sum()
        )

        record_check(
            results,
            dataset,
            "primary_key_not_null",
            null_key_rows == 0,
            null_key_rows,
            0,
        )

        record_check(
            results,
            dataset,
            "primary_key_unique",
            duplicate_key_rows == 0,
            duplicate_key_rows,
            0,
        )

    forbidden_fields = (
        contract.get(
            "forbidden_fields",
            [],
        )
        or []
    )

    present_forbidden_fields = [
        field
        for field in forbidden_fields
        if field in dataframe.columns
    ]

    record_check(
        results,
        dataset,
        "forbidden_fields_absent",
        not present_forbidden_fields,
        (
            ", ".join(
                present_forbidden_fields
            )
            if present_forbidden_fields
            else "none"
        ),
        "none",
    )

    pii_columns = [
        column_name
        for column_name, rules
        in contract_columns.items()
        if isinstance(rules, dict)
        and bool(
            rules.get(
                "pii",
                False,
            )
        )
    ]

    classification = str(
        contract.get(
            "classification",
            "",
        )
    ).lower()

    public_safe_pii_valid = not (
        classification
        == "public-safe"
        and pii_columns
    )

    record_check(
        results,
        dataset,
        "public_safe_contract_has_no_pii",
        public_safe_pii_valid,
        (
            ", ".join(
                pii_columns
            )
            if pii_columns
            else "none"
        ),
        "none for Public-Safe",
    )

    required_compatibility_fields = [
        "allow_add_optional_column",
        "allow_remove_required_column",
        "allow_type_change_required_column",
    ]

    missing_compatibility_fields = [
        field
        for field
        in required_compatibility_fields
        if field not in compatibility
    ]

    record_check(
        results,
        dataset,
        "compatibility_rules_complete",
        not missing_compatibility_fields,
        (
            ", ".join(
                missing_compatibility_fields
            )
            if missing_compatibility_fields
            else "none"
        ),
        "none missing",
    )

    print(
        f"Validated contract: {dataset} "
        f"({len(dataframe):,} rows)"
    )


def main() -> None:
    """Validate all Gold contracts."""
    started_at = datetime.now(
        timezone.utc
    )

    print(
        "Starting Gold contract validation...\n"
    )

    results: list[
        dict[str, Any]
    ] = []

    contract_paths = sorted(
        CONTRACT_DIR.glob(
            "gold_*.yml"
        )
    )

    expected_contract_count = len(
        DATASET_PATHS
    )

    record_check(
        results,
        "_contract_set",
        "all_gold_contracts_present",
        (
            len(contract_paths)
            == expected_contract_count
        ),
        len(contract_paths),
        expected_contract_count,
    )

    for contract_path in contract_paths:
        try:
            validate_contract(
                contract_path,
                results,
            )
        except Exception as error:
            record_check(
                results,
                contract_path.stem,
                "contract_processed_without_error",
                False,
                type(error).__name__,
                "no exception",
                details=str(error),
            )

            print(
                f"Contract error: "
                f"{contract_path.name}: "
                f"{error}"
            )

    completed_at = datetime.now(
        timezone.utc
    )

    result_frame = pd.DataFrame(
        results
    )

    results_path = (
        RESULTS_DIR
        / "gold_contract_validation_results.csv"
    )

    result_frame.to_csv(
        results_path,
        index=False,
    )

    passed_checks = int(
        (
            result_frame["status"]
            == "PASS"
        ).sum()
    )

    failed_checks = int(
        (
            result_frame["status"]
            == "FAIL"
        ).sum()
    )

    critical_failures = int(
        (
            (
                result_frame["status"]
                == "FAIL"
            )
            & (
                result_frame["severity"]
                == "critical"
            )
        ).sum()
    )

    overall_status = (
        "PASS"
        if critical_failures == 0
        else "FAIL"
    )

    summary = {
        "validation_started_at": (
            started_at.isoformat()
        ),
        "validation_completed_at": (
            completed_at.isoformat()
        ),
        "duration_seconds": round(
            (
                completed_at
                - started_at
            ).total_seconds(),
            4,
        ),
        "contract_count": len(
            contract_paths
        ),
        "overall_status": overall_status,
        "total_checks": len(
            result_frame
        ),
        "passed_checks": passed_checks,
        "failed_checks": failed_checks,
        "critical_failures": (
            critical_failures
        ),
    }

    summary_path = (
        RESULTS_DIR
        / "gold_contract_validation_summary.json"
    )

    summary_path.write_text(
        json.dumps(
            summary,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    log_path = (
        LOG_DIR
        / "gold_contract_validation.log"
    )

    log_path.write_text(
        (
            "Gold contract validation completed.\n"
            f"Overall status: {overall_status}\n"
            f"Contracts: {len(contract_paths)}\n"
            f"Passed checks: {passed_checks}\n"
            f"Failed checks: {failed_checks}\n"
            f"Critical failures: "
            f"{critical_failures}\n"
            f"Results: {results_path}\n"
            f"Summary: {summary_path}\n"
        ),
        encoding="utf-8",
    )

    print(
        "\nGold contract validation completed."
    )
    print(
        f"Overall status: {overall_status}"
    )
    print(
        f"Contracts validated: "
        f"{len(contract_paths)}"
    )
    print(
        f"Passed checks: {passed_checks}"
    )
    print(
        f"Failed checks: {failed_checks}"
    )
    print(
        f"Critical failures: "
        f"{critical_failures}"
    )
    print(f"Results: {results_path}")
    print(f"Summary: {summary_path}")

    if critical_failures > 0:
        failures = result_frame[
            (
                result_frame["status"]
                == "FAIL"
            )
            & (
                result_frame["severity"]
                == "critical"
            )
        ]

        print("\nCritical failures:")

        print(
            failures[
                [
                    "dataset",
                    "check_name",
                    "observed_value",
                    "expected_value",
                    "details",
                ]
            ].to_string(
                index=False
            )
        )

        raise SystemExit(1)


if __name__ == "__main__":
    main()