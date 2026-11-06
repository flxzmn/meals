# Docker (ein Nutzer, Demo)

Das Image startet Meal MCP über HTTP, zum Beispiel für ChatGPT oder als Remote-Server für eine Demo.
Claude Desktop braucht es nicht, dort läuft weiter das MCPB-Paket ([INSTALLATION.md](INSTALLATION.md)).
Für einen Server mit Anmeldung und eigenen Daten pro Person siehe [MEHRNUTZER.md](MEHRNUTZER.md).
Schritt für Schritt von der Docker-Installation bis zum Smoketest: [SCHNELLSTART.md](SCHNELLSTART.md).

**Ohne Anmeldung.** Wer die Adresse samt geheimem Pfad kennt, kann alle Rezepte lesen und löschen und
verbraucht den USDA-Key. Für eine Demo reicht das; den Tunnel danach beenden.

## Voraussetzungen

- Docker Desktop (Windows, macOS) oder Docker Engine (Linux)
- `.env` im Projektordner mit dem USDA-Key und einem geheimen Pfad:

```
USDA_API_KEY=<dein key>
MEAL_HTTP_PATH=/<zufall>/mcp
```

Zufälligen Teil erzeugen: `python -c "import secrets; print(secrets.token_urlsafe(16))"`.
`.env` kommt nicht ins Image (`.dockerignore`); Compose reicht die Werte beim Start herein.

## Starten

Nur auf diesem Rechner (`http://localhost:8000/<zufall>/mcp`):

```powershell
docker compose up --build -d
```

Mit öffentlicher Adresse über einen cloudflared-Tunnel:

```powershell
docker compose --profile tunnel up --build -d
docker compose logs tunnel
```

Im Log steht eine Adresse wie `https://abc-def.trycloudflare.com`. Die URL für den Client ist diese
Adresse plus der geheime Pfad: `https://abc-def.trycloudflare.com/<zufall>/mcp`. Sie ändert sich bei
jedem Start des Tunnels. In ChatGPT weiter wie in [CHATGPT.md](CHATGPT.md), Abschnitt 3.

Beenden: `docker compose --profile tunnel down`. Die Daten bleiben im Volume `meal-data` erhalten,
`docker compose down -v` löscht sie.

## Was das Image tut

| Punkt | Umsetzung |
|---|---|
| Inhalt | dieselben Laufzeitdateien wie das MCPB-Paket, Abhängigkeiten aus `uv.lock` |
| Daten | `/data` als Volume; beim ersten Start mit den 30 Startregeln |
| Netz | Port nur an `127.0.0.1` des Rechners; von außen nur über den Tunnel |
| Schutz | geheimer Pfad (sonst 404), Host-Prüfung (nur `localhost`, `meal` und `*.trycloudflare.com`, sonst 421) |
| Benutzer | läuft nicht als root |

## Tests

`python -m pytest tests/test_docker.py` prüft Dockerfile, `.dockerignore` und `compose.yaml` ohne
Docker. `python -m pytest -m release` baut das Image zusätzlich, startet es und ruft ein Tool auf;
ohne Docker wird dieser Test übersprungen.
