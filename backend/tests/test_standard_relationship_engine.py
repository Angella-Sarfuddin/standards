from io import StringIO
import json
import unittest
from unittest.mock import patch

from app.services.offline.standard_relationship_engine import (
    CatalogueEdition,
    ResolutionOutcome,
    SCHEMA_VERSION,
    resolve_relationship,
    validate_relationship_document,
    validate_relationship_file,
)


def _record(**overrides):
    record = {
        "source_sdo": "Example Standards Group",
        "source_designation": "ESG 12.4",
        "source_year": 2015,
        "target_sdo": "Example Standards Group",
        "target_designation": "ESG 12.4",
        "target_year": 2024,
        "relationship_type": "SUPERSEDES",
        "evidence_url": "https://publisher.example/record/12-4",
        "verification_state": "VERIFIED",
        "verification_date": "2026-10-26",
    }
    record.update(overrides)
    return record


def _validated(*records):
    report = validate_relationship_document(
        {"schema_version": SCHEMA_VERSION, "relationships": list(records)}
    )
    if report.errors:
        raise AssertionError([issue.as_dict() for issue in report.errors])
    return report


class StandardRelationshipEngineTests(unittest.TestCase):
    def test_versioned_json_accepts_all_supported_relationship_types(self):
        relationship_types = (
            "SUPERSEDES",
            "INCORPORATED_INTO",
            "AMENDS",
            "CORRIGENDUM_TO",
            "ALIAS_OF",
            "EQUIVALENT_TO",
        )
        report = _validated(
            *(_record(source_designation=f"ESG 12.{index}", relationship_type=kind)
              for index, kind in enumerate(relationship_types, 1))
        )

        self.assertTrue(report.is_valid)
        self.assertEqual(
            [relationship.relationship_type for relationship in report.relationships],
            list(relationship_types),
        )

    def test_target_is_representable_without_local_catalogue_ids(self):
        report = _validated(
            _record(
                target_sdo="Other Standards Body",
                target_designation="OSB 88",
                target_year=2030,
                source_catalog_id=None,
                target_catalog_id=None,
            )
        )

        relationship = report.relationships[0]
        self.assertEqual(relationship.target_sdo, "Other Standards Body")
        self.assertEqual(relationship.target_designation, "OSB 88")
        self.assertEqual(relationship.target_year, 2030)
        self.assertIsNone(relationship.target_catalog_id)

    def test_validation_reports_malformed_fields_types_years_and_evidence(self):
        malformed = _record(
            source_sdo=" ",
            target_designation="",
            source_year=True,
            target_year="2024",
            relationship_type="REPLACES",
            evidence_url="publisher record",
            verification_date="26-10-2026",
        )
        report = validate_relationship_document(
            {"schema_version": SCHEMA_VERSION, "relationships": [malformed]}
        )

        self.assertFalse(report.is_valid)
        codes = {issue.code for issue in report.errors}
        self.assertTrue(
            {
                "MISSING_REQUIRED_FIELD",
                "INVALID_YEAR",
                "INVALID_RELATIONSHIP_TYPE",
                "INVALID_EVIDENCE_URL",
                "INVALID_VERIFICATION_DATE",
            }.issubset(codes)
        )
        self.assertEqual(report.relationships, ())

    def test_verified_records_require_a_verification_date_and_supported_state(self):
        missing_date = validate_relationship_document(
            {
                "schema_version": SCHEMA_VERSION,
                "relationships": [_record(verification_date=None)],
            }
        )
        unsupported_state = validate_relationship_document(
            {
                "schema_version": SCHEMA_VERSION,
                "relationships": [_record(verification_state="PENDING")],
            }
        )

        self.assertIn(
            "MISSING_VERIFICATION_DATE",
            {issue.code for issue in missing_date.errors},
        )
        self.assertIn(
            "INVALID_VERIFICATION_STATE",
            {issue.code for issue in unsupported_state.errors},
        )

    def test_unsupported_schema_version_is_rejected(self):
        for schema_version in (2, 1.0, True):
            with self.subTest(schema_version=schema_version):
                report = validate_relationship_document(
                    {"schema_version": schema_version, "relationships": []}
                )

                self.assertFalse(report.is_valid)
                self.assertEqual(
                    report.errors[0].code,
                    "UNSUPPORTED_SCHEMA_VERSION",
                )

    def test_validator_reports_exact_duplicates_and_conflicting_claims(self):
        original = _record()
        conflicting = _record(
            target_designation="ESG 12.5",
            target_year=2025,
            relationship_type="INCORPORATED_INTO",
        )
        report = validate_relationship_document(
            {
                "schema_version": SCHEMA_VERSION,
                "relationships": [original, original, conflicting],
            }
        )

        self.assertEqual(len(report.duplicates), 1)
        self.assertEqual(report.duplicates[0].indexes, (0, 1))
        self.assertEqual(len(report.conflicts), 1)
        self.assertEqual(report.conflicts[0].indexes, (0, 1, 2))
        self.assertFalse(report.is_valid)

    def test_rejected_alternative_does_not_create_an_active_conflict(self):
        report = validate_relationship_document(
            {
                "schema_version": SCHEMA_VERSION,
                "relationships": [
                    _record(),
                    _record(
                        target_designation="ESG 12.5",
                        verification_state="REJECTED",
                        verification_date=None,
                    ),
                ],
            }
        )

        self.assertTrue(report.is_valid)
        self.assertEqual(report.conflicts, ())

    def test_file_validation_reports_missing_input_without_side_effects(self):
        report = validate_relationship_file("missing-relationship-input.json")

        self.assertFalse(report.is_valid)
        self.assertEqual(report.errors[0].code, "INPUT_READ_ERROR")

    def test_file_validation_parses_json_without_writing_or_network_access(self):
        payload = json.dumps(
            {"schema_version": SCHEMA_VERSION, "relationships": [_record()]}
        )
        with patch(
            "pathlib.Path.open",
            side_effect=lambda *_args, **_kwargs: StringIO(payload),
        ):
            report = validate_relationship_file("synthetic-input.json")

        self.assertTrue(report.is_valid)
        self.assertEqual(report.relationships[0].source_designation, "ESG 12.4")

    def test_explicit_year_matches_only_the_exact_source_edition(self):
        relationships = _validated(_record())

        exact = resolve_relationship(
            relationships,
            "Example Standards Group",
            "ESG 12.4",
            2015,
        )
        different_year = resolve_relationship(
            relationships,
            "Example Standards Group",
            "ESG 12.4",
            2010,
        )

        self.assertEqual(exact.outcome, ResolutionOutcome.MATCH)
        self.assertEqual(exact.relationship.source_year, 2015)
        self.assertEqual(different_year.outcome, ResolutionOutcome.NO_MATCH)

    def test_invalid_validation_reports_never_resolve_partial_valid_records(self):
        valid = _record()
        unsupported_schema = validate_relationship_document(
            {"schema_version": 99, "relationships": [valid]}
        )
        malformed_record = validate_relationship_document(
            {
                "schema_version": SCHEMA_VERSION,
                "relationships": [valid, _record(target_year="not-a-year")],
            }
        )

        self.assertFalse(unsupported_schema.is_valid)
        self.assertEqual(len(unsupported_schema.relationships), 1)
        self.assertFalse(malformed_record.is_valid)
        self.assertEqual(len(malformed_record.relationships), 1)
        for report in (unsupported_schema, malformed_record):
            with self.subTest(report=report):
                result = resolve_relationship(
                    report, "Example Standards Group", "ESG 12.4", 2015
                )
                self.assertEqual(result.outcome, ResolutionOutcome.INVALID_INPUT)
                self.assertIsNone(result.relationship)

    def test_validated_report_resolves_and_raw_records_are_rejected(self):
        report = _validated(_record())

        result = resolve_relationship(
            report, "Example Standards Group", "ESG 12.4", 2015
        )
        raw_records = resolve_relationship(
            report.relationships, "Example Standards Group", "ESG 12.4", 2015
        )

        self.assertEqual(result.outcome, ResolutionOutcome.MATCH)
        self.assertEqual(raw_records.outcome, ResolutionOutcome.INVALID_INPUT)

    def test_explicit_and_resolved_years_must_agree_when_both_are_supplied(self):
        report = _validated(_record())
        matching = resolve_relationship(
            report,
            "Example Standards Group",
            "ESG 12.4",
            2015,
            resolved_source_year=2015,
        )
        contradictory = resolve_relationship(
            report,
            "Example Standards Group",
            "ESG 12.4",
            2015,
            resolved_source_year=2010,
        )
        explicit_without_resolution = resolve_relationship(
            report, "Example Standards Group", "ESG 12.4", 2015
        )

        self.assertEqual(matching.outcome, ResolutionOutcome.MATCH)
        self.assertEqual(contradictory.outcome, ResolutionOutcome.NO_MATCH)
        self.assertEqual(explicit_without_resolution.outcome, ResolutionOutcome.MATCH)

    def test_local_source_identifier_is_required_when_relationship_is_row_scoped(self):
        relationships = _validated(
            _record(source_catalog_id="source-row-1")
        )

        unscoped = resolve_relationship(
            relationships,
            "Example Standards Group",
            "ESG 12.4",
            2015,
        )
        exact_row = resolve_relationship(
            relationships,
            "Example Standards Group",
            "ESG 12.4",
            2015,
            source_catalog_id="source-row-1",
        )
        other_row = resolve_relationship(
            relationships,
            "Example Standards Group",
            "ESG 12.4",
            2015,
            source_catalog_id="source-row-2",
        )

        self.assertEqual(unscoped.outcome, ResolutionOutcome.NO_MATCH)
        self.assertEqual(exact_row.outcome, ResolutionOutcome.MATCH)
        self.assertEqual(other_row.outcome, ResolutionOutcome.NO_MATCH)

    def test_yearless_request_needs_an_independently_resolved_unique_edition(self):
        relationships = _validated(_record())

        unresolved = resolve_relationship(
            relationships,
            "Example Standards Group",
            "ESG 12.4",
        )
        uniquely_resolved = resolve_relationship(
            relationships,
            "Example Standards Group",
            "ESG 12.4",
            resolved_source_year=2015,
            source_edition_is_unique=True,
        )

        self.assertEqual(unresolved.outcome, ResolutionOutcome.NO_MATCH)
        self.assertEqual(uniquely_resolved.outcome, ResolutionOutcome.MATCH)

    def test_yearless_request_does_not_apply_when_resolution_is_not_unique(self):
        relationships = _validated(_record())

        result = resolve_relationship(
            relationships,
            "Example Standards Group",
            "ESG 12.4",
            resolved_source_year=2015,
            source_edition_is_unique=False,
        )

        self.assertEqual(result.outcome, ResolutionOutcome.NO_MATCH)

    def test_unqualified_relationship_year_is_only_usable_after_unique_resolution(self):
        relationships = _validated(_record(source_year=None))

        unresolved = resolve_relationship(
            relationships,
            "Example Standards Group",
            "ESG 12.4",
        )
        resolved = resolve_relationship(
            relationships,
            "Example Standards Group",
            "ESG 12.4",
            resolved_source_year=2015,
            source_edition_is_unique=True,
        )

        self.assertEqual(unresolved.outcome, ResolutionOutcome.NO_MATCH)
        self.assertEqual(resolved.outcome, ResolutionOutcome.MATCH)

    def test_unverified_and_conflicted_records_are_not_resolved(self):
        records = [
            _record(verification_state="REVIEW_REQUIRED", verification_date=None),
            _record(
                source_designation="ESG 12.5",
                verification_state="CONFLICTED",
                verification_date=None,
            ),
        ]
        relationships = _validated(*records)

        review_required = resolve_relationship(
            relationships,
            "Example Standards Group",
            "ESG 12.4",
            2015,
        )
        conflicted = resolve_relationship(
            relationships,
            "Example Standards Group",
            "ESG 12.5",
            2015,
        )

        self.assertEqual(review_required.outcome, ResolutionOutcome.NO_MATCH)
        self.assertEqual(conflicted.outcome, ResolutionOutcome.NO_MATCH)

    def test_conflicting_report_is_rejected_before_relationship_resolution(self):
        relationships = _validated(
            _record(),
            _record(
                target_designation="ESG 12.5",
                target_year=2025,
                relationship_type="SUPERSEDES",
                evidence_url="https://publisher.example/record/alternate",
            ),
        )

        result = resolve_relationship(
            relationships,
            "Example Standards Group",
            "ESG 12.4",
            2015,
        )

        self.assertEqual(result.outcome, ResolutionOutcome.INVALID_INPUT)
        self.assertIsNone(result.relationship)

    def test_conflicting_verified_and_unverified_report_is_rejected(self):
        relationships = _validated(
            _record(),
            _record(
                target_designation="ESG 12.5",
                target_year=2025,
                relationship_type="SUPERSEDES",
                verification_state="REVIEW_REQUIRED",
                verification_date=None,
                evidence_url="https://publisher.example/record/review",
            ),
        )

        result = resolve_relationship(
            relationships,
            "Example Standards Group",
            "ESG 12.4",
            2015,
        )

        self.assertEqual(result.outcome, ResolutionOutcome.INVALID_INPUT)
        self.assertIsNone(result.relationship)

    def test_absent_catalogue_target_is_reported_without_fabrication(self):
        relationships = _validated(_record())

        result = resolve_relationship(
            relationships,
            "Example Standards Group",
            "ESG 12.4",
            2015,
            catalogue_editions=[],
        )

        self.assertEqual(result.outcome, ResolutionOutcome.UNAVAILABLE_TARGET)
        self.assertEqual(result.relationship.target_designation, "ESG 12.4")
        self.assertIsNone(result.target)

    def test_distinct_duplicate_catalogue_rows_make_target_ambiguous(self):
        relationships = _validated(_record())
        catalogue_rows = [
            CatalogueEdition(
                "Example Standards Group", "ESG 12.4", 2024, "catalog-1"
            ),
            CatalogueEdition(
                "Example Standards Group", "ESG 12.4", 2024, "catalog-2"
            ),
        ]

        result = resolve_relationship(
            relationships,
            "Example Standards Group",
            "ESG 12.4",
            2015,
            catalogue_editions=catalogue_rows,
        )

        self.assertEqual(result.outcome, ResolutionOutcome.AMBIGUOUS_TARGET)
        self.assertIsNone(result.target)

    def test_conflicting_catalogue_identity_for_one_id_is_rejected(self):
        relationships = _validated(_record(target_catalog_id="catalog-1"))
        catalogue_rows = [
            CatalogueEdition(
                "Example Standards Group", "ESG 12.4", 2024, "catalog-1"
            ),
            CatalogueEdition(
                "Example Standards Group", "ESG 12.5", 2025, "catalog-1"
            ),
        ]

        result = resolve_relationship(
            relationships,
            "Example Standards Group",
            "ESG 12.4",
            2015,
            catalogue_editions=catalogue_rows,
        )

        self.assertEqual(result.outcome, ResolutionOutcome.TARGET_IDENTITY_CONFLICT)
        self.assertEqual(result.target_availability, "CONFLICTED")

    def test_target_catalogue_id_must_match_target_identity(self):
        report = _validated(_record(target_catalog_id="catalog-1"))
        matching = CatalogueEdition(
            "Example Standards Group", "ESG 12.4", 2024, "catalog-1"
        )
        self.assertEqual(
            resolve_relationship(
                report,
                "Example Standards Group",
                "ESG 12.4",
                2015,
                catalogue_editions=[matching],
            ).outcome,
            ResolutionOutcome.MATCH,
        )

        contradictory_identities = (
            CatalogueEdition("Different Standards Body", "ESG 12.4", 2024, "catalog-1"),
            CatalogueEdition("Example Standards Group", "ESG 99", 2024, "catalog-1"),
            CatalogueEdition("Example Standards Group", "ESG 12.4", 2025, "catalog-1"),
        )
        for row in contradictory_identities:
            with self.subTest(row=row):
                result = resolve_relationship(
                    report,
                    "Example Standards Group",
                    "ESG 12.4",
                    2015,
                    catalogue_editions=[row],
                )
                self.assertEqual(
                    result.outcome, ResolutionOutcome.TARGET_IDENTITY_CONFLICT
                )
                self.assertEqual(result.target_availability, "CONFLICTED")
                self.assertIsNone(result.target)

    def test_absent_target_catalogue_id_remains_unavailable_not_conflicted(self):
        report = _validated(_record(target_catalog_id="missing-row"))

        result = resolve_relationship(
            report,
            "Example Standards Group",
            "ESG 12.4",
            2015,
            catalogue_editions=[
                CatalogueEdition(
                    "Example Standards Group", "ESG 12.4", 2024, "other-row"
                )
            ],
        )

        self.assertEqual(result.outcome, ResolutionOutcome.UNAVAILABLE_TARGET)
        self.assertEqual(result.target_availability, "UNAVAILABLE")

    def test_duplicate_references_to_one_catalogue_id_are_one_target(self):
        relationships = _validated(_record())
        row = CatalogueEdition(
            "Example Standards Group", "ESG 12.4", 2024, "catalog-1"
        )

        result = resolve_relationship(
            relationships,
            "Example Standards Group",
            "ESG 12.4",
            2015,
            catalogue_editions=[row, row],
        )

        self.assertEqual(result.outcome, ResolutionOutcome.MATCH)
        self.assertEqual(result.target.catalog_id, "catalog-1")
        self.assertEqual(result.target_availability, "AVAILABLE")

    def test_each_relationship_type_is_preserved_by_resolution(self):
        relationship_types = (
            "SUPERSEDES",
            "INCORPORATED_INTO",
            "AMENDS",
            "CORRIGENDUM_TO",
            "ALIAS_OF",
            "EQUIVALENT_TO",
        )
        for index, relationship_type in enumerate(relationship_types, 1):
            with self.subTest(relationship_type=relationship_type):
                relationships = _validated(
                    _record(
                        source_designation=f"ESG 12.{index}",
                        relationship_type=relationship_type,
                    )
                )
                result = resolve_relationship(
                    relationships,
                    "Example Standards Group",
                    f"ESG 12.{index}",
                    2015,
                )
                self.assertEqual(result.outcome, ResolutionOutcome.MATCH)
                self.assertEqual(
                    result.relationship.relationship_type,
                    relationship_type,
                )


if __name__ == "__main__":
    unittest.main()
