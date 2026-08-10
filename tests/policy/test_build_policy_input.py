from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = (
    Path(__file__).resolve().parents[2]
)

BUILDER = (
    REPO_ROOT
    / "scripts"
    / "policy"
    / "build_policy_input.py"
)

SCHEMA = (
    REPO_ROOT
    / "policies"
    / "contracts"
    / "policy-input.schema.json"
)

SAFE_FIXTURE = (
    REPO_ROOT
    / "policies"
    / "fixtures"
    / "c1-safe-baseline.json"
)

EVIDENCE_SECTIONS = (
    "metadata",
    "schema_contract",
    "transformation",
    "privacy",
    "quality",
    "freshness",
    "runtime",
)


def run_git(
    repository: Path,
    *arguments: str,
) -> str:
    completed = subprocess.run(
        [
            "git",
            "-C",
            str(repository),
            *arguments,
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    return completed.stdout.strip()


def make_evidence() -> dict:
    fixture = json.loads(
        SAFE_FIXTURE.read_text(
            encoding="utf-8"
        )
    )

    return {
        section: fixture[section]
        for section in EVIDENCE_SECTIONS
    }


class PolicyInputBuilderTests(
    unittest.TestCase
):
    def create_git_repository(
        self,
        root: Path,
    ) -> tuple[str, str]:
        subprocess.run(
            [
                "git",
                "init",
                "-q",
                str(root),
            ],
            check=True,
        )

        run_git(
            root,
            "config",
            "user.email",
            "builder-test@example.invalid",
        )

        run_git(
            root,
            "config",
            "user.name",
            "Builder Test",
        )

        run_git(
            root,
            "checkout",
            "-q",
            "-b",
            "builder-test",
        )

        marker = root / "marker.txt"

        marker.write_text(
            "builder-test\n",
            encoding="utf-8",
        )

        run_git(
            root,
            "add",
            "marker.txt",
        )

        run_git(
            root,
            "commit",
            "-q",
            "-m",
            "builder test",
        )

        branch = run_git(
            root,
            "rev-parse",
            "--abbrev-ref",
            "HEAD",
        )

        commit = run_git(
            root,
            "rev-parse",
            "HEAD",
        )

        return branch, commit

    def test_uses_live_git_metadata(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)

            branch, commit = (
                self.create_git_repository(
                    root
                )
            )

            evidence_path = (
                root / "evidence.json"
            )

            output_path = (
                root / "policy-input.json"
            )

            evidence_path.write_text(
                json.dumps(
                    make_evidence(),
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )

            subprocess.run(
                [
                    sys.executable,
                    str(BUILDER),
                    "--repo-root",
                    str(root),
                    "--schema",
                    str(SCHEMA),
                    "--evidence",
                    str(evidence_path),
                    "--stage",
                    "pre",
                    "--scenario",
                    "baseline",
                    "--run-key",
                    "unit-live-git",
                    "--target-layer",
                    "gold_public",
                    "--promotion-requested",
                    "true",
                    "--output",
                    str(output_path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            payload = json.loads(
                output_path.read_text(
                    encoding="utf-8"
                )
            )

            self.assertEqual(
                payload["git"]["branch"],
                branch,
            )

            self.assertEqual(
                payload["git"]["commit"],
                commit,
            )

            self.assertTrue(
                payload["controls"][
                    "policy_as_code_required"
                ]
            )

            self.assertFalse(
                payload["controls"][
                    "self_healing_permitted"
                ]
            )

            self.assertFalse(
                payload["controls"][
                    "automatic_remediation_permitted"
                ]
            )

    def test_explicit_git_metadata_supported(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)

            evidence_path = (
                root / "evidence.json"
            )

            output_path = (
                root / "policy-input.json"
            )

            evidence_path.write_text(
                json.dumps(
                    make_evidence(),
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )

            commit = "a" * 40

            subprocess.run(
                [
                    sys.executable,
                    str(BUILDER),
                    "--repo-root",
                    str(root),
                    "--schema",
                    str(SCHEMA),
                    "--evidence",
                    str(evidence_path),
                    "--stage",
                    "post",
                    "--scenario",
                    "quality_regression",
                    "--run-key",
                    "unit-explicit-git",
                    "--target-layer",
                    "gold_internal",
                    "--promotion-requested",
                    "false",
                    "--git-branch",
                    "gha-test",
                    "--git-commit",
                    commit,
                    "--output",
                    str(output_path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )

            payload = json.loads(
                output_path.read_text(
                    encoding="utf-8"
                )
            )

            self.assertEqual(
                payload["git"]["branch"],
                "gha-test",
            )

            self.assertEqual(
                payload["git"]["commit"],
                commit,
            )

    def test_missing_evidence_section_rejected(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)

            self.create_git_repository(
                root
            )

            evidence = make_evidence()

            evidence.pop(
                "runtime"
            )

            evidence_path = (
                root / "evidence.json"
            )

            output_path = (
                root / "policy-input.json"
            )

            evidence_path.write_text(
                json.dumps(
                    evidence,
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )

            completed = subprocess.run(
                [
                    sys.executable,
                    str(BUILDER),
                    "--repo-root",
                    str(root),
                    "--schema",
                    str(SCHEMA),
                    "--evidence",
                    str(evidence_path),
                    "--stage",
                    "pre",
                    "--scenario",
                    "baseline",
                    "--run-key",
                    "unit-missing-runtime",
                    "--target-layer",
                    "gold_public",
                    "--promotion-requested",
                    "true",
                    "--output",
                    str(output_path),
                ],
                capture_output=True,
                text=True,
            )

            self.assertEqual(
                completed.returncode,
                1,
            )

            self.assertFalse(
                output_path.exists()
            )

            self.assertIn(
                "missing=['runtime']",
                completed.stderr,
            )


if __name__ == "__main__":
    unittest.main()
