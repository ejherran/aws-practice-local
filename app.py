#!/usr/bin/env python3
"""Run the local certification trainer with Python 3.10+ and no pip install."""
import argparse
import getpass
import logging
from pathlib import Path
import socket
import sqlite3
import ssl
import sys
import threading
from trainer import __version__
from trainer.auth import Access
from trainer.banks import BankRepository, read_archive
from trainer.engine import Trainer
from trainer.errors import AppError
from trainer.server import LocalServer
from trainer.storage import Storage

BASE_DIR = Path(__file__).resolve().parent
LOG = logging.getLogger('practice')


def local_addresses():
    addresses = set()
    try:
        for entry in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            if not entry[4][0].startswith('127.'):
                addresses.add(entry[4][0])
    except OSError:
        pass
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            # Route lookup only. UDP connect sends no packet and needs no service.
            sock.connect(('192.0.2.1', 9))
            address = sock.getsockname()[0]
            if not address.startswith('127.'):
                addresses.add(address)
    except OSError:
        pass
    return sorted(addresses)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Offline, multi-user certification practice server.')
    parser.add_argument('--host', default='0.0.0.0', help='IPv4 interface (default: entire LAN).')
    parser.add_argument('--port', type=int, default=8080, help='HTTP(S) port (default: 8080).')
    parser.add_argument('--data-dir', type=Path, default=BASE_DIR / 'data', help='Local database directory.')
    parser.add_argument('--banks-dir', type=Path, default=BASE_DIR / 'banks', help='Starter-bank ZIP directory.')
    parser.add_argument('--no-starter-banks', action='store_true', help='Skip starter-bank installation; retain any existing catalog.')
    parser.add_argument('--disable-registration', action='store_true', help='Disallow new learner profiles.')
    parser.add_argument('--reset-password', metavar='USERNAME', help='Reset a password locally and exit.')
    parser.add_argument('--validate-bank', type=Path, help='Validate a bank ZIP without changing the database.')
    parser.add_argument('--cert-file', type=Path, help='Optional PEM certificate for HTTPS.')
    parser.add_argument('--key-file', type=Path, help='Optional PEM private key for HTTPS.')
    parser.add_argument('--verbose', action='store_true', help='Log HTTP requests.')
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format='%(levelname)s: %(message)s')
    if not 1 <= args.port <= 65535:
        parser.error('Port must be between 1 and 65535.')
    if bool(args.cert_file) != bool(args.key_file):
        parser.error('--cert-file and --key-file must be supplied together.')
    try:
        if args.validate_bank:
            manifest, questions, _, _ = read_archive(args.validate_bank.read_bytes())
            print(f"VALID: {manifest['bank_id']} {manifest['version']} | {len(questions)} questions | {', '.join(manifest['languages'])}")
            return 0
        storage = Storage(args.data_dir.resolve() / 'practice.sqlite3')
        access = Access(storage, registration_open=not args.disable_registration)
        created_admin = access.bootstrap_admin()
        if args.reset_password:
            password = getpass.getpass('New password (8-128 characters): ')
            if password != getpass.getpass('Repeat password: '):
                raise ValueError('Passwords do not match.')
            access.reset_password(args.reset_password, password)
            print('Password updated. Existing sessions were revoked; progress was preserved.')
            return 0
        banks = BankRepository(storage)
        if not args.no_starter_banks:
            # Startup only installs previously unknown bank IDs. It never reverts
            # a newer version, imports an update, or overrides admin settings.
            existing = {bank['id'] for bank in banks.list(admin=True)}
            for path in sorted(args.banks_dir.glob('*.zip')):
                raw = path.read_bytes()
                manifest, _, _, _ = read_archive(raw)
                if manifest['bank_id'] not in existing:
                    banks.import_archive(raw)
                    existing.add(manifest['bank_id'])
        trainer = Trainer(storage, banks)
        server = LocalServer((args.host, args.port), trainer, access, BASE_DIR / 'web',
                             BASE_DIR / 'schema' / 'question-bank-authoring-kit.zip', secure=bool(args.cert_file))
        if args.cert_file:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            context.load_cert_chain(args.cert_file, args.key_file)
            server.socket = context.wrap_socket(server.socket, server_side=True)
    except (OSError, ValueError, sqlite3.Error, AppError, EOFError) as exc:
        print(f'Startup failed: {exc}', file=sys.stderr)
        if isinstance(exc, AppError):
            print(exc.details, file=sys.stderr)
        return 1
    stop = threading.Event()

    def sweep():
        while not stop.wait(1):
            try:
                trainer.sweep()
            except Exception:
                LOG.exception('Deadline sweep failed')

    worker = threading.Thread(target=sweep, name='deadline-sweeper', daemon=True)
    worker.start()
    scheme = 'https' if args.cert_file else 'http'
    print(f'\n  AWS Practice Local {__version__} | {len(banks.list())} active bank(s)')
    print(f'  This computer: {scheme}://127.0.0.1:{args.port}')
    if args.host == '0.0.0.0':
        for address in local_addresses():
            print(f'  Local network: {scheme}://{address}:{args.port}')
    else:
        print(f'  Listening: {scheme}://{args.host}:{args.port}')
    if created_admin:
        print('  Initial Admin profile created. See README.md for the initial credentials; change the password.')
    print(f'  Data: {storage.path}')
    print('  Use a trusted LAN only. Do not expose this server to the Internet.')
    if not args.cert_file:
        print('  HTTP is unencrypted. Use unique passwords for this application.')
    print('  Keep this computer running. Ctrl+C stops the server.\n', flush=True)
    try:
        server.serve_forever(poll_interval=0.3)
    except KeyboardInterrupt:
        print('\nStopped. Confirmed progress is stored locally.')
    finally:
        stop.set()
        worker.join(timeout=2)
        server.server_close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
