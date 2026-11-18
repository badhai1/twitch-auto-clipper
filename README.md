# Twitch Auto Clipper – Version 1.0

Ein kleiner Python-Bot, der den Livestream von **badhai1** über die offizielle Twitch-Helix-API prüft und bei Fälligkeit einen Clip direkt auf Twitch anfordert. Es werden keine Videodateien heruntergeladen oder lokal als MP4 gespeichert. Es gibt keine Veröffentlichung auf TikTok oder YouTube und keinen eigenen Server.

## Stand und Grenzen

- Twitch erlaubt bei der Live-Clip-Erstellung aktuell eine Clip-Länge von 5 bis 60 Sekunden. Dieses Projekt bietet die angefragten Werte 15, 30, 45 und 60 Sekunden an. Twitch nimmt für die Clip-Erstellung ein Aufnahmefenster von bis zu 90 Sekunden auf; das ist vom veröffentlichten Clip mit der ausgewählten Länge zu unterscheiden. Die API veröffentlicht standardmäßig einen Clip und stellt im Ergebnis eine Bearbeitungsadresse bereit.
- Die aktuelle Helix-API nimmt einen Clip-Titel entgegen. Der Bot setzt Titel wie „badhai1 - Gaming Clip 001“. Twitch kann einen Titel durch AutoMod ablehnen.
- GitHub Actions unterstützt Zeitpläne frühestens alle fünf Minuten. Darum prüft der Workflow alle fünf Minuten und erstellt nur dann einen Clip, wenn das gespeicherte Intervall abgelaufen ist. Das funktioniert rechnerisch auch mit 25 Minuten. Es ist keine exakte Uhr: GitHub kann Zeitpläne verzögern und bei hoher Last sogar auslassen. Ein 25-Minuten-Clip kann dadurch später als geplant entstehen; ein verpasster Zeitraum wird nicht nachträglich mit mehreren Clips aufgeholt.
- Ein laufender Clip-Auftrag wird vor dem Twitch-Aufruf verschlüsselt und gespeichert. Nach einer unklaren Netzwerkstörung wird derselbe Zeitabschnitt nicht blind erneut angefragt. Das verhindert Doppelclips, kann aber bei einem Fehler nach der Reservierung einen Clip-Zeitpunkt auslassen.
- Der Zeitplan ist im Workflow zunächst auskommentiert und damit nicht aktiviert. Erst nach einem erfolgreichen Twitch-Dry-Run wird er eingeschaltet. Auch config.toml startet deaktiviert; ein manueller Testlauf ist standardmäßig ein Dry Run.

## Kosten und Repository-Sichtbarkeit

Ein Fünf-Minuten-Zeitplan startet bis zu 288 Läufe pro Tag beziehungsweise etwa 8.640 Läufe in 30 Tagen. GitHub rechnet Minuten bei privaten Repositories auf die nächste volle Minute je Job auf. Bei einem Lauf unter einer Minute wären das bis zu 8.640 berechnete Minuten im Monat. Die aktuelle GitHub-Free-Compute-Gutschrift entspricht ungefähr 2.000 Minuten auf einem Standard-Linuxrunner; bei hinterlegter Zahlungsmethode kann die Differenz Kosten auslösen. GitHub dokumentiert Standardrunner für öffentliche Repositories als kostenfrei; für private Repositories gilt die monatliche enthaltene Rechenleistung, danach kann zusätzliche Nutzung berechnet oder ohne hinterlegte Zahlungsmethode blockiert werden.

Damit dieser Zeitplan wirklich kostenlos bleibt, ist ein **öffentliches Repository** mit Standardrunnern die passende GitHub-Actions-Variante. Der Quellcode enthält keine Zugangsdaten; Twitch-Refresh- und Zugriffstoken liegen in GitHub Secrets beziehungsweise als Fernet-verschlüsselter Status in .state/runtime.enc. Der Verschlüsselungsschlüssel selbst liegt nur als GitHub Secret vor. Öffentlich sichtbarer Quellcode und private Zugangsdaten sind damit getrennt. Wenn du ein privates Repository willst, prüfe vorher die Actions-Nutzung und setze in GitHub ein Ausgabenlimit oder lasse den Zeitplan deaktiviert.

GitHub Actions bietet keine minutengenaue Ausführungsgarantie. Wenn dein Kanal häufig live ist und jeder einzelne Fünf-Minuten-Zeitpunkt wichtig ist, ist eine dauerhafte externe Laufzeit nötig; das wäre nicht mehr die kostenfreie GitHub-Variante.

