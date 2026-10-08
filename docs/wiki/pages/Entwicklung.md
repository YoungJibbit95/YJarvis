# Entwicklung und Verifikation

## Automatisierte Checks

Aus dem Projektroot auf Windows, Python-venv eingerichtet:

```powershell
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check apps/agent/jarvis_agent tests
npm run test:startup
npm ci
npm run typecheck
node --check apps/desktop/electron/main.cjs
node --check apps/desktop/electron/preload.cjs
npm run build
```

Auf macOS/Linux mit aktivem venv `python` verwenden. Linux benötigt
`libportaudio2` und `libsndfile1` für die vorhandenen Audioimports. Jeder Exit-Status
zählt; Fehler nicht durch späteren Erfolg maskieren. `npm ci` verändert den
Lockfile-Inhalt nicht absichtlich. Ruff prüft eine enge Korrektheitsauswahl, kein
vollständiges Stil-/Security-Audit.

Zusätzliche Wiki-Prüfung:

```powershell
py -3.11 scripts/build_wiki.py --output "$env:TEMP/YJarvis-wiki-preview"
py -3.11 -m pytest -q tests/documentation
```

Desktop-Vertragstests (modellfrei):

```powershell
node --test tests/desktop/model-catalog.test.cjs tests/desktop/hardware-profile.test.cjs tests/desktop/accelerator-profile.test.cjs
```

## CI-Nachweise und Grenzen

Sechs etablierte Checks: `python-tests`, `python-lint`, `desktop-typecheck`,
`desktop-build`, `windows-python-tests`, `windows-desktop-checks`.
Ubuntu/Windows testen Core/Startup und statischen Desktop. Diese Checks beweisen
keine echte Modellgenerierung, Audioqualität, Mikrofonrechte, AppleScript oder
paketierte Anwendung. Native macOS-Prüfung muss explizit separat berichtet werden.
Branch-Protection entsteht nicht durch Dokumente oder Workflow-Dateien; der
aktuelle Serverzustand muss bei Review geprüft werden.

Der Wiki-Workflow ergänzt `wiki-validate` und die bedingte Veröffentlichung
auf main. Ein fehlendes Publish-Secret ist ein sichtbarer Setup-Fehler, kein
stillschweigend erfolgreicher Wiki-Sync.

## Ein Schritt, ein Review

Aktuellen Branch/main und Architekturbaseline vergleichen; eigene kleine
Branch/PR pro explizit autorisiertem Ziel. Keine unreviewte Folgeimplementierung,
kein Auto-Merge, kein eigener Merge. PR-Template vollständig ausfüllen,
genaue Testbefehle/Ergebnisse, CI-Links, Risiken und Rollback angeben.
Danach tatsächlichen Diff extern prüfen lassen und stoppen.

Die lokalen Freigabehinweise nennen noch ältere Roadmapstände. Git-Merges,
offene PRs und Nutzerautorisierung sind getrennte Fakten; diese Dokumentation
ändert die Freigabehinweise nicht und startet keinen Runtime-Schritt.

Quellen: [CONTRIBUTING]({{SOURCE}}/CONTRIBUTING.md),
[PR-Template]({{SOURCE}}/.github/pull_request_template.md),
[Entwicklungsanleitung]({{SOURCE}}/docs/development.md).
