from pathlib import Path
import os
import unittest
from unittest.mock import patch

from scripts.authenticate import default_output_path


class AuthenticatePathTests(unittest.TestCase):
    @patch.dict(os.environ, {"LOCALAPPDATA": "/local/app-data"}, clear=True)
    def test_secret_file_defaults_to_local_app_data_when_available(self):
        self.assertEqual(
            default_output_path(),
            Path("/local/app-data") / "TwitchAutoClipper" / "github-secrets.json",
        )

    @patch.dict(os.environ, {"XDG_DATA_HOME": "/local/share"}, clear=True)
    def test_secret_file_uses_user_data_home_without_local_app_data(self):
        self.assertEqual(
            default_output_path(),
            Path("/local/share") / "twitch-auto-clipper" / "github-secrets.json",
        )


if __name__ == "__main__":
    unittest.main()
