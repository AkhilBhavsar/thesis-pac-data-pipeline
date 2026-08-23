#!/usr/bin/env python3

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from jsonschema import (
    Draft202012Validator,
    FormatChecker,
)


class VerificationError(RuntimeError):
    pass


CHECK_POLICY_IDS = {
    "schema_contract": "PAC-SCHEMA-001",
    "privacy": "PAC-PRIVACY-001",
    "freshness": "PAC-FRESH-001",
    "quality": "PAC-QUALITY-001",
    "runtime": "PAC-RUNTIME-001",
    "release_policy": "PAC-RELEASE-001",
}


OpaEvaluator = Callable[
    [
        Path,
        dict[str, Any],
        Path,
    ],
    tuple[
        bool,
        list[dict[str, Any]],
        float,
    ],
]


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def load_json(path: Path) -> Any:
    try:
        return json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )
    except FileNotFoundError as exc:
        raise VerificationError(
            f"JSON file does not exist: {path}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise VerificationError(
            f"Invalid JSON in {path}: {exc}"
        ) from exc


def canonical_bytes(
    payload: Any,
) -> bytes:
    return (
        json.dumps(
            payload,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
        + "\n"
    ).encode("utf-8")


def sha256_bytes(
    payload: bytes,
) -> str:
    return hashlib.sha256(
        payload
    ).hexdigest()


def sha256_file(
    path: Path,
) -> str:
    return hashlib.sha256(
        path.read_bytes()
    ).hexdigest()


def validate_document(
    *,
    schema: dict[str, Any],
    document: Any,
    label: str,
) -> None:
    Draft202012Validator.check_schema(
        schema
    )

    validator = Draft202012Validator(
        schema,
        format_checker=FormatChecker(),
    )

    errors = sorted(
        validator.iter_errors(document),
        key=lambda error: (
            list(error.absolute_path),
            error.message,
        ),
    )

    if not errors:
        return

    rendered = []

    for error in errors:
        location = ".".join(
            str(part)
            for part in error.absolute_path
        )

        rendered.append(
            f"{location or '<root>'}: "
            f"{error.message}"
        )

    raise VerificationError(
        f"{label} validation failed: "
        + " | ".join(rendered)
    )


def derive_c2_policy_input_schema(
    base_schema: dict[str, Any],
) -> dict[str, Any]:
    schema = copy.deepcopy(
        base_schema
    )

    schema["title"] = (
        "C2 Recovery Verification "
        "Normalized Policy Input"
    )

    schema["description"] = (
        "Derived in-memory C2 verification "
        "contract preserving the established "
        "normalized Policy-as-Code evidence shape."
    )

    experiment = (
        schema[
            "properties"
        ][
            "experiment"
        ][
            "properties"
        ]
    )

    experiment[
        "condition"
    ] = {
        "const": "C2"
    }

    controls = (
        schema[
            "properties"
        ][
            "controls"
        ][
            "properties"
        ]
    )

    controls[
        "policy_as_code_required"
    ] = {
        "const": True
    }

    controls[
        "self_healing_permitted"
    ] = {
        "const": True
    }

    controls[
        "automatic_remediation_permitted"
    ] = {
        "type": "boolean"
    }

    return schema


def policy_bundle_sha256(
    *,
    repo_root: Path,
    derived_input_schema: dict[str, Any],
) -> str:
    catalog = (
        repo_root
        / "policies"
        / "catalog"
        / "policy-catalog.json"
    )

    policy_dir = (
        repo_root
        / "policies"
        / "rego"
    )

    policies = sorted(
        policy_dir.glob("*.rego"),
        key=lambda path: path.name,
    )

    if not policies:
        raise VerificationError(
            "No Rego policy files found."
        )

    components = [
        (
            "policies/catalog/"
            "policy-catalog.json",
            sha256_file(catalog),
        ),
        (
            "derived:c2-policy-input.schema.json",
            sha256_bytes(
                canonical_bytes(
                    derived_input_schema
                )
            ),
        ),
    ]

    for path in policies:
        components.append(
            (
                str(
                    path.relative_to(
                        repo_root
                    )
                ),
                sha256_file(path),
            )
        )

    material = "".join(
        f"{digest}  {name}\n"
        for name, digest in components
    ).encode("utf-8")

    return hashlib.sha256(
        material
    ).hexdigest()


def evaluate_opa(
    opa_bin: Path,
    input_payload: dict[str, Any],
    policy_dir: Path,
) -> tuple[
    bool,
    list[dict[str, Any]],
    float,
]:
    resolved_opa = shutil.which(
        str(opa_bin)
    )

    if resolved_opa is None:
        raise VerificationError(
            f"OPA executable cannot be resolved: "
            f"{opa_bin}"
        )

    policies = sorted(
        policy_dir.glob("*.rego"),
        key=lambda path: path.name,
    )

    if not policies:
        raise VerificationError(
            "No Rego policy files found."
        )

    query = (
        '{"allow": data.thesis.pac.allow, '
        '"violations": data.thesis.pac.violations}'
    )

    with tempfile.TemporaryDirectory() as temp:
        input_path = (
            Path(temp)
            / "c2-verification-input.json"
        )

        input_path.write_bytes(
            canonical_bytes(
                input_payload
            )
        )

        command = [
            resolved_opa,
            "eval",
            "--format=json",
        ]

        for policy in policies:
            command.extend(
                [
                    "--data",
                    str(policy),
                ]
            )

        command.extend(
            [
                "--input",
                str(input_path),
                query,
            ]
        )

        started = time.perf_counter_ns()

        process = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
        )

        finished = time.perf_counter_ns()

    evaluation_ms = round(
        (
            finished
            - started
        )
        / 1_000_000,
        3,
    )

    if process.returncode != 0:
        raise VerificationError(
            "OPA recovery verification failed: "
            + process.stderr.strip()
        )

    try:
        payload = json.loads(
            process.stdout
        )

        value = (
            payload[
                "result"
            ][0][
                "expressions"
            ][0][
                "value"
            ]
        )

    except (
        json.JSONDecodeError,
        KeyError,
        IndexError,
        TypeError,
    ) as exc:
        raise VerificationError(
            "OPA result did not contain "
            "the expected verification value."
        ) from exc

    if not isinstance(
        value,
        dict,
    ):
        raise VerificationError(
            "OPA verification value must "
            "be an object."
        )

    allow = value.get(
        "allow"
    )

    violations = value.get(
        "violations"
    )

    if not isinstance(
        allow,
        bool,
    ):
        raise VerificationError(
            "OPA allow result is not boolean."
        )

    if not isinstance(
        violations,
        list,
    ):
        raise VerificationError(
            "OPA violations result is not "
            "an array."
        )

    normalized = []

    for violation in violations:
        if not isinstance(
            violation,
            dict,
        ):
            raise VerificationError(
                "OPA violation must be "
                "an object."
            )

        policy_id = violation.get(
            "policy_id"
        )

        if (
            not isinstance(
                policy_id,
                str,
            )
            or not policy_id
        ):
            raise VerificationError(
                "OPA violation has no "
                "policy_id."
            )

        normalized.append(
            violation
        )

    normalized.sort(
        key=lambda item: (
            str(
                item.get(
                    "policy_id",
                    "",
                )
            ),
            str(
                item.get(
                    "reason",
                    "",
                )
            ),
        )
    )

    return (
        allow,
        normalized,
        evaluation_ms,
    )


