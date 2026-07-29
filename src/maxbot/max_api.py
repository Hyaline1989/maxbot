"""Минимальный клиент MAX API без чтения истории чата."""

from collections.abc import Callable
import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class MaxApiError(RuntimeError):
    """Безопасная ошибка MAX API без токена и содержимого сообщения."""


Transport = Callable[[str, str, dict[str, str], bytes | None], dict[str, Any]]


class MaxClient:
    def __init__(
        self,
        token: str,
        chat_id: str,
        *,
        base_url: str = "https://platform-api2.max.ru",
        transport: Transport | None = None,
        timeout_seconds: float = 15,
    ) -> None:
        if not token:
            raise ValueError("MAX token is required")
        if not chat_id:
            raise ValueError("MAX chat ID is required")
        self._token = token
        self.chat_id = chat_id
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._transport = transport or self._request

    def get_membership(self) -> dict[str, Any]:
        return self._transport(
            "GET",
            f"{self._base_url}/chats/{self.chat_id}/members/me",
            self._headers(),
            None,
        )

    def send_text(self, text: str) -> str | None:
        return self._send_text(text, {"chat_id": self.chat_id})

    def send_text_to_user(self, user_id: str, text: str) -> str | None:
        if not str(user_id).strip():
            raise ValueError("MAX user ID is required")
        return self._send_text(text, {"user_id": str(user_id)})

    def _send_text(
        self,
        text: str,
        recipient: dict[str, str],
    ) -> str | None:
        if not text.strip():
            raise ValueError("MAX message text is required")
        query = urlencode(recipient)
        response = self._transport(
            "POST",
            f"{self._base_url}/messages?{query}",
            self._headers(content_type=True),
            json.dumps({"text": text}, ensure_ascii=False).encode("utf-8"),
        )
        return _message_id(response)

    def _headers(self, *, content_type: bool = False) -> dict[str, str]:
        headers = {"Authorization": self._token}
        if content_type:
            headers["Content-Type"] = "application/json; charset=utf-8"
        return headers

    def _request(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
    ) -> dict[str, Any]:
        request = Request(url, data=body, headers=headers, method=method)
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                payload = json.load(response)
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as error:
            raise MaxApiError(
                "Не удалось выполнить безопасный запрос к MAX."
            ) from error
        if not isinstance(payload, dict):
            raise MaxApiError("MAX вернул ответ неизвестного формата.")
        return payload


def _message_id(response: dict[str, Any]) -> str | None:
    candidates = (
        response.get("message_id"),
        response.get("mid"),
        response.get("message", {}).get("body", {}).get("mid")
        if isinstance(response.get("message"), dict)
        else None,
    )
    return next((str(value) for value in candidates if value is not None), None)
