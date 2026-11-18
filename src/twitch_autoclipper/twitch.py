from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import time
from typing import Any, Callable, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


API_ROOT = "https://api.twitch.tv/helix"
OAUTH_ROOT = "https://id.twitch.tv/oauth2"
REQUIRED_SCOPE = "clips:edit"


class TwitchError(RuntimeError):
    """Base class for safe, user-readable Twitch errors."""


class TwitchNetworkError(TwitchError):
    pass


class TwitchApiError(TwitchError):
    def __init__(self, status: int, message: str, retry_after: int | None = None):
        self.status = status
        self.retry_after = retry_after
        super().__init__(f"Twitch API HTTP {status}: {message}")


@dataclass
class HttpReply:
    status: int
    headers: dict[str, str]
    body: bytes

    def json(self) -> dict[str, Any]:
        if not self.body:
            return {}
        try:
            data = json.loads(self.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise TwitchError("Twitch hat eine ungültige JSON-Antwort zurückgegeben.") from exc
        if not isinstance(data, dict):
            raise TwitchError("Twitch hat ein unerwartetes Antwortformat zurückgegeben.")
        return data


class Transport(Protocol):
    def request(
        self, method: str, url: str, headers: dict[str, str], body: bytes | None = None
    ) -> HttpReply: ...


class UrlLibTransport:
    def __init__(self, timeout_seconds: int = 20):
        self.timeout_seconds = timeout_seconds

    def request(
        self, method: str, url: str, headers: dict[str, str], body: bytes | None = None
    ) -> HttpReply:
        request = Request(url, data=body, headers=headers, method=method)
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                return HttpReply(
                    status=response.status,
                    headers={key.lower(): value for key, value in response.headers.items()},
                    body=response.read(),
                )
        except HTTPError as response:
            return HttpReply(
                status=response.code,
                headers={key.lower(): value for key, value in response.headers.items()},
                body=response.read(),
            )
        except (URLError, TimeoutError, OSError) as exc:
            raise TwitchNetworkError(
                "Keine Verbindung zu Twitch möglich oder Zeitüberschreitung."
            ) from exc


class TwitchClient:
    def __init__(
        self,
        client_id: str,
        state: Any,
        save_state: Callable[[], None],
        transport: Transport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ):
        self.client_id = client_id.strip()
        if not self.client_id:
            raise TwitchError("GitHub Secret TWITCH_CLIENT_ID fehlt.")
        self.state = state
        self.save_state = save_state
        self.transport = transport or UrlLibTransport()
        self.sleep = sleep
        self.monotonic = monotonic

    def _form_request(self, endpoint: str, fields: dict[str, str]) -> dict[str, Any]:
        response = self.transport.request(
            "POST",
            f"{OAUTH_ROOT}/{endpoint}",
            {"Content-Type": "application/x-www-form-urlencoded"},
            urlencode(fields).encode("utf-8"),
        )
        data = response.json()
        if not 200 <= response.status < 300:
            message = str(data.get("message") or data.get("error") or "OAuth-Anfrage fehlgeschlagen.")
            raise TwitchApiError(response.status, message)
        return data

    def refresh_access_token(self) -> None:
        if not self.state.refresh_token:
            raise TwitchError(
                "Kein Refresh-Token vorhanden. Starte scripts/authenticate.py erneut."
            )
        data = self._form_request(
            "token",
            {
                "grant_type": "refresh_token",
                "refresh_token": self.state.refresh_token,
                "client_id": self.client_id,
            },
        )
        access_token = data.get("access_token")
        refresh_token = data.get("refresh_token")
        if not access_token or not refresh_token:
            raise TwitchError("Twitch hat beim Token-Refresh kein vollständiges Token-Paar geliefert.")
        self.state.access_token = str(access_token)
        self.state.refresh_token = str(refresh_token)
        self.save_state()
        logging.info("Twitch-Zugriffstoken erneuert; verschlüsselter Status aktualisiert.")

    def _validate_token(self) -> dict[str, Any]:
        if not self.state.access_token:
            self.refresh_access_token()
        refreshed = False
        while True:
            response = self.transport.request(
                "GET",
                f"{OAUTH_ROOT}/validate",
                {"Authorization": f"OAuth {self.state.access_token}"},
            )
            if response.status == 401 and not refreshed:
                self.refresh_access_token()
                refreshed = True
                continue
            if not 200 <= response.status < 300:
                data = response.json()
                message = str(data.get("message") or "OAuth-Token konnte nicht geprüft werden.")
                raise TwitchApiError(response.status, message)
            return response.json()

    def get_authorized_user(self, expected_login: str) -> tuple[str, str]:
        validation = self._validate_token()
        if validation.get("client_id") != self.client_id:
            raise TwitchError("Das Twitch-Token gehört zu einer anderen Developer-Anwendung.")
        scopes = validation.get("scopes", [])
        if isinstance(scopes, str):
            scopes = scopes.split()
        if REQUIRED_SCOPE not in scopes:
            raise TwitchError(
                "Die Twitch-Autorisierung benötigt den Berechtigungsumfang clips:edit. "
                "Autorisiere die Anwendung erneut."
            )
        login = str(validation.get("login", "")).lower()
        user_id = str(validation.get("user_id", ""))
        if login != expected_login.lower() or not user_id:
            raise TwitchError(
                f"Das autorisierte Twitch-Konto ist nicht {expected_login}. "
                "Es werden keine Clips erstellt."
            )
        return user_id, login

    def _safe_error(self, response: HttpReply) -> TwitchApiError:
        data = response.json()
        message = str(data.get("message") or data.get("error") or "Unbekannter Twitch-Fehler.")
        message = " ".join(message.split())[:240]
        retry_after: int | None = None
        raw_retry_after = response.headers.get("retry-after")
        if raw_retry_after:
            try:
                retry_after = max(1, int(float(raw_retry_after)))
            except ValueError:
                retry_after = None
        return TwitchApiError(response.status, message, retry_after)

    def _helix(
        self,
        method: str,
        path: str,
        params: dict[str, str],
        *,
        safe_to_retry: bool,
    ) -> dict[str, Any]:
        query = urlencode(params)
        url = f"{API_ROOT}/{path}" + (f"?{query}" if query else "")
        attempts = 0
        refreshed = False
        while True:
            if not self.state.access_token:
                self.refresh_access_token()
            response = self.transport.request(
                method,
                url,
                {
                    "Authorization": f"Bearer {self.state.access_token}",
                    "Client-Id": self.client_id,
                },
            )
            if response.status == 401 and not refreshed:
                self.refresh_access_token()
                refreshed = True
                continue
            if response.status == 429 and attempts < 2:
                attempts += 1
                retry_after = response.headers.get("retry-after", "2")
                try:
                    delay = min(30, max(1, int(float(retry_after))))
                except ValueError:
                    delay = 2
                logging.warning("Twitch begrenzt Anfragen; erneuter Versuch in %s Sekunden.", delay)
                self.sleep(delay)
                continue
            if response.status >= 500 and safe_to_retry and attempts < 2:
                attempts += 1
                delay = attempts * 2
                logging.warning("Twitch ist vorübergehend nicht verfügbar; erneuter Versuch in %s Sekunden.", delay)
                self.sleep(delay)
                continue
            if not 200 <= response.status < 300:
                raise self._safe_error(response)
            return response.json()

    def get_live_stream(self, user_id: str) -> dict[str, Any] | None:
        data = self._helix(
            "GET", "streams", {"user_id": user_id, "first": "1"}, safe_to_retry=True
        ).get("data", [])
        if not data:
            return None
        stream = data[0]
        if stream.get("type") != "live" or str(stream.get("user_id")) != user_id:
            return None
        return stream

    def create_clip(
        self, broadcaster_id: str, duration_seconds: int, title: str
    ) -> dict[str, Any]:
        response = self._helix(
            "POST",
            "clips",
            {
                "broadcaster_id": broadcaster_id,
                "duration": str(duration_seconds),
                "title": title,
            },
            safe_to_retry=False,
        )
        clips = response.get("data", [])
        if not clips or not clips[0].get("id"):
            raise TwitchError("Twitch hat den Clip-Auftrag ohne Clip-ID bestätigt.")
        clip_id = str(clips[0]["id"])
        edit_url = str(clips[0].get("edit_url") or "")
        deadline = self.monotonic() + 60
        while True:
            result = self._helix(
                "GET", "clips", {"id": clip_id}, safe_to_retry=True
            ).get("data", [])
            if result:
                clip = result[0]
                return {
                    "id": clip_id,
                    "url": str(clip.get("url") or f"https://clips.twitch.tv/{clip_id}"),
                    "title": str(clip.get("title") or title),
                    "duration": clip.get("duration"),
                    "edit_url": edit_url,
                }
            remaining = deadline - self.monotonic()
            if remaining <= 0:
                raise TwitchError(
                    "Twitch hat den Clip innerhalb von 60 Sekunden nicht veröffentlicht. "
                    "Der Versuch wurde gespeichert und wird nicht automatisch wiederholt."
                )
            self.sleep(min(3, remaining))
