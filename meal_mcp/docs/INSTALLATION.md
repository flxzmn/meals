# Installation

## Voraussetzungen

- Claude Desktop (getestet: 4.29 unter Windows 11)
- Ein eigener, kostenloser USDA-API-Key: https://fdc.nal.usda.gov/api-key-signup
  Jede Person nutzt ihren eigenen Key. Ein gemeinsamer Key stößt schnell an das Limit von
  1.000 Anfragen pro Stunde.
- Je nach Paket Python 3.11 oder neuer (siehe unten)

## Welches Paket?

| Paket | Wann | Python nötig? |
|---|---|---|
| `meal-<version>-uv.mcpb` | **Empfohlen**, Windows und macOS | Keine Einrichtung nötig: Claude Desktop bringt uv mit und installiert die Abhängigkeiten selbst |
| `meal-<version>.mcpb` | Ausweichweg, wenn das uv-Paket nicht installiert werden kann | Ja, mit den Paketen aus `requirements.txt` |

## Windows und macOS: uv-Paket (empfohlen)

1. Eine alte `meal`-Erweiterung entfernen.
2. `meal-<version>-uv.mcpb` installieren und den USDA-Key eingeben.
3. **Neuen Chat öffnen.** Ein laufender Chat nutzt weiter den alten Serverprozess. Der erste Start
   kann länger dauern, weil Abhängigkeiten geladen werden.
4. Test: „Suche Chicken Handi, speichere es und berechne die Nährwerte.“ Erwartet: etwa 4.358 kcal.

Getestet mit Claude Desktop unter Windows 11 und macOS (arm64). Claude Desktop nutzt sein eigenes
uv (`uv-runtime`, gesehen: 0.9.7) und legt im Erweiterungsordner eine `.venv` an. Ein eigenes uv ist
nicht nötig. Noch nicht belegt ist der Fall eines Rechners ganz ohne Python: Auf beiden Testrechnern
war ein Python vorhanden.

## Windows: Python-Paket (Ausweichweg)

1. Python 3.11+ installieren (python.org oder Microsoft Store) und prüfen:
   ```powershell
   python --version
   ```
2. Abhängigkeiten für das System-Python installieren. Claude Desktop startet das System-Python,
   nicht eine virtuelle Umgebung:
   ```powershell
   python -m pip install -r requirements.txt
   ```
3. Claude Desktop → Einstellungen → Erweiterungen → eine alte `meal`-Erweiterung entfernen.
4. `meal-<version>.mcpb` per Doppelklick oder Drag-and-drop installieren.
5. USDA-Key eingeben, wenn danach gefragt wird.
6. **Neuen Chat öffnen.** Ein laufender Chat nutzt weiter den alten Serverprozess.
7. Test: „Suche ein Rezept mit Chicken und berechne die Nährwerte.“

## macOS: Python-Paket

Das Python-Paket scheitert auf macOS meist mit `ModuleNotFoundError: No module named 'sqlalchemy'`,
weil Claude Desktop `/usr/bin/python3` startet, in dem die Pakete fehlen. Deshalb auf dem Mac das
uv-Paket verwenden.

## Datenbank

Die SQLite-Datei `recipe_mcp.db` liegt im Installationsordner der Erweiterung, unter Windows z. B.
`%LOCALAPPDATA%\Claude-Data\…\Claude Extensions\local.mcpb.felix-zimmermann.meal\`. Eine
Neuinstallation beginnt mit einer leeren Datenbank. Neue Spalten werden beim Start ergänzt; beim
Wechsel von v0.5.0 oder älter die Datenbank löschen.

## Häufige Probleme

| Meldung | Ursache | Lösung |
|---|---|---|
| `Invalid manifest: Unrecognized key(s) in object: '_meta'` | Paket mit `mcpb pack --update` gebaut | Mit `python scripts/build_mcpb.py` neu bauen |
| `No module named 'sqlalchemy'` | System-Python ohne Pakete | `pip install -r requirements.txt` für dieses Python oder uv-Paket |
| `USDA HTTP 403: API key rejected` | Key falsch oder abgelaufen | Key in den Erweiterungseinstellungen prüfen |
| `USDA_API_KEY fehlt oder ist noch ein Platzhalter` | Kein Key angekommen | Key in den Einstellungen der Erweiterung setzen |
| Tool-Änderungen nicht sichtbar | Alter Serverprozess im laufenden Chat | Neuen Chat öffnen |

Logs: Claude Desktop → Einstellungen → Entwickler → Log-Ordner öffnen, Datei `mcp-server-meal.log`.
Mehr dazu in [FEHLERANALYSE.md](FEHLERANALYSE.md).
