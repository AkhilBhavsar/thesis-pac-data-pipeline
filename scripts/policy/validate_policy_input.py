from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError


def load_json(file_path: Path) -> object:
    return json.loads(
        file_path.read_text(encoding="utf-8")
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate a normalized C1 policy input "
            "against the thesis JSON Schema contract."
        )
    )

    parser.add_argument(
        "--schema",
        required=True,
        type=Path,
    )

    parser.add_argument(
        "--input",
        required=True,
        type=Path,
    )

    args = parser.parse_args()

    try:
        schema = load_json(args.schema)
        payload = load_json(args.input)

        Draft202012Validator.check_schema(schema)

        validator = Draft202012Validator(schema)

        errors = sorted(
            validator.iter_errors(payload),
            key=lambda error: (
                list(error.absolute_path),
                error.message,
            ),
        )

    except (
        OSError,
        json.JSONDecodeError,
        SchemaError,
    ) as error:
        print(
            json.dumps(
                {
                    "status": "ERROR",
                    "valid": False,
                    "error": str(error),
                },
                indent=2,
                sort_keys=True,
            )
        )

        return 2

    formatted_errors = [
        {
            "path": "/".join(
                str(part)
                for part in error.absolute_path
            ),
            "message": error.message,
            "validator": error.validator,
        }
        for error in errors
    ]

    result = {
        "status": (
            "PASS"
            if not errors
            else "FAIL"
        ),
        "valid": not errors,
        "schema_draft": "2020-12",
        "error_count": len(errors),
        "errors": formatted_errors,
    }

    print(
        json.dumps(
            result,
            indent=2,
            sort_keys=True,
        )
    )

    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
