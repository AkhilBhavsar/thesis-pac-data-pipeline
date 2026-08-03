from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator

import boto3
import dagster as dg

from thesis_orchestration.bronze_gate import (
    BronzeAvailabilityChecker,
    BronzeGateResult,
    load_bronze_sources,
)
from thesis_orchestration.evidence import (
    EvidenceArtifact,
    EvidenceRecorder,
    RunIdentity,
)


class BronzeGateResource(
    dg.ConfigurableResource
):
    """Read-only AWS resource for the Bronze gate."""

    region_name: str = "eu-west-1"

    expected_bucket: str

    expected_prefix: str = "bronze/"

    def _create_clients(
        self,
    ) -> tuple[Any, Any]:
        session = boto3.session.Session(
            region_name=self.region_name
        )

        return (
            session.client("glue"),
            session.client("s3"),
        )

    def evaluate(
        self,
        *,
        manifest_path: Path,
        glue_client: Any | None = None,
        s3_client: Any | None = None,
    ) -> BronzeGateResult:
        one_client_missing = (
            (glue_client is None)
            != (s3_client is None)
        )

        if one_client_missing:
            raise ValueError(
                "Glue and S3 clients must either "
                "both be supplied or both omitted."
            )

        if (
            glue_client is None
            and s3_client is None
        ):
            (
                glue_client,
                s3_client,
            ) = self._create_clients()

        sources = load_bronze_sources(
            manifest_path
        )

        checker = BronzeAvailabilityChecker(
            glue_client=glue_client,
            s3_client=s3_client,
            expected_bucket=(
                self.expected_bucket
            ),
            expected_prefix=(
                self.expected_prefix
            ),
        )

        return checker.check_all(
            sources
        )

    def enforce(
        self,
        *,
        manifest_path: Path,
        identity: RunIdentity,
        recorder: EvidenceRecorder,
        glue_client: Any | None = None,
        s3_client: Any | None = None,
    ) -> tuple[
        BronzeGateResult,
        EvidenceArtifact,
    ]:
        result = self.evaluate(
            manifest_path=manifest_path,
            glue_client=glue_client,
            s3_client=s3_client,
        )

        artifact = recorder.record(
            identity=identity,
            stage="bronze-availability",
            status=result.status,
            payload=result.to_payload(),
        )

        if result.status != "PASS":
            violation_codes = sorted(
                {
                    check.violation_code
                    for check in result.checks
                    if check.violation_code
                }
            )

            raise dg.Failure(
                description=(
                    "Bronze availability gate "
                    "blocked dbt execution: "
                    f"{result.blocked_count} of "
                    f"{result.expected_count} "
                    "governed Bronze sources "
                    "failed validation."
                ),
                metadata={
                    "expected_count": (
                        result.expected_count
                    ),
                    "available_count": (
                        result.available_count
                    ),
                    "blocked_count": (
                        result.blocked_count
                    ),
                    "violation_codes": (
                        ", ".join(
                            violation_codes
                        )
                        or "UNKNOWN"
                    ),
                    "evidence_json": str(
                        artifact.json_path
                    ),
                    "evidence_sha256": (
                        artifact.sha256
                    ),
                },
            )

        return result, artifact


def run_bronze_guarded_dbt(
    *,
    context: Any,
    dbt: Any,
    bronze_gate: BronzeGateResource,
    manifest_path: Path,
) -> Iterator[Any]:
    """Run dbt only after the Bronze gate passes."""

    identity = (
        RunIdentity.from_environment(
            dagster_run_id=str(
                context.run_id
            )
        )
    )

    recorder = (
        EvidenceRecorder.from_environment()
    )

    result, artifact = bronze_gate.enforce(
        manifest_path=manifest_path,
        identity=identity,
        recorder=recorder,
    )

    context.log.info(
        "Bronze availability gate passed: "
        f"{result.available_count}/"
        f"{result.expected_count} sources. "
        f"Evidence: {artifact.json_path}"
    )

    yield from dbt.cli(
        ["build"],
        context=context,
    ).stream()
