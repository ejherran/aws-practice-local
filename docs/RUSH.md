# RUSH mode specification

## Goal and lifetime

A RUSH session challenges a learner to confirm N correct answers in a row before
one global deadline. The default is N=10 with 600 seconds. An administrator can
configure each bank independently: 1..min(500, bank size) consecutive answers and
1..86400 seconds. On an imported bank smaller than 10 items, the automatic goal
is capped at the bank size. Question content is the same as in quizzes/exams.

The session ends on the first of: reaching the streak goal, expiration, or the
learner choosing **End RUSH and view report**. A completed streak ends the game;
there is no additional round after success. All rounds belong to one session
and one history entry, not separate quizzes. RUSH does not affect the last-five
quiz average.

## Answering and immediate feedback

Only the current question is available. A learner may select and clear options
before confirmation; these draft choices are persisted. For multi-answer
questions, exactly the required number of options must be selected. **Confirm
answer** grades the exact set, without partial credit. A confirmed response is
immutable. There is no skip, back, flag or manual redraw operation.

A correct response increments the current streak, best streak and cumulative
correct total. The next question appears immediately. Reaching N finalizes the
session automatically. A nonblocking accessibility announcement signals a
correct answer; no overlay obscures the next question.

An incorrect response, in a single transaction:

1. Records the confirmed wrong answer.
2. Marks the old set's unused questions as discarded.
3. Generates and consumes a new complete set of N questions.
4. Resets the current streak to zero, retaining the cumulative correct total and
   best streak; increments the restart count.
5. Persists the failed question as pending feedback.

The learner immediately sees the correct answer(s) and general explanation.
An expandable section shows the selected options, why each alternative is right
or wrong, any content note and reference links. **Continue with the new set**
acknowledges the feedback and reveals the already generated first question of
the next set. Acknowledging never draws a second set or incurs another penalty.
Reloading, switching languages or using a second device preserves pending
feedback and the exact option order.

## Clock rules

The deadline is computed once on the server. An incorrect answer, a new set,
reading feedback, leaving the practice screen, closing the browser or restarting
the process does not pause, reset or extend it. An offline server cannot process
new answers; on restart, an overdue session is finalized with the original
deadline as its finish time. Do not change the host's system clock during play.

A submission received after the deadline does not count or generate a new set.
If time expires on the feedback screen, its already generated next set still
counts in the score. The final report retains the failed question and correction.
Only **confirmed** answers count; even a correct saved selection is worth zero
when time expires before confirmation.

## Score

```text
score percentage = 100 × confirmed correct answers / ALL generated questions
```

The numerator includes correct answers from all rounds, not just the final
streak. The denominator starts at N and increases by N on every wrong answer
that generates another set. It includes wrong, discarded, unanswered and
unconfirmed items. The stored percentage is rounded to two decimal places;
UI percentages use the existing one-decimal display alongside the exact counts.

| Sequence with N=10 | Correct | Generated | Score | Outcome |
|---|---:|---:|---:|---|
| Ten consecutive correct answers | 10 | 10 | 100% | Streak completed |
| Three correct, wrong, then ten correct | 13 | 20 | 65% | Streak completed |
| Wrong first, then ten correct | 10 | 20 | 50% | Streak completed |
| Wrong first in each of two rounds, then ten correct | 10 | 30 | 33.33% | Streak completed |
| Three correct, wrong, time expires while reading feedback | 3 | 20 | 15% | Not completed |
| Three correct, then time expires before any wrong answer | 3 | 10 | 30% | Not completed |

**Streak completion and percentage are different outcomes.** Completion does
not imply 100%, and the score is not an official certification score. In result
JSON, `target_percentage` and `target_met` are null for RUSH; use
`result.rush.completed` to determine whether the consecutive-answer goal was met.

## Selection and bank isolation

Quizzes, exams and RUSH share one deck per learner, bank and content version.
A generated set is consumed in full, even when its unused questions are
discarded. No repeats occur until that deck is exhausted. After exhaustion a
new shuffled cycle begins. There are never duplicates inside one set, including
sets crossing a cycle boundary. A sufficiently long RUSH session may revisit
questions in later sets once the shared cycle has been exhausted.

This generated-set interpretation means discarded questions may not have been
shown individually even though they are consumed. This is intentional: they
are part of the generated denominator and are available in the final report.

Every new set uses the content version and format captured at session creation,
not a replacement imported by an administrator during the game. Disabling a
bank prevents new sessions but does not block an existing game's new rounds.
Domain weights remain best-effort and cannot override no-repeat requirements.

## Reporting and history

The final report includes percentage and raw counts, elapsed time and finish
reason, best streak and target, number of sets and restarts, confirmed responses,
per-domain performance, and explanations for every generated question. Each
question is tagged with its set and position.

RUSH-specific outcomes distinguish `skipped` (discarded after a wrong answer),
`unconfirmed` (a saved selection not confirmed), and `unanswered` (no selection),
besides confirmed `correct` and `incorrect`. All unconfirmed items, including
skipped ones, contribute to the report's aggregate `unanswered` count; dedicated
filters distinguish them. The incorrect filter shows confirmed wrong answers,
not every generated item that failed to earn a point.

The History screen can filter by RUSH. Finished reports can be exported or
printed. The same authorization rules apply as in other modes: administrators
manage banks, but cannot use learner endpoints to read someone else's history.

## API and state-machine notes

All mutation routes require the existing session, same-origin protections and
`X-Profile-ID` binding. Revisions are integers and prevent duplicate/stale writes.

| Route | Purpose |
|---|---|
| `POST /api/attempts` | Start with `bank_id` and `kind: "rush"`. |
| `GET /api/attempts/{id}` | Resume the current question or pending feedback. |
| `POST /api/attempts/{id}/answer` | Save a draft: revision, current index, selected IDs. Never grades. |
| `POST /api/attempts/{id}/rush-answer` | Confirm the current response: revision, index, exact selected IDs. |
| `POST /api/attempts/{id}/rush-continue` | Acknowledge failure feedback: revision only. |
| `POST /api/attempts/{id}/finish` | End early: revision only. |
| `GET /api/history?kind=rush` | This learner's finished RUSH sessions. |

A wrong-answer response includes full explanations only for that confirmed
failed question. It contains no questions from the new set until acknowledgment.
The current-question phase exposes only one redacted question, with a global
index across all sets. Never use that global index as an offset into the active
API's one-item `questions` list. Complete snapshots stay server-side until the
session ends. Personal exports follow the same active-view rules.

The phases are `question`, `feedback` and `completed` (successful completion).
Timeout/manual termination is represented by `status: "finished"` and the final
report reason, even when the last active phase was `question` or `feedback`.
Use status before rendering a phase. Neither a duplicate post nor a failed
transaction can count twice or consume a second replacement set.
