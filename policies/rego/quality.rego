package thesis.pac

import rego.v1

quality_violations contains violation if {
	input.evaluation_stage == "post"
	input.quality.status == "FAIL"

	violation := {
		"policy_id": "PAC-QUALITY-001",
		"category": "runtime_validation",
		"severity": "deny",
		"quality_status": input.quality.status,
		"total_tests": input.quality.total_tests,
		"failed_tests": input.quality.failed_tests,
		"critical_failures": input.quality.critical_failures,
		"reason": sprintf(
			"critical data-quality validation failed: failed_tests=%v critical_failures=%v",
			[
				input.quality.failed_tests,
				input.quality.critical_failures,
			],
		),
	}
}

blocking_violations contains violation if {
	violation := quality_violations[_]
}
