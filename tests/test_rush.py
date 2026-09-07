"""RUSH state transitions, exact scoring, clocks, isolation and bank contracts."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
from unittest.mock import patch
from trainer.banks import make_archive, read_archive, validate_settings
from trainer.engine import Trainer
from trainer.errors import AppError
from trainer.storage import Storage
from tests.helpers import Fixture, bank_data


class RushTests(Fixture):
    def create(self, goal=None, seconds=600, user=2):
        if goal is not None:
            settings = self.settings()
            settings['rush'] = {'question_count': goal, 'duration_seconds': seconds}
            self.configure(settings)
        return self.engine.create(user, 'test-cert', 'rush')

    def commit(self, a, correct=True, user=2):
        q = self.snapshots(a)[a['rush']['index']]
        selected = [o['id'] for o in q['options'] if o['correct']]
        if not correct:
            selected[-1] = next(o['id'] for o in q['options'] if not o['correct'])
        return self.engine.rush_action(user, a['id'], {'revision': a['revision'],
                                      'index': a['rush']['index'], 'selected': selected})

    def continue_round(self, a):
        return self.engine.rush_action(2, a['id'], {'revision': a['revision']}, 'continue')

    def win(self, a):
        while a['status'] == 'active':
            a = self.commit(a)
        return a

    def test_defaults_ten_questions_ten_minutes(self):
        a = self.create()
        self.assertEqual((a['total'], a['duration'], a['rush']['goal']), (10, 600, 10))
        self.assertEqual(a['deadline'] - a['started_at'], 600)
        self.assertEqual(a['rush']['percentage'], 0)

    def test_only_current_question_is_visible(self):
        a = self.create()
        self.assertEqual(len(a['questions']), 1)
        q = a['questions'][0]
        self.assertEqual(set(q), {'index','prompt','select_count','selected','flagged','options'})
        self.assertNotIn('feedback', a)
        for o in q['options']:
            self.assertEqual(set(o), {'id','text'})
        self.assertNotIn('result', a)

    def test_correct_answer_advances_automatically(self):
        a = self.create()
        b = self.commit(a)
        self.assertEqual((b['rush']['streak'], b['rush']['correct_count'], b['rush']['index']), (1,1,1))
        self.assertEqual(b['questions'][0]['index'], 1)
        self.assertEqual(b['rush']['percentage'], 10)
        self.assertEqual(a['deadline'], b['deadline'])
        self.assertNotIn('feedback', b)

    def test_goal_completed_finishes_immediately(self):
        a = self.win(self.create())
        r = a['result']
        self.assertEqual(r['reason'], 'rush_completed')
        self.assertEqual((r['correct'], r['scored_total'], r['percentage']), (10,10,100))
        self.assertTrue(r['rush']['completed'])
        self.assertIsNone(r['target_met'])
        self.assertEqual(r['rush']['best_streak'], 10)

    def test_wrong_answer_returns_immediate_full_feedback(self):
        a = self.create()
        original = self.snapshots(a)[0]
        b = self.commit(a, False)
        self.assertEqual(b['rush']['phase'], 'feedback')
        self.assertEqual(b['feedback']['id'], original['id'])
        self.assertEqual(b['feedback']['explanation'], original['explanation'])
        self.assertEqual(b['feedback']['options'], original['options'])
        self.assertFalse(b['feedback']['is_correct'])
        self.assertTrue(b['feedback']['confirmed'])
        self.assertEqual(b['questions'], [])

    def test_new_set_is_generated_before_feedback_acknowledgment(self):
        a = self.commit(self.create(), False)
        self.assertEqual((a['total'], a['rush']['round_number'], a['rush']['index']), (20,2,10))
        self.assertEqual(self.engine.dashboard(2)['banks'][0]['stats']['remaining'], 0)
        self.assertEqual(sum(q['skipped'] for q in self.snapshots(a)), 9)

    def test_wrong_answer_resets_streak_not_cumulative_correct_or_clock(self):
        a = self.create()
        deadline = a['deadline']
        for _ in range(3):
            a = self.commit(a)
        self.now[0] += 37
        a = self.commit(a, False)
        self.assertEqual((a['rush']['streak'], a['rush']['correct_count'], a['rush']['best_streak']), (0,3,3))
        self.assertEqual(a['rush']['percentage'], 15)
        self.assertEqual(a['deadline'], deadline)

    def test_requested_score_formula_after_restart_and_success(self):
        a = self.create()
        for _ in range(3):
            a = self.commit(a)
        a = self.commit(a, False)
        a = self.win(self.continue_round(a))
        r = a['result']
        self.assertEqual((r['correct'], r['total'], r['scored_total'], r['percentage']), (13,20,20,65))
        self.assertEqual(r['rush']['failures'], 1)
        self.assertEqual(r['rush']['rounds'], 2)
        self.assertEqual(r['rush']['skipped'], 6)
        self.assertEqual(r['rush']['confirmed'], 14)
        self.assertTrue(r['rush']['completed'])
        self.assertIsNone(r['target_met'])

    def test_every_failed_set_counts_even_if_no_answers_were_correct(self):
        a = self.create()
        for _ in range(2):
            a = self.continue_round(self.commit(a, False))
        a = self.win(a)
        self.assertEqual((a['result']['correct'],a['result']['scored_total']), (10,30))
        self.assertEqual(a['result']['percentage'], 33.33)

    def test_failure_on_last_question_still_resets(self):
        a = self.create(goal=3)
        a = self.commit(self.commit(a))
        a = self.commit(a,False)
        self.assertEqual(a['rush']['best_streak'], 2)
        self.assertEqual(a['rush']['streak'], 0)
        self.assertEqual(sum(q['skipped'] for q in self.snapshots(a)),0)
        self.assertEqual(a['total'],6)

    def test_continue_does_not_generate_or_consume_more_questions(self):
        a = self.commit(self.create(), False)
        snapshots = self.snapshots(a)
        deck = self.engine.dashboard(2)['banks'][0]['stats']
        b = self.continue_round(a)
        self.assertEqual(snapshots,self.snapshots(b))
        self.assertEqual(deck,self.engine.dashboard(2)['banks'][0]['stats'])
        self.assertEqual(b['rush']['phase'], 'question')
        self.assertNotIn('feedback',b)
        self.assertEqual(b['questions'][0]['index'], 10)

    def test_feedback_survives_reload_restart_and_language_change(self):
        a = self.commit(self.create(), False)
        self.now[0] += 20
        self.access.edit_profile(2,'Alice','es')
        engine = Trainer(self.storage, self.banks)
        b = engine.fetch(2,a['id'])
        self.assertEqual(a['feedback'],b['feedback'])
        self.assertEqual(a['deadline'],b['deadline'])
        self.assertEqual(a['rush'],b['rush'])

    def test_clock_expires_during_feedback(self):
        a = self.commit(self.create(), False)
        self.now[0] = a['deadline']
        b = self.engine.fetch(2,a['id'])
        self.assertEqual(b['status'],'finished')
        self.assertEqual(b['result']['reason'],'timeout')
        self.assertEqual(b['result']['scored_total'],20)
        self.assertEqual(b['result']['elapsed_seconds'],600)
        self.assertFalse(b['result']['rush']['completed'])
        self.assertEqual(b['questions'][0]['outcome'],'incorrect')

    def test_late_correct_answer_never_counts(self):
        a = self.create()
        self.now[0] = a['deadline']
        b = self.commit(a)
        self.assertEqual(b['result']['correct'],0)
        self.assertEqual(b['result']['reason'],'timeout')

    def test_late_incorrect_answer_does_not_generate_extra_set(self):
        a = self.create()
        self.now[0] = a['deadline'] + 1
        b = self.commit(a,False)
        self.assertEqual(b['total'],10)
        self.assertEqual(b['result']['rush']['failures'],0)

    def test_late_continue_does_not_extend_timer(self):
        a = self.commit(self.create(),False)
        self.now[0] = a['deadline'] + 1
        b = self.continue_round(a)
        self.assertEqual(b['status'],'finished')
        self.assertEqual(b['finished_at'],a['deadline'])

    def test_timeout_after_server_restart(self):
        a = self.create()
        self.now[0] = a['deadline'] + 20
        Trainer(self.storage,self.banks)
        self.assertEqual(self.engine.fetch(2,a['id'])['result']['elapsed_seconds'],600)

    def test_draft_is_saved_without_scoring_or_advancing(self):
        a = self.create()
        q = self.snapshots(a)[0]
        selected = [o['id'] for o in q['options'] if o['correct']]
        a = self.engine.update(2,a['id'],{'revision':a['revision'],'index':0,'selected':selected})
        self.assertEqual(a['questions'][0]['selected'],selected)
        self.assertEqual(a['answered'],0)
        self.assertEqual(a['rush']['correct_count'],0)
        self.assertEqual(a['rush']['index'],0)

    def test_unconfirmed_correct_selection_never_scores_on_finish(self):
        a = self.create()
        q = self.snapshots(a)[0]
        selected = [o['id'] for o in q['options'] if o['correct']]
        a = self.engine.update(2,a['id'],{'revision':0,'index':0,'selected':selected})
        b = self.finish(a)
        self.assertEqual(b['result']['correct'],0)
        self.assertEqual(b['questions'][0]['outcome'],'unconfirmed')
        self.assertFalse(b['result']['rush']['completed'])

    def test_manual_end_in_feedback_keeps_feedback_and_all_sets_in_report(self):
        a = self.commit(self.create(),False)
        b = self.finish(a)
        self.assertEqual(b['result']['reason'],'submitted')
        self.assertEqual(b['total'],20)
        self.assertEqual(b['questions'][0]['explanation'],a['feedback']['explanation'])

    def test_exact_cardinality_and_valid_option_ids_required(self):
        a = self.create()
        q = a['questions'][0]
        for selected in ([], ['invalid'], [q['options'][0]['id']]*2, 'invalid', None, [True]):
            self.assertCode('rush_complete_selection',self.engine.rush_action,2,a['id'],
                            {'revision':0,'index':0,'selected':selected})
        self.assertEqual(self.engine.fetch(2,a['id'])['revision'],0)
        self.assertEqual(self.engine.fetch(2,a['id'])['total'],10)

    def test_multiselect_is_exact_set_no_partial_credit(self):
        # Rotate deterministically by winning one-question rounds until a
        # choose-two item is drawn. Every bank cycle contains such items.
        for _ in range(20):
            a = self.create(goal=1)
            if a['questions'][0]['select_count']==2:
                a = self.commit(a,False)
                self.assertEqual(a['rush']['correct_count'],0)
                self.assertEqual(a['rush']['failures'],1)
                return
            self.commit(a)
        self.fail('Expected a multiple-answer fixture question.')

    def test_cannot_skip_or_edit_previous_questions(self):
        a = self.create()
        q = self.snapshots(a)[1]
        selected = [o['id'] for o in q['options'] if o['correct']]
        self.assertCode('rush_current_only',self.engine.rush_action,2,a['id'],
                        {'revision':0,'index':1,'selected':selected})
        self.assertCode('rush_current_only',self.engine.update,2,a['id'],{'revision':0,'index':1,'selected':[]})
        a = self.commit(a)
        self.assertCode('rush_current_only',self.engine.update,2,a['id'],{'revision':a['revision'],'index':0,'selected':[]})

    def test_no_flags(self):
        a=self.create()
        self.assertCode('rush_no_flags',self.engine.update,2,a['id'],{'revision':0,'index':0,'flagged':True})

    def test_cannot_answer_while_feedback_is_pending(self):
        a=self.commit(self.create(),False)
        self.assertCode('rush_feedback_pending',self.engine.rush_action,2,a['id'],
                        {'revision':a['revision'],'index':10,'selected':[]})
        self.assertCode('rush_current_only',self.engine.update,2,a['id'],
                        {'revision':a['revision'],'index':10,'selected':[]})

    def test_continue_requires_feedback(self):
        a=self.create()
        self.assertCode('rush_no_feedback',self.engine.rush_action,2,a['id'],{'revision':0},'continue')

    def test_rush_endpoints_reject_other_modes(self):
        a=self.engine.create(2,'test-cert','quiz')
        self.assertCode('invalid_mode',self.engine.rush_action,2,a['id'],{'revision':0})

    def test_stale_duplicate_answer_does_not_count_twice(self):
        a=self.create()
        b=self.commit(a)
        self.assertCode('revision_conflict',self.commit,a)
        self.assertEqual(self.engine.fetch(2,a['id'])['rush']['correct_count'],1)
        self.assertEqual(b['rush']['index'],1)

    def test_duplicate_wrong_answer_does_not_generate_twice(self):
        a=self.create()
        self.commit(a,False)
        self.assertCode('revision_conflict',self.commit,a,False)
        self.assertEqual(self.engine.fetch(2,a['id'])['total'],20)

    def test_revision_types_are_strict(self):
        a=self.create()
        for revision in (False,'0',None,0.0):
            self.assertCode('revision_conflict',self.engine.rush_action,2,a['id'],{'revision':revision})

    def test_concurrent_submissions_only_one_wins(self):
        a=self.create()
        def submit():
            try:
                self.commit(a)
                return 'ok'
            except AppError as error:
                return error.code
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:submit(),range(2)))
        self.assertCountEqual(results,['ok','revision_conflict'])
        self.assertEqual(self.engine.fetch(2,a['id'])['rush']['correct_count'],1)

    def test_two_users_are_independent_and_cannot_read_each_other(self):
        a=self.create()
        b=self.create(user=3)
        self.commit(a,False)
        self.assertEqual(self.engine.fetch(3,b['id'])['total'],10)
        for function,args in ((self.engine.fetch,(3,a['id'])),
                              (self.engine.rush_action,(3,a['id'],{'revision':0})),
                              (self.engine.rush_action,(1,a['id'],{'revision':0}))):
            self.assertCode('attempt_not_found',function,*args)

    def test_one_active_session_includes_rush(self):
        self.create()
        self.assertCode('active_attempt_exists',self.engine.create,2,'test-cert','quiz')
        self.assertCode('active_attempt_exists',self.engine.create,2,'test-cert','exam')

    def test_no_repeat_until_entire_pool_generated(self):
        a=self.commit(self.create(),False)
        snapshots=self.snapshots(a)
        self.assertEqual(len({q['id'] for q in snapshots}),20)
        self.assertEqual({q['cycle'] for q in snapshots},{1})
        a=self.commit(self.continue_round(a),False)
        self.assertEqual({q['cycle'] for q in self.snapshots(a)[20:]},{2})
        self.assertEqual(len({q['id'] for q in self.snapshots(a)[20:]}),10)

    def test_all_modes_share_no_repeat_pool(self):
        a=self.engine.create(2,'test-cert','quiz')
        ids={q['id'] for q in self.snapshots(a)}
        self.finish(a)
        a=self.create()
        rush_ids={q['id'] for q in self.snapshots(a)}
        self.assertFalse(ids&rush_ids)
        self.finish(a)
        a=self.engine.create(2,'test-cert','quiz')
        new_ids={q['id'] for q in self.snapshots(a)}
        self.assertFalse((ids|rush_ids)&new_ids)
        self.assertEqual(len(ids|rush_ids|new_ids),20)

    def test_crossing_cycle_boundary_never_duplicates_within_set(self):
        a=self.create(goal=13)
        a=self.commit(a,False)
        questions=self.snapshots(a)
        for start in (0,13):
            self.assertEqual(len({q['id'] for q in questions[start:start+13]}),13)
        self.assertEqual({q['cycle'] for q in questions[13:]},{1,2})

    def test_bank_version_remains_pinned_after_update(self):
        a=self.create()
        m,q=bank_data(version='2.0.0')
        for question in q:
            question['prompt']['en']='NEW '+question['prompt']['en']
        self.banks.import_archive(make_archive(m,q),1,replace=True)
        a=self.commit(a,False)
        self.assertEqual(a['bank_version'],'1.0.0')
        self.assertFalse(any(q['prompt']['en'].startswith('NEW') for q in self.snapshots(a)))

    def test_disabled_bank_can_finish_its_existing_rush(self):
        a=self.create()
        self.configure(self.settings(),enabled=False)
        a=self.commit(a,False)
        self.assertEqual(a['total'],20)
        self.assertEqual(self.win(self.continue_round(a))['status'],'finished')

    def test_admin_configuration_applies_to_future_sessions_only(self):
        a=self.create()
        settings=self.settings();settings['rush']={'question_count':4,'duration_seconds':180}
        self.configure(settings)
        a=self.commit(a,False)
        self.assertEqual((a['total'],a['duration'],a['rush']['goal']),(20,600,10))
        self.finish(a)
        b=self.create()
        self.assertEqual((b['total'],b['duration']),(4,180))

    def test_rush_history_filter_and_average_separation(self):
        quiz=self.finish(self.answer_correct(self.engine.create(2,'test-cert','quiz')))
        rush=self.win(self.create())
        history=self.engine.history(2,kind='rush')
        self.assertEqual(history['total'],1)
        self.assertEqual(history['items'][0]['id'],rush['id'])
        stats=self.engine.dashboard(2)['banks'][0]['stats']
        self.assertEqual((stats['average'],stats['recent_count']),(100,1))
        self.assertEqual(stats['completed'],2)

    def test_profile_export_only_discloses_confirmed_feedback(self):
        a=self.commit(self.create(),False)
        exported=self.engine.export_profile(2)['attempts'][0]
        self.assertEqual(exported['feedback'],a['feedback'])
        self.assertEqual(exported['questions'],[])
        self.assertNotIn('result',exported)
        self.assertEqual(self.engine.export_profile(3)['attempts'],[])

    def test_final_report_explains_every_generated_question(self):
        a=self.finish(self.commit(self.create(),False))
        self.assertEqual(len(a['questions']),20)
        for q in a['questions']:
            self.assertIn('explanation',q)
            self.assertIn('round_number',q)
            self.assertTrue(q['scored'])
        self.assertEqual(a['result']['unscored_total'],0)
        self.assertEqual(sum(d['total'] for d in a['result']['domains'].values()),20)

    def test_empty_rush_finishes_with_zero_score(self):
        a=self.finish(self.create())
        self.assertEqual((a['result']['percentage'],a['result']['scored_total']),(0,10))
        self.assertEqual(a['result']['rush']['confirmed'],0)

    def test_goal_one_can_win_and_restart(self):
        a=self.create(goal=1)
        a=self.commit(a,False)
        a=self.win(self.continue_round(a))
        self.assertEqual(a['result']['percentage'],50)
        self.assertTrue(a['result']['rush']['completed'])

    def test_legacy_bank_defaults_gain_rush_without_content_change(self):
        raw=make_archive(self.manifest,self.questions)
        m,q,settings,digest=read_archive(raw)
        self.assertNotIn('rush',m['defaults'])
        self.assertEqual(settings['rush'],{'question_count':10,'duration_seconds':600})
        self.assertEqual(q,self.questions)
        self.assertEqual(len(digest),64)

    def test_small_bank_default_is_capped_at_its_size(self):
        m,q=bank_data(count=4,quiz=2,exam=4)
        _,_,settings,_=read_archive(make_archive(m,q))
        self.assertEqual(settings['rush']['question_count'],4)

    def test_invalid_rush_settings_rejected(self):
        for value in ({'question_count':0,'duration_seconds':600},
                      {'question_count':21,'duration_seconds':600},
                      {'question_count':10,'duration_seconds':0},
                      {'question_count':10,'duration_seconds':86401},
                      {'question_count':True,'duration_seconds':600},
                      {'question_count':10,'duration_seconds':False},
                      {'question_count':10,'duration_seconds':600,'unscored_count':1},
                      {'question_count':10},None):
            s=self.settings();s['rush']=value
            self.assertCode('invalid_bank',self.configure,s)

    def test_rush_settings_round_trip_through_export(self):
        settings=self.settings();settings['rush']={'question_count':7,'duration_seconds':120}
        self.configure(settings)
        m,q,s,_=read_archive(self.banks.export('test-cert'))
        self.assertEqual(m['defaults']['rush'],settings['rush'])
        self.assertEqual(s['rush'],settings['rush'])

    def test_legacy_v3_settings_in_database_work_without_reimport(self):
        with self.storage.connection() as con:
            con.execute('UPDATE banks SET settings=? WHERE id=?',
                        (json.dumps(self.manifest['defaults']),'test-cert'))
        self.assertEqual(self.engine.dashboard(2)['banks'][0]['settings']['rush']['question_count'],10)
        self.assertEqual(self.create()['duration'],600)

    def test_v3_database_marker_is_upgraded_without_losing_records(self):
        a = self.engine.create(2, 'test-cert', 'quiz')
        before = self.snapshots(a)
        with self.storage.connection() as con:
            con.execute('PRAGMA user_version=3')
        reopened = Storage(self.storage.path, clock=lambda: self.now[0])
        with reopened.connection() as con:
            self.assertEqual(con.execute('PRAGMA user_version').fetchone()[0], 4)
        self.assertEqual(before, self.snapshots(a))
        self.assertEqual(self.engine.fetch(2, a['id'])['deadline'], a['deadline'])

    def test_contract_v2_accepts_explicit_rush_defaults(self):
        manifest = deepcopy(self.manifest)
        manifest['schema_version'] = 2
        manifest['defaults']['rush'] = {'question_count': 6, 'duration_seconds': 420}
        _, _, settings, _ = read_archive(make_archive(manifest, self.questions))
        self.assertEqual(settings['rush']['question_count'], 6)

    def test_contract_v1_does_not_silently_accept_v2_fields(self):
        manifest = deepcopy(self.manifest)
        manifest['defaults']['rush'] = {'question_count': 6, 'duration_seconds': 420}
        self.assertCode('invalid_bank', read_archive, make_archive(manifest, self.questions))

    def test_export_upgrades_contract_not_content_version(self):
        manifest, _, _, _ = read_archive(self.banks.export('test-cert'))
        self.assertEqual(manifest['schema_version'], 2)
        self.assertEqual(manifest['version'], self.manifest['version'])

    def test_failed_draw_rolls_back_confirmation_counters_and_deck(self):
        a = self.create()
        before = self.snapshots(a)
        stats = self.engine.dashboard(2)['banks'][0]['stats']
        with patch.object(self.engine, 'draw', side_effect=RuntimeError('Simulated write failure')):
            with self.assertRaises(RuntimeError):
                self.commit(a, False)
        after = self.engine.fetch(2, a['id'])
        self.assertEqual(after['revision'], a['revision'])
        self.assertEqual(after['rush'], a['rush'])
        self.assertEqual(before, self.snapshots(a))
        self.assertEqual(stats, self.engine.dashboard(2)['banks'][0]['stats'])
