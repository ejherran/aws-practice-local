# AWS Practice Local 4.0 — RUSH

A local, multi-user certification practice web application. Run one Python
process on a computer and use the application from browsers on the same trusted
network, including phones. No packages to install, API keys, subscriptions,
CDNs, translation services or cloud resources are required.

**Requirements:** Python 3.10 or newer with its standard library, and a modern
browser with JavaScript enabled. The server uses only standard-library modules.
The frontend is native HTML, CSS and JavaScript. English and Spanish are included.

## Quick start

Extract this release into a **new folder**. A fresh install is ready immediately.
To preserve a v3 installation, stop the old server, back up its entire `data/`
folder, and copy that folder to this release **before the first launch**. The
v3 database marker is upgraded automatically; profiles, passwords, banks,
active quizzes/exams and history remain intact. Do not run v3 on the upgraded
database. Keep the untouched backup to roll back. V1/v2 databases are unsupported.
See [UPGRADE.md](docs/UPGRADE.md) for exact precautions.

From the folder containing `app.py`:

**Windows**

```powershell
py -3 app.py
```

Alternatively, double-click `start_windows.bat`.

**macOS / Linux**

```bash
python3 app.py
```

Alternatively, run `sh start.sh`. The terminal prints the addresses to open:

```text
This computer: http://127.0.0.1:8080
Local network: http://YOUR-COMPUTER-IP:8080
```

Use the actual address printed by the server, not the placeholder. Connect the
phone and computer to the same reachable LAN. A guest Wi-Fi network may isolate
devices. The computer must remain running and must not sleep during use. Allow
the chosen port through your computer's firewall only on the trusted private
network. Do not forward the port from your router to the internet.

The first startup installs the bundled Cloud Practitioner bank automatically.

### Initial administrator

```text
Username: Admin
Password: Aws+10C41
```

The account is created **once per new data directory**. Restarting never resets
its password. Sign in and change it under **Profile** before sharing access to
the server. This initial password is intentionally documented and must not be
considered secret. Other users select **Create profile** and choose their own
credentials. Registration cannot create administrator accounts.

The administrator can also practice, with a separate personal history just like
other users. Normal users cannot import banks, change formats, read the admin
audit log or export full question banks through the API.

## Practice and results

The included `aws-clf-c02` bank has **310 original questions**, each available
in English and Spanish, including all options, general explanations, every
option explanation and applicable notes. It has 242 single-answer questions
and 68 questions requiring exactly two answers. It is independent practice
material, not an official AWS exam or an exam dump.

Initial Cloud Practitioner formats:

| Mode | Questions | Time | Scored / unscored |
|---|---:|---:|---:|
| Quiz | 10 | 13 minutes 51 seconds | 10 / 0 |
| Exam | 65 | 90 minutes | 50 / 15 |
| RUSH | 10 per set; target 10 consecutive | 10 minutes total | Every generated question |

The quiz time is calculated proportionally: `5400 × 10 / 65`, rounded to the
nearest whole second. The administrator can change all three formats per bank.
These are the supplied bank's defaults, not constants in the engine.

Each user's home page shows a separate card for every enabled certification,
including the arithmetic mean of the **last five completed quiz percentages**
for that bank. With fewer than five quizzes, the app uses the available results
and identifies the sample size. Exams and RUSH sessions do not enter that average. Quizzes from
older versions of the same bank still count; different bank IDs never mix.

You can review every completed quiz, exam and RUSH session in **History**, filter by bank or
mode, reopen its full report, export result JSON, print a report, and filter the
question review by outcome or domain. History remains accessible when a bank is
disabled or updated. Personal progress exports do not include password hashes,
session tokens or another user's results.

### RUSH: consecutive answers against one clock

Choose **Start RUSH** on a bank card. By default, reach **10 correct answers in
a row within 10 minutes**. Select the required option(s) and press **Confirm
answer**. A correct answer advances immediately; a wrong answer resets the
streak, generates a new full set, and immediately shows the correct answer and
its explanation. Read it, then choose **Continue with the new set**.

**Time does not reset or pause during feedback.** A generated set counts in full,
even when an error discards its remaining questions. Only confirmed answers can
score; saving or selecting an option is not a graded submission. The session
ends on success, timeout, or explicit **End RUSH and view report**.

