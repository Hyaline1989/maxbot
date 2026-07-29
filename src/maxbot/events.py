"""Безопасный разбор события изменения сделки Битрикс24."""

from dataclasses import dataclass
from hmac import compare_digest
from typing import Mapping


DEAL_UPDATE_EVENT = "ONCRMDEALUPDATE"


class InvalidBitrixEvent(ValueError):
    """Событие не прошло проверку и не должно обрабатываться."""


@dataclass(frozen=True, slots=True)
class DealUpdateEvent:
    deal_id: str
    event_name: str = DEAL_UPDATE_EVENT


def parse_deal_update_event(
    payload: Mapping[str, object],
    *,
    expected_application_token: str,
    expected_domain: str,
) -> DealUpdateEvent:
    """Проверяет источник события и возвращает только ID сделки.

    Секреты из ``auth`` намеренно не включаются в результат и не должны
    записываться в журнал.
    """

    event_name = _value(payload, "event").upper()
    if event_name != DEAL_UPDATE_EVENT:
        raise InvalidBitrixEvent("Получено событие другого типа.")

    application_token = _nested_value(
        payload,
        nested_key="auth",
        item_key="application_token",
        flat_keys=("auth[application_token]", "AUTH[application_token]"),
    )
    if not expected_application_token or not compare_digest(
        application_token,
        expected_application_token,
    ):
        raise InvalidBitrixEvent("Неверный защитный токен события.")

    domain = _nested_value(
        payload,
        nested_key="auth",
        item_key="domain",
        flat_keys=("auth[domain]", "AUTH[domain]"),
    ).lower()
    if domain != expected_domain.strip().lower():
        raise InvalidBitrixEvent("Событие пришло с другого портала.")

    deal_id = _deal_id(payload)
    if not deal_id or not deal_id.isdigit():
        raise InvalidBitrixEvent("В событии отсутствует корректный ID сделки.")

    return DealUpdateEvent(deal_id=deal_id)


def _deal_id(payload: Mapping[str, object]) -> str:
    data = payload.get("data")
    if isinstance(data, Mapping):
        fields = data.get("FIELDS")
        if not isinstance(fields, Mapping):
            fields = data.get("fields")
        if isinstance(fields, Mapping):
            return _text(fields.get("ID") or fields.get("id"))
    for key in (
        "data[FIELDS][ID]",
        "data[fields][id]",
        "DATA[FIELDS][ID]",
    ):
        value = _text(payload.get(key))
        if value:
            return value
    return ""


def _nested_value(
    payload: Mapping[str, object],
    *,
    nested_key: str,
    item_key: str,
    flat_keys: tuple[str, ...],
) -> str:
    nested = payload.get(nested_key)
    if not isinstance(nested, Mapping):
        nested = payload.get(nested_key.upper())
    if isinstance(nested, Mapping):
        value = _text(nested.get(item_key) or nested.get(item_key.upper()))
        if value:
            return value
    for key in flat_keys:
        value = _text(payload.get(key))
        if value:
            return value
    return ""


def _value(payload: Mapping[str, object], key: str) -> str:
    return _text(payload.get(key) or payload.get(key.upper()))


def _text(value: object) -> str:
    return "" if value is None else str(value).strip()
