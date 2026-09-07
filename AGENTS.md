# AGENTS.md — AWS Practice Local

## Product boundary

This is a local, multi-user practice tool for multiple certification banks. The
runtime and shipped test suite must use **Python 3.10+ standard library only**.
Keep the browser UI native HTML/CSS/JavaScript. Do not introduce pip packages,
Node build steps, CDNs, external fonts, analytics, hosted databases, translation
APIs, cloud authentication or runtime service dependencies.

All identifiers, source comments, developer documentation and new filenames
must be English. Spanish belongs in `es` localization fields and educational
content. Do not hardcode visible prose in JavaScript: update both locale files
and preserve matching interpolation placeholders. Keep documents readable and
source changes focused.

## Separation of concerns

- `trainer/banks.py` owns the bank ZIP contract and import/export validation.
- `trainer/engine.py` is certification-agnostic. Never special-case a bank ID,
  exam code, AWS service, question count, scoring count or domain list here.
- `trainer/auth.py` owns credentials and sessions. Browser state is not authority.
- `trainer/storage.py` owns schema and transactions. Persist progress server-side.
- `trainer/server.py` owns transport, route authorization and safe responses.
- `web/` presents server state; it must not contain answer keys or scoring logic.
- `banks/` and imported database versions are content, independent of the engine.

The initial `Admin` account is created once with the requested documented
password. Never reset a changed password on restart. Registration always creates
a learner and cannot request an administrator role. Do not add additional
administrator accounts without an explicit product requirement.

## Core invariants

1. Every read/write of an attempt is scoped to the authenticated user. Admin
   bank-management privileges do not implicitly grant access to another user's
   practice endpoints or personal exports.
2. Active attempt responses use an explicit field allowlist. Quizzes/exams
   never expose answer keys before completion. RUSH exposes only the current
   question; the sole exception is the confirmed failed question's immediate
   feedback. Never expose future questions/answers. Apply this to exports too.
3. A deck is scoped by user, bank ID and content version. Quizzes, exams and RUSH sets
   consume it without replacement. Do not repeat a question within a quiz, exam
   or individual RUSH set, including across cycle boundaries. Multiple RUSH
   rounds may revisit earlier questions only after the shared cycle is exhausted. No-repeat takes priority over
   exact domain quotas; report any distribution adjustment.
4. Shuffle questions and choices only on session creation or a RUSH failure
   that generates a new full set. Save their order.
   Language changes, page reloads and device changes must not shuffle or redraw.
5. The server owns absolute deadlines. Resume is not pause. Sweep overdue
   attempts at startup and during operation; reject late edits. Test with an
   injected clock instead of sleeping through real exams.
6. Multiple-answer grading is exact-set matching with no partial credit.
   RUSH requires explicit confirmation; draft selections never receive credit.
   Unscored items do not enter the main percentage. Practice percentages and
   targets must never be labeled official scaled scores or official pass marks.
7. Each attempt snapshots its settings, bilingual content, correct options,
   references and notes. New bank versions or settings must never mutate old
   reports or active attempts. Version pairs are immutable.
8. Last-five averages are per user and bank ID, from completed quiz percentages,
   not exams or RUSH. Preserve access to historical banks when disabled or replaced.
9. Use revision checks to prevent stale tabs overwriting saved answers. Bind
   mutating requests to the expected signed-in profile as well as its cookie.
10. Backup/export code must not accidentally expose another profile's records,
    password derivatives or session tokens. Personal exports are not full backups.

## RUSH invariants

Read `docs/RUSH.md` before changing this state machine. Confirming a wrong answer,
marking its unused suffix discarded, consuming a new full set, resetting the
streak and persisting feedback must be **one transaction** with one revision
change. Feedback acknowledgement never draws again. The absolute deadline does
not change. Every generated question enters the denominator immediately, even
if the session expires on the feedback screen. Score only confirmed exact-set
matches; never grade saved drafts at timeout. Reaching N consecutive correct
answers finishes the session even when its overall percentage is below 100%.
Keep `result.rush.completed` separate from percentage targets (null for RUSH).

