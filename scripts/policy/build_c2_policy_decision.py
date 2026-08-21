#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema import FormatChecker


SHA256_PATTERN = re.compile(
    r"^[0-9a-f]{64}$"
)


class ProjectionError(RuntimeError):
    pass


def canonical_bytes(
    value: Any,
) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode(
        "utf-8"
    )


def load_json(
    path: Path,
) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )
    except (
        OSError,
        json.JSONDecodeError,
    ) as error:
        raise ProjectionError(
            f"Unable to load JSON from {path}: {error}"
        ) from error

    if not isinstance(
        value,
        dict,
    ):
        raise ProjectionError(
            f"Expected JSON object in {path}."
        )

    return value


def sha256_file(
    path: Path,
) -> str:
    digest = hashlib.sha256()

    with path.open(
        "rb"
    ) as handle:
        for chunk in iter(
            lambda: handle.read(
                1024 * 1024
            ),
            b"",
        ):
            digest.update(
                chunk
            )

    return digest.hexdigest()


def require_sha256(
    value: Any,
    *,
    label: str,
) -> str:
    if (
        not isinstance(
            value,
            str,
        )
        or SHA256_PATTERN.fullmatch(
            value
        )
        is None
    ):
        raise ProjectionError(
            f"{label} must be a 64-character "
            "lowercase SHA-256."
        )

    return value


def validate_schema_document(
    *,
    schema: dict[str, Any],
    document: dict[str, Any],
) -> None:
    validator = Draft202012Validator(
        schema,
        format_checker=FormatChecker(),
    )

    errors = sorted(
        validator.iter_errors(
            document
        ),
        key=lambda error: list(
            error.absolute_path
        ),
    )

    if not errors:
        return

    rendered = []

    for error in errors:
        path = "/".join(
            str(component)
            for component
            in error.absolute_path
        )

        rendered.append(
            f"{path or '$'}: {error.message}"
        )

    raise ProjectionError(
        "Projected C2 decision failed schema validation: "
        + "; ".join(
            rendered
        )
    )


def write_json_atomic(
    *,
    path: Path,
    document: dict[str, Any],
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(
            path.parent
        ),
    )

    temporary_path = Path(
        temporary
    )

    try:
        with os.fdopen(
            descriptor,
            "wb",
        ) as handle:
            handle.write(
                canonical_bytes(
                    document
                )
            )

            handle.flush()

            os.fsync(
                handle.fileno()
            )

        os.replace(
            temporary_path,
            path,
        )

    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def validate_catalog(
    catalog: dict[str, Any],
) -> dict[str, Any]:
    if catalog.get(
        "condition"
    ) != "C2":
        raise ProjectionError(
            "C2 remediation catalog condition "
            "must equal C2."
        )

    scenarios = catalog.get(
        "scenarios"
    )

    if (
        not isinstance(
            scenarios,
            dict,
        )
        or not scenarios
    ):
        raise ProjectionError(
            "C2 remediation catalog scenarios "
            "must be a non-empty object."
        )

    return scenarios


def validate_source_c1_decision(
    *,
    decision: dict[str, Any],
    catalog: dict[str, Any],
) -> tuple[
    str,
    dict[str, Any],
    list[str],
    str,
    str,
]:
    scenarios = validate_catalog(
        catalog
    )

    if decision.get(
        "condition"
    ) != "C1":
        raise ProjectionError(
            "Projection source must be an "
            "explicit C1 policy decision."
        )

    if decision.get(
        "decision"
    ) != "DENY":
        raise ProjectionError(
            "C2 remediation projection requires "
            "a C1 DENY."
        )

    if decision.get(
        "allow"
    ) is not False:
        raise ProjectionError(
            "C1 DENY must record allow=false."
        )

    if decision.get(
        "promotion_requested"
    ) is not True:
        raise ProjectionError(
            "C2 remediation projection requires "
            "promotion_requested=true."
        )

    recorded_at = decision.get(
        "recorded_at_utc"
    )

    if (
        not isinstance(
            recorded_at,
            str,
        )
        or not recorded_at.strip()
    ):
        raise ProjectionError(
            "C1 decision requires recorded_at_utc."
        )

    run_key = decision.get(
        "run_key"
    )

    if (
        not isinstance(
            run_key,
            str,
        )
        or not run_key.strip()
    ):
        raise ProjectionError(
            "C1 decision requires a non-empty run_key."
        )

    scenario_id = decision.get(
        "scenario_id"
    )

    if scenario_id not in scenarios:
        raise ProjectionError(
            "C1 decision scenario is absent "
            "from the C2 remediation catalog."
        )

    scenario = scenarios[
        scenario_id
    ]

    if not isinstance(
        scenario,
        dict,
    ):
        raise ProjectionError(
            "C2 scenario definition must be an object."
        )

    detection_stage = scenario.get(
        "detection_stage"
    )

    if detection_stage not in {
        "pre",
        "post",
    }:
        raise ProjectionError(
            "C2 scenario requires pre/post detection_stage."
        )

    if decision.get(
        "evaluation_stage"
    ) != detection_stage:
        raise ProjectionError(
            "C1 decision evaluation stage does not "
            "match C2 scenario detection stage."
        )

    triggered = decision.get(
        "triggered_policy_ids"
    )

    if (
        not isinstance(
            triggered,
            list,
        )
        or not triggered
        or not all(
            isinstance(
                item,
                str,
            )
            and item
            for item in triggered
        )
    ):
        raise ProjectionError(
            "C1 DENY must contain triggered_policy_ids."
        )

    if len(
        set(
            triggered
        )
    ) != len(
        triggered
    ):
        raise ProjectionError(
            "Triggered policy IDs must be unique."
        )

    controls = decision.get(
        "controls"
    )

    if not isinstance(
        controls,
        dict,
    ):
        raise ProjectionError(
            "C1 decision controls must be an object."
        )

    if controls.get(
        "policy_as_code_required"
    ) is not True:
        raise ProjectionError(
            "C1 decision must require Policy-as-Code."
        )

    if controls.get(
        "self_healing_permitted"
    ) is not False:
        raise ProjectionError(
            "Source C1 decision must have "
            "self_healing_permitted=false."
        )

    if controls.get(
        "automatic_remediation_permitted"
    ) is not False:
        raise ProjectionError(
            "Source C1 decision must have "
            "automatic_remediation_permitted=false."
        )

    measurement = decision.get(
        "measurement"
    )

    if not isinstance(
        measurement,
        dict,
    ):
        raise ProjectionError(
            "C1 decision measurement must be an object."
        )

    if measurement.get(
        "promotion_requested"
    ) is not True:
        raise ProjectionError(
            "C1 decision measurement must record "
            "promotion_requested=true."
        )

    if measurement.get(
        "promotion_blocked"
    ) is not True:
        raise ProjectionError(
            "C2 remediation requires promotion to "
            "already be blocked by the C1 DENY."
        )

    input_sha = require_sha256(
        decision.get(
            "input_sha256"
        ),
        label="C1 input_sha256",
    )

    policy_bundle_sha = require_sha256(
        decision.get(
            "policy_bundle_sha256"
        ),
        label="C1 policy_bundle_sha256",
    )

    automatic = scenario.get(
        "automatic_remediation_permitted"
    )

    if automatic not in {
        True,
        False,
    }:
        raise ProjectionError(
            "C2 scenario must explicitly define "
            "automatic_remediation_permitted."
        )

    return (
        scenario_id,
        scenario,
        sorted(
            triggered
        ),
        input_sha,
        policy_bundle_sha,
    )


