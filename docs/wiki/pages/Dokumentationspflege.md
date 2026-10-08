# Dokumentationspflege und commitbasierter Changelog

## Quellen und Ownership

Die Texte liegen in `docs/wiki/pages` im Hauptrepository und werden über dessen
PR-Prozess geprüft. Die ursprünglichen Wiki-Seiten `Home` und
`YJarvis-Documentation-and-Wiki` bleiben als Einstieg erhalten. Ein eigener
Sidebar/Footer macht die Kategorien erreichbar.

`metadata.json` hält den unveränderlichen, fachlich geprüften SHA fest. Alle
Code-/Architekturlinks beziehen sich auf diesen SHA. Jede Seite zeigt zusätzlich
den Git-Stand der letzten Veröffentlichung. Wenn der Changelog neuer als die
fachliche Prüfung ist, wurden die Texte dadurch nicht automatisch revalidiert.

## Was automatisch aktualisiert wird

Bei **jedem Push auf main**, ohne Pfadfilter, baut der Workflow `wiki-documentation`
die Seiten und die vollständige Historie neu. Pro Commit: vollständiger SHA,
Committer-Datum, Betreff/Body, geänderte Pfade und Zeilenstatistik. Monatsarchive
halten die Historie navigierbar. Alle erreichbaren Commits bleiben enthalten,
auch Merge-Commits und mehrere Commits zwischen zwei Veröffentlichungen.

Keine PR-Branch wird als veröffentlichtes Feature geführt. PRs bekommen eine
validierte Preview als Actions-Artefakt. Die initiale Dokumentations-PR muss
extern geprüft und vom Nutzer gemergt werden; erst dann publiziert der Workflow.
Manueller Dispatch funktioniert nur von main.

Git-Text wird escaped und nie als Kommando ausgeführt. Der Generator importiert
den Agenten nicht und liest keine persönlichen Runtime-Dateien. Bei Wiki-
Schreibkonflikten scheitert der normale Push; es wird nicht force-gepusht.
Unbekannte/manuelle Wiki-Seiten bleiben erhalten. Verwaltete Seiten werden
aus den Repository-Quellen erzeugt; Änderungen dort direkt im Wiki würden beim
nächsten Sync ersetzt und gehören deshalb in einen Dokumentations-PR.

## Was bewusst fachlich gepflegt wird

Funktionen, Plattformstatus, Installationsanleitung, Dependency-Erklärungen,
API-/Settings-Semantik und Release Notes benötigen Review des echten Diffs.
Commit-Texte alleine beweisen keine funktionierende Integration oder Freigabe.
Bei jeder relevanten Änderung diese Seiten im selben PR anpassen; nach Prüfung
`reviewed_sha` auf einen verfügbaren unveränderlichen Quellcommit setzen.
Wenn ein PR noch nicht gemergt ist, nicht als released markieren.

## Veröffentlichung einrichten

Actions-Secret **WIKI_SYNC_TOKEN** als dedizierten Git-Zugang mit Wiki-Schreibrecht
hinterlegen, ausschließlich in GitHub Settings. Nicht im Chat/Git speichern und
nicht implizit den Entwickler-Login wiederverwenden. Der Publish-Job prüft das
Secret, nutzt temporäres Askpass und schreibt keine Credentials in Remote-URLs.
Der tatsächliche erste Publish-Lauf bestätigt, ob der gewählte Token den Wiki-
Remote schreiben darf. Fehlendes/abgelaufenes Secret wird als Fehler angezeigt.

## Pflegezyklus

1. Quellcode/PR-Diff und Nachweise lesen; Status pro Funktion einordnen.
2. Betroffene Texte/Release Notes aktualisieren, geprüften SHA dokumentieren.
3. Wiki-Generator, Links und relevante Tests ausführen.
4. PR extern prüfen lassen; keine Folgeimplementierung vor Nutzerfreigabe.
5. Nach Nutzer-Merge Publish-Lauf und sichtbare Wiki-Seiten prüfen.

Kein automatischer Changelog-Eintrag ist eine Release-Freigabe.
Anleitung: [Repository-Wiki-Guide]({{SOURCE}}/docs/development.md),
[GitHub Wiki-Git](https://docs.github.com/en/communities/documenting-your-project-with-wikis/adding-or-editing-wiki-pages).
