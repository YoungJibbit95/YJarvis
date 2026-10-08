# Roadmap: zukünftige Funktionen nach Kategorien

Diese Seite listet die im Architekturplan vorgesehenen Ziele, keine beliebigen
Zukunftsversprechen. Ein Merge/CI-Erfolg autorisiert weder Folgeschritte noch
einen Release-Termin. Umsetzung jeweils erst nach externer Prüfung und expliziter
Freigabe. Aktueller Code: [Funktionen]({{WIKI}}/Funktionen).

## Planung, Ausführung und Vertrauen

| Schritt | Geplante Funktion | Grenze / Voraussetzung |
|---|---|---|
| YJ2-05C3 und spätere Runtime-Teilzyklen | Produktionsadapter/-verdrahtung für semantische Tools | im geprüften Stand nicht begonnen; genaue Freigabe separat |
| YJ2-06 | zentrale Policy in `legacy_strict` | zunächst gleiche Bestätigungspflicht |
| YJ2-07 | gescopter Trust und ausgewählte sofortige Low-Risk-Aktionen | Policy-Matrix, Audit und explizites Opt-in |
| YJ2-11 | strukturierter Multi-Action-PlanBuilder hinter Featureflag | Schema-/Capability-/Argument-/DAG-Validierung, Fail-closed |
| YJ2-12 | abhängige Ausführung und gebündelte Freigaben | Observations, Partial Failure, Abbruch zwischen Schritten |

Beispielziel: Kalenderereignis und davon abhängige Erinnerung aus einer Anfrage.
Es gibt keinen transaktionalen Rollback externer Apps ohne eigene Implementierung.
Spec-Timeouts, Execution-Persistenz und neue Events müssen explizit implementiert
werden; vorhandene Metadaten allein erzwingen sie nicht.

## Plattformprovider und native Parität

Windows-URL-Öffnen (YJW-01A) und Clipboard-Lesen (YJW-01B) sind isoliert gemergt.
Weitere Provider für Apps, Clipboard-Schreiben und später Dateien sowie ihre
Produktionsadapter benötigen gesonderte Freigaben, keine automatische Fortsetzung.
Windows-Dateipolicy muss vor Dateimutationen sicher sein. Native Produktivität darf über sichere
lokale/optionale Provider angeboten oder explizit unsupported bleiben;
Pflicht-Cloudintegration ist kein Paritätsziel. Raycast bleibt optional/macOS.

## Desktop, Stimme und Bedienung

| Schritt / Bereich | Ziel |
|---|---|
| YJ2-08 | weitere Frontend-Zerlegung: Chat, Settings, Freigaben, Socket-/Voice-/TTS-Hooks |
| YJ2-09 | verbindliche Voice-Zustandsmaschine, Segmentierung und Latenzinstrumentierung |
| YJ2-10 | warmer/persistenter STT-Backendpfad, Health/Timeout/Restart/Fallback |
| Cross-Platform Audio | getrennte STT-/TTS-/Playback-Provider, echte Windows-/macOS-Smokes |
| YJ2-15 | einfache Hauptkonversation, Inline-Freigaben und sekundäre Diagnostik |
| weitere YJUX-Zyklen | nur durch separate UX-Spezifikation/Freigabe konkretisiert |

Im geprüften Stand liefert YJUX-02C2A native Windows-Adapterdeskriptoren. Weitere
macOS-/Linux-Adapterabfragen, Hardware-Empfehlungen, automatische Modellinstallation
oder Performance-Presets sind damit nicht veröffentlicht.
Dedicated Wake Word und getrennte Planner-/Antwortmodelle sind optionale spätere
Architekturmöglichkeiten, keine bestätigten nahen Releases.

## Kontinuität und Lernen

YJ2-13: typisierte Memories mit Herkunft, Confidence, Retrieval und Nutzerkontrolle.
YJ2-14: Planvorlagen statt Einzeltool-Trigger, Legacy-Migration mit Statistik.
Kontext soll aus Session, Vorlieben, passenden Erinnerungen, Routinen und
Umgebungsdaten selektiert werden. Sensible dauerhafte Inferenz bleibt konservativ.

## Zuverlässigkeit, Sicherheit und Beta

YJ2-16: Cold Start, Modell-/Audioausfälle, Rechtefehler, WebSocket-Reconnect,
veraltete Freigaben, Migration/Backup, Diagnostikexport und Security Review.
Geplant sind stable Fehlercodes und Timing-/Toolmetriken ohne standardmäßige
Weitergabe sensibler Inhalte. Vor Beta zusätzlich Windows-/macOS-Paketierung,
Nutzerdaten außerhalb des App-Pakets und Upgrade-/Restore-Prüfungen.
Ein Vite-Build ist noch kein paketiertes Release.

Bereits gemergte Fundamente YJ2-00–04, 05A/B1/B2/B3/C1/C2, YJW-00A/B/B.1,
YJW-01A/B und YJUX-00A/B/01A/02A/B/C1/C2A sind in
[Release Notes]({{WIKI}}/Release-Notes) eingeordnet. „Gemergt“ ist ein Git-Fakt,
keine Aussage über eine hier nicht nachgewiesene externe Abnahme.

Quelle: [gesamter Architekturplan]({{SOURCE}}/docs/architecture/YJarvis_V2_Architecture_and_Browser_Agent_Master_Prompt.md),
[Plattform-Addendum]({{SOURCE}}/docs/architecture/02_WINDOWS_CROSS_PLATFORM_ARCHITECTURE_ADDENDUM.md).
