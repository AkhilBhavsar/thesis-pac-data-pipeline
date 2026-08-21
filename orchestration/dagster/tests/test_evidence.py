from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from thesis_orchestration.evidence import (
    EvidenceRecorder,
    RunIdentity,
)


class EvidenceFoundationTest(
    unittest.TestCase
):
    def test_environment_defaults_to_c0(
        self,
    ) -> None:
        with patch.dict(
            os.environ,
            {},
            clear=True,
        ):
            identity = RunIdentity.from_environment(
                dagster_run_id="run-001"
            )

        self.assertEqual(
            identity.experiment_condition,
            "C0",
        )

        self.assertEqual(
            identity.scenario_id,
            "none",
        )

        self.assertEqual(
            identity.git_commit,
            "UNKNOWN",
        )

        self.assertEqual(
            identity.git_branch,
            "UNKNOWN",
        )

    def test_invalid_condition_is_rejected(
        self,
    ) -> None:
        with self.assertRaises(ValueError):
            RunIdentity(
                dagster_run_id="run-002",
                experiment_condition="C9",
                scenario_id="baseline",
                git_commit="abc123",
                git_branch="feature/test",
                initiated_at_utc=(
                    "2026-08-02T00:00:00.000Z"
                ),
            )

    def test_record_writes_json_and_checksum(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as root:
            identity = RunIdentity(
                dagster_run_id="run-003",
                experiment_condition="C0",
                scenario_id="baseline",
                git_commit="abc123",
                git_branch="feature/test",
                initiated_at_utc=(
                    "2026-08-02T00:00:00.000Z"
                ),
            )

            artifact = EvidenceRecorder(
                Path(root)
            ).record(
                identity=identity,
                stage="bronze-availability",
                status="PASS",
                payload={
                    "tables_expected": 10,
                    "tables_available": 10,
                },
            )

            self.assertTrue(
                artifact.json_path.is_file()
            )

            self.assertTrue(
                artifact.checksum_path.is_file()
            )

            digest = hashlib.sha256(
                artifact.json_path.read_bytes()
            ).hexdigest()

            self.assertEqual(
                digest,
                artifact.sha256,
            )

            checksum_text = (
                artifact.checksum_path
                .read_text(
                    encoding="utf-8"
                )
                .strip()
            )

            self.assertEqual(
                checksum_text,
                (
                    f"{digest}  "
                    f"{artifact.json_path.name}"
                ),
            )

            document = json.loads(
                artifact.json_path.read_text(
                    encoding="utf-8"
                )
            )

            self.assertEqual(
                document["schema_version"],
                1,
            )

            self.assertEqual(
                document["status"],
                "PASS",
            )

            self.assertEqual(
                document["stage"],
                "bronze-availability",
            )

            self.assertEqual(
                document["run"][
                    "experiment_condition"
                ],
                "C0",
            )

            self.assertEqual(
                document["payload"][
                    "tables_available"
                ],
                10,
            )

            self.assertEqual(
                artifact.json_path.parent,
                (
                    Path(root).resolve()
                    / "C0"
                    / "baseline"
                    / "run-003"
                ),
            )

    def test_invalid_status_is_rejected(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as root:
            identity = RunIdentity(
                dagster_run_id="run-004",
                experiment_condition="C0",
                scenario_id="baseline",
                git_commit="abc123",
                git_branch="feature/test",
                initiated_at_utc=(
                    "2026-08-02T00:00:00.000Z"
                ),
            )

            with self.assertRaises(ValueError):
                EvidenceRecorder(
                    Path(root)
                ).record(
                    identity=identity,
                    stage="test",
                    status="UNKNOWN",
                    payload={},
                )


if __name__ == "__main__":
    unittest.main()
