import unittest
from unittest.mock import patch

from app.services.iso_open_data_service import ISOOpenDataService


class ISOOpenDataServiceTests(unittest.TestCase):
    def test_returns_latest_published_edition_for_requested_part(self):
        records = [
            {
                "id": 54503,
                "reference": "ISO 15589-1:2015",
                "currentStage": 6060,
                "publicationDate": "2015-03-02",
                "edition": 2,
                "ownerCommittee": "ISO/TC 67/SC 2",
            },
            {
                "id": 86820,
                "reference": "ISO 15589-1:2026",
                "currentStage": 6060,
                "publicationDate": "2026-07-13",
                "edition": 3,
                "ownerCommittee": "ISO/TC 67/SC 2",
            },
            {
                "id": 99999,
                "reference": "ISO 15589-2:2026",
                "currentStage": 6060,
                "publicationDate": "2026-07-13",
                "edition": 3,
            },
            {
                "id": 100000,
                "reference": "ISO 15589-1:2015/Cor 1:2020",
                "currentStage": 6060,
                "supplementType": "cor",
                "publicationDate": "2020-01-01",
                "edition": 1,
            },
        ]
        with patch.object(ISOOpenDataService, "_get_records", return_value=records):
            latest = ISOOpenDataService.latest_published(
                "ISO", "ISO 15589-1:2015"
            )
        self.assertEqual(latest["reference"], "ISO 15589-1:2026")
        self.assertEqual(latest["ownerCommittee"], "ISO/TC 67/SC 2")

    def test_returns_no_candidate_when_no_published_edition_matches(self):
        records = [
            {
                "id": 1,
                "reference": "ISO 1234:2026",
                "currentStage": 5050,
                "publicationDate": "2026-01-01",
                "edition": 1,
            }
        ]
        with patch.object(ISOOpenDataService, "_get_records", return_value=records):
            latest = ISOOpenDataService.latest_published("ISO", "ISO 1234")
        self.assertIsNone(latest)

if __name__ == "__main__":
    unittest.main()
