from pathlib import Path
import tempfile
import unittest

from twitch_autoclipper.config import (
    ALLOWED_DURATIONS,
    ALLOWED_INTERVALS,
    ConfigError,
    load_config,
)


class ConfigTests(unittest.TestCase):
    def write_config(self, content: str, directory: str) -> Path:
        path = Path(directory) / "config.toml"
        path.write_text(content, encoding="utf-8")
        return path

    def test_default_configuration_is_badhai1_and_disabled(self):
        config = load_config(Path(__file__).parents[1] / "config.toml")
        self.assertEqual(config.channel, "badhai1")
        self.assertEqual(config.interval_minutes, 10)
        self.assertEqual(config.clip_duration_seconds, 60)
        self.assertFalse(config.enabled)

    def test_all_requested_intervals_and_lengths_are_supported(self):
        self.assertEqual(ALLOWED_INTERVALS, (5, 10, 15, 20, 25, 30))
        self.assertEqual(ALLOWED_DURATIONS, (15, 30, 45, 60))

    def test_rejects_unsupported_interval(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_config(
                '[twitch]\nchannel="badhai1"\ninterval_minutes=7\n'
                'clip_duration_seconds=60\n[bot]\nenabled=true\n',
                directory,
            )
            with self.assertRaises(ConfigError):
                load_config(path)

    def test_rejects_other_channel(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_config(
                '[twitch]\nchannel="someone_else"\ninterval_minutes=10\n'
                'clip_duration_seconds=60\n[bot]\nenabled=true\n',
                directory,
            )
            with self.assertRaises(ConfigError):
                load_config(path)


if __name__ == "__main__":
    unittest.main()
