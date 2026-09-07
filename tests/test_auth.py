"""Real password hashing, administrator bootstrap and session isolation tests."""
from pathlib import Path
import tempfile
import unittest
from trainer.auth import Access, COOKIE_NAME, INITIAL_ADMIN_PASSWORD, PASSWORD_ITERATIONS, SESSION_SECONDS
from trainer.errors import AppError
from trainer.storage import Storage


class AuthenticationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.now = [1_780_000_000.0]
        self.storage = Storage(Path(self.tmp.name) / 'auth.sqlite3', clock=lambda: self.now[0])
        self.access = Access(self.storage)
        self.access.bootstrap_admin()

    def tearDown(self):
        self.tmp.cleanup()

    def assertCode(self, code, function, *args, **kwargs):
        with self.assertRaises(AppError) as context:
            function(*args, **kwargs)
        self.assertEqual(context.exception.code, code)

    def test_initial_administrator_credentials(self):
        token, user = self.access.login('Admin', 'Aws+10C41')
        self.assertEqual(user['role'], 'admin')
        self.assertTrue(user['default_password'])
        self.assertEqual(self.access.authenticated(f'{COOKIE_NAME}={token}')['id'], user['id'])

    def test_bootstrap_is_idempotent(self):
        self.assertFalse(self.access.bootstrap_admin())
        with self.storage.connection() as con:
            self.assertEqual(con.execute('SELECT COUNT(*) FROM users').fetchone()[0], 1)

    def test_password_never_stored_as_plaintext(self):
        with self.storage.connection() as con:
            row = con.execute('SELECT * FROM users').fetchone()
        self.assertNotEqual(row['password_hash'], INITIAL_ADMIN_PASSWORD)
        self.assertEqual(row['password_iterations'], PASSWORD_ITERATIONS)
        self.assertEqual(len(row['password_salt']), 32)
        self.assertEqual(len(row['password_hash']), 64)

    def test_registration_always_creates_learner(self):
        token, user = self.access.register('alice', 'A-unique-password', language='en')
        self.assertEqual(user['role'], 'learner')
        self.assertEqual(user['language'], 'en')
        self.assertNotIn('password_hash', user)
        self.assertTrue(self.access.authenticated(f'{COOKIE_NAME}={token}'))

    def test_username_is_case_insensitive(self):
        self.access.register('Alice', 'A-unique-password')
        _, user = self.access.login('ALICE', 'A-unique-password')
        self.assertEqual(user['username'], 'Alice')
        self.assertCode('username_exists', self.access.register, 'alice', 'Another-password')

    def test_reserved_admin_name_cannot_be_registered(self):
        for username in ('Admin', 'admin', 'ADMIN'):
            self.assertCode('username_exists', self.access.register, username, 'Another-password')

    def test_invalid_username(self):
        self.assertCode('invalid_username', self.access.register, '../Admin', 'Another-password')

    def test_invalid_password_length(self):
        self.assertCode('invalid_password', self.access.register, 'alice', 'short')

    def test_unknown_language_rejected(self):
        self.assertCode('invalid_language', self.access.register, 'alice', 'Another-password', language='fr')

    def test_bad_credentials_generic_error(self):
        self.assertCode('bad_credentials', self.access.login, 'Admin', 'Wrong-password')
        self.assertCode('bad_credentials', self.access.login, 'UnknownUser', 'Wrong-password')

    def test_learner_registration_can_be_disabled(self):
        self.access.registration_open = False
        self.assertCode('registration_closed', self.access.register, 'alice', 'Another-password')
        self.assertEqual(self.access.login('Admin', INITIAL_ADMIN_PASSWORD)[1]['role'], 'admin')

    def test_session_tokens_are_hashed_in_database(self):
        token, _ = self.access.login('Admin', INITIAL_ADMIN_PASSWORD)
        with self.storage.connection() as con:
            stored = con.execute('SELECT token_hash FROM sessions').fetchone()[0]
        self.assertNotEqual(token, stored)
        self.assertEqual(len(stored), 64)

    def test_logout_revokes_only_current_session(self):
        first, _ = self.access.login('Admin', INITIAL_ADMIN_PASSWORD)
        second, _ = self.access.login('Admin', INITIAL_ADMIN_PASSWORD)
        self.access.logout(f'{COOKIE_NAME}={first}')
        self.assertIsNone(self.access.authenticated(f'{COOKIE_NAME}={first}'))
        self.assertIsNotNone(self.access.authenticated(f'{COOKIE_NAME}={second}'))

    def test_expired_session_is_rejected(self):
        token, _ = self.access.login('Admin', INITIAL_ADMIN_PASSWORD)
        self.now[0] += SESSION_SECONDS + 1
        self.assertIsNone(self.access.authenticated(f'{COOKIE_NAME}={token}'))

    def test_malformed_cookie_is_rejected(self):
        for value in ('', None, f'{COOKIE_NAME}=../../bad', 'other=abc'):
            self.assertIsNone(self.access.authenticated(value))

    def test_password_change_revokes_other_sessions(self):
        first, user = self.access.login('Admin', INITIAL_ADMIN_PASSWORD)
        second, _ = self.access.login('Admin', INITIAL_ADMIN_PASSWORD)
        new = self.access.change_password(user['id'], INITIAL_ADMIN_PASSWORD, 'Replacement-password')
        self.assertIsNone(self.access.authenticated(f'{COOKIE_NAME}={first}'))
        self.assertIsNone(self.access.authenticated(f'{COOKIE_NAME}={second}'))
        self.assertFalse(self.access.authenticated(f'{COOKIE_NAME}={new}')['default_password'])
        self.assertFalse(self.access.bootstrap_admin())
        self.assertCode('bad_credentials', self.access.login, 'Admin', INITIAL_ADMIN_PASSWORD)
        self.assertEqual(self.access.login('Admin', 'Replacement-password')[1]['role'], 'admin')

    def test_wrong_current_password_does_not_change_account(self):
        _, user = self.access.login('Admin', INITIAL_ADMIN_PASSWORD)
        self.assertCode('wrong_current_password', self.access.change_password, user['id'], 'Incorrect', 'Replacement-password')
        self.assertEqual(self.access.login('Admin', INITIAL_ADMIN_PASSWORD)[1]['role'], 'admin')

    def test_local_password_reset_preserves_role_and_revokes_session(self):
        token, _ = self.access.login('Admin', INITIAL_ADMIN_PASSWORD)
        self.access.reset_password('admin', 'Reset-password')
        self.assertIsNone(self.access.authenticated(f'{COOKIE_NAME}={token}'))
        self.assertEqual(self.access.login('Admin', 'Reset-password')[1]['role'], 'admin')

    def test_profile_edit_cannot_change_role(self):
        _, user = self.access.register('alice', 'A-unique-password')
        result = self.access.edit_profile(user['id'], 'Alice Display', 'en')
        self.assertEqual(result['role'], 'learner')
        self.assertEqual(result['display_name'], 'Alice Display')

    def test_rate_limiter_blocks_repeated_attempts(self):
        for _ in range(12):
            self.access.rate_limit('login', '192.0.2.4', 'alice')
        self.assertCode('rate_limited', self.access.rate_limit, 'login', '192.0.2.4', 'alice')

    def test_users_have_different_password_salts(self):
        self.access.register('alice', 'Same-password')
        self.access.register('bobby', 'Same-password')
        with self.storage.connection() as con:
            rows = con.execute("SELECT password_salt,password_hash FROM users WHERE role='learner'").fetchall()
        self.assertNotEqual(rows[0]['password_salt'], rows[1]['password_salt'])
        self.assertNotEqual(rows[0]['password_hash'], rows[1]['password_hash'])
