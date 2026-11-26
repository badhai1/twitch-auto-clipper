from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
from typing import Any

from cryptography.fernet import Fernet, InvalidToken


class StateError(RuntimeError):
    """Raised when encrypted state is missing, corrupt, or cannot be written."""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def format_time(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="seconds")


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


@dataclass
class RuntimeState:
    access_token: str = ""
    refresh_token: str = ""
    stream_id: str | None = None
    stream_started_at: str | None = None
    next_clip_due_at: str | None = None
    interval_minutes: int | None = None
    last_attempt_at: str | None = None
    last_success_at: str | None = None
    last_clip_id: str | None = None
    last_clip_url: str | None = None
    clip_sequence: int = 0

    @property
    def stream_started(self) -> datetime | None:
        return parse_time(self.stream_started_at)

    @property
    def next_due(self) -> datetime | None:
        return parse_time(self.next_clip_due_at)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> RuntimeState:
        fields = cls.__dataclass_fields__
        values = {key: raw[key] for key in fields if key in raw}
        return cls(**values)


class EncryptedStateStore:
    def __init__(self, path: str | Path, encryption_key: str):
        self.path = Path(path)
        if not encryption_key:
            raise StateError("GitHub Secret TOKEN_ENCRYPTION_KEY fehlt.")
        try:
            self.fernet = Fernet(encryption_key.encode("ascii"))
        except (ValueError, TypeError) as exc:
            raise StateError("TOKEN_ENCRYPTION_KEY ist ungültig.") from exc

    def load(self, initial_refresh_token: str = "") -> RuntimeState:
        if not self.path.exists():
            if not initial_refresh_token:
                raise StateError(
                    "Kein verschlüsselter Tokenstatus und kein Bootstrap-Secret "
                    "TWITCH_REFRESH_TOKEN vorhanden."
                )
            return RuntimeState(refresh_token=initial_refresh_token.strip())
        try:
            encrypted = self.path.read_bytes()
            raw = json.loads(self.fernet.decrypt(encrypted))
            state = RuntimeState.from_dict(raw)
        except (OSError, InvalidToken, json.JSONDecodeError, TypeError, KeyError) as exc:
            raise StateError(
                "Der verschlüsselte Laufzeitstatus kann nicht gelesen werden. "
                "Prüfe TOKEN_ENCRYPTION_KEY oder starte die Twitch-Autorisierung erneut."
            ) from exc
        if not state.refresh_token:
            if initial_refresh_token:
                state.refresh_token = initial_refresh_token.strip()
            else:
                raise StateError("Im verschlüsselten Laufzeitstatus fehlt das Refresh-Token.")
        return state

    def save(self, state: RuntimeState) -> None:
        payload = json.dumps(state.to_dict(), sort_keys=True).encode("utf-8")
        encrypted = self.fernet.encrypt(payload)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb", dir=self.path.parent, prefix=".state-", delete=False
            ) as handle:
                temp_name = handle.name
                handle.write(encrypted)
            try:
                os.chmod(temp_name, 0o600)
            except OSError:
                pass
            os.replace(temp_name, self.path)
        except OSError as exc:
            if temp_name:
                try:
                    os.unlink(temp_name)
                except OSError:
                    pass
            raise StateError("Der verschlüsselte Laufzeitstatus konnte nicht gespeichert werden.") from exc