def validate_sha256(
    value: str,
    *,
    label: str,
) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(
            character
            not in "0123456789abcdef"
            for character in value
        )
    ):
        raise VerificationError(
            f"{label} must be a "
            "64-character lowercase SHA-256."
        )

    return value


def scenario_from_catalog(
    *,
    catalog: dict[str, Any],
    scenario_id: str,
) -> dict[str, Any]:
    if catalog.get(
        "condition"
    ) != "C2":
        raise VerificationError(
            "Remediation catalog is not C2."
        )

    scenarios = catalog.get(
        "scenarios"
    )

    if (
        not isinstance(
            scenarios,
            dict,
        )
        or scenario_id not in scenarios
    ):
        raise VerificationError(
            "Scenario is not present in "
            "the C2 catalog."
        )

    scenario = scenarios[
        scenario_id
    ]

    if not isinstance(
        scenario,
        dict,
    ):
        raise VerificationError(
            "C2 scenario definition must "
            "be an object."
        )

    return scenario


def verify_plan_catalog_alignment(
    *,
    plan: dict[str, Any],
    scenario: dict[str, Any],
) -> None:
    body = plan.get(
        "plan",
        {},
    )

    expected = {
        "primary_action": scenario[
            "primary_action"
        ],
        "fallback_action": scenario[
            "fallback_action"
        ],
        "max_attempts": scenario[
            "max_attempts"
        ],
        "timeout_seconds": scenario[
            "timeout_seconds"
        ],
        "target_scope": scenario[
            "target_scope"
        ],
        "verification": scenario[
            "verification"
        ],
        "canonical_mutation_before_verification": False,
    }

    for field, value in expected.items():
        if body.get(field) != value:
            raise VerificationError(
                "Remediation plan drifted "
                f"from the C2 catalog: {field}"
            )

    automatic = scenario[
        "automatic_remediation_permitted"
    ]

    controls = plan.get(
        "controls",
        {},
    )

    if (
        controls.get(
            "automatic_remediation_permitted"
        )
        is not automatic
    ):
        raise VerificationError(
            "Plan automatic-remediation "
            "control does not match catalog."
        )