```text
RUSH percentage = 100 × total confirmed correct answers / total generated questions
```

Example: three correct answers, one error, then ten correct answers gives
**13 / 20 = 65%**, and the streak is completed. The abandoned six questions from
the first set still count in the denominator. Streak completion is a separate
outcome from the percentage, not a 100% threshold.

The report includes all generated questions and explanations, best streak,
sets, restarts and confirmed-answer counts. Filter the review by wrong answers,
discarded questions, unanswered questions or unconfirmed selections. RUSH has
its own **History** mode filter and never changes the last-five quiz average.
Both languages, profile isolation, resume and versioned bank snapshots apply.
A full specification, edge cases and API notes are in [RUSH.md](docs/RUSH.md).

### Timing, navigation and grading (quiz and exam)

- Questions and answer options are shuffled when the session is created. Their
  order is then saved; reloading or switching languages does not reshuffle them.
- Every confirmed answer and review flag is stored on the server. Wait for the
  saved confirmation, especially on an unreliable network. If a request fails,
  the UI restores the confirmed state and asks you to check and retry.
- A session has an absolute server-side deadline. Closing the tab, switching
  devices or restarting the server does not pause or reset the clock. After an
  outage, overdue sessions are finalized when the server restarts.
- One active session is allowed per user across all certifications. Different
  users can practice concurrently. Sign in with the same profile to resume from
  another device. Do not change the server's system clock during practice.
- Unscored questions are selected when an attempt starts and are not identified
  in the active-session response or interface. The completed report identifies
  them and explains them just like the other questions.
- Multiple-answer questions require the exact set of correct options. There is
  no partial credit. Blank or incomplete answers receive no credit. Only scored
  questions enter the main percentage; a separate total covers every question.

Results are **practice percentages**, not AWS scaled scores. The configurable
80% initial practice target is an application goal, not an official pass mark.
The app does not convert results into a supposed score out of 1000 or guarantee
that reaching the practice target predicts certification success.

### No-repeat cycles

A separate deck exists for each **user + bank ID + bank version**. Quizzes, exams and RUSH
sets consume the same deck without replacement. Questions are assigned when a
session starts, so abandoning a session does not return its questions to the
unseen pool. At exhaustion, another shuffled cycle begins.

A quiz, exam or individual RUSH set crossing a cycle boundary can draw from both
cycles, but never contains a duplicate question. A long RUSH session may repeat
questions in later sets only after the shared bank cycle is exhausted. Domain weights are best-effort quotas. If the
remaining pool cannot satisfy exact weights without repetition, no repetition
takes priority and the completed report identifies the adjusted distribution.
Question order is shuffled after selection as well.

A new content version starts its own fresh deck. A format-only change preserves
the current version's remaining-question cycle.

## English and Spanish

Use the header language selector before signing in or during practice. A signed-in
user's preference is saved in the profile. The bundled bank has complete local
translations; changing language preserves the attempt, answers, option order,
review flags and deadline.

The UI supports both languages for every bank. Imported banks may declare either
or both supported languages. Every declared language must be fully populated.
For a monolingual bank, the app displays a clear content-language fallback notice
instead of claiming to translate missing questions. External reference links are
optional reading and require internet access when clicked; practice does not.

## Administrator workflow

Open **Administration** after signing in as `Admin`.

### Import a certification bank

1. Choose a ZIP containing exactly `manifest.json` and `questions.json` at its root.
2. Select **Validate ZIP** and inspect the title, version, languages and count.
3. Select **Import bank**. For an existing bank ID, confirm the version replacement.

A new certification uses a new `bank_id`. Revised content uses the same ID and a
new version such as `1.1.0`. An already imported ID/version pair is immutable and
cannot be overwritten. Version numbers identify releases; numeric ordering is
not enforced. Imported content is stored locally in SQLite, independently from
the Python engine. The original upload is not extracted into application folders.

Importing a new version makes it current and applies its manifest defaults to
**future sessions**. Previously started attempts and completed reports retain
snapshots of their original content, translations and settings. Importing a
replacement never silently rewrites old answers or report explanations.

### Configure a bank

Each bank has independent quiz, exam and RUSH settings:

