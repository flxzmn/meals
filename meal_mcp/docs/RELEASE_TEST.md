# Release test

Run once per release, after all automated tests are green. Feature behavior is covered by
pytest; this test only checks that the bundle installs and runs in Claude Desktop.

## 1. Automated checks

```powershell
python -m pytest
python -m pytest -m release
```

`pytest -m release` builds `dist/meal-<version>.mcpb` and `dist/meal-<version>-uv.mcpb` and checks:

- bundle size below 1 MB, only runtime files, no `.env`, database, `.pyc` or old bundles
- the USDA key from the local `.env` does not appear anywhere in the bundle
- manifest has no keys Claude Desktop rejects (e.g. `_meta`) and matches `manifest.json`
- `user_config.usda_api_key` is required, sensitive and passed as `USDA_API_KEY`
- the server starts from the unpacked bundle exactly as the manifest describes, lists the
  manifest's tools, answers a tool call and creates its database in the install directory
- the uv bundle contains `pyproject.toml` and `uv.lock` but no dependencies, its manifest differs
  only in `server` and `manifest_version`, and it starts with `uv run --frozen` in a fresh
  environment (needs `uv`, e.g. `python -m pip install uv`)

Both commands must pass before continuing.

## 2. Manual check in Claude Desktop

| # | Step | Expected | OK |
|---|------|----------|----|
| 1 | Settings → Extensions: remove the old `meal` extension | Extension is gone | |
| 2 | Install `dist/meal-<version>.mcpb` | Preview shows name, version and tool list, no error | |
| 3 | Enter the USDA API key when asked | Key field is masked, install completes | |
| 4 | Start a **new** chat | Tool menu lists all `meal` tools, including `record_substitution_suggestions` | |
| 5 | Ask: "Schlage vegane, nussfreie Ersatzprodukte für Halloumi vor, aber kein Tofu." | Claude calls `suggest_substitutions`, then `record_substitution_suggestions`; tofu appears in `excluded_candidates` | |
| 6 | Approve one suggestion, reject another | `approve_substitutions` / `reject_substitutions` succeed | |
| 7 | Ask: "Zeig mir das Substitutions-Feedback." | Both entries, with constraints | |
| 8 | Ask: "Suche ein Rezept mit Chicken und berechne die Nährwerte." | `search_recipes`, `save_recipes`, `enrich_recipes` succeed (checks the USDA key) | |
| 9 | Ask: "Mach das Rezept vegan, ohne Tofu, und speichere die Variante." | `adapt_recipes`, then `save_adapted_recipes`; answer names an ID like `52795-v1` | |
| 10 | In a **new** chat ask: "Zeig mir meine gespeicherten Rezeptvarianten." | `list_recipe_variants` / `get_recipes` show the variant with constraints and changes; the original is unchanged | |
| 11 | Ask to change an ingredient of the variant, then its nutrition | `update_recipe_variants`, then `enrich_recipes` / `get_nutrition` on the variant ID succeed | |
| 12 | Ask: "Pass die Anleitung der Variante an die neuen Zutaten an." | `rewrite_instructions`, then `save_rewritten_instructions`; new text names the substitutes, no warning, `instructions_source` is `llm` | |
| 13 | Ask: "Ersetze in dem Rezept Hähnchen durch Kichererbsen, Verhältnis 0,8, und speichere die Variante." | `set_substitution_quantities` or `add_substitutions` with `quantity_ratio`; variant shows the scaled amount, not the original count | |
| 14 | Ask: "Vergleiche die Nährwerte der Variante mit dem Original." | `compare_nutrition` returns both totals, differences in percent, coverage and per-ingredient effects | |
| 15 | Ask: "Bockshornklee ist als Samen zugeordnet, gemeint sind getrocknete Blätter. Korrigiere das." | `list_ingredient_matches`, then `reject_ingredient_matches` or `search_usda_foods` + `set_ingredient_matches`; after `enrich_recipes` with refresh the choice is kept | |
| 16 | Ask: "Berechne die Nährwerte für 500 g Hähnchen und 2 Zwiebeln." (German names) | `calculate_nutrition`; matches are "Chicken, broilers or fryers ..." and "Onions, raw", about 1.190 kcal | |
| 17 | Ask: "Seitan hat laut Etikett 140 kcal, 25 g Eiweiß, 2 g Fett und 5 g Kohlenhydrate pro 100 g. Speichere das und vergleiche nochmal." | `set_ingredient_matches` with values; `compare_nutrition` counts seitan; `comparable` is true once all substitutes have data | |
| 18 | Ask: "Chicken Handi reicht für 4 Portionen. Wie viele Kalorien hat eine Portion?" | `set_recipe_servings`, then `get_nutrition` with `per_serving` (about 1.060 kcal) | |
| 19 | Ask: "Rechne Chicken Handi auf 6 Portionen um." | `scale_recipes`: chicken 1.8 kg, "to taste" stays; nothing is saved | |
| 20 | Ask: "Sichere meine Rezepte und Regeln in einer Datei." | `export_data` names a file in the data folder | |
| 21 | Remove the extension, install it again, new chat, ask: "Welche Rezepte habe ich gespeichert?" | The recipes are still there (data folder outside the extension) | |