def verify_plan_result_identity(
    *,
    plan: dict[str, Any],
    result: dict[str, Any],
    plan_sha256: str,
) -> None:
    for field in (
        "condition",
        "scenario_id",
        "run_key",
    ):
        if (
            plan.get(field)
            != result.get(field)
        ):
            raise VerificationError(
                f"Plan/result {field} mismatch."
            )

    if (
        result.get(
            "source_remediation_plan_sha256"
        )
        != plan_sha256
    ):
        raise VerificationError(
            "Result remediation-plan "
            "fingerprint mismatch."
        )

    if (
        result.get(
            "action"
        )
        != plan[
            "plan"
        ][
            "primary_action"
        ]
    ):
        raise VerificationError(
            "Result action does not match plan."
        )

    if (
        result.get(
            "mode"
        )
        != plan[
            "plan"
        ][
            "mode"
        ]
    ):
        raise VerificationError(
            "Result mode does not match plan."
        )

    if (
        result.get(
            "canonical_mutation_performed"
        )
        is not False
    ):
        raise VerificationError(
            "Canonical mutation must remain false."
        )


def build_policy_input(
    *,
    plan: dict[str, Any],
    scenario: dict[str, Any],
    evidence: dict[str, Any],
    branch: str,
    commit: str,
    target_layer: str,
) -> dict[str, Any]:
    required_sections = (
        "metadata",
        "schema_contract",
        "transformation",
        "privacy",
        "quality",
        "freshness",
        "runtime",
    )

    missing = [
        section
        for section in required_sections
        if section not in evidence
    ]

    if missing:
        raise VerificationError(
            "Recovery evidence is missing "
            f"sections: {missing}"
        )

    payload = {
        "schema_version": "1.0.0",
        "evaluation_stage": scenario[
            "detection_stage"
        ],
        "experiment": {
            "condition": "C2",
            "scenario_id": plan[
                "scenario_id"
            ],
            "run_key": plan[
                "run_key"
            ],
        },
        "controls": {
            "policy_as_code_required": True,
            "self_healing_permitted": True,
            "automatic_remediation_permitted": (
                scenario[
                    "automatic_remediation_permitted"
                ]
            ),
        },
        "git": {
            "branch": branch,
            "commit": commit,
        },
        "release": {
            "target_layer": target_layer,
            "promotion_requested": True,
        },
    }

    for section in required_sections:
        payload[
            section
        ] = evidence[
            section
        ]

    return payload


def check_results(
    *,
    required_checks: list[str],
    triggered_policy_ids: set[str],
) -> list[dict[str, Any]]:
    results = []

    for check in required_checks:
        if check == "manual_policy_review":
            results.append(
                {
                    "check": check,
                    "status": "PENDING",
                    "policy_id": None,
                }
            )
            continue

        policy_id = CHECK_POLICY_IDS.get(
            check
        )

        if policy_id is None:
            raise VerificationError(
                "Unsupported automatic "
                f"verification check: {check}"
            )

        results.append(
            {
                "check": check,
                "status": (
                    "FAIL"
                    if policy_id
                    in triggered_policy_ids
                    else "PASS"
                ),
                "policy_id": policy_id,
            }
        )

    return results


def parse_utc(
    value: str,
) -> datetime:
    try:
        parsed = datetime.fromisoformat(
            value.replace(
                "Z",
                "+00:00",
            )
        )
    except ValueError as exc:
        raise VerificationError(
            f"Invalid timestamp: {value}"
        ) from exc

    if parsed.tzinfo is None:
        raise VerificationError(
            "Timestamp must be timezone-aware."
        )

    return parsed.astimezone(
        timezone.utc
    )


