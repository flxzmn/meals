# Fehleranalyse anhand realer Logs

Alle Fälle sind während der Entwicklung von v0.4 bis v0.12 tatsächlich aufgetreten. Jeder Fall
folgt demselben Schema: Symptom, Beleg, Ursache, Behebung, Lehre. Die Fälle eignen sich als
Übungen (siehe [UEBUNGEN.md](UEBUNGEN.md)): Log zeigen, Ursache suchen lassen.

Logs findet man in Claude Desktop unter Einstellungen → Entwickler → Log-Ordner öffnen, Datei
`mcp-server-meal.log`. Alles, was der Server auf `stderr` schreibt, steht dort. `stdout` ist für
MCP-Nachrichten reserviert; ein `print()` nach `stdout` zerstört das Protokoll.

## 1. Server startet nicht: relativer Datenbankpfad

**Symptom:** Erweiterung installiert, Server bricht sofort ab.

**Beleg:**
```
File "...\local.mcpb.unknown-author.meal\db\db.py", line 34, in init_db
    Base.metadata.create_all(bind=engine)
sqlite3.OperationalError: unable to open database file
...
Server transport closed unexpectedly, this is likely due to the process exiting early.
```

**Ursache:** `DATABASE_URL=sqlite:///recipe_mcp.db` ist relativ zum Arbeitsverzeichnis. Claude
Desktop startet den Server aus einem Ordner, in dem er nicht schreiben darf.

**Behebung:** Pfad aus der Lage von `config/settings.py` ableiten (`BASE_DIR / "recipe_mcp.db"`).
Seit v0.12 setzt auch `.env.example` keinen relativen Pfad mehr.

**Lehre:** Ein Server, der lokal läuft, läuft nicht zwangsläufig im Host. Pfade nie relativ zum
Arbeitsverzeichnis.

## 2. Pydantic: nicht annotiertes Attribut

**Beleg:**
```
pydantic.errors.PydanticUserError: A non-annotated attribute was detected:
`BASE_DIR = WindowsPath('C:/Users/.../local.mcpb.unknown-author.meal')`.
```

**Ursache:** `BASE_DIR` stand innerhalb der `BaseSettings`-Klasse. Pydantic hält jedes Attribut
für ein Feld und verlangt eine Typangabe.

**Behebung:** `BASE_DIR` auf Modulebene definieren (oder als `ClassVar[Path]`).

**Lehre:** Einstellungsklassen enthalten nur Felder; Hilfswerte gehören daneben.

## 3. Installation abgelehnt: `_meta` im Manifest

**Beleg (Claude Desktop):** `Invalid manifest: Unrecognized key(s) in object: '_meta'`

**Ursache:** `mcpb pack --update` schrieb das Manifest neu, fügte `_meta` hinzu und entfernte
nebenbei `user_config`.

**Behebung:** Eigenes Build-Skript mit `--sync-manifest`; der Release-Test prüft die erlaubten
Manifest-Schlüssel.

**Lehre:** Werkzeuge, die Quelldateien „aktualisieren“, nicht blind nutzen. Was der Host
akzeptiert, automatisch prüfen.

## 4. Paket mit über 100 MB

**Ursache:** `mcpb pack` im Projektordner packte `.venv` mit ein; die Ignore-Muster der CLI
(`dir/`, `**`) griffen nicht wie erwartet.

**Behebung:** Allowlist statt Blocklist (`scripts/build_mcpb.py`), Ergebnis etwa 50 KB.

**Lehre:** Für Auslieferungen festlegen, was hinein darf, nicht, was draußen bleiben soll.

## 5. USDA 403 und Key im Klartext

**Beleg (Tool-Antwort im Chat):** Jede Zutat meldete HTTP 403. Die Fehlermeldung enthielt die
vollständige Anfrage-URL mit dem Key als Parameter, am Ende ein `+` (ein URL-kodiertes Leerzeichen).

**Ursache:** Zwei Fehler. Beim Einfügen in den Installationsdialog kam ein Leerzeichen oder
Zeilenumbruch mit, und der Key wurde als URL-Parameter gesendet, also auch in jeder Fehlermeldung
ausgegeben.

**Behebung:** `str_strip_whitespace=True` in den Settings; Key als Header `X-Api-Key`;
Fehlertexte ohne URL (`USDA HTTP 403: API key rejected …`).

**Lehre:** Secrets nie in URLs. Fehlertexte gehen an das LLM und landen im Chatverlauf.

## 6. USDA antwortet zeitweise 400

**Ursache:** Die Suche mit Filter `dataType` lieferte bei ungefähr jeder zweiten Anfrage einen
nginx-400, ohne dass sich die Anfrage änderte.

**Behebung:** Bis zu vier Wiederholungen, danach eine Suche ohne Filter und lokales Filtern.
Später zusätzlich: Alias-Suchtexte ohne `/` (`80% lean meat / 20% fat` löste immer 400 aus).

