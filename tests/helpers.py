"""Deterministic test fixtures; never modify application data."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from trainer.auth import Access, COOKIE_NAME
from trainer.banks import BankRepository, make_archive
from trainer.engine import Trainer
from trainer.errors import AppError
from trainer.storage import Storage

ROOT = Path(__file__).resolve().parents[1]


def bank_data(count=20, bank_id='test-cert', version='1.0.0', quiz=5, exam=10):
    """Create synthetic questions with transparent correctness for engine tests."""
    name = lambda value: {'en': value, 'es': 'ES ' + value}
    manifest = {
        'schema_version': 1, 'bank_id': bank_id, 'version': version,
        'exam_code': 'TEST', 'title': name('Test certification'),
        'description': name('Synthetic test fixture, not learning content.'),
        'languages': ['en', 'es'], 'default_language': 'en',
        'domains': [{'id': 'd1', 'name': name('Domain one')},
                    {'id': 'd2', 'name': name('Domain two')}],
        'defaults': {
            'quiz': {'question_count': quiz, 'duration_seconds': 300,
                     'unscored_count': 0, 'time_mode': 'proportional', 'target_percentage': 80},
            'exam': {'question_count': exam, 'duration_seconds': 600,
                     'unscored_count': min(2, exam - 1), 'time_mode': 'fixed', 'target_percentage': 80},
            'domain_weights': {'d1': 50, 'd2': 50}},
        'references': {'example': {'title': name('Reference'), 'url': 'https://example.org/reference'}},
        'content_updated_at': '2026-09-06'}
    questions = []
    for i in range(count):
        select = 2 if i % 3 == 0 else 1
        questions.append({
            'id': f'T{i:04d}', 'domain_id': 'd1' if i % 2 == 0 else 'd2',
            'task_id': 'test', 'select_count': select,
            'prompt': name(f'Synthetic question {i}: choose {select} matching options.'),
            'explanation': name('Match the expected options.'),
            'options': [{'id': chr(65 + j), 'text': name(f'Option {j} for question {i}'),
                         'explanation': name(f'Explanation for option {j}.'), 'correct': j < select}
                        for j in range(4)],
            'references': ['example']})
    return manifest, questions


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.now = [1_780_000_000.0]
        self.storage = Storage(Path(self.tmp.name) / 'test.sqlite3', clock=lambda: self.now[0])
        self.access = Access(self.storage)
        # Production hashing is tested separately. Most domain tests need only
        # existing users and should not repeat expensive password derivation.
        with self.storage.connection() as con:
            for uid, username, role in [(1, 'Admin', 'admin'), (2, 'alice', 'learner'), (3, 'bob', 'learner')]:
                con.execute('''INSERT INTO users(id,username,display_name,role,language,password_salt,
                    password_hash,password_iterations,created_at) VALUES(?,?,?,?,?,?,?,?,?)''',
                    (uid, username, username, role, 'en', '00' * 16, '0' * 64, 600000, self.now[0]))
        self.banks = BankRepository(self.storage)
        self.manifest, self.questions = bank_data()
        self.banks.import_archive(make_archive(self.manifest, self.questions), 1)
        self.engine = Trainer(self.storage, self.banks)

    def tearDown(self):
        self.tmp.cleanup()

    def assertCode(self, code, function, *args, **kwargs):
        with self.assertRaises(AppError) as context:
            function(*args, **kwargs)
        self.assertEqual(context.exception.code, code)
        return context.exception

    def snapshots(self, attempt):
        with self.storage.connection() as con:
            return json.loads(con.execute('SELECT payload FROM attempts WHERE id=?', (attempt['id'],)).fetchone()[0])

    def answer_correct(self, attempt, user=2, how_many=None, scored_only=False):
        snapshots = self.snapshots(attempt)
        picked = 0
        for index, q in enumerate(snapshots):
            if scored_only and not q['scored']:
                continue
            if how_many is not None and picked >= how_many:
                break
            selected = [option['id'] for option in q['options'] if option['correct']]
            attempt = self.engine.update(user, attempt['id'], {'index': index, 'revision': attempt['revision'], 'selected': selected})
            picked += 1
        return attempt

    def finish(self, attempt, user=2):
        self.now[0] += 1
        return self.engine.finish(user, attempt['id'], attempt['revision'])

    def settings(self):
        return deepcopy(self.banks.list(True)[0]['settings'])

    def configure(self, settings, enabled=True):
        return self.banks.configure('test-cert', settings, enabled, 1)

    def cookie(self, uid):
        with self.storage.connection() as con:
            token = self.access.new_session(con, uid)
        return f'{COOKIE_NAME}={token}'
