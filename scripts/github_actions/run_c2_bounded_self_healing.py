#!/usr/bin/env python3
"""
Run one deterministic C2 bounded self-healing execution.

This wrapper orchestrates already validated C2 components:
- policy decision projection
- remediation planning
- execution context preparation
- bounded remediation execution
- recovery verification

No direct canonical data mutation is permitted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


EXPECTED_BRANCH = "feature/c2-bounded-self-healing"
EXPECTED_CONDITION = "C2"


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def require_environment(name: str) -> str:
    value = os.getenv(name, "").strip()

    if not value:
        raise RuntimeError(
            f"Required environment variable missing: {name}"
        )

    return value


def canonical_json(
    payload: Any,
) -> str:
    return json.dumps(
        payload,
        indent=2,
        sort_keys=True,
    ) + "\n"


def write_json(
    path: Path,
    payload: Any,
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_text(
        canonical_json(payload),
        encoding="utf-8",
    )


def sha256_file(
    path: Path,
) -> str:
    return hashlib.sha256(
        path.read_bytes()
    ).hexdigest()


def run_command(
    command: list[str],
) -> None:
    print(
        "Executing:",
        " ".join(command),
    )

    result = subprocess.run(
        command,
        check=False,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed: {command}"
        )

def run_python_script(
    script: str,
    arguments: list[str],
) -> None:
    command = [
        sys.executable,
        script,
        *arguments,
    ]

    run_command(command)

def validate_environment() -> dict[str, str]:
    branch = require_environment(
        "THESIS_GIT_BRANCH"
    )

    condition = require_environment(
        "THESIS_EXPERIMENT_CONDITION"
    )

    scenario = require_environment(
        "THESIS_SCENARIO_ID"
    )

    commit = require_environment(
        "THESIS_GIT_COMMIT"
    )

    run_key = require_environment(
        "C2_RUN_KEY"
    )

    target_layer = require_environment(
        "C2_TARGET_LAYER"
    )

    if branch != EXPECTED_BRANCH:
        raise RuntimeError(
            f"Unexpected branch: {branch}"
        )

    if condition != EXPECTED_CONDITION:
        raise RuntimeError(
            f"Unexpected condition: {condition}"
        )
    return {
        "branch": branch,
        "condition": condition,
        "scenario": scenario,
        "commit": commit,
        "run_key": run_key,
        "target_layer": target_layer,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run deterministic C2 bounded "
            "self-healing orchestration."
        )
    )

    parser.add_argument(
        "--decision",
        required=True,
    )

    parser.add_argument(
        "--catalog",
        required=True,
    )

    parser.add_argument(
        "--decision-schema",
        required=True,
    )

    parser.add_argument(
        "--plan-schema",
        required=True,
    )

    parser.add_argument(
        "--context-schema",
        required=True,
    )

    parser.add_argument(
        "--result-schema",
        required=True,
    )

    parser.add_argument(
        "--opa-bin",
        required=True,
    )

    parser.add_argument(
        "--evidence-root",
        required=True,
    )

    return parser.parse_args()

def build_c2_decision(
    *,
    decision: str,
    catalog: str,
    schema: str,
    output: str,
) -> None:
    run_python_script(
        "scripts/policy/build_c2_policy_decision.py",
        [
            "--decision",
            decision,
            "--catalog",
            catalog,
            "--schema",
            schema,
            "--output",
            output,
        ],
    )

def build_c2_plan(
    *,
    decision: str,
    catalog: str,
    schema: str,
    output: str,
) -> None:
    run_python_script(
        "scripts/policy/build_c2_remediation_plan.py",
        [
            "--decision",
            decision,
            "--catalog",
            catalog,
            "--schema",
            schema,
            "--output",
            output,
        ],
    )


def build_c2_context(
    *,
    plan: str,
    schema: str,
    workspace_root: str,
    context_output: str,
    preparation_output: str,
) -> None:
    run_python_script(
        "scripts/remediation/build_c2_execution_context.py",
        [
            "--plan",
            plan,
            "--schema",
            schema,
            "--workspace-root",
            workspace_root,
            "--context-output",
            context_output,
            "--preparation-output",
            preparation_output,
        ],
    )

def execute_c2_remediation(
    *,
    plan: str,
    context: str,
    plan_schema: str,
    context_schema: str,
    result_schema: str,
    workspace_root: str,
    result_output: str,
    details_output: str,
) -> None:
    run_python_script(
        "scripts/remediation/execute_c2_remediation.py",
        [
            "--plan",
            plan,
            "--context",
            context,
            "--plan-schema",
            plan_schema,
            "--context-schema",
            context_schema,
            "--result-schema",
            result_schema,
            "--workspace-root",
            workspace_root,
            "--result-output",
            result_output,
            "--details-output",
            details_output,
        ],
    )

def verify_c2_recovery(
    *,
    plan: str,
    result: str,
    evidence: str,
    opa_bin: str,
    git_branch: str,
    git_commit: str,
    target_layer: str,
    verification_output: str,
    verified_result_output: str,
) -> None:
    run_python_script(
        "scripts/remediation/verify_c2_recovery.py",
        [
            "--plan",
            plan,
            "--result",
            result,
            "--evidence",
            evidence,
            "--opa-bin",
            opa_bin,
            "--git-branch",
            git_branch,
            "--git-commit",
            git_commit,
            "--target-layer",
            target_layer,
            "--verification-output",
            verification_output,
            "--verified-result-output",
            verified_result_output,
        ],
    )

def build_c2_fallback_request(
    *,
    plan: str,
    result: str,
    verification: str,
    catalog: str,
    schema: str,
    output: str,
) -> None:
    run_python_script(
        "scripts/remediation/build_c2_fallback_request.py",
        [
            "--plan",
            plan,
            "--result",
            result,
            "--verification",
            verification,
            "--catalog",
            catalog,
            "--schema",
            schema,
            "--output",
            output,
        ],
    )

def main() -> int:
    args = parse_args()

    environment = validate_environment()

    evidence_root = Path(
        args.evidence_root
    )

    evidence_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    runtime = {
        "timestamp": utc_now(),
        "environment": environment,
        "condition": "C2",
    }

    write_json(
        evidence_root / "c2-runtime-start.json",
        runtime,
    )

    decision_output = (
        evidence_root
        / "c2-policy-decision.json"
    )

    plan_output = (
        evidence_root
        / "remediation-plan.json"
    )

    context_output = (
        evidence_root
        / "execution-context.json"
    )

    preparation_output = (
        evidence_root
        / "execution-preparation.json"
    )

    workspace_root = (
        evidence_root
        / "workspace"
    )

    result_output = (
        evidence_root
        / "remediation-result.json"
    )

    details_output = (
        evidence_root
        / "remediation-details.json"
    )

    verification_output = (
        evidence_root
        / "recovery-verification.json"
    )

    verified_result_output = (
        evidence_root
        / "verified-result.json"
    )

    fallback_output = (
        evidence_root
        / "fallback-request.json"
    )

    build_c2_decision(
        decision=args.decision,
        catalog=args.catalog,
        schema=args.decision_schema,
        output=str(decision_output),
    )

    build_c2_plan(
        decision=str(decision_output),
        catalog=args.catalog,
        schema=args.plan_schema,
        output=str(plan_output),
    )

    build_c2_context(
        plan=str(plan_output),
        schema=args.context_schema,
        workspace_root=str(workspace_root),
        context_output=str(context_output),
        preparation_output=str(preparation_output),
    )

    execute_c2_remediation(
        plan=str(plan_output),
        context=str(context_output),
        plan_schema=args.plan_schema,
        context_schema=args.context_schema,
        result_schema=args.result_schema,
        workspace_root=str(workspace_root),
        result_output=str(result_output),
        details_output=str(details_output),
    )

    verify_c2_recovery(
        plan=str(plan_output),
        result=str(result_output),
        evidence=str(evidence_root),
        opa_bin=args.opa_bin,
        git_branch=environment["branch"],
        git_commit=environment["commit"],
        target_layer=environment["target_layer"],
        verification_output=str(verification_output),
        verified_result_output=str(verified_result_output),
    )

    build_c2_fallback_request(
        plan=str(plan_output),
        result=str(result_output),
        verification=str(verification_output),
        catalog=args.catalog,
        schema=(
            "policies/contracts/"
            "c2-fallback-request-input.schema.json"
        ),
        output=str(fallback_output),
    )

    write_json(
        evidence_root / "c2-runtime-complete.json",
        {
            "status": "PASS",
            "condition": "C2",
            "decision": str(decision_output),
            "plan": str(plan_output),
            "result": str(result_output),
            "verification": str(verification_output),
        },
    )

    print(
        "C2 bounded self-healing orchestration: PASS"
    )

    return 0
