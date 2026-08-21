package thesis.pac

import rego.v1

transformation_violations contains violation if {
	input.evaluation_stage == "pre"
	count(input.transformation.unapproved_definitions) > 0

	violation := {
		"policy_id": "PAC-TRANSFORM-001",
		"category": "transformation_definition",
		"severity": "deny",
		"changed_models": input.transformation.changed_models,
		"unapproved_definitions": input.transformation.unapproved_definitions,
		"manifest_sha256": input.transformation.manifest_sha256,
		"reason": sprintf(
			"unapproved or out-of-scope governed transformation definitions detected: %v",
			[
				input.transformation.unapproved_definitions,
			],
		),
	}
}

blocking_violations contains violation if {
	violation := transformation_violations[_]
}
