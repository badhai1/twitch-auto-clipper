# Twitch Auto Clipper – Version 1.0

Ein kleiner Python-Bot, der den Livestream von **badhai1** über die offizielle Twitch-Helix-API prüft und bei Fälligkeit einen Clip direkt auf Twitch anfordert. Es werden keine Videodateien heruntergeladen oder lokal als MP4 gespeichert. Es gibt keine Veröffentlichung auf TikTok oder YouTube und keinen eigenen Server.

## Stand und Grenzen

- Twitch erlaubt bei der Live-Clip-Erstellung aktuell eine Clip-Länge von 5 bis 60 Sekunden. Dieses Projekt bietet die angefragten Werte 15, 30, 45 und 60 Sekunden an. Twitch nimmt für die Clip-Erstellung ein Aufnahmefenster von bis zu 90 Sekunden auf; das ist vom veröffentlichten Clip mit der ausgewählten Länge zu unterscheiden. Die API veröffentlicht standardmäßig einen Clip und stellt im Ergebnis eine Bearbeitungsadresse bereit.
- Die aktuelle Helix-API nimmt einen Clip-Titel entgegen. Der Bot setzt Titel wie „badhai1 - Gaming Clip 001“. Twitch kann einen Titel durch AutoMod ablehnen.
- GitHub Actions unterstützt Zeitpläne frühestens alle fünf Minuten. Der Workflow prüft alle fünf Minuten und erstellt höchstens einen Clip pro Lauf, wenn das gespeicherte Intervall abgelaufen ist. Verpasste Zeitfenster werden übersprungen statt nachträglich mit mehreren Clips aufgeholt. GitHub kann geplante Läufe verzögern oder auslassen; die tatsächlichen Clip-Abstände sind daher nicht garantiert.
- Ein laufender Clip-Auftrag wird vor dem Twitch-Aufruf verschlüsselt und gespeichert. Nach einer unklaren Netzwerkstörung wird derselbe Zeitabschnitt nicht blind erneut angefragt. Das verhindert Doppelclips, kann aber bei einem Fehler nach der Reservierung einen Clip-Zeitpunkt auslassen.
- Der Zeitplan wird über die Repository-Variable TWITCH_CLIPPER_ENABLED gesteuert. Ein manueller Testlauf ist standardmäßig ein Dry Run.

## Kosten und Repository-Sichtbarkeit

Ein Fünf-Minuten-Zeitplan startet bis zu 288 Läufe pro Tag beziehungsweise etwa 8.640 Läufe in 30 Tagen. GitHub rechnet Minuten bei privaten Repositories auf die nächste volle Minute je Job auf. Bei einem Lauf unter einer Minute wären das bis zu 8.640 berechnete Minuten im Monat. Die aktuelle GitHub-Free-Compute-Gutschrift entspricht ungefähr 2.000 Minuten auf einem Standard-Linuxrunner; bei hinterlegter Zahlungsmethode kann die Differenz Kosten auslösen. GitHub dokumentiert Standardrunner für öffentliche Repositories als kostenfrei; für private Repositories gilt die monatliche enthaltene Rechenleistung, danach kann zusätzliche Nutzung berechnet oder ohne hinterlegte Zahlungsmethode blockiert werden.

Damit dieser Zeitplan wirklich kostenlos bleibt, ist ein **öffentliches Repository** mit Standardrunnern die passende GitHub-Actions-Variante. Der Quellcode enthält keine Zugangsdaten; Twitch-Refresh- und Zugriffstoken liegen in GitHub Secrets beziehungsweise als Fernet-verschlüsselter Status in .state/runtime.enc. Der Verschlüsselungsschlüssel selbst liegt nur als GitHub Secret vor. Öffentlich sichtbarer Quellcode und private Zugangsdaten sind damit getrennt. Wenn du ein privates Repository willst, prüfe vorher die Actions-Nutzung und setze in GitHub ein Ausgabenlimit oder lasse den Zeitplan deaktiviert.

GitHub Actions bietet keine minutengenaue Ausführungsgarantie. Wenn dein Kanal häufig live ist und jeder einzelne Fünf-Minuten-Zeitpunkt wichtig ist, ist eine dauerhafte externe Laufzeit nötig; das wäre nicht mehr die kostenfreie GitHub-Variante.

