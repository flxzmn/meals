# Test mit ChatGPT (HTTP und Tunnel)

ChatGPT startet keinen lokalen Server, sondern verbindet sich mit einer öffentlichen HTTPS-Adresse.
Für einen Test läuft Meal MCP deshalb über HTTP auf `127.0.0.1`, ein Tunnel macht den Port von
außen erreichbar. Claude Desktop bleibt unverändert beim Paket (stdio).

**Nur zum Testen.** Es gibt keine Anmeldung: Wer die Adresse kennt, kann Rezepte lesen, ändern und
löschen und verbraucht deinen USDA-Key. Der geheime Pfad schützt nur, solange er geheim bleibt.
Tunnel nach dem Test beenden.

Mit Docker geht es ohne lokale Python-Umgebung: [DOCKER.md](DOCKER.md) startet Server und Tunnel mit
einem Befehl.

## 1. Server über HTTP starten

Einmal einen zufälligen Pfad erzeugen:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(16))"
```

Dann im Projektordner (der USDA-Key kommt wie bisher aus `.env`):

```powershell
$env:MEAL_TRANSPORT = "http"
$env:MEAL_HTTP_PATH = "/<zufall>/mcp"
$env:MEAL_ALLOWED_HOSTS = "*.trycloudflare.com"
$env:MEAL_DATA_DIR = "$env:APPDATA\MealMCP-ChatGPT"
uv run main.py
```

`MEAL_DATA_DIR` hält den Test von deinen echten Rezepten fern; ohne die Zeile nutzt der Server
`%APPDATA%\MealMCP`. Der Server meldet `HTTP on http://127.0.0.1:8000/<zufall>/mcp`. Anderer Port:
`MEAL_HTTP_PORT`.

## 2. Tunnel öffnen

Mit cloudflared (`winget install --id Cloudflare.cloudflared`), in einem zweiten Terminal:

```powershell
cloudflared tunnel --url http://127.0.0.1:8000
```

cloudflared zeigt eine Adresse wie `https://abc-def.trycloudflare.com`. Sie ändert sich bei jedem
Start. Für ngrok statt cloudflared `MEAL_ALLOWED_HOSTS` auf `*.ngrok-free.app` setzen.

Der Server nimmt nur Anfragen an `127.0.0.1`, `localhost` und die Hosts aus `MEAL_ALLOWED_HOSTS`
an (sonst 421), und nur auf dem geheimen Pfad (sonst 404).

## 3. In ChatGPT verbinden

Braucht ein bezahltes Abo mit Developer Mode. Die Menünamen hat OpenAI mehrfach geändert
(Connectors, Apps, Plugins); sinngemäß:

1. Einstellungen → Apps/Connectors → Erweitert → **Developer Mode** einschalten.
2. Neue App/Connector anlegen: Name `Meal MCP`, URL `https://abc-def.trycloudflare.com/<zufall>/mcp`,
   Authentifizierung **keine**, dem Anbieter vertrauen.
3. In einem neuen Chat über **+** → Developer Mode die App zuschalten (pro Chat nötig).

Lesende Tools (`get_recipes`, `get_nutrition`, `find_substitutions` …) tragen `readOnlyHint` und laufen
ohne Rückfrage; schreibende Tools fragt ChatGPT vorher ab, `delete_*` sind als destruktiv markiert.

## 4. Prüfen

| # | Frage im Chat | Erwartet |
|---|---|---|
| 1 | „Welche Ersatzregeln kennst du?“ | `find_substitutions` ohne Zutaten, 30 Startregeln |
| 2 | „Suche Chicken Handi, speichere es und berechne die Nährwerte.“ | `search_recipes`, `save_recipes` (Rückfrage), `enrich_recipes`, `get_nutrition`, etwa 4.250 kcal |
| 3 | „Mach eine vegane Variante und vergleiche die Nährwerte.“ | `adapt_recipes`, `save_adapted_recipes`, `compare_nutrition` |

## Grenzen des Tests

- `export_data`, `import_data` und `download_recipe_images` schreiben in Ordner auf deinem PC. Das
  funktioniert über den Tunnel, ChatGPT sieht die Dateien aber nicht.
- Die Evals (`scripts/run_evals.py`) lesen das Log von Claude Desktop und gelten nicht für ChatGPT.
- Für Dauerbetrieb fehlen Anmeldung (OAuth) und ein Server, der ohne deinen PC läuft.
