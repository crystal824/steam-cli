# Release notes

Write the notes for a release in `<tag>.md` (for example `v0.2.2.md`) **before**
pushing the tag. `.github/workflows/release.yml` publishes that file verbatim as the
GitHub Release body; when it is missing, the release falls back to the changelog
generated from conventional commits.

## Language: bilingual (Chinese first, then English)

Every release note is written twice — 中文在前，English after — because the notes are
read by a Chinese-speaking user and by anyone browsing the public repository. Keep
both halves equivalent; do not let one become a summary of the other.

```markdown
# vX.Y.Z

**一句话概括 / One-line summary**

## 中文

...正文...

**升级说明**：…

## English

...body...

**Upgrading**: ...

**Full diff**: https://github.com/crystal824/steam-cli/compare/<prev>...<tag>
```

## What good notes contain

- what the version is about, in one short paragraph per language
- what changed from a user's point of view — old behaviour versus new behaviour
- anything to do before or after upgrading
- a link to the full diff

Keep them readable: they are the public face of the release, not a commit log.

`v0.2.0` and `v0.2.1` predate this convention and keep English-only notes; their
release pages are left as they are.

## Releasing

1. write `docs/releases/<tag>.md` (bilingual)
2. bump the version in `pyproject.toml` and `uv.lock`, commit, push to `main`
3. tag and push: `git tag -a vX.Y.Z -m "..." && git push origin vX.Y.Z`

CI then builds both artifacts, publishes the GitHub Release using your notes, and
commits the regenerated `CHANGELOG.md` back to `main`.

4. **Keep exactly one public release.** A new tag becomes *latest* automatically but does
   not hide its predecessor, so draft the previous one right after the new one publishes
   (`gh release edit <previous-tag> --draft` — see *Hiding a published release*). This
   repository is maintained that way on purpose: only the newest version stays
   downloadable.

## Hiding a published release

Old releases can be hidden without deleting them: a **draft** keeps its tag (so the
`compare/…` links in later notes still resolve) while its body and assets disappear from
the public view.

```bash
gh release edit v0.2.5 --draft      # hide
gh release edit v0.2.5 --draft=false # show again
gh release list --limit 20          # drafts appear only for accounts with push access
```

This needs the GitHub API (a PAT, or the `gh` CLI — the device-flow login needs no token
of your own). SSH deploy keys and GPG signatures cannot do it: they only push and sign
git refs. Note that hiding a release does **not** hide its tag message or the matching
`docs/releases/<tag>.md` in this repository — those stay public, so keep them free of
anything you would not publish.

## Correcting the notes of a published release

Pushing a tag is what makes CI publish notes, and a tag runs the workflow file stored
in its own tree. For tags created with the current workflow (v0.2.2 and later) the
notes themselves are read from `main`, so the fix is simply:

1. edit `docs/releases/<tag>.md` and push to `main`
2. re-push the tag (recreate it: `git tag -d <tag> && git tag -a <tag> -m "..." && git push origin <tag>`)

Note the guard in the release workflow: the automatic `CHANGELOG.md` commit only runs
for the newest tag, so nothing you re-run can roll the changelog backwards. For older
tags (whose workflow predates this behaviour) the only option is editing the release
in the GitHub UI or via `PATCH /repos/{owner}/{repo}/releases/{id}`.
