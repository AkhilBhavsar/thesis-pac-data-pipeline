package thesis.pac

import rego.v1

privacy_violations contains violation if {
	count(input.privacy.detected_forbidden_columns) > 0

	violation := {
		"policy_id": "PAC-PRIVACY-001",
		"category": "schema_contract",
		"severity": "deny",
		"public_models": input.privacy.public_models,
		"detected_forbidden_columns": input.privacy.detected_forbidden_columns,
		"reason": sprintf(
			"public Gold output contains governed forbidden columns: %v",
			[
				input.privacy.detected_forbidden_columns,
			],
		),
	}
}

blocking_violations contains violation if {
	violation := privacy_violations[_]
}
