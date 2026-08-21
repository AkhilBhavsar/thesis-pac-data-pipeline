package thesis.pac_runtime_test

import rego.v1

import data.thesis.pac

safe_runtime := {
	"pipeline_status": "PASS",
	"canonical_unchanged": true,
	"isolated_output_tables": 15,
	"athena_failed_queries": 0,
}

safe_post_input := {
	"evaluation_stage": "post",
	"experiment": {
		"condition": "C1",
		"scenario_id": "baseline",
		"run_key": "runtime-safe-post",
	},
	"release": {
		"promotion_requested": true,
	},
	"runtime": safe_runtime,
}

pre_failed_runtime_input := {
	"evaluation_stage": "pre",
	"experiment": {
		"condition": "C1",
		"scenario_id": "quality_regression",
		"run_key": "runtime-pre-failure",
	},
	"release": {
		"promotion_requested": true,
	},
	"runtime": {
		"pipeline_status": "FAIL",
		"canonical_unchanged": false,
		"isolated_output_tables": 14,
		"athena_failed_queries": 1,
	},
}

pipeline_failed_input := {
	"evaluation_stage": "post",
	"experiment": {
		"condition": "C1",
		"scenario_id": "quality_regression",
		"run_key": "runtime-pipeline-failure",
	},
	"release": {
		"promotion_requested": true,
	},
	"runtime": {
		"pipeline_status": "FAIL",
		"canonical_unchanged": true,
		"isolated_output_tables": 15,
		"athena_failed_queries": 0,
	},
}

canonical_failed_input := {
	"evaluation_stage": "post",
	"experiment": {
		"condition": "C1",
		"scenario_id": "schema_break",
		"run_key": "runtime-canonical-failure",
	},
	"release": {
		"promotion_requested": true,
	},
	"runtime": {
		"pipeline_status": "PASS",
		"canonical_unchanged": false,
		"isolated_output_tables": 15,
		"athena_failed_queries": 0,
	},
}

isolated_count_failed_input := {
	"evaluation_stage": "post",
	"experiment": {
		"condition": "C1",
		"scenario_id": "schema_break",
		"run_key": "runtime-isolated-count-failure",
	},
	"release": {
		"promotion_requested": true,
	},
	"runtime": {
		"pipeline_status": "PASS",
		"canonical_unchanged": true,
		"isolated_output_tables": 14,
		"athena_failed_queries": 0,
	},
}

athena_failed_input := {
	"evaluation_stage": "post",
	"experiment": {
		"condition": "C1",
		"scenario_id": "quality_regression",
		"run_key": "runtime-athena-failure",
	},
	"release": {
		"promotion_requested": true,
	},
	"runtime": {
		"pipeline_status": "PASS",
		"canonical_unchanged": true,
		"isolated_output_tables": 15,
		"athena_failed_queries": 1,
	},
}

multiple_failures_input := {
	"evaluation_stage": "post",
	"experiment": {
		"condition": "C1",
		"scenario_id": "quality_regression",
		"run_key": "runtime-multiple-failures",
	},
	"release": {
		"promotion_requested": true,
	},
	"runtime": {
		"pipeline_status": "FAIL",
		"canonical_unchanged": false,
		"isolated_output_tables": 14,
		"athena_failed_queries": 2,
	},
}

failure_without_promotion_input := {
	"evaluation_stage": "post",
	"experiment": {
		"condition": "C1",
		"scenario_id": "quality_regression",
		"run_key": "runtime-no-promotion",
	},
	"release": {
		"promotion_requested": false,
	},
	"runtime": pipeline_failed_input.runtime,
}

test_safe_runtime_allows if {
	found := pac.runtime_violations with input as safe_post_input
	count(found) == 0

	result := pac.allow with input as safe_post_input
	result == true
}

test_runtime_policy_is_post_stage_only if {
	found := pac.runtime_violations with input as pre_failed_runtime_input
	count(found) == 0

	result := pac.allow with input as pre_failed_runtime_input
	result == true
}

test_pipeline_failure_blocks if {
	found := pac.runtime_violations with input as pipeline_failed_input
	count(found) == 1

	violation := found[_]

	violation.policy_id == "PAC-RUNTIME-001"
	violation.pipeline_status == "FAIL"
}

test_canonical_mutation_blocks if {
	found := pac.runtime_violations with input as canonical_failed_input
	count(found) == 1

	violation := found[_]

	violation.policy_id == "PAC-RUNTIME-001"
	violation.canonical_unchanged == false
}

test_isolated_output_count_mismatch_blocks if {
	found := pac.runtime_violations with input as isolated_count_failed_input
	count(found) == 1

	violation := found[_]

	violation.policy_id == "PAC-RUNTIME-001"
	violation.isolated_output_tables == 14
	violation.expected_isolated_output_tables == 15
}

test_athena_failure_blocks if {
	found := pac.runtime_violations with input as athena_failed_input
	count(found) == 1

	violation := found[_]

	violation.policy_id == "PAC-RUNTIME-001"
	violation.athena_failed_queries == 1
}

test_multiple_integrity_failures_emit_one_runtime_policy_violation if {
	found := pac.runtime_violations with input as multiple_failures_input
	count(found) == 1
}

test_runtime_failure_blocks_release_when_promotion_requested if {
	found := pac.violations with input as pipeline_failed_input

	ids := {
		item.policy_id |
			item := found[_]
	}

	ids == {
		"PAC-RUNTIME-001",
		"PAC-RELEASE-001",
	}
}

test_runtime_failure_remains_blocking_without_promotion if {
	found := pac.violations with input as failure_without_promotion_input

	ids := {
		item.policy_id |
			item := found[_]
	}

	ids == {
		"PAC-RUNTIME-001",
	}

	result := pac.allow with input as failure_without_promotion_input
	result == false
}
