#!/usr/bin/env python3

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


class PlannerError(RuntimeError):
    pass


def load_json(path: Path) -> Any:
    try:
        return json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )
    except FileNotFoundError as exc:
        raise PlannerError(
            f"JSON file does not exist: {path}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise PlannerError(
            f"Invalid JSON in {path}: {exc}"
        ) from exc


def sha256_file(path: Path) -> str:
    return hashlib.sha256(
        path.read_bytes()
    ).hexdigest()


def validate_schema_document(
    schema: dict[str, Any],
    document: dict[str, Any],
) -> None:
    Draft202012Validator.check_schema(
        schema
    )

    validator = Draft202012Validator(
        schema
    )

    errors = sorted(
        validator.iter_errors(
            document
        ),
        key=lambda error: (
            list(error.absolute_path),
            error.message,
        ),
    )

    if errors:
        rendered = []

        for error in errors:
            path = ".".join(
                str(part)
                for part
                in error.absolute_path
            )

            rendered.append(
                f"{path or '<root>'}: "
                f"{error.message}"
            )

        raise PlannerError(
            "Remediation plan schema "
            "validation failed: "
            + " | ".join(rendered)
        )


def validate_catalog(
    catalog: dict[str, Any],
) -> None:
    if catalog.get("condition") != "C2":
        raise PlannerError(
            "Remediation catalog must "
            "belong to condition C2."
        )

    principles = catalog.get(
        "principles"
    )

    scenarios = catalog.get(
        "scenarios"
    )

    actions = catalog.get(
        "actions"
    )

    if not isinstance(
        principles,
        dict,
    ):
        raise PlannerError(
            "Catalog principles must "
            "be an object."
        )

    if not isinstance(
        scenarios,
        dict,
    ) or not scenarios:
        raise PlannerError(
            "Catalog scenarios must "
            "be a non-empty object."
        )

    if not isinstance(
        actions,
        list,
    ) or not actions:
        raise PlannerError(
            "Catalog actions must "
            "be a non-empty array."
        )

    maximum_attempts = principles.get(
        "maximum_automatic_attempts"
    )

    maximum_timeout = principles.get(
        "maximum_automatic_timeout_seconds"
    )

    if (
        not isinstance(
            maximum_attempts,
            int,
        )
        or isinstance(
            maximum_attempts,
            bool,
        )
        or maximum_attempts < 1
    ):
        raise PlannerError(
            "Invalid global maximum "
            "automatic attempt bound."
        )

    if (
        not isinstance(
            maximum_timeout,
            int,
        )
        or isinstance(
            maximum_timeout,
            bool,
        )
        or maximum_timeout <= 0
    ):
        raise PlannerError(
            "Invalid global maximum "
            "automatic timeout bound."
        )

    if (
        principles.get(
            "fail_closed"
        )
        is not True
    ):
        raise PlannerError(
            "C2 catalog must fail closed."
        )

    if (
        principles.get(
            "promotion_blocked_until_verified_safe"
        )
        is not True
    ):
        raise PlannerError(
            "Promotion must remain blocked "
            "until verification."
        )

    if (
        principles.get(
            "verification_required_after_action"
        )
        is not True
    ):
        raise PlannerError(
            "Post-action verification "
            "must be mandatory."
        )

    if (
        principles.get(
            "canonical_mutation_before_verification"
        )
        is not False
    ):
        raise PlannerError(
            "Canonical mutation before "
            "verification must be forbidden."
        )

    for scenario_id, scenario in (
        scenarios.items()
    ):
        if not isinstance(
            scenario,
            dict,
        ):
            raise PlannerError(
                f"Scenario {scenario_id} "
                "must be an object."
            )

        automatic = scenario.get(
            "automatic_remediation_permitted"
        )

        attempts = scenario.get(
            "max_attempts"
        )

        timeout = scenario.get(
            "timeout_seconds"
        )

        primary = scenario.get(
            "primary_action"
        )

        fallback = scenario.get(
            "fallback_action"
        )

        verification = scenario.get(
            "verification"
        )

        if primary not in actions:
            raise PlannerError(
                f"Scenario {scenario_id} "
                "uses unknown primary action."
            )

        if fallback not in actions:
            raise PlannerError(
                f"Scenario {scenario_id} "
                "uses unknown fallback action."
            )

        if (
            not isinstance(
                verification,
                list,
            )
            or not verification
        ):
            raise PlannerError(
                f"Scenario {scenario_id} "
                "must define verification."
            )

        if (
            not isinstance(
                attempts,
                int,
            )
            or isinstance(
                attempts,
                bool,
            )
        ):
            raise PlannerError(
                f"Scenario {scenario_id} "
                "has invalid attempt bound."
            )

        if (
            not isinstance(
                timeout,
                int,
            )
            or isinstance(
                timeout,
                bool,
            )
        ):
            raise PlannerError(
                f"Scenario {scenario_id} "
                "has invalid timeout bound."
            )

        if attempts > maximum_attempts:
            raise PlannerError(
                f"Scenario {scenario_id} "
                "exceeds global attempt bound."
            )

        if timeout > maximum_timeout:
            raise PlannerError(
                f"Scenario {scenario_id} "
                "exceeds global timeout bound."
            )

        if automatic is True:
            if attempts < 1:
                raise PlannerError(
                    f"Automatic scenario "
                    f"{scenario_id} requires "
                    "at least one attempt."
                )

            if timeout <= 0:
                raise PlannerError(
                    f"Automatic scenario "
                    f"{scenario_id} requires "
                    "a positive timeout."
                )

        elif automatic is False:
            if attempts != 0:
                raise PlannerError(
                    f"Manual scenario "
                    f"{scenario_id} must "
                    "have zero attempts."
                )

            if timeout != 0:
                raise PlannerError(
                    f"Manual scenario "
                    f"{scenario_id} must "
                    "have zero timeout."
                )

        else:
            raise PlannerError(
                f"Scenario {scenario_id} "
                "must explicitly define "
                "automatic remediation."
            )


