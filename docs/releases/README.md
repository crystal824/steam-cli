# Release notes

Write the notes for a release in `<tag>.md` (for example `v0.2.0.md`) **before**
pushing the tag. `.github/workflows/release.yml` publishes that file verbatim as the
GitHub Release body; when it is missing, the release falls back to the changelog
generated from conventional commits.

Good notes answer:

- what this version is about, in one short paragraph
- what changed from a user's point of view — old behaviour versus new behaviour
- anything to do before or after upgrading
- a link to the full diff (`/compare/<previous tag>...<tag>`)

Keep them readable: they are the public face of the release, not a commit log.

## Releasing

1. write `docs/releases/<tag>.md`
2. bump the version in `pyproject.toml` and `uv.lock`, commit, push to `main`
3. tag and push: `git tag -a vX.Y.Z -m "..." && git push origin vX.Y.Z`

CI then builds both artifacts, publishes the GitHub Release using your notes, and
commits the regenerated `CHANGELOG.md` back to `main`.

## Fixing a release that is already published

Pushing a tag is what makes CI publish notes, and **a tag runs the workflow file
stored in its own tree** — so re-pushing an old tag uses the workflow from back then
and will not apply notes written later. To correct an already published release,
edit it directly: *Releases → the release → Edit*, paste the contents of
`docs/releases/<tag>.md`, and save. (The GitHub API does the same thing with
`PATCH /repos/{owner}/{repo}/releases/{id}`; `GITHUB_TOKEN` from within Actions has
the required `contents: write` scope, a personal token needs it too.)

Note the guard in the release workflow: the automatic `CHANGELOG.md` commit only runs
for the newest tag, so nothing you re-run can roll the changelog backwards.
