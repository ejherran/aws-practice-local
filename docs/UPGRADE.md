# Upgrade from version 3 to version 4

The v4 engine can open a v3 `data/practice.sqlite3` database. It preserves local
profiles and passwords, imported bank versions and settings, decks, completed
results and active quizzes/exams. It adds normalized RUSH defaults without
rewriting question content or resetting progress.

## Recommended procedure

1. Stop the v3 server with Ctrl+C. Do not run both versions against one database.
2. Copy the entire old `data/` directory to a separate, safe backup location.
   Keep the old v3 application folder too. Never make this backup while either
   server is writing the database.
3. Extract v4 into a new directory. Before its first launch, copy the old `data/`
   directory into it. Do not merge two existing progress databases.
4. Launch `py -3 app.py` on Windows or `python3 app.py` on macOS/Linux from the
   new application folder. Existing credentials still apply; the administrator
   password is not reset.
5. Open the printed address, reload the browser to load the v4 UI, check History,
   and verify the bank formats under Administration. RUSH should appear as the
   third practice mode for each enabled bank.

A clean install instead creates a fresh local database and the documented
initial administrator. V1/v2 progress schemas are unsupported; do not copy
those databases into v4.

## Compatibility details

Storage marker 3 is upgraded to marker 4 transactionally using the existing
relational columns. This marker change prevents the old v3 engine from trying
to process new RUSH attempts. **Do not run v3 on the upgraded database.** To roll
back, stop v4 and restore the untouched backup into the old application folder.
Any results produced after the backup are not present in that rollback.

An existing active quiz/exam retains its absolute deadline during the upgrade.
It may expire while the server is stopped; upgrades do not pause clocks. RUSH
state, including pending feedback, also survives subsequent v4 restarts.

Legacy schema-v1 bank ZIPs still import without edits. RUSH defaults are 10
questions (or bank size when smaller) and 600 seconds. Explicit RUSH settings in
bank files use contract v2; newly exported banks and the updated authoring kit
use that contract. App v3 cannot import contract-v2 exports. Content versions
and the bundled `aws-clf-c02-4.0.0.zip` and `aws-aif-c01-1.1.0.zip` banks are
independent of app versions. Startup installs a previously unknown starter bank
ID, including AI Practitioner on an existing installation that does not already
contain it. It does not replace an existing version of the same bank ID; use the
administrator bank-import workflow for content updates.

Only local LAN connectivity is required. No migration downloads, package
installation, cloud services or network calls are made.

## HTTPS and inactivity update

After installing this update, open `https://` instead of `http://`, using the
same port. A first startup creates `data/tls/` with a unique certificate and key;
existing complete pairs are reused. Trust the public certificate on each client
after comparing its SHA-256 fingerprint with the server console. See README.md
for renewal, changed addresses and custom certificates. Browser settings and
certificate trust stores are never modified automatically.

Saved profiles, passwords, banks, settings, question cycles and attempts remain
intact. The sessions table gains a persisted activity timestamp without changing
the storage marker. Legacy sessions use their original sign-in time and expire
if it was at least an hour ago; signing in again restores access to saved work.
Do not run the older application against this updated database; use your
stopped-server backup to roll back. HTTPS is a different browser origin, so a
previous HTTP cookie/local UI preference is not reused. Server-side progress is
unaffected.
