from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path
import subprocess
import sys

from .bot import run_once
from .config import ConfigError, load_config
from .state import EncryptedStateStore, StateError
from .twitch import TwitchClient, TwitchError


def _persist_reservation_to_github(state_file: Path) -> None:
    """Push the encrypted pre-request reservation before creating a live clip."""
    if os.environ.get("GITHUB_ACTIONS") != "true":
        return
    relative_path = state_file.resolve().relative_to(Path.cwd().resolve())
    subprocess.run(["git", "add", "--", str(relative_path)], check=True)
    staged_diff = subprocess.run(["git", "diff", "--cached", "--quiet"], check=False)
    if staged_diff.returncode == 0:
        return
    if staged_diff.returncode != 1:
        raise RuntimeError("Git-Status des verschlüsselten Laufzeitstatus fehlgeschlagen.")
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=github-actions[bot]",
            "-c",
            "user.email=41898282+github-actions[bot]@users.noreply.github.com",
            "commit",
            "-m",
            "chore: reserve Twitch clip interval",
        ],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    subprocess.run(["git", "push"], check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Einmalige Prüfung des Twitch Auto Clippers.")
    parser.add_argument("--config", default="config.toml", help="Pfad zur TOML-Konfiguration.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Prüft Stream und Intervall, fordert aber keinen Clip an.",
    )
    args = parser.parse_args()
    try:
        config = load_config(args.config)
    except ConfigError as exc:
        logging.basicConfig(level=logging.ERROR, format="%(levelname)s %(message)s")
        logging.error("%s", exc)
        return 2

    logging.basicConfig(
        level=getattr(logging, config.log_level),
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%SZ",
    )
    logging.info("Ausführung gestartet.")
    try:
        if not config.enabled:
            logging.info("Automatische Clip-Erstellung ist in config.toml deaktiviert.")
            logging.info("Ausführung beendet.")
            return 0

        client_id = os.environ.get("TWITCH_CLIENT_ID", "")
        encryption_key = os.environ.get("TOKEN_ENCRYPTION_KEY", "")
        initial_refresh_token = os.environ.get("TWITCH_REFRESH_TOKEN", "")
        store = EncryptedStateStore(config.state_file, encryption_key)
        state = store.load(initial_refresh_token=initial_refresh_token)
        save_state = lambda: store.save(state)
        twitch = TwitchClient(client_id, state, save_state)
        dry_run = args.dry_run or os.environ.get("DRY_RUN", "").lower() == "true"
        result = run_once(
            config,
            state,
            twitch,
            save_state,
            dry_run=dry_run,
            before_clip_request=lambda: _persist_reservation_to_github(config.state_file),
        )
        logging.info("Ausführung beendet: %s.", result)
        return 0
    except (StateError, TwitchError, RuntimeError, OSError, subprocess.SubprocessError) as exc:
        logging.error("%s", exc)
        logging.info("Ausführung beendet: Fehler.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
