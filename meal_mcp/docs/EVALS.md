# Evals

Die Tests in `tests/` prüfen den Server. Sie zeigen nicht, ob Claude das richtige Tool wählt. Genau dort
lagen viele Fehler aus [FEHLERANALYSE.md](FEHLERANALYSE.md): Die Tests waren grün, das Verhalten im Chat
war falsch. Die Evals prüfen deshalb den Chat.

## Ablauf

Du brauchst keinen API-Key, Claude Desktop ist der Client. Der Server schreibt jeden Tool-Aufruf als
`TOOL_CALL <tool> ok|error` ins MCP-Log, ohne die Argumente.

1. Installiere die Erweiterung und öffne den Log-Ordner (Einstellungen → Entwickler → Logs-Ordner
   öffnen). Die Datei heißt `mcp-server-Meal MCP.log` oder ähnlich.
2. Starte das Skript:

   ```powershell
   python scripts/run_evals.py --log "<Pfad zum Log>"
   ```

3. Das Skript zeigt einen Prompt. Führe ihn in einem neuen Chat aus und warte die Antwort ab.
4. Drücke Enter. Das Skript liest die neuen Log-Zeilen und bewertet den Fall.

Die Fälle bauen aufeinander auf, zum Beispiel braucht der Vergleich die zuvor gespeicherte Variante.
Einzelne Fälle laufen mit `--only compare-variant,scale`. Das Ergebnis liegt in `evals/results/`
(nicht im Repository).

## Bewertung

Die Fälle stehen in [`evals/cases.json`](../evals/cases.json). Ein Fall ist bestanden, wenn:

- alle Tools aus `required` in dieser Reihenfolge vorkommen (eine Liste bedeutet: eines davon),
- kein Tool aus `forbidden` vorkommt,
- kein Tool-Aufruf fehlschlägt.

Weitere Tools dazwischen sind erlaubt.

## Grenzen

- Geprüft wird die Wahl der Tools, nicht die Qualität der Antwort. Ob Claude ein `comparable: false`
  richtig erklärt, musst du selbst lesen.
- Claude antwortet nicht immer gleich. Wiederhole einen Fall, bevor du daraus Schlüsse ziehst.
- Warnt das Skript vor nichts, obwohl Tools liefen, stimmt meist der Log-Pfad nicht.

## Einen Fall ergänzen

Einen Eintrag in `evals/cases.json` anlegen: `id`, `prompt`, `required`, `forbidden` und `checks` (was
der Fall zeigen soll). `tests/test_v1_1.py` prüft, dass alle genannten Tools existieren.
