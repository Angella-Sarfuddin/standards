"""Offline validation and resolution for reviewed standard-edition links.

This module is deliberately independent of SQLAlchemy, application search,
and publisher-specific metadata. It accepts versioned JSON records and
catalogue editions supplied by its caller; it never fetches or writes data.
"""

from dataclasses import dataclass
from datetime import date
from enum import Enum
import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import urlsplit


SCHEMA_VERSION = 1
RELATIONSHIP_TYPES = frozenset(
    {
        "SUPERSEDES",
        "INCORPORATED_INTO",
        "AMENDS",
        "CORRIGENDUM_TO",
        "ALIAS_OF",
        "EQUIVALENT_TO",
    }
)
VERIFICATION_STATES = frozenset(
    {"REVIEW_REQUIRED", "VERIFIED", "CONFLICTED", "REJECTED"}
)


class ResolutionOutcome(str, Enum):
    INVALID_INPUT = "INVALID_INPUT"
    NO_MATCH = "NO_MATCH"
    MATCH = "MATCH"
    AMBIGUOUS = "AMBIGUOUS"
    UNAVAILABLE_TARGET = "UNAVAILABLE_TARGET"
    AMBIGUOUS_TARGET = "AMBIGUOUS_TARGET"
    TARGET_IDENTITY_CONFLICT = "TARGET_IDENTITY_CONFLICT"


@dataclass(frozen=True)
class EditionRelationship:
    source_sdo: str
    source_designation: str
    source_year: Optional[int]
    target_sdo: str
    target_designation: str
    target_year: Optional[int]
    relationship_type: str
    evidence_url: str
    verification_state: str
    verification_date: Optional[str]
    source_catalog_id: Optional[str] = None
    target_catalog_id: Optional[str] = None


@dataclass(frozen=True)
class CatalogueEdition:
    """Minimal caller-supplied catalogue identity used for target lookup."""

    sdo: str
    designation: str
    year: Optional[int]
    catalog_id: Optional[str] = None


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str
    indexes: Tuple[int, ...] = ()

    def as_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "indexes": list(self.indexes),
        }


@dataclass(frozen=True)
class ValidationReport:
    schema_version: Optional[int]
    relationships: Tuple[EditionRelationship, ...]
    errors: Tuple[ValidationIssue, ...]
    duplicates: Tuple[ValidationIssue, ...]
    conflicts: Tuple[ValidationIssue, ...]

    @property
    def is_valid(self) -> bool:
        return not self.errors and not self.conflicts

    def as_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "valid": self.is_valid,
            "relationship_count": len(self.relationships),
            "errors": [issue.as_dict() for issue in self.errors],
            "duplicates": [issue.as_dict() for issue in self.duplicates],
            "conflicts": [issue.as_dict() for issue in self.conflicts],
        }


@dataclass(frozen=True)
class ResolutionResult:
    outcome: ResolutionOutcome
    relationship: Optional[EditionRelationship] = None
    target: Optional[CatalogueEdition] = None
    candidates: Tuple[EditionRelationship, ...] = ()
    target_availability: str = "NOT_CHECKED"


def _normalized_identity_part(value: Any) -> str:
    """Normalize case and whitespace while retaining designation punctuation."""
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


def _source_key(relationship: EditionRelationship) -> Tuple[str, str, Optional[int]]:
    return (
        _normalized_identity_part(relationship.source_sdo),
        _normalized_identity_part(relationship.source_designation),
        relationship.source_year,
    )


def _semantic_key(relationship: EditionRelationship) -> Tuple[Any, ...]:
    return (
        _source_key(relationship),
        _normalized_identity_part(relationship.target_sdo),
        _normalized_identity_part(relationship.target_designation),
        relationship.target_year,
        relationship.relationship_type,
        relationship.verification_state,
        relationship.evidence_url,
        relationship.verification_date,
        relationship.source_catalog_id,
        relationship.target_catalog_id,
    )


def _relationship_claim_key(relationship: EditionRelationship) -> Tuple[Any, ...]:
    return (
        _normalized_identity_part(relationship.target_sdo),
        _normalized_identity_part(relationship.target_designation),
        relationship.target_year,
        relationship.relationship_type,
    )


