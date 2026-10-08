"""Protect publication boundaries, untrusted Git text and complete history."""
import importlib.util
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("wiki_builder", ROOT / "scripts/build_wiki.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def run_git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], encoding="utf-8").strip()


@pytest.fixture
def history_repo(tmp_path):
    run_git(tmp_path, "init", "-b", "main")
    run_git(tmp_path, "config", "user.name", "Wiki Test")
    run_git(tmp_path, "config", "user.email", "wiki-test@example.invalid")
    (tmp_path / "one.md").write_text("first\n", encoding="utf-8")
    run_git(tmp_path, "add", "one.md")
    run_git(tmp_path, "commit", "-m", "Initial ![tracking](https://example.invalid)")
    run_git(tmp_path, "switch", "-c", "feature")
    (tmp_path / "feature.md").write_text("feature\n", encoding="utf-8")
    run_git(tmp_path, "add", "feature.md")
    run_git(tmp_path, "commit", "-m", "Feature", "-m", "<script>never execute</script>")
    run_git(tmp_path, "switch", "main")
    (tmp_path / "one.md").write_text("second\n", encoding="utf-8")
    run_git(tmp_path, "add", "one.md")
    run_git(tmp_path, "commit", "-m", "Parallel main change")
    run_git(tmp_path, "merge", "--no-ff", "feature", "-m", "Merge feature")
    return tmp_path


def test_ledger_contains_every_commit_and_escapes_git_data(history_repo):
    revision = run_git(history_repo, "rev-parse", "HEAD")
    pages = builder.history(history_repo, revision, "https://github.com/test/repo")
    combined = "\n".join(pages.values())
    for sha in run_git(history_repo, "rev-list", "HEAD").splitlines():
        assert f"/commit/{sha}" in combined
    assert "**4 Commits**" in pages["Changelog.md"]
    assert "feature.md" in combined and "one.md" in combined
    assert "<script>" not in combined
    assert "&lt;script&gt;" in combined
    assert "![tracking]" not in combined
    assert "&#91;tracking&#93;" in combined


def test_unknown_pages_preserved_and_collision_is_atomic(tmp_path):
    (tmp_path / "Manual.md").write_text("Keep me", encoding="utf-8")
    (tmp_path / "Home.md").write_text("User edited home", encoding="utf-8")
    with pytest.raises(ValueError, match="Unmanaged wiki page collision"):
        builder.write_pages(tmp_path, {"New.md": "new", "Home.md": "generated"}, managed_only=True)
    assert not (tmp_path / "New.md").exists()
    assert (tmp_path / "Home.md").read_text() == "User edited home"
    assert (tmp_path / "Manual.md").read_text() == "Keep me"


def test_only_exact_original_template_can_be_adopted(tmp_path):
    (tmp_path / "Home.md").write_text(builder.PLACEHOLDER + "\n", encoding="utf-8")
    pages = {"Home.md": builder.MARKER + "\n\nHome"}
    builder.write_pages(tmp_path, pages, managed_only=True)
    builder.write_pages(tmp_path, pages, managed_only=True)
    assert (tmp_path / "Home.md").read_text() == pages["Home.md"]


def test_missing_page_and_missing_source_are_rejected(history_repo):
    revision = run_git(history_repo, "rev-parse", "HEAD")
    url = "https://github.com/test/repo"
    with pytest.raises(ValueError, match="Missing wiki page"):
        builder.validate_links({"Home.md": f"[Missing]({url}/wiki/Missing)"}, history_repo, url, revision)
    with pytest.raises(ValueError, match="Missing reviewed source"):
        builder.validate_links({"Home.md": f"[Missing]({url}/blob/{revision}/missing.py)"}, history_repo, url, revision)


def test_actual_documentation_build_is_complete_and_reproducible():
    pages = builder.build(ROOT)
    assert pages == builder.build(ROOT)
    assert {"Home.md", "YJarvis-Documentation-and-Wiki.md", "_Sidebar.md", "_Footer.md", "Changelog.md"} <= pages.keys()
    assert all(content.startswith(builder.MARKER) for content in pages.values())
    assert all("{{" not in content for content in pages.values())


def test_shallow_history_fails_explicitly(history_repo, tmp_path):
    clone = tmp_path / "shallow"
    subprocess.check_call(["git", "clone", "--depth=1", history_repo.as_uri(), str(clone)])
    with pytest.raises(ValueError, match="Full Git history"):
        builder.build(clone)
