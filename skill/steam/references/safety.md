# Safety policy

## Forbidden operations (refuse immediately)

Any request involving these is a hard red line — refuse and explain why:

- Purchasing or any real-money payment
- Trading items or generating trade offers
- Changing account email, phone number, or password
- Selling, transferring, or otherwise acting on the account's security/identity

These are intentionally absent from the CLI and the Skill must never approximate them with hand-crafted HTTP.

## CDK format rules

Keys must be **3 segments × 5 chars (15 chars, e.g. `XXXXX-XXXXX-XXXXX`)** or, less commonly, **5 × 5 (25 chars)**. If a key matches neither, ask the user to re-check the source rather than blindly submitting.

## Activation & batch pacing

- Single `steam activate` — second-confirm intent before submitting.
- `steam activate --batch <file>` — show the full list preview and confirm **once** for the whole batch (never per-key interruptions). Pacing interval is inserted between keys; never submit back-to-back without a delay. Every activation is logged with timestamp and result.
- `--dry-run` previews the action without submitting — use it first.

## Review text filtering

`review post` applies basic length and sensitive-word filtering. Draft the text with the user; a `--dry-run` previews it before posting.

## Confirmation requirements (write ops)

Second confirmation of user intent is required before executing:

- `activate` (and `--batch`)
- `wishlist add` / `remove`
- `review post`
- `friends invite-link --refresh`

Skip the second confirmation only when the user already said "直接执行" / "just do it".

## Audit logging

Every write/state-change operation appends a line (timestamp, command, target, result) to a local-only audit log under `~/.config/steam-cli/audit.log`. Nothing is uploaded.