| Setting | Behavior |
|---|---|
| Question count | 1 to the smaller of 500 and the available bank size. |
| Time limit | 1 to 86,400 seconds; exam and RUSH timing is fixed. |
| Unscored questions | Quiz/exam only: zero to one less than the mode's question count. Hidden until completion. RUSH scores all generated questions. |
| Proportional quiz timing | Calculates quiz seconds from the exam's duration and question count. Disable it for a fixed quiz time. |
| Practice target | Quiz/exam percentage from 0 to 100, never an official pass mark. RUSH uses its consecutive-answer goal instead. |
| RUSH goal | `question_count` correct answers in a row, default 10 (capped at bank size for tiny banks). |
| Domain weights | Integer percentages totaling 100. No-repeat selection has priority over exact quotas. |
| Available to learners | Disabling prevents new sessions, without deleting history or blocking an existing session. |

Saved settings affect only future attempts. The admin page also exports the
current bank as a ZIP, including its current format settings, and shows recent
bank import/configuration activity. Import updates through this page rather than
editing the SQLite database or overwriting application source files.

## Create new banks: schema and AI authoring

Contract v2 adds optional `defaults.rush` with `question_count` and
`duration_seconds`. The app still imports unchanged contract-v1 banks, applying
RUSH defaults automatically. Bank exports use v2 and retain the content version;
the bundled 310-question bank uses contract v2 / content version 4.0.0.
The updated authoring kit documents both contracts. V2 banks require engine 4+.


Any signed-in user can download **the authoring kit ZIP** from the footer. The
administrator also has a download button in Administration. A copy ships at:

```text
schema/question-bank-authoring-kit.zip
```

The kit includes:

```text
README.md                    Detailed contract and workflow
AGENTS.md                    Editorial and AI-authoring instructions
manifest.schema.json         Manifest JSON Schema
questions.schema.json        Question-array JSON Schema
example/manifest.json        Editable bilingual example
example/questions.json       Editable bilingual example
example-bank.zip             Importable four-question example
build_bank.py                Standard-library ZIP builder
validate_bank.py             Standard-library semantic validator
validator/                   Shared validation implementation
```

**The kit itself is not an importable bank.** Its `example-bank.zip` is. The
example is illustrative, not a complete study bank, and is not installed in the
normal catalog by default. A second copy is in `docs/example-bank.zip` for tests.

After editing a copy of the example folder:

```bash
python3 build_bank.py my-bank my-certification-1.0.0.zip
python3 validate_bank.py my-certification-1.0.0.zip
```

You can also validate a completed bank with the main app, without starting the
server or changing data:

```bash
python3 app.py --validate-bank my-certification-1.0.0.zip
```

The contract supports single-answer and multiple-answer questions. Different
certifications can have different banks, domains, counts, timings and unscored
counts without modifying the engine. This is not a claim that every possible
interactive question format or psychometric scoring method is implemented.
Verify each certification's current official guide before authoring its bank.

The bank limit is 5,000 questions, 10 MiB compressed and 40 MiB expanded. ZIPs
must contain only the two JSON entries; no folder wrappers, hidden operating-
system files or attachments. ZIP_STORED and DEFLATE are supported. The importer
rejects malformed or duplicate-key JSON, missing translations, inconsistent
answer counts, unknown references/domains, invalid format settings, encrypted
entries, symlinks and excessive expansion ratios. It never executes bank content.

Validation establishes structural consistency, **not factual accuracy** or exam
calibration. Review content, translations and distractors separately. The
original Cloud Practitioner bank retains a September 6, 2026 content reference
date and relevant terminology/availability notes from the preceding review.

## Storage and backups

The app creates:

```text
data/practice.sqlite3
```

This local SQLite file contains profiles, hashed passwords, session records,
versioned imported content, format settings, decks, attempt snapshots, results
and the administration audit log. No database server is required.

**For a full backup:** stop the app, copy the entire `data` directory to safe
storage, then restart. Restore with the server stopped, using the same application
storage version. Treat backups as sensitive: they contain all local accounts and
results. Imported banks are included in the database backup. Exporting a bank is
not a backup of progress. A personal JSON export is for inspection, not automatic
restoration. The server host's operating-system account can read local files;
application roles are not protection against someone with host administrator access.

