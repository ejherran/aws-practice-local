"""LAN-only HTTP adapter. No third-party dependencies or outbound calls."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
import logging
from pathlib import Path
import socket
import threading
from urllib.parse import parse_qs, urlsplit
from . import __version__
from .auth import SESSION_SECONDS, COOKIE_NAME
from .banks import MAX_ARCHIVE, dump, parse_json
from .errors import AppError

LOG = logging.getLogger('practice')


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, trainer, access, web_dir, schema_path, secure=False):
        self.trainer, self.access = trainer, access
        self.web_dir, self.schema_path = Path(web_dir), Path(schema_path)
        self.secure = secure
        self.slots = threading.BoundedSemaphore(32)
        super().__init__(address, Handler)

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()


class Handler(BaseHTTPRequestHandler):
    server_version = 'LocalPractice/4.0'
    sys_version = ''
    timeout = 15

    def setup(self):
        super().setup()
        self.connection.settimeout(self.timeout)

    def log_message(self, fmt, *args):
        LOG.debug('%s %s', self.client_address[0], fmt % args)

    def send(self, status, data, content_type='application/json; charset=utf-8', headers=None):
        if not isinstance(data, bytes):
            data = dump(data).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
        self.send_header('Permissions-Policy', 'camera=(), microphone=(), geolocation=()')
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(data)

    def session_cookie(self, token):
        return (f'{COOKIE_NAME}={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age={SESSION_SECONDS}'
                + ('; Secure' if self.server.secure else ''))

    def check_host(self):
        host = self.headers.get('Host', '')
        try:
            parsed = urlsplit('//' + host)
            name, port = parsed.hostname, parsed.port
            if parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment or not name:
                raise ValueError()
            try:
                ip = ipaddress.ip_address(name)
                allowed = ip.is_private or ip.is_loopback
            except ValueError:
                allowed = name in {'localhost', socket.gethostname().lower(), self.server.server_address[0].lower()} or name.endswith('.local')
            if not allowed or port not in (None, self.server.server_port):
                raise ValueError()
        except ValueError:
            raise AppError(403, 'host_forbidden')

    def read_body(self, zipped=False):
        if self.headers.get('Transfer-Encoding'):
            raise AppError(400, 'invalid_request')
        if self.headers.get_content_type() != ('application/zip' if zipped else 'application/json'):
            raise AppError(415, 'invalid_content_type')
        if self.headers.get('X-Local-App') != '1':
            raise AppError(403, 'origin_forbidden')
        origin = self.headers.get('Origin')
        scheme = 'https' if self.server.secure else 'http'
        if origin and origin != f"{scheme}://{self.headers.get('Host')}":
            raise AppError(403, 'origin_forbidden')
        if self.headers.get('Sec-Fetch-Site') == 'cross-site':
            raise AppError(403, 'origin_forbidden')
        try:
            size = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            raise AppError(400, 'invalid_request')
        if not 0 < size <= (MAX_ARCHIVE if zipped else 65536):
            raise AppError(413, 'request_too_large')
        raw = self.rfile.read(size)
        if len(raw) != size:
            raise AppError(400, 'invalid_request')
        if zipped:
            return raw
        try:
            body = parse_json(raw)
        except (ValueError, UnicodeError, RecursionError):
            raise AppError(400, 'invalid_json')
        if not isinstance(body, dict):
            raise AppError(400, 'invalid_json')
        return body

    def route(self):
        self.check_host()
        parsed = urlsplit(self.path)
        path, params = parsed.path, parse_qs(parsed.query)
        get = self.command in ('GET', 'HEAD')
        static = {'/': ('index.html', 'text/html; charset=utf-8'),
                  '/index.html': ('index.html', 'text/html; charset=utf-8'),
                  '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
                  '/styles.css': ('styles.css', 'text/css; charset=utf-8'),
                  '/favicon.svg': ('favicon.svg', 'image/svg+xml'),
                  '/locales/en.json': ('locales/en.json', 'application/json; charset=utf-8'),
                  '/locales/es.json': ('locales/es.json', 'application/json; charset=utf-8')}
        if get and path in static:
            name, content_type = static[path]
            return self.send(200, (self.server.web_dir / name).read_bytes(), content_type)
        access, trainer = self.server.access, self.server.trainer
        user = access.authenticated(self.headers.get('Cookie'))
        if get and path == '/api/session':
            return self.send(200, {'authenticated': user is not None, 'user': user,
                                  'registration_open': access.registration_open, 'version': __version__})
        if self.command == 'POST' and path in ('/api/login', '/api/register'):
            body = self.read_body()
            if path == '/api/login':
                token, user = access.login(body.get('username'), body.get('password'), self.client_address[0])
            else:
                token, user = access.register(body.get('username'), body.get('password'), body.get('display_name'),
                                              body.get('language', 'es'), self.client_address[0])
            return self.send(200, {'user': user}, headers={'Set-Cookie': self.session_cookie(token)})
        if not user:
            raise AppError(401, 'sign_in_required')
        expected = self.headers.get('X-Profile-ID')
        if (expected is not None and expected != str(user['id'])) or (not get and expected is None):
            raise AppError(409, 'profile_changed')
        user_id = user['id']
        if path.startswith('/api/admin/') and user['role'] != 'admin':
            raise AppError(403, 'admin_required')
        if path == '/api/profile':
            if get:
                return self.send(200, {'user': user})
            body = self.read_body()
            return self.send(200, {'user': access.edit_profile(user_id, body.get('display_name'), body.get('language'))})
        if self.command == 'POST' and path == '/api/password':
            body = self.read_body()
            token = access.change_password(user_id, body.get('current_password'), body.get('new_password'), self.client_address[0])
            return self.send(200, {'ok': True}, headers={'Set-Cookie': self.session_cookie(token)})
        if self.command == 'POST' and path == '/api/logout':
            self.read_body()
            access.logout(self.headers.get('Cookie'))
            return self.send(200, {'ok': True}, headers={'Set-Cookie': f'{COOKIE_NAME}=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0'})
        if get and path == '/api/dashboard':
            return self.send(200, trainer.dashboard(user_id))
        if get and path == '/api/banks':
            return self.send(200, {'banks': trainer.banks.list()})
        if get and path == '/api/history':
            try:
                offset, limit = int(params.get('offset', ['0'])[0]), int(params.get('limit', ['25'])[0])
            except ValueError:
                raise AppError(400, 'invalid_pagination')
            return self.send(200, trainer.history(user_id, params.get('bank_id', [''])[0],
                                                 params.get('kind', ['all'])[0], offset, limit))
        if get and path == '/api/export-profile':
            return self.send(200, trainer.export_profile(user_id), headers={
                'Content-Disposition': f'attachment; filename="profile-{user["username"]}.json"'})
        if self.command == 'POST' and path == '/api/attempts':
            body = self.read_body()
            return self.send(201, trainer.create(user_id, body.get('bank_id'), body.get('kind')))
        parts = path.strip('/').split('/')
        if len(parts) in (3, 4) and parts[:2] == ['api', 'attempts']:
            attempt_id = parts[2]
            if len(attempt_id) != 24 or any(c not in '0123456789abcdef' for c in attempt_id):
                raise AppError(404, 'attempt_not_found')
            if get and len(parts) == 3:
                return self.send(200, trainer.fetch(user_id, attempt_id))
            if get and len(parts) == 4 and parts[3] == 'export':
                attempt = trainer.fetch(user_id, attempt_id)
                if attempt['status'] == 'active':
                    raise AppError(409, 'attempt_not_finished')
                return self.send(200, attempt, headers={'Content-Disposition': f'attachment; filename="result-{attempt_id}.json"'})
            if self.command == 'POST' and len(parts) == 4:
                body = self.read_body()
                if parts[3] == 'answer':
                    return self.send(200, trainer.update(user_id, attempt_id, body))
                if parts[3] in ('rush-answer', 'rush-continue'):
                    return self.send(200, trainer.rush_action(user_id, attempt_id, body,
                                     'answer' if parts[3] == 'rush-answer' else 'continue'))
                if parts[3] == 'finish':
                    return self.send(200, trainer.finish(user_id, attempt_id, body.get('revision')))
        if get and path == '/api/schema.zip':
            return self.send(200, self.server.schema_path.read_bytes(), 'application/zip',
                             {'Content-Disposition': 'attachment; filename="question-bank-authoring-kit.zip"'})
        if get and path == '/api/admin/banks':
            return self.send(200, {'banks': trainer.banks.list(admin=True)})
        if self.command == 'POST' and path in ('/api/admin/banks/validate', '/api/admin/banks/import'):
            raw = self.read_body(zipped=True)
            return self.send(200, trainer.banks.import_archive(raw, user_id, replace=params.get('replace') == ['1'],
                                                             dry_run=path.endswith('/validate')))
        if len(parts) == 5 and parts[:3] == ['api', 'admin', 'banks']:
            bank_id, action = parts[3:]
            if get and action == 'export':
                raw = trainer.banks.export(bank_id)
                return self.send(200, raw, 'application/zip', {'Content-Disposition': f'attachment; filename="{bank_id}.zip"'})
            if self.command == 'POST' and action == 'configure':
                body = self.read_body()
                return self.send(200, trainer.banks.configure(bank_id, body.get('settings'), body.get('enabled'), user_id))
        if get and path == '/api/admin/audit':
            with trainer.storage.connection() as con:
                rows = con.execute('''SELECT a.action,a.bank_id,a.details,a.created_at,u.username FROM audit a
                                    LEFT JOIN users u ON a.user_id=u.id ORDER BY a.id DESC LIMIT 100''').fetchall()
                return self.send(200, {'items': [dict(row) for row in rows]})
        raise AppError(404, 'not_found')

    def dispatch(self):
        try:
            self.route()
        except AppError as exc:
            self.send(exc.status, {'code': exc.code, **exc.details})
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            pass
        except Exception:
            LOG.exception('Request failed')
            try:
                self.send(500, {'code': 'internal_error'})
            except (BrokenPipeError, ConnectionResetError):
                pass

    do_GET = dispatch
    do_HEAD = dispatch
    do_POST = dispatch
