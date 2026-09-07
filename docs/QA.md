# Version 4 release validation

## Automated regression suite

The delivered source passed **216 tests** using Python 3.13.5 on Linux, including
64 added RUSH/upgrade/contract checks. The complete suite runs with Python site
packages disabled:

```bash
python3 -S -m unittest discover -s tests -v
```

Tests use only the standard library and temporary databases. They cover all
previous authentication, bank validation, timing, scoring, ownership, locale
parity, archive validation and authoring-kit checks, plus:

- Default 10-question/600-second RUSH configuration and bank-size-aware defaults.
- Exact-set confirmation, draft persistence without grading, immutable answered
  items, no skipping/flags and current-question-only responses.
- Automatic advancement and completion, immediate bilingual failed-answer
  explanations, full-set regeneration and persistent feedback acknowledgment.
- Correct/generated scoring including 13/20=65%, discarded items, multiple
  restarts, separate success state, per-domain counts and complete reports.
- Global deadlines, timeout during feedback, rejection of late submissions,
  process restart recovery and no timer reset on wrong answers or acknowledgment.
- Duplicate/stale/concurrent submissions, failed-draw transaction rollback,
  question cycles across modes/rounds, and unique questions within each set.
- Bank version/configuration snapshots, disabled-bank continuation, per-user
  isolation, admin access boundaries, history filters and unchanged quiz means.
- Live HTTP confirmation/continuation routes, authentication, expected-profile
  and same-origin enforcement, safe personal exports and admin configuration.
- Contract v2 defaults and exports, unchanged v1 import support, rejected mixed
  contracts, portable authoring-kit synchronization, and v3 storage upgrades.

Python compilation and JavaScript syntax checks passed. Both the current
310-question bilingual starter ZIP and the four-question contract-v2 example
validate with `python3 -S app.py --validate-bank ...`.

`test-results.txt` records the final suite output. The release is also extracted
into a separate directory and the standard-library suite rerun from that copy
before delivery. No test database, user cookie, generated cache or browser test
dependency is included in the release.

## Browser rendering and interaction

Native Chromium rendered the real HTML/CSS/JavaScript at desktop and mobile
widths. Question layout was checked at 320, 360, 390, 768 and 1440 CSS pixels.
A narrow-navigation overflow was found and corrected. Checked flows include:

- Admin sign-in, default RUSH card, and editing RUSH settings in the admin form.
- Starting a game, single/multiple selection, confirming a correct answer,
  failing the next one and seeing its correct answer and explanation immediately.
- Switching EN/ES while feedback is pending without changing deadline or state.
- Loading a fresh browser document and resuming the same pending correction.
- A completed three-answer test streak after a restart: 4/6 = 66.67%.
- Full generated-question review, wrong/discarded filters and RUSH history.
- Standard ten-question quiz completion and all per-option report explanations.
- A four-second wall-clock game that auto-finalizes while feedback is displayed.

No uncaught JavaScript exceptions occurred in these flows. Correct-answer
announcements are nonblocking and no longer overlay the next question or a
subsequent failure correction. The failed-answer explanation was visually
inspected in the narrow Spanish view; the question view was inspected in English.

### Browser environment limitation

The managed Chromium environment blocks direct URL navigation, including local
HTTP URLs. This policy was not changed. HTML, CSS and JavaScript were loaded
into an `about:blank` document, and a development-only fetch bridge forwarded
requests through Python's standard HTTP client to the actual local server.
The client used a cookie jar; the local favicon was supplied inline.

These checks exercise the real DOM, JavaScript and live application endpoints,
not unrestricted browser networking or a physical phone. HTTP headers, cookies,
origin validation and route permissions are also checked directly by the live
HTTP regression suite. Playwright/Chromium/Node were development-time tools,
not runtime or shipped-test requirements. No dependency is installed at startup.

## Real v3 upgrade rehearsal

The original v3 release was extracted into a temporary folder and run with its
own code. It created the initial admin, two test learners, a completed quiz and
an active exam. V4 then opened that actual v3 database. Checks confirmed that:

- Existing learner credentials still authenticated and Admin was not recreated.
- The completed quiz retained identical questions, responses and result data.
- The active exam retained identical question/option order and deadline.
- The quiz average and remaining-question cycle were unchanged.
- RUSH became available with 10/600 defaults without reimporting the bank.
- Its first set did not repeat the prior quiz's questions.
- The storage marker advanced to 4.

This rehearsal used synthetic profiles, not the user's installation. Make the
stopped-server backup described in `UPGRADE.md` before upgrading real progress.

## Remaining limits

Physical phones, iOS Safari, Android hardware, Windows/macOS installations,
Wi-Fi/router/firewall configurations and trusted HTTPS certificates were not
tested here. This is not a cross-browser certification, load test for many
simultaneous learners, public-hosting security audit or independent penetration
test. The default connection remains HTTP on a trusted LAN.

RUSH snapshots are retained in the local database to explain every generated
question. Very large banks, unusually large goals, very long limits or many
restarts can increase database size and report-rendering cost; no high-volume
stress benchmark is claimed.

The 310-question bilingual bank reports a September 6, 2026 research cut-off,
50 new items and 12 targeted revisions from content version 3.0.0. Repository
validation establishes structure and answer consistency; it does not constitute
an independent factual review, psychometric calibration or official difficulty
assessment. The application remains independent practice software, not an
official exam system.