def build_verified_result(
    *,
    source_result: dict[str, Any],
    verification_sha256: str,
    completed_at: str,
) -> dict[str, Any]:
    result = copy.deepcopy(
        source_result
    )

    fault_at = parse_utc(
        str(
            source_result[
                "fault_detected_at_utc"
            ]
        )
    )

    completed = parse_utc(
        completed_at
    )

    recovery_ms = (
        completed
        - fault_at
    ).total_seconds() * 1000.0

    if recovery_ms < 0:
        raise VerificationError(
            "Verification completed before "
            "fault detection."
        )

    result[
        "verification"
    ] = {
        "required": True,
        "status": "PASS",
        "evidence_sha256": (
            verification_sha256
        ),
    }

    result[
        "terminal_state"
    ] = "RECOVERED"

    result[
        "execution_status"
    ] = "SUCCEEDED"

    result[
        "self_healing_performed"
    ] = True

    result[
        "recovery_time_ms"
    ] = round(
        recovery_ms,
        3,
    )

    return result


def verify_recovery(
    *,
    plan: dict[str, Any],
    result: dict[str, Any],
    evidence: dict[str, Any],
    catalog: dict[str, Any],
    base_policy_input_schema: dict[str, Any],
    plan_schema: dict[str, Any],
    result_schema: dict[str, Any],
    verification_schema: dict[str, Any],
    repo_root: Path,
    branch: str,
    commit: str,
    target_layer: str,
    opa_bin: Path | None,
    plan_artifact_sha256: str,
    result_artifact_sha256: str,
    evidence_artifact_sha256: str,
    evaluator: OpaEvaluator = evaluate_opa,
    started_at: str | None = None,
    completed_at: str | None = None,
) -> tuple[
    dict[str, Any],
    dict[str, Any] | None,
]:
    validate_document(
        schema=plan_schema,
        document=plan,
        label="Remediation plan",
    )

    validate_document(
        schema=result_schema,
        document=result,
        label="Remediation result",
    )

    if plan.get(
        "condition"
    ) != "C2":
        raise VerificationError(
            "Verifier accepts only C2 plans."
        )

    scenario_id = plan[
        "scenario_id"
    ]

    scenario = scenario_from_catalog(
        catalog=catalog,
        scenario_id=scenario_id,
    )

    verify_plan_catalog_alignment(
        plan=plan,
        scenario=scenario,
    )

    plan_sha = validate_sha256(
        plan_artifact_sha256,
        label="Plan artifact SHA-256",
    )

    result_sha = validate_sha256(
        result_artifact_sha256,
        label="Result artifact SHA-256",
    )

    evidence_sha = validate_sha256(
        evidence_artifact_sha256,
        label="Evidence artifact SHA-256",
    )

    verify_plan_result_identity(
        plan=plan,
        result=result,
        plan_sha256=plan_sha,
    )

    required_checks = list(
        scenario[
            "verification"
        ]
    )

    automatic = scenario[
        "automatic_remediation_permitted"
    ]

    started = (
        started_at
        if started_at is not None
        else utc_now()
    )

    completed = (
        completed_at
        if completed_at is not None
        else utc_now()
    )

    if automatic is False:
        if (
            plan[
                "plan"
            ][
                "mode"
            ]
            != "manual"
        ):
            raise VerificationError(
                "Non-automatic scenario must "
                "remain manual."
            )

        if result.get(
            "automatic_remediation_performed"
        ) is not False:
            raise VerificationError(
                "Manual scenario cannot report "
                "automatic remediation."
            )

        checks = check_results(
            required_checks=required_checks,
            triggered_policy_ids=set(),
        )

        artifact = {
            "schema_version": "1.0.0",
            "condition": "C2",
            "scenario_id": scenario_id,
            "run_key": plan[
                "run_key"
            ],
            "mode": "manual",
            "automatic_remediation_permitted": False,
            "source_remediation_plan_sha256": plan_sha,
            "source_remediation_result_sha256": result_sha,
            "source_evidence_sha256": evidence_sha,
            "verification_started_at_utc": started,
            "verification_completed_at_utc": completed,
            "required_checks": required_checks,
            "check_results": checks,
            "policy_input": None,
            "policy_input_sha256": None,
            "policy_input_contract_sha256": None,
            "policy_bundle_sha256": None,
            "policy_evaluation_ms": 0.0,
            "policy_allow": None,
            "triggered_policy_ids": [],
            "violations": [],
            "verification_status": "MANUAL_REQUIRED",
            "promotion_requested": True,
            "promotion_blocked": True,
            "recommended_fallback_action": scenario[
                "fallback_action"
            ],
            "verified_result_emitted": False,
        }

        validate_document(
            schema=verification_schema,
            document=artifact,
            label="Recovery verification",
        )

        return artifact, None

    if (
        result.get(
            "terminal_state"
        )
        != "PENDING_VERIFICATION"
    ):
        raise VerificationError(
            "Automatic recovery verification "
            "requires PENDING_VERIFICATION."
        )

    verification = result.get(
        "verification",
        {},
    )

    if (
        verification.get(
            "status"
        )
        != "NOT_RUN"
    ):
        raise VerificationError(
            "Automatic recovery source result "
            "must not already be verified."
        )

    if (
        result.get(
            "self_healing_performed"
        )
        is not False
    ):
        raise VerificationError(
            "Self-healing must not be claimed "
            "before verification."
        )

    if (
        result.get(
            "automatic_remediation_performed"
        )
        is not True
    ):
        raise VerificationError(
            "Automatic scenario must record "
            "automatic remediation."
        )

    derived_schema = (
        derive_c2_policy_input_schema(
            base_policy_input_schema
        )
    )

    policy_input = build_policy_input(
        plan=plan,
        scenario=scenario,
        evidence=evidence,
        branch=branch,
        commit=commit,
        target_layer=target_layer,
    )

    validate_document(
        schema=derived_schema,
        document=policy_input,
        label="C2 verification policy input",
    )

    if opa_bin is None:
        raise VerificationError(
            "Automatic recovery verification "
            "requires OPA."
        )

    allow, violations, evaluation_ms = (
        evaluator(
            opa_bin,
            policy_input,
            repo_root
            / "policies"
            / "rego",
        )
    )

    triggered = sorted({
        str(
            violation[
                "policy_id"
            ]
        )
        for violation in violations
    })

    checks = check_results(
        required_checks=required_checks,
        triggered_policy_ids=set(
            triggered
        ),
    )

    checks_pass = all(
        item[
            "status"
        ]
        == "PASS"
        for item in checks
    )

    verification_pass = (
        allow is True
        and checks_pass
        and not violations
    )

    status = (
        "PASS"
        if verification_pass
        else "FAIL"
    )

    input_contract_sha = sha256_bytes(
        canonical_bytes(
            derived_schema
        )
    )

    input_sha = sha256_bytes(
        canonical_bytes(
            policy_input
        )
    )

    bundle_sha = policy_bundle_sha256(
        repo_root=repo_root,
        derived_input_schema=(
            derived_schema
        ),
    )

    artifact = {
        "schema_version": "1.0.0",
        "condition": "C2",
        "scenario_id": scenario_id,
        "run_key": plan[
            "run_key"
        ],
        "mode": "automatic",
        "automatic_remediation_permitted": True,
        "source_remediation_plan_sha256": plan_sha,
        "source_remediation_result_sha256": result_sha,
        "source_evidence_sha256": evidence_sha,
        "verification_started_at_utc": started,
        "verification_completed_at_utc": completed,
        "required_checks": required_checks,
        "check_results": checks,
        "policy_input": policy_input,
        "policy_input_sha256": input_sha,
        "policy_input_contract_sha256": (
            input_contract_sha
        ),
        "policy_bundle_sha256": bundle_sha,
        "policy_evaluation_ms": (
            evaluation_ms
        ),
        "policy_allow": allow,
        "triggered_policy_ids": triggered,
        "violations": violations,
        "verification_status": status,
        "promotion_requested": True,
        "promotion_blocked": (
            not verification_pass
        ),
        "recommended_fallback_action": (
            None
            if verification_pass
            else scenario[
                "fallback_action"
            ]
        ),
        "verified_result_emitted": (
            verification_pass
        ),
    }

    validate_document(
        schema=verification_schema,
        document=artifact,
        label="Recovery verification",
    )

    if not verification_pass:
        return artifact, None

    verification_sha = sha256_bytes(
        canonical_bytes(
            artifact
        )
    )

    verified_result = build_verified_result(
        source_result=result,
        verification_sha256=(
            verification_sha
        ),
        completed_at=completed,
    )

    validate_document(
        schema=result_schema,
        document=verified_result,
        label="Verified remediation result",
    )

    return (
        artifact,
        verified_result,
    )


