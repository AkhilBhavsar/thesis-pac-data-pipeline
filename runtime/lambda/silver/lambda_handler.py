from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import boto3
import pandas as pd
from botocore.config import Config


PACKAGE_ROOT = Path(__file__).resolve().parent

WORKSPACE_ROOT = Path(
    os.environ.get(
        "SILVER_WORKSPACE_ROOT",
        "/tmp/thesis-pac-silver",
    )
)

CONTRACT_FILE = (
    PACKAGE_ROOT
    / "config"
    / "silver-input-contract.json"
)

PACKAGED_SCRIPTS = {
    "build_silver.py": (
        PACKAGE_ROOT
        / "scripts"
        / "build_silver.py"
    ),
    "validate_silver.py": (
        PACKAGE_ROOT
        / "scripts"
        / "validate_silver.py"
    ),
}

DOWNLOAD_CHUNK_BYTES = 8 * 1024 * 1024


def sha256_file(file_name: Path) -> str:
    digest = hashlib.sha256()

    with file_name.open("rb") as source:
        for block in iter(
            lambda: source.read(
                DOWNLOAD_CHUNK_BYTES
            ),
            b"",
        ):
            digest.update(block)

    return digest.hexdigest()


def load_contract() -> dict[str, Any]:
    contract = json.loads(
        CONTRACT_FILE.read_text(
            encoding="utf-8"
        )
    )

    if contract.get("contract_version") != 1:
        raise ValueError(
            "Unsupported Silver input contract version."
        )

    if contract.get("input_count") != 10:
        raise ValueError(
            "The Silver input contract must contain "
            "exactly 10 inputs."
        )

    if len(contract.get("inputs", [])) != 10:
        raise ValueError(
            "The Silver input list must contain "
            "exactly 10 entries."
        )

    return contract


def clear_workspace() -> None:
    WORKSPACE_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    for child in WORKSPACE_ROOT.iterdir():
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def prepare_workspace() -> None:
    clear_workspace()

    required_directories = [
        WORKSPACE_ROOT / "scripts",
        WORKSPACE_ROOT / "config",
        WORKSPACE_ROOT / "data" / "silver",
        (
            WORKSPACE_ROOT
            / "data"
            / "bronze"
            / "raw"
            / "olist"
        ),
        (
            WORKSPACE_ROOT
            / "data"
            / "bronze"
            / "generated"
        ),
        (
            WORKSPACE_ROOT
            / "experiments"
            / "results"
        ),
        WORKSPACE_ROOT / "logs",
    ]

    for directory in required_directories:
        directory.mkdir(
            parents=True,
            exist_ok=True,
        )

    for destination_name, source_file in (
        PACKAGED_SCRIPTS.items()
    ):
        if not source_file.is_file():
            raise FileNotFoundError(
                f"Missing packaged script: "
                f"{source_file}"
            )

        shutil.copy2(
            source_file,
            (
                WORKSPACE_ROOT
                / "scripts"
                / destination_name
            ),
        )

    shutil.copy2(
        CONTRACT_FILE,
        (
            WORKSPACE_ROOT
            / "config"
            / "silver-input-contract.json"
        ),
    )


def safe_workspace_file(
    relative_name: str,
) -> Path:
    relative_file = Path(relative_name)

    if relative_file.is_absolute():
        raise ValueError(
            "Absolute workspace paths are forbidden."
        )

    if ".." in relative_file.parts:
        raise ValueError(
            "Workspace parent traversal is forbidden."
        )

    destination_file = (
        WORKSPACE_ROOT
        / relative_file
    )

    resolved_root = WORKSPACE_ROOT.resolve()
    resolved_destination = (
        destination_file.resolve()
    )

    if (
        resolved_destination != resolved_root
        and resolved_root
        not in resolved_destination.parents
    ):
        raise ValueError(
            "Destination escapes the workspace."
        )

    return destination_file


