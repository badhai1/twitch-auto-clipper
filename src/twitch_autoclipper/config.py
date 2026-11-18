from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib


ALLOWED_INTERVALS = (5, 10, 15, 20, 25, 30)
ALLOWED_DURATIONS = (15, 30, 45, 60)
REQUIRED_CHANNEL = "badhai1"


class ConfigError(ValueError):
    """Raised when the project configuration is invalid."""


@dataclass(frozen=True)
class AppConfig:
    channel: str
    interval_minutes: int
    clip_duration_seconds: int
    enabled: bool
    log_level: str
    state_file: Path


def load_config(path: str | Path) -> AppConfig:
    config_path = Path(path)
    try:
        with config_path.open("rb") as handle:
            raw = tomllib.load(handle)
    except OSError as exc:
        raise ConfigError(f"Konfigurationsdatei nicht lesbar: {config_path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Ungültige TOML-Konfiguration: {exc}") from exc

    twitch = raw.get("twitch", {})
    bot = raw.get("bot", {})
    channel = str(twitch.get("channel", "")).strip().lower()
    if channel != REQUIRED_CHANNEL:
        raise ConfigError(
            f"Diese Version darf ausschließlich Clips für {REQUIRED_CHANNEL} erstellen."
        )

    interval = twitch.get("interval_minutes")
    if interval not in ALLOWED_INTERVALS:
        raise ConfigError(
            "twitch.interval_minutes muss einer dieser Werte sein: "
            + ", ".join(map(str, ALLOWED_INTERVALS))
        )

    duration = twitch.get("clip_duration_seconds")
    if duration not in ALLOWED_DURATIONS:
        raise ConfigError(
            "twitch.clip_duration_seconds muss einer dieser Werte sein: "
            + ", ".join(map(str, ALLOWED_DURATIONS))
        )

    enabled = bot.get("enabled", False)
    if not isinstance(enabled, bool):
        raise ConfigError("bot.enabled muss true oder false sein.")

    log_level = str(bot.get("log_level", "INFO")).upper()
    if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR"}:
        raise ConfigError("bot.log_level muss DEBUG, INFO, WARNING oder ERROR sein.")

    state_file = Path(str(bot.get("state_file", ".state/runtime.enc")))
    if not state_file.is_absolute():
        state_file = config_path.parent / state_file

    return AppConfig(
        channel=channel,
        interval_minutes=interval,
        clip_duration_seconds=duration,
        enabled=enabled,
        log_level=log_level,
        state_file=state_file,
    )
