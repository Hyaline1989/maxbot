"""Безопасные настройки и подтверждённые коды полей Битрикс24."""

from dataclasses import dataclass
from pathlib import Path
import os


CONFIRMED_DEAL_FIELDS = {
    "candidate_title": "TITLE",
    "directed_at": "UF_CRM_1684488775220",
    "planned_arrival": "UF_CRM_622F3E04D997E",
    "call_center_employee": "UF_CRM_68F1ED4DB3EE8",
    "object_name": "UF_CRM_642A972B79B02",
    "contact_id": "CONTACT_ID",
}

CONFIRMED_CONTACT_FIELDS = {
    "last_name": "LAST_NAME",
    "name": "NAME",
    "second_name": "SECOND_NAME",
    "birth_date": "BIRTHDATE",
    "phones": "PHONE",
}

# Обратная совместимость для раннего кода, использовавшего это имя.
CONFIRMED_BITRIX_FIELDS = CONFIRMED_DEAL_FIELDS

BITRIX_DEAL_CATEGORY_ID = "0"
BITRIX_DEAL_CATEGORY_NAME = "Вахта"
BITRIX_INTERVIEW_STAGE_ID = "NEW"
BITRIX_INTERVIEW_STAGE_NAME = "Назначено собеседование"
BITRIX_DIRECTED_STAGE_ID = "3"
BITRIX_DIRECTED_STAGE_NAME = "Направлен на объект"


@dataclass(frozen=True, slots=True)
class Settings:
    journal_path: Path
    bitrix_webhook_base_url: str | None
    bitrix_event_token: str | None
    bitrix_event_domain: str
    bitrix_portal_url: str
    bitrix_allowed_deal_ids: frozenset[str]
    bitrix_discover_funnel_deals: bool
    bitrix_additional_object_managers_field: str | None
    max_bot_token: str | None
    max_chat_id: str | None
    max_api_base_url: str
    max_sending_enabled: bool
    max_webhook_secret: str | None
    max_registry_path: Path
    max_admin_user_id: str | None
    max_private_delivery_enabled: bool

    @classmethod
    def from_environment(cls) -> "Settings":
        return cls(
            journal_path=Path(
                os.getenv("JOURNAL_PATH", "data/test_journal.sqlite3")
            ),
            bitrix_webhook_base_url=os.getenv("BITRIX_WEBHOOK_BASE_URL") or None,
            bitrix_event_token=os.getenv("BITRIX_EVENT_TOKEN") or None,
            bitrix_event_domain=os.getenv(
                "BITRIX_EVENT_DOMAIN",
                "crm.complect.org",
            ),
            bitrix_portal_url=os.getenv(
                "BITRIX_PORTAL_URL",
                "https://crm.complect.org",
            ).rstrip("/"),
            bitrix_allowed_deal_ids=frozenset(
                item.strip()
                for item in os.getenv(
                    "BITRIX_ALLOWED_DEAL_IDS",
                    "43528",
                ).split(",")
                if item.strip()
            ),
            bitrix_discover_funnel_deals=os.getenv(
                "BITRIX_DISCOVER_FUNNEL_DEALS", "false"
            ).lower() in {"1", "true", "yes"},
            bitrix_additional_object_managers_field=(
                os.getenv("BITRIX_ADDITIONAL_OBJECT_MANAGERS_FIELD") or None
            ),
            max_bot_token=os.getenv("MAX_BOT_TOKEN") or None,
            max_chat_id=os.getenv("MAX_CHAT_ID") or None,
            max_api_base_url=os.getenv(
                "MAX_API_BASE_URL",
                "https://platform-api2.max.ru",
            ).rstrip("/"),
            max_sending_enabled=os.getenv(
                "MAX_SENDING_ENABLED", "false"
            ).lower() in {"1", "true", "yes"},
            max_webhook_secret=os.getenv("MAX_WEBHOOK_SECRET") or None,
            max_registry_path=Path(
                os.getenv(
                    "MAX_REGISTRY_PATH",
                    "data/max_registry.sqlite3",
                )
            ),
            max_admin_user_id=os.getenv("MAX_ADMIN_USER_ID") or None,
            max_private_delivery_enabled=os.getenv(
                "MAX_PRIVATE_DELIVERY_ENABLED", "false"
            ).lower() in {"1", "true", "yes"},
        )

    @property
    def external_connections_configured(self) -> bool:
        return all(
            (
                self.bitrix_webhook_base_url,
                self.bitrix_event_token,
                self.max_bot_token,
                self.max_chat_id,
            )
        )
