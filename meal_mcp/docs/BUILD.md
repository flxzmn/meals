# MCPB-Paket bauen

## Entwicklungsumgebung

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip install uv          # für uv lock und den Release-Test
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
4. Release-Test (baut das Paket, prüft Inhalt, Manifest, Key und Serverstart mit uv):
   ```powershell
   python -m pytest -m release
   ```
5. Kurztest in Claude Desktop nach [RELEASE_TEST.md](RELEASE_TEST.md).

Ergebnis ist `dist/meal-<version>.mcpb` mit Servertyp `uv` (manifest 0.4). Das Skript zippt es
selbst, weil die mcpb-CLI 0.3.5 den Typ `uv` ablehnt; die CLI wird nicht gebraucht.

## Was ins Paket kommt

Das Skript arbeitet mit einer Allowlist (`RUNTIME_FILES`, `RUNTIME_PACKAGES` in
`scripts/build_mcpb.py`): `main.py`, `manifest.json`, `README.md`, `icon.png`, `LICENSE`,
`pyproject.toml`, `uv.lock`, `config/`, `db/`, `repo/`, `services/`, `mcp_tools/`. Alles andere
bleibt draußen: `.env`, `.venv`, Datenbank, Tests, alte Pakete.

## Abhängigkeiten ändern

Laufzeitabhängigkeiten stehen zweimal: `requirements.txt` (Entwicklung) und `pyproject.toml`
(Paket). Nach einer Änderung beide anpassen und die Sperrdatei erneuern:

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
