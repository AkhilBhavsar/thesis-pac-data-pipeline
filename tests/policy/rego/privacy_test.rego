package thesis.pac_privacy_test

import data.thesis.pac as pac
import rego.v1

base_input := {
	"git": {
		"branch": "feature/policy-as-code-gates",
		"commit": "d172ab2036936fc8d87df0acced3838404e86a91",
	},
	"experiment": {
		"run_key": "c1-privacy-safe",
	},
	"release": {
		"promotion_requested": true,
	},
	"metadata": {
		"required_fields_present": true,
		"resource_count": 15,
	},
	"schema_contract": {
		"governed_models": [],
	},
	"privacy": {
		"public_models": [
			"gold_public_sales_dashboard",
		],
		"forbidden_columns": [
			"customer_id",
			"synthetic_email",
			"synthetic_phone",
		],
		"detected_forbidden_columns": [],
	},
}

pii_input := {
	"git": base_input.git,
	"experiment": {
		"run_key": "c1-pii-exposure",
	},
	"release": {
		"promotion_requested": true,
	},
	"metadata": base_input.metadata,
	"schema_contract": base_input.schema_contract,
	"privacy": {
		"public_models": [
			"gold_public_sales_dashboard",
		],
		"forbidden_columns": [
			"customer_id",
			"synthetic_email",
			"synthetic_phone",
		],
		"detected_forbidden_columns": [
			"synthetic_email",
		],
	},
}

no_promotion_pii_input := {
	"git": pii_input.git,
	"experiment": {
		"run_key": "c1-pii-no-promotion",
	},
	"release": {
		"promotion_requested": false,
	},
	"metadata": pii_input.metadata,
	"schema_contract": pii_input.schema_contract,
	"privacy": pii_input.privacy,
}

multi_pii_input := {
	"git": pii_input.git,
	"experiment": {
		"run_key": "c1-pii-multiple",
	},
	"release": {
		"promotion_requested": true,
	},
	"metadata": pii_input.metadata,
	"schema_contract": pii_input.schema_contract,
	"privacy": {
		"public_models": [
			"gold_public_sales_dashboard",
		],
		"forbidden_columns": [
			"customer_id",
			"synthetic_email",
			"synthetic_phone",
		],
		"detected_forbidden_columns": [
			"customer_id",
			"synthetic_email",
		],
	},
}

test_safe_public_gold_allows if {
	result := pac.allow with input as base_input
	result == true

	found := pac.privacy_violations with input as base_input
	count(found) == 0
}

test_pii_exposure_blocks_and_blocks_release if {
	result := pac.allow with input as pii_input
	result == false

	found := pac.violations with input as pii_input

	ids := {
	item.policy_id |
		item := found[_]
	}

	ids == {
		"PAC-PRIVACY-001",
		"PAC-RELEASE-001",
	}
}

test_pii_remains_blocked_without_promotion if {
	result := pac.allow with input as no_promotion_pii_input
	result == false

	found := pac.violations with input as no_promotion_pii_input

	ids := {
	item.policy_id |
		item := found[_]
	}

	ids == {
		"PAC-PRIVACY-001",
	}
}

test_multiple_forbidden_columns_denied if {
	found := pac.privacy_violations with input as multi_pii_input

	count(found) == 1

	violation := found[_]

	violation.policy_id == "PAC-PRIVACY-001"

	violation.detected_forbidden_columns == [
		"customer_id",
		"synthetic_email",
	]
}
