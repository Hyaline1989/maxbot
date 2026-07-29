import json
import unittest

from maxbot.max_api import MaxClient


class MaxClientTests(unittest.TestCase):
    def test_membership_uses_read_only_endpoint(self) -> None:
        calls = []

        def transport(method, url, headers, body):
            calls.append((method, url, headers, body))
            return {"is_admin": True, "permissions": ["write"]}

        client = MaxClient("secret", "-123", transport=transport)

        result = client.get_membership()

        self.assertTrue(result["is_admin"])
        self.assertEqual(calls[0][0], "GET")
        self.assertEqual(
            calls[0][1],
            "https://platform-api2.max.ru/chats/-123/members/me",
        )
        self.assertEqual(calls[0][2]["Authorization"], "secret")
        self.assertIsNone(calls[0][3])

    def test_send_text_posts_utf8_json_to_selected_chat(self) -> None:
        calls = []

        def transport(method, url, headers, body):
            calls.append((method, url, headers, body))
            return {"message": {"body": {"mid": "mid-1"}}}

        client = MaxClient("secret", "-123", transport=transport)

        message_id = client.send_text("Тест")

        self.assertEqual(message_id, "mid-1")
        self.assertEqual(calls[0][0], "POST")
        self.assertEqual(
            calls[0][1],
            "https://platform-api2.max.ru/messages?chat_id=-123",
        )
        self.assertEqual(
            json.loads(calls[0][3].decode("utf-8")),
            {"text": "Тест"},
        )

    def test_empty_message_is_rejected_before_request(self) -> None:
        client = MaxClient(
            "secret",
            "-123",
            transport=lambda *args: self.fail("request must not be called"),
        )

        with self.assertRaises(ValueError):
            client.send_text(" ")

    def test_send_text_to_user_uses_user_id(self) -> None:
        calls = []

        def transport(method, url, headers, body):
            calls.append((method, url, headers, body))
            return {"message": {"body": {"mid": "direct-1"}}}

        client = MaxClient("secret", "-123", transport=transport)

        self.assertEqual(
            client.send_text_to_user("777", "Личное сообщение"),
            "direct-1",
        )
        self.assertEqual(
            calls[0][1],
            "https://platform-api2.max.ru/messages?user_id=777",
        )


if __name__ == "__main__":
    unittest.main()
