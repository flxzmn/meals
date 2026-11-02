# Übungsaufgaben (Entwurf)

> Entwurf zur Prüfung durch die Kursleitung: Reihenfolge, Umfang und Zeitangaben an den Kurs
> anpassen. Lösungshinweise stehen jeweils darunter und können für die Teilnehmerfassung entfernt
> werden.

## Block A: MCP verstehen (ohne Programmierung)

### A1. Tools beobachten (20 Min.)

Installiere die Erweiterung ([INSTALLATION.md](INSTALLATION.md)) und bitte Claude: „Suche ein
Rezept mit Lachs, speichere es und berechne die Nährwerte.“ Öffne „Meal verwendet“ im Chat.

- Welche Tools wurden in welcher Reihenfolge aufgerufen?
- Welche Parameter hat Claude übergeben?
- Welche Zahl in der Antwort stammt vom Server, welche hat Claude selbst formuliert?

*Hinweis:* `search_recipes` → `save_recipes` → `enrich_recipes` → `get_nutrition`. Pro-Portion-Werte
rechnet Claude selbst aus.

### A2. Woher kommt die Zahl? (20 Min.)

Lass dir `get_nutrition` für das Rezept zeigen und suche in `ingredient_breakdown` die Zutat mit
den meisten Kalorien.

- Welcher USDA-Eintrag wurde verwendet (`usda_match`)? Passt er?
- Wie wurden die Gramm bestimmt (`grams_basis`)?
- Welche Zutaten fehlen in der Summe und warum?

### A3. Fehler im Log finden (30 Min.)

Lies Fall 1 und Fall 5 in [FEHLERANALYSE.md](FEHLERANALYSE.md) nur bis „Beleg“. Formuliere die
Ursache, bevor du weiterliest.

## Block B: Der Mensch entscheidet, der Server erinnert sich

### B1. Lernende Wissensbasis (30 Min.)

Bitte Claude um vegane, nussfreie Ersatzprodukte für Halloumi ohne Tofu. Nimm einen Vorschlag an,
lehne einen mit Begründung ab. Frage in einem **neuen Chat** erneut.

- Was wurde gespeichert (`list_substitution_feedback`)?
- Taucht der abgelehnte Vorschlag wieder auf? Warum nicht?
- Wo wird Tofu ausgeschlossen: von Claude oder vom Server? Wie lässt sich das nachweisen?

*Hinweis:* `excluded_candidates` in `record_substitution_suggestions` zeigt die serverseitige
Filterung.

### B2. Variante anlegen und vergleichen (40 Min.)

Erstelle eine vegetarische Variante eines Fleischrezepts, speichere sie, lass die Anleitung
umschreiben und vergleiche die Nährwerte.

- Welche Mengen hat der Server angepasst (`quantity`)? Welche sind `unverified`?
- Welche Warnungen gab `save_rewritten_instructions`?
- Wie groß ist die Abdeckung im Vergleich, und was bedeutet sie für die Aussagekraft?

### B3. Falscher Treffer (20 Min.)

Finde mit `list_ingredient_matches` einen Treffer, der nicht passt. Korrigiere ihn mit
`search_usda_foods` und `set_ingredient_matches` und rechne neu.

## Block C: Programmieren am Server

### C1. Alias ergänzen (30 Min.)

Ergänze in `services/usda_matching.py` einen Alias für eine Zutat, die falsch zugeordnet wird,
und einen Test in `tests/test_usda_matching.py`.

*Hinweis:* Die exakte USDA-Beschreibung mit `search_usda_foods` ermitteln; der Test nutzt
`search_queries`.

### C2. Neues Tool: Einkaufsliste (60 bis 90 Min.)

Baue `shopping_list(mealdb_ids)`: alle Zutaten mehrerer Rezepte, gleiche Zutaten zusammengefasst,
Mengen in Gramm, wo möglich.

- Tool in `mcp_tools/`, Logik in einem Service, kein SQL im Tool.
- Bulk: eine Liste von Rezepten, ein Aufruf.
- Nicht umrechenbare Mengen sichtbar lassen.
- Test über den In-Memory-MCP-Client nach dem Muster von `tests/test_acceptance_variants.py`.

*Hinweis:* `services.measure_service.ingredient_grams` liefert Gramm und Grundlage.

### C3. Prüfen statt vertrauen (45 Min.)

`save_rewritten_instructions` prüft nur, ob ersetzte Zutaten noch genannt werden. Ergänze eine
Warnung, wenn die neue Anleitung eine Zutat nennt, die nicht in der Variante vorkommt.

- Welche Fehlalarme sind zu erwarten („Salz und Pfeffer“, „Wasser“)?
- Wie hilft `mentioned_terms` mit dem Parameter `keep`?

### C4. Release-Fehler nachstellen (30 Min.)

Baue das Paket einmal mit `mcpb pack .` im Projektordner und vergleiche Größe und Inhalt mit
`python scripts/build_mcpb.py`. Welcher Release-Test würde anschlagen?

### C5. Eval verbessern (45 Min.)

Führe `python scripts/run_evals.py` aus ([EVALS.md](EVALS.md)) und wähle einen Fall, der nicht
bestanden ist. Ändere nur die Beschreibung eines Tools, baue neu, installiere und wiederhole den Fall
mehrmals. Hat sich etwas verbessert? Welcher andere Fall könnte dadurch schlechter werden?

## Block D: Reflexion

- Wo liegt in diesem Projekt die Grenze zwischen dem, was das LLM tun darf, und dem, was der
  Server erzwingt? Nenne drei Beispiele.
- Welche Fehler aus [FEHLERANALYSE.md](FEHLERANALYSE.md) hätten automatische Tests finden können,
  welche nur ein Mensch im Chat?
- Was müsste geschehen, bevor du Nährwerte aus diesem Server einer Person mit Allergie oder
  Diät-Vorgabe zeigst?
