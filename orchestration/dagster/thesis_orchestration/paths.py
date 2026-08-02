from __future__ import annotations

import os
import shutil
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]

DBT_PROJECT_DIR = (
    REPOSITORY_ROOT
    / "transformations"
    / "dbt"
)

DBT_PROFILE_NAME = "thesis_pac_athena"
DBT_TARGET_NAME = "dev"


def _required_existing_path(
    environment_variable: str,
    default: Path,
    *,
    expected_kind: str,
) -> Path:
    raw_value = os.getenv(environment_variable)

    candidate = (
        Path(raw_value).expanduser()
        if raw_value
        else default
    ).resolve()

    if expected_kind == "file":
        valid = candidate.is_file()
    elif expected_kind == "directory":
        valid = candidate.is_dir()
    else:
        raise ValueError(
            f"Unsupported expected kind: {expected_kind}"
        )

    if not valid:
        raise FileNotFoundError(
            f"{environment_variable} does not resolve "
            f"to an existing {expected_kind}: {candidate}"
        )

    return candidate


def resolve_manifest_path() -> Path:
    return _required_existing_path(
        "THESIS_DBT_MANIFEST_PATH",
        DBT_PROJECT_DIR / "target" / "manifest.json",
        expected_kind="file",
    )


def resolve_profiles_dir() -> Path:
    return _required_existing_path(
        "THESIS_DBT_PROFILES_DIR",
        Path.home() / ".dbt",
        expected_kind="directory",
    )


def resolve_dbt_executable() -> str:
    configured = os.getenv(
        "THESIS_DBT_EXECUTABLE",
        "dbt",
    )

    configured_path = Path(
        configured
    ).expanduser()

    if configured_path.is_absolute():
        if not (
            configured_path.is_file()
            and os.access(
                configured_path,
                os.X_OK,
            )
        ):
            raise FileNotFoundError(
                "THESIS_DBT_EXECUTABLE is not an "
                f"executable file: {configured_path}"
            )

        return str(
            configured_path.resolve()
        )

    resolved = shutil.which(configured)

    if resolved is None:
        raise FileNotFoundError(
            f"dbt executable not found: {configured}"
        )

    return resolved


MANIFEST_PATH = resolve_manifest_path()
DBT_PROFILES_DIR = resolve_profiles_dir()
DBT_EXECUTABLE = resolve_dbt_executable()