## Projektdateien

- src/twitch_autoclipper/: Konfiguration, OAuth/API-Client, Ablaufsteuerung und verschlüsselter Status
- scripts/authenticate.py: einmalige Twitch-Geräteautorisierung auf deinem PC
- config.toml: Kanal, Intervall, Clip-Länge, Aktivierung und Protokollstufe
- .github/workflows/clipper.yml: deaktivierter Fünf-Minuten-Zeitplan und manueller Testlauf
- .github/workflows/tests.yml: automatisierte Tests ohne echte Twitch-Aufrufe
- tests/: simulierte Antworten und Prüfungen
- requirements.txt: einzige externe Python-Abhängigkeit für den verschlüsselten Status

## 1. Twitch-Developer-Anwendung erstellen

1. Öffne das [Twitch Developer Console](https://dev.twitch.tv/console/apps) und registriere eine Anwendung.
2. Wähle den Client-Typ **Public**, damit der OAuth Device Code Flow ohne Client Secret funktioniert.
3. Falls Twitch beim Registrieren eine Redirect-URL verlangt, trage http://localhost:3000 ein. Der Geräte-Flow verwendet diese URL nicht.
4. Kopiere die Client-ID. Teile sie nicht im Quellcode; in dieser Einrichtung wird sie als GitHub Secret abgelegt.

Der Bot benötigt nur die OAuth-Berechtigung **clips:edit**. Twitch verlangt, dass du die Anwendung über den offiziellen Aktivierungscode autorisierst. Bei der Anmeldung muss das Konto badhai1 verwendet werden.

## 2. Twitch einmalig verbinden

Installiere Python 3.11 oder neuer. Im Projektverzeichnis führst du aus:

~~~powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
python scripts/authenticate.py --client-id DEINE_TWITCH_CLIENT_ID
~~~

Das Skript zeigt einen Twitch-Aktivierungslink und einen einmaligen Code. Melde dich bei Twitch als badhai1 an und bestätige die angezeigte Berechtigung. Das Skript prüft danach Konto, App-ID und Scope. Die drei Secret-Werte schreibt es in .secrets/github-secrets.json. Diese Datei ist lokal und durch .gitignore ausgeschlossen. Sie enthält vertrauliche Werte; teile und committe sie nicht.

## 3. GitHub Secrets anlegen

Lege im Repository unter **Settings → Secrets and variables → Actions → New repository secret** genau diese Repository Secrets an. Die Werte findest du in der lokalen JSON-Datei:

| Secret | Inhalt |
| --- | --- |
| TWITCH_CLIENT_ID | Client-ID der Twitch-Anwendung |
| TWITCH_REFRESH_TOKEN | Refresh-Token aus der Geräteautorisierung; dient als Bootstrap |
| TOKEN_ENCRYPTION_KEY | Fernet-Schlüssel aus der Ausgabe-Datei |

Das Refresh-Token wird bei der Erneuerung von Twitch rotiert. Der Bot verschlüsselt den neuen Token zusammen mit dem kurzen Zugriffstoken und dem Laufzeitstatus und speichert die verschlüsselte Datei im Repository. Deshalb braucht der Workflow die Berechtigung contents: write. Behalte denselben TOKEN_ENCRYPTION_KEY dauerhaft. Wenn du ihn verlierst oder änderst, kann der gespeicherte Status nicht mehr entschlüsselt werden; führe dann die Twitch-Autorisierung erneut aus und ersetze die Secrets.

Twitch weist für den Device Code Flow darauf hin, dass ein Refresh-Token nach 30 Tagen ohne Nutzung abläuft. Wenn du den Bot länger pausierst, kann eine erneute Geräteautorisierung nötig sein. Wenn du den verschlüsselten Status löschst oder zurücksetzt, ist das ursprüngliche Bootstrap-Token meist bereits verbraucht; autorisiere dann neu und aktualisiere TWITCH_REFRESH_TOKEN.

## 4. Konfiguration ändern und Bot aktivieren

In config.toml:

- Intervall: twitch.interval_minutes auf 5, 10, 15, 20, 25 oder 30 setzen. Standard: 10.
- Clip-Länge: twitch.clip_duration_seconds auf 15, 30, 45 oder 60 setzen. Standard: 60.
- Bot einschalten: bot.enabled auf true setzen. Standard: false.
- Bot ausschalten: bot.enabled wieder auf false setzen und committen.
- Protokollierung: bot.log_level auf DEBUG, INFO, WARNING oder ERROR setzen.

Der Kanal ist in Version 1.0 auf badhai1 festgelegt. Auch bei einer Änderung der Konfiguration verweigert der Bot Clips für andere Konten. Der OAuth-Login muss zum Kanal passen.

Starte unter **Actions → Twitch Auto Clipper → Run workflow** einen manuellen Lauf mit **Testlauf ohne echten Twitch-Clip** aktiviert. Der explizite Dry Run prüft OAuth, Konto, Livestream-Status und Fälligkeit auch bei bot.enabled=false und fordert niemals einen Clip an. Für echte Clip-Anfragen muss bot.enabled ausdrücklich auf true gesetzt werden. Wenn ein Dry Run erfolgreich war und du den automatischen Zeitplan aktivieren möchtest, entferne in .github/workflows/clipper.yml die drei Kommentarzeichen vor schedule und cron und commite die Änderung. Lege zusätzlich unter **Settings → Secrets and variables → Actions → Variables** die Repository-Variable TWITCH_CLIPPER_ENABLED=true an. Erst dann startet der automatische Zeitplan. Er läuft nur vom Standardbranch.

Zum Abschalten setze TWITCH_CLIPPER_ENABLED auf false und commite bot.enabled=false. Ein manueller Dry Run bleibt auch bei der Variablen false verfügbar. Zum Aktivieren einer echten manuellen Clip-Anfrage müsste das Dry-Run-Feld ausdrücklich deaktiviert werden.

## 5. Clips finden

Veröffentlichte Clips findest du im Clip-Bereich deines Twitch-Kanals unter [twitch.tv/badhai1/clips](https://www.twitch.tv/badhai1/clips). In den Actions-Protokollen stehen Clip-ID und Link, aber keine Tokens.

## 6. Tests und echter Stream-Test

Die Tests rufen keine Twitch-API auf und erstellen keine echten Clips. Sie simulieren Live-/Offline-Antworten, Konfiguration, Intervall, API-Fehler, Token-Erneuerung, verschlüsselten Status, Sperre gegen Wiederholungen und Workflow-Einstellungen.

Lokal kannst du die Tests so ausführen:

~~~powershell
python -m unittest discover -s tests -v
~~~

Ein echter Twitch-Test ist noch erforderlich, um die App-Autorisierung, tatsächliche Clip-Erstellung, Twitch-seitige Veröffentlichung und Clip-Anzeige im Kanal zu bestätigen. Dieser Test kann einen echten Clip erzeugen. Starte ihn daher erst, wenn du einen solchen Clip ausdrücklich auslösen möchtest.

## Sicherheit und Hinweise

- Im Repository und in Logs werden keine Klartext-Tokens oder Passwörter gespeichert.
- Der Bootstrap-Refresh-Token liegt als GitHub Secret. Twitch kann Refresh-Tokens rotieren; der verschlüsselte Status commitet die aktuelle Version nach jeder Ausführung.
- Der Workflow erzeugt pro Zeitpunkt höchstens einen Clip und wird über eine gemeinsame Concurrency-Gruppe serialisiert.
- Bei deaktivierten Clips, Follower-/Abonnenten-Beschränkungen, gesperrten Kategorien, fehlendem Scope oder einer nicht-live geschalteten Übertragung meldet Twitch einen Fehler. Aktiviere Clips in den Twitch-Kanaleinstellungen und prüfe gegebenenfalls Einschränkungen.
- Für spätere Highlight-Erkennung bleibt die Clip-Entscheidung in bot.py separat vom Twitch-API-Client. Eine spätere Version kann dort eine Bewertung ergänzen, ohne die OAuth- oder Veröffentlichungslogik neu aufzubauen.

## Offizielle Referenzen

- [Twitch Clips API – Referenz](https://dev.twitch.tv/docs/api/reference/clips)
- [Twitch OAuth – Device Code Grant und Token-Erneuerung](https://dev.twitch.tv/docs/authentication/getting-tokens-oauth)
- [GitHub Actions – Workflow-Syntax und Zeitpläne](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax)
- [GitHub Actions – Kosten und Abrechnung](https://docs.github.com/en/billing/concepts/product-billing/github-actions)
