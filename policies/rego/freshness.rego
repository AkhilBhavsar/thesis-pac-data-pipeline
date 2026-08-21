package thesis.pac

import rego.v1

freshness_source_failed(source) if {
	source.status == "FAIL"
}

freshness_source_failed(source) if {
	source.observed_age_seconds > source.maximum_age_seconds
}

freshness_violations contains violation if {
	input.evaluation_stage == "post"

	source := input.freshness.sources[_]

	freshness_source_failed(source)

	violation := {
		"policy_id": "PAC-FRESH-001",
		"category": "runtime_validation",
		"severity": "deny",
		"source": source.source,
		"observed_age_seconds": source.observed_age_seconds,
		"maximum_age_seconds": source.maximum_age_seconds,
		"source_status": source.status,
		"reason": sprintf(
			"freshness threshold breached for %s: observed_age_seconds=%v maximum_age_seconds=%v status=%s",
			[
				source.source,
				source.observed_age_seconds,
				source.maximum_age_seconds,
				source.status,
			],
		),
	}
}

freshness_violations contains violation if {
	input.evaluation_stage == "post"
	input.freshness.status == "FAIL"

	failed_sources := [
	source |
		source := input.freshness.sources[_]
		freshness_source_failed(source)
	]

	count(failed_sources) == 0

	violation := {
		"policy_id": "PAC-FRESH-001",
		"category": "runtime_validation",
		"severity": "deny",
		"source": "__aggregate__",
		"observed_age_seconds": 0,
		"maximum_age_seconds": 0,
		"source_status": "FAIL",
		"reason": "freshness evaluation failed without a source-level freshness failure record",
	}
}

blocking_violations contains violation if {
	violation := freshness_violations[_]
}
