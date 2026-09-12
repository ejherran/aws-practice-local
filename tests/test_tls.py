"""Generated TLS identities, fail-closed startup and real verified handshakes."""
import _ssl
import io
from pathlib import Path
import ssl
import tempfile
import unittest
from unittest.mock import patch
from contextlib import redirect_stdout, redirect_stderr
import app
from trainer.tls import certificate_names, ensure_certificate, fingerprint, load_context


class CertificateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def test_generates_identity_and_reuses_without_rewriting(self):
        context, cert, created = ensure_certificate(self.directory, '0.0.0.0', ['192.168.1.20'])
        self.assertTrue(created)
        self.assertEqual(context.minimum_version, ssl.TLSVersion.TLSv1_2)
        files = {path.name: path.read_bytes() for path in cert.parent.iterdir()}
        info = _ssl._test_decode_cert(str(cert))
        for item in [('DNS', 'localhost'), ('IP Address', '127.0.0.1'), ('IP Address', '192.168.1.20')]:
            self.assertIn(item, info['subjectAltName'])
        self.assertLessEqual(len(info['serialNumber']), 40)
        self.assertEqual(len(fingerprint(cert).split(':')), 32)
        with patch('trainer.tls._generate', side_effect=AssertionError('must reuse')):
            self.assertFalse(ensure_certificate(self.directory, '0.0.0.0')[2])
        self.assertEqual(files, {path.name: path.read_bytes() for path in cert.parent.iterdir()})

    def test_different_installations_have_different_keys(self):
        _, one, _ = ensure_certificate(self.directory / 'one', 'localhost')
        _, two, _ = ensure_certificate(self.directory / 'two', 'localhost')
        self.assertNotEqual(fingerprint(one), fingerprint(two))
        self.assertNotEqual((one.parent / 'server-key.pem').read_bytes(),
                            (two.parent / 'server-key.pem').read_bytes())

    def test_incomplete_pair_is_not_overwritten(self):
        directory = self.directory / 'tls'
        directory.mkdir()
        cert = directory / 'server-cert.pem'
        cert.write_text('existing identity', encoding='ascii')
        with self.assertRaisesRegex(ValueError, 'Incomplete TLS identity'):
            ensure_certificate(self.directory, 'localhost')
        self.assertEqual(cert.read_text(encoding='ascii'), 'existing identity')

    def test_missing_custom_pair_does_not_generate_anything(self):
        with self.assertRaises(OSError):
            ensure_certificate(self.directory, 'localhost', cert_file=self.directory / 'missing.pem',
                               key_file=self.directory / 'missing-key.pem')
        self.assertFalse((self.directory / 'tls').exists())

    def test_existing_custom_pair_can_be_loaded_without_generator(self):
        _, cert, _ = ensure_certificate(self.directory, 'localhost')
        with patch('trainer.tls._crypto', side_effect=AssertionError('not needed')):
            context, _, created = ensure_certificate(self.directory, 'localhost', cert_file=cert,
                                                     key_file=cert.parent / 'server-key.pem')
        self.assertFalse(created)
        self.assertEqual(context.protocol, ssl.PROTOCOL_TLS_SERVER)

    def test_expired_certificate_fails_closed(self):
        _, cert, _ = ensure_certificate(self.directory, 'localhost')
        info = _ssl._test_decode_cert(str(cert))
        with patch('trainer.tls.time.time', return_value=ssl.cert_time_to_seconds(info['notAfter']) + 1):
            with self.assertRaisesRegex(ValueError, 'expired'):
                load_context(cert, cert.parent / 'server-key.pem')

    def test_generation_failure_does_not_publish_identity(self):
        with patch('trainer.tls._generate', side_effect=ValueError('provider unavailable')):
            with self.assertRaises(ValueError):
                ensure_certificate(self.directory, 'localhost')
        self.assertFalse((self.directory / 'tls').exists())
        self.assertEqual(list(self.directory.iterdir()), [])

    def test_invalid_names_rejected_without_config_injection(self):
        for value in ['localhost,DNS:evil.test', 'bad\nname', '*.example.com', 'a' * 64]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                certificate_names(value)

    def test_startup_always_supplies_tls_and_reuses_on_restart(self):
        from trainer.server import LocalServer
        from trainer.auth import Access
        from trainer.storage import Storage
        arguments = ['--host', '127.0.0.1', '--port', '18443', '--data-dir', str(self.directory),
                     '--no-starter-banks']
        with patch.object(LocalServer, 'serve_forever'), redirect_stdout(io.StringIO()) as output:
            self.assertEqual(app.main(arguments), 0)
        self.assertIn('https://127.0.0.1:18443', output.getvalue())
        self.assertNotIn('http://', output.getvalue())
        cert = self.directory / 'tls/server-cert.pem'
        before = fingerprint(cert)
        access = Access(Storage(self.directory / 'practice.sqlite3'))
        access.reset_password('Admin', 'Preserved-local-password')
        with patch.object(LocalServer, 'serve_forever'), redirect_stdout(io.StringIO()):
            self.assertEqual(app.main(arguments), 0)
        self.assertEqual(fingerprint(cert), before)
        self.assertEqual(access.login('Admin', 'Preserved-local-password')[1]['id'], 1)

    def test_tls_failure_does_not_open_listener(self):
        with patch('app.ensure_certificate', side_effect=ValueError('TLS unavailable')), \
                patch('app.LocalServer') as server, redirect_stderr(io.StringIO()):
            result = app.main(['--data-dir', str(self.directory), '--no-starter-banks'])
        self.assertEqual(result, 1)
        server.assert_not_called()
