# Meal MCP v1.0.0

Local FastMCP server for bulk recipe lookup, storage, USDA nutrition enrichment and a learning substitution knowledge base.

## Scope

- Bulk recipe search, save and delete
- SQLite recipe and ingredient storage
- Bulk USDA enrichment with concurrent requests
- Local nutrition cache to avoid repeated USDA calls
- Approximate measurement conversion for common mass and volume units
- Bulk nutrition summaries with missing-data feedback
- Substitution knowledge base and bulk recipe adaptation
- Learning workflow for new substitutions with pending suggestions, approval, rejection and feedback
- Recipe variants: adapted recipes are saved with their own ID and can be shown and edited later
- Instruction rewriter: variant instructions are rewritten for the substituted ingredients
- Quantity adjustment: substitute amounts follow a ratio per substitution, piece counts become grams
- Nutrition comparison of a variant with its original
- USDA matches can be inspected, corrected by hand and rejected; German ingredient names work

## Documentation

Course material and guides (German):

| Document | Content |
|---|---|
| [docs/ARCHITEKTUR.md](docs/ARCHITEKTUR.md) | Layers, design decisions, data model, workflows, tools by area |
| [docs/INSTALLATION.md](docs/INSTALLATION.md) | Installation on Windows and macOS, both bundles, common problems |
| [docs/BUILD.md](docs/BUILD.md) | Building the MCPB bundles, release steps, pitfalls |
| [docs/RELEASE_TEST.md](docs/RELEASE_TEST.md) | Automated and manual release test in Claude Desktop |
| [docs/TESTPROTOKOLL.md](docs/TESTPROTOKOLL.md) | Test levels, test files, acceptance criteria per sprint, results |
| [docs/EINSCHRAENKUNGEN.md](docs/EINSCHRAENKUNGEN.md) | Known limitations |
| [docs/FEHLERANALYSE.md](docs/FEHLERANALYSE.md) | Thirteen real errors from the logs: symptom, cause, fix, lesson |
| [docs/VERSIONEN.md](docs/VERSIONEN.md) | Versions v0.2 to v0.12 compared |
| [docs/UEBUNGEN.md](docs/UEBUNGEN.md) | Exercises (draft) |

## Setup (Windows PowerShell)

