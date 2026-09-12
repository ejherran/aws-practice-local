# Architecture and data lifecycle

## Boundaries

```text
Phone / desktop browser
  Native UI + local EN/ES dictionaries
           |
           | Same-origin HTTPS, secure cookie, profile binding
           v
Python standard-library HTTPS adapter
  Access checks / request limits / localized error codes
           |
           +-- Access: profiles, password derivation, sessions
           +-- Trainer: selection, saved answers, time, scoring
           +-- BankRepository: validation, versions, settings, exports
                         |
                         v
                   Local SQLite file

Bank author / AI agent
  Manifest + question JSON --> bank ZIP --> validate --> admin import
                                  ^
                                  |
                 downloadable schema + authoring kit
```

No engine code reads a hardcoded exam format. The supplied content is installed
from a standard bank ZIP using the same validator as administrator uploads.
Admin settings are a mutable per-bank layer; imported versions remain immutable.
Full JSON content is stored in `bank_versions`, not compiled into Python or JS.

## Storage model

| Table | Scope and role |
|---|---|
| `users` | Local profile, role, language and password derivation data. |
| `sessions` | Hashed token, user, absolute expiry and persisted last activity. |
| `bank_versions` | Immutable `(bank_id, version)` content and normalized content digest. |
| `banks` | Current version pointer, enabled flag and current format settings. |
| `decks` | Remaining question IDs and cycle for `(user, bank, version)`. |
| `attempts` | Owner, immutable content/settings snapshot, answer state, deadline, revision and final result. |
| `audit` | Bank import and configuration actions. |

SQLite foreign keys and explicit transactions preserve relationships. An
application lock serializes access inside the server process. `BEGIN IMMEDIATE`
and SQLite locking also protect against concurrent local tools. A partial unique
index enforces at most one active attempt per user. Backup with the server stopped.

`trainer/tls.py` creates the initial private local identity through the OpenSSL
library linked to CPython, using stdlib ctypes for the native API. It loads and
validates the certificate before the listener opens. Each TLS handshake runs in
a bounded worker with a timeout, so an unfinished handshake cannot block accept.
There is no plaintext listener, downgrade or automatic certificate trust.

Authentication reads do not count as activity. `POST /api/activity` requires the
same origin and expected-profile checks as other mutations, rechecks expiry
inside the transaction, and updates only that cookie's session. The one-hour
idle deadline and 30-day absolute lifetime are both enforced by Access. Existing
v3/v4 sessions gain `last_activity` initialized from their sign-in timestamp.
Attempt deadlines and authentication deadlines remain independent.

## Session creation

1. Finalize overdue sessions and check that the owner has no active session.
2. Read the enabled bank's current version and configured mode.
3. Draw unique question IDs from that user's version-specific deck, approximating
   domain quotas without breaking no-repeat guarantees.
4. Create private snapshots, randomize option identifiers and option order,
   shuffle question order, and choose the required scored subset.
5. Save metadata, settings, bilingual content, cycle assignments, deadline and
   empty answers in the same transaction as deck consumption.
6. Return an active-view allowlist. Answer explanations and scoring flags remain
   server-side until submission or expiration (RUSH deliberately reveals the
   confirmed failed question as immediate feedback).

Selection happens once per quiz/exam or RUSH set. A RUSH failure atomically
appends another set. A process restart, language change or view request cannot
redraw questions. New versions create new decks; format-only changes do not.

## Answers and completion

Updates include the current revision. An older revision receives a conflict
response with the safe current state. The UI restores that state rather than
silently overwriting another device. A post is also bound to the expected user
ID, avoiding cross-profile writes after a different tab signs in.

The server accepts only valid opaque option IDs from the selected question and
no more choices than `select_count`. Partial multi-choice answers can be saved
while editing but receive no credit at completion. The final result compares
selected and correct sets, totals scored questions only, and includes separate
all-question and per-domain counts. Submission is idempotent once finished.

The absolute deadline is checked on API activity and by a periodic sweeper.
Expiration uses the deadline as the finish time. On restart, overdue attempts
are finalized before normal use. The UI clock is only a display of server time.

## Version replacement

A bank upload is validated before any database mutation. A duplicate ID/version
is rejected even if its bytes differ. Replacing the current version requires an
explicit administrative confirmation and makes the new version's defaults the
settings for future attempts. There is no mutation of existing snapshots.

Keeping old versions permits reproducible reports without fetching current
content or external sources. A full database backup retains these versions.
Disabling a bank changes availability for future sessions, not historical access.

## Localization

UI strings live in `web/locales/{en,es}.json`. Educational strings are language
maps in bank JSON and in attempt snapshots. The engine stores both and grades
stable private option IDs, so translating a display does not change correctness.
The application never calls a translation service.

Only `en` and `es` are supported in contract versions 1 and 2. A bank may declare one
or both, but all declared translations must exist throughout its metadata and
content. A visible fallback notice identifies monolingual content when necessary.

## Export distinctions

- **Bank ZIP:** current bank content with current admin defaults; no user progress.
- **Authoring-kit ZIP:** schemas, guide, agent instructions, validator and example;
  not directly importable as a bank.
- **Result JSON:** one completed attempt owned by the requesting profile.
- **Personal JSON:** that profile's records, with no credential data. Active
  attempts remain redacted, apart from the confirmed failed RUSH question in
  pending feedback. This is a review export, not a restore format.
- **Stopped-server database backup:** complete local installation data.

Optional source links are not fetched by the app. Opening one is the learner's
explicit navigation outside the local application.

## RUSH state machine and persistence

`kind=rush` uses the same attempts table and a server-private JSON snapshot
array. `metadata.rush` stores phase, goal, round offset, current index, streak,
best streak, correct count and pending feedback index. The active API removes
that internal object from public metadata and returns an explicit `rush` status
object. Only the current question is sent; the feedback phase sends the failed
question and no next question. Historical reports reveal all generated items.

An answer action validates owner, deadline, revision, phase, current index and
exact selection cardinality. Correct answers increase counters and advance;
reaching the goal finalizes immediately. Wrong answers mark the unused suffix
of the old set skipped, draw and snapshot the next full set, reset the streak,
and enter feedback. All changes and deck consumption commit atomically.
Acknowledgment only changes phase; it cannot draw or reset time. New draws use
the pinned version, even if the bank was updated or disabled. Draft saving uses
the ordinary answer endpoint but can only edit the current unanswered item.

RUSH uses all generated questions as its score denominator and only confirmed
correct responses as its numerator. Per-domain denominators use the same rule.
Percentage-target fields are null; `result.rush.completed` records success.
Read `RUSH.md` for routes, outcome labels and numeric examples.

Storage marker 4 reuses the existing relational columns and safely upgrades
marker 3. Old code refuses marker 4, avoiding interpretation of new RUSH rows
by the v3 engine. Contract-v1 banks are normalized with default RUSH settings;
contract v2 can declare them explicitly. Exported banks use contract v2.
