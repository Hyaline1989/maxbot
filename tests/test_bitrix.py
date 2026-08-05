import unittest

from maxbot.bitrix import (
    BitrixReadClient,
    BitrixReferralReader,
    DealNotAllowedError,
    RelatedEntityNotAllowedError,
    UnexpectedCategoryError,
    UnexpectedStageError,
)


class FakeTransport:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, str]]] = []
        self.responses = {
            "crm.deal.get": {
                "result": {
                    "ID": "TEST-43528",
                    "DATE_CREATE": "2026-07-23T11:59:00+03:00",
                    "CATEGORY_ID": "0",
                    "STAGE_ID": "3",
                    "TITLE": "Иванов Алексей Петрович",
                    "CONTACT_ID": "CONTACT-7",
                    "UF_CRM_1684488775220": "2026-07-23",
                    "UF_CRM_622F3E04D997E": "2026-07-30T10:00:00+03:00",
                    "UF_CRM_68F1ED4DB3EE8": "Тестовый менеджер",
                    "UF_CRM_642A972B79B02": "COMPANY_12",
                    "UF_CRM_1709115728": ["784"],
                    "UF_CRM_67F4D854D0BA5": "Грузчик",
                }
            },
            "crm.deal.fields": {
                "result": {
                    "UF_CRM_1709115728": {
                        "type": "enumeration",
                        "isMultiple": True,
                        "items": [
                            {"ID": "784", "VALUE": "Грузчик"},
                            {"ID": "785", "VALUE": "Комплектовщик"},
                        ],
                    }
                }
            },
            "crm.contact.get": {
                "result": {
                    "LAST_NAME": "Иванов",
                    "NAME": "Алексей",
                    "SECOND_NAME": "Алексей",
                    "BIRTHDATE": "1990-01-02",
                    "PHONE": [{"VALUE": "+7 (900) 000-00-00"}],
                }
            },
            "crm.company.get": {
                "result": {
                    "TITLE": "Тестовый объект Север",
                    "ASSIGNED_BY_ID": "17",
                    "UF_CRM_ADDITIONAL_MAX_MANAGERS": ["18", "17", "19"],
                }
            },
        }

    def __call__(self, method: str, parameters: object) -> dict:
        parameter_copy = dict(parameters)  # type: ignore[arg-type]
        self.calls.append((method, parameter_copy))
        return self.responses[method]


class BitrixReaderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.transport = FakeTransport()
        self.client = BitrixReadClient(
            "https://example.invalid/rest/test/",
            allowed_deal_ids={"TEST-43528"},
            transport=self.transport,
        )
        self.reader = BitrixReferralReader(
            self.client,
            "https://example.invalid",
        )

    def test_reader_builds_referral_without_changing_phone(self) -> None:
        referral = self.reader.read("TEST-43528")

        self.assertEqual(referral.deal_id, "TEST-43528")
        self.assertEqual(
            referral.created_at, "2026-07-23T11:59:00+03:00"
        )
        self.assertEqual(referral.full_name, "Иванов Алексей")
        self.assertEqual(referral.birth_date, "1990-01-02")
        self.assertEqual(referral.phone, "+7 (900) 000-00-00")
        self.assertEqual(referral.object_name, "Тестовый объект Север")
        self.assertEqual(referral.position_name, "Грузчик")
        self.assertEqual(referral.planned_arrival, "30.07.2026")
        self.assertEqual(referral.directed_at, "2026-07-23T00:00:00")
        self.assertEqual(
            [method for method, _ in self.transport.calls],
            [
                "crm.deal.get",
                "crm.contact.get",
                "crm.company.get",
                "crm.deal.fields",
            ],
        )

    def test_unlisted_deal_is_blocked_before_request(self) -> None:
        with self.assertRaises(DealNotAllowedError):
            self.reader.read("OTHER")
        self.assertEqual(self.transport.calls, [])

    def test_unlinked_contact_and_company_are_blocked(self) -> None:
        with self.assertRaises(RelatedEntityNotAllowedError):
            self.client.get_contact("OTHER")
        with self.assertRaises(RelatedEntityNotAllowedError):
            self.client.get_company("OTHER")
        self.assertEqual(self.transport.calls, [])

    def test_reader_gets_bitrix_id_of_object_responsible(self) -> None:
        referral = self.reader.read("TEST-43528")
        self.assertEqual(referral.object_manager_bitrix_id, "17")
        self.assertEqual(
            [method for method, _ in self.transport.calls],
            [
                "crm.deal.get",
                "crm.contact.get",
                "crm.company.get",
                "crm.deal.fields",
            ],
        )

    def test_reader_joins_multiple_positions_without_duplicates(self) -> None:
        self.transport.responses["crm.deal.get"]["result"][
            "UF_CRM_1709115728"
        ] = ["784", "785", "784"]

        referral = self.reader.read("TEST-43528")

        self.assertEqual(referral.position_name, "Грузчик, Комплектовщик")

    def test_reader_uses_technical_position_as_safe_fallback(self) -> None:
        self.transport.responses["crm.deal.get"]["result"][
            "UF_CRM_1709115728"
        ] = []

        referral = self.reader.read("TEST-43528")

        self.assertEqual(referral.position_name, "Грузчик")

    def test_reader_gets_additional_object_managers(self) -> None:
        reader = BitrixReferralReader(
            self.client,
            "https://example.invalid",
            additional_managers_field="UF_CRM_ADDITIONAL_MAX_MANAGERS",
        )

        referral = reader.read("TEST-43528")

        self.assertEqual(
            referral.additional_manager_bitrix_ids,
            ("18", "17", "19"),
        )

    def test_empty_additional_manager_field_is_not_a_manager(self) -> None:
        self.transport.responses["crm.company.get"]["result"][
            "UF_CRM_ADDITIONAL_MAX_MANAGERS"
        ] = False
        reader = BitrixReferralReader(
            self.client,
            "https://example.invalid",
            additional_managers_field="UF_CRM_ADDITIONAL_MAX_MANAGERS",
        )

        referral = reader.read("TEST-43528")

        self.assertEqual(referral.additional_manager_bitrix_ids, ())

    def test_wrong_category_is_rejected_before_related_reads(self) -> None:
        self.transport.responses["crm.deal.get"]["result"]["CATEGORY_ID"] = "9"

        with self.assertRaises(UnexpectedCategoryError):
            self.reader.read("TEST-43528")

        self.assertEqual(
            [method for method, _ in self.transport.calls],
            ["crm.deal.get"],
        )

    def test_discovery_allows_only_ids_returned_by_safe_funnel_query(self) -> None:
        transport = FakeTransport()
        transport.responses["crm.deal.list"] = {
            "result": [
                {
                    "ID": "TEST-43528",
                    "CATEGORY_ID": "0",
                    "MOVED_TIME": "2026-07-27T10:00:00+03:00",
                    "STAGE_ID": "3",
                },
                {
                    "ID": "OTHER-FUNNEL",
                    "CATEGORY_ID": "9",
                    "MOVED_TIME": "2026-07-27T10:00:00+03:00",
                    "STAGE_ID": "3",
                },
            ]
        }
        client = BitrixReadClient(
            "https://example.invalid/rest/test/",
            allowed_deal_ids=set(),
            discover_funnel_deals=True,
            transport=transport,
        )

        rows = client.list_recent_target_stage_deals(
            __import__("datetime").datetime(2026, 7, 27, 9, 0, 0)
        )

        self.assertEqual([row["ID"] for row in rows], ["TEST-43528"])
        client.get_deal("TEST-43528")
        with self.assertRaises(DealNotAllowedError):
            client.get_deal("OTHER-FUNNEL")

    def test_deal_that_left_target_stage_is_rejected_before_related_reads(self) -> None:
        self.transport.responses["crm.deal.get"]["result"]["STAGE_ID"] = "NEW"

        with self.assertRaises(UnexpectedStageError):
            self.reader.read("TEST-43528")

        self.assertEqual(
            [method for method, _ in self.transport.calls],
            ["crm.deal.get"],
        )


if __name__ == "__main__":
    unittest.main()
