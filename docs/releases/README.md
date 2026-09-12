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
