#!/usr/bin/env python3
"""Finalize one matched C0 observation without policy or remediation."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


PRE_SCENARIOS = {
    "schema_break",
    "pii_exposure",
    "policy_false_positive",
}

POST_SCENARIOS = {
    "freshness_breach",
    "quality_regression",
}

MATCHED_SCENARIOS = PRE_SCENARIOS | POST_SCENARIOS


def load_optional(root: Path, relative: str) -> dict[str, Any] | None:
    path = root / relative
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"Evidence root must be an object: {relative}")
    return payload


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_manifest(root: Path) -> str:
    files = sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and path.name != "SHA256SUMS"
    )
    lines = []
    for path in files:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        lines.append(f"{digest}  {path.relative_to(root).as_posix()}")
    manifest = root / "SHA256SUMS"
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return hashlib.sha256(manifest.read_bytes()).hexdigest()


def finalize(
    *,
    evidence_root: Path,
    scenario: str,
    environment: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    if scenario not in MATCHED_SCENARIOS:
        raise RuntimeError(f"Unsupported C0 scenario: {scenario}")

    environment = os.environ if environment is None else environment
    evidence_root.mkdir(parents=True, exist_ok=True)
    exit_code_path = evidence_root / "c0-runner-exit-code.txt"
    exit_code = None
    if exit_code_path.is_file():
        exit_code = int(exit_code_path.read_text(encoding="utf-8").strip())

    pre_fault = load_optional(
        evidence_root,
        "pre-fault-injection/fault-injection.json",
    )
    post_fault = load_optional(
        evidence_root,
        "post-fault-injection/fault-injection.json",
    )
    canonical = load_optional(evidence_root, "canonical-comparison.json")
    checkpoint = load_optional(evidence_root, "final-checkpoint.json")
    failure = load_optional(evidence_root, "failure.json")

    expected_stage = "pre" if scenario in PRE_SCENARIOS else "post"
    fault = pre_fault if expected_stage == "pre" else post_fault
    fault_condition = fault.get("condition") if fault is not None else None
    fault_scenario = fault.get("scenario_id") if fault is not None else None
    canonical_changed = (
        canonical.get("changed") if canonical is not None else None
    )

    errors = []
    if exit_code is None:
        errors.append("C0 pipeline exit code is missing.")
    if fault_condition != "C0":
        errors.append("Fault evidence condition is not C0.")
    if fault_scenario != scenario:
        errors.append("Fault evidence scenario does not match the dispatch input.")
    if canonical_changed is not False:
        errors.append("Canonical comparison is missing or changed.")

    observed_outcome = (
        "NOT_EXECUTED"
        if exit_code is None
        else "PASS"
        if exit_code == 0
        else "FAIL"
    )

    payload: dict[str, Any] = {
        "schema_version": "1.0.0",
        "recorded_at_utc": (
            datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        ),
        "status": "PASS" if not errors else "FAIL",
        "condition": "C0",
        "condition_label": "Standard CI/CD tests only",
        "scenario_id": scenario,
        "fault_stage": expected_stage,
        "pipeline_exit_code": exit_code,
        "observed_pipeline_outcome": observed_outcome,
        "github_run_id": environment.get("GITHUB_RUN_ID"),
        "github_run_attempt": environment.get("GITHUB_RUN_ATTEMPT"),
        "branch": environment.get("GITHUB_REF_NAME"),
        "commit": environment.get("GITHUB_SHA"),
        "pipeline_checkpoint_present": checkpoint is not None,
        "pipeline_failure_present": failure is not None,
        "fault_evidence_present": fault is not None,
        "post_execution_fault_reached_evidence_boundary": (
            expected_stage == "post" and exit_code == 0 and post_fault is not None
        ),
        "canonical_mutation_performed": canonical_changed,
        "experiment_controls": {
            "policy_as_code_active": False,
            "opa_conftest_active": False,
            "self_healing_active": False,
            "automatic_remediation_active": False,
        },
        "evidence_manifest": "SHA256SUMS",
        "errors": errors,
    }

    write_json(evidence_root / "experiment-result.json", payload)
    write_manifest(evidence_root)

    if errors:
        raise RuntimeError(
            "C0 observation evidence finalization failed: "
            + "; ".join(errors)
        )

    return payload


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("--evidence-root", required=True, type=Path)
    result.add_argument("--scenario", required=True, choices=sorted(MATCHED_SCENARIOS))
    return result


def main() -> int:
    arguments = parser().parse_args()
    payload = finalize(
        evidence_root=arguments.evidence_root.resolve(),
        scenario=arguments.scenario,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
