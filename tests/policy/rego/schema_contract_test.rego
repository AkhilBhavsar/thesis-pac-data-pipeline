package thesis.pac_schema_test

import data.thesis.pac as pac
import rego.v1

safe_model := {
	"model": "gold_daily_sales",
	"exposure": "internal",
	"expected_column_count": 5,
	"actual_column_count": 5,
	"missing_columns": [],
	"unexpected_columns": [],
	"incompatible_type_changes": [],
}

safe_input := {
	"git": {
		"branch": "feature/policy-as-code-gates",
		"commit": "0fb68fb9bdce85f248503f0074eb26031a95d6b9",
	},
	"experiment": {
		"run_key": "c1-schema-safe",
	},
	"release": {
		"promotion_requested": true,
	},
	"metadata": {
		"required_fields_present": true,
		"resource_count": 15,
	},
	"schema_contract": {
		"governed_models": [safe_model],
	},
}

missing_input := {
	"git": safe_input.git,
	"experiment": {
		"run_key": "c1-schema-missing",
	},
	"release": {
		"promotion_requested": true,
	},
	"metadata": safe_input.metadata,
	"schema_contract": {
		"governed_models": [{
			"model": "gold_daily_sales",
			"exposure": "internal",
			"expected_column_count": 5,
			"actual_column_count": 5,
			"missing_columns": ["order_date"],
			"unexpected_columns": [],
			"incompatible_type_changes": [],
		}],
	},
}

unexpected_input := {
	"git": safe_input.git,
	"experiment": {
		"run_key": "c1-schema-unexpected",
	},
	"release": {
		"promotion_requested": true,
	},
	"metadata": safe_input.metadata,
	"schema_contract": {
		"governed_models": [{
			"model": "gold_daily_sales",
			"exposure": "internal",
			"expected_column_count": 5,
			"actual_column_count": 5,
			"missing_columns": [],
			"unexpected_columns": ["unexpected_metric"],
			"incompatible_type_changes": [],
		}],
	},
}

type_change_input := {
	"git": safe_input.git,
	"experiment": {
		"run_key": "c1-schema-type",
	},
	"release": {
		"promotion_requested": true,
	},
	"metadata": safe_input.metadata,
	"schema_contract": {
		"governed_models": [{
			"model": "gold_daily_sales",
			"exposure": "internal",
			"expected_column_count": 5,
			"actual_column_count": 5,
			"missing_columns": [],
			"unexpected_columns": [],
			"incompatible_type_changes": [
				"order_date:date->bigint",
			],
		}],
	},
}

count_mismatch_input := {
	"git": safe_input.git,
	"experiment": {
		"run_key": "c1-schema-count",
	},
	"release": {
		"promotion_requested": true,
	},
	"metadata": safe_input.metadata,
	"schema_contract": {
		"governed_models": [{
			"model": "gold_daily_sales",
			"exposure": "internal",
			"expected_column_count": 5,
			"actual_column_count": 4,
			"missing_columns": [],
			"unexpected_columns": [],
			"incompatible_type_changes": [],
		}],
	},
}

no_promotion_input := {
	"git": missing_input.git,
	"experiment": missing_input.experiment,
	"release": {
		"promotion_requested": false,
	},
	"metadata": missing_input.metadata,
	"schema_contract": missing_input.schema_contract,
}

test_safe_schema_contract_allows if {
	result := pac.allow with input as safe_input
	result == true

	found := pac.schema_contract_violations with input as safe_input
	count(found) == 0
}

test_missing_column_blocks_and_blocks_release if {
	result := pac.allow with input as missing_input
	result == false

	found := pac.violations with input as missing_input

	ids := {
	item.policy_id |
		item := found[_]
	}

	ids == {
		"PAC-SCHEMA-001",
		"PAC-RELEASE-001",
	}
}

test_unexpected_column_denied if {
	found := pac.schema_contract_violations with input as unexpected_input

	ids := {
	item.policy_id |
		item := found[_]
	}

	ids == {
		"PAC-SCHEMA-001",
	}
}

test_incompatible_type_change_denied if {
	found := pac.schema_contract_violations with input as type_change_input

	ids := {
	item.policy_id |
		item := found[_]
	}

	ids == {
		"PAC-SCHEMA-001",
	}
}

test_column_count_mismatch_denied if {
	found := pac.schema_contract_violations with input as count_mismatch_input

	ids := {
	item.policy_id |
		item := found[_]
	}

	ids == {
		"PAC-SCHEMA-001",
	}
}

test_schema_block_remains_without_promotion if {
	result := pac.allow with input as no_promotion_input
	result == false

	found := pac.violations with input as no_promotion_input

	ids := {
	item.policy_id |
		item := found[_]
	}

	ids == {
		"PAC-SCHEMA-001",
	}
}
