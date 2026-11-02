# Installation

## Voraussetzungen

- Claude Desktop (getestet: 4.29 unter Windows 11)
- Ein eigener, kostenloser USDA-API-Key: https://fdc.nal.usda.gov/api-key-signup
  Jede Person nutzt ihren eigenen Key. Ein gemeinsamer Key stößt schnell an das Limit von
  1.000 Anfragen pro Stunde.

## Windows und macOS

1. Eine alte `meal`-Erweiterung entfernen (Einstellungen → Erweiterungen).
2. `meal-<version>.mcpb` per Doppelklick oder Drag-and-drop installieren und den USDA-Key eingeben.
3. **Neuen Chat öffnen.** Ein laufender Chat nutzt weiter den alten Serverprozess. Der erste Start
   kann länger dauern, weil Abhängigkeiten geladen werden.
4. Test: „Suche Chicken Handi, speichere es und berechne die Nährwerte.“ Erwartet: etwa 4.250 kcal.

Das Paket hat den Servertyp `uv`: Claude Desktop bringt sein eigenes uv mit (`uv-runtime`, gesehen:
0.9.7), legt im Erweiterungsordner eine `.venv` an und installiert die Abhängigkeiten aus `uv.lock`.
Python muss nicht eingerichtet werden. Getestet unter Windows 11 und macOS (arm64); noch nicht
belegt ist ein Rechner ganz ohne Python.

Bis v1.1 gab es zusätzlich ein Paket mit Servertyp `python`. Es startete das System-Python und
scheiterte ohne die passenden Pakete ([FEHLERANALYSE.md](FEHLERANALYSE.md), Fall 13). Seit v1.2 gibt
es nur noch das uv-Paket.

## Datenbank

Seit v1.1 liegt die SQLite-Datei `recipe_mcp.db` außerhalb der Erweiterung, damit eine
Neuinstallation sie nicht löscht:

- Windows: `%APPDATA%\MealMCP\`
- macOS: `~/Library/Application Support/MealMCP/`

Unter Windows kann eine Installation aus dem Microsoft Store den Ordner nach
`%LOCALAPPDATA%\Packages\Claude_*\LocalCache\Roaming\MealMCP\` umleiten.

`export_data` schreibt alles in eine JSON-Datei, `import_data` liest sie wieder ein, auch auf einem
anderen Rechner. Der Import ergänzt nur und überschreibt nichts. Der USDA-Key ist nie Teil des Exports.

**Wechsel von v1.0:** Beim Entfernen der Erweiterung wird die alte Datenbank mit gelöscht. Wer seine
Daten behalten will, kopiert `recipe_mcp.db` vorher aus dem Erweiterungsordner
(`%LOCALAPPDATA%\Claude-Data\…\Claude Extensions\local.mcpb.felix-zimmermann.meal\`) in den neuen
Ordner. Neue Spalten werden beim Start ergänzt, und die Grammwerte gespeicherter Zutaten werden mit
dem aktuellen Mengen-Parser neu berechnet (aus `1 ½ tbsp` werden dann 22,5 g statt 7,5 g).

## Häufige Probleme

| Meldung | Ursache | Lösung |
|---|---|---|
| `Invalid manifest: Unrecognized key(s) in object: '_meta'` | Paket mit `mcpb pack --update` gebaut | Mit `python scripts/build_mcpb.py` neu bauen |
| `USDA HTTP 403: API key rejected` | Key falsch oder abgelaufen | Key in den Erweiterungseinstellungen prüfen |
| `USDA_API_KEY fehlt oder ist noch ein Platzhalter` | Kein Key angekommen | Key in den Einstellungen der Erweiterung setzen |
| Tool-Änderungen nicht sichtbar | Alter Serverprozess im laufenden Chat | Neuen Chat öffnen |

Logs: Claude Desktop → Einstellungen → Entwickler → Log-Ordner öffnen, Datei `mcp-server-meal.log`.
Mehr dazu in [FEHLERANALYSE.md](FEHLERANALYSE.md).
