from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
from typing import Any, Callable

from .config import AppConfig
from .state import RuntimeState, format_time, parse_time, utc_now


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _interval_boundary_at_or_after(
    first_due_at: datetime, minimum_at: datetime, interval_minutes: int
) -> datetime:
    """Advance a durable cadence cursor past missed intervals without catch-up clips."""
    period = timedelta(minutes=interval_minutes)
    if minimum_at <= first_due_at:
        return first_due_at
    slots, remainder = divmod(minimum_at - first_due_at, period)
    if remainder:
        slots += 1
    return first_due_at + period * slots


def _latest_state_event(state: RuntimeState, started_at: datetime) -> datetime:
    timestamps = [started_at]
    for value in (state.last_attempt_at, state.last_success_at):
        parsed = parse_time(value)
        if parsed is not None:
            timestamps.append(parsed)
    return max(timestamps)


def run_once(
    config: AppConfig,
    state: RuntimeState,
    twitch: Any,
    save_state: Callable[[], None],
    *,
    dry_run: bool = False,
    now: datetime | None = None,
    before_clip_request: Callable[[], None] | None = None,
) -> str:
    supplied_now = now
    now = _as_utc(now or utc_now())
    user_id, login = twitch.get_authorized_user(config.channel)
    if login.lower() != config.channel.lower():
        raise RuntimeError("OAuth-Konto stimmt nicht mit dem konfigurierten Twitch-Kanal überein.")
    logging.info("OAuth-Konto geprüft: %s (ID %s).", login, user_id)

    stream = twitch.get_live_stream(user_id)
    if stream is None:
        logging.info("Livestream-Status: offline.")
        if state.stream_id is not None:
            state.stream_id = None
            state.stream_started_at = None
            state.next_clip_due_at = None
            state.interval_minutes = None
            save_state()
        return "offline"

    stream_id = str(stream["id"])
    started_at = parse_time(str(stream["started_at"]))
    if started_at is None:
        raise RuntimeError("Twitch hat beim Livestream keinen Startzeitpunkt geliefert.")
    logging.info(
        "Livestream-Status: live; Stream-ID %s; gestartet %s.",
        stream_id,
        format_time(started_at),
    )

    if state.stream_id != stream_id:
        state.stream_id = stream_id
        state.stream_started_at = format_time(started_at)
        state.next_clip_due_at = format_time(
            started_at + timedelta(minutes=config.interval_minutes)
        )
        state.interval_minutes = config.interval_minutes
        state.last_attempt_at = None
        save_state()
        logging.info("Neuer Stream erkannt; erstes Clip-Ziel ist %s.", state.next_clip_due_at)

    elif state.interval_minutes != config.interval_minutes or state.next_due is None:
        # Migrate old encrypted state and honor a changed interval from the last
        # clip attempt, while keeping future targets on the same stream cadence.
        first_due_at = started_at + timedelta(minutes=config.interval_minutes)
        minimum_at = _latest_state_event(state, started_at) + timedelta(
            minutes=config.interval_minutes
        )
        state.interval_minutes = config.interval_minutes
        state.stream_started_at = format_time(started_at)
        state.next_clip_due_at = format_time(
            _interval_boundary_at_or_after(
                first_due_at, minimum_at, config.interval_minutes
            )
        )
        save_state()

    due_at = state.next_due
    if due_at is None:  # Defensive fallback for malformed legacy state.
        due_at = started_at + timedelta(minutes=config.interval_minutes)
        state.next_clip_due_at = format_time(due_at)
        save_state()
    if now < due_at:
        logging.info("Noch nicht fällig; nächster Clip frühestens %s.", format_time(due_at))
        return "not_due"

    if dry_run:
        logging.info(
            "Testlauf: würde jetzt einen %s-Sekunden-Clip für %s anfordern.",
            config.clip_duration_seconds,
            config.channel,
        )
        return "dry_run_due"

    sequence = state.clip_sequence + 1
    title = f"{config.channel} - Gaming Clip {sequence:03d}"
    attempt_at = now if supplied_now is not None else _as_utc(utc_now())
    period = timedelta(minutes=config.interval_minutes)
    state.last_attempt_at = format_time(attempt_at)
    state.next_clip_due_at = format_time(
        _interval_boundary_at_or_after(
            due_at + period,
            attempt_at + period,
            config.interval_minutes,
        )
    )
    save_state()
    if before_clip_request is not None:
        before_clip_request()

    logging.info(
        "Clip-Anfrage: Länge %s Sekunden; Titel %s.",
        config.clip_duration_seconds,
        title,
    )
    clip = twitch.create_clip(user_id, config.clip_duration_seconds, title)
    completed_at = _as_utc(utc_now()) if supplied_now is None else _as_utc(supplied_now)
    state.last_success_at = format_time(completed_at)
    state.last_clip_id = str(clip["id"])
    state.last_clip_url = str(clip["url"])
    state.clip_sequence = sequence
    save_state()
    logging.info("Clip erstellt: ID %s, Link %s.", state.last_clip_id, state.last_clip_url)
    logging.info("Nächster Clip frühestens %s.", state.next_clip_due_at)
    return "created"
