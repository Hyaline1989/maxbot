import unittest

from maxbot.events import InvalidBitrixEvent, parse_deal_update_event


TOKEN = "test-event-token"
DOMAIN = "crm.example.invalid"


class EventTests(unittest.TestCase):
    def test_nested_json_event_is_accepted(self) -> None:
        event = parse_deal_update_event(
            {
                "event": "ONCRMDEALUPDATE",
                "data": {"FIELDS": {"ID": "43528"}},
                "auth": {
                    "application_token": TOKEN,
                    "domain": DOMAIN,
                    "access_token": "must-not-be-returned",
                },
            },
            expected_application_token=TOKEN,
            expected_domain=DOMAIN,
        )

        self.assertEqual(event.deal_id, "43528")
        self.assertFalse(hasattr(event, "access_token"))

    def test_flat_form_event_is_accepted(self) -> None:
        event = parse_deal_update_event(
            {
                "event": "ONCRMDEALUPDATE",
                "data[FIELDS][ID]": "43528",
                "auth[application_token]": TOKEN,
                "auth[domain]": DOMAIN,
            },
            expected_application_token=TOKEN,
            expected_domain=DOMAIN,
        )

        self.assertEqual(event.deal_id, "43528")

    def test_wrong_event_type_is_rejected(self) -> None:
        with self.assertRaises(InvalidBitrixEvent):
            parse_deal_update_event(
                {
                    "event": "ONCRMDEALADD",
                    "data": {"FIELDS": {"ID": "43528"}},
                    "auth": {
                        "application_token": TOKEN,
                        "domain": DOMAIN,
                    },
                },
                expected_application_token=TOKEN,
                expected_domain=DOMAIN,
            )

    def test_wrong_token_is_rejected(self) -> None:
        with self.assertRaises(InvalidBitrixEvent):
            parse_deal_update_event(
                {
                    "event": "ONCRMDEALUPDATE",
                    "data": {"FIELDS": {"ID": "43528"}},
                    "auth": {
                        "application_token": "wrong",
                        "domain": DOMAIN,
                    },
                },
                expected_application_token=TOKEN,
                expected_domain=DOMAIN,
            )

    def test_wrong_domain_is_rejected(self) -> None:
        with self.assertRaises(InvalidBitrixEvent):
            parse_deal_update_event(
                {
                    "event": "ONCRMDEALUPDATE",
                    "data": {"FIELDS": {"ID": "43528"}},
                    "auth": {
                        "application_token": TOKEN,
                        "domain": "other.example.invalid",
                    },
                },
                expected_application_token=TOKEN,
                expected_domain=DOMAIN,
            )

    def test_non_numeric_deal_id_is_rejected(self) -> None:
        with self.assertRaises(InvalidBitrixEvent):
            parse_deal_update_event(
                {
                    "event": "ONCRMDEALUPDATE",
                    "data": {"FIELDS": {"ID": "../secret"}},
                    "auth": {
                        "application_token": TOKEN,
                        "domain": DOMAIN,
                    },
                },
                expected_application_token=TOKEN,
                expected_domain=DOMAIN,
            )


if __name__ == "__main__":
    unittest.main()