New rounds use the attempt's pinned content version and settings, not the
current catalog. Do not allow skipping, flagging, editing confirmed responses,
answering while feedback is pending, or duplicate grading via stale tabs.
Test multi-select confirmation, transaction rollback, 13/20=65%, clock expiration,
restarts, language switching, hidden future answers, API ownership and exports.
Keep the admin form, localization files, schemas, toolkit and tests synchronized.

## Bank changes and authoring

Read `schema/README.md` and the downloadable kit's README and AGENTS.md. A bank
ZIP contains exactly two root JSON files. The standard-library validator is
canonical for semantic constraints that JSON Schema cannot express across files.
Do not weaken validation to accept missing translations or inconsistent answers.

Use `schema_version` for changes to the file contract (v1 remains readable;
v2 adds optional RUSH defaults and is used by exports), and a bank's `version`
for content revisions. If changing validator behavior, update both JSON Schemas,
authoring prose in `schema/authoring/` and rebuild the validator copy inside the
toolkit with `python3 tools/build_authoring_kit.py`. Validate the bundled
bank, the importable example and exported archives after changes. Never package
private progress, real user sessions, generated caches or test databases.

Questions must be original, self-contained, unambiguous and supported by checked
primary references. Multiple-answer prompts state the exact selection count.
Every option needs a specific explanation. Prefer plausible distractors based
on relevant conceptual confusions. Do not use position-dependent wording because
choices are shuffled. English and Spanish must test the same requirement.
Mechanical validation cannot establish subject-matter correctness or official
exam calibration; communicate those limits honestly.

## Security and operational constraints

Never extract uploaded ZIP entries to disk. Inspect entry names, count, expansion,
compression methods and encryption/symlink flags before parsing bounded UTF-8
JSON. Reject duplicate keys and unknown fields. Never execute bank content.
Keep profile credentials hashed with a salted, work-factored password derivation.
Do not log raw passwords, cookies or uploaded answer banks.

Static serving must stay allowlisted; never expose source, `data/`, bank ZIPs,
keys or arbitrary filesystem paths. Escape untrusted text in the DOM, restrict
reference URLs, keep CSP and same-origin checks, and test non-admin direct API
requests rather than relying only on hidden UI buttons. Preserve request and
hashing concurrency limits. Prefer local error codes and localized UI messages.

Treat this as a trusted-LAN tool, not a publicly hosted service or a proctored
exam system. Do not silently open firewall ports, create router mappings, install
certificates, transmit telemetry or connect to external services.

## Validation before delivery

Run from the repository root:

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q app.py trainer tests
python3 app.py --validate-bank banks/aws-clf-c02-3.0.0.zip
python3 app.py --validate-bank docs/example-bank.zip
```

Add regression tests for changed behavior. Exercise new-bank import, duplicate
version rejection, admin configuration, separate users, cross-bank cycles,
scored/unscored counts, timeouts, revision conflicts and immutable snapshots.
Check locale key and placeholder parity. Test invalid ZIP and JSON cases too.

Inspect login, bank catalog, question navigation, reports, history and admin
forms at narrow phone widths and desktop widths, in both languages. New-question
navigation should scroll to a useful starting position; answer saves should not
jump away from the current choice. Confirm saved state after errors. Where a
validation environment restricts browser navigation or other capabilities,
document the exact test method rather than implying a physical-device or full
network test that was not performed.

Storage marker 4 accepts and upgrades marker 3 without removing records. Never
reset admin credentials or a v3 bank deck on upgrade. V1/v2 progress is unsupported.

For delivery, use a new release directory, include all source, README.md,
AGENTS.md, schemas, the authoring kit and independent content ZIPs. Exclude
`data/`, `__pycache__`, `.pyc`, cookies, keys and private QA artifacts. Verify the
extracted release can validate banks and pass tests without installing packages.
