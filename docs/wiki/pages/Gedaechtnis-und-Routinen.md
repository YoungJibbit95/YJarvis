# Gedächtnis und Routinen

## Was heute vorhanden ist

Nachrichten, Einstellungen und gelernte Befehle werden lokal in SQLite
gespeichert. Gesprächskontext wird begrenzt und periodisch kompakt abgelegt;
FTS/gespeicherte Memory-Inhalte liefern Kontext. Diese Legacy-Funktion ist
kein allgemeines semantisches Langzeitgedächtnis.

Explizite Lernkommandos:

```text
/learn "abendroutine" => oeffne raycast
/learn-list
/unlearn "abendroutine"
```

Ein Trigger wird einer bestehenden **einzelnen** Tool-Aktion zugeordnet.
Freigaben bleiben erforderlich. Lokale Erfolgs-/Fehler-/Latenzstatistik kann
Legacy-Routingentscheidungen beeinflussen; sie trainiert kein neues LLM und
verleiht keine pauschale autonome Ausführungserlaubnis.

## Geplantes Memory V2

YJ2-13 trennt Vorlieben, Personen, Projekte, Fakten, Korrekturen, Routine-Hinweise
und Arbeitskontext. Geplant sind Herkunft, Confidence, Gültigkeit, Ablösung und
inspizierbare/löschbare Einträge. Nicht jede Unterhaltung soll dauerhaft zu
einer Tatsache umgewandelt werden. Eine Vektordatenbank ist nicht vorausgesetzt;
FTS kann zunächst reichen.

## Geplante Routines V2

YJ2-14 wandelt gelernte Befehle verlustfrei in Planvorlagen um. Der Legacy-Fall
wird ein Plan mit einer Aktion; spätere Routinen dürfen mehrere abhängige
Aktionen enthalten. Routinen erzeugen Pläne und ersetzen keine Policy-Prüfung.
Historische Nutzungs-/Erfolgsstatistik soll erhalten bleiben.

Quellen: [Legacy-Agent]({{SOURCE}}/apps/agent/jarvis_agent/agent_service.py),
[Datenhaltung]({{SOURCE}}/apps/agent/jarvis_agent/db.py),
[Architekturplan]({{SOURCE}}/docs/architecture/YJarvis_V2_Architecture_and_Browser_Agent_Master_Prompt.md).