### Local password recovery

Run from the application folder. Prefer stopping the server first:

```bash
python3 app.py --reset-password Admin
```

The command prompts twice without placing the new password in shell history.
It preserves the profile's role and progress and revokes that user's sessions.
Use the username of a learner to reset that learner's password instead.
For a custom data directory, pass the same `--data-dir` used by the server.

## Other startup options

```bash
# Use a different port.
python3 app.py --port 8090

# Listen only on this computer.
python3 app.py --host 127.0.0.1

# Store progress somewhere else.
python3 app.py --data-dir /path/to/practice-data

# Do not permit additional learner registrations.
python3 app.py --disable-registration

# A new installation without automatic starter bank installation.
python3 app.py --no-starter-banks --data-dir /path/to/new-empty-data

# Optional HTTPS with a certificate and key you already manage.
python3 app.py --cert-file /path/to/certificate.pem --key-file /path/to/private-key.pem

# Print all available options.
python3 app.py --help
```

For HTTPS, the browser must trust the certificate and its name must match the
address used. The application does not obtain certificates from an external
service. Keep private keys outside distributed source and backups shared with
others.

`banks/` is only a first-install seed directory. Startup imports an unknown bank
ID once; it never reverts a current version or overrides administrator settings.
Use the admin upload workflow for updates. `--no-starter-banks` skips this seed
step but does not remove banks already stored in an existing database.

## Security boundaries

Use a trusted private LAN. The built-in HTTP server is not presented as a
public-internet production service. HTTP is unencrypted, so use unique
application passwords and change the documented administrator password.
Optional TLS is available for deployments where you manage a trusted certificate.

Passwords are derived with PBKDF2-HMAC-SHA256, unique salts and 600,000 iterations.
Session tokens are stored as hashes and use HttpOnly/SameSite cookies; Secure is
added under HTTPS. Password changes revoke other sessions. The app checks roles,
attempt ownership, profile binding, request origins, allowed hosts and upload
limits. Active quiz/exam responses exclude solutions and scoring flags. Active RUSH
responses expose only the current question, plus the explicitly confirmed failed
question when feedback is pending; future questions remain hidden. Imported
text is escaped in the UI and references are restricted to HTTPS URLs.

These controls are not an independent security audit or secure exam proctoring.
Do not expose the port publicly. A local administrator can inspect the database
and the full question banks by design. Users share one server, not one progress
profile. There is no public password-recovery service or email integration.

## Source layout

```text
app.py                       CLI, startup, optional TLS and deadline sweeper
trainer/auth.py              Profiles, password hashing and sessions
trainer/banks.py             Bank contract, ZIP validation and version repository
trainer/engine.py            Generic question selection, timing and scoring
trainer/storage.py           SQLite schema and transactional access
trainer/server.py            HTTP routes, static allowlist and access checks
web/app.js                   Native browser application
web/styles.css               Responsive desktop/mobile presentation
web/locales/en.json           English interface and error messages
web/locales/es.json           Spanish interface and error messages
banks/*.zip                  Independent starter content
schema/                     Schemas and portable authoring kit
tests/                      Standard-library unit and HTTP integration tests
docs/                       RUSH specification, upgrade guide, architecture, QA and example bank
AGENTS.md                   Instructions for maintainers and coding agents
```

Source identifiers, comments and developer documentation are English. Spanish
appears only as localized UI or educational content. There is no `requirements.txt`
because there are no third-party runtime or test-suite requirements.

## Tests and maintenance

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q app.py trainer tests
```

Tests use temporary databases and never modify `data/`. Authentication tests use
real production password derivation, so test duration depends on the computer.
Read `docs/QA.md` for the validation performed on this release and its limits.
Read `AGENTS.md` before modifying the engine or generating another bank.

Editable authoring-kit sources are in `schema/authoring/`. After changing the
contract, schemas or authoring instructions, rebuild the downloadable kit with:

```bash
python3 tools/build_authoring_kit.py
```

The builder copies the canonical validator into the standalone kit and refreshes
the importable example. It does not import content into your progress database.

Official format reference for the bundled bank:
https://docs.aws.amazon.com/aws-certification/latest/cloud-practitioner-02/cloud-practitioner-02.html