def build_c2_policy_decision(
    *,
    source_decision: dict[str, Any],
    source_decision_sha256: str,
    catalog: dict[str, Any],
) -> dict[str, Any]:
    source_sha = require_sha256(
        source_decision_sha256,
        label="Source policy decision SHA-256",
    )

    (
        scenario_id,
        scenario,
        triggered,
        input_sha,
        policy_bundle_sha,
    ) = validate_source_c1_decision(
        decision=source_decision,
        catalog=catalog,
    )

    automatic = scenario[
        "automatic_remediation_permitted"
    ]

    return {
        "schema_version": "1.0.0",
        "condition": "C2",
        "recorded_at_utc": source_decision[
            "recorded_at_utc"
        ],
        "run_key": source_decision[
            "run_key"
        ],
        "scenario_id": scenario_id,
        "evaluation_stage": scenario[
            "detection_stage"
        ],
        "promotion_requested": True,
        "decision": "DENY",
        "allow": False,
        "triggered_policy_ids": triggered,
        "controls": {
            "policy_as_code_required": True,
            "self_healing_permitted": True,
            "automatic_remediation_permitted": (
                automatic
            ),
        },
        "measurement": {
            "promotion_requested": True,
            "promotion_blocked": True,
        },
        "projection": {
            "method": (
                "c1_deny_to_c2_bounded_remediation_v1"
            ),
            "source_condition": "C1",
            "source_policy_decision_sha256": (
                source_sha
            ),
            "source_input_sha256": (
                input_sha
            ),
            "source_policy_bundle_sha256": (
                policy_bundle_sha
            ),
            "source_self_healing_permitted": False,
            "source_automatic_remediation_permitted": (
                False
            ),
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Project one blocked C1 Policy-as-Code "
            "DENY into an explicit provenance-linked "
            "C2 bounded-remediation decision."
        )
    )

    parser.add_argument(
        "--decision",
        required=True,
        type=Path,
        help="Source C1 policy decision JSON.",
    )

    parser.add_argument(
        "--catalog",
        required=True,
        type=Path,
        help="C2 remediation catalog.",
    )

    parser.add_argument(
        "--schema",
        required=True,
        type=Path,
        help="C2 projected-decision schema.",
    )

    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="Projected C2 decision output.",
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        source_decision = load_json(
            args.decision
        )

        catalog = load_json(
            args.catalog
        )

        schema = load_json(
            args.schema
        )

        Draft202012Validator.check_schema(
            schema
        )

        projected = build_c2_policy_decision(
            source_decision=source_decision,
            source_decision_sha256=sha256_file(
                args.decision
            ),
            catalog=catalog,
        )

        validate_schema_document(
            schema=schema,
            document=projected,
        )

        write_json_atomic(
            path=args.output,
            document=projected,
        )

        sys.stdout.write(
            json.dumps(
                projected,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )

        return 0

    except (
        ProjectionError,
        OSError,
        ValueError,
    ) as error:
        print(
            f"ERROR: {error}",
            file=sys.stderr,
        )

        return 1


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
