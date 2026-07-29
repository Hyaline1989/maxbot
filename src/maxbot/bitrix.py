"""Безопасное чтение разрешённых сделок Битрикс24."""

from collections.abc import Callable, Mapping
from datetime import datetime
import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .config import BITRIX_DEAL_CATEGORY_ID, BITRIX_DIRECTED_STAGE_ID
from .models import Referral


class BitrixReadError(RuntimeError):
    """Ошибка чтения без раскрытия секретного URL."""


class DealNotAllowedError(BitrixReadError):
    """Попытка прочитать сделку вне разрешённого списка."""


class RelatedEntityNotAllowedError(BitrixReadError):
    """Контакт или компания не связаны с разрешённой сделкой."""


class UnexpectedCategoryError(BitrixReadError):
    """Сделка находится не в подтверждённой воронке."""


class UnexpectedStageError(BitrixReadError):
    """Сделка уже не находится в стадии направления."""


JsonObject = dict[str, Any]
Transport = Callable[[str, Mapping[str, str]], JsonObject]


class BitrixReadClient:
    """Минимальный клиент, в котором нет методов записи."""

    def __init__(
        self,
        webhook_base_url: str,
        *,
        allowed_deal_ids: set[str],
        discover_funnel_deals: bool = False,
        transport: Transport | None = None,
        timeout_seconds: float = 15.0,
    ) -> None:
        if not webhook_base_url.strip():
            raise ValueError("Не указан адрес вебхука Битрикс24.")
        self._base_url = webhook_base_url.rstrip("/") + "/"
        self._allowed_deal_ids = {str(value) for value in allowed_deal_ids}
        self._discover_funnel_deals = discover_funnel_deals
        self._allowed_contact_ids: set[str] = set()
        self._allowed_company_ids: set[str] = set()
        self._timeout_seconds = timeout_seconds
        self._transport = transport or self._request

    def get_deal(self, deal_id: str) -> JsonObject:
        normalized_id = str(deal_id)
        if normalized_id not in self._allowed_deal_ids:
            raise DealNotAllowedError(
                f"Чтение сделки {normalized_id} не разрешено."
            )
        deal = self._call("crm.deal.get", {"id": normalized_id})
        contact_id = _text(deal.get("CONTACT_ID"))
        company_id = _crm_identifier(deal.get("UF_CRM_642A972B79B02"))
        if contact_id:
            self._allowed_contact_ids.add(contact_id)
        if company_id:
            self._allowed_company_ids.add(company_id)
        return deal

    def get_contact(self, contact_id: str) -> JsonObject:
        normalized_id = str(contact_id)
        if normalized_id not in self._allowed_contact_ids:
            raise RelatedEntityNotAllowedError(
                "Чтение этого контакта не разрешено."
            )
        return self._call("crm.contact.get", {"id": normalized_id})

    def get_company(self, company_id: str) -> JsonObject:
        normalized_id = str(company_id)
        if normalized_id not in self._allowed_company_ids:
            raise RelatedEntityNotAllowedError(
                "Чтение этой компании не разрешено."
            )
        company = self._call("crm.company.get", {"id": normalized_id})
        return company

    def list_recent_target_stage_deals(
        self,
        moved_since: datetime,
    ) -> list[JsonObject]:
        """Читает сделки, недавно вошедшие в нужную стадию."""

        parameters: dict[str, str] = {
            "filter[>=MOVED_TIME]": moved_since.isoformat(),
            "filter[CATEGORY_ID]": BITRIX_DEAL_CATEGORY_ID,
            "filter[STAGE_ID]": BITRIX_DIRECTED_STAGE_ID,
            "order[MOVED_TIME]": "ASC",
            "order[ID]": "ASC",
            "select[0]": "ID",
            "select[1]": "MOVED_TIME",
            "select[2]": "CATEGORY_ID",
            "select[3]": "STAGE_ID",
        }
        # В тестовом режиме API даже не возвращает сведения о других сделках.
        if not self._discover_funnel_deals and len(self._allowed_deal_ids) == 1:
            parameters["filter[ID]"] = next(iter(self._allowed_deal_ids))
        elif not self._discover_funnel_deals and self._allowed_deal_ids:
            for index, deal_id in enumerate(sorted(self._allowed_deal_ids)):
                parameters[f"filter[ID][{index}]"] = deal_id

        rows: list[JsonObject] = []
        start = "0"
        seen_pages: set[str] = set()
        for _ in range(10_000):
            if start in seen_pages:
                raise BitrixReadError(
                    "Битрикс24 повторил указатель страницы сделок."
                )
            seen_pages.add(start)
            page_parameters = dict(parameters)
            page_parameters["start"] = start
            response = self._transport("crm.deal.list", page_parameters)
            if response.get("error"):
                description = (
                    response.get("error_description") or response["error"]
                )
                raise BitrixReadError(
                    f"Битрикс24 вернул ошибку: {description}"
                )
            result = response.get("result")
            if not isinstance(result, list):
                raise BitrixReadError(
                    "Битрикс24 вернул список сделок неожиданного формата."
                )
            safe_rows = [
                item
                for item in result
                if isinstance(item, dict)
                and _text(item.get("CATEGORY_ID")) == BITRIX_DEAL_CATEGORY_ID
                and _text(item.get("STAGE_ID")) == BITRIX_DIRECTED_STAGE_ID
            ]
            if self._discover_funnel_deals:
                self._allowed_deal_ids.update(
                    _text(item.get("ID"))
                    for item in safe_rows
                    if _text(item.get("ID"))
                )
            rows.extend(safe_rows)
            next_page = response.get("next")
            if next_page is None:
                return rows
            start = str(next_page)
        raise BitrixReadError(
            "Битрикс24 вернул более 10 000 страниц сделок."
        )

    def _call(self, method: str, parameters: Mapping[str, str]) -> JsonObject:
        response = self._transport(method, parameters)
        if response.get("error"):
            description = response.get("error_description") or response["error"]
            raise BitrixReadError(f"Битрикс24 вернул ошибку: {description}")
        result = response.get("result")
        if not isinstance(result, dict):
            raise BitrixReadError("Битрикс24 вернул ответ неожиданного формата.")
        return result

    def _request(
        self,
        method: str,
        parameters: Mapping[str, str],
    ) -> JsonObject:
        url = f"{self._base_url}{method}.json?{urlencode(parameters)}"
        request = Request(
            url,
            method="GET",
            headers={"Accept": "application/json"},
        )
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                payload = json.load(response)
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as error:
            raise BitrixReadError(
                "Не удалось безопасно прочитать данные из Битрикс24."
            ) from error
        if not isinstance(payload, dict):
            raise BitrixReadError("Битрикс24 вернул ответ неожиданного формата.")
        return payload


