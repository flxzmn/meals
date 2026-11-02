# Meal MCP v1.2.0

Local FastMCP server for Claude Desktop: recipe search and storage (TheMealDB), USDA nutrition
estimates, and a substitution knowledge base that learns from the user's decisions.

## Scope

- Recipes: search, save, list, delete in bulk; photos as files
- Nutrition: USDA enrichment with cache, per recipe, per serving or for free ingredient lists
- Substitutions: rules with quantity ratios; Claude suggests, the user approves or rejects, rejected
  suggestions do not come back
- Variants: adapted recipes with their own ID, rewritten instructions, nutrition compared with the original
- USDA matches can be inspected, corrected or replaced by label values; German ingredient names work
- Data folder outside the extension; export and import as JSON
- Evals: fixed prompts check which tools Claude chooses

## Documentation

Course material and guides (German):

| Document | Content |
|---|---|
| [docs/ARCHITEKTUR.md](docs/ARCHITEKTUR.md) | Layers, design decisions, data model, workflows, matching, amounts, tools by area |
| [docs/INSTALLATION.md](docs/INSTALLATION.md) | Installation, data folder, common problems |
| [docs/BUILD.md](docs/BUILD.md) | Building the MCPB bundle, release steps, pitfalls |
| [docs/RELEASE_TEST.md](docs/RELEASE_TEST.md) | Automated and short manual release test |
| [docs/TESTPROTOKOLL.md](docs/TESTPROTOKOLL.md) | Test levels, test files, acceptance criteria per sprint, results |
| [docs/EINSCHRAENKUNGEN.md](docs/EINSCHRAENKUNGEN.md) | Known limitations |
| [docs/FEHLERANALYSE.md](docs/FEHLERANALYSE.md) | Fifteen real errors from the logs: symptom, cause, fix, lesson |
| [docs/VERSIONEN.md](docs/VERSIONEN.md) | Versions compared |
| [docs/UEBUNGEN.md](docs/UEBUNGEN.md) | Exercises (draft) |
| [docs/EVALS.md](docs/EVALS.md) | Evals: which tools Claude chooses for fixed prompts |

## Setup (Windows PowerShell)

```powershell
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Enter your USDA key in `.env`. For Claude Desktop, install the bundle instead
([docs/INSTALLATION.md](docs/INSTALLATION.md)).

## Tests

```powershell
python -m pytest              # unit and MCP acceptance tests
python -m pytest -m release   # builds and checks the bundle
python -m tests.manual_api_check
```

## Run and build

```powershell
python main.py                # STDIO server, waits for an MCP client
python scripts/build_mcpb.py  # dist/meal-<version>.mcpb
```

After changing tool names or docstrings, build with `--sync-manifest` ([docs/BUILD.md](docs/BUILD.md)).

## Notes

Nutrition totals are estimates: USDA values per 100 g, average portion weights, amounts from recipe
texts. The response shows how each number was computed (`grams_basis`, `coverage`,
`uncovered_ingredients`). Tags such as `nut free` are metadata, not a product safety guarantee.