def write_new_json(
    *,
    path: Path,
    payload: dict[str, Any],
) -> None:
    if path.exists():
        raise VerificationError(
            f"Output already exists: {path}"
        )

    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    encoded = canonical_bytes(
        payload
    )

    with tempfile.NamedTemporaryFile(
        mode="wb",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temporary = Path(
            handle.name
        )

        handle.write(
            encoded
        )

        handle.flush()

    temporary.replace(
        path
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Verify one C2 bounded-remediation "
            "result against post-remediation "
            "Policy-as-Code evidence."
        )
    )

    parser.add_argument(
        "--plan",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--result",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--evidence",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--opa-bin",
        type=Path,
    )

    parser.add_argument(
        "--git-branch",
        required=True,
    )

    parser.add_argument(
        "--git-commit",
        required=True,
    )

    parser.add_argument(
        "--target-layer",
        required=True,
        choices=[
            "silver",
            "gold_internal",
            "gold_public",
        ],
    )

    parser.add_argument(
        "--verification-output",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--verified-result-output",
        required=True,
        type=Path,
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    repo_root = (
        Path(__file__)
        .resolve()
        .parents[2]
    )

    try:
        if not args.git_branch.strip():
            raise VerificationError(
                "Git branch must not be empty."
            )

        if (
            len(args.git_commit) != 40
            or any(
                character not in "0123456789abcdef"
                for character in args.git_commit
            )
        ):
            raise VerificationError(
                "Git commit must be a "
                "40-character lowercase SHA."
            )

        if args.verification_output.exists():
            raise VerificationError(
                "Verification output already exists."
            )

        if args.verified_result_output.exists():
            raise VerificationError(
                "Verified-result output already exists."
            )

        plan = load_json(
            args.plan
        )

        result = load_json(
            args.result
        )

        evidence = load_json(
            args.evidence
        )

        catalog = load_json(
            repo_root
            / "policies"
            / "catalog"
            / "c2-remediation-catalog.json"
        )

        base_policy_input_schema = load_json(
            repo_root
            / "policies"
            / "contracts"
            / "policy-input.schema.json"
        )

        plan_schema = load_json(
            repo_root
            / "policies"
            / "contracts"
            / "c2-remediation-plan.schema.json"
        )

        result_schema = load_json(
            repo_root
            / "policies"
            / "contracts"
            / "c2-remediation-result.schema.json"
        )

        verification_schema = load_json(
            repo_root
            / "policies"
            / "contracts"
            / "c2-remediation-verification.schema.json"
        )

        if not all(
            isinstance(
                document,
                dict,
            )
            for document in (
                plan,
                result,
                evidence,
                catalog,
                base_policy_input_schema,
                plan_schema,
                result_schema,
                verification_schema,
            )
        ):
            raise VerificationError(
                "All C2 verification inputs "
                "must be JSON objects."
            )

        artifact, verified_result = (
            verify_recovery(
                plan=plan,
                result=result,
                evidence=evidence,
                catalog=catalog,
                base_policy_input_schema=(
                    base_policy_input_schema
                ),
                plan_schema=plan_schema,
                result_schema=result_schema,
                verification_schema=(
                    verification_schema
                ),
                repo_root=repo_root,
                branch=args.git_branch,
                commit=args.git_commit,
                target_layer=(
                    args.target_layer
                ),
                opa_bin=args.opa_bin,
                plan_artifact_sha256=(
                    sha256_file(
                        args.plan
                    )
                ),
                result_artifact_sha256=(
                    sha256_file(
                        args.result
                    )
                ),
                evidence_artifact_sha256=(
                    sha256_file(
                        args.evidence
                    )
                ),
            )
        )

        write_new_json(
            path=args.verification_output,
            payload=artifact,
        )

        if verified_result is not None:
            write_new_json(
                path=args.verified_result_output,
                payload=verified_result,
            )

        print(
            json.dumps(
                {
                    "status": artifact[
                        "verification_status"
                    ],
                    "condition": "C2",
                    "scenario_id": artifact[
                        "scenario_id"
                    ],
                    "run_key": artifact[
                        "run_key"
                    ],
                    "promotion_blocked": artifact[
                        "promotion_blocked"
                    ],
                    "recommended_fallback_action": (
                        artifact[
                            "recommended_fallback_action"
                        ]
                    ),
                    "verified_result_emitted": (
                        verified_result
                        is not None
                    ),
                    "verification_output": str(
                        args.verification_output
                    ),
                    "verified_result_output": (
                        str(
                            args.verified_result_output
                        )
                        if verified_result
                        is not None
                        else None
                    ),
                },
                indent=2,
                sort_keys=True,
            )
        )

        return (
            0
            if artifact[
                "verification_status"
            ]
            == "PASS"
            else 2
        )

    except (
        VerificationError,
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
