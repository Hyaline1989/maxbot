"""Тестовый процесс опроса Битрикс24 без отправки сообщений."""

import json
import signal
import time

from .bitrix import BitrixReadClient, BitrixReferralReader
from .config import Settings
from .delivery import ReferralDelivery
from .journal import SQLiteJournal
from .max_api import MaxClient
from .max_registry import MaxManagerRegistry
from .polling import DealPollingRunner
from .service import ReferralProcessor
from .validation import missing_fields


POLL_INTERVAL_SECONDS = 10


def main() -> int:
    settings = Settings.from_environment()
    if not settings.bitrix_webhook_base_url:
        print(
            json.dumps(
                {"status": "stopped", "reason": "bitrix_not_configured"}
            ),
            flush=True,
        )
        return 2
    if (
        not settings.bitrix_allowed_deal_ids
        and not settings.bitrix_discover_funnel_deals
    ):
        print(
            json.dumps(
                {"status": "stopped", "reason": "no_allowed_deals"}
            ),
            flush=True,
        )
        return 2

    client = BitrixReadClient(
        settings.bitrix_webhook_base_url,
        allowed_deal_ids=set(settings.bitrix_allowed_deal_ids),
        discover_funnel_deals=settings.bitrix_discover_funnel_deals,
    )
    reader = BitrixReferralReader(
        client,
        settings.bitrix_portal_url,
        additional_managers_field=(
            settings.bitrix_additional_object_managers_field
        ),
    )
    delivery = None
    if settings.max_sending_enabled:
        if not settings.max_bot_token or not settings.max_chat_id:
            print(
                json.dumps(
                    {"status": "stopped", "reason": "max_not_configured"}
                ),
                flush=True,
            )
            return 2
        journal = SQLiteJournal(settings.journal_path)
        journal.initialize()
        manager_registry = MaxManagerRegistry(settings.max_registry_path)
        manager_registry.initialize()
        delivery = ReferralDelivery(
            ReferralProcessor(journal),
            journal,
            MaxClient(
                settings.max_bot_token,
                settings.max_chat_id,
                base_url=settings.max_api_base_url,
            ),
            private_delivery_enabled=settings.max_private_delivery_enabled,
            admin_max_user_id=settings.max_admin_user_id,
            manager_registry=manager_registry,
        )

    def inspect_deal(deal_id: str, event_key: str) -> bool:
        referral = reader.read(deal_id)
        if delivery is not None:
            result = delivery.deliver(referral, event_key=event_key)
            print(
                json.dumps(
                    {"status": result.status, "deal_id": deal_id}
                ),
                flush=True,
            )
            return result.status not in {"send_failed", "private_send_failed"}
        missing = missing_fields(referral)
        status = (
            "ignored_not_directed"
            if not referral.directed_at
            else "validation_error_ready"
            if missing
            else "ready_for_test_processing"
        )
        # Никаких ФИО, телефонов, дат и текстов сообщений в stdout.
        print(
            json.dumps(
                {
                    "status": status,
                    "deal_id": deal_id,
                    "missing_count": len(missing),
                }
            ),
            flush=True,
        )
        return True

    runner = DealPollingRunner(client, inspect_deal)
    stopping = False

    def request_stop(signum: int, frame: object) -> None:
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    print(
        json.dumps(
            {
                "status": "poller_started",
                "interval_seconds": POLL_INTERVAL_SECONDS,
                "allowed_deal_count": len(settings.bitrix_allowed_deal_ids),
                "discover_funnel_deals": settings.bitrix_discover_funnel_deals,
                "max_sending_enabled": settings.max_sending_enabled,
                "private_delivery_enabled": bool(
                    settings.max_private_delivery_enabled
                ),
            }
        ),
        flush=True,
    )
    while not stopping:
        try:
            result = runner.poll_once()
            print(
                json.dumps(
                    {
                        "status": "poll_complete",
                        "checked_count": result.checked_count,
                        "matched_count": result.matched_count,
                    }
                ),
                flush=True,
            )
        except Exception:
            # Не печатать исключение: оно может содержать служебные сведения.
            print(json.dumps({"status": "poll_failed"}), flush=True)
        for _ in range(POLL_INTERVAL_SECONDS):
            if stopping:
                break
            time.sleep(1)
    print(json.dumps({"status": "poller_stopped"}), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
