# Bekannte Einschränkungen (v1.2.0)

## Nährwerte

- **Alle Werte sind Schätzungen.** Grundlage sind USDA-Werte pro 100 g und Mengenangaben aus
  Rezepttexten.
- **Portionsgewichte sind Durchschnitte.** „5 onions“ wird mit 148 g pro Zwiebel gerechnet; wie
  groß die Zwiebeln wirklich waren, weiß niemand. Die Grundlage steht in `grams_basis`.
- **Volumen ohne USDA-Portion** wird mit etwa 1 g/ml gerechnet (Joghurt, Sahne), trockene Lebensmittel
  wie Mehl oder Reis mit einer typischen Dichte. Solche Zutaten stehen in `estimated_volume_conversions`.
- **„Pinch“ und „Dash“** zählen mit typischen 0,4 und 0,6 g. **„to taste“, „Bunch“, „Handful“** werden nicht
  gezählt (`uncovered_ingredients`).
- **Behälter** („1 can“, „1 Packet“, „1 pot“) werden nicht geschätzt, denn ihre Größe steht nicht im
  Rezept. Sie bleiben ungezählt, auch wenn sie eine Hauptzutat sind. Abhilfe: Menge in Gramm eintragen.
- **Abdeckung zählt Zutaten, nicht Gewicht.** Fehlende Lorbeerblätter senken sie genauso wie fehlende Bohnen.
  Welche Zutat fehlt, steht in `uncovered_ingredients`.
- **`hidden_ingredients`** findet nur Zutaten, für die es eine Ersatzregel gibt. Fisch in einer
  Sushi-Anleitung bleibt ohne Regel unsichtbar.
- **Eine Ersatzregel gilt für jede Verwendung.** Gekochte Eier und Eier im Teig bekommen denselben Ersatz.
- **Mehrdeutige Rezeptangaben** bleiben mehrdeutig: „Chicken 1.2 kg“ kann mit oder ohne Knochen
  gemeint sein. Gerechnet wird mit Fleisch und Haut, roh.
- **USDA-Matching ist eine Heuristik.** Für Zutaten außerhalb der Alias-Tabelle kann der Treffer
  falsch sein. Korrektur mit `reject_ingredient_matches` oder `set_ingredient_matches`. Manche
  Zutaten fehlen in USDA ganz (getrocknete Bockshornkleeblätter, Garam Masala wird als
  Currypulver gerechnet).
- **Lebensmittel ohne USDA-Eintrag** (Seitan, Hafer-Cuisine, Hefeflocken, Doubanjiang,
  Sichuanpfeffer) zählen erst, wenn Etikettwerte mit
  `set_ingredient_matches` gespeichert sind. Bis dahin meldet `compare_nutrition` `comparable: false`.
- **Portionsgewichte passen nicht immer zur Küche:** Grüne Chili zählt mit 45 g (US-Chili), eine
  indische wiegt eher 5 g.
- **Übersetzungen** decken nur eine Liste gängiger deutscher und britischer Begriffe ab
  (`TRANSLATIONS`). Unbekannte deutsche Namen bleiben `nutrition_missing`, englische Namen treffen
  sicherer.
- **Ein Aufruf pro Zutatenliste:** `calculate_nutrition` rechnet eine Liste, nicht mehrere. Für viele
  freie Rezepte ist es besser, sie als Varianten zu speichern und gesammelt mit `get_nutrition` zu rechnen.

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

## Fotos

- **Fotos gehören TheMealDB.** `download_recipe_images` speichert sie nur lokal. Wer ein Rezeptbuch
  veröffentlicht, nennt TheMealDB als Quelle.
- **Varianten haben kein eigenes Foto.** Eine vegane Variante zeigt das Foto des Originals.

## Installation und Betrieb

- **Paket:** in Claude Desktop unter Windows und macOS getestet, aber nicht auf einem Rechner ganz
  ohne Python. Der erste Start braucht Internet für die Abhängigkeiten.
- **Ein laufender Chat** nutzt nach einer Neuinstallation weiter den alten Serverprozess.
- **Datenbank:** Neue Spalten werden ergänzt, umbenannte oder gelöschte nicht migriert. Der Wechsel
  von v1.0 nimmt die alte Datenbank nur mit, wenn sie beim ersten Start noch vorhanden ist
  ([INSTALLATION.md](INSTALLATION.md)).
- **Portionen:** TheMealDB nennt keine Portionszahl. `per_serving` bleibt leer, bis jemand sie angibt.
  Beim Skalieren bleiben Mengen ohne Zahl („to taste“) unverändert; Garzeiten und Topfgrößen
  ändert das Tool nicht.
- **Evals** prüfen nur die Wahl der Tools, nicht die Qualität der Antwort, und das Ergebnis kann
  zwischen zwei Läufen schwanken ([EVALS.md](EVALS.md)).
- **USDA-Limit:** 1.000 Anfragen pro Stunde und Key. Das Anreichern lädt pro Zutat eine Suche und
  einen Detaildatensatz; Ergebnisse werden zwischengespeichert.
- Der volle Testablauf lief nur unter Windows 11 mit Claude Desktop 4.29; auf macOS (arm64) wurde
  das Paket mit Installation und Nährwertberechnung geprüft.
