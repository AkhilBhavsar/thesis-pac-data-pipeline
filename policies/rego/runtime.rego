package thesis.pac

import rego.v1

expected_isolated_output_tables := 15

runtime_integrity_failed if {
	input.runtime.pipeline_status != "PASS"
}

runtime_integrity_failed if {
	input.runtime.canonical_unchanged != true
}

runtime_integrity_failed if {
	input.runtime.isolated_output_tables != expected_isolated_output_tables
}

runtime_integrity_failed if {
	input.runtime.athena_failed_queries > 0
}

runtime_violations contains violation if {
	input.evaluation_stage == "post"
	runtime_integrity_failed

	violation := {
		"policy_id": "PAC-RUNTIME-001",
		"category": "runtime_validation",
		"severity": "deny",
		"pipeline_status": input.runtime.pipeline_status,
		"canonical_unchanged": input.runtime.canonical_unchanged,
		"isolated_output_tables": input.runtime.isolated_output_tables,
		"expected_isolated_output_tables": expected_isolated_output_tables,
		"athena_failed_queries": input.runtime.athena_failed_queries,
		"reason": sprintf(
			"runtime execution integrity failed: pipeline_status=%s canonical_unchanged=%v isolated_output_tables=%v expected_isolated_output_tables=%v athena_failed_queries=%v",
			[
				input.runtime.pipeline_status,
				input.runtime.canonical_unchanged,
				input.runtime.isolated_output_tables,
				expected_isolated_output_tables,
				input.runtime.athena_failed_queries,
			],
		),
	}
}

blocking_violations contains violation if {
	violation := runtime_violations[_]
}
