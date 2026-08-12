package thesis.pac_quality_test

import data.thesis.pac as pac
import rego.v1

common_metadata := {
	"required_fields_present": true,
	"resource_count": 15,
}

common_schema := {
	"governed_models": [],
}

common_privacy := {
	"public_models": [
		"gold_public_sales_dashboard",
	],
	"forbidden_columns": [
		"customer_id",
		"synthetic_email",
	],
	"detected_forbidden_columns": [],
}

pre_input := {
	"evaluation_stage": "pre",
	"git": {
		"branch": "feature/policy-as-code-gates",
		"commit": "292a089c0c69af6eb49af40263cc2658358fbe04",
	},
	"experiment": {
		"condition": "C1",
		"scenario_id": "baseline",
		"run_key": "c1-quality-pre-not-evaluated",
	},
	"release": {
		"promotion_requested": true,
	},
	"metadata": common_metadata,
	"schema_contract": common_schema,
	"privacy": common_privacy,
	"quality": {
		"status": "NOT_EVALUATED",
		"total_tests": 0,
		"failed_tests": 0,
		"critical_failures": [],
	},
}

post_pass_input := {
	"evaluation_stage": "post",
	"git": pre_input.git,
	"experiment": {
		"condition": "C1",
		"scenario_id": "baseline",
		"run_key": "c1-quality-post-pass",
	},
	"release": {
		"promotion_requested": true,
	},
	"metadata": common_metadata,
	"schema_contract": common_schema,
	"privacy": common_privacy,
	"quality": {
		"status": "PASS",
		"total_tests": 1,
		"failed_tests": 0,
		"critical_failures": [],
	},
}

post_fail_input := {
	"evaluation_stage": "post",
	"git": pre_input.git,
	"experiment": {
		"condition": "C1",
		"scenario_id": "quality_regression",
		"run_key": "c1-quality-regression",
	},
	"release": {
		"promotion_requested": true,
	},
	"metadata": common_metadata,
	"schema_contract": common_schema,
	"privacy": common_privacy,
	"quality": {
		"status": "FAIL",
		"total_tests": 1,
		"failed_tests": 1,
		"critical_failures": [
			"gold_daily_sales:not_null_revenue",
		],
	},
}

post_fail_no_promotion_input := {
	"evaluation_stage": "post",
	"git": post_fail_input.git,
	"experiment": {
		"condition": "C1",
		"scenario_id": "quality_regression",
		"run_key": "c1-quality-regression-no-promotion",
	},
	"release": {
		"promotion_requested": false,
	},
	"metadata": common_metadata,
	"schema_contract": common_schema,
	"privacy": common_privacy,
	"quality": post_fail_input.quality,
}

pre_fail_input := {
	"evaluation_stage": "pre",
	"git": post_fail_input.git,
	"experiment": {
		"condition": "C1",
		"scenario_id": "quality_regression",
		"run_key": "c1-quality-pre-stage-fail",
	},
	"release": {
		"promotion_requested": true,
	},
	"metadata": common_metadata,
	"schema_contract": common_schema,
	"privacy": common_privacy,
	"quality": post_fail_input.quality,
}

test_pre_not_evaluated_does_not_block if {
	result := pac.allow with input as pre_input
	result == true

	found := pac.quality_violations with input as pre_input
	count(found) == 0
}

test_post_pass_allows if {
	result := pac.allow with input as post_pass_input
	result == true

	found := pac.quality_violations with input as post_pass_input
	count(found) == 0
}

test_post_quality_failure_blocks if {
	result := pac.allow with input as post_fail_input
	result == false

	found := pac.quality_violations with input as post_fail_input
	count(found) == 1

	violation := found[_]

	violation.policy_id == "PAC-QUALITY-001"
	violation.quality_status == "FAIL"
	violation.failed_tests == 1
}

test_post_quality_failure_blocks_release if {
	found := pac.violations with input as post_fail_input

	ids := {
	item.policy_id |
		item := found[_]
	}

	ids == {
		"PAC-QUALITY-001",
		"PAC-RELEASE-001",
	}
}

test_quality_failure_remains_without_promotion if {
	result := pac.allow with input as post_fail_no_promotion_input
	result == false

	found := pac.violations with input as post_fail_no_promotion_input

	ids := {
	item.policy_id |
		item := found[_]
	}

	ids == {
		"PAC-QUALITY-001",
	}
}

test_quality_policy_is_post_stage_only if {
	found := pac.quality_violations with input as pre_fail_input
	count(found) == 0

	result := pac.allow with input as pre_fail_input
	result == true
}
