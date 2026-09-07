"""Local profiles, role checks, password derivation and revocable sessions."""
from collections import defaultdict, deque
import hashlib
import hmac
from http.cookies import SimpleCookie, CookieError
import re
import secrets
import sqlite3
import threading
import time
from .errors import AppError

PASSWORD_ITERATIONS = 600_000
SESSION_SECONDS = 30 * 86400
INITIAL_ADMIN_USERNAME = 'Admin'
INITIAL_ADMIN_PASSWORD = 'Aws+10C41'
COOKIE_NAME = 'practice_session'


class Access:
    def __init__(self, storage, registration_open=True):
        self.storage = storage
        self.registration_open = registration_open
        self.lock = threading.Lock()
        self.attempts = defaultdict(deque)
        self.hash_slots = threading.BoundedSemaphore(4)
        self.dummy_salt = secrets.token_hex(16)

    @staticmethod
    def username(value):
        if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{2,31}', value.strip()):
            raise AppError(400, 'invalid_username')
        return value.strip()

    @staticmethod
    def password(value, new=False):
        if not isinstance(value, str) or not (8 if new else 1) <= len(value) <= 128:
            raise AppError(400, 'invalid_password')
        try:
            value.encode('utf-8')
        except UnicodeError:
            raise AppError(400, 'invalid_password')
        return value

    @staticmethod
    def display_name(value, default=''):
        value = default if value is None else value
        if not isinstance(value, str) or not 1 <= len(value.strip()) <= 64:
            raise AppError(400, 'invalid_display_name')
        if any(ord(c) < 32 or 0xD800 <= ord(c) <= 0xDFFF for c in value):
            raise AppError(400, 'invalid_display_name')
        return value.strip()

    @staticmethod
    def language(value):
        if value not in ('en', 'es'):
            raise AppError(400, 'invalid_language')
        return value

    @staticmethod
    def derive(password, salt, iterations=PASSWORD_ITERATIONS):
        return hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), bytes.fromhex(salt), iterations).hex()

    @staticmethod
    def public(row):
        result = {key: row[key] for key in ('id', 'username', 'display_name', 'role', 'language', 'created_at')}
        result['default_password'] = bool(row['default_password'])
        return result

    def bootstrap_admin(self):
        """Create the administrator once; restarting never resets its password."""
        with self.storage.connection() as con:
            if con.execute("SELECT 1 FROM users WHERE username=? COLLATE NOCASE", (INITIAL_ADMIN_USERNAME,)).fetchone():
                return False
            salt = secrets.token_hex(16)
            digest = self.derive(INITIAL_ADMIN_PASSWORD, salt)
            con.execute('''INSERT INTO users(username,display_name,role,language,password_salt,
                         password_hash,password_iterations,created_at,default_password)
                         VALUES(?,?,'admin','es',?,?,?,?,1)''',
                        (INITIAL_ADMIN_USERNAME, 'Administrator', salt, digest, PASSWORD_ITERATIONS,
                         self.storage.clock()))
        return True

    def rate_limit(self, action, ip, username=''):
        now = time.monotonic()
        window, limit = (3600, 12) if action == 'register' else (60, 20)
        keys = [(f'{action}:ip:{ip}', limit)]
        if username:
            keys.append((f'{action}:user:{username.lower()}', 12))
        with self.lock:
            if len(self.attempts) > 2048:
                self.attempts = defaultdict(deque, {k: v for k, v in self.attempts.items()
                                                  if v and now - v[-1] < 3600})
            if len(self.attempts) > 4096:
                raise AppError(429, 'rate_limited')
            for key, cap in keys:
                queue = self.attempts[key]
                while queue and now - queue[0] >= window:
                    queue.popleft()
                if len(queue) >= cap:
                    raise AppError(429, 'rate_limited')
            for key, _ in keys:
                self.attempts[key].append(now)

    def new_session(self, con, user_id):
        now = self.storage.clock()
        con.execute('DELETE FROM sessions WHERE expires_at<=?', (now,))
        con.execute('''DELETE FROM sessions WHERE user_id=? AND token_hash NOT IN
                    (SELECT token_hash FROM sessions WHERE user_id=?
                     ORDER BY created_at DESC,rowid DESC LIMIT 19)''', (user_id, user_id))
        token = secrets.token_urlsafe(32)
        digest = hashlib.sha256(token.encode('ascii')).hexdigest()
        con.execute('INSERT INTO sessions VALUES(?,?,?,?)', (digest, user_id, now, now + SESSION_SECONDS))
        return token

    @staticmethod
    def token_hash(header):
        try:
            cookie = SimpleCookie()
            cookie.load(header or '')
            token = cookie[COOKIE_NAME].value
            if not re.fullmatch(r'[A-Za-z0-9_-]{43}', token):
                return None
            return hashlib.sha256(token.encode('ascii')).hexdigest()
        except (CookieError, KeyError, ValueError):
            return None

    def authenticated(self, header):
        digest = self.token_hash(header)
        if not digest:
            return None
        with self.storage.connection() as con:
            row = con.execute('''SELECT u.* FROM users u JOIN sessions s ON s.user_id=u.id
                              WHERE s.token_hash=? AND s.expires_at>?''',
                              (digest, self.storage.clock())).fetchone()
            return self.public(row) if row else None

    def register(self, username, password, display_name=None, language='es', ip='local'):
        if not self.registration_open:
            raise AppError(403, 'registration_closed')
        self.rate_limit('register', ip)
        username = self.username(username)
        if username.lower() == INITIAL_ADMIN_USERNAME.lower():
            raise AppError(409, 'username_exists')
        password = self.password(password, new=True)
        name = self.display_name(display_name, username)
        language = self.language(language)
        if not self.hash_slots.acquire(blocking=False):
            raise AppError(429, 'rate_limited')
        try:
            salt = secrets.token_hex(16)
            digest = self.derive(password, salt)
        finally:
            self.hash_slots.release()
        with self.storage.connection() as con:
            try:
                cursor = con.execute('''INSERT INTO users(username,display_name,role,language,password_salt,
                                   password_hash,password_iterations,created_at)
                                   VALUES(?,?,'learner',?,?,?,?,?)''',
                                   (username, name, language, salt, digest, PASSWORD_ITERATIONS, self.storage.clock()))
            except sqlite3.IntegrityError:
                raise AppError(409, 'username_exists')
            uid = cursor.lastrowid
            token = self.new_session(con, uid)
            user = self.public(con.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone())
            return token, user

    def login(self, username, password, ip='local'):
        username, password = self.username(username), self.password(password)
        self.rate_limit('login', ip, username)
        with self.storage.connection() as con:
            row = con.execute('SELECT * FROM users WHERE username=? COLLATE NOCASE', (username,)).fetchone()
        if not self.hash_slots.acquire(blocking=False):
            raise AppError(429, 'rate_limited')
        try:
            digest = self.derive(password, row['password_salt'] if row else self.dummy_salt,
                                 row['password_iterations'] if row else PASSWORD_ITERATIONS)
            expected = row['password_hash'] if row else '0' * 64
            if not hmac.compare_digest(digest, expected) or row is None:
                raise AppError(401, 'bad_credentials')
        finally:
            self.hash_slots.release()
        with self.storage.connection() as con:
            current = con.execute('SELECT * FROM users WHERE id=?', (row['id'],)).fetchone()
            if not current or current['password_hash'] != expected:
                raise AppError(401, 'bad_credentials')
            return self.new_session(con, row['id']), self.public(current)

    def logout(self, header):
        digest = self.token_hash(header)
        if digest:
            with self.storage.connection() as con:
                con.execute('DELETE FROM sessions WHERE token_hash=?', (digest,))

    def edit_profile(self, user_id, display_name, language):
        name, language = self.display_name(display_name), self.language(language)
        with self.storage.connection() as con:
            con.execute('UPDATE users SET display_name=?,language=? WHERE id=?', (name, language, user_id))
            row = con.execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone()
            if not row:
                raise AppError(401, 'sign_in_required')
            return self.public(row)

    def change_password(self, user_id, current_password, new_password, ip='local'):
        current_password = self.password(current_password)
        new_password = self.password(new_password, new=True)
        self.rate_limit('password', ip, str(user_id))
        with self.storage.connection() as con:
            row = con.execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone()
        if not row:
            raise AppError(401, 'sign_in_required')
        if not self.hash_slots.acquire(blocking=False):
            raise AppError(429, 'rate_limited')
        try:
            digest = self.derive(current_password, row['password_salt'], row['password_iterations'])
            if not hmac.compare_digest(digest, row['password_hash']):
                raise AppError(400, 'wrong_current_password')
            salt = secrets.token_hex(16)
            new_digest = self.derive(new_password, salt)
        finally:
            self.hash_slots.release()
        with self.storage.connection() as con:
            current = con.execute('SELECT password_hash FROM users WHERE id=?', (user_id,)).fetchone()
            if not current or current[0] != row['password_hash']:
                raise AppError(409, 'profile_changed')
            con.execute('''UPDATE users SET password_salt=?,password_hash=?,password_iterations=?,
                         default_password=0 WHERE id=?''', (salt, new_digest, PASSWORD_ITERATIONS, user_id))
            con.execute('DELETE FROM sessions WHERE user_id=?', (user_id,))
            return self.new_session(con, user_id)

    def reset_password(self, username, password):
        username, password = self.username(username), self.password(password, new=True)
        salt = secrets.token_hex(16)
        digest = self.derive(password, salt)
        with self.storage.connection() as con:
            row = con.execute('SELECT id FROM users WHERE username=? COLLATE NOCASE', (username,)).fetchone()
            if not row:
                raise AppError(404, 'user_not_found')
            con.execute('''UPDATE users SET password_salt=?,password_hash=?,password_iterations=?,
                         default_password=0 WHERE id=?''', (salt, digest, PASSWORD_ITERATIONS, row['id']))
            con.execute('DELETE FROM sessions WHERE user_id=?', (row['id'],))
