import unittest
from io import BytesIO
from unittest.mock import patch

from app.routes import export_routes
from app.routes.export_routes import export_excel
from app.services import export_preparation


class ExportRouteRefreshTests(unittest.TestCase):
    def test_excel_export_uses_submitted_rows_for_catalog_lifecycle_cases(self):
        # API RP 44 previously triggered a second search through the curated
        # lifecycle registry; exports now consume the resolved search payload.
        submitted = {
            "requested_sdo": "API",
            "requested_standard": "API RP 44 : 2011",
            "matched": True,
            "status": "AVAILABLE",
            "standard": {"Standard_id": "API-RP44-2011"},
        }
        with (
            patch.object(
                export_preparation.DocumentSearchService,
                "search",
            ) as search,
            patch.object(
                export_routes.GroupingService,
                "group_results",
                return_value={},
            ),
            patch.object(
                export_routes.ExportService,
                "export_results",
                return_value=BytesIO(b"xlsx"),
            ) as export,
        ):
            response = export_excel([submitted], db=object())

        exported_results = export.call_args.args[0]["results"]
        self.assertEqual(exported_results, [submitted])
        self.assertIs(exported_results[0], submitted)
        search.assert_not_called()
        self.assertEqual(response.body, b"xlsx")

    def test_api_1176_and_nace_refreshes_remain_enabled(self):
        # This captures current route behavior pending product approval of
        # publisher-specific API/NACE refresh semantics; it does not verify a
        # lifecycle or canonical-identity claim.
        api_result = {
            "requested_sdo": "API",
            "requested_standard": "API RP 1176 : 2016",
            "standard": {},
        }
        nace_result = {
            "requested_sdo": "NACE",
            "requested_standard": "NACE MR0103 (ISO 17945) : 2015",
            "standard": {},
        }
        api_refreshed = {"requested_sdo": "API", "standard": {"id": 1}}
        nace_refreshed = {
            "requested_sdo": "NACE",
            "matched": True,
            "standard": {"Standard_id": "ANSI-NACE-MR0103-ISO-17945-2015"},
        }

        with patch.object(
            export_preparation.DocumentSearchService,
            "search",
            side_effect=[[api_refreshed], [nace_refreshed]],
        ) as search:
            actual = export_preparation._refresh_official_catalog_rows(
                [api_result, nace_result],
                object(),
            )

        self.assertEqual(actual, [api_refreshed, nace_refreshed])
        self.assertEqual(search.call_count, 2)


if __name__ == "__main__":
    unittest.main()
