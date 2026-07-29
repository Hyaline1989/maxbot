from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from maxbot.delivery import ReferralDelivery
from maxbot.journal import SQLiteJournal
from maxbot.max_api import MaxApiError
from maxbot.max_registry import MaxManagerRegistry, RegisteredManager
from maxbot.service import ReferralProcessor
from tests.test_validation import complete_referral


class FakeMax:
    def __init__(self, fail=False, private_fail=False):
        self.fail = fail
        self.private_fail = private_fail
        self.sent = []
        self.private_sent = []

    def send_text(self, text):
        self.sent.append(text)
        if self.fail:
            raise MaxApiError("test")
        return "mid-test"

    def send_text_to_user(self, user_id, text):
        self.private_sent.append((user_id, text))
        if self.private_fail:
            raise MaxApiError("test")
        return "private-mid-test"


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.journal = SQLiteJournal(Path(self.temp.name) / "journal.sqlite3")
        self.journal.initialize()
        self.registry = MaxManagerRegistry(
            Path(self.temp.name) / "registry.sqlite3"
        )
        self.registry.register(
            RegisteredManager(
                "777",
                "Иван",
                "Иванов",
                "ivan",
                100,
                bitrix_user_id="17",
            )
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_success_is_marked_sent_and_not_repeated(self):
        max_client = FakeMax()
        delivery = ReferralDelivery(
            ReferralProcessor(self.journal), self.journal, max_client
        )
        referral = complete_referral()

        first = delivery.deliver(referral)
        second = delivery.deliver(referral)

        self.assertEqual(first.status, "sent")
        self.assertEqual(second.status, "duplicate")
        self.assertEqual(len(max_client.sent), 1)
        entry = self.journal.get(referral.deal_id, "stage:3")
        self.assertEqual(entry.max_message_id, "mid-test")

    def test_failed_send_can_be_retried(self):
        max_client = FakeMax(fail=True)
        delivery = ReferralDelivery(
            ReferralProcessor(self.journal), self.journal, max_client
        )
        referral = complete_referral()

        self.assertEqual(delivery.deliver(referral).status, "send_failed")
        max_client.fail = False
        self.assertEqual(delivery.deliver(referral).status, "sent")
        self.assertEqual(len(max_client.sent), 2)

    def test_new_stage_entry_is_sent_again(self):
        max_client = FakeMax()
        delivery = ReferralDelivery(
            ReferralProcessor(self.journal), self.journal, max_client
        )
        referral = complete_referral()

        first = delivery.deliver(
            referral,
            event_key="stage:3:2026-07-23T12:00:00+03:00",
        )
        second = delivery.deliver(
            referral,
            event_key="stage:3:2026-07-24T12:00:00+03:00",
        )

        self.assertEqual(first.status, "sent")
        self.assertEqual(second.status, "sent")
        self.assertEqual(len(max_client.sent), 2)

    def test_group_and_private_messages_use_different_templates(self):
        max_client = FakeMax()
        delivery = ReferralDelivery(
            ReferralProcessor(self.journal),
            self.journal,
            max_client,
            private_delivery_enabled=True,
            admin_max_user_id="999",
            manager_registry=self.registry,
        )
        referral = complete_referral(
            object_manager_bitrix_id="17",
            planned_arrival_at="30.07.2026 10:00",
        )

        result = delivery.deliver(referral)

        self.assertEqual(result.status, "sent_with_private")
        self.assertEqual(len(max_client.sent), 1)
        self.assertIn("Менеджер подбора:", max_client.sent[0])
        self.assertEqual(len(max_client.private_sent), 1)
        recipient, private_text = max_client.private_sent[0]
        self.assertEqual(recipient, "777")
        self.assertIn("🔔 НАПОМИНАНИЕ:", private_text)
        self.assertNotIn("Менеджер подбора:", private_text)
        entry = self.journal.get_private_delivery(
            referral.deal_id,
            "stage:3",
            "17",
        )
        self.assertEqual(entry.status, "sent")
        self.assertEqual(entry.max_message_id, "private-mid-test")

    def test_missing_manager_max_id_does_not_repeat_group(self):
        max_client = FakeMax()
        delivery = ReferralDelivery(
            ReferralProcessor(self.journal),
            self.journal,
            max_client,
            private_delivery_enabled=True,
            admin_max_user_id="999",
            manager_registry=self.registry,
        )
        referral = complete_referral(
            object_manager_bitrix_id="18",
        )

        first = delivery.deliver(referral)
        second = delivery.deliver(referral)

        self.assertEqual(first.status, "sent_private_max_id_missing")
        self.assertEqual(second.status, "duplicate")
        self.assertEqual(len(max_client.sent), 1)
        self.assertEqual(max_client.private_sent[0][0], "999")
        self.assertIn(
            "Сообщение в общую группу отправлено.",
            max_client.private_sent[0][1],
        )

    def test_failed_private_send_retries_without_repeating_group(self):
        max_client = FakeMax(private_fail=True)
        delivery = ReferralDelivery(
            ReferralProcessor(self.journal),
            self.journal,
            max_client,
            private_delivery_enabled=True,
            admin_max_user_id="999",
            manager_registry=self.registry,
        )
        referral = complete_referral(
            object_manager_bitrix_id="17",
        )

        first = delivery.deliver(referral)
        max_client.private_fail = False
        second = delivery.deliver(referral)

        self.assertEqual(first.status, "private_send_failed")
        self.assertEqual(second.status, "sent_with_private")
        self.assertEqual(len(max_client.sent), 1)
        self.assertEqual(
            [recipient for recipient, _ in max_client.private_sent],
            ["777", "999", "777"],
        )

    def test_primary_and_additional_managers_receive_once_each(self):
        self.registry.register(
            RegisteredManager(
                "778",
                "Пётр",
                "Петров",
                "petr",
                101,
                bitrix_user_id="18",
            )
        )
        max_client = FakeMax()
        delivery = ReferralDelivery(
            ReferralProcessor(self.journal),
            self.journal,
            max_client,
            private_delivery_enabled=True,
            admin_max_user_id="999",
            manager_registry=self.registry,
        )
        referral = complete_referral(
            object_manager_bitrix_id="17",
            additional_manager_bitrix_ids=("18", "17", "18"),
        )

        result = delivery.deliver(referral)

        self.assertEqual(result.status, "sent_with_private")
        recipients = [
            recipient for recipient, _ in max_client.private_sent
        ]
        self.assertEqual(recipients, ["777", "778"])
        self.assertEqual(len(max_client.sent), 1)

        duplicate = delivery.deliver(referral)
        self.assertEqual(duplicate.status, "duplicate")
        self.assertEqual(
            [recipient for recipient, _ in max_client.private_sent],
            ["777", "778"],
        )
