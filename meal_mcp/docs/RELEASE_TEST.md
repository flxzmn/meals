# Release test

Run once per release, after all automated tests are green. Feature behavior is covered by
pytest, the choice of tools by the evals; this test only checks that the bundle installs and runs
in Claude Desktop.

## 1. Automated checks

```powershell
python -m pytest
python -m pytest -m release
```

`pytest -m release` builds `dist/meal-<version>.mcpb` and checks:

- bundle size below 1 MB, only runtime files, no `.env`, database, `.pyc` or old bundles
- the USDA key from the local `.env` does not appear anywhere in the bundle
- manifest has no keys Claude Desktop rejects (e.g. `_meta`), matches `manifest.json` and uses
  server type `uv` (manifest 0.4)
- `user_config.usda_api_key` is required, sensitive and passed as `USDA_API_KEY`
- the server starts from the unpacked bundle with `uv run --frozen` in a fresh environment, lists
  the manifest's tools, answers a tool call and creates its database in the data folder, not in
  the install directory, and the seed rules are loaded (needs `uv`, e.g. `python -m pip install uv`)

Both commands must pass before continuing.

## 2. Smoke test in Claude Desktop

On Windows, and on macOS when the dependencies changed.

| # | Step | Expected | OK |
|---|------|----------|----|
| 1 | Settings → Extensions: remove the old `meal` extension | Extension is gone | |
| 2 | Install `dist/meal-<version>.mcpb` | Preview shows name, version and tool list; no "incompatible" or manifest error | |
| 3 | Enter the USDA API key when asked | Key field is masked, install completes | |
| 4 | Start a **new** chat | Tool menu lists all `meal` tools; the first call may take a while (dependencies are installed) | |
| 5 | Ask: "Suche Chicken Handi, speichere es und berechne die Nährwerte." | `search_recipes`, `save_recipes`, `enrich_recipes`, `get_nutrition` succeed, about 4.250 kcal; no "USDA_API_KEY fehlt" | |
| 6 | Remove the extension, install it again, new chat, ask: "Welche Rezepte habe ich gespeichert?" | Chicken Handi is still there (data folder outside the extension) | |

Tool calls in a running chat always use the server process started with that chat. After
reinstalling, use a new chat, otherwise the old version answers.

If step 2 fails, note the exact error ([FEHLERANALYSE.md](FEHLERANALYSE.md)).

## 3. Evals

`python scripts/run_evals.py --log "<MCP log>"` runs the fixed prompts (variants, comparison,
corrections, servings, export, photos), see [EVALS.md](EVALS.md). A failed case is a finding about
tool descriptions, not automatically a release blocker.

## 4. Weltküche (large run, after changes to parsing or matching)

Save the 51 recipes of the first run (v1.0.0), ask for their nutrition, then for a vegan variant of
each. Fixed IDs make two runs comparable. Run it after a fresh install on an empty data folder: move
`recipe_mcp.db` out of the data folder first ([INSTALLATION.md](INSTALLATION.md)). On the first start the
knowledge base gets the 30 seed rules from `data/substitutions_seed.json`, including milk → oat milk;
check with "Welche Ersatzregeln kennst du?" (`find_substitutions` without ingredients) before the vegan part.

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
| W4 | `hidden_ingredients` names the milk in the saffron of the Lamb Biryani (seed rule milk → oat milk) | |

## 5. Evidence for the acceptance report

- Screenshot of the tool list (step 4)
- MCP log `mcp-server-meal.log` (Claude Desktop: Settings → Developer → Open Logs Folder; usually
  `%APPDATA%\Claude\logs\`, for the Microsoft Store install under
  `%LOCALAPPDATA%\Packages\Claude_*\LocalCache\Roaming\Claude\logs\`)
- Output of `python -m pytest -m release` and of the evals
- Version, date, tester, OS

## Result

| Version | Date | Tester | OS | Automated | Manual | Result |
|---------|------|--------|----|-----------|--------|--------|
| | | | | | | |
