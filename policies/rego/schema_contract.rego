package thesis.pac

import rego.v1

schema_contract_violations contains violation if {
	model := input.schema_contract.governed_models[_]
	count(model.missing_columns) > 0

	violation := {
		"policy_id": "PAC-SCHEMA-001",
		"category": "schema_contract",
		"severity": "deny",
		"model": model.model,
		"reason": sprintf(
			"governed Gold model %s is missing required columns: %v",
			[
				model.model,
				model.missing_columns,
			],
		),
	}
}

schema_contract_violations contains violation if {
	model := input.schema_contract.governed_models[_]
	count(model.unexpected_columns) > 0

	violation := {
		"policy_id": "PAC-SCHEMA-001",
		"category": "schema_contract",
		"severity": "deny",
		"model": model.model,
		"reason": sprintf(
			"governed Gold model %s contains unexpected contract columns: %v",
			[
				model.model,
				model.unexpected_columns,
			],
		),
	}
}

schema_contract_violations contains violation if {
	model := input.schema_contract.governed_models[_]
	count(model.incompatible_type_changes) > 0

	violation := {
		"policy_id": "PAC-SCHEMA-001",
		"category": "schema_contract",
		"severity": "deny",
		"model": model.model,
		"reason": sprintf(
			"governed Gold model %s contains incompatible type changes: %v",
			[
				model.model,
				model.incompatible_type_changes,
			],
		),
	}
}

schema_contract_violations contains violation if {
	model := input.schema_contract.governed_models[_]
	model.expected_column_count != model.actual_column_count

	violation := {
		"policy_id": "PAC-SCHEMA-001",
		"category": "schema_contract",
		"severity": "deny",
		"model": model.model,
		"reason": sprintf(
			"governed Gold model %s column count mismatch: expected %v, actual %v",
			[
				model.model,
				model.expected_column_count,
				model.actual_column_count,
			],
		),
	}
}

blocking_violations contains violation if {
	violation := schema_contract_violations[_]
}
