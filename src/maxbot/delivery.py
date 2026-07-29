"""Надёжная отправка подготовленного уведомления в MAX."""

from dataclasses import dataclass

from .journal import PrivateDeliveryEntry, SQLiteJournal
from .max_api import MaxApiError, MaxClient
from .max_registry import MaxManagerRegistry
from .messages import (
    build_private_delivery_error,
    build_private_referral_message,
)
from .models import Referral
from .service import ReferralProcessor


@dataclass(frozen=True, slots=True)
class DeliveryResult:
    status: str
    max_message_id: str | None = None


class ReferralDelivery:
    def __init__(
        self,
        processor: ReferralProcessor,
        journal: SQLiteJournal,
        max_client: MaxClient,
        *,
        private_delivery_enabled: bool = False,
        admin_max_user_id: str | None = None,
        manager_registry: MaxManagerRegistry | None = None,
    ) -> None:
        self.processor = processor
        self.journal = journal
        self.max_client = max_client
        self.private_delivery_enabled = private_delivery_enabled
        self.admin_max_user_id = (admin_max_user_id or "").strip()
        self.manager_registry = manager_registry

    def deliver(
        self,
        referral: Referral,
        *,
        event_key: str = "stage:3",
    ) -> DeliveryResult:
        prepared = self.processor.process(
            referral,
            retry_existing=True,
            event_key=event_key,
        )
        if prepared.status == "duplicate":
            entry = self.journal.get(referral.deal_id, event_key)
            if (
                self.private_delivery_enabled
                and entry
                and entry.status == "sent"
            ):
                return self._deliver_private(referral, event_key)
            return DeliveryResult("duplicate")
        if not prepared.message or not referral.deal_id or not event_key:
            return DeliveryResult("not_sendable")

        is_validation_error = prepared.status.startswith("validation_error")
        try:
            message_id = self.max_client.send_text(prepared.message)
        except MaxApiError:
            self.journal.update_delivery(
                referral.deal_id,
                event_key,
                status=(
                    "validation_error_send_failed"
                    if is_validation_error
                    else "send_failed"
                ),
                error_description="temporary_max_error",
            )
            return DeliveryResult("send_failed")

        status = "validation_error_sent" if is_validation_error else "sent"
        self.journal.update_delivery(
            referral.deal_id,
            event_key,
            status=status,
            max_message_id=message_id,
        )
        if not is_validation_error and self.private_delivery_enabled:
            return self._deliver_private(referral, event_key)
        return DeliveryResult(status, message_id)

    def _deliver_private(
        self,
        referral: Referral,
        event_key: str,
    ) -> DeliveryResult:
        bitrix_user_ids = _unique_nonempty(
            (
                referral.object_manager_bitrix_id,
                *referral.additional_manager_bitrix_ids,
            )
        )
        if not bitrix_user_ids:
            missing_key = "__manager_missing__"
            existing = self.journal.get_private_delivery(
                referral.deal_id,
                event_key,
                missing_key,
            )
            if not existing:
                self.journal.upsert_private_delivery(
                    PrivateDeliveryEntry(
                        referral.deal_id,
                        event_key,
                        missing_key,
                        None,
                        "manager_missing",
                        error_description="manager_missing",
                    )
                )
                self._notify_admin(
                    referral,
                    "в карточке объекта не указан ответственный",
                )
                return DeliveryResult("sent_private_manager_missing")
            return DeliveryResult("duplicate")

        sent_count = 0
        newly_sent_count = 0
        unavailable_count = 0
        newly_unavailable_count = 0
        failed_count = 0
        last_message_id: str | None = None
        for bitrix_user_id in bitrix_user_ids:
            existing = self.journal.get_private_delivery(
                referral.deal_id,
                event_key,
                bitrix_user_id,
            )
            if existing and existing.status == "sent":
                sent_count += 1
                continue
            if existing and existing.status == "max_id_missing":
                unavailable_count += 1
                continue

            manager = (
                self.manager_registry.get_by_bitrix_user_id(bitrix_user_id)
                if self.manager_registry
                else None
            )
            recipient_id = manager.user_id if manager else ""
            if not recipient_id:
                self.journal.upsert_private_delivery(
                    PrivateDeliveryEntry(
                        referral.deal_id,
                        event_key,
                        bitrix_user_id,
                        None,
                        "max_id_missing",
                        error_description="max_id_missing",
                    )
                )
                if not existing:
                    self._notify_admin(
                        referral,
                        "один из менеджеров объекта ещё не связан "
                        "с зарегистрированным пользователем MAX",
                    )
                unavailable_count += 1
                newly_unavailable_count += 1
                continue

            try:
                message_id = self.max_client.send_text_to_user(
                    recipient_id,
                    build_private_referral_message(referral),
                )
            except MaxApiError:
                self.journal.upsert_private_delivery(
                    PrivateDeliveryEntry(
                        referral.deal_id,
                        event_key,
                        bitrix_user_id,
                        recipient_id,
                        "send_failed",
                        error_description="temporary_private_max_error",
                    )
                )
                if not existing:
                    self._notify_admin(
                        referral,
                        "MAX временно не принял одно из личных сообщений",
                    )
                failed_count += 1
                continue

            self.journal.upsert_private_delivery(
                PrivateDeliveryEntry(
                    referral.deal_id,
                    event_key,
                    bitrix_user_id,
                    recipient_id,
                    "sent",
                    max_message_id=message_id,
                )
            )
            sent_count += 1
            newly_sent_count += 1
            last_message_id = message_id

        if failed_count:
            return DeliveryResult("private_send_failed")
        if newly_sent_count:
            return DeliveryResult("sent_with_private", last_message_id)
        if newly_unavailable_count:
            return DeliveryResult("sent_private_max_id_missing")
        if sent_count or unavailable_count:
            return DeliveryResult("duplicate")
        return DeliveryResult("duplicate")

    def _notify_admin(self, referral: Referral, reason: str) -> None:
        if not self.admin_max_user_id:
            return
        try:
            self.max_client.send_text_to_user(
                self.admin_max_user_id,
                build_private_delivery_error(referral, reason),
            )
        except MaxApiError:
            # Групповое сообщение уже отправлено; его нельзя дублировать.
            return


def _unique_nonempty(values: tuple[str, ...]) -> tuple[str, ...]:
    result: list[str] = []
    for value in values:
        normalized = str(value).strip()
        if normalized and normalized not in result:
            result.append(normalized)
    return tuple(result)
