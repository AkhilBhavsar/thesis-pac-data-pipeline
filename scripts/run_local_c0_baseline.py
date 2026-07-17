from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
RESULTS_DIR = ROOT / "experiments" / "results"
LOGS_DIR = ROOT / "logs" / "local_c0"

RESULTS_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)


STAGES = [
    {
        "stage_order": 1,
        "stage_name": "silver_build",
        "script": ROOT / "scripts" / "build_silver.py",
    },
    {
        "stage_order": 2,
        "stage_name": "silver_validation",
        "script": ROOT / "scripts" / "validate_silver.py",
    },
    {
        "stage_order": 3,
        "stage_name": "gold_build",
        "script": ROOT / "scripts" / "build_gold.py",
    },
    {
        "stage_order": 4,
        "stage_name": "gold_validation",
        "script": ROOT / "scripts" / "validate_gold.py",
    },
    {
        "stage_order": 5,
        "stage_name": "gold_contract_validation",
        "script": (
            ROOT
            / "scripts"
            / "validate_gold_contracts.py"
        ),
    },
]


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


def load_json(path: Path) -> dict[str, Any]:
    """Load a JSON evidence file when it exists."""
    if not path.exists():
        return {}

    with path.open(
        "r",
        encoding="utf-8",
    ) as file:
        data = json.load(file)

    if not isinstance(data, dict):
        raise ValueError(
            f"Expected a JSON object in {path}"
        )

    return data


def run_stage(
    run_id: str,
    run_log_dir: Path,
    stage: dict[str, Any],
) -> dict[str, Any]:
    """Execute one C0 pipeline stage."""
    stage_name = str(stage["stage_name"])
    script_path = Path(stage["script"])

    if not script_path.exists():
        raise FileNotFoundError(
            f"Pipeline script not found: {script_path}"
        )

    started_at = utc_now()

    print(
        "\n"
        + "=" * 72
    )
    print(
        f"Starting stage "
        f"{stage['stage_order']}: {stage_name}"
    )
    print(
        "=" * 72
    )

    environment = os.environ.copy()
    environment["PYTHONUNBUFFERED"] = "1"

    process = subprocess.run(
        [
            sys.executable,
            str(script_path),
        ],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )

    completed_at = utc_now()

    duration_seconds = round(
        (
            completed_at
            - started_at
        ).total_seconds(),
        4,
    )

    status = (
        "PASS"
        if process.returncode == 0
        else "FAIL"
    )

    log_path = (
        run_log_dir
        / f"{stage['stage_order']:02d}_{stage_name}.log"
    )

    log_content = (
        f"run_id: {run_id}\n"
        f"condition: C0\n"
        f"stage: {stage_name}\n"
        f"script: {script_path}\n"
        f"started_at: {started_at.isoformat()}\n"
        f"completed_at: {completed_at.isoformat()}\n"
        f"duration_seconds: {duration_seconds}\n"
        f"exit_code: {process.returncode}\n"
        f"status: {status}\n"
        "\n===== STDOUT =====\n"
        f"{process.stdout}"
        "\n===== STDERR =====\n"
        f"{process.stderr}"
    )

    log_path.write_text(
        log_content,
        encoding="utf-8",
    )

    if process.stdout:
        print(process.stdout.rstrip())

    if process.stderr:
        print(
            process.stderr.rstrip(),
            file=sys.stderr,
        )

    print(
        f"\nStage result: {status}"
    )
    print(
        f"Duration: {duration_seconds:.4f} seconds"
    )
    print(
        f"Log: {log_path}"
    )

    return {
        "run_id": run_id,
        "condition": "C0",
        "environment": "local",
        "stage_order": stage["stage_order"],
        "stage_name": stage_name,
        "script": str(
            script_path.relative_to(ROOT)
        ),
        "started_at": started_at.isoformat(),
        "completed_at": completed_at.isoformat(),
        "duration_seconds": duration_seconds,
        "exit_code": process.returncode,
        "status": status,
        "log_path": str(
            log_path.relative_to(ROOT)
        ),
    }


