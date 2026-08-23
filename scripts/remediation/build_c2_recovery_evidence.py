#!/usr/bin/env python3
"""Build normalized C2 recovery evidence for bounded self-healing verification."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any


class EvidenceBuildError(RuntimeError):
    pass


def load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )
    except Exception as exc:
        raise EvidenceBuildError(
            f"Unable to read JSON {path}: {exc}"
        ) from exc

    if not isinstance(payload, dict):
        raise EvidenceBuildError(
            f"{path} must contain JSON object"
        )

    return payload


def canonical_bytes(payload: Any) -> bytes:
    return (
        json.dumps(
            payload,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        )
        + "\n"
    ).encode("utf-8")


def write_json_atomic(
    path: Path,
    payload: Any,
) -> str:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    encoded = canonical_bytes(payload)

    with tempfile.NamedTemporaryFile(
        mode="wb",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
        handle.write(encoded)

    temporary.replace(path)

    return hashlib.sha256(
        encoded
    ).hexdigest()


def safe_workspace_file(
    *,
    workspace_root: Path,
    relative_name: str,
) -> Path:
    root = workspace_root.resolve()
    candidate = (
        root
        / relative_name
    ).resolve()

    if not candidate.is_relative_to(root):
        raise EvidenceBuildError(
            "Recovery projection path escapes "
            "the isolated workspace."
        )

    if not candidate.is_file():
        raise EvidenceBuildError(
            "Remediated isolated candidate "
            f"does not exist: {candidate}"
        )

    return candidate


def project_pii_recovery(
    *,
    evidence: dict[str, Any],
    plan: dict[str, Any],
    context: dict[str, Any],
    result: dict[str, Any],
    details: dict[str, Any],
    workspace_root: Path,
) -> None:
    scenario = result.get(
        "scenario_id"
    )
    action = result.get("action")

    if not (
        scenario == "pii_exposure"
        and action == "redact_republish"
        and result.get("execution_status")
        == "SUCCEEDED"
    ):
        return

    plan_body = plan.get("plan")
    action_context = context.get(
        "action_context"
    )
    workspace = context.get("workspace")

    if not isinstance(plan_body, dict):
        raise EvidenceBuildError(
            "PII recovery plan body is missing."
        )

    if not isinstance(action_context, dict):
        raise EvidenceBuildError(
            "PII action context is missing."
        )

    if not isinstance(workspace, dict):
        raise EvidenceBuildError(
            "PII workspace context is missing."
        )

    identity_checks = (
        plan.get("scenario_id")
        == "pii_exposure",
        plan_body.get("primary_action")
        == "redact_republish",
        context.get("scenario_id")
        == "pii_exposure",
        action_context.get("action")
        == "redact_republish",
        plan.get("run_key")
        == result.get("run_key")
        == context.get("run_key"),
    )

    if not all(identity_checks):
        raise EvidenceBuildError(
            "PII recovery identity or action drift."
        )

    if (
        workspace.get("isolated") is not True
        or workspace.get(
            "canonical_access_permitted"
        ) is not False
    ):
        raise EvidenceBuildError(
            "PII recovery is not confined to "
            "the isolated workspace."
        )

    configured_root = workspace.get("root")

    if (
        not isinstance(configured_root, str)
        or Path(configured_root).resolve()
        != workspace_root.resolve()
    ):
        raise EvidenceBuildError(
            "PII workspace root does not match "
            "the execution context."
        )

    if (
        result.get(
            "canonical_mutation_performed"
        ) is not False
    ):
        raise EvidenceBuildError(
            "PII recovery cannot project after "
            "canonical mutation."
        )

    expected_operation = (
        "replace_with_sanitized_"
        "isolated_candidate"
    )

    if details.get("operation") != expected_operation:
        raise EvidenceBuildError(
            "PII recovery operation is not the "
            "reviewed isolated replacement."
        )

    if details.get("source_unchanged") is not True:
        raise EvidenceBuildError(
            "PII sanitized source was not "
            "confirmed unchanged."
        )

    source_sha = details.get("source_sha256")
    before_sha = details.get(
        "target_sha256_before"
    )
    after_sha = details.get(
        "target_sha256_after"
    )

    if (
        not isinstance(source_sha, str)
        or len(source_sha) != 64
        or source_sha != after_sha
        or before_sha == after_sha
    ):
        raise EvidenceBuildError(
            "PII remediation fingerprints do not "
            "prove sanitized replacement."
        )

    candidate_relative = action_context.get(
        "candidate_relative_path"
    )

    if not isinstance(candidate_relative, str):
        raise EvidenceBuildError(
            "PII candidate path is missing."
        )

    candidate_path = safe_workspace_file(
        workspace_root=workspace_root,
        relative_name=candidate_relative,
    )

    if hashlib.sha256(
        candidate_path.read_bytes()
    ).hexdigest() != after_sha:
        raise EvidenceBuildError(
            "PII candidate fingerprint differs "
            "from remediation details."
        )

    candidate = load_json(candidate_path)

    required_fixture_values = {
        "condition": "C2",
        "scenario_id": "pii_exposure",
        "synthetic_fixture": True,
        "canonical_data": False,
        "fixture_role": "sanitized_source",
        "trusted": True,
        "state": "redacted_safe",
    }

    for field, expected in (
        required_fixture_values.items()
    ):
        if candidate.get(field) != expected:
            raise EvidenceBuildError(
                "PII sanitized candidate has "
                f"invalid {field}."
            )

    removed_field = "synthetic_email"

    if removed_field in candidate:
        raise EvidenceBuildError(
            "PII sanitized candidate still contains "
            f"{removed_field}."
        )

    privacy = evidence.get("privacy")
    schema_contract = evidence.get(
        "schema_contract"
    )

    if not isinstance(privacy, dict):
        raise EvidenceBuildError(
            "PII privacy evidence must be an object."
        )

    if not isinstance(schema_contract, dict):
        raise EvidenceBuildError(
            "PII schema evidence must be an object."
        )

    detected = privacy.get(
        "detected_forbidden_columns"
    )

    if (
        not isinstance(detected, list)
        or removed_field not in detected
    ):
        raise EvidenceBuildError(
            "PII pre evidence does not contain "
            "the removed forbidden field."
        )

    privacy[
        "detected_forbidden_columns"
    ] = [
        field
        for field in detected
        if field != removed_field
    ]

    governed_models = schema_contract.get(
        "governed_models"
    )

    if not isinstance(governed_models, list):
        raise EvidenceBuildError(
            "PII governed models must be a list."
        )

    public_matches = [
        model
        for model in governed_models
        if (
            isinstance(model, dict)
            and model.get("model")
            == "gold_public_sales_dashboard"
        )
    ]

    if len(public_matches) != 1:
        raise EvidenceBuildError(
            "Expected exactly one governed PII "
            "public model."
        )

    public_model = public_matches[0]
    unexpected = public_model.get(
        "unexpected_columns"
    )
    actual_count = public_model.get(
        "actual_column_count"
    )
    expected_count = public_model.get(
        "expected_column_count"
    )

    if (
        not isinstance(unexpected, list)
        or removed_field not in unexpected
        or not isinstance(actual_count, int)
        or isinstance(actual_count, bool)
        or not isinstance(expected_count, int)
        or isinstance(expected_count, bool)
        or actual_count != expected_count + 1
    ):
        raise EvidenceBuildError(
            "PII schema evidence does not prove "
            "one removable injected field."
        )

    public_model["unexpected_columns"] = [
        field
        for field in unexpected
        if field != removed_field
    ]
    public_model[
        "actual_column_count"
    ] = actual_count - 1


def build_evidence(
    *,
    plan: dict[str, Any],
    context: dict[str, Any],
    workspace_root: Path,
    result: dict[str, Any],
    details: dict[str, Any],
    pre_evidence: dict[str, Any],
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
        if section not in pre_evidence
    ]

    if missing:
        raise EvidenceBuildError(
            "Pre evidence missing sections: "
            f"{missing}"
        )

    evidence = {
        section: copy.deepcopy(
            pre_evidence[section]
        )
        for section in required_sections
    }

    pre_runtime = pre_evidence[
        "runtime"
    ]

    if not isinstance(
        pre_runtime,
        dict,
    ):
        raise EvidenceBuildError(
            "Pre evidence runtime section "
            "must be an object."
        )

    required_runtime_metrics = (
        "isolated_output_tables",
        "athena_failed_queries",
    )

    missing_runtime_metrics = [
        field
        for field
        in required_runtime_metrics
        if field not in pre_runtime
    ]

    if missing_runtime_metrics:
        raise EvidenceBuildError(
            "Pre evidence runtime missing "
            "required metrics: "
            f"{missing_runtime_metrics}"
        )

    execution_status = result.get(
        "execution_status"
    )

    pipeline_status_by_execution = {
        "NOT_RUN": "NOT_RUN",
        "SUCCEEDED": "PASS",
        "FAILED": "FAIL",
    }

    if (
        execution_status
        not in pipeline_status_by_execution
    ):
        raise EvidenceBuildError(
            "Unsupported remediation execution "
            f"status: {execution_status}"
        )

    evidence["runtime"] = {
        "pipeline_status": (
            pipeline_status_by_execution[
                execution_status
            ]
        ),
        "canonical_unchanged": (
            result.get(
                "canonical_mutation_performed"
            )
            is False
        ),
        "isolated_output_tables": (
            pre_runtime[
                "isolated_output_tables"
            ]
        ),
        "athena_failed_queries": (
            pre_runtime[
                "athena_failed_queries"
            ]
        ),
    }

    project_pii_recovery(
        evidence=evidence,
        plan=plan,
        context=context,
        result=result,
        details=details,
        workspace_root=workspace_root,
    )

    return evidence


def parser() -> argparse.ArgumentParser:

    parser = argparse.ArgumentParser(
        description=(
            "Build C2 recovery verification evidence."
        )
    )

    parser.add_argument(
        "--plan",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--context",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--workspace-root",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--result",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--details",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--pre-evidence",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--output",
        required=True,
        type=Path,
    )

    return parser


def main() -> int:

    args = parser().parse_args()

    plan = load_json(
        args.plan
    )

    context = load_json(
        args.context
    )

    result = load_json(
        args.result
    )

    details = load_json(
        args.details
    )

    pre_evidence = load_json(
        args.pre_evidence
    )

    evidence = build_evidence(
        plan=plan,
        context=context,
        workspace_root=args.workspace_root,
        result=result,
        details=details,
        pre_evidence=pre_evidence,
    )

    digest = write_json_atomic(
        args.output,
        evidence,
    )

    print(
        json.dumps(
            {
                "status": "PASS",
                "output": str(args.output),
                "sha256": digest,
            },
            indent=2,
        )
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
