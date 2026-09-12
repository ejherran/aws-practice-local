# Version 4.0.0 — RUSH

## Responsive UI refinement

- Made each practice mode a full-card action with local inline icons, concise
  settings and a clear start label; moved progress below the practice choices.
- Added compact labeled phone navigation, an accessible sign-out icon, a
  shorter sticky exam header and 44px question-map targets.
- Improved tablet layout, mobile input sizing, stacked history filters,
  wrapping report badges and the bank search empty state.
- Preserved scroll position and focus after successful or failed answer saves;
  selecting a bank keeps the mobile bank selector in view.
- Added an optional standard-library headless browser runner with synthetic
  fixtures, bilingual responsive checks and isolated fixture regression tests.

## Bank navigation and local security

- Replaced the growing card grid with a searchable bank menu and one selected
  bank panel, preserving the existing visual style and practice controls.
  Mobile uses a collapsible menu; selection is remembered per browser/profile.
- Made HTTPS mandatory and added first-start local self-signed certificate
  generation with the OpenSSL library already used by Python. Identity reuse,
  private-key permissions, TLS 1.2 minimum and secure cookies are enforced.
- Added server-side one-hour inactivity expiry. Explicit UI interaction renews
  only the current cookie; polling cannot renew authentication. Existing
  profiles and practice records are preserved and attempt clocks keep running.

## AI Practitioner starter bank

- Added the independent `aws-aif-c01` content version 1.1.0 starter bank with
  300 original bilingual questions covering all 14 task statements and the five
  AIF-C01 domains in the declared 20/24/28/14/14 proportions.
- Included 240 single-answer, 54 two-answer and six three-answer questions, with
  bilingual rationales for every option and primary-source references for every
  question.
- Supplied 65-question / 90-minute exam defaults with 15 unscored questions,
  proportional ten-question quizzes and a ten-answer / 600-second RUSH default.
  The 80% target is a practice goal, not the official scaled passing score.

## Cloud Practitioner content update

- Updated the bundled `aws-clf-c02` starter bank from content version 3.0.0 to
  4.0.0, with 310 bilingual questions: 50 new items and 12 targeted revisions.
- Updated the bank contract to schema v2 with explicit RUSH defaults while
  preserving the 65-question exam, 15 unscored items and proportional quiz
  timing defaults.
- Preserved the 260 existing question IDs and added Q261 through Q310. The bank
  reports a September 6, 2026 research cut-off and references official AWS
  resources; automated validation is not an independent subject-matter or
  psychometric review.

- Added sequential consecutive-answer challenges, default 10 answers / 600 seconds.
- Added explicit confirmation, immediate failed-answer correction, automatic
  full-set regeneration, persistent feedback, and a single authoritative clock.
- Added generated-question scoring, separate streak completion, round-aware
  reports, RUSH history filtering and shared per-user/bank/version decks.
- Added per-bank administrator RUSH settings and bank contract v2 exports;
  unchanged v1 banks remain supported. Rebuilt the portable authoring kit.
- Preserved bilingual UI/content, user isolation, quiz/exam behavior, last-five
  quiz averages, offline standard-library runtime and versioned content.
- Added stopped-server v3 upgrade support and storage marker 4.
- Corrected narrow admin navigation wrapping and removed success overlays from
  RUSH question/feedback screens. Success uses a nonblocking live announcement.

## Earlier releases

# Release notes

## 3.0.0

- Added complete English/Spanish UI localization and local bilingual content for
  all 260 Cloud Practitioner questions and all 1,093 option explanations.
- Replaced the single embedded bank with an independent versioned JSON-in-ZIP
  contract, multi-bank catalog, per-bank settings and per-user/per-bank decks.
- Added the initial central `Admin` account, role-protected bank validation,
  import, format configuration, enable/disable, ZIP export and audit history.
- Added a downloadable schema/authoring kit with JSON Schemas, editable bilingual
  examples, an importable example ZIP and standard-library builder/validator.
- Added immutable bilingual attempt snapshots so updates do not rewrite reports
  or change active exams. New content versions start independent cycles.
- Preserved timing, exact-set grading, hidden unscored questions, reports, result
  export, history and per-bank last-five quiz averages.
- Improved narrow-screen navigation and restored top-of-question positioning
  after moving to a new question. Save failures retain an explicit warning.
- Added English maintainer and authoring instructions, architecture and QA docs.
- Uses a new version 3 local database. No version 1/2 migration is included.

Only the Cloud Practitioner bank is complete study content in this release.
Other certifications can be imported without engine changes; their banks are
not automatically downloaded or generated by the application.
