# Plan: ein Server für den ganzen Kurs

Ziel: Meal MCP läuft auf einem Entwicklungsserver. Teilnehmende installieren nichts, sondern tragen in
Claude oder ChatGPT nur eine Adresse ein und melden sich an. Jede Person sieht nur ihre eigenen
Rezepte, Regeln und Entscheidungen.

Umgesetzt ist Stufe 1 (ein Nutzer, Docker). Die Stufen 2 bis 4 sind geplant.

| Stufe | Inhalt | Aufwand | Stand |
|---|---|---|---|
| 1 | Docker-Image, HTTP, Tunnel für Demos ([DOCKER.md](DOCKER.md)) | 2–3 Stunden | umgesetzt |
| 2 | Anmeldung über OAuth | ca. 1 Tag | geplant |
| 3 | Eigene Daten pro Person | 1–2 Tage | geplant |
| 4 | Betrieb auf dem Entwicklungsserver: HTTPS, Backups, Updates | ½–1 Tag | geplant |

## Stufe 2: Anmeldung

Ohne Anmeldung kann jeder, der die Adresse kennt, alles lesen und löschen. Der geheime Pfad aus
Stufe 1 reicht für eine Demo, nicht für einen Kurs.

- **OAuth**, weil Claude und ChatGPT Remote-Server mit OAuth anbinden. FastMCP bringt einen
  OAuth-Proxy mit fertigen Anbietern mit (u. a. GitHub, Google, Microsoft Entra ID). Der Proxy
  übernimmt die dynamische Client-Registrierung, die beide Clients erwarten.
- **Anbieter:** Am naheliegendsten ist die Anmeldung des Arbeitgebers (z. B. Entra ID), dann braucht
  niemand ein neues Konto. Sonst GitHub.
- **Ergebnis:** Jeder Tool-Aufruf kennt die angemeldete Person (stabile ID aus dem Token, z. B. `sub`).
- **Test:** Aufruf ohne Token wird abgelehnt, mit gültigem Token kommt die Nutzer-ID im Tool an.

## Stufe 3: Eigene Daten pro Person

Heute gibt es eine Datenbank pro Installation. Zwei Wege:

| Weg | Änderung | Bewertung |
|---|---|---|
| **A: eine SQLite-Datei pro Person** (`/data/users/<hash der ID>.db`) | `db.py` wählt die Datei nach der angemeldeten Person; `session_scope` liest die ID aus dem Request. Repos, Services und Tools bleiben unverändert. | **empfohlen**: kleine Änderung, Daten sauber getrennt, Löschen = Datei löschen |
| B: Spalte `user_id` in allen Tabellen | Jede Abfrage und jeder Unique-Index braucht die ID, Migration bestehender Daten | fehleranfällig: eine vergessene Bedingung zeigt fremde Daten |

Zu Weg A:

- **Startregeln:** Jede neue Datenbank bekommt die 30 Regeln aus `data/substitutions_seed.json`
  (wie heute in `init_db`).
- **Nährwert-Cache gemeinsam:** USDA-Werte hängen nicht von der Person ab. Ein gemeinsamer Cache
  spart USDA-Anfragen; Treffer-Regeln und Etikettwerte bleiben pro Person.
- **USDA-Key:** ein Key des Servers. data.gov begrenzt die Anfragen pro Key und Stunde; der
  gemeinsame Cache entschärft das, weil viele dieselben Zutaten abfragen. Reicht es nicht: eigener Key
  pro Person als Einstellung.
- **Datei-Tools:** `export_data`, `import_data` und `download_recipe_images` schreiben heute in Ordner
  auf dem Rechner, auf dem der Server läuft. Auf einem Server sieht die Person diese Dateien nicht.
  Export gibt den Inhalt direkt zurück, Import nimmt ihn als Text, Bilder liefern die Bild-URLs statt
  Dateien. Der Schalter `MEAL_HOSTED=true` wählt dieses Verhalten.
- **Test:** Person A speichert ein Rezept, Person B sieht es nicht; beide haben die Startregeln.

## Stufe 4: Betrieb

- **HTTPS** über einen Reverse Proxy (z. B. Caddy oder Traefik) mit eigener Domain; der Tunnel aus
  Stufe 1 entfällt.
- **Daten:** Volume `/data` mit regelmäßigem Backup.
- **Updates:** neues Image bauen, Container neu starten; `init_db` ergänzt fehlende Spalten wie bisher.
- **Datenschutz:** Gespeichert werden Rezepte, Regeln und die ID aus der Anmeldung. Das Tool-Log
  enthält keine Argumente (siehe `mcp_tools/server.py`). Auf Wunsch einer Person wird ihre
  Datenbankdatei gelöscht.

## Offene Fragen an den Arbeitgeber

1. Welcher Anmeldedienst ist erlaubt (Firmen-SSO, GitHub, Google)?
2. Domain und TLS-Zertifikat für den Entwicklungsserver?
3. Darf der Server ausgehend TheMealDB und die USDA-API erreichen?
4. Wer betreibt ihn, wer macht Backups?
5. Haben die Teilnehmenden Claude- oder ChatGPT-Konten, die Remote-Server anbinden dürfen?
   (ChatGPT braucht dafür Developer Mode, nach aktuellem Stand nur mit bezahltem Abo.)
