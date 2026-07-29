import unittest
from unittest.mock import patch

from maxbot.config import (
    BITRIX_DEAL_CATEGORY_ID,
    BITRIX_INTERVIEW_STAGE_ID,
    BITRIX_DIRECTED_STAGE_ID,
    CONFIRMED_CONTACT_FIELDS,
    CONFIRMED_DEAL_FIELDS,
    Settings,
)


class ConfigTests(unittest.TestCase):
    def test_confirmed_deal_field_codes(self) -> None:
        self.assertEqual(
            CONFIRMED_DEAL_FIELDS["directed_at"],
            "UF_CRM_1684488775220",
        )
        self.assertEqual(CONFIRMED_DEAL_FIELDS["candidate_title"], "TITLE")
        self.assertEqual(CONFIRMED_DEAL_FIELDS["contact_id"], "CONTACT_ID")

    def test_confirmed_contact_field_codes(self) -> None:
        self.assertEqual(CONFIRMED_CONTACT_FIELDS["last_name"], "LAST_NAME")
        self.assertEqual(CONFIRMED_CONTACT_FIELDS["name"], "NAME")
        self.assertEqual(
            CONFIRMED_CONTACT_FIELDS["second_name"],
            "SECOND_NAME",
        )
        self.assertEqual(CONFIRMED_CONTACT_FIELDS["birth_date"], "BIRTHDATE")
        self.assertEqual(CONFIRMED_CONTACT_FIELDS["phones"], "PHONE")

    def test_confirmed_funnel_and_stage(self) -> None:
        self.assertEqual(BITRIX_DEAL_CATEGORY_ID, "0")
        self.assertEqual(BITRIX_INTERVIEW_STAGE_ID, "NEW")
        self.assertEqual(BITRIX_DIRECTED_STAGE_ID, "3")

    def test_current_max_api_base_url_is_default(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            settings = Settings.from_environment()

        self.assertEqual(
            settings.max_api_base_url,
            "https://platform-api2.max.ru",
        )
        self.assertFalse(settings.bitrix_discover_funnel_deals)
        self.assertFalse(settings.max_sending_enabled)


if __name__ == "__main__":
    unittest.main()