```powershell
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Enter your USDA key in `.env`.

## Tests

```powershell
python -m pytest
python -m pytest -m release
python -m tests.manual_api_check
```

`pytest -m release` builds the MCPB bundle and checks it (manifest, contents, server start from
the bundle). See `docs/RELEASE_TEST.md` for the full release test including the manual check in
Claude Desktop.

## Start MCP server

```powershell
python main.py
```

The server uses STDIO and waits for an MCP client such as Claude Desktop.

## MCP tools

- `search_recipes(queries)`
- `save_recipes(mealdb_ids)`
- `list_recipes()`
- `get_recipes(mealdb_ids)`
- `delete_recipes(mealdb_ids)`
- `enrich_recipes(mealdb_ids, refresh)`
- `get_nutrition(mealdb_ids)`
- `calculate_nutrition(ingredients)`
- `compare_nutrition(mealdb_ids, enrich)`
- `search_usda_foods(queries)`
- `list_ingredient_matches(ingredients)`
- `set_ingredient_matches(matches)`
- `reject_ingredient_matches(rejections)`
- `add_substitutions(substitutions)`
- `find_substitutions(ingredients, constraints)`
- `list_substitutions()`
- `set_substitution_quantities(rules)`
- `delete_substitutions(substitutions)`
- `adapt_recipes(mealdb_ids, constraints)`
- `suggest_substitutions(ingredients, constraints)`
- `record_substitution_suggestions(suggestions, constraints)`
- `approve_substitutions(suggestions, constraints)`
- `reject_substitutions(suggestions, constraints)`
- `list_substitution_suggestions(status)`
- `list_substitution_feedback(accepted)`
- `save_adapted_recipes(variants)`
- `list_recipe_variants(source_mealdb_ids)`
- `update_recipe_variants(updates)`
- `rewrite_instructions(mealdb_ids, force)`
- `save_rewritten_instructions(rewrites)`

## Substitution learning workflow

1. `suggest_substitutions` returns active substitutions, pending suggestions and a structured
   `suggestion_request` for ingredients without either (required tags, targets to avoid).
2. Claude generates candidates and stores them with `record_substitution_suggestions`. The server
   removes candidates that violate the constraints or were rejected before under the same constraints.
3. `approve_substitutions` re-validates the constraints and activates the rule;
   `reject_substitutions` records the rejection. Both only work on recorded pending suggestions.
4. Approved rules are found by `find_substitutions` and `adapt_recipes`.

Constraints example:

```json
{"diet": "vegan", "required_tags": ["nut free"], "excluded_ingredients": ["tofu"]}
```

Tags such as `nut free` are metadata, not a product safety guarantee. Responses include a
`label_check` note for such tags.

## Recipe variants

1. `adapt_recipes` returns adapted recipes; nothing is stored yet.
2. `save_adapted_recipes` stores them (optionally edited) as variants. A variant gets its own ID
   `<original>-v<n>` (e.g. `52795-v1`) and keeps the constraints and the changes to the original
   (substituted, added, removed ingredients and changed measures, with the substitution reason).
   Saving the same variant again returns the existing one.
3. `list_recipe_variants` and `get_recipes` show them again; `update_recipe_variants` edits name,
   instructions, constraints or the ingredient list and recomputes the changes.
4. Variants are rows in `recipes` with `parent_id`, so `enrich_recipes`, `get_nutrition` and
   `delete_recipes` accept variant IDs. Original recipes are never changed; deleting an original
   also deletes its variants. Variant numbers are reused after deleting the newest variant.

## Quantity adjustment

A substitute is not taken over 1:1 by count ("4 chicken breasts" must not become "4 chickpeas").
Each substitution has a `quantity_ratio` (grams of target per gram of source, default 1.0) and an
optional `quantity_note` for rules a ratio cannot express. Set them with `add_substitutions`,
`record_substitution_suggestions` (kept on approval) or `set_substitution_quantities`.

`adapt_recipes` computes the amount of each substitute (`quantity` per ingredient):

- mass and volume are scaled in their own unit (`100 g` butter × 0.75 → `75 g` oil),
- piece counts are converted to grams with the USDA portion weight of the original ingredient
  (`4` chicken breasts × 174 g → `696 g` chickpeas); run `enrich_recipes` first,
- amounts without a number or portion weight are kept and listed in `unverified_quantities`.

Converted amounts are marked `estimated`. The changes of a saved variant show source and target measure.

## Nutrition comparison

`compare_nutrition` compares variants with their originals (pass variant IDs, or an original ID
for all its variants). With `enrich=true` (default) missing USDA data is loaded first.

Per pair it returns calories, protein, fat and carbs of both, the difference (absolute and in
percent), the coverage (`covered` of `total` ingredients counted) and `change_effects`: kcal and
protein before and after each changed ingredient. If an ingredient is not counted on one side, the
comparison says so in `notes` and the change effect has `counted: false`. If a replaced ingredient
has no data, `comparable` is false, `difference` is null and the numbers are only in
`partial_difference`, because the substitute would count as 0.

The comparison is only as good as the USDA matches; check `usda_match` in `get_nutrition`.

## Instruction rewriter

A variant first keeps the instructions of the original ("Fry the chicken for 20 minutes").

1. `rewrite_instructions` returns one request per variant: current and original instructions,
   the ingredient changes, the replaced terms still mentioned, and guidelines (replace names,
   adapt cooking times and steps, add no new ingredients, keep the language).
2. Claude writes the new text and stores it with `save_rewritten_instructions`. The server marks
   it `instructions_source: "llm"` and warns when a replaced ingredient is still mentioned
   (names of the variant's own ingredients are ignored, so "oat milk" does not count as "milk").
3. Manual edits with `update_recipe_variants` are marked `"edited"`. The original recipe keeps its
   instructions. Variants already rewritten are skipped unless `force=true`.

## Build the MCPB

```powershell
python scripts/build_mcpb.py
```

The script copies only the runtime files (`main.py`, `manifest.json`, `config/`, `db/`, `repo/`,
`services/`, `mcp_tools/`) into `build/` and builds two bundles:

| Bundle | Server type | Python on the machine | Status |
|---|---|---|---|
| `dist/meal-<version>.mcpb` | `python` (manifest 0.2) | needed, with the packages from `requirements.txt` | tested in Claude Desktop on Windows; fails on a system python without the packages |
| `dist/meal-<version>-uv.mcpb` | `uv` (manifest 0.4) | not needed: the host installs the dependencies from `pyproject.toml` / `uv.lock` | recommended; tested in Claude Desktop on Windows and macOS |

The uv bundle is the recommended way to install. Claude Desktop brings its own uv (seen: 0.9.7 on
Windows and macOS) and creates a `.venv` in the extension folder. The mcpb CLI 0.3.5 rejects type
`uv`, so the script zips this bundle itself. After changing dependencies, update `pyproject.toml`, `requirements.txt` and run
`uv lock`.
After changing tool names or docstrings, run `python scripts/build_mcpb.py --sync-manifest`: it
copies the server's tool list into `manifest.json` and keeps everything else.
Do not run `mcpb pack` in the project root: the CLI cannot reliably exclude `.venv`.
Avoid `mcpb pack --update`: it rewrites `manifest.json`, drops `user_config` and adds a `_meta`
key that Claude Desktop rejects ("Unrecognized key(s) in object: '_meta'").

The python bundle contains no Python packages. Claude Desktop starts the system `python`, which
needs the packages from `requirements.txt`. Claude Desktop asks for the USDA API key at install time
(`user_config.usda_api_key`) and passes it to the server as `USDA_API_KEY`.

Delete `recipe_mcp.db` after upgrading from v0.5.0 or older: the schema changed and existing
tables are not migrated.

## USDA matching

The USDA search ranks by text relevance, so the first result is often a dish or product
("Chicken, chicken roll, roasted", "Pecans, salted"). `services/usda_matching.py` therefore:

- maps common recipe ingredients to an exact generic USDA food (`ALIASES`), e.g. `chicken` →
  "Chicken, broilers or fryers, meat and skin, raw"; add entries there for further ingredients,
- translates German and international names (`Hähnchen` → `chicken`, `frischer Knoblauch` →
  `garlic`, `courgette` → `zucchini`, `parmigiano-reggiano` → `parmesan cheese`; `TRANSLATIONS`),
- normalizes spellings (`chilli` → `chili`, `yoghurt` → `yogurt`),
- scores all results: every word of the ingredient must appear, the food must be the ingredient
  itself (not a dish containing it), raw foods win, processed products and brands lose.

An ingredient without a plausible result is reported as missing instead of a wrong match.
`get_nutrition` lists the USDA food used per ingredient in `ingredient_breakdown`. Matches are
cached; after improving the matching, call `enrich_recipes` with `refresh=true` to replace them.

Correcting matches by hand:

1. `list_ingredient_matches` shows the USDA food per ingredient and whether it was chosen
   automatically or by hand.
2. `reject_ingredient_matches` blocks a wrong food for an ingredient and loads the next best one
   (`new_matches`), or reports `no_alternative`.
3. `search_usda_foods` lists candidates with nutrients; `set_ingredient_matches` pins one by
   `fdc_id`. For foods USDA does not have (seitan, oat cream) it stores values per 100 g from a
   label instead (`calories_per_100g`, ...).

`calculate_nutrition` computes free ingredients without saving a recipe.

Decisions are stored in `ingredient_match_rules` and kept by `enrich_recipes`, also with
`refresh=true`.

## Amounts

Measures are converted to grams in this order (`grams_basis` in `ingredient_breakdown`):

1. Mass (`1.2 kg`, `100 g`): exact, `measured`.
2. Pieces and spoons (`5`, `8 cloves`, `1 tsp`): USDA average portion weight of the matched food,
   e.g. `USDA portion: 1 whole = 148 g`. Portions are loaded with the match and cached. If USDA
   only knows teaspoons, tablespoons and cups are scaled (1 tbsp = 3 tsp, 1 cup = 48 tsp).
3. Other volumes: approximately 1 g/ml, listed in `estimated_volume_conversions`.

Amounts like `To taste` stay uncovered. Entries cached before v0.5.3 have no portion weights and
are looked up again by the next `enrich_recipes`; the database column is added on start.

## Notes

Nutrition totals are estimates. USDA values are per 100 g, portion weights are averages. Ingredients without a convertible amount remain visible as uncovered.
