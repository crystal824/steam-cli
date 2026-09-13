# Changelog

All notable changes to this project will be documented in this file.

## [0.2.4] - 2026-09-13

### Bug Fixes

- **review:** Publish through the real endpoint, not a silent no-op
  The command posted to steamcommunity.com/profiles/<id>/recommended/, which is
  only a page: it answers HTTP 200 + HTML and saves nothing. Because nothing but
  the status code was checked, it printed "Review posted." while publishing
  nothing at all.
  
  Reviews now go to store.steampowered.com/friends/recommendgame -- the endpoint
  the store front-end calls -- with the parameters it sends, and the JSON reply is
  parsed: Steam's strError becomes the structured review_rejected error, a non-JSON
  body raises network_error instead of passing for success, and a published review
  is read back from the profile page to confirm it landed.
  
  --mine reads that profile page too: the public review feed only returns its
  newest page and filters by language, so it could never match an account whose
  reviews are Chinese.


### Documentation

- **releases:** V0.2.4 notes and version bump

## [0.2.3] - 2026-09-12

### Documentation

- **releases:** Document the release flow and how to fix a published release

- **releases:** Bilingual release notes, read notes and changelog config from main

- **releases:** Bilingual release notes (zh + en) as the convention

## [0.2.2] - 2026-09-12

### Documentation

- **release:** Write release notes per version and make them the release body
  The release page was showing the conventional-commit changelog: bare titles such as
  "chore(release): 0.2.1" and "**release:** Commit the regenerated CHANGELOG back to
  the default branch", which say nothing about what shipped. It now publishes
  docs/releases/<tag>.md when that file exists, falling back to the generated
  changelog otherwise, and notes are written for 0.2.0, 0.2.1 and 0.2.2.
  
  The generated changelog also improves: cliff.toml prints each commit's description
  under its title and skips housekeeping commits, so CHANGELOG.md explains itself.
  Two safeguards come with it -- the release job reads cliff.toml from main so template
  fixes reach re-published older tags, and the automatic CHANGELOG commit only runs for
  the newest tag so a re-release can never roll the changelog backwards.

## [0.2.1] - 2026-09-12

### Build & CI