class BitrixReferralReader:
    """Собирает внутреннюю модель из сделки, контакта и объекта."""

    def __init__(
        self,
        client: BitrixReadClient,
        portal_url: str,
        *,
        additional_managers_field: str | None = None,
    ) -> None:
        self.client = client
        self.portal_url = portal_url.rstrip("/")
        self.additional_managers_field = (
            additional_managers_field or ""
        ).strip()

    def read(self, deal_id: str) -> Referral:
        deal = self.client.get_deal(deal_id)
        category_id = _text(deal.get("CATEGORY_ID"))
        if category_id != BITRIX_DEAL_CATEGORY_ID:
            raise UnexpectedCategoryError(
                "Сделка находится не в воронке «Вахта»."
            )
        if _text(deal.get("STAGE_ID")) != BITRIX_DIRECTED_STAGE_ID:
            raise UnexpectedStageError(
                "Сделка уже не находится в стадии «Направлен на объект»."
            )

        contact_id = _text(deal.get("CONTACT_ID"))
        contact = self.client.get_contact(contact_id) if contact_id else {}

        company_id = _crm_identifier(deal.get("UF_CRM_642A972B79B02"))
        company = self.client.get_company(company_id) if company_id else {}
        object_manager_id = _text(company.get("ASSIGNED_BY_ID"))
        additional_manager_ids = _user_identifiers(
            company.get(self.additional_managers_field)
            if self.additional_managers_field
            else None
        )

        return Referral(
            deal_id=_text(deal.get("ID")) or str(deal_id),
            created_at=_stable_datetime(deal.get("DATE_CREATE")),
            candidate_title=_text(deal.get("TITLE")),
            full_name=_full_name(contact),
            birth_date=_iso_date(contact.get("BIRTHDATE")),
            phone=_first_phone(contact.get("PHONE")),
            object_name=_text(company.get("TITLE")),
            manager_name=_text(deal.get("UF_CRM_68F1ED4DB3EE8")),
            directed_at=_stable_datetime(deal.get("UF_CRM_1684488775220")),
            planned_arrival=_display_date(
                deal.get("UF_CRM_622F3E04D997E")
            ),
            planned_arrival_at=_display_datetime(
                deal.get("UF_CRM_622F3E04D997E")
            ),
            object_manager_bitrix_id=object_manager_id,
            additional_manager_bitrix_ids=additional_manager_ids,
            deal_url=f"{self.portal_url}/crm/deal/details/{deal_id}/",
        )


def _text(value: object) -> str:
    return "" if value is None else str(value).strip()


def _crm_identifier(value: object) -> str:
    if isinstance(value, list):
        value = value[0] if value else ""
    text = _text(value)
    return text.rsplit("_", 1)[-1] if "_" in text else text


def _user_identifiers(value: object) -> tuple[str, ...]:
    values = value if isinstance(value, list) else [value]
    result: list[str] = []
    for item in values:
        if item is None or item is False:
            continue
        identifier = _text(item)
        if identifier.casefold() in {"", "0", "false", "n", "no"}:
            continue
        if identifier and identifier not in result:
            result.append(identifier)
    return tuple(result)


def _full_name(contact: Mapping[str, object]) -> str:
    result: list[str] = []
    seen: set[str] = set()
    for field in ("LAST_NAME", "NAME", "SECOND_NAME"):
        part = _text(contact.get(field))
        normalized = part.casefold()
        if part and normalized not in seen:
            result.append(part)
            seen.add(normalized)
    return " ".join(result)


def _first_phone(value: object) -> str:
    if not isinstance(value, list):
        return ""
    for item in value:
        if isinstance(item, Mapping):
            phone = _text(item.get("VALUE"))
            if phone:
                return phone
    return ""


def _parse_bitrix_datetime(value: object) -> datetime | None:
    text = _text(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        pass
    for pattern in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(text[:10], pattern)
        except ValueError:
            continue
    return None


def _display_date(value: object) -> str:
    parsed = _parse_bitrix_datetime(value)
    return parsed.strftime("%d.%m.%Y") if parsed else _text(value)


def _display_datetime(value: object) -> str:
    parsed = _parse_bitrix_datetime(value)
    if not parsed:
        return _text(value)
    if parsed.hour == 0 and parsed.minute == 0:
        return parsed.strftime("%d.%m.%Y")
    return parsed.strftime("%d.%m.%Y %H:%M")


def _iso_date(value: object) -> str:
    parsed = _parse_bitrix_datetime(value)
    return parsed.strftime("%Y-%m-%d") if parsed else _text(value)


def _stable_datetime(value: object) -> str:
    parsed = _parse_bitrix_datetime(value)
    return parsed.isoformat() if parsed else _text(value)
