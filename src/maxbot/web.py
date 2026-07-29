"""Небольшое WSGI-приложение для FastPanel и Gunicorn."""

from collections.abc import Callable, Iterable, Mapping
import json
from types import TracebackType
from typing import Any
from urllib.parse import parse_qs

from .bitrix import BitrixReadClient, BitrixReferralReader
from .config import Settings
from .events import InvalidBitrixEvent, parse_deal_update_event
from .models import Referral
from .max_api import MaxApiError, MaxClient
from .max_registry import MaxManagerRegistry, RegisteredManager
from .validation import missing_fields


MAX_REQUEST_BYTES = 64 * 1024
StartResponse = Callable[
    [str, list[tuple[str, str]], TracebackType | None],
    Callable[[bytes], Any],
]
ReferralLoader = Callable[[str], Referral]


def create_app(
    settings: Settings | None = None,
    *,
    referral_loader: ReferralLoader | None = None,
    max_registry: MaxManagerRegistry | None = None,
    max_client: MaxClient | None = None,
) -> Callable[[Mapping[str, Any], StartResponse], Iterable[bytes]]:
    configured_settings = settings or Settings.from_environment()

    def application(
        environ: Mapping[str, Any],
        start_response: StartResponse,
    ) -> Iterable[bytes]:
        method = str(environ.get("REQUEST_METHOD", "GET")).upper()
        path = str(environ.get("PATH_INFO", "/"))

        if method == "GET" and path == "/health":
            return _json_response(
                start_response,
                "200 OK",
                {"status": "ok"},
            )

        if method == "POST" and path == "/max/event":
            return _handle_max_event(
                environ,
                start_response,
                configured_settings,
                max_registry=max_registry,
                max_client=max_client,
            )

        if method != "POST" or path != "/bitrix/event":
            return _json_response(
                start_response,
                "404 Not Found",
                {"status": "not_found"},
            )

        if (
            not configured_settings.bitrix_event_token
            or not configured_settings.bitrix_webhook_base_url
        ):
            return _json_response(
                start_response,
                "503 Service Unavailable",
                {"status": "not_configured"},
            )

        try:
            payload = _read_payload(environ)
            event = parse_deal_update_event(
                payload,
                expected_application_token=(
                    configured_settings.bitrix_event_token
                ),
                expected_domain=configured_settings.bitrix_event_domain,
            )
        except (InvalidBitrixEvent, ValueError):
            return _json_response(
                start_response,
                "403 Forbidden",
                {"status": "rejected"},
            )

        if event.deal_id not in configured_settings.bitrix_allowed_deal_ids:
            return _json_response(
                start_response,
                "202 Accepted",
                {"status": "ignored_not_allowed"},
            )

        loader = referral_loader or _default_loader(configured_settings)
        try:
            referral = loader(event.deal_id)
        except Exception:
            # Ответ не раскрывает URL вебхука, ID связанных сущностей и данные.
            return _json_response(
                start_response,
                "502 Bad Gateway",
                {"status": "read_failed"},
            )

        missing = missing_fields(referral)
        if not referral.directed_at:
            return _json_response(
                start_response,
                "200 OK",
                {"status": "ignored_not_directed"},
            )
        if missing:
            return _json_response(
                start_response,
                "200 OK",
                {
                    "status": "validation_error_ready",
                    "missing_count": len(missing),
                },
            )
        return _json_response(
            start_response,
            "200 OK",
            {"status": "ready_for_test_processing"},
        )

    return application


def _default_loader(settings: Settings) -> ReferralLoader:
    def load(deal_id: str) -> Referral:
        client = BitrixReadClient(
            settings.bitrix_webhook_base_url or "",
            allowed_deal_ids={deal_id},
        )
        reader = BitrixReferralReader(client, settings.bitrix_portal_url)
        return reader.read(deal_id)

    return load


def _read_payload(environ: Mapping[str, Any]) -> dict[str, object]:
    length_text = str(environ.get("CONTENT_LENGTH") or "0")
    try:
        length = int(length_text)
    except ValueError as error:
        raise ValueError("Некорректный размер запроса.") from error
    if length < 0 or length > MAX_REQUEST_BYTES:
        raise ValueError("Слишком большой запрос.")

    stream = environ.get("wsgi.input")
    body = stream.read(length) if stream is not None and length else b""
    content_type = str(environ.get("CONTENT_TYPE", "")).lower()
    if "application/json" in content_type:
        payload = json.loads(body.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Ожидался JSON-объект.")
        return payload

    parsed = parse_qs(
        body.decode("utf-8"),
        keep_blank_values=True,
        strict_parsing=False,
    )
    return {key: values[-1] if values else "" for key, values in parsed.items()}


def _json_response(
    start_response: StartResponse,
    status: str,
    payload: Mapping[str, object],
) -> list[bytes]:
    body = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    start_response(
        status,
        [
            ("Content-Type", "application/json; charset=utf-8"),
            ("Content-Length", str(len(body))),
            ("Cache-Control", "no-store"),
            ("X-Content-Type-Options", "nosniff"),
        ],
        None,
    )
    return [body]


application = create_app()


def _handle_max_event(
    environ: Mapping[str, Any],
    start_response: StartResponse,
    settings: Settings,
    *,
    max_registry: MaxManagerRegistry | None,
    max_client: MaxClient | None,
) -> list[bytes]:
    secret = getattr(settings, "max_webhook_secret", None)
    received_secret = str(
        environ.get("HTTP_X_MAX_BOT_API_SECRET", "")
    )
    if not secret or received_secret != secret:
        return _json_response(
            start_response,
            "403 Forbidden",
            {"status": "rejected"},
        )
    try:
        payload = _read_payload(environ)
    except (ValueError, json.JSONDecodeError):
        return _json_response(
            start_response,
            "400 Bad Request",
            {"status": "invalid_payload"},
        )
    if payload.get("update_type") != "bot_started":
        return _json_response(
            start_response,
            "200 OK",
            {"status": "ignored"},
        )
    user = payload.get("user")
    if not isinstance(user, dict):
        return _json_response(
            start_response,
            "400 Bad Request",
            {"status": "missing_user"},
        )
    user_id = str(user.get("user_id") or "").strip()
    if not user_id:
        return _json_response(
            start_response,
            "400 Bad Request",
            {"status": "missing_user_id"},
        )
    registry = max_registry or MaxManagerRegistry(
        getattr(settings, "max_registry_path")
    )
    registered = registry.register(
        RegisteredManager(
            user_id=user_id,
            first_name=str(user.get("first_name") or "").strip(),
            last_name=str(user.get("last_name") or "").strip(),
            username=str(user.get("username") or "").strip(),
            registered_at=int(payload.get("timestamp") or 0),
        )
    )
    client = max_client or MaxClient(
        getattr(settings, "max_bot_token") or "",
        getattr(settings, "max_chat_id") or "",
        base_url=getattr(settings, "max_api_base_url"),
    )
    try:
        client.send_text_to_user(
            user_id,
            "Регистрация завершена.\n"
            f"Ваш код привязки: {registered.binding_code}\n"
            "Передайте этот код администратору.",
        )
    except MaxApiError:
        return _json_response(
            start_response,
            "200 OK",
            {"status": "registered_confirmation_failed"},
        )
    return _json_response(
        start_response,
        "200 OK",
        {"status": "registered"},
    )