def collect_pipeline_evidence() -> dict[str, Any]:
    """Collect evidence created by the completed stages."""
    silver_build = load_json(
        RESULTS_DIR
        / "silver_build_summary.json"
    )

    silver_validation = load_json(
        RESULTS_DIR
        / "silver_validation_summary.json"
    )

    gold_build = load_json(
        RESULTS_DIR
        / "gold_build_summary.json"
    )

    gold_validation = load_json(
        RESULTS_DIR
        / "gold_validation_summary.json"
    )

    gold_contract_validation = load_json(
        RESULTS_DIR
        / "gold_contract_validation_summary.json"
    )

    gold_determinism = load_json(
        RESULTS_DIR
        / "gold_determinism_summary.json"
    )

    return {
        "silver_dataset_count": (
            silver_build.get(
                "dataset_count"
            )
        ),
        "silver_validation_status": (
            silver_validation.get(
                "overall_status"
            )
        ),
        "silver_validation_checks": (
            silver_validation.get(
                "total_checks"
            )
        ),
        "silver_validation_failures": (
            silver_validation.get(
                "failed_checks"
            )
        ),
        "gold_dataset_count": (
            gold_build.get(
                "dataset_count"
            )
        ),
        "delivered_order_count": (
            gold_build.get(
                "delivered_order_count"
            )
        ),
        "delivered_item_count": (
            gold_build.get(
                "delivered_item_count"
            )
        ),
        "gold_validation_status": (
            gold_validation.get(
                "overall_status"
            )
        ),
        "gold_validation_checks": (
            gold_validation.get(
                "total_checks"
            )
        ),
        "gold_validation_failures": (
            gold_validation.get(
                "failed_checks"
            )
        ),
        "gold_contract_status": (
            gold_contract_validation.get(
                "overall_status"
            )
        ),
        "gold_contract_count": (
            gold_contract_validation.get(
                "contract_count"
            )
        ),
        "gold_contract_checks": (
            gold_contract_validation.get(
                "total_checks"
            )
        ),
        "gold_contract_failures": (
            gold_contract_validation.get(
                "failed_checks"
            )
        ),
        "gold_determinism_validated_separately": (
            gold_determinism.get(
                "overall_status"
            )
            == "PASS"
        ),
        "gold_deterministic_datasets": (
            gold_determinism.get(
                "deterministic_datasets"
            )
        ),
    }


def main() -> None:
    """Run the complete local C0 reference pipeline."""
    pipeline_started_at = utc_now()

    run_id = (
        "local-c0-"
        + pipeline_started_at.strftime(
            "%Y%m%dT%H%M%SZ"
        )
    )

    run_log_dir = LOGS_DIR / run_id
    run_log_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    print(
        "Starting local end-to-end "
        "C0 baseline pipeline."
    )
    print(f"Run ID: {run_id}")
    print("Policy-as-Code enabled: false")
    print("Bounded self-healing enabled: false")

    stage_results: list[
        dict[str, Any]
    ] = []

    failed_stage: str | None = None

    for stage in STAGES:
        result = run_stage(
            run_id=run_id,
            run_log_dir=run_log_dir,
            stage=stage,
        )

        stage_results.append(result)

        if result["status"] == "FAIL":
            failed_stage = str(
                result["stage_name"]
            )
            break

    pipeline_completed_at = utc_now()

    total_duration_seconds = round(
        (
            pipeline_completed_at
            - pipeline_started_at
        ).total_seconds(),
        4,
    )

    passed_stages = sum(
        result["status"] == "PASS"
        for result in stage_results
    )

    failed_stages = sum(
        result["status"] == "FAIL"
        for result in stage_results
    )

    overall_status = (
        "PASS"
        if (
            failed_stages == 0
            and len(stage_results)
            == len(STAGES)
        )
        else "FAIL"
    )

    stage_results_frame = pd.DataFrame(
        stage_results
    )

    stage_results_path = (
        RESULTS_DIR
        / "local_c0_stage_results.csv"
    )

    stage_results_frame.to_csv(
        stage_results_path,
        index=False,
    )

    evidence = (
        collect_pipeline_evidence()
        if overall_status == "PASS"
        else {}
    )

    summary = {
        "run_id": run_id,
        "condition": "C0",
        "environment": "local",
        "description": (
            "Local reference pipeline without "
            "Policy-as-Code gates or bounded "
            "self-healing."
        ),
        "pipeline_started_at": (
            pipeline_started_at.isoformat()
        ),
        "pipeline_completed_at": (
            pipeline_completed_at.isoformat()
        ),
        "total_duration_seconds": (
            total_duration_seconds
        ),
        "overall_status": overall_status,
        "planned_stage_count": len(STAGES),
        "executed_stage_count": len(
            stage_results
        ),
        "passed_stages": passed_stages,
        "failed_stages": failed_stages,
        "failed_stage": failed_stage,
        "policy_as_code_enabled": False,
        "bounded_self_healing_enabled": False,
        "automatic_remediation_enabled": False,
        "source_profile_in_timed_pipeline": False,
        "determinism_check_in_timed_pipeline": False,
        "stage_results_path": str(
            stage_results_path.relative_to(ROOT)
        ),
        "run_log_directory": str(
            run_log_dir.relative_to(ROOT)
        ),
        "evidence": evidence,
    }

    summary_path = (
        RESULTS_DIR
        / "local_c0_run_summary.json"
    )

    summary_path.write_text(
        json.dumps(
            summary,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print(
        "\n"
        + "=" * 72
    )
    print("Local C0 baseline completed.")
    print(f"Overall status: {overall_status}")
    print(
        f"Stages passed: "
        f"{passed_stages}/{len(STAGES)}"
    )
    print(
        "Total duration: "
        f"{total_duration_seconds:.4f} seconds"
    )
    print(
        f"Stage results: {stage_results_path}"
    )
    print(f"Summary: {summary_path}")
    print("=" * 72)

    if overall_status != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()