def download_inputs(
    contract: dict[str, Any],
) -> list[dict[str, Any]]:
    session = boto3.Session(
        region_name=contract["aws"]["region"]
    )

    retry_config = Config(
        retries={
            "max_attempts": 8,
            "mode": "standard",
        }
    )

    sts_client = session.client(
        "sts",
        config=retry_config,
    )

    identity = (
        sts_client.get_caller_identity()
    )

    if identity["Account"] != (
        contract["aws"]["account_id"]
    ):
        raise RuntimeError(
            "AWS account does not match the "
            "Silver input contract."
        )

    s3_client = session.client(
        "s3",
        config=retry_config,
    )

    results: list[dict[str, Any]] = []

    for item in contract["inputs"]:
        destination_file = (
            safe_workspace_file(
                item["local_relative_path"]
            )
        )

        destination_file.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        partial_file = (
            destination_file.with_name(
                destination_file.name
                + ".partial"
            )
        )

        partial_file.unlink(
            missing_ok=True
        )

        response = s3_client.get_object(
            Bucket=item["s3_bucket"],
            Key=item["s3_key"],
            VersionId=item["s3_version_id"],
        )

        try:
            observed_version = response.get(
                "VersionId"
            )

            observed_size = int(
                response["ContentLength"]
            )

            observed_encryption = (
                response.get(
                    "ServerSideEncryption"
                )
            )

            observed_metadata = (
                response.get(
                    "Metadata",
                    {}
                )
            )

            if observed_version != (
                item["s3_version_id"]
            ):
                raise RuntimeError(
                    f"Version mismatch for "
                    f"{item['dataset']}."
                )

            if observed_size != int(
                item["size_bytes"]
            ):
                raise RuntimeError(
                    f"Size mismatch for "
                    f"{item['dataset']}."
                )

            if observed_encryption != (
                item[
                    "server_side_encryption"
                ]
            ):
                raise RuntimeError(
                    f"Encryption mismatch for "
                    f"{item['dataset']}."
                )

            if observed_metadata.get(
                "sha256"
            ) != item["sha256"]:
                raise RuntimeError(
                    f"S3 metadata checksum mismatch "
                    f"for {item['dataset']}."
                )

            digest = hashlib.sha256()
            downloaded_bytes = 0

            with partial_file.open(
                "wb"
            ) as target:
                while True:
                    block = (
                        response["Body"].read(
                            DOWNLOAD_CHUNK_BYTES
                        )
                    )

                    if not block:
                        break

                    target.write(block)
                    digest.update(block)

                    downloaded_bytes += (
                        len(block)
                    )

                target.flush()
                os.fsync(
                    target.fileno()
                )

            observed_sha256 = (
                digest.hexdigest()
            )

            if downloaded_bytes != int(
                item["size_bytes"]
            ):
                raise RuntimeError(
                    f"Downloaded byte count mismatch "
                    f"for {item['dataset']}."
                )

            if observed_sha256 != (
                item["sha256"]
            ):
                raise RuntimeError(
                    f"Downloaded checksum mismatch "
                    f"for {item['dataset']}."
                )

            os.replace(
                partial_file,
                destination_file,
            )

            if sha256_file(
                destination_file
            ) != item["sha256"]:
                raise RuntimeError(
                    f"Final local checksum mismatch "
                    f"for {item['dataset']}."
                )

            results.append(
                {
                    "dataset": (
                        item["dataset"]
                    ),
                    "s3_key": (
                        item["s3_key"]
                    ),
                    "s3_version_id": (
                        item["s3_version_id"]
                    ),
                    "local_relative_path": (
                        item[
                            "local_relative_path"
                        ]
                    ),
                    "size_bytes": (
                        downloaded_bytes
                    ),
                    "sha256": (
                        observed_sha256
                    ),
                    "status": "PASS",
                }
            )

            print(
                "DOWNLOADED:",
                item["dataset"],
                downloaded_bytes,
                observed_sha256,
            )

        finally:
            response["Body"].close()

            partial_file.unlink(
                missing_ok=True
            )

    results.sort(
        key=lambda item: item["dataset"]
    )

    total_bytes = sum(
        item["size_bytes"]
        for item in results
    )

    if len(results) != 10:
        raise RuntimeError(
            "Unexpected downloaded input count."
        )

    if total_bytes != int(
        contract["total_input_bytes"]
    ):
        raise RuntimeError(
            "Unexpected downloaded byte total."
        )

    return results


