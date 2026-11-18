import json
import unittest

from twitch_autoclipper.state import RuntimeState
from twitch_autoclipper.twitch import HttpReply, TwitchApiError, TwitchClient, TwitchError


def reply(status, data=None, headers=None):
    return HttpReply(
        status=status,
        headers=headers or {},
        body=json.dumps(data or {}).encode("utf-8"),
    )


class FakeTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, headers, body=None):
        self.calls.append((method, url, headers, body))
        if not self.responses:
            raise AssertionError("Unexpected HTTP request")
        return self.responses.pop(0)


class TwitchClientTests(unittest.TestCase):
    def test_expired_token_refreshes_once_and_rotated_tokens_are_saved(self):
        transport = FakeTransport(
            [
                reply(401, {"message": "invalid token"}),
                reply(200, {"access_token": "new-access", "refresh_token": "rotated-refresh"}),
                reply(200, {
                    "client_id": "client-1",
                    "login": "badhai1",
                    "user_id": "123",
                    "scopes": ["clips:edit"],
                }),
            ]
        )
        state = RuntimeState(access_token="expired", refresh_token="old-refresh")
        saved = []
        client = TwitchClient(
            "client-1", state, lambda: saved.append(state.refresh_token), transport=transport
        )
        self.assertEqual(client.get_authorized_user("badhai1"), ("123", "badhai1"))
        self.assertEqual(state.access_token, "new-access")
        self.assertEqual(state.refresh_token, "rotated-refresh")
        self.assertEqual(saved, ["rotated-refresh"])

    def test_missing_scope_is_reported_without_stream_or_clip_calls(self):
        transport = FakeTransport(
            [reply(200, {
                "client_id": "client-1",
                "login": "badhai1",
                "user_id": "123",
                "scopes": [],
            })]
        )
        client = TwitchClient("client-1", RuntimeState(access_token="valid"), lambda: None, transport)
        with self.assertRaisesRegex(TwitchError, "clips:edit"):
            client.get_authorized_user("badhai1")
        self.assertEqual(len(transport.calls), 1)

    def test_wrong_authorized_account_is_rejected(self):
        transport = FakeTransport(
            [reply(200, {
                "client_id": "client-1",
                "login": "otheruser",
                "user_id": "456",
                "scopes": ["clips:edit"],
            })]
        )
        client = TwitchClient("client-1", RuntimeState(access_token="valid"), lambda: None, transport)
        with self.assertRaisesRegex(TwitchError, "nicht badhai1"):
            client.get_authorized_user("badhai1")

    def test_forbidden_clip_request_returns_safe_http_error(self):
        transport = FakeTransport(
            [reply(403, {"message": "Clips are disabled for this channel."})]
        )
        state = RuntimeState(access_token="valid", refresh_token="refresh")
        client = TwitchClient("client-1", state, lambda: None, transport)
        with self.assertRaises(TwitchApiError) as raised:
            client.create_clip("123", 30, "safe title")
        self.assertEqual(raised.exception.status, 403)
        self.assertIn("Clips are disabled", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
