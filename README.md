# AWS Practice Local

A local, multi-user certification practice app for desktop, tablet and phone.
Run one Python process and practice from browsers on the same trusted network.
Your profiles, question banks and progress stay on the server computer.

**Version 4.0** includes bilingual English/Spanish practice, searchable question
banks, quizzes, timed exams and RUSH challenges. No pip packages, Node build,
API keys, subscriptions, CDNs or cloud services are required.

This is independent practice material, **not an official AWS exam, exam dump or
proctored testing system**. Use it on a trusted private LAN, not the public internet.

## Contents

- [Quick start](#quick-start)
- [Included question banks](#included-question-banks)
- [Practice and results](#practice-and-results)
- [Administration and bank authoring](#administration-and-bank-authoring)
- [HTTPS and session security](#https-and-session-security)
- [Data, backups and upgrades](#data-backups-and-upgrades)
- [Startup options](#startup-options)
- [Troubleshooting](#troubleshooting)
- [Development and validation](#development-and-validation)

## Quick start

### 1. Prepare the application

Use Python **3.10 or newer** and a modern browser with JavaScript enabled.
The backend uses the Python standard library; the frontend is native HTML,
CSS and JavaScript. Certificate generation uses the OpenSSL library already
linked to Python, not an external executable. See [HTTPS requirements](#local-https)
if using an unusual Python distribution.

Extract the release into a **new folder**, or work from a checkout of this
repository. No dependency installation or database setup is needed.

**Already using the app?** Stop the old server and back up its entire data
directory before updating. Preserve that directory before the new version's
first launch; see [Upgrades](#upgrades). Do not merge two progress databases.

### 2. Start the server

Run these commands from the folder containing `app.py`.

Windows:

```powershell
py -3 app.py
```

You can also double-click `start_windows.bat`.

macOS / Linux:

```bash
python3 app.py
```

You can also run `sh start.sh`. The terminal prints the actual addresses,
data location, certificate path and SHA-256 fingerprint. With the default port:

```text
This computer: https://127.0.0.1:8080
Local network: https://YOUR-COMPUTER-IP:8080
```

Replace the placeholder with the actual address printed by the server.
First startup creates local storage, the initial administrator, both starter
banks and a unique self-signed HTTPS identity.

### 3. Verify HTTPS and sign in

Before entering credentials, verify the certificate fingerprint against the
server terminal and explicitly trust the public certificate on the client
device. See [Local HTTPS](#local-https) for the full procedure. The app never
installs certificate trust automatically, and plain `http://` is rejected.

Initial credentials for a **new data directory**:

| Username | Password |
|---|---|
| `Admin` | `Aws+10C41` |

Change this documented password under **Profile** before sharing access.
The account is created once; restarting or upgrading never resets a changed
password. Other users choose **Create profile** and receive learner accounts,
never administrator privileges.

### 4. Connect a phone or another computer

Keep both devices on the same reachable, trusted LAN and open the printed LAN
`https://` address. On a phone, `127.0.0.1` refers to the phone itself, not the
server computer. Each client needs to trust the verified certificate.

Keep the server computer awake and the Python process running. Guest Wi-Fi may
isolate devices. If required, allow the selected port through the host firewall
**only for the trusted private network**. The app does not change firewall
rules or router settings. Do not forward the port to the internet.

Press **Ctrl+C** in the server terminal to stop it. Confirmed progress is saved;
stopping the process does not pause an attempt's deadline.

## Included question banks

The two independent starter archives contain **610 bilingual questions**:

| Certification | Bank ID | Content version | Questions |
|---|---|---|---:|
| [Cloud Practitioner — CLF-C02](banks/aws-clf-c02-4.0.0.zip) | `aws-clf-c02` | 4.0.0 | 310 |
| [AI Practitioner — AIF-C01](banks/aws-aif-c01-1.1.0.zip) | `aws-aif-c01` | 1.1.0 | 300 |

Cloud Practitioner includes 242 single-answer and 68 two-answer questions.
AI Practitioner includes 240 single-answer, 54 two-answer and six three-answer
questions across five domains and all 14 task statements. Both include local
English/Spanish prompts, options, explanations and applicable notes.

Initial formats for both banks:

| Mode | Questions | Time | Scored / unscored |
|---|---|---|---|
| Practice quiz | 10 | 13 min 51 sec | 10 / 0 |
| Full exam | 65 | 90 min | 50 / 15 |
| RUSH | 10 per set; goal of 10 consecutive correct | 10 min total | Every generated question |

Quiz time is proportional to the exam: `5400 × 10 / 65`, rounded to the nearest
second. Administrators can change formats per bank; these values are content
defaults, not engine constants or a claim of official exam calibration.

At startup, the app imports starter ZIPs only for **previously unknown bank
IDs**. Replacing a ZIP on disk does not update an existing imported bank or
overwrite its settings. Use the administration import workflow for updates.

## Practice and results

### Choose a bank and a mode

The bank menu searches by name or exam code in either language, including
accent-insensitive matches. Desktop uses a scrollable sidebar; phones use a
collapsible selector. The last selected bank is remembered per profile in that
browser, while progress remains server-side.

Each mode is a full-card action, with the bank's progress summary underneath.
Phone layouts include compact labeled navigation, large touch targets, stacked
filters and a shorter sticky attempt header that keeps the timer visible.
Answer saves preserve scroll position and keyboard focus.

Only **one active attempt per user** is allowed across all banks. Use
**Continue session** to resume it, including from another device signed in
with the same profile. Separate users can practice concurrently.

### Quizzes and exams

- Questions and options are shuffled once at creation and their order is saved.
  Reloading, resuming or changing language does not reshuffle them.
- Answer selections and review flags are stored on the server. Wait for the
  saved confirmation. After a failed save, check the restored server-confirmed
  selection and retry.
- Navigate freely between questions, flag items for review and submit when
  ready. The server finalizes overdue attempts automatically.
- Multiple-answer grading requires the exact set of correct options, with no
  partial credit. Blank or incomplete answers receive no credit.
- Unscored questions are chosen at creation and hidden as such until the report.
  They do not enter the main percentage.
- Deadlines are absolute. Closing the tab, losing connectivity, signing out or
  restarting the server does not pause the clock. Do not change the server's
  system time during practice.

### RUSH: a consecutive-answer challenge

Select the required option(s), then press **Confirm answer**. A correct answer
advances the streak. A wrong answer resets the streak, discards the unused
suffix of the set and generates a new full set. Read the immediate explanation,
then choose **Continue with the new set**.

The clock **never resets or pauses**, including during feedback. Only confirmed
answers score; draft selections do not. The session ends when the streak goal
is reached, time expires or you choose **End RUSH and view report**.

```text
RUSH percentage = 100 × confirmed correct answers / all generated questions
```

For example, three correct answers, one error, then ten correct answers gives
**13 / 20 = 65% with the streak completed**. The six discarded questions from
the first set still count. Streak completion and percentage are separate
outcomes. See [the RUSH specification](docs/RUSH.md) for full rules and examples.

### Progress, history and question cycles

The bank summary averages the **last five completed quiz percentages** for
that user and bank ID. With fewer quizzes, it uses the available results and
shows the sample size. Exams and RUSH never affect this average; older content
versions of the same bank still count.

**History** lets you filter by bank or mode, reopen reports, review explanations
and references, export result JSON and print reports. Historical results remain
available after a bank is disabled or replaced. Results are practice percentages,
not AWS scaled scores. The initial 80% practice target is configurable and is
**not an official pass mark or a guarantee of certification success**.

A separate question deck exists for each **user + bank ID + content version**.
Quizzes, exams and RUSH sets share that deck without replacement. Questions are
consumed when assigned; abandoning an attempt does not return them to the pool.
After exhaustion, a new cycle begins.

There are no duplicate questions within a quiz, exam or individual RUSH set,
even across cycle boundaries. Later RUSH sets can revisit questions only after
the shared cycle is exhausted. No-repeat selection takes priority over exact
domain quotas; reports identify distribution adjustments. New content versions
start a fresh deck; settings-only changes preserve the current deck.

### English and Spanish

Change language from the header at any time. Signed-in preferences are saved
to the profile. Answers, option order, flags and deadlines remain unchanged.

Imported banks can declare English, Spanish or both; every declared translation
must be complete. A monolingual bank shows a content-language fallback notice.
The app never calls a translation service. Optional external reference links
need internet access when opened; practice itself does not.

## Administration and bank authoring

Open **Admin** using the initial administrator profile. Administrators can
practice with their own progress, but bank-management privileges do not grant
access to another user's practice endpoints or personal exports.

### Import or update a bank

1. Choose a ZIP containing exactly `manifest.json` and `questions.json` at its root.
2. Select **Validate ZIP** and inspect the title, version, languages and count.
3. Select **Import bank**. Confirm replacement if that bank ID already exists.

Use a new `bank_id` for a new certification and the same ID with a new `version`
for revised content. ID/version pairs are immutable: duplicates cannot be
overwritten. Numeric version ordering is not enforced.

A replacement becomes current and applies its defaults to **future attempts**.
Active attempts and old reports retain snapshots of their original content,
translations and settings. Imported content is stored in SQLite; uploaded ZIP
entries are never extracted to application folders or executed.

### Configure formats

| Setting | Behavior |
|---|---|
| Question count | 1 to the smaller of 500 and the bank size. |
| Time limit | 1–86,400 seconds; fixed for exam and RUSH. Quiz can be proportional. |
| Unscored questions | Quiz/exam only: 0 to one less than the question count; hidden until completion. |
| Practice target | Quiz/exam only: 0–100%; never an official passing score. |
| RUSH goal | The set's question count, reached as consecutive correct answers. |
| Domain weights | Integer percentages totaling 100; no-repeat rules take priority. |
| Available to learners | Disabling prevents new attempts but preserves history and active attempts. |

Changes affect future attempts only. The admin page also exports the current
bank with its settings and shows recent import/configuration activity.
Learners cannot access these management operations through the UI or API.

### Author a new bank

Download the authoring kit from the app footer, or use
[schema/question-bank-authoring-kit.zip](schema/question-bank-authoring-kit.zip).
It contains the contract guide, authoring instructions, JSON Schemas, a
standard-library builder/validator and an importable example.

**The authoring kit itself is not an importable bank.** Use its
`example-bank.zip` as an example, not a complete study bank. After editing a
copy of the kit's example directory:

```bash
python3 build_bank.py my-bank my-certification-1.0.0.zip
python3 validate_bank.py my-certification-1.0.0.zip
```

From the app directory, validate an archive without starting the server or
modifying the database:

```bash
python3 app.py --validate-bank my-certification-1.0.0.zip
```

The contract supports single- and multiple-answer questions, bank-specific
domains and configurable formats. Limits are **5,000 questions, 10 MiB
compressed and 40 MiB expanded**. Only the two root JSON files are allowed;
ZIP_STORED and DEFLATE are supported. Malformed or duplicate-key JSON, unknown
fields, missing translations, inconsistent answers, encrypted/symlink entries
and excessive expansion are rejected.

Contract v1 remains readable. Contract v2 adds optional RUSH defaults and is
used by exports and both starter banks; v2 requires app version 4 or newer.
The bank's content version and the file contract's `schema_version` are distinct.

See [the schema guide](schema/README.md) for the complete contract.
Validation establishes structural consistency, **not factual accuracy or exam
calibration**. Review facts, translations, references and distractors separately,
using the certification's current official guide. See
[the changelog](docs/CHANGELOG.md) for bundled content revisions and review notes.

## HTTPS and session security

### Local HTTPS

The app requires **TLS 1.2 or later**. With the default configuration, it creates
`data/tls/` only when that identity directory is absent, then reuses the existing
certificate/key pair. Invalid, expired or incomplete pairs stop startup; there
is no plaintext fallback and no silent renewal.

The generated identity uses RSA-3072/SHA-256, lasts one year and covers
`localhost`, loopback addresses, the hostname and detected local IPs at creation.
Generation uses Python's linked OpenSSL library through standard-library
`ctypes`. No pip package, external OpenSSL command or certificate service is
needed. Python builds that do not expose the required OpenSSL symbols must use
an existing certificate/key pair.

To connect safely:

1. Obtain the public `data/tls/server-cert.pem` and the SHA-256 fingerprint
   printed in the server terminal.
2. Transfer **only the public certificate** to the client and compare its
   fingerprint through a trusted channel.
3. Explicitly trust the verified certificate using the device/browser's
   supported certificate settings, then open a covered `https://` hostname/IP.

Trust steps differ by device and browser. An untrusted device will show a
certificate warning; do not blindly bypass it. The app never modifies trust
stores. Keep `server-key.pem` private and out of shared archives and Git.

Generated TLS directories are owner-only on POSIX; Windows grants access to
the owner and SYSTEM. For renewal or an address change, stop the server and
move the existing `data/tls/` to a protected backup location before restarting.
Verify and trust the new identity on each client. Do not remove the database.
A stable hostname or reserved LAN IP can reduce address changes.

Custom identities use `--cert-file` and `--key-file` together. Supply a valid
PEM certificate with matching SAN names and an unencrypted matching private key
readable by the server account. Custom files are never generated or overwritten.

### Inactivity timeout

Authentication expires after **one hour without acknowledged user interaction**,
with a separate maximum lifetime of 30 days. The server persists and enforces
both limits. Clicks, typing, wheel scrolling and touch interactions send activity
notices at most once every 20 seconds.

Reading without interaction counts as inactivity. Background polling, timer
updates and focus changes do not renew authentication. Tabs sharing a cookie
share its activity deadline; separate browser sessions have separate deadlines.

The UI checks every 15 seconds and when returning to a tab. It clears private
content on expiry, including when offline once the last known deadline is
reached. The API rejects expired cookies immediately. Sign in again to access
saved progress; attempt clocks continue while signed out.

### Security boundaries

Passwords use salted PBKDF2-HMAC-SHA256 with 600,000 iterations. Session tokens
are hashed in storage; cookies use Secure, HttpOnly and SameSite attributes.
Password changes revoke other sessions. Server checks enforce roles, ownership,
profile binding, origins, host validation and upload limits.

Active quizzes/exams do not reveal answer keys. RUSH exposes only its current
question, with immediate explanations for an explicitly confirmed wrong answer.
Future RUSH questions remain hidden. Imported text is escaped and reference
URLs are restricted to HTTPS.

These safeguards are not an independent security audit. Anyone with sufficient
host operating-system access can inspect the database and full question banks.
Use unique passwords and a trusted LAN. There is no cloud authentication,
email recovery service or public-hosting support.

## Data, backups and upgrades

By default, these files live beside `app.py`:

```text
data/
  practice.sqlite3       Profiles, sessions, banks, settings, decks and results
  tls/
    server-cert.pem     Public HTTPS certificate
    server-key.pem      Private key — never share
```

Use the same `--data-dir` consistently if choosing a different location.
Imported banks and immutable attempt snapshots are stored in SQLite.

### Full backup and restore

1. Stop the server with **Ctrl+C**.
2. Copy the entire data directory to protected storage, including TLS files.
3. Restart the server after the copy completes.

Restore with the server stopped and a compatible application version. Do not
merge databases or copy a live database while it is being written. Backups
contain all accounts, sessions, results and private keys: treat them as sensitive.

| Export or backup | Contains | Intended use |
|---|---|---|
| Bank ZIP | Current bank content and format settings | Import/share a bank; no user progress |
| Result JSON | One completed attempt belonging to the signed-in user | Review |
| Personal JSON | That profile's progress, without password derivatives, tokens or other users' records | Review; not automatic restore |
| Full stopped-server data copy | Database and local TLS identity | Disaster recovery or upgrade migration |

### Upgrades

Always extract an update into a **new directory**. Stop and back up the previous
installation, then copy its data directory before the new version's first start.
Existing passwords and progress are preserved; do not run two versions against
the same database.

Storage marker 3 upgrades automatically to marker 4. V1/v2 progress is
unsupported. Never reopen an upgraded database with older code; rollback uses
the untouched backup and old application. See [UPGRADE.md](docs/UPGRADE.md).

An upgrade from HTTP to HTTPS changes the browser origin, so old HTTP cookies
and local UI preferences are not reused. Server-side progress is unaffected.
Legacy sign-ins without activity metadata use their original sign-in time and
may immediately require signing in again. Deadlines continue during upgrades.

### Local password recovery

Prefer stopping the server first, then run from the application directory:

```bash
python3 app.py --reset-password Admin
```

The command prompts twice without putting the password in shell history.
It preserves role and progress and revokes the target user's sessions. Substitute
a learner's username to reset that profile. Include the original `--data-dir`
when using a custom location. On Windows, use `py -3` in place of `python3`.

## Startup options

Use `py -3` on Windows or `python3` on macOS/Linux. Run `app.py --help` through
that interpreter for the complete CLI reference.

| Option | Purpose / default |
|---|---|
| `--host ADDRESS` | IPv4 bind address; default `0.0.0.0` exposes the service to reachable LAN clients. Use `127.0.0.1` for this computer only. |
| `--port PORT` | HTTPS port; default `8080`. |
| `--data-dir PATH` | Database and generated TLS identity; default `data/` beside the application. |
| `--banks-dir PATH` | Starter ZIP directory; default `banks/` beside the application. |
| `--no-starter-banks` | Skip seed imports; does not remove existing banks. |
| `--disable-registration` | Prevent new learner registrations; existing users can still sign in. |
| `--cert-file PATH --key-file PATH` | Use an existing PEM certificate/key pair. |
| `--validate-bank PATH` | Validate a bank and exit without modifying data. |
| `--reset-password USERNAME` | Prompt for a new password locally and exit. |
| `--verbose` | Enable HTTP request logging. |

Examples:

```bash
# This computer only, with a different HTTPS port.
python3 app.py --host 127.0.0.1 --port 8090

# A separate installation with registrations disabled.
python3 app.py --data-dir /path/to/practice-data --disable-registration

# Use an existing TLS identity.
python3 app.py --cert-file /path/to/certificate.pem --key-file /path/to/private-key.pem
```

## Troubleshooting

| Symptom | Check |
|---|---|
| The page does not open over HTTP | Use `https://` and the printed port. Plain HTTP is intentionally rejected. |
| The phone cannot reach the server | Use the computer's LAN IP, not `127.0.0.1`; check the running process, sleep, Wi-Fi isolation and private-network firewall rules. |
| Certificate warning | Verify the fingerprint, trust the correct public certificate and use a hostname/IP listed in its SAN. Do not ignore an unexpected identity change. |
| Startup reports an invalid/incomplete TLS identity | Restore the matching pair, or follow the stopped-server renewal procedure above. Check the host clock for validity errors. |
| Certificate generation cannot access OpenSSL | Use a compatible CPython installation or provide an existing valid PEM pair. |
| Port already in use | Stop the previous instance or choose another `--port`; update the browser address too. |
| Signed out while reading | Reading alone counts as inactivity. Sign in again; saved answers remain, but the attempt deadline may have passed. |
| A save failed or another tab changed the attempt | Check the restored saved state and retry from the current profile; avoid editing one attempt from multiple tabs at once. |
| Copying a new bank ZIP did not update the catalog | Startup seeds unknown bank IDs only. Import the new content version through Admin. |
| Import says the version already exists | Use a new content version for a revision; an existing ID/version pair cannot be overwritten. |
| A bank ZIP is rejected | Validate it locally, check the two root JSON filenames, and ensure it is not the authoring-kit ZIP. |
| Old interface after an update | Reload the page and confirm the server is running from the new application directory. |

## Development and validation

### Source map

```text
app.py                       CLI, HTTPS startup and deadline sweeper
trainer/auth.py              Credentials and persisted sessions
trainer/banks.py             Bank ZIP contract and version repository
trainer/engine.py            Certification-agnostic practice and scoring
trainer/storage.py           SQLite schema and transactions
trainer/server.py            Routes, authorization and static allowlist
trainer/tls.py               Certificate generation and TLS configuration
web/                         Native responsive UI and English/Spanish locales
banks/                       Independent starter content archives
schema/                      Schemas, authoring sources and downloadable kit
tests/                       Standard-library unit and HTTPS integration tests
tools/check_ui.py            Optional isolated headless browser regression checks
tools/build_authoring_kit.py  Portable kit builder
docs/                        Architecture, upgrades, RUSH rules and validation notes
```

Read [AGENTS.md](AGENTS.md) before changing the source. Identifiers, comments and
developer documentation use English; Spanish belongs in localization fields
and educational content. Keep the runtime and normal test suite standard-library
only. Do not add hosted dependencies or expose private data through static routes.

### Run the checks

From the repository root, with Python site packages disabled:

```bash
python3 -S -m unittest discover -s tests -v
python3 -S -m compileall -q app.py trainer tests tools
python3 -S app.py --validate-bank banks/aws-clf-c02-4.0.0.zip
python3 -S app.py --validate-bank banks/aws-aif-c01-1.1.0.zip
python3 -S app.py --validate-bank docs/example-bank.zip
```

On Windows, substitute `py -3` for `python3`. Tests use temporary databases,
not your `data/`, and include real password derivation and HTTPS requests.
The latest recorded validation passed **245 tests** and **88 browser-view
combinations**. See [QA.md](docs/QA.md) and
[test-results.txt](docs/test-results.txt) for exact methods and limitations.

Optional browser regression checks use an **already installed** Chromium/Chrome
executable and synthetic engine fixtures. They do not require a running service
or live profiles. Example for Windows:

```powershell
py -3 -S tools/check_ui.py --browser 'C:\Program Files\Google\Chrome\Application\chrome.exe' --output .qa/ui-check-new
```

The output directory must be new. Defaults cover 320, 390, 768 and 1280 CSS-pixel
widths, both languages and 11 views. Screenshots and results remain local QA
artifacts. These are headless browser checks, not physical-phone or Safari/iOS
validation; the standard-library unit suite does not require a browser.

### Maintain the authoring kit and releases

After changing the bank contract or authoring instructions:

```bash
python3 tools/build_authoring_kit.py
```

The builder synchronizes the canonical validator and examples; it does not
import content into a user's database. Keep the JSON Schemas, authoring guide,
kit and tests aligned.

Release into a new directory with source, docs, schemas, the kit and independent
bank ZIPs. Refresh `SHA256SUMS.txt` for shipped file bytes, then validate banks
and run tests from an extracted copy. Exclude `data/`, private keys, cookies,
caches and generated QA artifacts. Keep generated data and QA output in their
Git-ignored directories.

Further reading: [Architecture](docs/ARCHITECTURE.md) ·
[Changelog](docs/CHANGELOG.md) · [Upgrade guide](docs/UPGRADE.md) ·
[Bank schema](schema/README.md) · [RUSH rules](docs/RUSH.md).
