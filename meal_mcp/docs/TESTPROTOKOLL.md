# Testprotokoll

## Teststufen

| Stufe | Befehl | Prüft | Netz |
|---|---|---|---|
| Unit-Tests | `python -m pytest` | Services und Repositories mit In-Memory-SQLite | nein |
| MCP-Abnahmetests | `python -m pytest` (in den Unit-Tests enthalten) | Echte FastMCP-Tools über einen In-Memory-MCP-Client, wie Claude Desktop sie aufruft | nein (USDA und TheMealDB ersetzt) |
| Release-Test | `python -m pytest -m release` | Beide Pakete: Inhalt, Manifest, kein Key, Serverstart aus dem entpackten Paket | nur für das uv-Paket (lädt Abhängigkeiten) |
| Manueller Test | [RELEASE_TEST.md](RELEASE_TEST.md) | Installation und Chat in Claude Desktop | ja |
| API-Check | `python -m tests.manual_api_check` | TheMealDB und USDA live | ja |

## Testdateien

| Datei | Tests | Inhalt |
|---|---|---|
| `test_db.py` | 3 | Speichern, Cache, Migration neuer Spalten |
| `test_measure_service.py` | 10 | Mengen, Dezimalzahlen, Portionsgewichte |
| `test_usda_service.py` | 9 | Key im Header, Fehlertexte, kcal statt kJ, Wiederholungen, Portionen |
| `test_usda_matching.py` | 12 | Trefferbewertung mit echten USDA-Suchergebnissen |
| `test_nutrition_service.py` | 4 | Cache, Refresh, Aufschlüsselung, Portionsgewichte |
| `test_substitutions.py` | 5 | Ersatzregeln, Rezeptanpassung |
| `test_substitution_learning.py` | 14 | Vorschlags-Workflow, Dedup, Ablehnungen, Feedback |
| `test_variants.py` | 9 | Varianten speichern, bearbeiten, löschen |
| `test_instructions.py` | 9 | Anleitung umschreiben, Restbegriffe |
| `test_quantities.py` | 7 | Mengenverhältnisse, Stück zu Gramm |
| `test_compare.py` | 7 | Nährwertvergleich, Abdeckung |
| `test_matches.py` | 10 | Treffer setzen, sperren, Übersetzungen |
| `test_acceptance_sprint5.py` | 11 | Abnahme Sprint 5 (MCP) |
| `test_acceptance_variants.py` | 18 | Abnahme Sprints 6 bis 9 (MCP) |
| `test_acceptance_matching.py` | 4 | Abnahme Sprint 10 (MCP) |
| `test_release.py` | 10 | Release beider Pakete (Marker `release`) |

## Abnahmekriterien und Tests

| Sprint | Kriterium | Test |
|---|---|---|
| 5 | Zehn Kriterien aus dem Übergabeprotokoll | `test_acceptance_sprint5.py::test_01` bis `test_10` |
| 6 | Variante mit eigener ID gespeichert | `test_acceptance_variants.py::test_01_adapted_recipe_is_saved_with_own_id` |
| 6 | Original bleibt unverändert | `::test_02_original_recipe_stays_unchanged`, `::test_06_original_cannot_be_edited` |
| 6 | Constraints und Änderungen gespeichert | `::test_03_constraints_and_changes_are_stored` |
| 6 | Variante später anzeigen und bearbeiten | `::test_04_variant_is_shown_again_later`, `::test_05_variant_can_be_edited` |
| 6 | Kein Duplikat, Bulk, Löschen | `::test_07`, `::test_08`, `::test_10` |
| 7 | Auftrag nennt ersetzte Zutaten | `::test_s7_01_rewrite_request_names_replaced_ingredients` |
| 7 | Anleitung gespeichert und als LLM-Text markiert, Original unverändert | `::test_s7_02_rewritten_instructions_are_stored_and_marked` |
| 7 | Übrig gebliebene Zutatennamen werden gemeldet | `::test_s7_03_leftover_ingredient_mentions_are_reported` |
| 8 | Stückzahl wird zu Gramm, nicht 1:1 übernommen | `::test_s8_01_piece_count_is_converted_to_grams` |
| 8 | Verhältnis pro Ersatzpaar, in Variante sichtbar | `::test_s8_02_ratio_rule_per_pair_is_used_and_saved_in_variant` |
| 8 | Gelernter Vorschlag behält Mengenregel | `::test_s8_03_learned_suggestion_keeps_its_quantity_rule` |
| 9 | kcal, Makros, Differenz absolut und in Prozent, Abdeckung | `::test_s9_01_compare_nutrition_of_variant_and_original` |
| 9 | Nährwerte von Varianten | `::test_09_nutrition_works_for_variants` |
| 10 | Treffer sichtbar, sperren, von Hand setzen | `test_acceptance_matching.py::test_01` bis `test_03` |
| 10 | Übersetzungen, Kichererbsen aus der Dose | `test_matches.py::test_german_and_international_names_are_translated`, `::test_plain_chickpeas_mean_canned_not_dried` |
| 11 | uv-Paket ohne Abhängigkeiten, startet mit `uv run --frozen` | `test_release.py::test_uv_bundle_contains_project_files_but_no_dependencies`, `::test_server_starts_from_uv_bundle` |