- **release:** Commit the regenerated CHANGELOG back to the default branch
  The release workflow rendered CHANGELOG.md with git-cliff but only used it as the
  GitHub Release body, so the copy in the repository still had to be edited by hand
  and drifted from the released notes. The job now copies the rendered file onto
  main and commits it, skipping the commit when nothing changed. It runs after the
  build and publish steps on purpose: those must operate on the tagged tree, whereas
  this step switches the worktree to the default branch.
  
  cliff.toml also gains per-version sections (## [x.y.z] - date). The previous
  template grouped commits by type but never printed a version heading, so the file
  read as one flat list and could not be regenerated without losing the release
  boundaries.

## [0.2.0] - 2026-09-12

### Bug Fixes

- Rework the Steam endpoints that broke activation, wishlist and sessions
  Steam retired or changed several endpoints this CLI was built on. The symptoms
  looked like bad credentials or a bad key rather than dead endpoints, so each fix
  is written up in docs/steam-endpoint-changes-2026.md.
  
  - activate: POST /account/registerkey is only the HTML form page, so every
    activation ended in `endpoint_unavailable` no matter how good the key was.
    Post to /account/ajaxregisterkey/ (JSON, XHR headers) and map
    purchase_result_details in full -- 9 already owned, 15 already activated by
    another account, 13 region locked, 53 rate limited, 14 invalid, 24 base game
    required, 4 retry later. The activated product name is now printed and logged.
  - wishlist: the store wishlistdata endpoint answers 302 for every request. Read
    via IWishlistService/GetWishlist/v1 and resolve display names with concurrent
    single-appid lookups -- batched appdetails returns 400 for any comma-separated
    list and GetAppList is 404/403 -- cached in ~/.config/steam-cli/appnames.json.
  - auth: add cookie_value(), an iteration-based lookup. Steam mirrors sessionid
    and steamLoginSecure across three domains, so requests' cookies.get() raised
    CookieConflictError and crashed activate, friends, review and wishlist.
  - achievements: ISteamUserStats returns percent as a string; formatting it with
    :.2f raised ValueError. Coerce it, sorting unparseable values last.
  - docs: every `steam auth <cmd>` reference was wrong -- the commands are top
    level (`steam status`, `steam set-key`, ...).
  
  Tests move to the JSON activation contract and cover the result-code mapping,
  the ajax endpoint plus its headers, cookie_value against mirrored domains, and
  the percent coercion.


### Features

- **tools:** Modern login, session re-mint and licence verification; docs; 0.2.0
  ValvePython's WebAuth posts to the retired community /login/dologin/. Steam still
  answers that call -- after a correct password and Steam Guard code it returns
  success + login_complete -- but it mints no usable session, so `steam status`
  reported an invalid session and every session-based command failed with
  not_authenticated. steam 1.4.4 is the newest release on PyPI, so there is no
  upgrade that fixes it.
  
  - tools/steam_modern_login.py implements what Steam actually uses:
    GetPasswordRSAPublicKey -> BeginAuthSessionViaCredentials -> mobile-app
    approval or UpdateAuthSessionWithSteamGuardCode -> PollAuthSessionStatus ->
    login.steampowered.com/jwt/finalizelogin -> settoken per domain. Note for
    anyone reimplementing this: the settoken body must carry steamID in addition
    to the nonce and auth from finalizelogin. Without it Steam replies
    {"result":8} and sets no cookie at all.
  - tools/steam_remint_session.py re-mints session cookies from the stored refresh
    token, with no password and no 2FA.
  - tools/check_licenses.py lists licences with acquisition date and method, the
    authoritative way to verify that an activation landed: GetOwnedGames carries no
    acquisition timestamp and playtime can predate a key.
  - docs/steam-endpoint-changes-2026.md, tools/README.md and patches/README.md
    document each retired endpoint, its symptom, the fix and the two local patches
    the installed steam package still needs.
  - CI lints and formats tools/ as well; version bumped to 0.2.0 in pyproject and
    uv.lock with a matching CHANGELOG entry.

## [0.1.2] - 2026-08-15

### Build & CI

- Separate release artifacts

## [0.1.1] - 2026-08-15

### Bug Fixes

- **activate:** Stop leaking raw CD keys into the audit log
  log_audit() previously received the unmasked key from both the
  single-key and batch activation paths, so a fully readable product
  key ended up in ~/.config/steam-cli/audit.log even though every
  console/table surface already masks it via _mask_key(). The log file
  was also opened with no explicit permissions, inheriting the process
  umask instead of the 0o600 used for the keyring-fallback secret files.
  
  - Pass _mask_key(key) into log_audit() at both call sites.
  - Open the audit log with os.open(..., 0o600) so new files aren't
    group/world-readable.
  
  Adds a regression test that runs _activate_batch end-to-end and
  asserts the logged target is the masked form, plus a test asserting
  the audit log file's permission bits.

- **friends:** Use the real GetPlayerSummaries field names
  profile() read locacountryid/locastateid/locacityid, none of which
  Steam's Web API actually returns (the real fields are loccountrycode,
  locstatecode, and loccityid). Since the keys never matched, Country/
  State/City silently never printed, even for profiles that expose
  them -- no error, just permanently missing output.
  
  Pulls the field/label pairs out into a small pure helper
  (_profile_detail_lines) so this is unit-testable without mocking the
  Steam API, and adds tests covering the corrected fields plus a
  regression test for the old, incorrect ones.

- **review:** Match banned words on boundaries, not substrings
  filter_review_text() rejected a review if any banned word appeared
  anywhere in it, including inside unrelated words -- 'retard' matches
  inside 'retardant'/'retardation', and 'spic' matches inside
  'despicable'/'conspicuous'/'auspicious'. A perfectly clean review
  mentioning any of those gets rejected with a generic 'disallowed
  word' error and no indication of why.
  
  Switches to a compiled regex with \b word boundaries so the filter
  still catches the words it's meant to catch without flagging
  ordinary words that happen to contain them as substrings.
  
  Tests cover both directions: the previously-rejected clean phrases
  now pass, and a synthetic banned word (swapped in via monkeypatch, so
  the test suite doesn't need to hardcode a real slur) confirms
  whole-word matches are still blocked.

- **client:** Url-encode the search term in resolve_appid
  The SearchApps request built its path with raw string concatenation
  ("...SearchApps/" + term). The host is fixed so this wasn't
  exploitable as SSRF, but unencoded path segments are still worth
  avoiding -- config.py already does this correctly two files over.
  Uses urllib.parse.quote() instead.

## [0.1.0] - 2026-08-14

### Bug Fixes

- Add ruff and mypy to dev dependencies for CI


### Build & CI

- Upgrade actions to Node 24 (checkout v7, setup-python v7, gh-release v3), add dependabot


### Documentation

- Add development plan (PRD)

- Sync with implementation (proxy, ITAD key, recommend, refresh semantics, testing principles)

- Regenerate changelog for v0.1.0 (full history)


### Features

- Initial steam-cli CLI and Hermes skill

<!-- generated by git-cliff -->
