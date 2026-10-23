"""Characterize candidate exclusion helpers before extracting them."""

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.services.document_search_service import DocumentSearchService


class CandidateFilteringCharacterizationTests(unittest.TestCase):
    def test_revision_suffix_returns_normalized_suffix_from_first_matching_field(self):
        candidate = SimpleNamespace(
            standardno="IEC 61378-1 CORR 1 : 2012",
            display_stdNo="IEC 61378-1 + AMD 2A:2019",
        )

        self.assertEqual(
            DocumentSearchService._candidate_revision_suffix(candidate),
            "CORR 1",
        )

    def test_revision_suffix_supports_amendment_aliases_and_missing_fields(self):
        amendment = SimpleNamespace(
            standardno=None,
            display_stdNo="IEC 123+AMD 2A:2020",
        )
        no_designation = SimpleNamespace(
            standardno=None,
            display_stdNo="",
        )
        missing_fields = SimpleNamespace()

        self.assertEqual(
            DocumentSearchService._candidate_revision_suffix(amendment),
            "+AMD 2A",
        )
        self.assertEqual(
            DocumentSearchService._candidate_revision_suffix(no_designation),
            "",
        )
        self.assertEqual(
            DocumentSearchService._candidate_revision_suffix(missing_fields),
            "",
        )

    def test_revision_suffix_recognizes_supported_corrigendum_and_amendment_forms(self):
        cases = (
            ("IEC 100/CORRIGENDUM. NO. 12B:2022", "/CORRIGENDUM.NO.12B"),
            ("IEC 100 COR. 3:2022", "COR.3"),
            ("IEC 100 AMEND. NO. 4A:2022", "AMEND.NO.4A"),
        )
        for designation, expected in cases:
            with self.subTest(designation=designation):
                self.assertEqual(
                    DocumentSearchService._candidate_revision_suffix(
                        SimpleNamespace(standardno=designation)
                    ),
                    expected,
                )

    def test_amendment_detection_accepts_designation_aliases_and_empty_fields(self):
        self.assertTrue(
            DocumentSearchService._candidate_is_amendment(
                SimpleNamespace(
                    display_stdNo="IEC 60079-0:2017 Amendment No. 1",
                    standardno="IEC 60079-0",
                )
            )
        )
        self.assertTrue(
            DocumentSearchService._candidate_is_amendment(
                SimpleNamespace(
                    display_stdNo=None,
                    standardno="IEC 60079-0 AMD 2",
                )
            )
        )
        self.assertFalse(
            DocumentSearchService._candidate_is_amendment(
                SimpleNamespace(display_stdNo="", standardno=None)
            )
        )
        self.assertFalse(
            DocumentSearchService._candidate_is_amendment(SimpleNamespace())
        )

    def test_proposal_detection_checks_designations_and_title(self):
        self.assertTrue(
            DocumentSearchService._candidate_is_proposal(
                SimpleNamespace(
                    display_stdNo="",
                    standardno=None,
                    title="CSDS Proposal: corrosion test method",
                )
            )
        )
        self.assertTrue(
            DocumentSearchService._candidate_is_proposal(
                SimpleNamespace(
                    display_stdNo="ASTM D123 Proposed Edition",
                    standardno="ASTM D123",
                    title="",
                )
            )
        )
        self.assertFalse(
            DocumentSearchService._candidate_is_proposal(
                SimpleNamespace(
                    display_stdNo="ASTM D123:2024",
                    standardno="ASTM D123",
                    title="Published test method",
                )
            )
        )
        self.assertFalse(
            DocumentSearchService._candidate_is_proposal(SimpleNamespace())
        )

    def test_proposal_detection_recognizes_supported_proposal_phrases(self):
        for designation in (
            "IEC 123 Proposal",
            "IEC 123 Proposed Standard",
            "IEC 123 Proposed Edition",
        ):
            with self.subTest(designation=designation):
                self.assertTrue(
                    DocumentSearchService._candidate_is_proposal(
                        SimpleNamespace(standardno=designation)
                    )
                )

    def test_ul_supplemental_detection_requires_ul_identifier_and_marker(self):
        for marker in (
            "Red Line",
            "Revision",
            "Certification Requirement Decision",
            "red line",
            "CERTIFICATION REQUIREMENT DECISION",
        ):
            with self.subTest(marker=marker):
                self.assertTrue(
                    DocumentSearchService._candidate_is_ul_supplemental_publication(
                        SimpleNamespace(
                            display_stdNo=f"UL 840:2022 ({marker})",
                            standardno="UL 840",
                        )
                    )
                )

        self.assertFalse(
            DocumentSearchService._candidate_is_ul_supplemental_publication(
                SimpleNamespace(
                    display_stdNo="UL 840:2022",
                    standardno="UL 840",
                )
            )
        )
        self.assertFalse(
            DocumentSearchService._candidate_is_ul_supplemental_publication(
                SimpleNamespace(
                    display_stdNo="IEC 840:2022 (Red Line)",
                    standardno="IEC 840",
                )
            )
        )
        self.assertFalse(
            DocumentSearchService._candidate_is_ul_supplemental_publication(
                SimpleNamespace()
            )
        )

    def test_exclusion_predicate_combines_amendment_revision_proposal_and_ul_rules(self):
        candidates = (
            SimpleNamespace(standardno="IEC 60079-0 AMD 1"),
            SimpleNamespace(standardno="IEC 61378-1 CORR 1"),
            SimpleNamespace(title="Proposed Standard IEC 123"),
            SimpleNamespace(display_stdNo="UL 840:2022 (Red Line)"),
            SimpleNamespace(standardno="IEC 61378-1:2024", title="Published"),
        )

        self.assertEqual(
            [
                DocumentSearchService._candidate_should_be_excluded(candidate)
                for candidate in candidates
            ],
            [True, True, True, True, False],
        )

    def test_exclusion_predicate_dispatches_helpers_in_short_circuit_order(self):
        calls = []

        def record(name, result):
            def callback(candidate):
                calls.append(name)
                return result

            return callback

        with (
            patch.object(
                DocumentSearchService,
                "_candidate_is_amendment",
                side_effect=record("amendment", False),
            ),
            patch.object(
                DocumentSearchService,
                "_candidate_revision_suffix",
                side_effect=record("revision", ""),
            ),
            patch.object(
                DocumentSearchService,
                "_candidate_is_proposal",
                side_effect=record("proposal", False),
            ),
            patch.object(
                DocumentSearchService,
                "_candidate_is_ul_supplemental_publication",
                side_effect=record("ul_supplemental", False),
            ),
        ):
            self.assertFalse(
                DocumentSearchService._candidate_should_be_excluded(
                    SimpleNamespace()
                )
            )

        self.assertEqual(
            calls,
            ["amendment", "revision", "proposal", "ul_supplemental"],
        )

    def test_exclusion_predicate_stops_after_first_positive_helper(self):
        calls = []

        def amendment(candidate):
            calls.append("amendment")
            return True

        with (
            patch.object(
                DocumentSearchService,
                "_candidate_is_amendment",
                side_effect=amendment,
            ),
            patch.object(
                DocumentSearchService,
                "_candidate_revision_suffix",
                side_effect=AssertionError("revision helper should short-circuit"),
            ),
        ):
            self.assertTrue(
                DocumentSearchService._candidate_should_be_excluded(
                    SimpleNamespace()
                )
            )

        self.assertEqual(calls, ["amendment"])

    def test_exclusion_predicate_returns_true_for_each_later_positive_helper(self):
        helper_names = (
            "_candidate_is_amendment",
            "_candidate_revision_suffix",
            "_candidate_is_proposal",
            "_candidate_is_ul_supplemental_publication",
        )
        positive_results = (True, "CORR 1", True, True)

        for positive_index in range(1, len(helper_names)):
            calls = []
            patches = []
            for index, (name, positive_result) in enumerate(
                zip(helper_names, positive_results)
            ):
                result = positive_result if index == positive_index else (
                    "" if name == "_candidate_revision_suffix" else False
                )

                def callback(candidate, *, helper=name, value=result):
                    calls.append(helper)
                    return value

                patches.append(
                    patch.object(
                        DocumentSearchService,
                        name,
                        side_effect=callback,
                    )
                )

            entered = []
            try:
                for patcher in patches:
                    entered.append(patcher)
                    patcher.start()
                self.assertTrue(
                    DocumentSearchService._candidate_should_be_excluded(
                        SimpleNamespace()
                    ),
                    helper_names[positive_index],
                )
            finally:
                for patcher in reversed(entered):
                    patcher.stop()

            self.assertEqual(
                calls,
                list(helper_names[: positive_index + 1]),
                helper_names[positive_index],
            )


if __name__ == "__main__":
    unittest.main()
