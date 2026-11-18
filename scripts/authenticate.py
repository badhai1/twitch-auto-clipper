from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from cryptography.fernet import Fernet


OAUTH_ROOT = "https://id.twitch.tv/oauth2"
SCOPE = "clips:edit"
EXPECTED_LOGIN = "badhai1"


def default_output_path() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "TwitchAutoClipper" / "github-secrets.json"
    data_home = os.environ.get("XDG_DATA_HOME")
    if data_home:
        base = Path(data_home)
    else:
        base = Path.home() / ".local" / "share"
    return base / "twitch-auto-clipper" / "github-secrets.json"


def request_json(url: str, fields: dict[str, str] | None = None) -> dict:
    body = urlencode(fields).encode("utf-8") if fields else None
    headers = {}
    if body:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    request = Request(url, data=body, headers=headers)
    try:
        with urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        try:
            payload = json.loads(exc.read().decode("utf-8"))
            message = str(payload.get("message") or payload.get("error") or "OAuth-Anfrage fehlgeschlagen.")
        except (ValueError, AttributeError):
            message = "OAuth-Anfrage fehlgeschlagen."
        raise RuntimeError(f"Twitch OAuth HTTP {exc.code}: {message}") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise RuntimeError("Keine Verbindung zu Twitch möglich oder Zeitüberschreitung.") from exc


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Twitch-Geräteautorisierung für badhai1 und lokale Secret-Datei."
    )
    parser.add_argument("--client-id", default=os.environ.get("TWITCH_CLIENT_ID", ""))
    parser.add_argument("--output", default=str(default_output_path()))
    args = parser.parse_args()
    client_id = args.client_id.strip()
    if not client_id:
        print("Client-ID fehlt. Verwende --client-id oder TWITCH_CLIENT_ID.", file=sys.stderr)
        return 2

    try:
        device = request_json(
            f"{OAUTH_ROOT}/device",
            {"client_id": client_id, "scopes": SCOPE},
        )
        print(f"Öffne: {device['verification_uri']}")
        print(f"Gib dort diesen Code ein: {device['user_code']}")
        print("Warte auf die Bestätigung in Twitch ...")
        deadline = time.monotonic() + int(device.get("expires_in", 1800))
        interval = max(5, int(device.get("interval", 5)))
        token_data: dict | None = None
        while time.monotonic() < deadline:
            time.sleep(interval)
            try:
                token_data = request_json(
                    f"{OAUTH_ROOT}/token",
                    {
                        "client_id": client_id,
                        "scopes": SCOPE,
                        "device_code": str(device["device_code"]),
                        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                    },
                )
                break
            except RuntimeError as exc:
                if "authorization_pending" in str(exc).lower():
                    continue
                if "slow_down" in str(exc).lower():
                    interval += 5
                    continue
                raise
        if token_data is None:
            raise RuntimeError("Die Twitch-Autorisierung ist abgelaufen. Starte sie erneut.")

        # The validation endpoint requires the OAuth access token in its header.
        validation_request = Request(
            f"{OAUTH_ROOT}/validate",
            headers={"Authorization": f"OAuth {token_data['access_token']}"},
        )
        with urlopen(validation_request, timeout=20) as response:
            validation = json.loads(response.read().decode("utf-8"))
        scopes = validation.get("scopes", [])
        if isinstance(scopes, str):
            scopes = scopes.split()
        login = str(validation.get("login", "")).lower()
        if login != EXPECTED_LOGIN:
            raise RuntimeError(
                f"Autorisiert wurde {login or 'ein unbekanntes Konto'}, erwartet wird {EXPECTED_LOGIN}."
            )
        if SCOPE not in scopes:
            raise RuntimeError("Twitch hat clips:edit nicht erteilt. Autorisiere erneut mit dem Scope.")
        if validation.get("client_id") != client_id:
            raise RuntimeError("Das erhaltene Token gehört zu einer anderen Developer-Anwendung.")

        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        secrets = {
            "TWITCH_CLIENT_ID": client_id,
            "TWITCH_REFRESH_TOKEN": token_data["refresh_token"],
            "TOKEN_ENCRYPTION_KEY": Fernet.generate_key().decode("ascii"),
        }
        output.write_text(json.dumps(secrets, indent=2) + "\n", encoding="utf-8")
        try:
            os.chmod(output, 0o600)
        except OSError:
            pass
        print(f"Autorisierung für {login} geprüft.")
        print(f"Die drei GitHub-Secret-Werte stehen lokal in: {output.resolve()}")
        print("Diese Datei ist vertraulich und darf nicht committet oder geteilt werden.")
        return 0
    except (KeyError, ValueError, RuntimeError, URLError, TimeoutError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
