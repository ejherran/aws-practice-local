"""Live HTTP tests using only the Python standard library."""
from copy import deepcopy
import http.client
import json
from pathlib import Path
import socket
import ssl
import tempfile
import threading
from trainer.auth import IDLE_SECONDS
from trainer.banks import make_archive, read_archive
from trainer.server import LocalServer
from trainer.tls import ensure_certificate
from tests.helpers import ROOT, Fixture, bank_data


class HTTPTests(Fixture):
    @classmethod
    def setUpClass(cls):
        cls.tls_directory = tempfile.TemporaryDirectory()
        cls.tls_context, cert, _ = ensure_certificate(Path(cls.tls_directory.name), '127.0.0.1')
        cls.client_context = ssl.create_default_context(cafile=str(cert))

    @classmethod
    def tearDownClass(cls):
        cls.tls_directory.cleanup()

    def setUp(self):
        super().setUp()
        self.server = LocalServer(('127.0.0.1', 0), self.engine, self.access, ROOT / 'web',
                                  ROOT / 'schema/question-bank-authoring-kit.zip', tls_context=self.tls_context)
        self.thread = threading.Thread(target=lambda: self.server.serve_forever(poll_interval=0.01), daemon=True)
        self.thread.start()
        self.cookies = {uid: self.cookie(uid) for uid in (1, 2, 3)}
        self.origin = f'https://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        super().tearDown()

    def request(self, path, method='GET', body=None, user=2, headers=None, raw=False):
        request_headers = {'Host': f'127.0.0.1:{self.server.server_port}'}
        if user:
            request_headers.update({'Cookie': self.cookies[user], 'X-Profile-ID': str(user)})
        if method == 'POST':
            request_headers.update({'Content-Type': 'application/zip' if raw else 'application/json',
                                    'X-Local-App': '1', 'Origin': self.origin})
        if headers:
            for k, v in headers.items():
                if v is None:
                    request_headers.pop(k, None)
                else:
                    request_headers[k] = v
        payload = body if raw else json.dumps(body).encode() if body is not None else b'{}' if method == 'POST' else None
        con = http.client.HTTPSConnection('127.0.0.1', self.server.server_port, timeout=5,
                                          context=self.client_context)
        try:
            con.request(method, path, body=payload, headers=request_headers)
            response = con.getresponse()
            content, response_headers = response.read(), dict(response.getheaders())
            decoded = json.loads(content) if content and 'application/json' in response_headers.get('Content-Type', '') else content
            return response.status, decoded, response_headers
        finally:
            con.close()

    def test_public_page_available(self):
        status, body, headers = self.request('/', user=None)
        self.assertEqual(status, 200)
        self.assertIn(b'/app.js', body)
        self.assertIn('Content-Security-Policy', headers)
        self.assertEqual(headers['X-Content-Type-Options'], 'nosniff')

    def test_http_is_rejected(self):
        con = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=2)
        try:
            with self.assertRaises((OSError, http.client.HTTPException)):
                con.request('GET', '/')
                con.getresponse()
        finally:
            con.close()

    def test_unfinished_handshake_does_not_block_other_clients(self):
        with socket.create_connection(('127.0.0.1', self.server.server_port), timeout=2):
            self.assertEqual(self.request('/')[0], 200)

    def test_passive_requests_never_extend_idle_session(self):
        for _ in range(6):
            self.now[0] += 599
            self.assertEqual(self.request('/api/dashboard')[0], 200)
            self.assertTrue(self.request('/api/session')[1]['authenticated'])
        self.now[0] += 6
        self.assertFalse(self.request('/api/session')[1]['authenticated'])
        self.assertEqual(self.request('/api/dashboard')[0], 401)

    def test_activity_extends_only_the_current_cookie(self):
        original = self.now[0]
        self.now[0] += 3599
        status, result, headers = self.request('/api/activity', 'POST', {})
        self.assertEqual(status, 200)
        self.assertEqual(result['expires_at'], self.now[0] + IDLE_SECONDS)
        self.assertEqual(float(headers['X-Session-Expires-At']), result['expires_at'])
        self.now[0] = original + 3600
        self.assertEqual(self.request('/api/dashboard')[0], 200)
        self.assertEqual(self.request('/api/dashboard', user=3)[0], 401)

    def test_expired_session_cannot_be_revived_or_edit_attempt(self):
        attempt = self.engine.create(2, 'test-cert', 'quiz')
        self.now[0] += IDLE_SECONDS
        for route, body in [('/api/activity', {}),
                            (f'/api/attempts/{attempt["id"]}/answer',
                             {'revision': 0, 'index': 0, 'selected': []})]:
            self.assertEqual(self.request(route, 'POST', body)[0], 401)

    def test_activity_requires_origin_and_expected_profile(self):
        for headers, expected in [({'Origin': 'https://attacker.example'}, 403),
                                  ({'X-Profile-ID': '3'}, 409),
                                  ({'X-Profile-ID': None}, 409),
                                  ({'X-Local-App': None}, 403)]:
            with self.subTest(headers=headers):
                self.assertEqual(self.request('/api/activity', 'POST', {}, headers=headers)[0], expected)

    def test_cookie_always_secure_including_deletion(self):
        from trainer.server import Handler
        self.assertIn('; Secure;', Handler.session_cookie(None, 'example'))
        status, _, headers = self.request('/api/logout', 'POST', {})
        self.assertEqual(status, 200)
        self.assertIn('; Secure;', headers['Set-Cookie'])
        self.assertIn('Max-Age=0', headers['Set-Cookie'])

    def test_tls_files_are_never_served(self):
        for path in ('/data/tls/server-key.pem', '/data/tls/server-cert.pem', '/trainer/tls.py'):
            self.assertEqual(self.request(path)[0], 404)

    def test_locales_available_without_login(self):
        for language in ('en', 'es'):
            status, body, _ = self.request(f'/locales/{language}.json', user=None)
            self.assertEqual(status, 200)
            self.assertIn('sign_in', body)

    def test_unauthenticated_session_is_public(self):
        status, body, _ = self.request('/api/session', user=None)
        self.assertEqual(status, 200)
        self.assertFalse(body['authenticated'])

    def test_dashboard_requires_authentication(self):
        status, body, _ = self.request('/api/dashboard', user=None)
        self.assertEqual((status, body['code']), (401, 'sign_in_required'))

    def test_student_cannot_access_admin_catalog(self):
        status, body, _ = self.request('/api/admin/banks')
        self.assertEqual((status, body['code']), (403, 'admin_required'))

    def test_student_cannot_import_bank(self):
        m, q = bank_data(bank_id='other-cert')
        status, body, _ = self.request('/api/admin/banks/import', 'POST', make_archive(m, q), raw=True)
        self.assertEqual((status, body['code']), (403, 'admin_required'))
        self.assertEqual(len(self.banks.list()), 1)

    def test_student_cannot_configure_bank(self):
        status, body, _ = self.request('/api/admin/banks/test-cert/configure', 'POST', {'settings': self.settings(), 'enabled': False})
        self.assertEqual((status, body['code']), (403, 'admin_required'))

    def test_student_cannot_export_full_answer_bank(self):
        status, body, _ = self.request('/api/admin/banks/test-cert/export')
        self.assertEqual((status, body['code']), (403, 'admin_required'))

    def test_admin_can_validate_import_configure_and_export(self):
        m, q = bank_data(bank_id='another-cert')
        archive = make_archive(m, q)
        status, preview, _ = self.request('/api/admin/banks/validate', 'POST', archive, user=1, raw=True)
        self.assertEqual(status, 200)
        self.assertEqual(preview['question_count'], 20)
        self.assertEqual(len(self.banks.list()), 1)
        self.assertEqual(self.request('/api/admin/banks/import', 'POST', archive, user=1, raw=True)[0], 200)
        settings = deepcopy(m['defaults'])
        settings['quiz']['question_count'] = 3
        status, body, _ = self.request('/api/admin/banks/another-cert/configure', 'POST', {'settings': settings, 'enabled': True}, user=1)
        self.assertEqual(status, 200)
        self.assertEqual(body['settings']['quiz']['duration_seconds'], 180)
        status, exported, headers = self.request('/api/admin/banks/another-cert/export', user=1)
        self.assertEqual(status, 200)
        self.assertEqual(headers['Content-Type'], 'application/zip')
        self.assertEqual(read_archive(exported)[2]['quiz']['question_count'], 3)

    def test_any_authenticated_user_can_download_schema(self):
        status, body, headers = self.request('/api/schema.zip')
        self.assertEqual(status, 200)
        self.assertEqual(headers['Content-Type'], 'application/zip')
        self.assertTrue(body.startswith(b'PK'))

    def test_cross_origin_post_rejected(self):
        status, body, _ = self.request('/api/attempts', 'POST', {'bank_id': 'test-cert', 'kind': 'quiz'}, headers={'Origin': 'http://malicious.example'})
        self.assertEqual((status, body['code']), (403, 'origin_forbidden'))

    def test_missing_csrf_header_rejected(self):
        status, body, _ = self.request('/api/attempts', 'POST', {'bank_id': 'test-cert', 'kind': 'quiz'}, headers={'X-Local-App': None})
        self.assertEqual((status, body['code']), (403, 'origin_forbidden'))

    def test_mismatched_profile_header_rejected(self):
        status, body, _ = self.request('/api/dashboard', headers={'X-Profile-ID': '3'})
        self.assertEqual((status, body['code']), (409, 'profile_changed'))

    def test_post_requires_profile_binding(self):
        status, body, _ = self.request('/api/attempts', 'POST', {'bank_id': 'test-cert', 'kind': 'quiz'}, headers={'X-Profile-ID': None})
        self.assertEqual((status, body['code']), (409, 'profile_changed'))

    def test_untrusted_host_rejected(self):
        status, body, _ = self.request('/', headers={'Host': 'malicious.example'})
        self.assertEqual((status, body['code']), (403, 'host_forbidden'))

    def test_database_not_served(self):
        status, _, _ = self.request('/data/practice.sqlite3')
        self.assertNotEqual(status, 200)

    def test_source_code_not_served(self):
        status, _, _ = self.request('/trainer/auth.py')
        self.assertNotEqual(status, 200)

    def test_path_traversal_not_served(self):
        status, _, _ = self.request('/../app.py')
        self.assertNotEqual(status, 200)

    def test_cross_user_result_fetch_rejected(self):
        a = self.engine.create(2, 'test-cert', 'quiz')
        status, body, _ = self.request('/api/attempts/' + a['id'], user=3)
        self.assertEqual((status, body['code']), (404, 'attempt_not_found'))

    def test_live_attempt_answer_submit_and_export(self):
        status, a, _ = self.request('/api/attempts', 'POST', {'bank_id': 'test-cert', 'kind': 'quiz'})
        self.assertEqual(status, 201)
        correct = [o['id'] for o in self.snapshots(a)[0]['options'] if o['correct']]
        status, a, _ = self.request(f"/api/attempts/{a['id']}/answer", 'POST', {'index': 0, 'revision': a['revision'], 'selected': correct})
        self.assertEqual(status, 200)
        status, a, _ = self.request(f"/api/attempts/{a['id']}/finish", 'POST', {'revision': a['revision']})
        self.assertEqual(status, 200)
        self.assertEqual(a['result']['correct'], 1)
        status, report, _ = self.request(f"/api/attempts/{a['id']}/export")
        self.assertEqual(status, 200)
        self.assertTrue(report['questions'][0]['is_correct'])

    def test_active_attempt_export_blocked(self):
        a = self.engine.create(2, 'test-cert', 'quiz')
        status, body, _ = self.request(f"/api/attempts/{a['id']}/export")
        self.assertEqual((status, body['code']), (409, 'attempt_not_finished'))

    def test_unknown_kind_rejected(self):
        status, body, _ = self.request('/api/attempts', 'POST', {'bank_id': 'test-cert', 'kind': 'official'})
        self.assertEqual((status, body['code']), (400, 'invalid_mode'))

    def test_registration_ignores_attempted_admin_role(self):
        status, body, headers = self.request('/api/register', 'POST', {'username': 'newlearner', 'password': 'Unique-password', 'language': 'en', 'role': 'admin'}, user=None)
        self.assertEqual(status, 200)
        self.assertEqual(body['user']['role'], 'learner')
        self.assertIn('HttpOnly', headers['Set-Cookie'])
        self.assertIn('SameSite=Strict', headers['Set-Cookie'])

    def test_language_profile_update_persisted(self):
        status, body, _ = self.request('/api/profile', 'POST', {'display_name': 'Alice', 'language': 'es', 'role': 'admin'})
        self.assertEqual(status, 200)
        self.assertEqual(body['user']['language'], 'es')
        self.assertEqual(body['user']['role'], 'learner')

    def test_duplicate_json_key_rejected(self):
        status, body, _ = self.request('/api/profile', 'POST', b'{"language":"es","language":"en"}', raw=True,
                                       headers={'Content-Type': 'application/json'})
        self.assertEqual((status, body['code']), (400, 'invalid_json'))

    def test_audit_read_requires_admin(self):
        self.assertEqual(self.request('/api/admin/audit', user=2)[0], 403)
        status, body, _ = self.request('/api/admin/audit', user=1)
        self.assertEqual(status, 200)
        self.assertEqual(body['items'][0]['action'], 'bank_import')

    def rush_submission(self, a, correct=True):
        q = self.snapshots(a)[a['rush']['index']]
        selected = [o['id'] for o in q['options'] if o['correct']]
        if not correct:
            selected[-1] = next(o['id'] for o in q['options'] if not o['correct'])
        return {'revision': a['revision'], 'index': a['rush']['index'], 'selected': selected}

    def test_http_rush_full_flow_and_filtered_history(self):
        settings = self.settings(); settings['rush'] = {'question_count': 2, 'duration_seconds': 600}
        self.configure(settings)
        status, a, _ = self.request('/api/attempts', 'POST', {'bank_id': 'test-cert', 'kind': 'rush'})
        self.assertEqual(status, 201)
        status, a, _ = self.request(f"/api/attempts/{a['id']}/rush-answer", 'POST', self.rush_submission(a, False))
        self.assertEqual(status, 200)
        self.assertEqual(a['rush']['phase'], 'feedback')
        self.assertIn('explanation', a['feedback'])
        status, a, _ = self.request(f"/api/attempts/{a['id']}/rush-continue", 'POST', {'revision': a['revision']})
        self.assertEqual(status, 200)
        for _ in range(2):
            status, a, _ = self.request(f"/api/attempts/{a['id']}/rush-answer", 'POST', self.rush_submission(a))
            self.assertEqual(status, 200)
        self.assertEqual(a['result']['percentage'], 50)
        self.assertTrue(a['result']['rush']['completed'])
        status, h, _ = self.request('/api/history?kind=rush')
        self.assertEqual((status, h['total']), (200, 1))
        self.assertEqual(h['items'][0]['id'], a['id'])
        status, exported, _ = self.request(f"/api/attempts/{a['id']}/export")
        self.assertEqual((status, exported['total']), (200, 4))

    def test_http_rush_owner_and_admin_cannot_access_another_profile(self):
        a = self.engine.create(2, 'test-cert', 'rush')
        body = self.rush_submission(a)
        for uid in (1, 3):
            status, data, _ = self.request(f"/api/attempts/{a['id']}/rush-answer", 'POST', body, user=uid)
            self.assertEqual((status, data['code']), (404, 'attempt_not_found'))

    def test_http_rush_requires_login_and_expected_profile(self):
        a = self.engine.create(2, 'test-cert', 'rush')
        for uid, headers, expected in ((None, None, 401), (2, {'X-Profile-ID': None}, 409),
                                       (2, {'X-Profile-ID': '3'}, 409)):
            self.assertEqual(self.request(f"/api/attempts/{a['id']}/rush-answer", 'POST',
                                         self.rush_submission(a), user=uid, headers=headers)[0], expected)

    def test_http_rush_same_origin_protection(self):
        a = self.engine.create(2, 'test-cert', 'rush')
        for headers in ({'Origin': 'https://evil.example'}, {'X-Local-App': None}):
            self.assertEqual(self.request(f"/api/attempts/{a['id']}/rush-answer", 'POST',
                                         self.rush_submission(a), headers=headers)[0], 403)

    def test_http_rush_active_export_does_not_reveal_future_answers(self):
        a = self.engine.create(2, 'test-cert', 'rush')
        self.assertEqual(self.request(f"/api/attempts/{a['id']}/export")[0], 409)
        _, profile, _ = self.request('/api/export-profile')
        active = profile['attempts'][0]
        self.assertEqual(len(active['questions']), 1)
        self.assertNotIn('explanation', active['questions'][0])
        self.assertNotIn('feedback', active)

    def test_http_admin_configures_rush_and_export_contains_settings(self):
        settings = self.settings(); settings['rush'] = {'question_count': 3, 'duration_seconds': 120}
        route = '/api/admin/banks/test-cert/configure'
        status, data, _ = self.request(route, 'POST', {'settings': settings, 'enabled': True}, user=1)
        self.assertEqual((status, data['settings']['rush']), (200, settings['rush']))
        self.assertEqual(self.request(route, 'POST', {'settings': settings, 'enabled': True})[0], 403)
        status, archive, _ = self.request('/api/admin/banks/test-cert/export', user=1)
        self.assertEqual(status, 200)
        manifest, _, _, _ = read_archive(archive)
        self.assertEqual(manifest['defaults']['rush'], settings['rush'])

    def test_http_rush_late_post_finishes_without_new_round(self):
        a = self.engine.create(2, 'test-cert', 'rush')
        body = self.rush_submission(a, False)
        self.now[0] = a['deadline']
        status, data, _ = self.request(f"/api/attempts/{a['id']}/rush-answer", 'POST', body)
        self.assertEqual(status, 200)
        self.assertEqual(data['result']['reason'], 'timeout')
        self.assertEqual(data['total'], 10)

    def test_http_rush_draft_route_never_scores(self):
        a = self.engine.create(2, 'test-cert', 'rush')
        status, data, _ = self.request(f"/api/attempts/{a['id']}/answer", 'POST', self.rush_submission(a))
        self.assertEqual((status, data['rush']['correct_count'], data['answered']), (200, 0, 0))

    def test_http_rush_duplicate_submission_is_not_replayed(self):
        a = self.engine.create(2, 'test-cert', 'rush')
        route = f"/api/attempts/{a['id']}/rush-answer"
        body = self.rush_submission(a, False)
        self.assertEqual(self.request(route, 'POST', body)[0], 200)
        status, data, _ = self.request(route, 'POST', body)
        self.assertEqual((status, data['code']), (409, 'revision_conflict'))
        self.assertEqual(data['attempt']['total'], 20)

    def test_http_rush_feedback_get_preserves_explanations(self):
        a = self.engine.create(2, 'test-cert', 'rush')
        _, a, _ = self.request(f"/api/attempts/{a['id']}/rush-answer", 'POST', self.rush_submission(a, False))
        status, fetched, _ = self.request(f"/api/attempts/{a['id']}")
        self.assertEqual(status, 200)
        self.assertEqual(a['feedback'], fetched['feedback'])
        self.assertEqual(a['deadline'], fetched['deadline'])
