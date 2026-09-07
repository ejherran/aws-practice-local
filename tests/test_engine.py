"""Scoring, timing, user isolation, shuffling and version retention tests."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
from trainer.banks import BankRepository, make_archive
from trainer.engine import Trainer, targets
from trainer.errors import AppError
from trainer.storage import Storage
from tests.helpers import ROOT, Fixture, bank_data


class EngineTests(Fixture):
    def test_default_quiz_format(self):
        a = self.engine.create(2, 'test-cert', 'quiz')
        self.assertEqual(a['total'], 5)
        self.assertEqual(a['duration'], 300)
        self.assertEqual(a['deadline'] - a['started_at'], 300)

    def test_exam_has_exact_unscored_count(self):
        a = self.engine.create(2, 'test-cert', 'exam')
        self.assertEqual(sum(not q['scored'] for q in self.snapshots(a)), 2)
        self.assertEqual(self.finish(a)['result']['scored_total'], 8)

    def test_cloud_practitioner_real_length(self):
        self.banks.import_archive((ROOT / 'banks/aws-clf-c02-4.0.0.zip').read_bytes(), 1)
        a = self.engine.create(2, 'aws-clf-c02', 'exam')
        self.assertEqual(a['total'], 65)
        self.assertEqual(a['duration'], 5400)
        r = self.finish(a)['result']
        self.assertEqual((r['scored_total'], r['unscored_total']), (50, 15))

    def test_active_response_hides_answer_key_and_unscored_items(self):
        a = self.engine.create(2, 'test-cert', 'exam')
        for q in a['questions']:
            self.assertEqual(set(q), {'index', 'prompt', 'select_count', 'selected', 'flagged', 'options'})
            for option in q['options']:
                self.assertEqual(set(option), {'id', 'text'})
                self.assertEqual(len(option['id']), 16)
        self.assertNotIn('result', a)

    def test_session_order_and_deadline_survive_reload(self):
        a = self.engine.create(2, 'test-cert', 'quiz')
        self.now[0] += 10
        reloaded = self.engine.fetch(2, a['id'])
        self.assertEqual(a['questions'], reloaded['questions'])
        self.assertEqual(a['deadline'], reloaded['deadline'])

    def test_language_change_does_not_mutate_attempt(self):
        a = self.engine.create(2, 'test-cert', 'quiz')
        self.access.edit_profile(2, 'Alice', 'es')
        b = self.engine.fetch(2, a['id'])
        self.assertEqual(a['questions'], b['questions'])
        self.assertEqual(a['deadline'], b['deadline'])

    def test_one_active_attempt_per_user(self):
        self.engine.create(2, 'test-cert', 'quiz')
        self.assertCode('active_attempt_exists', self.engine.create, 2, 'test-cert', 'exam')

    def test_other_user_can_practice_concurrently(self):
        a = self.engine.create(2, 'test-cert', 'exam')
        b = self.engine.create(3, 'test-cert', 'quiz')
        self.assertNotEqual(a['id'], b['id'])

    def test_foreign_attempt_access_denied(self):
        a = self.engine.create(2, 'test-cert', 'quiz')
        for function, args in [(self.engine.fetch, (3, a['id'])),
                               (self.engine.finish, (3, a['id'], 0)),
                               (self.engine.update, (3, a['id'], {'index': 0, 'revision': 0, 'selected': []}))]:
            self.assertCode('attempt_not_found', function, *args)

    def test_no_repeat_full_cycle(self):
        ids = []
        for _ in range(4):
            a = self.engine.create(2, 'test-cert', 'quiz')
            ids.extend(q['id'] for q in self.snapshots(a))
            self.finish(a)
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(set(ids), {q['id'] for q in self.questions})
        self.assertEqual(self.engine.dashboard(2)['banks'][0]['stats']['remaining'], 0)
        a = self.engine.create(2, 'test-cert', 'quiz')
        self.assertTrue(all(q['cycle'] == 2 for q in self.snapshots(a)))

    def test_quiz_and_exam_share_cycle(self):
        seen = set()
        for kind in ('quiz', 'exam', 'quiz'):
            a = self.engine.create(2, 'test-cert', kind)
            ids = {q['id'] for q in self.snapshots(a)}
            self.assertFalse(seen & ids)
            seen.update(ids)
            self.finish(a)
        self.assertEqual(len(seen), 20)

    def test_cycle_boundary_never_duplicates_within_attempt(self):
        for _ in range(3):
            self.finish(self.engine.create(2, 'test-cert', 'quiz'))
        a = self.engine.create(2, 'test-cert', 'exam')
        snapshots = self.snapshots(a)
        self.assertEqual(len({q['id'] for q in snapshots}), 10)
        self.assertEqual({q['cycle'] for q in snapshots}, {1, 2})
        self.assertEqual(self.engine.dashboard(2)['banks'][0]['stats']['remaining'], 15)

    def test_bank_and_user_cycles_are_independent(self):
        m, q = bank_data(bank_id='another-cert')
        self.banks.import_archive(make_archive(m, q), 1)
        self.finish(self.engine.create(2, 'test-cert', 'quiz'))
        stats = {b['id']: b['stats'] for b in self.engine.dashboard(2)['banks']}
        self.assertEqual(stats['test-cert']['remaining'], 15)
        self.assertEqual(stats['another-cert']['remaining'], 20)
        self.assertEqual(self.engine.dashboard(3)['banks'][1]['stats']['remaining'], 20)

    def test_every_option_uses_opaque_attempt_id(self):
        a = self.engine.create(2, 'test-cert', 'quiz')
        ids = [o['id'] for q in a['questions'] for o in q['options']]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all(len(v) == 16 for v in ids))

    def test_draw_order_changes_between_cycles(self):
        # Compare four full-bank orders to make a random false failure negligible.
        settings = self.settings()
        settings['exam']['question_count'] = 20
        self.configure(settings)
        orders = []
        for _ in range(4):
            a = self.engine.create(2, 'test-cert', 'exam')
            orders.append(tuple(q['id'] for q in self.snapshots(a)))
            self.finish(a)
        self.assertGreater(len(set(orders)), 1)

    def test_all_correct_is_100_percent(self):
        a = self.answer_correct(self.engine.create(2, 'test-cert', 'quiz'))
        r = self.finish(a)['result']
        self.assertEqual(r['percentage'], 100)
        self.assertEqual(r['correct'], 5)
        self.assertTrue(r['target_met'])

    def test_unscored_answers_do_not_change_scored_percentage(self):
        a = self.answer_correct(self.engine.create(2, 'test-cert', 'exam'), scored_only=True)
        r = self.finish(a)['result']
        self.assertEqual(r['percentage'], 100)
        self.assertEqual(r['all_correct'], 8)
        self.assertEqual(r['unanswered'], 2)

    def test_empty_submission_is_zero(self):
        r = self.finish(self.engine.create(2, 'test-cert', 'quiz'))['result']
        self.assertEqual((r['correct'], r['percentage'], r['unanswered']), (0, 0, 5))

    def test_multi_answer_incomplete_is_wrong(self):
        a = self.engine.create(2, 'test-cert', 'exam')
        i, q = next((i, q) for i, q in enumerate(self.snapshots(a)) if q['select_count'] == 2)
        correct = next(o['id'] for o in q['options'] if o['correct'])
        a = self.engine.update(2, a['id'], {'index': i, 'revision': 0, 'selected': [correct]})
        r = self.finish(a)
        self.assertFalse(r['questions'][i]['is_correct'])
        self.assertTrue(r['questions'][i]['incomplete'])
        self.assertEqual(r['result']['incomplete'], 1)

    def test_multiple_choice_order_irrelevant(self):
        a = self.engine.create(2, 'test-cert', 'exam')
        i, q = next((i, q) for i, q in enumerate(self.snapshots(a)) if q['select_count'] == 2)
        correct = [o['id'] for o in q['options'] if o['correct']][::-1]
        a = self.engine.update(2, a['id'], {'index': i, 'revision': 0, 'selected': correct})
        self.assertTrue(self.finish(a)['questions'][i]['is_correct'])

    def test_invalid_selections_rejected(self):
        a = self.engine.create(2, 'test-cert', 'quiz')
        for selected in [['unknown'], 'not-a-list', [123], [a['questions'][0]['options'][0]['id']] * 2]:
            self.assertCode('invalid_selection', self.engine.update, 2, a['id'], {'index': 0, 'revision': 0, 'selected': selected})

    def test_too_many_choices_rejected(self):
        a = self.engine.create(2, 'test-cert', 'quiz')
        q = a['questions'][0]
        self.assertCode('invalid_selection', self.engine.update, 2, a['id'],
                        {'index': 0, 'revision': 0, 'selected': [o['id'] for o in q['options']]})

    def test_answer_clear_and_review_flag(self):
        a = self.engine.create(2, 'test-cert', 'quiz')
        a = self.engine.update(2, a['id'], {'index': 0, 'revision': 0, 'selected': [a['questions'][0]['options'][0]['id']], 'flagged': True})
        a = self.engine.update(2, a['id'], {'index': 0, 'revision': a['revision'], 'selected': []})
        self.assertTrue(a['questions'][0]['flagged'])
        self.assertEqual(a['questions'][0]['selected'], [])

    def test_stale_revision_rejected(self):
        a = self.engine.create(2, 'test-cert', 'quiz')
        self.engine.update(2, a['id'], {'index': 0, 'revision': 0, 'flagged': True})
        self.assertCode('revision_conflict', self.engine.update, 2, a['id'], {'index': 0, 'revision': 0, 'flagged': False})

    def test_boolean_revision_is_not_integer_revision(self):
        a = self.engine.create(2, 'test-cert', 'quiz')
        self.assertCode('revision_conflict', self.engine.update, 2, a['id'], {'index': 0, 'revision': False, 'flagged': True})

    def test_deadline_finalizes_saved_answers(self):
        a = self.answer_correct(self.engine.create(2, 'test-cert', 'quiz'), how_many=2)
        self.now[0] = a['deadline']
        finished = self.engine.fetch(2, a['id'])
        self.assertEqual(finished['status'], 'finished')
        self.assertEqual(finished['result']['reason'], 'timeout')
        self.assertEqual(finished['result']['correct'], 2)
        self.assertEqual(finished['result']['elapsed_seconds'], 300)

    def test_late_answer_cannot_be_saved(self):
        a = self.engine.create(2, 'test-cert', 'quiz')
        self.now[0] = a['deadline'] + 1
        self.assertCode('attempt_finished', self.engine.update, 2, a['id'], {'index': 0, 'revision': 0, 'selected': [a['questions'][0]['options'][0]['id']]})
        self.assertEqual(self.engine.fetch(2, a['id'])['result']['correct'], 0)

    def test_restart_expires_overdue_attempt(self):
        a = self.engine.create(2, 'test-cert', 'quiz')
        self.now[0] += 1000
        storage = Storage(self.storage.path, clock=lambda: self.now[0])
        engine = Trainer(storage, BankRepository(storage))
        self.assertEqual(engine.fetch(2, a['id'])['result']['reason'], 'timeout')

    def test_finish_is_idempotent(self):
        a = self.finish(self.engine.create(2, 'test-cert', 'quiz'))
        b = self.engine.finish(2, a['id'], 0)
        self.assertEqual(a['result'], b['result'])
        self.assertEqual(a['revision'], b['revision'])

    def test_average_last_five_quizzes_only(self):
        for correct in (0, 1, 2, 3, 4, 5):
            self.finish(self.answer_correct(self.engine.create(2, 'test-cert', 'quiz'), how_many=correct))
        self.finish(self.engine.create(2, 'test-cert', 'exam'))
        stats = self.engine.dashboard(2)['banks'][0]['stats']
        self.assertEqual(stats['average'], 60)
        self.assertEqual(stats['recent_count'], 5)
        self.assertEqual(stats['completed'], 7)

    def test_average_handles_fewer_than_five(self):
        self.finish(self.answer_correct(self.engine.create(2, 'test-cert', 'quiz'), how_many=4))
        stats = self.engine.dashboard(2)['banks'][0]['stats']
        self.assertEqual(stats['average'], 80)
        self.assertEqual(stats['recent_count'], 1)
        self.assertIsNone(self.engine.dashboard(3)['banks'][0]['stats']['average'])

    def test_history_separate_users_and_modes(self):
        self.finish(self.engine.create(2, 'test-cert', 'quiz'))
        self.finish(self.engine.create(2, 'test-cert', 'exam'))
        self.finish(self.engine.create(3, 'test-cert', 'quiz'), 3)
        self.assertEqual(self.engine.history(2)['total'], 2)
        self.assertEqual(self.engine.history(2, kind='quiz')['total'], 1)
        self.assertEqual(self.engine.history(3)['total'], 1)

    def test_history_pagination(self):
        for _ in range(3):
            self.finish(self.engine.create(2, 'test-cert', 'quiz'))
        page = self.engine.history(2, offset=1, limit=1)
        self.assertEqual(page['total'], 3)
        self.assertEqual(len(page['items']), 1)

    def test_history_filter_includes_disabled_banks_on_other_pages(self):
        self.finish(self.engine.create(2, 'test-cert', 'quiz'))
        self.configure(self.settings(), False)
        page = self.engine.history(2, offset=100, limit=1)
        self.assertEqual(page['items'], [])
        self.assertEqual([bank['id'] for bank in page['banks']], ['test-cert'])
        self.assertEqual(self.engine.history(3)['banks'], [])

    def test_configuration_does_not_change_active_attempt(self):
        a = self.engine.create(2, 'test-cert', 'quiz')
        settings = self.settings()
        settings['quiz']['question_count'] = 3
        settings['quiz']['target_percentage'] = 50
        self.configure(settings)
        old = self.engine.fetch(2, a['id'])
        self.assertEqual(old['total'], 5)
        self.assertEqual(old['metadata']['target_percentage'], 80)
        self.finish(old)
        new = self.engine.create(2, 'test-cert', 'quiz')
        self.assertEqual(new['total'], 3)
        self.assertEqual(new['duration'], 180)

    def test_bank_replacement_preserves_active_and_finished_content(self):
        a = self.engine.create(2, 'test-cert', 'quiz')
        m, q = deepcopy(self.manifest), deepcopy(self.questions)
        m['version'] = '2.0.0'
        for question in q:
            question['prompt']['en'] = 'REVISED ' + question['prompt']['en']
        self.banks.import_archive(make_archive(m, q), 1, replace=True)
        current = self.engine.fetch(2, a['id'])
        self.assertEqual(current['questions'], a['questions'])
        self.assertEqual(current['bank_version'], '1.0.0')
        finished = self.finish(current)
        new = self.engine.create(2, 'test-cert', 'quiz')
        self.assertEqual(new['bank_version'], '2.0.0')
        self.assertTrue(all(q['prompt']['en'].startswith('REVISED ') for q in new['questions']))
        self.assertEqual(self.engine.fetch(2, a['id'])['questions'], finished['questions'])
        self.assertEqual(self.engine.dashboard(2)['banks'][0]['stats']['remaining'], 15)

    def test_disabled_bank_blocks_new_not_existing_attempts(self):
        a = self.engine.create(2, 'test-cert', 'quiz')
        self.configure(self.settings(), False)
        self.assertCode('bank_unavailable', self.engine.create, 3, 'test-cert', 'quiz')
        self.assertEqual(self.engine.fetch(2, a['id'])['status'], 'active')
        self.assertEqual(self.finish(a)['status'], 'finished')

    def test_no_repeat_takes_priority_over_weights(self):
        settings = self.settings()
        settings['domain_weights'] = {'d1': 100, 'd2': 0}
        self.configure(settings)
        reports = []
        for _ in range(4):
            reports.append(self.finish(self.engine.create(2, 'test-cert', 'quiz'))['result'])
        self.assertTrue(any(r['distribution_adjusted'] for r in reports))
        self.assertTrue(all(set(r['domains']) == {'d1', 'd2'} for r in reports))

    def test_profile_export_has_no_credentials_or_foreign_data(self):
        self.finish(self.engine.create(3, 'test-cert', 'quiz'), 3)
        a = self.engine.create(2, 'test-cert', 'quiz')
        export = self.engine.export_profile(2)
        serialized = json.dumps(export)
        for forbidden in ('password_hash', 'password_salt', 'token_hash', 'bob', 'is_correct'):
            self.assertNotIn(forbidden, serialized)
        self.assertEqual(len(export['attempts']), 1)
        self.assertEqual(export['attempts'][0]['id'], a['id'])
        self.assertNotIn('correct', export['attempts'][0]['questions'][0]['options'][0])

    def test_concurrent_stale_updates_only_one_wins(self):
        a = self.engine.create(2, 'test-cert', 'quiz')
        def update(flag):
            try:
                self.engine.update(2, a['id'], {'index': 0, 'revision': 0, 'flagged': flag})
                return 'ok'
            except AppError as error:
                return error.code
        with ThreadPoolExecutor(max_workers=2) as pool:
            result = list(pool.map(update, [True, False]))
        self.assertEqual(sorted(result), ['ok', 'revision_conflict'])

    def test_largest_remainder_preserves_total(self):
        weights = {'1': 24, '2': 30, '3': 34, '4': 12}
        self.assertEqual(sum(targets(65, weights).values()), 65)
        self.assertEqual(sum(targets(50, weights).values()), 50)
        self.assertEqual(targets(50, weights), {'1': 12, '2': 15, '3': 17, '4': 6})
