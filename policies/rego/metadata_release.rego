package thesis.pac

import rego.v1

valid_nonempty_string(value) if {
	is_string(value)
	count(value) > 0
}

metadata_violations contains violation if {
	not valid_nonempty_string(input.git.branch)

	violation := {
		"policy_id": "PAC-META-001",
		"category": "metadata",
		"severity": "deny",
		"reason": "git branch is missing or empty",
	}
}

metadata_violations contains violation if {
	not valid_nonempty_string(input.git.commit)

	violation := {
		"policy_id": "PAC-META-001",
		"category": "metadata",
		"severity": "deny",
		"reason": "git commit is missing or empty",
	}
}

metadata_violations contains violation if {
	not valid_nonempty_string(input.experiment.run_key)

	violation := {
		"policy_id": "PAC-META-001",
		"category": "metadata",
		"severity": "deny",
		"reason": "experiment run key is missing or empty",
	}
}

metadata_violations contains violation if {
	input.metadata.required_fields_present == false

	violation := {
		"policy_id": "PAC-META-001",
		"category": "metadata",
		"severity": "deny",
		"reason": "required governance metadata is incomplete",
	}
}

metadata_violations contains violation if {
	input.metadata.resource_count <= 0

	violation := {
		"policy_id": "PAC-META-001",
		"category": "metadata",
		"severity": "deny",
		"reason": "governed resource inventory is empty",
	}
}

blocking_violations contains violation if {
	violation := metadata_violations[_]
}

release_violations contains violation if {
	input.release.promotion_requested == true
	count(blocking_violations) > 0

	violation := {
		"policy_id": "PAC-RELEASE-001",
		"category": "release_rule",
		"severity": "deny",
		"reason": "promotion requested while blocking policy violations remain unresolved",
	}
}

violations contains violation if {
	violation := blocking_violations[_]
}

violations contains violation if {
	violation := release_violations[_]
}

default allow := false

allow if {
	count(violations) == 0
}

deny contains message if {
	violation := violations[_]

	message := sprintf(
		"%s: %s",
		[
			violation.policy_id,
			violation.reason,
		],
	)
}
