# Version 4 release validation

## Automated regression suite

The delivered source passed **245 tests** using Python 3.12.2 on Windows.
The complete suite runs with Python site packages disabled:

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
- Live HTTPS confirmation/continuation routes, authentication, expected-profile
  and same-origin enforcement, safe personal exports and admin configuration.
- Contract v2 defaults and exports, unchanged v1 import support, rejected mixed
  contracts, portable authoring-kit synchronization, and v3 storage upgrades.
- Generated TLS identity reuse, SAN names, independent private keys, validity
  checks, incomplete/custom pairs, fail-closed startup and preserved passwords.
- Real certificate-verified HTTPS requests, rejected plaintext connections,
  stalled-handshake isolation, secure cookies and static-file protection.
- Inactivity at exactly 3600 seconds, passive polling, explicit activity,
  separate cookies, profile/origin binding, restart persistence, conservative
  migration and the unchanged maximum absolute session lifetime.
- Isolated UI fixture generation, public-profile field allowlists, hidden
  active answer keys, immutable saved snapshots and inert embedded JSON.

Python compilation and JavaScript syntax checks passed. Both bilingual starter
ZIPs (310 Cloud Practitioner questions and 300 AI Practitioner questions) and
the four-question contract-v2 example validate with
`python3 -S app.py --validate-bank ...`.

`test-results.txt` records the final automated validation summary. The release is also extracted
into a separate directory and the standard-library suite rerun from that copy
before delivery. No test database, user cookie, generated cache or browser test
dependency is included in the release.

## Browser rendering and interaction

### Current responsive UI refinement

The optional `tools/check_ui.py` runner uses only Python's standard library and
an already installed Chromium/Chrome executable. It creates temporary synthetic
engine records and supplies their public response shapes to the actual native
HTML/CSS/JavaScript through a fixture fetch adapter. It neither reads `data/` nor
uses a running service, credentials, cookies or third-party Python modules.
The normal `unittest` suite does not require a browser.

```powershell
python -S tools/check_ui.py --browser 'C:\Program Files\Google\Chrome\Application\chrome.exe' --output .qa/ui-check-new
```

The output directory must be new. The runner writes local fixture HTML,
screenshots and a machine-readable results file there. These generated files
are QA artifacts, not release content. `--widths` and `--views` can select a
smaller subset for iteration.

All 88 combinations passed: 320, 390, 768 and 1280 CSS-pixel widths, both locales,
and catalog, expanded bank menu, login, quiz question, RUSH question, report,
history, admin import, expanded bank settings, profile and session-expiry views.
Exact-width same-origin iframes avoid Windows Chrome's minimum outer window
width. Each viewport is 1100 CSS pixels high. These are headless Chrome tests,
not physical-device, Safari/iOS, soft-keyboard or live network end-to-end tests.

The runner checks 26 banks, search by code and accent-insensitive bilingual
title, search clearing and focus, per-profile selection, unavailable-bank
fallback, mobile collapse, one selected detail panel and language persistence.
It also verifies saved answers and scroll/focus after successful saves,
server-confirmed selections after simulated network failures, scroll and focus
on question navigation, at least 44px question-map targets, session-expiry
cleanup and stale-response isolation. No tested view had horizontal document
overflow or a JavaScript runtime error. Screenshots were inspected, including
narrow settings forms and the tablet practice panel.

### Previous bank navigation and HTTPS update

The browser connector was unavailable. Installed headless Chrome rendered the
real HTML/CSS/JavaScript using synthetic API response fixtures collected from a
separate local HTTPS server with a temporary database. It contained 26 banks
(the two starter banks plus 24 clearly labeled QA banks) and synthetic profiles.
The fixture collector verified the server's generated public certificate.

Checks covered login, bank catalog, question view, report, history and expanded
administrator settings in both English and Spanish. Desktop viewport width was
1264 CSS pixels. Windows Chrome enforces a minimum outer window width, so
same-origin iframe documents provided exact 320px and 390px viewports for narrow
checks. These are browser rendering tests, not physical-phone tests.

DOM assertions verified one selected bank panel, all 26 menu items, searching by
code and accent-insensitive bilingual title, no-result behavior, selected-bank
focus, automatic mobile collapse, per-profile saved selection, language changes,
rerender persistence and fallback when a bank becomes unavailable. The tested
views had no horizontal document overflow. Screenshots of the desktop and narrow
bank menu and panel were inspected. JavaScript syntax validation also passed.
Additional DOM checks confirmed that expiry clears private UI state, closes an
open dialog and returns to sign-in, and that an old pending response cannot
sign out a newly authenticated profile.

The isolated renderer uses response fixtures, not live browser authentication or
browser TLS trust installation. Live transport, cookie, ownership and timeout
behavior is tested separately with Python's certificate-verifying HTTPS client.
No browser package, fixture, temporary profile or private key ships in the release.

### Earlier RUSH browser rehearsal

The following records the previous release's browser checks, not new testing of
those interactions in the current Windows environment.

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

### Earlier browser environment limitation

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

Physical phones, iOS Safari, Android hardware, macOS/Linux certificate generation,
Wi-Fi/router/firewall configurations and device-wide certificate trust installation
were not tested in this update. Windows CPython certificate generation and
verification by a Python HTTPS client were tested. This is not a cross-browser
certification, many-user load test or independent penetration test. All server
connections now require HTTPS on a trusted LAN.

RUSH snapshots are retained in the local database to explain every generated
question. Very large banks, unusually large goals, very long limits or many
restarts can increase database size and report-rendering cost; no high-volume
stress benchmark is claimed.

The 310-question Cloud Practitioner bank reports a September 6, 2026 research
cut-off, 50 new items and 12 targeted revisions from content version 3.0.0. The
300-question AI Practitioner bank reports a September 7, 2026 review date and
50 additions over its prior version. Repository validation establishes
structure and answer consistency; it does not constitute an independent factual
review, psychometric calibration or official difficulty assessment. The
application remains independent practice software, not an official exam system.
