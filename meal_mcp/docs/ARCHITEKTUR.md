# Architektur

Meal MCP ist ein lokaler MCP-Server für Claude Desktop. Er sucht Rezepte bei TheMealDB, speichert
sie in SQLite, reichert Zutaten mit Nährwerten aus USDA FoodData Central an und verwaltet eine
lernende Wissensbasis für Zutatenersatz. Stand: v1.2.0.

## Schichten

```
Claude Desktop (LLM, Chat, Nutzerentscheidungen)
    │  MCP über STDIO
    ▼
mcp_tools/      32 Tools. Nur Ein- und Ausgabe, keine Fachlogik.
    ▼
services/       Fachlogik: Bulk-Verarbeitung, Filter, Umrechnung, Vergleich.
    ▼
repo/           Lesen und Schreiben in SQLite (SQLAlchemy).
    ▼
db/             Engine, Session, Tabellenmodelle, Migration neuer Spalten.

Externe Quellen: services/mealdb_service.py → TheMealDB
                 services/usda_service.py   → USDA FoodData Central
```

Regel für Erweiterungen: Ein neues Tool ruft genau einen Service auf. Ein Service spricht nie
direkt mit MCP und ein Repository nie mit einer externen API.

## Zentrale Designentscheidungen

| Entscheidung | Begründung |
|---|---|
| **Claude Desktop ist das LLM.** Der Server erzeugt keine Texte, sondern liefert strukturierte Aufträge und speichert die Antworten (Vorschläge in Sprint 5, Anleitungen in Sprint 7). | Kein zweiter API-Key, keine Kosten im Server, der Mensch sieht jeden Vorschlag im Chat. |
| **Der Server prüft, was das LLM liefert.** Ausschlüsse, Pflicht-Tags, frühere Ablehnungen und übrig gebliebene Zutatennamen werden serverseitig kontrolliert. | Ein LLM vergisst Regeln. Prüfungen im Code sind reproduzierbar und testbar. |
| **Bulk-Tools mit Listen.** Fast jedes Tool nimmt mehrere Rezepte, Zutaten oder Regeln. | Weniger Tool-Aufrufe pro Chat, kürzere Antwortzeiten. |
| **Varianten sind Rezepte mit `parent_id`.** | `enrich_recipes`, `get_nutrition`, `delete_recipes` und der Vergleich funktionieren ohne Sonderfälle. |
| **Schätzungen bleiben sichtbar.** `grams_basis`, `estimated`, `coverage`, `uncovered_ingredients`. | Nährwerte aus Rezepttexten sind nie exakt; der Nutzer soll sehen, woher eine Zahl kommt. |
| **Allowlist-Build.** Das Paket enthält nur Laufzeitdateien. | Keine `.env`, keine Datenbank, kein `.venv` im Paket (früher über 100 MB, jetzt ca. 170 KB). |

## Datenmodell

| Tabelle | Inhalt | Seit |
|---|---|---|
| `recipes` | Rezepte und Varianten (`parent_id`, `constraints`, `changes`, `instructions_source`) | v0.2 / v0.6 |
| `ingredients` | Zutaten mit `measure`, `normalized_name`, `estimated_grams` | v0.2 |
| `nutrition_cache` | USDA-Treffer pro Zutat: Nährwerte pro 100 g, `portions` (Portionsgewichte) | v0.3 / v0.5.3 |
| `ingredient_match_rules` | Manuell gewählte und abgelehnte USDA-Treffer | v0.10 |
| `substitutions` | Aktive Ersatzregeln mit `quantity_ratio` und `quantity_note` | v0.4 / v0.8 |
| `substitution_suggestions` | Vorschläge im Status `pending`, `approved`, `rejected` | v0.5.1 |
| `substitution_feedback` | Entscheidungen mit Constraints, Hash und Nutzerbegründung | v0.5 |

Neue Spalten bestehender Tabellen legt `db.db.add_missing_columns` beim Start an
(`ADDED_COLUMNS`). Neue Tabellen erzeugt `create_all`. Es gibt keine Migration für umbenannte oder
gelöschte Spalten.

## Abläufe

### Rezept und Nährwerte

```
search_recipes → save_recipes → enrich_recipes → get_nutrition
                                      │
                                      ├─ Übersetzung (Hähnchen → chicken), Alias-Tabelle
                                      ├─ USDA-Suche, Bewertung aller Treffer, manuelle Regeln
                                      └─ Portionsgewichte (1 whole onion = 148 g)
```

