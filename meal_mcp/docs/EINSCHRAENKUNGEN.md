# Bekannte Einschränkungen (v0.12.1)

## Nährwerte

- **Alle Werte sind Schätzungen.** Grundlage sind USDA-Werte pro 100 g und Mengenangaben aus
  Rezepttexten.
- **Portionsgewichte sind Durchschnitte.** „5 onions“ wird mit 148 g pro Zwiebel gerechnet; wie
  groß die Zwiebeln wirklich waren, weiß niemand. Die Grundlage steht in `grams_basis`.
- **Volumen ohne USDA-Portion** wird mit etwa 1 g/ml gerechnet (Joghurt, Sahne). Für Öl oder
  Mehl kann das deutlich abweichen; solche Zutaten stehen in `estimated_volume_conversions`.
- **„to taste“, „a pinch“** und ähnliche Angaben werden nicht gezählt (`uncovered_ingredients`).
- **Mehrdeutige Rezeptangaben** bleiben mehrdeutig: „Chicken 1.2 kg“ kann mit oder ohne Knochen
  gemeint sein. Gerechnet wird mit Fleisch und Haut, roh.
- **USDA-Matching ist eine Heuristik.** Für Zutaten außerhalb der Alias-Tabelle kann der Treffer
  falsch sein. Korrektur mit `reject_ingredient_matches` oder `set_ingredient_matches`. Manche
  Zutaten fehlen in USDA ganz (getrocknete Bockshornkleeblätter, Garam Masala wird als
  Currypulver gerechnet).
- **Lebensmittel ohne USDA-Eintrag** (Seitan, Hafer-Cuisine) zählen erst, wenn Etikettwerte mit
  `set_ingredient_matches` gespeichert sind. Bis dahin meldet `compare_nutrition` `comparable: false`.
- **Portionsgewichte passen nicht immer zur Küche:** Grüne Chili zählt mit 45 g (US-Chili), eine
  indische wiegt eher 5 g.
- **Übersetzungen** decken nur eine Liste gängiger deutscher und britischer Begriffe ab
  (`TRANSLATIONS`).

## Ersatz und Varianten

- **Mengenverhältnisse** (`quantity_ratio`) sind Gewichtsverhältnisse. Regeln wie
  „1 Ei = 1 EL Leinsamen + 3 EL Wasser“ stehen nur als Text in `quantity_note`.
- **Stückzahlen ohne USDA-Portion** werden beim Ersetzen nicht umgerechnet und in
  `unverified_quantities` gemeldet; vorher `enrich_recipes` für das Original ausführen.
- **Umgeschriebene Anleitungen stammen vom LLM.** Der Server prüft nur, ob ersetzte Zutaten noch
  genannt werden, nicht Garzeiten oder Temperaturen. Vor dem Kochen lesen.
- **Tags wie „nut free“ sind keine Produktgarantie.** Antworten enthalten einen Hinweis zur
  Etikettenprüfung.
- **Variantennummern** werden nach dem Löschen der neuesten Variante wiederverwendet.
- **Löschen eines Originals** löscht seine Varianten mit.
- Mit `diet` in den Constraints meldet `adapt_recipes` jede Zutat ohne Ersatzregel als fehlend,
  auch Gewürze.

## Installation und Betrieb

- **Python-Paket:** braucht ein System-Python 3.11+ mit den Paketen aus `requirements.txt`.
- **uv-Paket:** in Claude Desktop unter Windows und macOS getestet, aber nicht auf einem Rechner ganz
  ohne Python. Der erste Start braucht Internet für die Abhängigkeiten.
- **Ein laufender Chat** nutzt nach einer Neuinstallation weiter den alten Serverprozess.
- **Datenbank:** Neue Spalten werden ergänzt, umbenannte oder gelöschte nicht migriert. Eine
  Neuinstallation beginnt leer.
- **USDA-Limit:** 1.000 Anfragen pro Stunde und Key. Das Anreichern lädt pro Zutat eine Suche und
  einen Detaildatensatz; Ergebnisse werden zwischengespeichert.
- Der volle Testablauf lief nur unter Windows 11 mit Claude Desktop 4.29; auf macOS (arm64) wurde
  das uv-Paket mit Installation und Nährwertberechnung geprüft.
