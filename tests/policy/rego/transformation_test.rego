package thesis.pac_transformation_test

import data.thesis.pac as pac
import rego.v1

manifest_sha := "306474a24e4f544c869bfb7f7625f46a80d06e878332869108a5a574b89a52a2"

common_git := {
	"branch": "feature/policy-as-code-gates",
	"commit": "e8bec9700ebd0a5163646ab60a6a7546960713d3",
}

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

pre_quality := {
	"status": "NOT_EVALUATED",
	"total_tests": 0,
	"failed_tests": 0,
	"critical_failures": [],
}

pre_freshness := {
	"status": "NOT_EVALUATED",
	"sources": [],
}

post_quality := {
	"status": "PASS",
	"total_tests": 1,
	"failed_tests": 0,
	"critical_failures": [],
}

post_freshness := {
	"status": "PASS",
	"sources": [],
}

safe_input := {
	"evaluation_stage": "pre",
	"git": common_git,
	"experiment": {
		"condition": "C1",
		"scenario_id": "baseline",
		"run_key": "c1-transform-safe",
	},
	"release": {
		"promotion_requested": true,
	},
	"metadata": common_metadata,
	"schema_contract": common_schema,
	"privacy": common_privacy,
	"quality": pre_quality,
	"freshness": pre_freshness,
	"transformation": {
		"changed_models": [],
		"unapproved_definitions": [],
		"manifest_sha256": manifest_sha,
	},
}

approved_change_input := {
	"evaluation_stage": "pre",
	"git": common_git,
	"experiment": {
		"condition": "C1",
		"scenario_id": "policy_false_positive",
		"run_key": "c1-transform-approved-change",
	},
	"release": {
		"promotion_requested": true,
	},
	"metadata": common_metadata,
	"schema_contract": common_schema,
	"privacy": common_privacy,
	"quality": pre_quality,
	"freshness": pre_freshness,
	"transformation": {
		"changed_models": [
			"gold_daily_sales",
		],
		"unapproved_definitions": [],
		"manifest_sha256": manifest_sha,
	},
}

unapproved_change_input := {
	"evaluation_stage": "pre",
	"git": common_git,
	"experiment": {
		"condition": "C1",
		"scenario_id": "quality_regression",
		"run_key": "c1-transform-unapproved",
	},
	"release": {
		"promotion_requested": true,
	},
	"metadata": common_metadata,
	"schema_contract": common_schema,
	"privacy": common_privacy,
	"quality": pre_quality,
	"freshness": pre_freshness,
	"transformation": {
		"changed_models": [
			"gold_daily_sales",
		],
		"unapproved_definitions": [
			"gold_daily_sales",
		],
		"manifest_sha256": manifest_sha,
	},
}

no_promotion_input := {
	"evaluation_stage": "pre",
	"git": common_git,
	"experiment": {
		"condition": "C1",
		"scenario_id": "quality_regression",
		"run_key": "c1-transform-no-promotion",
	},
	"release": {
		"promotion_requested": false,
	},
	"metadata": common_metadata,
	"schema_contract": common_schema,
	"privacy": common_privacy,
	"quality": pre_quality,
	"freshness": pre_freshness,
	"transformation": unapproved_change_input.transformation,
}

post_unapproved_input := {
	"evaluation_stage": "post",
	"git": common_git,
	"experiment": {
		"condition": "C1",
		"scenario_id": "quality_regression",
		"run_key": "c1-transform-post-scope",
	},
	"release": {
		"promotion_requested": true,
	},
	"metadata": common_metadata,
	"schema_contract": common_schema,
	"privacy": common_privacy,
	"quality": post_quality,
	"freshness": post_freshness,
	"transformation": unapproved_change_input.transformation,
}

multiple_unapproved_input := {
	"evaluation_stage": "pre",
	"git": common_git,
	"experiment": {
		"condition": "C1",
		"scenario_id": "schema_break",
		"run_key": "c1-transform-multiple-unapproved",
	},
	"release": {
		"promotion_requested": true,
	},
	"metadata": common_metadata,
	"schema_contract": common_schema,
	"privacy": common_privacy,
	"quality": pre_quality,
	"freshness": pre_freshness,
	"transformation": {
		"changed_models": [
			"gold_daily_sales",
			"gold_sales_by_state",
		],
		"unapproved_definitions": [
			"gold_daily_sales",
			"gold_sales_by_state",
		],
		"manifest_sha256": manifest_sha,
	},
}

test_safe_pre_baseline_allows if {
	result := pac.allow with input as safe_input
	result == true

	found := pac.transformation_violations with input as safe_input
	count(found) == 0
}

test_approved_changed_model_allows if {
	result := pac.allow with input as approved_change_input
	result == true

	found := pac.transformation_violations with input as approved_change_input
	count(found) == 0
}

test_unapproved_definition_denied if {
	result := pac.allow with input as unapproved_change_input
	result == false

	found := pac.transformation_violations with input as unapproved_change_input
	count(found) == 1

	violation := found[_]

	violation.policy_id == "PAC-TRANSFORM-001"
	violation.unapproved_definitions == [
		"gold_daily_sales",
	]
}

test_unapproved_definition_blocks_release if {
	found := pac.violations with input as unapproved_change_input

	ids := {
	item.policy_id |
		item := found[_]
	}

	ids == {
		"PAC-TRANSFORM-001",
		"PAC-RELEASE-001",
	}
}

test_unapproved_definition_remains_without_promotion if {
	result := pac.allow with input as no_promotion_input
	result == false

	found := pac.violations with input as no_promotion_input

	ids := {
	item.policy_id |
		item := found[_]
	}

	ids == {
		"PAC-TRANSFORM-001",
	}
}

test_transformation_policy_is_pre_stage_only if {
	found := pac.transformation_violations with input as post_unapproved_input
	count(found) == 0

	result := pac.allow with input as post_unapproved_input
	result == true
}

test_multiple_unapproved_definitions_are_reported if {
	found := pac.transformation_violations with input as multiple_unapproved_input
	count(found) == 1

	violation := found[_]

	violation.unapproved_definitions == [
		"gold_daily_sales",
		"gold_sales_by_state",
	]
}
