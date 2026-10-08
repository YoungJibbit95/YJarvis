# Architektur: Ist-Zustand und Ziel

## Repository

| Pfad | Verantwortung |
|---|---|
| `apps/agent/jarvis_agent` | Python-Agent, API, Legacy-Routing, Tools, Audio und DB |
| `apps/desktop` | Electron-Prozessgrenze, React/TypeScript-Renderer |
| `packages/shared-types` | gemeinsame TypeScript-DTOs |
| `runtime` | persönliche DB, Profile und Modelle; keine Git-Quelldaten |
| `tests` | Python-, Domain-, Persistenz-, Startup- und Desktop-Vertragstests |
| `docs/architecture` | Masterplan und einzelne Implementierungs-/Grenznotizen |
| `docs/wiki` | reviewbare Wiki-Quellen und geprüfter Quellstand |

## Aktiver Pfad

```text
Electron/React → HTTP/WebSocket → FastAPI
→ AgentService / extrahierte TurnEngine
→ Legacy-Routing (strikte Kommandos, Trigger, Heuristiken, optionaler Planner)
→ Legacy-Freigabe → Legacy-ToolRegistry → ToolResult
→ Antwort/Streaming + SQLite
```

Die TurnEngine-, Routing- und Planner-Extraktionen bewahren das bestehende
Single-Tool-Verhalten. Die Baseline-Migration übernimmt vorhandene SQLite-Daten
atomar; sie führt keine neuen Plan-/Observation-/Trust-Datenmodelle produktiv ein.

## Gemergtes, isoliertes V2-Fundament

Domain-Verträge definieren Turn, Action, ActionPlan mit Abhängigkeiten,
PolicyDecision und Observation. ToolSpec V2 und getypte Inputs/Outputs/Kataloge
stehen getrennt von den laufenden Wire-/DB-Namen.

Der semantische `ToolRuntime`-Kernel kann explizit injizierte Provider aufrufen
und Ein-/Ausgaben validieren. Die Provider-Registry unterscheidet bekannte Specs
von explizit verfügbar gemachten Providern. Es gibt keine automatische
Registrierung bei Import. Die Windows-Provider für URL-Öffnen und Clipboard-Lesen
sind solche isolierten Bausteine. Beide werden nur durch explizite Registrierung
verfügbar. Kernel/Registry/Provider sind kein neuer produktiver Ausführungspfad.
Timeout-Metadaten werden dabei noch nicht erzwungen; Policy, Observations,
Execution-Persistenz und Events folgen später.

## Zielarchitektur

```text
Input Gateway → TurnEngine → Context / Router / Routinen
→ PlanBuilder → Validierung → Policy
→ PlanExecutor → ToolRuntime / Plattformprovider
→ Observations → Antwort / Memory-Commit
```

Planung darf keine Tools ausführen. Provider entscheiden nicht über Policy.
OS-Aufrufe gehören an explizite Plattform-/Prozessgrenzen; Domain/Core bleiben
OS-neutral. Datenmigration, Safety-Änderungen, Mehrschritt-Ausführung und Audio
werden jeweils separat reviewt. Das Diagramm ist das Ziel, kein Ist-Diagramm.

Architekturentscheidungen und Nachweise:
[Index]({{SOURCE}}/docs/architecture/README.md),
[Domain]({{SOURCE}}/docs/architecture/domain-contracts-v2.md),
[Persistenz]({{SOURCE}}/docs/architecture/persistence-migrations.md),
[Kernel]({{SOURCE}}/docs/architecture/semantic-tool-runtime-kernel.md),
[Registry]({{SOURCE}}/docs/architecture/capability-provider-registry.md).