### uv bundle (recommended, Sprint 11)

Repeat steps 1–4 and 8 with `dist/meal-<version>-uv.mcpb`, on Windows and on macOS (ideally a Mac
without the Python packages, where the python bundle fails with `No module named 'sqlalchemy'`).

| # | Step | Expected | OK |
|---|------|----------|----|
| U1 | Install `dist/meal-<version>-uv.mcpb` | No "incompatible" or manifest error | |
| U2 | First tool call in a new chat | Works; the first start may take a while (dependencies are installed) | |
| U3 | Step 8 (USDA) | No "USDA_API_KEY fehlt" error, so `user_config` reaches the server | |

If U1 fails, note the exact error; the python bundle is the fallback.

Tool calls in a running chat always use the server process started with that chat. After
reinstalling, use a new chat (step 4), otherwise the old version answers.

### Weltküche (large run)

Save the 51 recipes of the first run (v1.0.0), ask for their nutrition, then for a vegan variant of
each. Fixed IDs make two runs comparable; run it first after a fresh install, on an empty data folder.

```
52795, 53053, 52843, 52827, 52820, 53034, 52773, 53151, 52963, 53219, 52945, 53065, 53191, 53238,
52821, 53051, 52814, 53196, 52997, 53073, 52805, 52808, 52785, 53027, 53028, 53091, 53262, 53287,
53112, 53114, 53113, 53472, 53006, 53009, 53057, 53019, 53078, 52832, 52908, 52982, 52844, 53060,
53134, 53334, 53482, 52937, 52819, 52840, 52804, 53104, 53103
```

| # | Expected | OK |
|---|---|---|
| W1 | `enrich_recipes` reports `complete: false` and is called again until `complete: true`; no timeout | |
| W2 | `get_nutrition`, `adapt_recipes` and `compare_nutrition` answer compact above 5 recipes, no token limit error | |
| W3 | No amount is obviously wrong: check `1/2`, `1½`, `2 x 400g`, `1 can` in `compact=false` for a few recipes | |
| W4 | `hidden_ingredients` names the milk in the saffron of the Lamb Biryani (needs a rule milk → oat milk) | |

### Evals

`python scripts/run_evals.py --log "<MCP log>"` runs the fixed prompts, see [EVALS.md](EVALS.md).
A failed case is a finding about tool descriptions, not automatically a release blocker.

## 3. Evidence for the acceptance report

- Screenshot of the tool list (step 4) and of the halloumi run (step 5)
- MCP log `mcp-server-meal.log` (Claude Desktop: Settings → Developer → Open Logs Folder; usually
  `%APPDATA%\Claude\logs\`, for the Microsoft Store install under
  `%LOCALAPPDATA%\Packages\Claude_*\LocalCache\Roaming\Claude\logs\`)
- Output of `python -m pytest -m release`
- Version, date, tester, OS

## Result

| Version | Date | Tester | OS | Automated | Manual | Result |
|---------|------|--------|----|-----------|--------|--------|
| | | | | | | |
