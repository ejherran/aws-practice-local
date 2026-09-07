# Instructions for question bank authors and AI agents

## Deliverable

Produce an importable ZIP with exactly `manifest.json` and `questions.json` at
the archive root. Use the contract version and validator included in this kit.
All JSON field names, identifiers, source-code comments and authoring documents
must be English. Actual Spanish question content belongs in `es` fields.

Use a new `bank_id` for a different certification, and a new numeric `version`
for a revised release of the same bank. Do not overwrite an existing version.
Do not copy the illustrative example's defaults into an unrelated exam without
checking that exam's official format and current objectives.

## Research and factual accuracy

Use the official certification guide and primary service documentation. Verify
current names, scope, service availability and pricing/support conditions when
relevant. Distinguish exam terminology from changed commercial names with a
precise, localized note. Do not invent citations, dates of review or official
exam access. Produce original practice material, never leaked exam questions.
Include references that genuinely support the answer and explanation.

## Editorial quality

Each prompt must be understandable without reading its options. State the
workload, explicit requirement and decision to make. Do not require readers to
infer what the question is asking from the answer choices. For multiple-answer
questions, state the exact number to select in both languages, and make each
choice independently assessable under the stated requirement.

Use plausible distractors based on nearby services or common conceptual
confusions. Avoid absurd choices, grammatical clues, repeated correct-answer
wording, conspicuously longer correct answers and unsupported absolutes. Ensure
there is exactly the stated number of defensible correct choices. Explain both
why each correct choice satisfies the requirement and why every distractor
fails that particular requirement, including when it might fit another case.

Do not mention answer letters or their positions: the application shuffles
options. Avoid "all/none of the above" and combinations such as "A and C".
Vary scenarios and reasoning patterns instead of creating superficial duplicate
questions that merely substitute service names.

## Bilingual equivalence

English and Spanish versions must test the same decision. Translate the prompt,
all options, all option explanations, overall explanation and any notes. Keep
proper service names consistent. Do not introduce a qualifier, hint or exception
in only one language. Use natural standalone wording, not a literal translation
that forces readers to guess the intent. Every declared language must be present
in every localized field, including reference titles and domain names.

## Validation and review

Run `python build_bank.py DIRECTORY OUTPUT.zip` and
`python validate_bank.py OUTPUT.zip`. Review domain coverage, declared weights,
format counts, unique IDs, choice counts and translation completeness. Import
into a test installation and read a quiz and completed report in both languages.

Machine validation does not prove correct subject matter, good distractors,
equivalent difficulty or official exam calibration. Report these limits honestly.
`target_percentage` is a practice target, not an official scaled pass mark.

## RUSH and version compatibility

Use schema version 2 for new banks and optional `defaults.rush` with exactly
`question_count` and `duration_seconds`. Respect bank-size limits. RUSH is a
training game, not a statement about official exam rules. Do not add answer
hints or positional wording specifically for RUSH: the same questions are used
by all modes. Legacy v1 banks remain readable if this new field is omitted.
Validate exports with the bundled updated validator rather than an older v1 kit.
