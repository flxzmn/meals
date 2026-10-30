# Entwicklungsstände v0.2 bis v0.12

| Version | Sprint | Inhalt | Neue Tools | Status |
|---|---|---|---|---|
| v0.2 | 1, 2 | TheMealDB-Suche, SQLite, Repository, Bulk-Rezepte | `search_recipes`, `save_recipes`, `list_recipes`, `delete_recipes` | abgenommen |
| v0.3 | 3 | USDA-Anreicherung, Nutrition Cache, Bulk-Nährwerte | `enrich_recipes`, `get_nutrition` | abgenommen |
| v0.4 | 4 | Ersatz-Wissensbasis, Rezeptanpassung | `add_substitutions`, `find_substitutions`, `list_substitutions`, `delete_substitutions`, `adapt_recipes` | abgenommen |
| v0.5.0 | 5 | Vorschläge, Freigabe, Ablehnung, Feedback | `suggest_substitutions`, `approve_substitutions`, `reject_substitutions`, `list_substitution_feedback` | Abnahme fehlgeschlagen |
| v0.5.1 | 5 | Serverseitiger Pending-Store, Dedup, Constraints, Ablehnungen wirken, Release-Test | `record_substitution_suggestions`, `list_substitution_suggestions` | abgenommen nach zwei Fix-Runden |
| v0.5.2 | 10 (vorgezogen) | USDA-Trefferbewertung, Alias-Tabelle, Aufschlüsselung pro Zutat | – | in Claude Desktop geprüft |
| v0.5.3 | 3 (Nachtrag) | Stück und Löffel über USDA-Portionsgewichte | – | in Claude Desktop geprüft |
| v0.6.0 | 6 | Rezeptvarianten dauerhaft speichern | `save_adapted_recipes`, `list_recipe_variants`, `update_recipe_variants`, `get_recipes` | automatisch getestet |
| v0.7.0 | 7 | Anleitungen an Ersatzzutaten anpassen (LLM) | `rewrite_instructions`, `save_rewritten_instructions` | automatisch getestet |
| v0.8.0 | 8 | Mengenanpassung pro Ersatzregel | `set_substitution_quantities` | automatisch getestet |
| v0.9.0 | 9 | Nährwertvergleich Original gegen Variante | `compare_nutrition` | automatisch getestet |
| v0.10.0 | 10 | Treffer korrigieren und sperren, Übersetzungen | `search_usda_foods`, `list_ingredient_matches`, `set_ingredient_matches`, `reject_ingredient_matches` | automatisch getestet |
| v0.11.0 | 11 | uv-Paket ohne Python-Einrichtung | – | automatisch getestet |
| v0.12.0 | 12 | Dokumentation und Lehrmaterial | – | Endabnahme Windows: vier Befunde |
| v0.12.1 | – | Befunde behoben: ehrlicher Vergleich, Etikettwerte, Berechnung ohne Rezept, Fehlalarm bei Anleitungen | `calculate_nutrition` | uv-Paket auf Windows und macOS bestanden |
| v1.0.0 | – | Manifest für den Release: Name, Beschreibung, Autor, Links, Icon | – | Release-Kandidat |

„Automatisch getestet“: Unit-Tests, MCP-Abnahmetest und Release-Test grün. Die Stände v0.6 bis v0.11
wurden gemeinsam mit v0.12.0 und v0.12.1 in Claude Desktop abgenommen ([TESTPROTOKOLL.md](TESTPROTOKOLL.md)).

## Was sich zwischen den Ständen lernen lässt

| Übergang | Thema für den Kurs |
|---|---|
| v0.4 → v0.5.0 | Ein Tool, das „Vorschläge erzeugt“, aber nur einen Auftrag zurückgibt, erfüllt sein Abnahmekriterium nicht. Tool-Semantik genau definieren. |
| v0.5.0 → v0.5.1 | Zustand gehört auf den Server (Pending-Store), nicht ins Gedächtnis des LLM. Regeln serverseitig prüfen. |
| v0.5.1 → v0.5.3 | Automatische Tests waren grün, erst der Test in Claude Desktop zeigte Key-Leck, kJ statt kcal und falsche Treffer. Siehe [FEHLERANALYSE.md](FEHLERANALYSE.md). |
| v0.6 | Datenmodell-Entscheidung: Varianten als Rezepte mit `parent_id` statt eigener Tabelle; dadurch funktionieren vorhandene Tools sofort. |
| v0.7 | Gleiches Muster wie Sprint 5: Auftrag an das LLM, Ergebnis speichern, Ergebnis prüfen, Herkunft kennzeichnen. |
| v0.8 bis v0.10 | Daten statt Annahmen: Portionsgewichte und Kandidatenlisten kommen aus USDA, Entscheidungen des Menschen werden als Regeln gespeichert. |
| v0.11 | Auslieferung ist Teil des Produkts: gleiche Software, zwei Pakete, unterschiedliche Voraussetzungen. |

## Testumfang

| Stand | Tests (ohne Release) | Release-Tests |
|---|---|---|
| v0.5.1 | 42 | 7 |
| v0.6.0 | 88 | 7 |
| v0.10.0 | 125 | 7 |
| v0.12.0 | 125 | 10 |
| v0.12.1 | 132 | 10 |
