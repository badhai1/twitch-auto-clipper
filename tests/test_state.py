from pathlib import Path
import tempfile
import unittest

from cryptography.fernet import Fernet

from twitch_autoclipper.state import EncryptedStateStore, RuntimeState, StateError


class EncryptedStateTests(unittest.TestCase):
    def test_state_is_encrypted_and_round_trips(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "runtime.enc"
            key = Fernet.generate_key().decode("ascii")
            store = EncryptedStateStore(path, key)
            original = RuntimeState(
                access_token="sample-access",
                refresh_token="sample-refresh",
                stream_id="stream-1",
            )
            store.save(original)
            encrypted = path.read_bytes()
            self.assertNotIn(b"sample-access", encrypted)
            self.assertNotIn(b"sample-refresh", encrypted)
            self.assertEqual(store.load().to_dict(), original.to_dict())

    def test_wrong_encryption_key_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "runtime.enc"
            first = EncryptedStateStore(path, Fernet.generate_key().decode("ascii"))
            first.save(RuntimeState(refresh_token="sample-refresh"))
            second = EncryptedStateStore(path, Fernet.generate_key().decode("ascii"))
            with self.assertRaises(StateError):
                second.load()

    def test_bootstrap_refresh_token_is_used_until_state_exists(self):
        with tempfile.TemporaryDirectory() as directory:
            store = EncryptedStateStore(
                Path(directory) / "runtime.enc", Fernet.generate_key().decode("ascii")
            )
            self.assertEqual(store.load("initial-refresh").refresh_token, "initial-refresh")


if __name__ == "__main__":
    unittest.main()
