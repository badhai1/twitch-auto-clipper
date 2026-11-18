from pathlib import Path
from types import SimpleNamespace
import os
import sys
import unittest
from unittest.mock import Mock, patch

from twitch_autoclipper import __main__ as entrypoint


class EntrypointTests(unittest.TestCase):
    def setUp(self):
        self.config = SimpleNamespace(
            enabled=False,
            log_level="INFO",
            state_file=Path(".state/runtime.enc"),
        )

    @patch.dict(
        os.environ,
        {
            "DRY_RUN": "true",
            "TWITCH_CLIENT_ID": "test-client-id",
            "TWITCH_REFRESH_TOKEN": "test-refresh-token",
            "TOKEN_ENCRYPTION_KEY": "test-encryption-key",
        },
        clear=True,
    )
    def test_explicit_dry_run_checks_twitch_even_when_bot_is_disabled(self):
        state = object()
        client = object()
        store = Mock()
        store.load.return_value = state
        with (
            patch.object(entrypoint, "load_config", return_value=self.config),
            patch.object(entrypoint, "EncryptedStateStore", return_value=store),
            patch.object(entrypoint, "TwitchClient", return_value=client),
            patch.object(entrypoint, "run_once", return_value="Dry-Run") as run_once,
            patch.object(sys, "argv", ["twitch-autoclipper"]),
        ):
            self.assertEqual(entrypoint.main(), 0)

        run_once.assert_called_once()
        self.assertIs(run_once.call_args.kwargs["dry_run"], True)

    @patch.dict(os.environ, {}, clear=True)
    def test_disabled_bot_without_dry_run_does_not_connect_to_twitch(self):
        with (
            patch.object(entrypoint, "load_config", return_value=self.config),
            patch.object(entrypoint, "EncryptedStateStore") as store,
            patch.object(entrypoint, "TwitchClient") as twitch,
            patch.object(entrypoint, "run_once") as run_once,
            patch.object(sys, "argv", ["twitch-autoclipper"]),
        ):
            self.assertEqual(entrypoint.main(), 0)

        store.assert_not_called()
        twitch.assert_not_called()
        run_once.assert_not_called()


if __name__ == "__main__":
    unittest.main()
