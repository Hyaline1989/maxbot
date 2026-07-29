from io import BytesIO
import json
from types import SimpleNamespace
import unittest
from urllib.parse import urlencode

from maxbot.models import Referral
from maxbot.web import create_app
from maxbot.max_registry import MaxManagerRegistry
from tests.test_max_registry import FakeDirectClient


def test_settings() -> SimpleNamespace:
    return SimpleNamespace(
        bitrix_event_token="event-token",
        bitrix_webhook_base_url="https://example.invalid/rest/test/",
        bitrix_event_domain="crm.example.invalid",
        bitrix_portal_url="https://crm.example.invalid",
        bitrix_allowed_deal_ids=frozenset({"43528"}),
        max_webhook_secret="webhook-secret",
    )


def complete_referral(**changes: str) -> Referral:
    values = {
        "deal_id": "43528",
        "candidate_title": "Иванов Алексей Петрович",
        "full_name": "Иванов Алексей Петрович",
        "birth_date": "01.01.1990",
        "phone": "+7 900 000-00-00",
        "object_name": "Тестовый объект",
        "manager_name": "Тестовый менеджер",
        "directed_at": "2026-07-23T00:00:00",
        "planned_arrival": "30.07.2026",
        "deal_url": "https://example.invalid/deal/43528",
    }
    values.update(changes)
    return Referral(**values)


def call_app(
    app: object,
    *,
    method: str,
    path: str,
    payload: dict[str, object] | None = None,
    json_payload: dict[str, object] | None = None,
    max_secret: str = "",
) -> tuple[str, dict[str, object]]:
    body = b""
    content_type = ""
    if payload is not None:
        body = urlencode(payload).encode("utf-8")
        content_type = "application/x-www-form-urlencoded"
    if json_payload is not None:
        body = json.dumps(json_payload).encode("utf-8")
        content_type = "application/json"
    captured: dict[str, object] = {}

    def start_response(
        status: str,
        headers: list[tuple[str, str]],
        exc_info: object = None,
    ) -> None:
        captured["status"] = status
        captured["headers"] = headers

    environ = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "CONTENT_LENGTH": str(len(body)),
        "CONTENT_TYPE": content_type,
        "wsgi.input": BytesIO(body),
        "HTTP_X_MAX_BOT_API_SECRET": max_secret,
    }
    chunks = app(environ, start_response)  # type: ignore[operator]
    response_body = b"".join(chunks)
    return str(captured["status"]), json.loads(response_body)


def valid_event(deal_id: str = "43528") -> dict[str, object]:
    return {
        "event": "ONCRMDEALUPDATE",
        "data[FIELDS][ID]": deal_id,
        "auth[application_token]": "event-token",
        "auth[domain]": "crm.example.invalid",
    }


class WebTests(unittest.TestCase):
    def test_health_endpoint(self) -> None:
        app = create_app(test_settings(), referral_loader=complete_referral)
        status, body = call_app(app, method="GET", path="/health")

        self.assertEqual(status, "200 OK")
        self.assertEqual(body, {"status": "ok"})

    def test_valid_test_event_is_read(self) -> None:
        loaded: list[str] = []

        def loader(deal_id: str) -> Referral:
            loaded.append(deal_id)
            return complete_referral()

        app = create_app(test_settings(), referral_loader=loader)
        status, body = call_app(
            app,
            method="POST",
            path="/bitrix/event",
            payload=valid_event(),
        )

        self.assertEqual(status, "200 OK")
        self.assertEqual(body["status"], "ready_for_test_processing")
        self.assertEqual(loaded, ["43528"])

    def test_other_deal_is_ignored_without_reading(self) -> None:
        loaded: list[str] = []
        app = create_app(
            test_settings(),
            referral_loader=lambda deal_id: (
                loaded.append(deal_id) or complete_referral()
            ),
        )
        status, body = call_app(
            app,
            method="POST",
            path="/bitrix/event",
            payload=valid_event("99999"),
        )

        self.assertEqual(status, "202 Accepted")
        self.assertEqual(body["status"], "ignored_not_allowed")
        self.assertEqual(loaded, [])

    def test_not_directed_deal_is_ignored(self) -> None:
        app = create_app(
            test_settings(),
            referral_loader=lambda deal_id: complete_referral(directed_at=""),
        )
        status, body = call_app(
            app,
            method="POST",
            path="/bitrix/event",
            payload=valid_event(),
        )

        self.assertEqual(status, "200 OK")
        self.assertEqual(body["status"], "ignored_not_directed")

    def test_invalid_token_is_rejected_without_reading(self) -> None:
        payload = valid_event()
        payload["auth[application_token]"] = "wrong"
        app = create_app(test_settings(), referral_loader=complete_referral)

        status, body = call_app(
            app,
            method="POST",
            path="/bitrix/event",
            payload=payload,
        )

        self.assertEqual(status, "403 Forbidden")
        self.assertEqual(body["status"], "rejected")

    def test_max_bot_started_registers_user_and_confirms(self) -> None:
        from tempfile import TemporaryDirectory
        from pathlib import Path

        with TemporaryDirectory() as directory:
            registry = MaxManagerRegistry(
                Path(directory) / "registry.sqlite3"
            )
            client = FakeDirectClient()
            app = create_app(
                test_settings(),
                max_registry=registry,
                max_client=client,
            )
            status, body = call_app(
                app,
                method="POST",
                path="/max/event",
                json_payload={
                    "update_type": "bot_started",
                    "timestamp": 123,
                    "user": {
                        "user_id": 777,
                        "first_name": "Иван",
                        "last_name": "Иванов",
                        "username": "ivan",
                    },
                },
                max_secret="webhook-secret",
            )

            self.assertEqual(status, "200 OK")
            self.assertEqual(body["status"], "registered")
            registered = registry.get("777")
            self.assertEqual(registered.first_name, "Иван")
            self.assertRegex(registered.binding_code, r"^\d{6}$")
            self.assertEqual(client.sent[0][0], "777")
            self.assertIn(
                f"Ваш код привязки: {registered.binding_code}",
                client.sent[0][1],
            )

    def test_max_webhook_rejects_wrong_secret(self) -> None:
        app = create_app(test_settings())
        status, body = call_app(
            app,
            method="POST",
            path="/max/event",
            json_payload={"update_type": "bot_started"},
            max_secret="wrong",
        )

        self.assertEqual(status, "403 Forbidden")
        self.assertEqual(body["status"], "rejected")


if __name__ == "__main__":
    unittest.main()