**Lehre:** Externe APIs sind unzuverlässig. Wiederholen, Ausweichweg vorsehen, Fehler pro Zutat
melden statt das ganze Ergebnis zu verwerfen.

## 7. Hähnchen mit 550 g Eiweiß

**Beleg:** Chicken Handi ergab 550 g Eiweiß für ein Rezept mit 1,2 kg Hähnchen.

**Ursachen:**

1. `"1.2 kg"` wurde als 2 kg gelesen: Der Punkt wurde wie ein Abkürzungspunkt (`tsp.`) entfernt,
   aus „1 2 kg“ blieb „2 kg“.
2. Für Energie nahm der Code den kJ-Wert statt kcal (USDA liefert beide unter „Energy“).
3. Die USDA-Suche nach „chicken“ lieferte „Chicken, chicken roll, roasted“.

**Behebung:** Dezimalpunkt erhalten; Energie nur mit Einheit KCAL; Trefferbewertung und
Alias-Tabelle (`services/usda_matching.py`).

**Lehre:** Plausibilitätsprüfung durch einen Menschen ist Teil des Tests. Mehrere Fehler
überlagern sich und ergeben trotzdem eine plausibel aussehende Zahl.

## 8. Foundation-Lebensmittel ohne Kalorien

**Ursache:** Foundation-Einträge melden Energie als „Energy (Atwater General Factors)“, nicht als
„Energy“. Joghurt hatte deshalb `calories_per_100g: None`.

**Behebung:** Mehrere Energienamen in fester Reihenfolge (`ENERGY_NAMES`).

## 9. Begründung des Nutzers ging verloren

**Beleg:** Ablehnung mit „mag ich nicht“, im Feedback stand `feedback: null`. Ein nachgereichter
Grund wurde als `already_decided` abgewiesen.

**Ursache:** Claude schickte den Grund im Feld `reason`, das schon die Begründung des Vorschlags
enthielt. Nachträgliches Feedback war nicht vorgesehen.

**Behebung:** `reason` als Nutzerfeedback werten, wenn es vom Vorschlag abweicht; erneuter Aufruf
für eine entschiedene Suggestion ergänzt das Feedback.

**Lehre:** Das LLM füllt Parameter nach eigenem Verständnis. Tool-Beschreibungen präzise
formulieren und den Server tolerant gegenüber naheliegenden Varianten machen.

## 10. „milk“ steckt in „oat milk“

**Ursache:** Die Prüfung, ob eine umgeschriebene Anleitung noch ersetzte Zutaten nennt, fand
„milk“ in „oat milk“.

**Behebung:** Namen der aktuellen Zutaten der Variante vor der Suche ausblenden.

**Lehre:** Textprüfungen mit echten Beispielen testen, nicht nur mit dem Fehlerfall.

## 11. Variante doppelt gelöscht

**Beleg (Test):** `SAWarning: DELETE statement on table 'recipes' expected to delete 1 row(s); 0 were matched.`

**Ursache:** Nach dem Löschen einer Variante stand sie noch in `parent.variants` der Session.
Das spätere Löschen des Originals löschte sie ein zweites Mal.

**Behebung:** Variante aus der Sammlung des Originals entfernen (`delete-orphan` löscht die Zeile).

**Lehre:** Warnungen in Tests ernst nehmen. Sie zeigen Fehler, bevor Daten verloren gehen.

## 12. Vergleich meldet −78 % Kalorien

**Beleg (Endabnahme v0.12.0):** Für die vegane Variante meldete `compare_nutrition` −78 % Kalorien und
−93 % Eiweiß. Claude erkannte das und rechnete von Hand mit Etikettwerten weiter.

**Ursache:** Seitan, Haferjoghurt und Hafer-Cuisine fehlen in USDA und zählten als 0. Der Hinweis
stand nur in `notes`, die Prozentzahlen sahen trotzdem verlässlich aus. Eigene Werte ließen sich
nicht speichern.

**Behebung:** `comparable: false`, `difference: null`, Zahlen nur noch in `partial_difference`;
`set_ingredient_matches` nimmt Etikettwerte an.

**Lehre:** Wenn eine Zahl nicht stimmen kann, sollte das Tool sie nicht als Ergebnis ausgeben. Ein
Hinweis daneben genügt nicht.

## 13. macOS: Modul fehlt

**Beleg:** `ModuleNotFoundError: No module named 'sqlalchemy'`, Server gestartet mit `/usr/bin/python3`.

**Ursache:** Das Python-Paket enthält keine Abhängigkeiten; Claude Desktop nutzt das System-Python.

**Behebung:** uv-Paket mit `pyproject.toml` und `uv.lock` (v0.11); auf dem Mac mit Claude Desktop
getestet: Der Host startet sein eigenes uv statt `/usr/bin/python3`. Siehe
[INSTALLATION.md](INSTALLATION.md).