def run_script(
    script_name: str,
) -> dict[str, Any]:
    completed = subprocess.run(
        [
            sys.executable,
            (
                WORKSPACE_ROOT
                / "scripts"
                / script_name
            ).as_posix(),
        ],
        cwd=WORKSPACE_ROOT,
        check=False,
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    )

    if completed.stdout:
        print(completed.stdout)

    if completed.stderr:
        print(
            completed.stderr,
            file=sys.stderr,
        )

    if completed.returncode != 0:
        raise RuntimeError(
            f"{script_name} exited with "
            f"code {completed.returncode}."
        )

    return {
        "script": script_name,
        "return_code": (
            completed.returncode
        ),
        "stdout_sha256": hashlib.sha256(
            completed.stdout.encode(
                "utf-8"
            )
        ).hexdigest(),
        "stderr_sha256": hashlib.sha256(
            completed.stderr.encode(
                "utf-8"
            )
        ).hexdigest(),
    }


def verify_outputs() -> dict[str, Any]:
    silver_directory = (
        WORKSPACE_ROOT
        / "data"
        / "silver"
    )

    silver_files = sorted(
        silver_directory.glob(
            "silver_*.csv"
        )
    )

    if len(silver_files) != 10:
        raise RuntimeError(
            "Expected exactly 10 Silver CSV files."
        )

    manifest_file = (
        WORKSPACE_ROOT
        / "experiments"
        / "results"
        / "silver_build_manifest.csv"
    )

    validation_file = (
        WORKSPACE_ROOT
        / "experiments"
        / "results"
        / "silver_validation_summary.json"
    )

    manifest = pd.read_csv(
        manifest_file
    )

    validation = json.loads(
        validation_file.read_text(
            encoding="utf-8"
        )
    )

    if len(manifest) != 10:
        raise RuntimeError(
            "Expected 10 Silver manifest rows."
        )

    required_validation = {
        "overall_status": "PASS",
        "total_checks": 53,
        "passed_checks": 53,
        "failed_checks": 0,
        "critical_failures": 0,
    }

    for field_name, expected_value in (
        required_validation.items()
    ):
        if (
            validation.get(field_name)
            != expected_value
        ):
            raise RuntimeError(
                "Silver validation contract failed: "
                f"{field_name}."
            )

    output_files = []

    for file_name in silver_files:
        output_files.append(
            {
                "file_name": file_name.name,
                "relative_path": (
                    file_name.relative_to(
                        WORKSPACE_ROOT
                    ).as_posix()
                ),
                "size_bytes": (
                    file_name.stat().st_size
                ),
                "sha256": sha256_file(
                    file_name
                ),
            }
        )

    output_files.sort(
        key=lambda item: item["file_name"]
    )

    return {
        "dataset_count": len(output_files),
        "datasets": output_files,
        "validation": validation,
    }


def lambda_handler(
    event: dict[str, Any],
    context: Any,
) -> dict[str, Any]:
    mode = event.get(
        "mode"
    )

    if mode != "read-only-rehearsal":
        raise ValueError(
            "Only read-only-rehearsal mode "
            "is accepted by this candidate."
        )

    request_id = (
        getattr(
            context,
            "aws_request_id",
            None,
        )
        if context is not None
        else None
    )

    run_id = (
        request_id
        or "local-read-only-rehearsal"
    )

    contract = load_contract()

    prepare_workspace()

    downloads = download_inputs(
        contract
    )

    build_execution = run_script(
        "build_silver.py"
    )

    validation_execution = run_script(
        "validate_silver.py"
    )

    output_summary = verify_outputs()

    report = {
        "status": "PASS",
        "mode": mode,
        "run_id": run_id,
        "workspace_root": (
            WORKSPACE_ROOT.as_posix()
        ),
        "input_contract_sha256": (
            sha256_file(
                CONTRACT_FILE
            )
        ),
        "downloaded_inputs": (
            len(downloads)
        ),
        "downloaded_bytes": sum(
            item["size_bytes"]
            for item in downloads
        ),
        "build_execution": (
            build_execution
        ),
        "validation_execution": (
            validation_execution
        ),
        "output_summary": (
            output_summary
        ),
        "s3_write_operations": 0,
        "s3_delete_operations": 0,
    }

    report_file = (
        WORKSPACE_ROOT
        / "experiments"
        / "results"
        / "lambda_read_only_execution_report.json"
    )

    report_file.write_text(
        json.dumps(
            report,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    print(
        "Lambda read-only adapter execution: PASS"
    )

    print(
        "Inputs:",
        report["downloaded_inputs"],
    )

    print(
        "Silver datasets:",
        output_summary[
            "dataset_count"
        ],
    )

    print(
        "Validation checks:",
        output_summary[
            "validation"
        ]["passed_checks"],
    )

    return report
