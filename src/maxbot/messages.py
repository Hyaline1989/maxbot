"""Формирование сообщений без отправки во внешние сервисы."""

from datetime import datetime

from .models import Referral


def build_private_referral_message(referral: Referral) -> str:
    arrival = referral.planned_arrival_at or referral.planned_arrival
    position = referral.position_name or "не указана"
    return (
        "🔔 НАПОМИНАНИЕ:\n"
        f"Вахтовик {referral.candidate_title} номер телефона {referral.phone} "
        f"направлен на {referral.object_name} на должность {position}, "
        f"прибудет к Вам ориентировочно "
        f"{arrival}\n\n"
        "💡 Не забудьте встретить вахтовика!"
    )


def build_private_delivery_error(
    referral: Referral,
    reason: str,
) -> str:
    return "\n".join(
        (
            "Не удалось отправить личное уведомление менеджеру объекта",
            f"Объект: {referral.object_name or 'не определён'}",
            f"Сделка: {referral.deal_url or referral.deal_id}",
            f"Причина: {reason}",
            "Сообщение в общую группу отправлено.",
        )
    )


def build_group_referral_message(referral: Referral) -> str:
    recruitment_manager = (
        referral.manager_name or "Перевахтовка/Приведи друга"
    )
    position = referral.position_name or "не указана"
    message = (
        f"Вахтовик {referral.candidate_title}, {referral.birth_date}, "
        f"номер телефона {referral.phone}, направлен на "
        f"{referral.object_name} на должность {position}, "
        f"прибудет к вам ориентировочно "
        f"{referral.planned_arrival}, сделка: {referral.deal_url}"
    )
    message += f"\nМенеджер подбора: {recruitment_manager}"
    return message


def build_referral_message(referral: Referral) -> str:
    """Совместимое имя для основного сообщения в общей группе."""
    return build_group_referral_message(referral)


def build_error_message(
    referral: Referral,
    missing: list[str],
    detected_at: datetime,
) -> str:
    deal_reference = referral.deal_url or referral.deal_id or "не определена"
    return "\n".join(
        (
            "Ошибка обработки направления",
            f"Сделка: {deal_reference}",
            f"Не заполнено: {', '.join(missing)}",
            f"Обнаружено: {detected_at:%d.%m.%Y %H:%M:%S}",
            "Уведомление о направлении не отправлено.",
            "Ответственная: Екатерина Линник",
        )
    )
