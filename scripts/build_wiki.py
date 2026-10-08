"""Build a reviewed GitHub wiki and complete commit ledger without app imports."""
from __future__ import annotations

import argparse
from collections import defaultdict
import html
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
MARKER = "<!-- YJarvis managed wiki page; edit docs/wiki/pages in the application repository. -->"
PLACEHOLDER = "Welcome to the YJarvis wiki!"


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(root), *args], encoding="utf-8", errors="strict",
    )


def literal(value: str) -> str:
    # Commit messages/paths are data, never Markdown/HTML or shell instructions.
    escaped = "".join(f"&#{ord(character)};" if character in "\\[]!*_`|#~/{}"
                      else html.escape(character, quote=True) for character in value)
    return escaped.replace("\r", "").replace("\n", "<br>")


def history(root: Path, revision: str, repository_url: str) -> dict[str, str]:
    groups: dict[str, list[str]] = defaultdict(list)
    fields = git(root, "log", "-z", "--topo-order", "--format=%H%x00%cs%x00%s%x00%b%x00%P", revision).removesuffix("\0").split("\0")
    if len(fields) % 5:
        raise ValueError("Invalid Git history record")
    commits = [fields[index:index + 5] for index in range(0, len(fields), 5)]
    for sha, date, subject, body, parent_text in commits:
        parents = parent_text.split()
        base = [parents[0], sha] if parents else ["--root", sha]
        stats = git(root, "diff-tree", "--no-commit-id", "--no-renames", "-r", "--numstat", "-z", *base)
        files = []
        for entry in stats.split("\0"):
            if not entry:
                continue
            added, deleted, path = entry.split("\t", 2)
            files.append(f"| <code>{literal(path)}</code> | {added} | {deleted} |")
        detail = f"### {date} · {literal(subject)}\n\nCommit: [{sha}]({repository_url}/commit/{sha})\n\n"
        if body.strip():
            plain_body = literal(body.strip()).replace("<br>", "\n")
            detail += f"<details><summary>Commit-Beschreibung</summary>\n\n<pre>{plain_body}</pre>\n\n</details>\n\n"
        if files:
            detail += "| Geänderter Pfad | Hinzugefügt | Entfernt |\n|---|---:|---:|\n" + "\n".join(files) + "\n\n"
        else:
            detail += "Keine Dateiänderungen gegenüber dem ersten Parent.\n\n"
        groups[date[:7]].append(detail)
    pages = {}
    index = (
        "# Changelog\n\nAutomatisch aus der vollständigen erreichbaren Git-Historie erzeugt. "
        f"Stand: [{revision}]({repository_url}/commit/{revision}); **{len(commits)} Commits**.\n\n"
        "Jeder Commit enthält Datum, vollständigen SHA, Beschreibung und Dateiänderungen. "
        "Merge-Änderungen werden gegen den ersten Parent gezeigt; Binärdateien tragen `-`. "
        "Datumsangaben stammen aus Git (`%cs`, Committer-Datum); Reihenfolge folgt der Git-Topologie. "
        "Eine Commit-Beschreibung bestätigt weder Testausführung noch Plattformverfügbarkeit.\n\n"
        f"Fachlich gepflegte Einordnung: [Release Notes]({repository_url}/wiki/Release-Notes).\n\n"
    )
    for month in sorted(groups, reverse=True):
        slug = f"Changelog-{month}"
        pages[f"{slug}.md"] = f"# Changelog {month}\n\n" + "".join(groups[month])
        index += f"- [{month}]({repository_url}/wiki/{slug}) · {len(groups[month])} Commits\n"
    pages["Changelog.md"] = index
    return pages


def validate_links(pages: dict[str, str], root: Path, repository_url: str, reviewed_sha: str) -> None:
    slugs = {Path(name).stem for name in pages}
    source_paths = set(git(root, "ls-tree", "-r", "--name-only", "-z", reviewed_sha).split("\0"))
    for name, content in pages.items():
        if re.search(r"\{\{[A-Z_]+\}\}", content):
            raise ValueError(f"Unresolved placeholder in {name}")
        for slug in re.findall(re.escape(repository_url) + r"/wiki/([A-Za-z0-9_-]+)", content):
            if slug not in slugs:
                raise ValueError(f"Missing wiki page {slug}, linked from {name}")
        for path in re.findall(re.escape(repository_url + f"/blob/{reviewed_sha}/") + r"([^\s)]+)", content):
            if path.split('#', 1)[0] not in source_paths:
                raise ValueError(f"Missing reviewed source {path}, linked from {name}")


def build(root: Path) -> dict[str, str]:
    if git(root, "rev-parse", "--is-shallow-repository").strip() != "false":
        raise ValueError("Full Git history is required; checkout with fetch-depth: 0")
    metadata = json.loads((root / "docs/wiki/metadata.json").read_text(encoding="utf-8"))
    repository = metadata["repository"]
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("Invalid repository name")
    reviewed = metadata["reviewed_sha"]
    if not re.fullmatch(r"[a-f0-9]{40}", reviewed):
        raise ValueError("reviewed_sha must be an immutable commit")
    revision = git(root, "rev-parse", "HEAD").strip()
    git(root, "merge-base", "--is-ancestor", reviewed, revision)
    repository_url = f"https://github.com/{repository}"
    values = {
        "{{WIKI}}": f"{repository_url}/wiki",
        "{{SOURCE}}": f"{repository_url}/blob/{reviewed}",
        "{{REVIEWED_SHA}}": reviewed,
        "{{REVIEWED_ON}}": metadata["reviewed_on"],
        "{{PUBLISHED_SHA}}": revision,
    }
    pages = {}
    for path in sorted((root / "docs/wiki/pages").glob("*.md")):
        content = path.read_text(encoding="utf-8")
        for key, value in values.items():
            content = content.replace(key, value)
        pages[path.name] = content
    pages.update(history(root, revision, repository_url))
    validate_links(pages, root, repository_url, reviewed)
    stamp = (
        f"\n\n---\nFachlich geprüft: {metadata['reviewed_on']} · "
        f"[Quellstand {reviewed[:12]}]({repository_url}/commit/{reviewed}). "
        f"Git-Historie veröffentlicht bis [{revision[:12]}]({repository_url}/commit/{revision}).\n"
    )
    return {name: MARKER + "\n\n" + content + (stamp if not name.startswith("_") else "")
            for name, content in pages.items()}


def write_pages(output: Path, pages: dict[str, str], *, managed_only: bool) -> None:
    output.mkdir(parents=True, exist_ok=True)
    # Check all destinations before touching any page. Never remove unknown pages.
    for name in pages:
        destination = output / name
        if destination.is_symlink():
            raise ValueError(f"Refusing symlink destination: {name}")
        if managed_only and destination.exists():
            previous = destination.read_text(encoding="utf-8")
            initial = name in {"Home.md", "YJarvis-Documentation-and-Wiki.md"} and previous.strip() == PLACEHOLDER
            if not previous.startswith(MARKER) and not initial:
                raise ValueError(f"Unmanaged wiki page collision: {name}")
    for name, content in pages.items():
        (output / name).write_text(content, encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--managed-only", action="store_true", help="Preserve manually owned wiki pages")
    args = parser.parse_args()
    output = args.output.resolve()
    if output == ROOT or ROOT in output.parents:
        parser.error("Output must be outside the source checkout")
    pages = build(ROOT)
    write_pages(output, pages, managed_only=args.managed_only)
    print(f"Validated and built {len(pages)} wiki pages in {output}")


if __name__ == "__main__":
    main()
