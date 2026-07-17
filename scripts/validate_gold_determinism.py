from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
BUILD_SCRIPT = ROOT / "scripts" / "build_gold.py"
MANIFEST_PATH = (
    ROOT
    / "experiments"
    / "results"
    / "gold_build_manifest.csv"
)
RESULTS_DIR = ROOT / "experiments" / "results"
LOG_DIR = ROOT / "logs"

RESULTS_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)


def run_gold_build() -> pd.DataFrame:
    """Run the Gold build and return its manifest."""
    subprocess.run(
        [
            sys.executable,
            str(BUILD_SCRIPT),
        ],
        cwd=ROOT,
        check=True,
    )

    if not MANIFEST_PATH.exists():
        raise FileNotFoundError(
            f"Gold build manifest not found: {MANIFEST_PATH}"
        )

    return pd.read_csv(
        MANIFEST_PATH,
        low_memory=False,
    )


def main() -> None:
    started_at = datetime.now(timezone.utc)

    print("Starting Gold determinism validation...\n")
    print("Executing Gold build run 1...\n")

    first_manifest = run_gold_build()[
        [
            "dataset",
            "dataset_hash_sha256",
            "row_count",
            "column_count",
        ]
    ].rename(
        columns={
            "dataset_hash_sha256": "hash_run_1",
            "row_count": "row_count_run_1",
            "column_count": "column_count_run_1",
        }
    )

    print("\nExecuting Gold build run 2...\n")

    second_manifest = run_gold_build()[
        [
            "dataset",
            "dataset_hash_sha256",
            "row_count",
            "column_count",
        ]
    ].rename(
        columns={
            "dataset_hash_sha256": "hash_run_2",
            "row_count": "row_count_run_2",
            "column_count": "column_count_run_2",
        }
    )

    comparison = first_manifest.merge(
        second_manifest,
        on="dataset",
        how="outer",
        validate="one_to_one",
    )

    comparison["hash_matches"] = (
        comparison["hash_run_1"]
        == comparison["hash_run_2"]
    )

    comparison["row_count_matches"] = (
        comparison["row_count_run_1"]
        == comparison["row_count_run_2"]
    )

    comparison["column_count_matches"] = (
        comparison["column_count_run_1"]
        == comparison["column_count_run_2"]
    )

    comparison["deterministic"] = (
        comparison[
            [
                "hash_matches",
                "row_count_matches",
                "column_count_matches",
            ]
        ].all(axis=1)
    )

    completed_at = datetime.now(timezone.utc)

    result_path = (
        RESULTS_DIR
        / "gold_determinism_results.csv"
    )

    comparison.to_csv(
        result_path,
        index=False,
    )

    deterministic_count = int(
        comparison["deterministic"].sum()
    )

    failure_count = int(
        (~comparison["deterministic"]).sum()
    )

    overall_status = (
        "PASS"
        if failure_count == 0
        else "FAIL"
    )

    summary = {
        "validation_started_at": started_at.isoformat(),
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
        "overall_status": overall_status,
        "dataset_count": len(comparison),
        "deterministic_datasets": deterministic_count,
        "failed_datasets": failure_count,
    }

    summary_path = (
        RESULTS_DIR
        / "gold_determinism_summary.json"
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
        / "gold_determinism.log"
    )

    log_path.write_text(
        (
            "Gold determinism validation completed.\n"
            f"Overall status: {overall_status}\n"
            f"Datasets checked: {len(comparison)}\n"
            f"Deterministic datasets: {deterministic_count}\n"
            f"Failed datasets: {failure_count}\n"
            f"Results: {result_path}\n"
            f"Summary: {summary_path}\n"
        ),
        encoding="utf-8",
    )

    print("\nGold determinism validation completed.")
    print(f"Overall status: {overall_status}")
    print(f"Datasets checked: {len(comparison)}")
    print(
        "Deterministic datasets: "
        f"{deterministic_count}"
    )
    print(f"Failed datasets: {failure_count}")
    print(f"Results: {result_path}")
    print(f"Summary: {summary_path}")

    print(
        "\n"
        + comparison[
            [
                "dataset",
                "hash_matches",
                "row_count_matches",
                "column_count_matches",
                "deterministic",
            ]
        ].to_string(index=False)
    )

    if failure_count > 0:
        raise SystemExit(1)


if __name__ == "__main__":
    main()