## Endabnahme v0.12.0 in Claude Desktop (Windows, Python-Paket)

Schritte A bis I bestanden im Kern; vier Befunde führten zu v0.12.1: Fehlalarm bei umformulierten
Ersatznamen, irreführender Vergleich bei ungezählten Ersatzzutaten, keine eigenen Nährwerte,
keine Berechnung ohne Rezept.

## Endabnahme uv-Paket v0.12.1 in Claude Desktop

| System | Installation | Start | USDA-Key | Chicken Handi |
|---|---|---|---|---|
| Windows 11, Claude Desktop 4.29, System-Python ohne Pakete | bestanden | bestanden, `uv-runtime` 0.9.7 mit eigener `.venv` | angekommen | 4.358 kcal, 15 von 16 Zutaten |
| macOS arm64 | bestanden | bestanden, `uv-runtime` 0.9.7 | angekommen | 4.358 kcal, 15 von 16 Zutaten |

Nachtest der Korrekturen aus v0.12.1 in Claude Desktop (`RELEASE_TEST.md`, Schritte 16 und 17,
Windows 11): bestanden. `compare_nutrition` mit Chicken Handi und einer erfundenen Ersatzzutat ohne
USDA-Treffer meldete zuerst `comparable: false` und `difference: null`. Nach dem Speichern der
Etikettwerte (140 kcal pro 100 g) meldete es `comparable: true` und −900 kcal (−20,7 %).

## Lauf über 51 Rezepte

Der Protokolllauf „Weltküche“ mit v1.0.0 lieferte die Befunde für v1.1.0: 19 von 51 Gerichten verlässlich,
22 mit Lücken, 10 unbrauchbar (Einschätzung von Claude im Chat). Dieselben Rezepte mit v1.1.0 wurden live gegen
USDA wiederholt, ohne Claude: Das Anreichern brauchte vier Aufrufe von je höchstens 44 s; 6 Gerichte liegen
unter 60 % Abdeckung, 28 bei mindestens 80 %. Ein Lauf in Claude Desktop steht aus.

Offen: ein Rechner ganz ohne Python, der Lauf von v1.1.0 in Claude Desktop.

## Läufe

| Datum | System | Unit + MCP | Release | Manuell |
|---|---|---|---|---|
| 2026-10-29 | v0.12.0, Windows 11, Python 3.15, uv 0.13.6, mcpb 0.3.5 | 125 bestanden | 10 bestanden | siehe oben |
| 2026-10-30 | v0.12.1, wie oben | 132 bestanden | 10 bestanden | siehe oben |

Zusätzlich live gegen USDA geprüft (nicht automatisiert): Chicken Handi mit 15 von 16 Zutaten,
etwa 4.360 kcal; Vergleich mit veganer Variante; deutsche Zutatennamen; Ablehnung eines Treffers
ohne Alternative (Bockshornklee).