**Treffer.** Die USDA-Suche sortiert nach Textrelevanz, der erste Treffer ist oft ein Gericht
(„Chicken, chicken roll, roasted“). `services/usda_matching.py` übersetzt deshalb zuerst
(`TRANSLATIONS`: Hähnchen → chicken, courgette → zucchini), ordnet häufige Zutaten fest einem
generischen USDA-Eintrag zu (`ALIASES`) und bewertet sonst alle Treffer: Jedes Wort der Zutat muss
vorkommen, roh gewinnt, Gerichte, Marken und Verarbeitetes verlieren. Ohne plausiblen Treffer gilt
die Zutat als fehlend statt falsch. Treffer werden zwischengespeichert; nach einer Änderung am
Matching `enrich_recipes` mit `refresh=true`.

**Mengen** werden in dieser Reihenfolge in Gramm umgerechnet (`grams_basis`):

1. Gewicht (`1.2 kg`): exakt.
2. Stück und Löffel (`5`, `8 cloves`, `1 tsp`): USDA-Portionsgewicht des Treffers, z. B.
   `1 whole = 148 g`. Kennt USDA nur Teelöffel, werden Esslöffel und Tassen hochgerechnet.
3. Übrige Volumen: etwa 1 g/ml (`estimated_volume_conversions`).

Was sich nicht umrechnen lässt („to taste“), bleibt sichtbar ungezählt. `estimated_grams` ist ein
Zwischenspeicher und wird beim Start mit dem aktuellen Parser neu berechnet.

### Lernende Ersatz-Wissensbasis (Sprint 5)

```
suggest_substitutions ──► suggestion_request (Pflicht-Tags, zu meidende Ziele)
        │
Claude erzeugt Kandidaten
        ▼
record_substitution_suggestions ──► Server filtert Verstöße und frühere Ablehnungen → pending
        │
Nutzer entscheidet im Chat
        ▼
approve_substitutions / reject_substitutions ──► Regel aktiv / Ablehnung mit Begründung
        │
        ▼
find_substitutions, adapt_recipes nutzen die Regel
```

### Varianten (Sprints 6 bis 9)

```
adapt_recipes ──► Variante mit angepassten Mengen (quantity_ratio, Portionsgewichte)
     ▼
save_adapted_recipes ──► eigene ID 52795-v1, Original unverändert
     ▼
rewrite_instructions ──► Claude schreibt Anleitung ──► save_rewritten_instructions (llm)
     ▼
update_recipe_variants (Handkorrektur) / compare_nutrition (Original gegen Variante)
```

Ersatzmengen folgen dem `quantity_ratio` der Regel (Gramm Ersatz pro Gramm Original): Gewicht und
Volumen werden skaliert, Stückzahlen über das Portionsgewicht des Originals in Gramm umgerechnet
(„4 chicken breasts“ → 696 g Kichererbsen statt „4 chickpeas“). Ein Vergleich mit einem Ersatz ohne
Nährwerte meldet `comparable: false`, weil der Ersatz sonst als 0 zählen würde.

### USDA-Treffer korrigieren (Sprint 10)

```
list_ingredient_matches ──► falscher Treffer?
     ├─ reject_ingredient_matches ──► nächstbester Treffer oder no_alternative
     └─ search_usda_foods ──► set_ingredient_matches (fdc_id oder Etikettwerte)
```

Entscheidungen stehen in `ingredient_match_rules` und überstehen `enrich_recipes` mit `refresh=true`.

## Tools nach Bereich

| Bereich | Tools |
|---|---|
| Rezepte | `search_recipes`, `save_recipes`, `list_recipes`, `get_recipes`, `delete_recipes`, `download_recipe_images` |
| Nährwerte | `enrich_recipes`, `get_nutrition`, `calculate_nutrition`, `compare_nutrition` |
| USDA-Treffer | `search_usda_foods`, `list_ingredient_matches`, `set_ingredient_matches`, `reject_ingredient_matches` |
| Ersatzregeln | `add_substitutions`, `find_substitutions`, `list_substitutions`, `delete_substitutions`, `adapt_recipes` |
| Lernen | `suggest_substitutions`, `record_substitution_suggestions`, `approve_substitutions`, `reject_substitutions`, `list_substitution_suggestions` |
| Varianten | `save_adapted_recipes`, `update_recipe_variants`, `rewrite_instructions`, `save_rewritten_instructions` |
| Portionen | `set_recipe_servings`, `scale_recipes` |
| Daten | `export_data`, `import_data` |

## Wo was steht

| Thema | Datei |
|---|---|
| Konfiguration, API-Key, Datenbankpfad | `config/settings.py` |
| Constraints, Hash, Label-Hinweis | `services/constraint_service.py` |
| Mengen, Portionsgewichte, Skalierung | `services/measure_service.py` |
| USDA-Abfragen, Retries, Fehlertexte ohne Key | `services/usda_service.py` |
| Aliase, Übersetzungen, Trefferbewertung | `services/usda_matching.py` |
| Build der Pakete | `scripts/build_mcpb.py` |