Ein optionaler Cloudflare-Worker kann als externer Zeitgeber den bestehenden Actions-Workflow alle fünf Minuten über die GitHub-API starten. Der Worker läuft auf Cloudflares kostenlosem Workers-Plan; die Konfiguration verwendet einen einzelnen Cron Trigger und benötigt weder einen eigenen Domainnamen noch einen eingeschalteten PC. Cloudflares Free-Plan hat Nutzungslimits und keine minutengenaue Ausführungsgarantie. Änderungen am Cron Trigger können bis zu 15 Minuten benötigen, bis sie überall aktiv sind. Der Worker startet standardmäßig nur den sicheren Probe-Workflow. Erst nach einer mindestens einstündigen Messung wird er auf den Clipper umgestellt und der interne Actions-Zeitplan abgeschaltet.

## Projektdateien

- src/twitch_autoclipper/: Konfiguration, OAuth/API-Client, Ablaufsteuerung und verschlüsselter Status
- scripts/authenticate.py: einmalige Twitch-Geräteautorisierung auf deinem PC
- config.toml: Kanal, Intervall, Clip-Länge, Aktivierung und Protokollstufe
- .github/workflows/clipper.yml: über Repository-Variable gesteuerter Fünf-Minuten-Zeitplan und manueller Testlauf
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

Das Skript zeigt einen Twitch-Aktivierungslink und einen einmaligen Code. Melde dich bei Twitch als badhai1 an und bestätige die angezeigte Berechtigung. Das Skript prüft danach Konto, App-ID und Scope. Unter Windows schreibt es die drei Secret-Werte nach %LOCALAPPDATA%\TwitchAutoClipper\github-secrets.json, außerhalb des Projektordners und OneDrive. Unter Linux verwendet es XDG_DATA_HOME oder ~/.local/share/twitch-auto-clipper/github-secrets.json. Die Datei enthält vertrauliche Werte; teile oder committe sie nicht. Das Skript gibt den vollständigen lokalen Pfad aus.

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

Aktive Konfiguration in config.toml:

- Twitch-Kanal: badhai1.
- Clip-Intervall: twitch.interval_minutes = 5.
- Clip-Länge: twitch.clip_duration_seconds = 60.
- Bot-Status: bot.enabled = true.
- Protokollierung: bot.log_level auf DEBUG, INFO, WARNING oder ERROR setzen.

Der Kanal ist in Version 1.0 auf badhai1 festgelegt. Auch bei einer Änderung der Konfiguration verweigert der Bot Clips für andere Konten. Der OAuth-Login muss zum Kanal passen.

Der aktive Actions-Zeitplan prüft alle fünf Minuten. Beim ersten Clip wartet der Bot, bis genug Live-Material für die ausgewählte Clip-Länge vorhanden ist; danach gilt das konfigurierte Intervall. Bei 60 Sekunden Clip-Länge und fünf Minuten Intervall kann ein pünktlicher Zeitplan so zwölf Clips innerhalb einer Stunde anfordern. Der Bot erstellt höchstens einen Clip pro Lauf. Der nächste Zielzeitpunkt bleibt am Intervalltakt des aktuellen Streams ausgerichtet; verspätete Läufe überspringen verpasste Zeitfenster und lösen keinen Clip-Stapel aus. GitHub Actions kann Läufe verzögern oder auslassen, daher sind exakte Abstände nicht garantiert. Der verschlüsselte Laufzeitstatus und die Sperre gegen parallele Läufe verhindern doppelte Intervallversuche. Stelle unter **Settings → Secrets and variables → Actions → Variables** die Repository-Variable TWITCH_CLIPPER_ENABLED auf true, damit geplante Läufe ausgeführt werden.

Ein manueller Verbindungstest ist unter **Actions → Twitch Auto Clipper → Run workflow** mit **Testlauf ohne echten Twitch-Clip** möglich. Der explizite Dry Run prüft OAuth, Konto und Livestream-Status, fordert aber niemals einen Clip an.

Zum Abschalten setze TWITCH_CLIPPER_ENABLED auf false. Wenn auch manuelle echte Clip-Anfragen blockiert werden sollen, setze zusätzlich bot.enabled auf false und commite die Änderung. Ein manueller Dry Run bleibt bei der Variablen false verfügbar. Zum manuellen Erstellen eines Clips müsste das Dry-Run-Feld ausdrücklich deaktiviert werden.

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

