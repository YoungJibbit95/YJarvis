# YJarvis documentation foundation

This documentation-only cycle was explicitly requested on 2026-10-08. It does
not authorize a runtime roadmap step. The original wiki at
`https://github.com/YoungJibbit95/YJarvis.wiki.git` contains `Home.md` and
`YJarvis-Documentation-and-Wiki.md`; both page names are retained.

`pages/` is the reviewed source of the German wiki. `metadata.json` records the
commit against which editorial statements were checked. The original architecture
baseline was `dea0e9e6a266584e9c8efaf53dd82138aecbd662`; the inspected main is
`bd1f92d671ec43957e52c51ea3b673ea53ed549d`, including merged core/Windows/UX
work through PR #23. During drafting PR #24 merged as
`da5bd07a9836b53461161bb7747fa26ed83fc32a`; its read-only Windows accelerator
profile was inspected and incorporated, and the clean documentation branch
fast-forwarded to that main before its own commit. Dirty local clipboard work is
not a released capability. Architecture, CONTRIBUTING and AGENTS still contain
older authorization snapshots; this cycle documents that discrepancy without
changing them or inferring approval from merges.

Build a disposable preview from the repository root (Python 3.11+, Git only):

```powershell
py -3.11 scripts/build_wiki.py --output "$env:TEMP/YJarvis-wiki-preview"
py -3.11 -m pytest -q tests/documentation
```

The builder checks page links, source links at the reviewed SHA, unresolved
template placeholders and full Git history. It never imports the application,
downloads models, reads personal runtime data, or executes commit text. Preview
output is disposable and is not committed to the application repository.

The generated `Changelog.md` indexes month archives containing **every reachable
commit**, including merge commits, with full SHA, commit date/body, changed paths
and line counts. Merge diffs are relative to their first parent. Commit text is
escaped; it is evidence about a change, not proof of testing or feature availability.
`Release-Notes.md` is a separately reviewed explanation of product impact.

## Publication and review

The initial pages and publisher are reviewed together in one PR. Publication is
on pushes to `main` **after** that PR is externally reviewed and merged by the
user. The implementer does not merge it or publish an unreviewed branch as released
documentation. Preview artifacts are uploaded on PRs without publishing credentials.

The `wiki-documentation.yml` workflow validates and builds on all PRs to main and
all main pushes (no path filter). On main it clones the existing wiki, changes only
pages carrying its ownership marker (or the two exact initial placeholder pages),
and pushes normally to the wiki's existing default branch. Unknown/manual pages
are preserved; edits to owned pages belong in this repository. A conflicting
push fails rather than overwriting concurrent work. No force push or auto-merge.

An administrator must add the repository Actions secret **WIKI_SYNC_TOKEN**, a
dedicated Git credential with wiki write access. Never put its value in chat,
Git, command arguments, URLs or logs; do not reuse a developer's login implicitly.
Authenticate through the ephemeral askpass environment. The workflow fails with
an explicit setup message when the secret is absent. Expiry/revocation also fails
visibly. Wiki Git is documented by [GitHub](https://docs.github.com/en/communities/documenting-your-project-with-wikis/adding-or-editing-wiki-pages).
Token management is documented [here](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens).
Do not assume the built-in Actions token can write the separate wiki Git remote;
verify the chosen dedicated credential with an actual publish run.

All main commits are retained even if queued publication runs are coalesced:
each build traverses the complete history of the main tip it checked out. Feature
branches are only previewed; they never become the wiki's released feature list.
Manual workflow dispatch is limited to main. Automation updates Git evidence;
contributors must still update editorial pages and `reviewed_sha` whenever behavior,
dependencies, settings or platform support change. The visible source timestamp
keeps that distinction explicit.

## Rollback

Revert this PR to remove the publisher and sources. For already published pages,
revert the relevant commit in the wiki clone and push normally. Disable the workflow
or revoke its dedicated credential first if restoring manual wiki ownership.
Preserve other wiki pages and all personal databases/model files.
