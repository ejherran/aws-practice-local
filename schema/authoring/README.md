# Question bank authoring kit

Create portable question banks for AWS Practice Local 3.x. All tooling uses
Python 3.10+ and its standard library. Internet access and API keys are not
required to build or validate a bank. Researching accurate questions is a
separate authoring responsibility.

**This toolkit ZIP is not itself importable.** `example-bank.zip` is a working,
four-question bilingual example. A real bank is a ZIP containing exactly
`manifest.json` and `questions.json` at its root, with no other entries.

## Build your first bank

1. Copy the `example` folder to a new working folder.
2. Edit both JSON files. Replace the example title, description, exam code,
   bank ID, domains, references, formats and questions with your own content.
3. Keep every textual field translated into each declared language.
4. Build and validate the archive with the included scripts:

```bash
python build_bank.py my-bank my-certification-1.0.0.zip
python validate_bank.py my-certification-1.0.0.zip
```

On Windows, `py -3` can replace `python`; on macOS/Linux, use `python3` when
needed. The builder adds only the two required JSON files, avoiding hidden
operating-system files that would cause rejection.

Sign in as an administrator, open **Administration**, select the ZIP,
**Validate ZIP**, review the preview, then **Import bank**. Validation checks
structure, not subject-matter accuracy or psychometric quality.

## Manifest fields

| Field | Meaning |
|---|---|
| `schema_version` | Use integer `2` for new banks. Version `1` remains importable without RUSH defaults. |
| `bank_id` | Permanent lowercase identity, e.g. `aws-saa-c03`. Two to 64 characters; letters, numbers and hyphens; starts with a letter or number. |
| `version` | Unique numeric triplet, e.g. `1.0.0` or `1.1.0`. Increment it whenever content changes. A version already imported cannot be overwritten. |
| `exam_code` | Display code; never interpreted as engine logic. |
| `title`, `description` | Objects containing localized text. |
| `languages` | `['en']`, `['es']` or both language codes. Use JSON double quotes. |
| `default_language` | One of the declared languages. |
| `domains` | One to 30 objects containing `id` and localized `name`. Each domain must have at least one question. |
| `defaults` | Quiz format, exam format, optional RUSH format and domain weights. |
| `references` | Map of source IDs to localized `title` and HTTPS `url`. An empty map is allowed, but well-supported questions are strongly recommended. |
| `content_updated_at` | Optional ISO date indicating the content review date. Do not claim a review that did not occur. |

No unknown fields are accepted. Reference URLs are displayed as optional links
in completed reports; the app does not fetch them. Only include sources you
actually checked. A source URL may be shared by both language versions.

## Format settings

Both `quiz` and `exam` contain:

```json
{
  "question_count": 10,
  "duration_seconds": 831,
  "unscored_count": 0,
  "time_mode": "proportional",
  "target_percentage": 80
}
```

The exam must use `"fixed"` timing. The quiz can use `"fixed"` or
`"proportional"`. For proportional quizzes, the importer calculates:

```text
quiz seconds = floor(exam seconds × quiz question count / exam question count + 0.5)
```

A valid integer `duration_seconds` must still be supplied in the JSON; it is
normalized on import. Question counts must be between 1 and the smaller of 500
and the bank size. Durations are between 1 and 86,400 seconds. The unscored count
is between zero and one less than the mode's question count.

`target_percentage` is an optional-to-the-learner practice goal but a required
integer field from 0 to 100. It is **not an official certification pass mark**.
Never transform official scaled scores into a supposed percentage threshold.

`domain_weights` maps every declared domain ID to an integer percentage. Values
must sum to 100, including zero-weight domains. Quotas use largest-remainder
rounding. Selection prioritizes the no-repeat cycle over exact weights when
the remaining pool cannot meet both; reports identify adjusted distributions.
A zero weight does not permanently exclude a domain from the no-repeat pool.

## Question fields

`questions.json` is an array, not an object with a wrapper property. Each entry
contains:

- `id`: unique stable identifier, such as `Q001`.
- `domain_id`: one of the manifest domain IDs.
- `task_id`: optional objective label, not interpreted by the engine.
- `select_count`: exact number of correct choices required.
- `prompt`, `explanation`: localized text objects.
- `options`: two to ten options. Each has `id`, localized `text`, localized
  `explanation`, and a Boolean `correct` value.
- `references`: array of existing keys from the manifest's reference map.
- `notes`: optional localized currency or scope note.

An example localized field is:

```json
{"en": "Which service meets this requirement?", "es": "¿Qué servicio cumple este requisito?"}
```

Every localized field must contain **exactly the languages declared in the
manifest**. This applies to prompts, general explanations, every option,
option explanations, titles, domain names, reference titles and optional notes.
Do not include empty translations or place English placeholder text in Spanish
fields. The importer checks completeness, not the correctness of translation.

Correct choices must total exactly `select_count`, with at least one incorrect
choice. Answers are graded as exact sets; there is no partial credit. Use stable
option IDs in authoring files, but never refer to option letters, positions or
IDs in displayed prose: the app shuffles the order and assigns private runtime
IDs. Avoid "all of the above," "both A and B," and other position-dependent
choices. Duplicate prompts (ignoring case/whitespace) or duplicate option texts
within one question are rejected.

## Language behavior

The UI always supports English and Spanish. A bilingual bank changes questions
and explanations immediately with the UI language, preserving time and answer
order. A monolingual bank is accepted and displays an explicit fallback notice
when the selected UI language is unavailable. The app never silently translates
missing content and does not call translation services.

## Versions and independent content

A different certification needs a different `bank_id`. A content revision uses
the same ID and a new `version`. Keep question IDs stable when the underlying
question is the same, but preserve the truth of revised answers and sources.

Importing a new version requires explicit confirmation, makes it current and
loads its defaults for future attempts. It starts a new no-repeat cycle for that
version. Previously completed reports and active attempts retain complete
immutable snapshots of the old content and settings. Version strings identify
immutable releases; the app does not enforce numeric version ordering.

Exporting an installed bank includes its current administrator format settings.
To edit and reimport it into the same installation, increment the version.
Changing a format in the admin panel alone does not require a content version.

## Limits and validation

Maximums: 10 MiB compressed ZIP, 40 MiB expanded, 5,000 questions, 1,000 reference
entries, 20 references per question. Only stored or DEFLATE ZIP entries are
accepted. Encrypted archives, symlinks, extra entries, suspicious compression
ratios, invalid UTF-8, duplicate JSON keys, non-finite numbers, unknown fields,
missing translations and inconsistent answer counts are rejected.

The two JSON Schema files document structural limits. The included Python
validator additionally checks semantic and cross-file constraints. It is the
same validation implementation shipped with this application release. Do not
weaken it just to make a malformed bank import successfully.

The schema supports single-answer and multiple-answer questions, not every
possible delivery format of every certification. Research each certification's
current exam format before setting its defaults. Do not call original practice
questions "official questions," and do not include exam dumps or paid material
without permission.

Read `AGENTS.md` for the editorial checklist. A mechanically valid archive still
needs substantive review for ambiguity, current facts and plausible distractors.

## RUSH format — schema version 2

New banks should use `"schema_version": 2`. Under `defaults`, an optional RUSH
object configures a consecutive-answer challenge:

```json
"rush": {
  "question_count": 10,
  "duration_seconds": 600
}
```

Use an integer goal between 1 and min(500, bank size), and an integer global
limit between 1 and 86400 seconds. Omission defaults to min(10, bank size) and
600 seconds. A wrong answer generates another complete set and immediate
feedback; the timer keeps running. The numerator is every confirmed correct
answer, the denominator every generated question, including discarded or
unanswered items. The goal is a consecutive streak, not a score threshold.
No `unscored_count`, `time_mode` or `target_percentage` belongs in this object.
RUSH configuration is independent of official exam timings. The administrator
can change it without editing questions or resetting the deck.

The app accepts legacy schema-v1 banks without changes, but the v1 contract
cannot contain `defaults.rush`. Exports use schema v2 and require app version 4
or later. Content IDs/versions and the question-file contract remain unchanged.