## Externen Zeitgeber einrichten und messen

Der Cloudflare-Worker in `cloudflare/` ist vorbereitet, aber noch nicht veröffentlicht. Der interne GitHub-Zeitplan bleibt aktiv, bis der Probezeitraum erfolgreich geprüft wurde. Cron-job.org wurde nicht als Dispatcher ausgewählt: Der Dienst ist zwar kostenlos, führt POST-Aufrufe aus und erlaubt Minutentakte, gibt aber keine Pünktlichkeitsgarantie. Seine Nutzungsbedingungen warnen zudem davor, sicherheitskritische Geheimnisse in Headern oder Request-Daten zu hinterlegen. Ein GitHub-Workflow-Dispatch benötigt ein GitHub-Token; deshalb verwahrt der vorbereitete Worker stattdessen einen eng beschränkten GitHub-App-Schlüssel als Cloudflare Secret und erstellt kurzlebige Installationstokens.

1. Erstelle unter [GitHub → Settings → Developer settings → GitHub Apps](https://github.com/settings/apps) eine GitHub-App. Deaktiviere Webhooks. Gib unter **Repository permissions** nur **Actions: Read and write** frei; abonniere keine Events.
2. Installiere die App ausschließlich auf `badhai1/twitch-auto-clipper`. Erstelle einen privaten Schlüssel und speichere die PEM-Datei außerhalb des Projektordners. Teile oder committe sie nicht.
3. Notiere die App-ID und die Installations-ID aus der GitHub-App-Seite beziehungsweise der Installations-URL.
4. Erstelle ein kostenloses Cloudflare-Konto und installiere Node.js LTS. Im Projektordner führst du `npx wrangler login` aus und bestätigst die Cloudflare-Anmeldung im Browser.
5. Veröffentliche den Worker mit `npx wrangler deploy --config cloudflare/wrangler.jsonc`. Trage in den Worker-Einstellungen unter **Settings → Variables and Secrets** die Variablen `GITHUB_APP_ID` und `GITHUB_INSTALLATION_ID` ein. Füge den Inhalt der PEM-Datei als Secret `GITHUB_APP_PRIVATE_KEY` hinzu. Das Secret bleibt in Cloudflare; nicht in GitHub-Dateien oder Logs.
6. Der Worker startet standardmäßig den Workflow **External schedule probe**, der keine Twitch-Secrets benötigt und keine Clips erstellen kann. Warte nach dem Einrichten 15 Minuten auf die Verteilung des Cron Triggers und beobachte anschließend mindestens 60 Minuten lang die Probe-Läufe. In den Logs stehen der vorgesehene UTC-Zeitpunkt und der tatsächliche Workflow-Start. Ein einzelner erfolgreicher Lauf genügt nicht.
7. Erst nach erfolgreicher Messung: Setze die GitHub-Variable `TWITCH_CLIPPER_ENABLED` auf `false`, damit der interne Cron nicht mehr startet. Setze anschließend die Cloudflare-Worker-Variable `TARGET_MODE` auf `clipper`. In diesem Modus sendet der Worker für `workflow_dispatch` ausdrücklich `dry_run=false`; die GitHub-Secrets und die bestehende Twitch-Verbindung bleiben dort. Der nächste externe Lauf startet den Clipper.

Wenn die Messung unregelmäßige GitHub-Starts zeigt, bleibt der interne Zeitplan aktiv und der Probe-Modus bleibt eingeschaltet. Dann müsste eine direkte Cloud-Ausführung des Bots geprüft werden; diese erfordert mehr Änderungen am bestehenden synchronen Python-API-Client. Auch ein direkter Cloudflare-Cronlauf hat keine harte Zeitgarantie.

Der GitHub-App-Dispatch benötigt nur `Actions: Read and write` für dieses eine Repository. GitHub erstellt pro Aufruf ein kurzlebiges Installationstoken. Die Workflow-Concurrency-Gruppe und die vor dem Clip-Aufruf gespeicherte Intervallreservierung verhindern parallele Clip-Anfragen; verpasste Intervalle werden nicht nachgeholt.