def validate_source_decision(
    decision: dict[str, Any],
    catalog: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    if not isinstance(
        decision,
        dict,
    ):
        raise PlannerError(
            "Policy decision must "
            "be a JSON object."
        )

    if decision.get(
        "condition"
    ) != "C2":
        raise PlannerError(
            "Remediation planner accepts "
            "only C2-labelled policy decisions."
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
        raise PlannerError(
            "Policy decision requires "
            "a non-empty run_key."
        )

    recorded_at_utc = decision.get(
        "recorded_at_utc"
    )

    if (
        not isinstance(
            recorded_at_utc,
            str,
        )
        or not recorded_at_utc.strip()
    ):
        raise PlannerError(
            "Policy decision requires "
            "recorded_at_utc for recovery "
            "measurement."
        )

    scenario_id = decision.get(
        "scenario_id"
    )

    scenarios = catalog[
        "scenarios"
    ]

    if scenario_id not in scenarios:
        raise PlannerError(
            "Policy decision scenario is "
            "not present in the C2 catalog."
        )

    scenario = scenarios[
        scenario_id
    ]

    evaluation_stage = decision.get(
        "evaluation_stage"
    )

    if (
        evaluation_stage
        != scenario.get(
            "detection_stage"
        )
    ):
        raise PlannerError(
            "Policy decision evaluation "
            "stage does not match the "
            "catalog scenario."
        )

    if decision.get(
        "decision"
    ) != "DENY":
        raise PlannerError(
            "Remediation planning requires "
            "a DENY policy decision."
        )

    if decision.get(
        "allow"
    ) is not False:
        raise PlannerError(
            "DENY policy decision must "
            "have allow=false."
        )

    if decision.get(
        "promotion_requested"
    ) is not True:
        raise PlannerError(
            "Remediation planning requires "
            "promotion_requested=true."
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
            for item
            in triggered
        )
    ):
        raise PlannerError(
            "DENY policy decision must "
            "contain triggered policy IDs."
        )

    if len(set(triggered)) != len(
        triggered
    ):
        raise PlannerError(
            "Triggered policy IDs "
            "must be unique."
        )

    measurement = decision.get(
        "measurement"
    )

    if not isinstance(
        measurement,
        dict,
    ):
        raise PlannerError(
            "Policy decision requires "
            "measurement evidence."
        )

    if (
        measurement.get(
            "promotion_requested"
        )
        is not True
    ):
        raise PlannerError(
            "Policy decision measurement "
            "must record promotion requested."
        )

    if (
        measurement.get(
            "promotion_blocked"
        )
        is not True
    ):
        raise PlannerError(
            "Remediation planning requires "
            "promotion to already be blocked."
        )

    return scenario_id, scenario


def build_remediation_plan(
    *,
    decision: dict[str, Any],
    catalog: dict[str, Any],
    decision_sha256: str,
) -> dict[str, Any]:
    validate_catalog(
        catalog
    )

    (
        scenario_id,
        scenario,
    ) = validate_source_decision(
        decision,
        catalog,
    )

    automatic = scenario[
        "automatic_remediation_permitted"
    ]

    mode = (
        "automatic"
        if automatic
        else "manual"
    )

    triggered = sorted(
        decision[
            "triggered_policy_ids"
        ]
    )

    plan = {
        "schema_version": "1.0.0",
        "condition": "C2",
        "scenario_id": scenario_id,
        "run_key": decision[
            "run_key"
        ],
        "fault_detected_at_utc": decision[
            "recorded_at_utc"
        ],
        "source_policy_decision_sha256": (
            decision_sha256
        ),
        "source_policy_decision": {
            "evaluation_stage": decision[
                "evaluation_stage"
            ],
            "decision": "DENY",
            "triggered_policy_ids": (
                triggered
            ),
            "promotion_blocked": True,
        },
        "controls": {
            "policy_as_code_required": True,
            "self_healing_permitted": True,
            "automatic_remediation_permitted": (
                automatic
            ),
        },
        "plan": {
            "mode": mode,
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
        },
        "rationale": (
            "Policy DENY selected the "
            "catalog-governed bounded "
            f"remediation plan for "
            f"{scenario_id}: "
            f"{scenario['primary_action']} "
            "with fallback "
            f"{scenario['fallback_action']}."
        ),
    }

    return plan


def canonical_json(
    payload: dict[str, Any],
) -> str:
    return (
        json.dumps(
            payload,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


def write_atomic(
    output_path: Path,
    content: str,
) -> None:
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=output_path.parent,
        prefix=(
            f".{output_path.name}."
        ),
        suffix=".tmp",
        delete=False,
    ) as handle:
        temporary = Path(
            handle.name
        )

        handle.write(
            content
        )

        handle.flush()

    temporary.replace(
        output_path
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build one catalog-driven "
            "bounded C2 remediation plan "
            "from a blocked C2 policy DENY."
        )
    )

    parser.add_argument(
        "--decision",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--catalog",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--schema",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--output",
        required=True,
        type=Path,
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        decision = load_json(
            args.decision
        )

        catalog = load_json(
            args.catalog
        )

        schema = load_json(
            args.schema
        )

        if not isinstance(
            catalog,
            dict,
        ):
            raise PlannerError(
                "Remediation catalog must "
                "be a JSON object."
            )

        if not isinstance(
            schema,
            dict,
        ):
            raise PlannerError(
                "Remediation plan schema "
                "must be a JSON object."
            )

        plan = build_remediation_plan(
            decision=decision,
            catalog=catalog,
            decision_sha256=sha256_file(
                args.decision
            ),
        )

        validate_schema_document(
            schema,
            plan,
        )

        rendered = canonical_json(
            plan
        )

        write_atomic(
            args.output,
            rendered,
        )

        sys.stdout.write(
            rendered
        )

        return 0

    except (
        PlannerError,
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
