# Schnellstart: Meal MCP in Docker mit ChatGPT

Von null bis zum ersten Chat in sechs Schritten, unter Windows 10/11. Alle Befehle in **PowerShell**.
Hintergrund und Details: [DOCKER.md](DOCKER.md), [CHATGPT.md](CHATGPT.md).

**Nur für Demos.** Der Server hat keine Anmeldung: Wer die Adresse samt geheimem Pfad kennt, kann alle
Rezepte lesen und löschen. Den Tunnel nach der Demo beenden (Schritt 6).

Du brauchst:

- Adminrechte auf dem Rechner (einmal für die Installation)
- einen kostenlosen USDA-API-Key: https://fdc.nal.usda.gov/api-key-signup
- Git (`winget install --id Git.Git -e`)
- ein ChatGPT-Abo mit **Developer Mode** (nicht im kostenlosen Plan)

## 1. Docker installieren

```powershell
wsl --status
```

Meldet das einen Fehler, zuerst WSL einrichten, danach neu starten: `wsl --install --no-distribution`.
Dann Docker Desktop installieren (Windows fragt nach Adminrechten):

```powershell
winget install --id Docker.DockerDesktop -e
```

Docker Desktop aus dem Startmenü öffnen, die Nutzungsbedingungen annehmen, die Anmeldung mit **Skip**
überspringen. Warten, bis unten links „Engine running“ steht. In einem **neuen** PowerShell-Fenster prüfen:

```powershell
docker version
```

Unter „Server“ muss eine Version stehen. Docker Desktop ist für Privatleute, Bildung und kleine Firmen
kostenlos; größere Firmen brauchen ein Abo. Das gilt auch für einen Server beim Arbeitgeber.

## 2. Projekt holen und einrichten

```powershell
git clone https://github.com/flxzmn/meals.git
cd meals\meal_mcp
git switch chatgpt-http
```

`git switch` braucht es nur, solange Docker noch nicht in `main` ist. Einen geheimen Pfad erzeugen:

```powershell
[guid]::NewGuid().ToString("N")
```

Dann `notepad .env` öffnen (neue Datei bestätigen) und zwei Zeilen eintragen, mit deinem Key und der
erzeugten Zeichenfolge:

```
USDA_API_KEY=dein-usda-key
MEAL_HTTP_PATH=/3f2a9c0e8b1d4e7fa6c5b4d3e2f1a0b9/mcp
```

Gibt es `.env` schon, nur die Zeile `MEAL_HTTP_PATH` ergänzen. `.env` bleibt auf deinem Rechner, sie
kommt weder ins Image noch zu Git.

## 3. Container und Server starten

```powershell
docker compose --profile tunnel up --build -d
```

Der erste Start baut das Image und dauert ein paar Minuten, spätere Starts nur Sekunden. Das startet
zwei Container: `meal` (der MCP-Server) und `tunnel` (eine öffentliche HTTPS-Adresse über Cloudflare).

```powershell
docker compose ps
```

Bei `meal` muss nach etwa 10 Sekunden `(healthy)` stehen. Jetzt die öffentliche Adresse holen:

```powershell
(docker compose logs tunnel | Select-String 'https://[a-z0-9-]+\.trycloudflare\.com').Matches.Value | Select-Object -Last 1
```

Kommt nichts, ein paar Sekunden warten und noch einmal. Die **Server-URL** für ChatGPT ist die Adresse
plus dein geheimer Pfad:

```
https://abc-def-ghi.trycloudflare.com/3f2a9c0e8b1d4e7fa6c5b4d3e2f1a0b9/mcp
```

Die Adresse ändert sich bei jedem Start des Tunnels.

## 4. Smoketest

Der Test läuft im Container, ein lokales Python ist nicht nötig. Zuerst den Server selbst:

```powershell
Get-Content scripts\smoke_test.py | docker compose exec -T meal python -
```

Dann den öffentlichen Weg, den ChatGPT nimmt (deine Tunnel-Adresse **ohne** Pfad):

```powershell
Get-Content scripts\smoke_test.py | docker compose exec -T meal python - https://abc-def-ghi.trycloudflare.com
```

Beide Male erwartet:

```
OK      31 Tools, davon 13 nur lesend
OK      30 Ersatzregeln (frische Daten: 30)
OK      Milch -> Hafermilch gefunden
OK      ohne geheimen Pfad: 404 (erwartet 404)

Alles in Ordnung.
```

Ein frischer Tunnel braucht manchmal bis zu einer halben Minute, bis er erreichbar ist. Schlägt der
zweite Test sofort nach dem Start fehl, kurz warten und wiederholen.

## 5. Mit ChatGPT verbinden

Die Menünamen ändert OpenAI öfter (Connectors, Apps); sinngemäß:

1. Einstellungen → Apps/Connectors → Erweitert → **Developer Mode** einschalten.
2. **App/Connector erstellen**: Name `Meal MCP`, URL = deine Server-URL aus Schritt 3,
   Authentifizierung **keine**, dem Anbieter vertrauen, speichern.
3. Neuer Chat → **+** → Developer Mode → `Meal MCP` zuschalten. Das ist in jedem Chat nötig.

Danach im Chat prüfen:

| # | Frage | Erwartet |
|---|---|---|
| 1 | „Welche Ersatzregeln kennst du für Milch?“ | `find_substitutions` läuft ohne Rückfrage, Antwort nennt u. a. Hafermilch |
| 2 | „Suche Chicken Handi und speichere es.“ | `search_recipes`, dann `save_recipes` mit Rückfrage, die du bestätigst |
| 3 | „Welche Rezepte habe ich gespeichert?“ | `list_recipes` zeigt Chicken Handi |

Lesende Tools laufen ohne Rückfrage, schreibende fragt ChatGPT vorher, Löschen ist als destruktiv
markiert.

## 6. Beenden und wieder starten

```powershell
docker compose --profile tunnel down
```

Die Rezepte bleiben im Volume `meal-data` erhalten. Für die nächste Demo Schritt 3 wiederholen (ohne
`--build`, außer der Code hat sich geändert) und in ChatGPT die URL der App auf die neue
Tunnel-Adresse ändern. Alles löschen, auch die Daten: `docker compose --profile tunnel down -v`.

## Wenn etwas nicht klappt

| Meldung | Ursache und Lösung |
|---|---|
| `docker` wird nicht erkannt | neues PowerShell-Fenster öffnen; Docker Desktop muss laufen |
| `USDA_API_KEY fehlt in .env` / `MEAL_HTTP_PATH fehlt in .env` | `.env` liegt nicht in `meal_mcp` oder die Zeile fehlt |
| `meal` wird nicht `healthy` | `docker compose logs meal` ansehen |
| Smoketest: `404` statt Tools | Pfad in `.env` beginnt nicht mit `/` oder endet nicht auf `/mcp` |
| Smoketest öffentlich: Verbindungsfehler | Tunnel noch nicht bereit, 30 Sekunden warten; `docker compose logs tunnel` |
| ChatGPT erreicht den Server nicht | Tunnel-Adresse hat sich geändert oder der geheime Pfad fehlt in der URL |
| `421 Misdirected Request` | Aufruf über einen anderen Host als `localhost` oder `*.trycloudflare.com` |
