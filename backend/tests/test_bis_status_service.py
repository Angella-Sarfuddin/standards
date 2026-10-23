import unittest
from unittest.mock import patch

from app.services.bis_status_service import BISStatusService
from app.utils.standard_identity import parse_identity


class BISStatusServiceTests(unittest.TestCase):
    def test_search_number_builds_exact_bis_edition_queries(self):
        cases = {
            "IS 3025 PT 24 : 1986": "IS 3025 : Part 24 : 1986",
            "IS 3025 PT 31 : 1988": "IS 3025 : Part 31 : 1988",
            "IS SP 7 : 2017": "SP 7 : 2017",
        }
        for requested, expected in cases.items():
            with self.subTest(requested=requested):
                identity = parse_identity("IS", requested)
                self.assertEqual(
                    BISStatusService._search_number({"identity": identity}),
                    expected,
                )

    def test_fetch_status_reads_withdrawn_and_superseded_by(self):
        html = b"""
        <html><head><title>Result</title></head><body>
        <div>You Searched for: IS 3025 Part 31 : 1988</div>
        <div>Superseeded by : IS 3025 Part 31 Sec 1 : 2022</div>
        <div>Status : withdrawn</div>
        </body></html>
        """

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return html

        with patch("app.services.bis_status_service.urlopen", return_value=Response()):
            result = BISStatusService._fetch_status("IS 3025 : Part 31 : 1988")

        self.assertEqual(result["status"], "WITHDRAWN")
        self.assertEqual(
            result["superseded_by"], "IS 3025 Part 31 Sec 1 : 2022"
        )
        self.assertTrue(result["verified"])

    def test_fetch_status_keeps_textual_supersession_after_status_and_price(self):
        html = b"""
        <html><body>
        <div>You Searched for: IS 3025 Part 24 : 1986</div>
        <div>Status : Withdrawn</div>
        <div>Price within India : Rs. 0</div>
        <div>Superseeded by : Decided by Council</div>
        </body></html>
        """

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return html

        with patch("app.services.bis_status_service.urlopen", return_value=Response()):
            result = BISStatusService._fetch_status("IS 3025 : Part 24 : 1986")

        self.assertEqual(result["status"], "WITHDRAWN")
        self.assertEqual(result["superseded_by"], "Decided by Council")

    def test_fetch_status_stops_supersession_text_at_next_bis_field(self):
        html = b"""
        <html><body>
        <div>You Searched for: IS 3025 Part 31 : 1988</div>
        <div>Status : Withdrawn</div>
        <div>Superseded by : IS 3025 Part 31 Sec 1 : 2022</div>
        <div>No. of Amendments : 0</div>
        <div>Price within India : Rs. 0</div>
        </body></html>
        """

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return html

        with patch("app.services.bis_status_service.urlopen", return_value=Response()):
            result = BISStatusService._fetch_status("IS 3025 : Part 31 : 1988")

        self.assertEqual(
            result["superseded_by"], "IS 3025 Part 31 Sec 1 : 2022"
        )

    def test_unverified_lookup_is_not_treated_as_active(self):
        with patch(
            "app.services.bis_status_service.urlopen",
            side_effect=TimeoutError("timed out"),
        ):
            result = BISStatusService._fetch_status("IS 123 : 2000")

        self.assertEqual(result["status"], "STATUS UNVERIFIED")
        self.assertFalse(result["verified"])


if __name__ == "__main__":
    unittest.main()
