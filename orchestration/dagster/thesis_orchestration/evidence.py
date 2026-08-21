from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


ALLOWED_CONDITIONS = {
    "C0",
    "C1",
    "C2",
}

ALLOWED_STATUSES = {
    "RUNNING",
    "PASS",
    "FAIL",
    "BLOCKED",
}

SCHEMA_VERSION = 1


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def filename_timestamp() -> str:
    return datetime.now(timezone.utc).strftime(
        "%Y%m%dT%H%M%S%fZ"
    )


def safe_component(value: str) -> str:
    result = re.sub(
        r"[^A-Za-z0-9._-]+",
        "-",
        value.strip(),
    ).strip("-")

    if result in {"", ".", ".."}:
        raise ValueError(
            "Evidence path component is invalid."
        )

    return result


def atomic_write(
    destination: Path,
    payload: bytes,
) -> None:
    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        dir=destination.parent,
    )

    temporary_path = Path(temporary_name)

    try:
        with os.fdopen(
            descriptor,
            "wb",
        ) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())

        os.replace(
            temporary_path,
            destination,
        )
    except BaseException:
        temporary_path.unlink(
            missing_ok=True
        )
        raise


@dataclass(frozen=True)
class RunIdentity:
    dagster_run_id: str
    experiment_condition: str
    scenario_id: str
    git_commit: str
    git_branch: str
    initiated_at_utc: str

    def __post_init__(self) -> None:
        if (
            self.experiment_condition
            not in ALLOWED_CONDITIONS
        ):
            raise ValueError(
                "Experiment condition must be "
                "C0, C1 or C2."
            )

        safe_component(
            self.dagster_run_id
        )

        safe_component(
            self.scenario_id
        )

    @classmethod
    def from_environment(
        cls,
        *,
        dagster_run_id: str,
    ) -> "RunIdentity":
        return cls(
            dagster_run_id=dagster_run_id,
            experiment_condition=os.getenv(
                "THESIS_EXPERIMENT_CONDITION",
                "C0",
            ).upper(),
            scenario_id=os.getenv(
                "THESIS_SCENARIO_ID",
                "none",
            ),
            git_commit=os.getenv(
                "THESIS_GIT_COMMIT",
                "UNKNOWN",
            ),
            git_branch=os.getenv(
                "THESIS_GIT_BRANCH",
                "UNKNOWN",
            ),
            initiated_at_utc=utc_now(),
        )


@dataclass(frozen=True)
class EvidenceArtifact:
    json_path: Path
    checksum_path: Path
    sha256: str


class EvidenceRecorder:
    def __init__(
        self,
        root: Path,
    ) -> None:
        self.root = (
            root
            .expanduser()
            .resolve()
        )

    @classmethod
    def from_environment(
        cls,
    ) -> "EvidenceRecorder":
        configured = os.getenv(
            "THESIS_DAGSTER_EVIDENCE_ROOT"
        )

        if not configured:
            raise ValueError(
                "THESIS_DAGSTER_EVIDENCE_ROOT "
                "must be configured."
            )

        return cls(
            Path(configured)
        )

    def run_directory(
        self,
        identity: RunIdentity,
    ) -> Path:
        return (
            self.root
            / safe_component(
                identity.experiment_condition
            )
            / safe_component(
                identity.scenario_id
            )
            / safe_component(
                identity.dagster_run_id
            )
        )

    def record(
        self,
        *,
        identity: RunIdentity,
        stage: str,
        status: str,
        payload: Mapping[str, Any],
    ) -> EvidenceArtifact:
        normalized_status = status.upper()

        if normalized_status not in ALLOWED_STATUSES:
            raise ValueError(
                "Unsupported evidence status."
            )

        stage_component = safe_component(
            stage
        )

        document = {
            "schema_version": SCHEMA_VERSION,
            "recorded_at_utc": utc_now(),
            "run": asdict(identity),
            "stage": stage,
            "status": normalized_status,
            "payload": dict(payload),
        }

        serialized = (
            json.dumps(
                document,
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
                default=str,
            )
            + "\n"
        ).encode("utf-8")

        digest = hashlib.sha256(
            serialized
        ).hexdigest()

        json_path = (
            self.run_directory(identity)
            / (
                f"{filename_timestamp()}-"
                f"{stage_component}.json"
            )
        )

        checksum_path = json_path.with_suffix(
            ".json.sha256"
        )

        atomic_write(
            json_path,
            serialized,
        )

        atomic_write(
            checksum_path,
            (
                f"{digest}  "
                f"{json_path.name}\n"
            ).encode("utf-8"),
        )

        return EvidenceArtifact(
            json_path=json_path,
            checksum_path=checksum_path,
            sha256=digest,
        )
