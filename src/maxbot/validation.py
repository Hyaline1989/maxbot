"""Проверка обязательных полей до подготовки уведомления."""

from .models import Referral


REQUIRED_FIELDS = {
    "deal_id": "идентификатор сделки",
    "candidate_title": "название кандидата",
    "full_name": "полное ФИО",
    "birth_date": "дата рождения",
    "phone": "телефон",
    "object_name": "объект",
    "directed_at": "дата и время направления",
    "planned_arrival": "ориентировочная дата прибытия",
    "deal_url": "ссылка на сделку",
}


def missing_fields(referral: Referral) -> list[str]:
    return [
        label
        for field_name, label in REQUIRED_FIELDS.items()
        if not getattr(referral, field_name).strip()
    ]