def _optional_year(value: Any, field_name: str, index: int, errors: List[ValidationIssue]) -> Optional[int]:
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 1 or value > 9999:
        errors.append(
            ValidationIssue(
                "INVALID_YEAR",
                f"relationship {index}: {field_name} must be an integer from 1 to 9999 or null",
                (index,),
            )
        )
        return None
    return value


def _optional_catalog_id(value: Any, field_name: str, index: int, errors: List[ValidationIssue]) -> Optional[str]:
    if value is None or value == "":
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        errors.append(
            ValidationIssue(
                "INVALID_CATALOG_ID",
                f"relationship {index}: {field_name} must be a string, integer, or null",
                (index,),
            )
        )
        return None
    return str(value).strip() or None


def _valid_evidence_url(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    parsed = urlsplit(value.strip())
    return parsed.scheme.casefold() in {"http", "https"} and bool(parsed.netloc)


def _parse_relationship(raw: Any, index: int, errors: List[ValidationIssue]) -> Optional[EditionRelationship]:
    if not isinstance(raw, dict):
        errors.append(
            ValidationIssue("INVALID_RECORD", f"relationship {index} must be an object", (index,))
        )
        return None

    required_text = (
        "source_sdo",
        "source_designation",
        "target_sdo",
        "target_designation",
        "relationship_type",
        "evidence_url",
        "verification_state",
    )
    values: Dict[str, str] = {}
    for field_name in required_text:
        value = raw.get(field_name)
        if not isinstance(value, str) or not value.strip():
            errors.append(
                ValidationIssue(
                    "MISSING_REQUIRED_FIELD",
                    f"relationship {index}: {field_name} must be a non-empty string",
                    (index,),
                )
            )
        else:
            values[field_name] = value.strip()

    relationship_type = values.get("relationship_type", "").upper()
    if relationship_type and relationship_type not in RELATIONSHIP_TYPES:
        errors.append(
            ValidationIssue(
                "INVALID_RELATIONSHIP_TYPE",
                f"relationship {index}: unsupported relationship_type {relationship_type!r}",
                (index,),
            )
        )

    verification_state = values.get("verification_state", "").upper()
    if verification_state and verification_state not in VERIFICATION_STATES:
        errors.append(
            ValidationIssue(
                "INVALID_VERIFICATION_STATE",
                f"relationship {index}: unsupported verification_state {verification_state!r}",
                (index,),
            )
        )

    evidence_url = values.get("evidence_url", "")
    if evidence_url and not _valid_evidence_url(evidence_url):
        errors.append(
            ValidationIssue(
                "INVALID_EVIDENCE_URL",
                f"relationship {index}: evidence_url must be an absolute HTTP(S) URL",
                (index,),
            )
        )

    verification_date = raw.get("verification_date")
    if verification_date in (None, ""):
        verification_date = None
    elif not isinstance(verification_date, str):
        errors.append(
            ValidationIssue(
                "INVALID_VERIFICATION_DATE",
                f"relationship {index}: verification_date must use YYYY-MM-DD or be null",
                (index,),
            )
        )
        verification_date = None
    else:
        try:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", verification_date):
                raise ValueError("expected YYYY-MM-DD")
            date.fromisoformat(verification_date)
        except ValueError:
            errors.append(
                ValidationIssue(
                    "INVALID_VERIFICATION_DATE",
                    f"relationship {index}: verification_date must use YYYY-MM-DD",
                    (index,),
                )
            )
    if verification_state == "VERIFIED" and verification_date is None:
        errors.append(
            ValidationIssue(
                "MISSING_VERIFICATION_DATE",
                f"relationship {index}: VERIFIED records require verification_date",
                (index,),
            )
        )

    source_year = _optional_year(raw.get("source_year"), "source_year", index, errors)
    target_year = _optional_year(raw.get("target_year"), "target_year", index, errors)
    source_catalog_id = _optional_catalog_id(
        raw.get("source_catalog_id"), "source_catalog_id", index, errors
    )
    target_catalog_id = _optional_catalog_id(
        raw.get("target_catalog_id"), "target_catalog_id", index, errors
    )

    # Do not return partially invalid records to the resolver.
    if any(issue.indexes == (index,) for issue in errors):
        return None

    return EditionRelationship(
        source_sdo=values["source_sdo"],
        source_designation=values["source_designation"],
        source_year=source_year,
        target_sdo=values["target_sdo"],
        target_designation=values["target_designation"],
        target_year=target_year,
        relationship_type=relationship_type,
        evidence_url=evidence_url,
        verification_state=verification_state,
        verification_date=verification_date,
        source_catalog_id=source_catalog_id,
        target_catalog_id=target_catalog_id,
    )


def validate_relationship_document(document: Any) -> ValidationReport:
    """Validate an in-memory versioned JSON document without side effects."""
    errors: List[ValidationIssue] = []
    duplicates: List[ValidationIssue] = []
    conflicts: List[ValidationIssue] = []
    if not isinstance(document, dict):
        return ValidationReport(
            schema_version=None,
            relationships=(),
            errors=(ValidationIssue("INVALID_DOCUMENT", "document must be an object"),),
            duplicates=(),
            conflicts=(),
        )

    schema_version = document.get("schema_version")
    if (
        isinstance(schema_version, bool)
        or not isinstance(schema_version, int)
        or schema_version != SCHEMA_VERSION
    ):
        errors.append(
            ValidationIssue(
                "UNSUPPORTED_SCHEMA_VERSION",
                f"schema_version must be {SCHEMA_VERSION}",
            )
        )
    raw_relationships = document.get("relationships")
    if not isinstance(raw_relationships, list):
        errors.append(
            ValidationIssue("INVALID_RELATIONSHIPS", "relationships must be an array")
        )
        raw_relationships = []

    parsed: List[Tuple[int, EditionRelationship]] = []
    for index, raw in enumerate(raw_relationships):
        relationship = _parse_relationship(raw, index, errors)
        if relationship is not None:
            parsed.append((index, relationship))

    seen_semantics: Dict[Tuple[Any, ...], int] = {}
    by_source: Dict[Tuple[str, str, Optional[int]], List[Tuple[int, EditionRelationship]]] = {}
    for index, relationship in parsed:
        semantic_key = _semantic_key(relationship)
        if semantic_key in seen_semantics:
            duplicates.append(
                ValidationIssue(
                    "DUPLICATE_RECORD",
                    f"relationship {index} duplicates relationship {seen_semantics[semantic_key]}",
                    (seen_semantics[semantic_key], index),
                )
            )
        else:
            seen_semantics[semantic_key] = index
        by_source.setdefault(_source_key(relationship), []).append((index, relationship))

    for source_key, entries in sorted(by_source.items(), key=lambda item: repr(item[0])):
        active_claims: Dict[Tuple[Any, ...], List[int]] = {}
        for index, relationship in entries:
            if relationship.verification_state == "REJECTED":
                continue
            active_claims.setdefault(_relationship_claim_key(relationship), []).append(index)
        if len(active_claims) > 1:
            indexes = tuple(sorted(index for group in active_claims.values() for index in group))
            conflicts.append(
                ValidationIssue(
                    "CONFLICTING_SOURCE_RELATIONSHIPS",
                    "multiple non-rejected relationship claims share source edition "
                    f"{source_key!r}",
                    indexes,
                )
            )

    return ValidationReport(
        schema_version=schema_version if isinstance(schema_version, int) else None,
        relationships=tuple(relationship for _index, relationship in parsed),
        errors=tuple(errors),
        duplicates=tuple(duplicates),
        conflicts=tuple(conflicts),
    )


def validate_relationship_file(path: str) -> ValidationReport:
    """Read and validate a JSON relationship document; never writes or connects."""
    try:
        with Path(path).open("r", encoding="utf-8") as source:
            document = json.load(source)
    except (OSError, json.JSONDecodeError) as exc:
        return ValidationReport(
            schema_version=None,
            relationships=(),
            errors=(ValidationIssue("INPUT_READ_ERROR", str(exc)),),
            duplicates=(),
            conflicts=(),
        )
    return validate_relationship_document(document)


def _target_key(sdo: str, designation: str, year: Optional[int]) -> Tuple[str, str, Optional[int]]:
    return (
        _normalized_identity_part(sdo),
        _normalized_identity_part(designation),
        year,
    )


def resolve_relationship(
    report: ValidationReport,
    source_sdo: str,
    source_designation: str,
    source_year: Optional[int] = None,
    *,
    source_catalog_id: Optional[str] = None,
    resolved_source_year: Optional[int] = None,
    source_edition_is_unique: bool = False,
    catalogue_editions: Optional[Sequence[CatalogueEdition]] = None,
) -> ResolutionResult:
    """Resolve relationships only from a valid report produced by the validator.

    Invalid reports and raw record iterables return ``INVALID_INPUT``. For an
    explicit request year, an independently resolved year may be omitted, but
    when supplied it must agree with the request.
    """
    if not isinstance(report, ValidationReport) or not report.is_valid:
        return ResolutionResult(ResolutionOutcome.INVALID_INPUT)
    return _resolve_relationship_records(
        report.relationships,
        source_sdo,
        source_designation,
        source_year,
        source_catalog_id=source_catalog_id,
        resolved_source_year=resolved_source_year,
        source_edition_is_unique=source_edition_is_unique,
        catalogue_editions=catalogue_editions,
    )


def _resolve_relationship_records(
    relationships: Iterable[EditionRelationship],
    source_sdo: str,
    source_designation: str,
    source_year: Optional[int] = None,
    *,
    source_catalog_id: Optional[str] = None,
    resolved_source_year: Optional[int] = None,
    source_edition_is_unique: bool = False,
    catalogue_editions: Optional[Sequence[CatalogueEdition]] = None,
) -> ResolutionResult:
    """Internal resolver for records from a valid ``ValidationReport`` only.

    An unqualified request needs an independently resolved unique source
    edition. An explicit-year request only matches a relationship carrying
    that exact source year. Passing ``catalogue_editions`` (including an empty
    sequence) asks the resolver to classify the target as available,
    unavailable, or ambiguous; omitting it leaves availability unchecked.
    """
    if source_year is None:
        if (
            not source_edition_is_unique
            or isinstance(resolved_source_year, bool)
            or not isinstance(resolved_source_year, int)
            or resolved_source_year < 1
            or resolved_source_year > 9999
        ):
            return ResolutionResult(ResolutionOutcome.NO_MATCH)
        effective_year = resolved_source_year
        allow_unspecified_relationship_year = True
    else:
        if (
            isinstance(source_year, bool)
            or not isinstance(source_year, int)
            or source_year < 1
            or source_year > 9999
        ):
            return ResolutionResult(ResolutionOutcome.NO_MATCH)
        if resolved_source_year is not None and (
            isinstance(resolved_source_year, bool)
            or not isinstance(resolved_source_year, int)
            or resolved_source_year != source_year
        ):
            return ResolutionResult(ResolutionOutcome.NO_MATCH)
        effective_year = source_year
        allow_unspecified_relationship_year = False

    applicable: List[EditionRelationship] = []
    for relationship in relationships or ():
        if relationship.verification_state == "REJECTED":
            continue
        if relationship.source_catalog_id is not None and (
            source_catalog_id is None
            or str(source_catalog_id) != relationship.source_catalog_id
        ):
            continue
        if (
            _normalized_identity_part(relationship.source_sdo)
            != _normalized_identity_part(source_sdo)
            or _normalized_identity_part(relationship.source_designation)
            != _normalized_identity_part(source_designation)
        ):
            continue
        if relationship.source_year != effective_year and not (
            allow_unspecified_relationship_year
            and relationship.source_year is None
        ):
            continue
        applicable.append(relationship)

    applicable_by_semantics = {
        _semantic_key(relationship): relationship
        for relationship in applicable
    }
    all_applicable = tuple(
        applicable_by_semantics[key]
        for key in sorted(applicable_by_semantics, key=repr)
    )
    if not all_applicable:
        return ResolutionResult(ResolutionOutcome.NO_MATCH)
    claims = {_relationship_claim_key(item) for item in all_applicable}
    if len(claims) > 1:
        return ResolutionResult(
            ResolutionOutcome.AMBIGUOUS,
            candidates=all_applicable,
        )
    matching = {
        _semantic_key(relationship): relationship
        for relationship in all_applicable
        if relationship.verification_state == "VERIFIED"
    }
    candidates = tuple(matching[key] for key in sorted(matching, key=repr))
    if not candidates:
        return ResolutionResult(ResolutionOutcome.NO_MATCH)
    relationship = candidates[0]
    if catalogue_editions is None:
        return ResolutionResult(
            ResolutionOutcome.MATCH,
            relationship=relationship,
            candidates=candidates,
            target_availability="NOT_CHECKED",
        )

    if relationship.target_catalog_id is not None:
        target_matches = [
            edition
            for edition in catalogue_editions
            if edition.catalog_id is not None
            and str(edition.catalog_id) == relationship.target_catalog_id
        ]
        target_identity = _target_key(
            relationship.target_sdo,
            relationship.target_designation,
            relationship.target_year,
        )
        if any(
            _target_key(edition.sdo, edition.designation, edition.year)
            != target_identity
            for edition in target_matches
        ):
            return ResolutionResult(
                ResolutionOutcome.TARGET_IDENTITY_CONFLICT,
                relationship=relationship,
                candidates=candidates,
                target_availability="CONFLICTED",
            )
    else:
        target_identity = _target_key(
            relationship.target_sdo,
            relationship.target_designation,
            relationship.target_year,
        )
        target_matches = [
            edition
            for edition in catalogue_editions
            if _target_key(edition.sdo, edition.designation, edition.year)
            == target_identity
        ]

    # Repeated references to the same identified row are one target. Distinct
    # row IDs (or unidentified duplicate rows) remain ambiguous.
    by_catalog_id: Dict[str, List[CatalogueEdition]] = {}
    unidentified: List[CatalogueEdition] = []
    for edition in target_matches:
        if edition.catalog_id is None:
            unidentified.append(edition)
        else:
            by_catalog_id.setdefault(str(edition.catalog_id), []).append(edition)
    conflicting_catalog_ids = any(
        len(
            {
                _target_key(item.sdo, item.designation, item.year)
                for item in editions
            }
        )
        > 1
        for editions in by_catalog_id.values()
    )
    distinct_count = len(by_catalog_id) + len(unidentified)
    if distinct_count == 0:
        return ResolutionResult(
            ResolutionOutcome.UNAVAILABLE_TARGET,
            relationship=relationship,
            candidates=candidates,
            target_availability="UNAVAILABLE",
        )
    if distinct_count > 1 or conflicting_catalog_ids:
        return ResolutionResult(
            ResolutionOutcome.AMBIGUOUS_TARGET,
            relationship=relationship,
            candidates=candidates,
            target_availability="AMBIGUOUS",
        )
    if by_catalog_id:
        target_options = next(iter(by_catalog_id.values()))
        target = sorted(
            target_options,
            key=lambda item: repr(
                (item.sdo, item.designation, item.year, item.catalog_id)
            ),
        )[0]
    else:
        target = unidentified[0]
    return ResolutionResult(
        ResolutionOutcome.MATCH,
        relationship=relationship,
        target=target,
        candidates=candidates,
        target_availability="AVAILABLE",
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate an offline standard-edition relationship JSON file."
    )
    parser.add_argument("--validate", required=True, help="Path to a versioned JSON document")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and print a report without writing or importing data",
    )
    arguments = parser.parse_args(argv)
    if not arguments.dry_run:
        parser.error("--dry-run is required; this tool never imports relationship data")
    report = validate_relationship_file(arguments.validate)
    print(json.dumps(report.as_dict(), indent=2, sort_keys=True))
    return 0 if report.is_valid else 1


if __name__ == "__main__":
    sys.exit(main())
