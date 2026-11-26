from datetime import datetime, timedelta, timezone
from pathlib import Path
import unittest

from twitch_autoclipper.bot import run_once
from twitch_autoclipper.config import AppConfig
from twitch_autoclipper.state import RuntimeState, format_time


UTC = timezone.utc
NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def config(enabled=True, interval=10, duration=60):
    return AppConfig(
        channel="badhai1",
        interval_minutes=interval,
        clip_duration_seconds=duration,
        enabled=enabled,
        log_level="INFO",
        state_file=Path(".state/runtime.enc"),
    )


class FakeTwitch:
    def __init__(self, stream=None):
        self.stream = stream
        self.clip_requests = []

    def get_authorized_user(self, expected_login):
        return "123", expected_login

    def get_live_stream(self, user_id):
        return self.stream

    def create_clip(self, broadcaster_id, duration, title):
        self.clip_requests.append((broadcaster_id, duration, title))
        return {
            "id": "clip123",
            "url": "https://clips.twitch.tv/clip123",
            "title": title,
            "duration": duration,
        }


class BotTests(unittest.TestCase):
    def test_offline_stream_never_requests_a_clip(self):
        state = RuntimeState(stream_id="old-stream")
        twitch = FakeTwitch(stream=None)
        saved = []
        result = run_once(config(), state, twitch, lambda: saved.append(state.to_dict()), now=NOW)
        self.assertEqual(result, "offline")
        self.assertEqual(twitch.clip_requests, [])
        self.assertIsNone(state.stream_id)
        self.assertTrue(saved)

    def test_interval_waits_from_live_stream_start(self):
        started = NOW - timedelta(minutes=9)
        twitch = FakeTwitch(
            {"id": "stream1", "type": "live", "user_id": "123", "started_at": format_time(started)}
        )
        state = RuntimeState()
        result = run_once(config(interval=10), state, twitch, lambda: None, now=NOW)
        self.assertEqual(result, "not_due")
        self.assertEqual(twitch.clip_requests, [])

    def test_five_minute_interval_becomes_due_at_five_minute_boundary(self):
        started = NOW - timedelta(minutes=5)
        twitch = FakeTwitch(
            {"id": "stream1", "type": "live", "user_id": "123", "started_at": format_time(started)}
        )
        state = RuntimeState()
        result = run_once(
            config(interval=5), state, twitch, lambda: None, now=NOW, dry_run=True
        )
        self.assertEqual(result, "dry_run_due")
        self.assertEqual(twitch.clip_requests, [])

    def test_delayed_run_skips_missed_slots_and_does_not_catch_up(self):
        started = NOW - timedelta(minutes=47)
        stream = {
            "id": "stream1",
            "type": "live",
            "user_id": "123",
            "started_at": format_time(started),
        }
        state = RuntimeState()
        first = FakeTwitch(stream)
        result = run_once(
            config(interval=5), state, first, lambda: None, now=NOW
        )
        self.assertEqual(result, "created")
        self.assertEqual(len(first.clip_requests), 1)
        self.assertEqual(state.next_due, NOW + timedelta(minutes=8))

        before_due = FakeTwitch(stream)
        result = run_once(
            config(interval=5),
            state,
            before_due,
            lambda: None,
            now=NOW + timedelta(minutes=7, seconds=59),
        )
        self.assertEqual(result, "not_due")
        self.assertEqual(before_due.clip_requests, [])

        at_due = FakeTwitch(stream)
        result = run_once(
            config(interval=5),
            state,
            at_due,
            lambda: None,
            now=NOW + timedelta(minutes=8),
        )
        self.assertEqual(result, "created")
        self.assertEqual(len(at_due.clip_requests), 1)

    def test_interval_change_rebases_legacy_state_from_last_clip(self):
        started = NOW - timedelta(minutes=30)
        stream = {
            "id": "stream1",
            "type": "live",
            "user_id": "123",
            "started_at": format_time(started),
        }
        state = RuntimeState(
            stream_id="stream1",
            stream_started_at=format_time(started),
            next_clip_due_at=format_time(NOW + timedelta(minutes=10)),
            interval_minutes=10,
            last_attempt_at=format_time(NOW - timedelta(minutes=1)),
            last_success_at=format_time(NOW - timedelta(minutes=1)),
        )
        twitch = FakeTwitch(stream)
        result = run_once(
            config(interval=5), state, twitch, lambda: None, now=NOW
        )
        self.assertEqual(result, "not_due")
        self.assertEqual(state.interval_minutes, 5)
        self.assertEqual(state.next_due, NOW + timedelta(minutes=5))
        self.assertEqual(twitch.clip_requests, [])

    def test_twenty_five_minute_interval_becomes_due_at_twenty_five(self):
        started = NOW - timedelta(minutes=25)
        twitch = FakeTwitch(
            {"id": "stream1", "type": "live", "user_id": "123", "started_at": format_time(started)}
        )
        state = RuntimeState()
        result = run_once(config(interval=25), state, twitch, lambda: None, now=NOW, dry_run=True)
        self.assertEqual(result, "dry_run_due")
        self.assertEqual(twitch.clip_requests, [])

    def test_due_interval_creates_configured_length_and_title(self):
        started = NOW - timedelta(minutes=11)
        twitch = FakeTwitch(
            {"id": "stream1", "type": "live", "user_id": "123", "started_at": format_time(started)}
        )
        state = RuntimeState()
        result = run_once(config(interval=10, duration=45), state, twitch, lambda: None, now=NOW)
        self.assertEqual(result, "created")
        self.assertEqual(twitch.clip_requests, [("123", 45, "badhai1 - Gaming Clip 001")])
        self.assertEqual(state.last_clip_id, "clip123")
        self.assertEqual(state.clip_sequence, 1)

    def test_manual_dry_run_never_requests_a_clip(self):
        started = NOW - timedelta(minutes=20)
        twitch = FakeTwitch(
            {"id": "stream1", "type": "live", "user_id": "123", "started_at": format_time(started)}
        )
        state = RuntimeState()
        result = run_once(config(), state, twitch, lambda: None, dry_run=True, now=NOW)
        self.assertEqual(result, "dry_run_due")
        self.assertEqual(twitch.clip_requests, [])
        self.assertIsNone(state.last_attempt_at)

    def test_reserved_attempt_prevents_duplicate_after_uncertain_failure(self):
        started = NOW - timedelta(minutes=20)
        stream = {
            "id": "stream1",
            "type": "live",
            "user_id": "123",
            "started_at": format_time(started),
        }
        state = RuntimeState()
        class UncertainTwitch(FakeTwitch):
            def create_clip(self, broadcaster_id, duration, title):
                self.clip_requests.append((broadcaster_id, duration, title))
                raise RuntimeError("simulated timeout after reservation")

        twitch = UncertainTwitch(stream)
        saved_states = []
        pre_request_state = []
        with self.assertRaisesRegex(RuntimeError, "simulated timeout"):
            run_once(
                config(interval=10),
                state,
                twitch,
                lambda: saved_states.append(state.last_attempt_at),
                now=NOW,
                before_clip_request=lambda: pre_request_state.append(
                    (state.last_attempt_at, state.next_clip_due_at)
                ),
            )
        self.assertEqual(len(twitch.clip_requests), 1)
        self.assertEqual(len(saved_states), 2)
        self.assertEqual(len(pre_request_state), 1)
        self.assertIsNotNone(pre_request_state[0][0])
        self.assertIsNotNone(pre_request_state[0][1])
        restarted = RuntimeState.from_dict(state.to_dict())
        next_run = FakeTwitch(stream)
        next_result = run_once(
            config(interval=10),
            restarted,
            next_run,
            lambda: None,
            now=NOW + timedelta(minutes=1),
        )
        self.assertEqual(next_result, "not_due")
        self.assertEqual(next_run.clip_requests, [])


if __name__ == "__main__":
    unittest.main()
