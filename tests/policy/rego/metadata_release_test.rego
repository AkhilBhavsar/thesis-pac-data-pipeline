package thesis.pac_test

import data.thesis.pac as pac
import rego.v1

safe_input := {
	"git": {
		"branch": "feature/policy-as-code-gates",
		"commit": "7716bbda8ce9e9cd304aae6527739f57fd6407b7",
	},
	"experiment": {
		"run_key": "c1-metadata-release-test",
	},
	"release": {
		"promotion_requested": true,
	},
	"metadata": {
		"required_fields_present": true,
		"resource_count": 15,
	},
}

metadata_failure_input := {
	"git": {
		"branch": "feature/policy-as-code-gates",
		"commit": "7716bbda8ce9e9cd304aae6527739f57fd6407b7",
	},
	"experiment": {
		"run_key": "c1-metadata-release-test",
	},
	"release": {
		"promotion_requested": true,
	},
	"metadata": {
		"required_fields_present": false,
		"resource_count": 15,
	},
}

metadata_failure_no_promotion_input := {
	"git": {
		"branch": "feature/policy-as-code-gates",
		"commit": "7716bbda8ce9e9cd304aae6527739f57fd6407b7",
	},
	"experiment": {
		"run_key": "c1-metadata-release-test",
	},
	"release": {
		"promotion_requested": false,
	},
	"metadata": {
		"required_fields_present": false,
		"resource_count": 15,
	},
}

empty_resource_input := {
	"git": {
		"branch": "feature/policy-as-code-gates",
		"commit": "7716bbda8ce9e9cd304aae6527739f57fd6407b7",
	},
	"experiment": {
		"run_key": "c1-metadata-release-test",
	},
	"release": {
		"promotion_requested": true,
	},
	"metadata": {
		"required_fields_present": true,
		"resource_count": 0,
	},
}

test_safe_baseline_allows if {
	result := pac.allow with input as safe_input
	result == true

	found := pac.violations with input as safe_input
	count(found) == 0
}

test_metadata_failure_blocks_promotion if {
	result := pac.allow with input as metadata_failure_input
	result == false

	found := pac.violations with input as metadata_failure_input

	ids := {
	item.policy_id |
		item := found[_]
	}

	ids == {
		"PAC-META-001",
		"PAC-RELEASE-001",
	}
}

test_release_not_triggered_without_promotion if {
	result := pac.allow with input as metadata_failure_no_promotion_input
	result == false

	found := pac.violations with input as metadata_failure_no_promotion_input

	ids := {
	item.policy_id |
		item := found[_]
	}

	ids == {
		"PAC-META-001",
	}
}

test_empty_resource_inventory_denied if {
	result := pac.allow with input as empty_resource_input
	result == false

	found := pac.metadata_violations with input as empty_resource_input

	reasons := {
	item.reason |
		item := found[_]
	}

	"governed resource inventory is empty" in reasons
}
