# Question bank contracts, versions 1 and 2

This folder contains the two JSON Schema documents and the downloadable
`question-bank-authoring-kit.zip`. The ZIP is a **toolkit, not an importable
question bank**. Unpack it and follow its README. Its `example-bank.zip` is
importable and demonstrates a complete four-question bilingual bank.

A bank ZIP contains **exactly** `manifest.json` and `questions.json` at its root.
Do not add a parent folder, schema files, images, `.DS_Store`, or `__MACOSX` files.
ZIP entries are read in memory, never extracted to the server filesystem.

JSON Schema expresses structural constraints. `trainer/banks.py` is the
canonical standard-library validator for cross-file and semantic constraints:
translations, unique identifiers and prompts, correct-answer counts, domain
membership, referenced sources, available bank size, weights and format limits.
Passing a JSON Schema checker alone does not guarantee import acceptance.

Application administrators can download the current bank, change its files,
increment its version and upload it as a replacement. Configuration changes
apply only to new attempts. An imported version cannot be overwritten.

## RUSH defaults (contract v2, engine 4+)

Set `schema_version` to `2` when adding `defaults.rush`:

```json
"rush": {"question_count": 10, "duration_seconds": 600}
```

The goal is 1..min(500, bank size); time is 1..86400 integer seconds. The clock
covers every set and feedback screen. This object has no unscored questions,
proportional timing or percentage target. Omission uses min(10, bank size) and
600 seconds. The v1 contract remains supported but cannot declare this new
field. Exports use v2. Question content fields did not change. Both schemas,
editable examples and the validator inside the kit are synchronized.
