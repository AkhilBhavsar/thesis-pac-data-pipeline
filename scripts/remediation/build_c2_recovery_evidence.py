#!/usr/bin/env python3
"""Build normalized C2 recovery evidence for bounded self-healing verification."""

from __future__ import annotations

import argparse
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


def build_evidence(
    *,
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
        section: pre_evidence[section]
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

    return evidence


def parser() -> argparse.ArgumentParser:

    parser = argparse.ArgumentParser(
        description=(
            "Build C2 recovery verification evidence."
        )
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
