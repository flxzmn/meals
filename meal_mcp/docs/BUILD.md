# MCPB-Pakete bauen

## Entwicklungsumgebung

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip install uv          # nur für das uv-Paket und dessen Release-Test
dotnet tool install -g mcpb       # mcpb-CLI (getestet: 0.3.5)
Copy-Item .env.example .env       # eigenen USDA-Key eintragen, .env nie committen
```

## Ablauf pro Version

1. Version in `manifest.json` und `pyproject.toml` erhöhen.
2. Tests:
   ```powershell
   python -m pytest
   ```
3. Nach Änderungen an Tool-Namen oder Docstrings die Toolliste ins Manifest übernehmen und bauen:
   ```powershell
   python scripts/build_mcpb.py --sync-manifest
   ```
   Ohne Tool-Änderung reicht `python scripts/build_mcpb.py`.
4. Release-Test (baut beide Pakete, prüft Inhalt, Manifest, Key und Serverstart):
   ```powershell
   python -m pytest -m release
   ```
5. Manueller Test in Claude Desktop nach [RELEASE_TEST.md](RELEASE_TEST.md).

Ergebnis:

- `dist/meal-<version>-uv.mcpb`: empfohlen, Servertyp `uv` (manifest 0.4), vom Skript selbst gezippt,
  weil die CLI 0.3.5 den Typ `uv` noch ablehnt
- `dist/meal-<version>.mcpb`: Ausweichweg, Servertyp `python`, gepackt mit der mcpb-CLI

## Was ins Paket kommt

Das Skript arbeitet mit einer Allowlist (`RUNTIME_FILES`, `RUNTIME_PACKAGES` in
`scripts/build_mcpb.py`): `main.py`, `manifest.json`, `README.md`, `icon.png`, `config/`, `db/`, `repo/`,
`services/`, `mcp_tools/`, dazu `requirements.txt` (Python-Paket) bzw. `pyproject.toml` und
`uv.lock` (uv-Paket). Alles andere bleibt draußen: `.env`, `.venv`, Datenbank, Tests, alte Pakete.

## Abhängigkeiten ändern

Laufzeitabhängigkeiten stehen zweimal: `requirements.txt` (Python-Paket, Entwicklung) und
`pyproject.toml` (uv-Paket). Nach einer Änderung beide anpassen und die Sperrdatei erneuern:

```powershell
uv lock
```

## Fallen

| Falle | Folge | Richtig |
|---|---|---|
| `mcpb pack` im Projektordner | `.venv` landet im Paket (über 100 MB); die Ignore-Muster der CLI greifen nicht zuverlässig | Nur `scripts/build_mcpb.py` |
| `mcpb pack --update` | Schreibt `manifest.json` um, entfernt `user_config`, fügt `_meta` hinzu; Claude Desktop lehnt das Paket ab | `--sync-manifest` des Skripts |
| Docstring geändert, Manifest nicht | Claude Desktop zeigt alte Tool-Beschreibungen, Release-Test schlägt fehl | `--sync-manifest` |
| Key im Manifest oder in Testdaten | Key wird mit dem Paket verteilt | Key nur in `.env` und `user_config`; der Release-Test sucht den Key im Paket |
