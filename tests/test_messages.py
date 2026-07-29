from datetime import datetime
import unittest

from maxbot.messages import (
    build_error_message,
    build_private_referral_message,
    build_referral_message,
)
from tests.test_validation import complete_referral


class MessageTests(unittest.TestCase):
    def test_referral_message_matches_confirmed_template(self) -> None:
        referral = complete_referral(phone="8 (900) 123-45-67")
        message = build_referral_message(referral)

        self.assertEqual(
            message,
            "Вахтовик Иванов Алексей Петрович, 1990-01-01, "
            "номер телефона 8 (900) 123-45-67, направлен на "
            "Тестовый объект, прибудет к вам ориентировочно "
            "30.07.2026, сделка: https://example.invalid/deal/TEST-1\n"
            "Менеджер подбора: Тестовый менеджер",
        )
        self.assertIn("Менеджер подбора: Тестовый менеджер", message)

    def test_group_message_omits_empty_recruitment_manager(self) -> None:
        message = build_referral_message(
            complete_referral(manager_name="")
        )
        self.assertNotIn("Менеджер подбора:", message)

    def test_private_message_matches_confirmed_template(self) -> None:
        referral = complete_referral(
            candidate_title="Тарасов Максим Викторович",
            phone="+79625164193",
            object_name="Спортмастер СПБ",
            planned_arrival="04.12.2025",
            planned_arrival_at="04.12.2025 10:00",
        )

        self.assertEqual(
            build_private_referral_message(referral),
            "🔔 НАПОМИНАНИЕ:\n"
            "Вахтовик Тарасов Максим Викторович номер телефона +79625164193 "
            "направлен на Спортмастер СПБ прибудет к Вам ориентировочно "
            "04.12.2025 10:00\n\n"
            "💡 Не забудьте встретить вахтовика!",
        )
        self.assertNotIn(
            "Менеджер подбора",
            build_private_referral_message(referral),
        )

    def test_error_message_contains_missing_fields_and_detection_time(self) -> None:
        referral = complete_referral(object_name="", planned_arrival="")
        message = build_error_message(
            referral,
            ["объект", "ориентировочная дата прибытия"],
            datetime(2026, 7, 23, 13, 45, 12),
        )

        self.assertIn("Ошибка обработки направления", message)
        self.assertIn(
            "Не заполнено: объект, ориентировочная дата прибытия",
            message,
        )
        self.assertIn("Обнаружено: 23.07.2026 13:45:12", message)
        self.assertIn("Уведомление о направлении не отправлено.", message)
        self.assertIn("Ответственная: Екатерина Линник", message)


if __name__ == "__main__":
    unittest.main()
