# Chat und Desktop

## Gespräche und Streaming

Eine Sitzung erhält eine ID und speichert Nachrichten in SQLite. Text wird über
`POST /v1/chat` verarbeitet; WebSocket-Ereignisse auf `/v1/ws/{session_id}`
liefern den laufenden Zustand beziehungsweise Antwort-Streaming. Lokale direkte
Antworten, strikte Lernkommandos, gelernte Trigger und heuristische Tool-Intents
stehen vor dem optionalen Legacy-Planner/der normalen Ollama-Konversation.

Die extrahierte `TurnEngine` koordiniert diesen bestehenden Ablauf. Das bedeutet
noch keine produktiven V2-Pläne mit mehreren Aktionen. Ein Wunsch wie „Termin
anlegen und vorher erinnern“ ist ein Roadmap-Szenario, keine zugesagte aktuelle
Mehrschritt-Ausführung.

## Anwendungshülle

Design Tokens und native UI-Primitive liefern konsistente Farben, Abstände und
Interaktionszustände. Die extrahierte `AppShell` steuert die responsive Hülle,
Navigation und den Rahmen für bestehende Bereiche. Chat, Freigaben, Einstellungen
und der Smart-Home-Legacy-Bereich bleiben fachlich getrennte Ansichten.

Das ist keine vollständige Zerlegung von `App.tsx`: Audio-Lifecycle,
WebSocket-/TTS-Zustand und andere Legacy-Verantwortlichkeiten sind noch nicht
vollständig in die geplanten Services verschoben.

## Einrichtungsansichten

Setup-Status, Modellbrowser und Basishardwareansicht sind integriert. Der
Modellbrowser erklärt Kategorien, Quellen und Lizenzen. Die Hardwareansicht
zeigt beschreibende Basiswerte und ausdrücklich unbekannte Angaben. Ein
separater Bereich ergänzt unter Windows native Grafikadapterdaten; auf macOS/
Linux ist diese Abfrage ausdrücklich unsupported. Er empfiehlt keine Modelle.
Keine dieser Ansichten installiert ein Modell oder verändert die Runtime-Auswahl.
Details und Grenzen: [Setup]({{WIKI}}/Setup).

## Freigaben

Eine erkannte Legacy-Tool-Aktion wartet auf eine explizite Entscheidung. Ein
gelernter Trigger oder eine erfolgreiche frühere Ausführung ersetzt keine
Freigabe. Gruppierte Plan-Freigaben und Inline-Consent sind Architekturziele.

Quellen: [TurnEngine]({{SOURCE}}/docs/architecture/turn-engine-shell.md),
[Routing]({{SOURCE}}/docs/architecture/deterministic-routing-stages.md),
[Shell]({{SOURCE}}/docs/architecture/product-application-shell.md),
[UI-Fundament]({{SOURCE}}/docs/architecture/product-experience-foundations.md).
