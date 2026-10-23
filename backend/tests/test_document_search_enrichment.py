import unittest
from types import SimpleNamespace

from app.services.document_search_service import DocumentSearchService


class DocumentSearchEnrichmentTests(unittest.TestCase):
    def _make_service(
        self,
        standards,
        masters,
        *,
        currencies=None,
        sdo_titles=None,
        prices=None,
        classifications=None,
        edition_aliases=None,
    ):
        test_case = self

        class FakeEnrichmentRepository:
            def __init__(self):
                self.price_calls = []
                self.classification_fallback_calls = []

            def get_currency_info_for_sdos(self, sdo_ids):
                return {
                    sdo_id: value
                    for sdo_id, value in (currencies or {}).items()
                    if sdo_id in sdo_ids
                }

            def get_sdo_titles(self, sdo_ids):
                return {
                    sdo_id: title
                    for sdo_id, title in (sdo_titles or {}).items()
                    if sdo_id in sdo_ids
                }

            def get_master_standards(self, standard_ids):
                test_case.assertEqual(
                    set(standard_ids),
                    {standard.Standard_id for standard in standards},
                )
                return masters

            def get_edition_price_aliases(self, master_ids):
                test_case.assertEqual(
                    set(master_ids),
                    {master.id for master in masters},
                )
                return edition_aliases or []

            def get_bis_master_aliases(self, master_ids):
                return []

            def get_api_master_price_aliases(self, master_ids):
                return []

            def get_international_equivalent_price_aliases(self, master_ids):
                return []

            def get_prices_for_standards(
                self,
                master_ids,
                additional_master_ids=None,
            ):
                self.price_calls.append(
                    (list(master_ids), list(additional_master_ids or []))
                )
                return prices or []

            def get_classifications_for_standards(self, master_ids):
                return classifications or []

            def get_classifications_from_exact_catalog_duplicates(self, missing_masters):
                self.classification_fallback_calls.append(list(missing_masters))
                return {}

        service = DocumentSearchService.__new__(DocumentSearchService)
        repository = FakeEnrichmentRepository()
        service.enrichment_repository = repository
        return service, repository

    def _standard_and_master(self, *, standard_id=101, master_id=1001):
        standard = SimpleNamespace(
            Standard_id=standard_id,
            sdo_id=7,
            standardno="ISO 9001",
        )
        master = SimpleNamespace(
            id=master_id,
            Standard_id=standard_id,
            sdo_id=7,
            standardno="ISO 9001",
            display_stdNo="ISO 9001 : 2022",
            standardyear=2022,
            DocumentAvailability=1,
        )
        return standard, master

    def test_empty_input_returns_empty_map_without_repository_calls(self):
        service, repository = self._make_service([], [])

        self.assertEqual(service.build_enrichment_map([]), {})
        self.assertEqual(repository.price_calls, [])
        self.assertEqual(repository.classification_fallback_calls, [])

    def test_direct_enrichment_fields_and_classification_owner_filter(self):
        standard, master = self._standard_and_master()
        classification_assignment = SimpleNamespace(
            standard_id=master.id,
            sdo_id=master.sdo_id,
        )
        classifications = [
            (
                classification_assignment,
                {
                    "id": 51,
                    "code": "TC 176",
                    "description": "Quality management",
                    "owner_sdo": "ISO",
                    "owner_sdo_id": 7,
                },
            ),
            (
                classification_assignment,
                {
                    "id": 52,
                    "code": "TC 9",
                    "description": "Wrong owner",
                    "owner_sdo": "BIS",
                    "owner_sdo_id": 21,
                },
            ),
        ]
        prices = [
            SimpleNamespace(
                std_id=master.id,
                formate_id=1,
                id=1,
                non_member_price_rate=0,
            ),
            SimpleNamespace(
                std_id=master.id,
                formate_id=1,
                id=2,
                non_member_price_rate=125.5,
            ),
        ]
        service, repository = self._make_service(
            [standard],
            [master],
            currencies={7: {"code": "CHF", "symbol": "CHF"}},
            sdo_titles={7: "ISO"},
            prices=prices,
            classifications=classifications,
        )

        result = service.build_enrichment_map([standard])

        self.assertEqual(
            result,
            {
                101: {
                    "year": 2022,
                    "currency": "CHF",
                    "currency_symbol": "CHF",
                    "price": 125.5,
                    "document_available": True,
                    "has_database_price": True,
                    "classifications": [
                        {
                            "id": 51,
                            "code": "TC 176",
                            "description": "Quality management",
                            "owner_sdo": "ISO",
                        }
                    ],
                }
            },
        )
        self.assertEqual(repository.price_calls, [([1001], [])])
        self.assertEqual(repository.classification_fallback_calls, [[]])

    def test_edition_alias_supplies_price_and_call_arguments(self):
        standard, master = self._standard_and_master()
        alias = SimpleNamespace(
            id=1002,
            Standard_id=202,
            sdo_id=7,
            standardno="ISO 9001",
            display_stdNo="ISO 9001 : 2022",
            standardyear=2022,
            DocumentAvailability=1,
        )
        alias_price = SimpleNamespace(
            std_id=alias.id,
            formate_id=1,
            id=20,
            non_member_price_rate=72,
        )
        service, repository = self._make_service(
            [standard],
            [master],
            currencies={7: {"code": "USD", "symbol": "$"}},
            sdo_titles={7: "ISO"},
            prices=[alias_price],
            edition_aliases=[alias],
        )

        result = service.build_enrichment_map([standard])

        self.assertEqual(result[101]["price"], 72)
        self.assertEqual(result[101]["currency"], "USD")
        self.assertEqual(result[101]["currency_symbol"], "$")
        self.assertTrue(result[101]["document_available"])
        self.assertFalse(result[101]["has_database_price"])
        self.assertEqual(repository.price_calls, [([1001], [1002])])

    def test_conflicting_duplicate_prices_are_not_resolved(self):
        standard, master = self._standard_and_master()
        prices = [
            SimpleNamespace(
                std_id=master.id,
                formate_id=1,
                id=31,
                non_member_price_rate=100,
            ),
            SimpleNamespace(
                std_id=master.id,
                formate_id=1,
                id=32,
                non_member_price_rate=110,
            ),
        ]
        service, _repository = self._make_service(
            [standard],
            [master],
            currencies={7: {"code": "USD", "symbol": "$"}},
            sdo_titles={7: "ISO"},
            prices=prices,
        )

        result = service.build_enrichment_map([standard])

        self.assertIsNone(result[101]["price"])
        self.assertTrue(result[101]["has_database_price"])


if __name__ == "__main__":
    unittest.main()
