import unittest
from io import BytesIO

from sqlalchemy.exc import OperationalError

from app.core.api_classification_filter import filter_api_classifications
from app.repositories.identity_lookup import (
    keep_rows_containing_core,
    unique_rows_by_id,
)
from app.core.db_retry import run_with_retry
from app.core.legacy_office import OfficeConversionError, converted_office_file
from app.core.normalizer import alphanumeric_upper, normalize_standard_number
from app.core.standard_expression_parser import StandardExpressionParser
from app.core.standard_formatter import normalize_display_number
from app.core.standard_identity import (
    clean,
    extract_year,
    identity_matches,
    normalize_identity_core,
    normalize_tokens,
    parse_identity,
    reaffirmation_year,
    sdo_identifier_prefixes,
    standard_number_year,
)


class NormalizationTests(unittest.TestCase):
    def test_clean_maps_unicode_dashes_and_collapses_space(self):
        self.assertEqual(clean("  ISO\u2011 9001  "), "ISO- 9001")

    def test_normalize_tokens_tightens_separators(self):
        self.assertEqual(normalize_tokens(" iso : 9001 - 1 "), "ISO:9001-1")

    def test_identity_core_drops_punctuation(self):
        self.assertEqual(normalize_identity_core("ISO 9001-1"), "ISO90011")

    def test_standard_number_removes_all_whitespace(self):
        self.assertEqual(normalize_standard_number(" iso  9001 "), "ISO9001")

    def test_display_number_keeps_single_spaces_and_case(self):
        self.assertEqual(normalize_display_number(" iso   9001 "), "iso 9001")

    def test_alphanumeric_upper_matches_catalogue_keys(self):
        self.assertEqual(alphanumeric_upper("API STD 650:2013"), "APISTD6502013")


class AliasAndYearTests(unittest.TestCase):
    def test_is_and_bis_share_identifier_prefixes(self):
        is_prefixes = sdo_identifier_prefixes("IS")
        bis_prefixes = sdo_identifier_prefixes("BIS")
        self.assertIn("BIS", is_prefixes)
        self.assertIn("IS", bis_prefixes)
        self.assertIn("IS/IEC", is_prefixes)

    def test_catalogue_numbers_are_not_treated_as_edition_years(self):
        self.assertEqual(extract_year("API 2003"), ("API 2003", None))
        self.assertEqual(extract_year("IS 1905"), ("IS 1905", None))

    def test_hyphenated_and_colon_years_are_editions(self):
        self.assertEqual(extract_year("IBC-2024"), ("IBC", 2024))
        self.assertEqual(extract_year("ISO 9001:2015"), ("ISO 9001", 2015))

    def test_reaffirmation_year_is_separate_from_edition_year(self):
        self.assertEqual(
            reaffirmation_year("ASTM A36 (Reaffirmed 2019)"),
            2019,
        )
        self.assertIsNone(reaffirmation_year("ASTM A36-19"))

    def test_standard_number_year_reads_four_and_two_digit_suffixes(self):
        self.assertEqual(standard_number_year("ISO9001:2015"), 2015)
        self.assertEqual(standard_number_year("AMS2750-25"), 2025)


class QualifierTests(unittest.TestCase):
    def test_parser_canonicalizes_qualifier_words(self):
        parsed = {
            "ISO 9001 Part 1": "PART",
            "IEC 60079 Sec 2": "SEC",
            "ASME BPVC Chapter 3": "CHAPTER",
            "ISO 9001 Series": "SERIES",
        }
        for text, qualifier_type in parsed.items():
            result = StandardExpressionParser.parse(text)
            self.assertIsNotNone(result)
            self.assertEqual(result["qualifier"]["type"], qualifier_type)


class IdentityMatchTests(unittest.TestCase):
    def test_publisher_specific_identities_keep_their_cores(self):
        expected = {
            ("ASTM", "A36-19"): ("A36", 2019, None),
            ("IEC", "60079-1"): ("60079", None, "PART:1"),
            ("IEC", "146-1-3"): ("146PART1", None, "SECTION:3"),
            ("SAE", "AMS 2750"): ("AMS2750", None, None),
            ("BIS", "IS 5831"): ("5831", None, None),
            ("BSI", "BS EN 10213"): ("10213", None, None),
            ("JIS", "B 2220"): ("B2220", None, None),
            ("ISA", "S75.01"): ("S7501", None, None),
            ("IS", "1905"): ("1905", None, None),
        }
        for (sdo, number), (core, year, qualifier) in expected.items():
            identity = parse_identity(sdo, number)
            self.assertEqual(identity["core_number"], core)
            self.assertEqual(identity["year"], year)
            self.assertEqual(identity["qualifier"], qualifier)

    def test_same_edition_matches_and_a_different_year_does_not(self):
        requested = parse_identity("ASTM", "A36-19")
        self.assertTrue(identity_matches(requested, parse_identity("ASTM", "A36-19")))
        self.assertFalse(identity_matches(requested, parse_identity("ASTM", "A36-20")))

    def test_part_qualifier_must_agree(self):
        requested = parse_identity("IEC", "60079-1")
        other_part = parse_identity("IEC", "60079-2")
        self.assertFalse(identity_matches(requested, other_part))

    def test_api_classification_keeps_the_preferred_code(self):
        classifications = [{"code": "1"}, {"code": "8"}]
        selected = filter_api_classifications("API STD 650", classifications)
        self.assertEqual([item["code"] for item in selected], ["8"])


class DatabaseRetryTests(unittest.TestCase):
    def test_disconnect_retries_once_after_rollback(self):
        calls = {"count": 0}

        class Query:
            def all(self):
                calls["count"] += 1
                if calls["count"] == 1:
                    error = OperationalError("SELECT 1", {}, Exception("db"))
                    error.orig = type("Orig", (), {"args": (2006, "gone")})()
                    raise error
                return ["ok"]

        class Session:
            def __init__(self):
                self.rollbacks = 0

            def rollback(self):
                self.rollbacks += 1

        session = Session()
        self.assertEqual(run_with_retry(session, Query), ["ok"])
        self.assertEqual(session.rollbacks, 1)

    def test_other_mysql_errors_are_not_retried(self):
        class Query:
            def all(self):
                error = OperationalError("SELECT 1", {}, Exception("db"))
                error.orig = type("Orig", (), {"args": (1064, "syntax")})()
                raise error

        class Session:
            def rollback(self):
                raise AssertionError("rollback should not run")

        with self.assertRaises(OperationalError):
            run_with_retry(Session(), Query)


class LookupHelperTests(unittest.TestCase):
    def test_duplicate_rows_are_kept_once_when_the_core_appears(self):
        class Row:
            def __init__(self, row_id, display):
                self.id = row_id
                self.display_stdNo = display
                self.standardno = ""

        first = Row(1, "ISO 9001")
        duplicate = Row(1, "ISO 9001")
        other = Row(2, "ISO 14001")
        seen = set()
        kept = keep_rows_containing_core(
            [first, duplicate, other],
            ["9001"],
            ("display_stdNo", "standardno"),
            seen,
        )
        self.assertEqual([row.id for row in kept], [1])
        self.assertEqual(
            [row.id for row in unique_rows_by_id([other, other], seen)],
            [2],
        )


class OfficeConversionTests(unittest.TestCase):
    def test_unexpected_target_extension_is_rejected(self):
        with self.assertRaises(OfficeConversionError):
            with converted_office_file(BytesIO(b"data"), "../secret.doc", ".exe"):
                pass


if __name__ == "__main__":
    unittest.main()
