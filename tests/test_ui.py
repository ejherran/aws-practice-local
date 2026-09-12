"""Standard-library checks for the optional, isolated browser QA fixtures."""
import json
import tempfile
import unittest

from tools.check_ui import create_fixtures, json_for_script


class UIFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with tempfile.TemporaryDirectory() as directory:
            cls.fixtures = create_fixtures(directory)

    def test_many_banks_and_one_profile_without_credentials(self):
        self.assertEqual(len(self.fixtures['/api/dashboard']['banks']), 26)
        user = self.fixtures['/api/session']['user']
        self.assertEqual(user['username'], 'Admin')
        self.assertEqual(set(user), {'id', 'username', 'display_name', 'role',
                                     'language', 'created_at', 'default_password'})
        self.assertNotIn('Synthetic-UI-password', json.dumps(self.fixtures))

    def test_active_fixtures_keep_answer_keys_private(self):
        for name in ('attempt', 'saved', 'rush'):
            attempt = self.fixtures[name]
            self.assertEqual(attempt['status'], 'active')
            for question in attempt['questions']:
                self.assertNotIn('explanation', question)
                self.assertTrue(all('correct' not in option for option in question['options']))
        self.assertEqual(len(self.fixtures['rush']['questions']), 1)

    def test_saved_answer_and_finished_report_are_distinct_snapshots(self):
        attempt, saved, report = (self.fixtures[name] for name in ('attempt', 'saved', 'report'))
        self.assertEqual(attempt['questions'][0]['selected'], [])
        self.assertEqual(len(saved['questions'][0]['selected']), 1)
        self.assertEqual(report['status'], 'finished')
        self.assertGreater(saved['revision'], attempt['revision'])

    def test_embedded_json_cannot_close_script(self):
        content = {'en': '</script><script>alert(1)</script>', 'es': '<!-- & café'}
        encoded = json_for_script(content)
        self.assertNotIn('<', encoded)
        self.assertEqual(json.loads(encoded), content)
