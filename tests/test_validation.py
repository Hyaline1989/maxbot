import unittest

from maxbot.models import Referral
from maxbot.validation import missing_fields


def complete_referral(**changes: str) -> Referral:
    values = {
        "deal_id": "TEST-1",
        "created_at": "2026-07-23T11:59:00+03:00",
        "candidate_title": "Иванов Алексей Петрович",
        "full_name": "Иванов Алексей Петрович",
        "birth_date": "1990-01-01",
        "phone": "+7 900 000-00-00",
        "object_name": "Тестовый объект",
        "position_name": "Комплектовщик",
        "manager_name": "Тестовый менеджер",
        "directed_at": "2026-07-23T12:00:00+03:00",
        "planned_arrival": "30.07.2026",
        "deal_url": "https://example.invalid/deal/TEST-1",
    }
    values.update(changes)
    return Referral(**values)


class ValidationTests(unittest.TestCase):
    def test_complete_referral_has_no_missing_fields(self) -> None:
        self.assertEqual(missing_fields(complete_referral()), [])

    def test_manager_is_not_required(self) -> None:
        self.assertEqual(
            missing_fields(complete_referral(manager_name="")),
            [],
        )

    def test_blank_fields_are_reported_with_readable_names(self) -> None:
        referral = complete_referral(object_name=" ", planned_arrival="")
        self.assertEqual(
            missing_fields(referral),
            ["объект", "ориентировочная дата прибытия"],
        )


if __name__ == "__main__":
    unittest.main()
