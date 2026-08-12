package thesis.pac_freshness_test

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

common_quality := {
	"status": "PASS",
	"total_tests": 1,
	"failed_tests": 0,
	"critical_failures": [],
}

pre_not_evaluated_input := {
	"evaluation_stage": "pre",
	"git": {
		"branch": "feature/policy-as-code-gates",
		"commit": "3d3684046a626c3e5248c4ac440135fabe533d43",
	},
	"experiment": {
		"condition": "C1",
		"scenario_id": "baseline",
		"run_key": "c1-freshness-pre-not-evaluated",
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
	"freshness": {
		"status": "NOT_EVALUATED",
		"sources": [],
	},
}

post_pass_input := {
	"evaluation_stage": "post",
	"git": pre_not_evaluated_input.git,
	"experiment": {
		"condition": "C1",
		"scenario_id": "baseline",
		"run_key": "c1-freshness-post-pass",
	},
	"release": {
		"promotion_requested": true,
	},
	"metadata": common_metadata,
	"schema_contract": common_schema,
	"privacy": common_privacy,
	"quality": common_quality,
	"freshness": {
		"status": "PASS",
		"sources": [
			{
				"source": "bronze_orders",
				"observed_age_seconds": 300,
				"maximum_age_seconds": 900,
				"status": "PASS",
			},
		],
	},
}

post_breach_input := {
	"evaluation_stage": "post",
	"git": pre_not_evaluated_input.git,
	"experiment": {
		"condition": "C1",
		"scenario_id": "freshness_breach",
		"run_key": "c1-freshness-breach",
	},
	"release": {
		"promotion_requested": true,
	},
	"metadata": common_metadata,
	"schema_contract": common_schema,
	"privacy": common_privacy,
	"quality": common_quality,
	"freshness": {
		"status": "FAIL",
		"sources": [
			{
				"source": "bronze_orders",
				"observed_age_seconds": 1200,
				"maximum_age_seconds": 900,
				"status": "FAIL",
			},
		],
	},
}

post_breach_no_promotion_input := {
	"evaluation_stage": "post",
	"git": post_breach_input.git,
	"experiment": {
		"condition": "C1",
		"scenario_id": "freshness_breach",
		"run_key": "c1-freshness-breach-no-promotion",
	},
	"release": {
		"promotion_requested": false,
	},
	"metadata": common_metadata,
	"schema_contract": common_schema,
	"privacy": common_privacy,
	"quality": common_quality,
	"freshness": post_breach_input.freshness,
}

pre_breach_input := {
	"evaluation_stage": "pre",
	"git": post_breach_input.git,
	"experiment": {
		"condition": "C1",
		"scenario_id": "freshness_breach",
		"run_key": "c1-freshness-pre-stage-breach",
	},
	"release": {
		"promotion_requested": true,
	},
	"metadata": common_metadata,
	"schema_contract": common_schema,
	"privacy": common_privacy,
	"quality": common_quality,
	"freshness": post_breach_input.freshness,
}

status_fail_within_threshold_input := {
	"evaluation_stage": "post",
	"git": post_breach_input.git,
	"experiment": {
		"condition": "C1",
		"scenario_id": "freshness_breach",
		"run_key": "c1-freshness-source-status-fail",
	},
	"release": {
		"promotion_requested": true,
	},
	"metadata": common_metadata,
	"schema_contract": common_schema,
	"privacy": common_privacy,
	"quality": common_quality,
	"freshness": {
		"status": "FAIL",
		"sources": [
			{
				"source": "gold_daily_sales",
				"observed_age_seconds": 300,
				"maximum_age_seconds": 900,
				"status": "FAIL",
			},
		],
	},
}

threshold_overrun_status_pass_input := {
	"evaluation_stage": "post",
	"git": post_breach_input.git,
	"experiment": {
		"condition": "C1",
		"scenario_id": "freshness_breach",
		"run_key": "c1-freshness-threshold-overrun",
	},
	"release": {
		"promotion_requested": true,
	},
	"metadata": common_metadata,
	"schema_contract": common_schema,
	"privacy": common_privacy,
	"quality": common_quality,
	"freshness": {
		"status": "PASS",
		"sources": [
			{
				"source": "gold_daily_sales",
				"observed_age_seconds": 901,
				"maximum_age_seconds": 900,
				"status": "PASS",
			},
		],
	},
}

aggregate_fail_input := {
	"evaluation_stage": "post",
	"git": post_breach_input.git,
	"experiment": {
		"condition": "C1",
		"scenario_id": "freshness_breach",
		"run_key": "c1-freshness-aggregate-fail",
	},
	"release": {
		"promotion_requested": true,
	},
	"metadata": common_metadata,
	"schema_contract": common_schema,
	"privacy": common_privacy,
	"quality": common_quality,
	"freshness": {
		"status": "FAIL",
		"sources": [],
	},
}

test_pre_not_evaluated_does_not_block if {
	result := pac.allow with input as pre_not_evaluated_input
	result == true

	found := pac.freshness_violations with input as pre_not_evaluated_input
	count(found) == 0
}

test_post_within_threshold_allows if {
	result := pac.allow with input as post_pass_input
	result == true

	found := pac.freshness_violations with input as post_pass_input
	count(found) == 0
}

test_post_threshold_breach_blocks if {
	result := pac.allow with input as post_breach_input
	result == false

	found := pac.freshness_violations with input as post_breach_input
	count(found) == 1

	violation := found[_]

	violation.policy_id == "PAC-FRESH-001"
	violation.source == "bronze_orders"
	violation.observed_age_seconds == 1200
	violation.maximum_age_seconds == 900
}

test_post_threshold_breach_blocks_release if {
	found := pac.violations with input as post_breach_input

	ids := {
	item.policy_id |
		item := found[_]
	}

	ids == {
		"PAC-FRESH-001",
		"PAC-RELEASE-001",
	}
}

test_breach_remains_without_promotion if {
	result := pac.allow with input as post_breach_no_promotion_input
	result == false

	found := pac.violations with input as post_breach_no_promotion_input

	ids := {
	item.policy_id |
		item := found[_]
	}

	ids == {
		"PAC-FRESH-001",
	}
}

test_freshness_policy_is_post_stage_only if {
	found := pac.freshness_violations with input as pre_breach_input
	count(found) == 0

	result := pac.allow with input as pre_breach_input
	result == true
}

test_source_status_fail_blocks_even_within_threshold if {
	found := pac.freshness_violations with input as status_fail_within_threshold_input
	count(found) == 1

	violation := found[_]

	violation.policy_id == "PAC-FRESH-001"
	violation.source_status == "FAIL"
}

test_threshold_overrun_blocks_even_when_status_pass if {
	found := pac.freshness_violations with input as threshold_overrun_status_pass_input
	count(found) == 1

	violation := found[_]

	violation.policy_id == "PAC-FRESH-001"
	violation.observed_age_seconds == 901
	violation.maximum_age_seconds == 900
}

test_aggregate_fail_without_source_detail_blocks if {
	result := pac.allow with input as aggregate_fail_input
	result == false

	found := pac.freshness_violations with input as aggregate_fail_input
	count(found) == 1

	violation := found[_]

	violation.policy_id == "PAC-FRESH-001"
	violation.source == "__aggregate__"
}
