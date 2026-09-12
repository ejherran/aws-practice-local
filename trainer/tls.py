"""Local TLS certificates using Python's existing OpenSSL, via stdlib ctypes.

All key generation, signing and PEM encoding run in OpenSSL. No cryptographic
algorithm is implemented here and no external command or package is needed.
"""
import _ssl
from contextlib import ExitStack
import ctypes as C
import hashlib
import ipaddress
import os
from pathlib import Path
import re
import secrets
import socket
import ssl
import tempfile
import time


def _crypto():
    # On POSIX, dlsym on _ssl also searches its linked libraries. On Windows,
    # load only the DLL shipped alongside this interpreter (never from PATH).
    module = Path(_ssl.__file__).resolve()
    candidates = sorted(module.parent.glob('libcrypto*.dll')) if os.name == 'nt' else [module]
    for candidate in candidates:
        try:
            lib = C.CDLL(str(candidate))
            lib.OpenSSL_version_num.restype = C.c_ulong
            if lib.OpenSSL_version_num() == ssl.OPENSSL_VERSION_NUMBER:
                return lib
        except (OSError, AttributeError):
            continue
    raise ValueError('Cannot access the OpenSSL library used by this Python. '
                     'Use a standard CPython installation or supply --cert-file and --key-file.')


def _bind(lib, name, result, *arguments):
    function = getattr(lib, name)
    function.restype, function.argtypes = result, list(arguments)
    return function


def certificate_names(host, addresses=()):
    names = {'DNS:localhost', 'IP:127.0.0.1', 'IP:::1'}
    for value in (socket.gethostname(), host, *addresses):
        try:
            address = ipaddress.ip_address(value)
            if not address.is_unspecified:
                names.add('IP:' + str(address))
        except ValueError:
            value = value.rstrip('.').lower()
            if len(value) > 253 or not all(re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?',
                                                       label) for label in value.split('.')):
                raise ValueError('Invalid TLS hostname. Use an IP address or an ASCII DNS name.')
            names.add('DNS:' + value)
    return sorted(names)


def _generate(names):
    lib = _crypto()
    ptr, integer = C.c_void_p, C.c_int
    with ExitStack() as resources:
        def owned(value, free_name):
            if not value:
                raise ValueError('OpenSSL could not create the local TLS certificate.')
            resources.callback(_bind(lib, free_name, None, ptr), value)
            return value

        def check(value):
            if value <= 0:
                raise ValueError('OpenSSL could not generate or sign the local TLS certificate.')
            return value

        # EVP_PKEY_RSA; the EVP interface delegates randomness and RSA to OpenSSL.
        ctx = owned(_bind(lib, 'EVP_PKEY_CTX_new_id', ptr, integer, ptr)(6, None), 'EVP_PKEY_CTX_free')
        check(_bind(lib, 'EVP_PKEY_keygen_init', integer, ptr)(ctx))
        check(_bind(lib, 'EVP_PKEY_CTX_ctrl_str', integer, ptr, C.c_char_p, C.c_char_p)(
            ctx, b'rsa_keygen_bits', b'3072'))
        key = ptr()
        check(_bind(lib, 'EVP_PKEY_keygen', integer, ptr, C.POINTER(ptr))(ctx, C.byref(key)))
        owned(key, 'EVP_PKEY_free')
        cert = owned(_bind(lib, 'X509_new', ptr)(), 'X509_free')
        check(_bind(lib, 'X509_set_version', integer, ptr, C.c_long)(cert, 2))
        serial = _bind(lib, 'X509_get_serialNumber', ptr, ptr)(cert)
        serial_bytes = (secrets.randbits(159) or 1).to_bytes(20, 'big')
        serial_bn = owned(_bind(lib, 'BN_bin2bn', ptr, C.c_char_p, integer, ptr)(
            serial_bytes, 20, None), 'BN_free')
        check(_bind(lib, 'BN_to_ASN1_INTEGER', ptr, ptr, ptr)(serial_bn, serial) or 0)
        adjust = _bind(lib, 'X509_gmtime_adj', ptr, ptr, C.c_long)
        check(adjust(_bind(lib, 'X509_getm_notBefore', ptr, ptr)(cert), -300) or 0)
        check(adjust(_bind(lib, 'X509_getm_notAfter', ptr, ptr)(cert), 365 * 86400) or 0)
        check(_bind(lib, 'X509_set_pubkey', integer, ptr, ptr)(cert, key))
        subject = _bind(lib, 'X509_get_subject_name', ptr, ptr)(cert)
        check(_bind(lib, 'X509_NAME_add_entry_by_txt', integer, ptr, C.c_char_p, integer,
                    C.c_char_p, integer, integer, integer)(
                        subject, b'CN', 0x1001, b'AWS Practice Local', -1, -1, 0))
        check(_bind(lib, 'X509_set_issuer_name', integer, ptr, ptr)(cert, subject))
        extension = _bind(lib, 'X509V3_EXT_conf_nid', ptr, ptr, ptr, integer, C.c_char_p)
        for nid, value in ((87, 'critical,CA:FALSE'), (83, 'critical,digitalSignature,keyEncipherment'),
                           (126, 'serverAuth'), (85, ','.join(names))):
            ext = owned(extension(None, None, nid, value.encode('ascii')), 'X509_EXTENSION_free')
            check(_bind(lib, 'X509_add_ext', integer, ptr, ptr, integer)(cert, ext, -1))
        digest = _bind(lib, 'EVP_sha256', ptr)()
        check(_bind(lib, 'X509_sign', integer, ptr, ptr, ptr)(cert, key, digest))

        def pem(value, private=False):
            bio = owned(_bind(lib, 'BIO_new', ptr, ptr)(_bind(lib, 'BIO_s_mem', ptr)()), 'BIO_free')
            if private:
                check(_bind(lib, 'PEM_write_bio_PrivateKey', integer, ptr, ptr, ptr,
                            ptr, integer, ptr, ptr)(bio, value, None, None, 0, None, None))
            else:
                check(_bind(lib, 'PEM_write_bio_X509', integer, ptr, ptr)(bio, value))
            size = _bind(lib, 'BIO_ctrl_pending', C.c_size_t, ptr)(bio)
            if not 0 < size < 65536:
                raise ValueError('Unexpected certificate encoding size.')
            buffer = C.create_string_buffer(size)
            if _bind(lib, 'BIO_read', integer, ptr, ptr, integer)(bio, buffer, size) != size:
                raise ValueError('Could not encode the local TLS certificate.')
            return buffer.raw

        return pem(cert), pem(key, private=True)


def _protect_directory(path):
    if os.name != 'nt':
        path.chmod(0o700)
        return
    # Protect private material before writing it. Windows chmod alone does not
    # restrict access; this DACL grants access only to the owner and SYSTEM.
    advapi, kernel = C.WinDLL('advapi32', use_last_error=True), C.WinDLL('kernel32', use_last_error=True)
    descriptor, dacl = C.c_void_p(), C.c_void_p()
    convert = _bind(advapi, 'ConvertStringSecurityDescriptorToSecurityDescriptorW', C.c_int,
                    C.c_wchar_p, C.c_ulong, C.POINTER(C.c_void_p), C.c_void_p)
    if not convert('D:P(A;OICI;FA;;;SY)(A;OICI;FA;;;OW)', 1, C.byref(descriptor), None):
        raise C.WinError(C.get_last_error())
    try:
        present, defaulted = C.c_int(), C.c_int()
        get_dacl = _bind(advapi, 'GetSecurityDescriptorDacl', C.c_int, C.c_void_p,
                         C.POINTER(C.c_int), C.POINTER(C.c_void_p), C.POINTER(C.c_int))
        if not get_dacl(descriptor, C.byref(present), C.byref(dacl), C.byref(defaulted)):
            raise C.WinError(C.get_last_error())
        set_info = _bind(advapi, 'SetNamedSecurityInfoW', C.c_ulong, C.c_wchar_p, C.c_int,
                         C.c_ulong, C.c_void_p, C.c_void_p, C.c_void_p, C.c_void_p)
        status = set_info(str(path), 1, 0x80000004, None, None, dacl, None)
        if status:
            raise C.WinError(status)
    finally:
        _bind(kernel, 'LocalFree', C.c_void_p, C.c_void_p)(descriptor)


def load_context(cert_path, key_path):
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    # An encrypted key must fail unattended startup instead of prompting.
    context.load_cert_chain(cert_path, key_path, password=lambda: '')
    info = _ssl._test_decode_cert(str(cert_path))
    now = time.time()
    if not ssl.cert_time_to_seconds(info['notBefore']) <= now < ssl.cert_time_to_seconds(info['notAfter']):
        raise ValueError('TLS certificate is expired or not yet valid. Replace it before starting.')
    if not info.get('subjectAltName'):
        raise ValueError('TLS certificate must include subject alternative names (SAN).')
    return context


def ensure_certificate(data_dir, host, addresses=(), cert_file=None, key_file=None):
    """Create once, reuse unchanged, and fail closed for incomplete/invalid pairs."""
    if bool(cert_file) != bool(key_file):
        raise ValueError('--cert-file and --key-file must be supplied together.')
    if cert_file:
        cert, key = Path(cert_file).resolve(), Path(key_file).resolve()
        context = load_context(cert, key)
        return context, cert, False
    directory = Path(data_dir).resolve() / 'tls'
    cert, key = directory / 'server-cert.pem', directory / 'server-key.pem'
    if directory.exists():
        if not cert.is_file() or not key.is_file():
            raise ValueError(f'Incomplete TLS identity in {directory}. Restore both PEM files or '
                             'move this directory aside to generate a new identity.')
        return load_context(cert, key), cert, False
    directory.parent.mkdir(parents=True, exist_ok=True)
    # Validate both staged files before publishing; never replace an identity.
    with tempfile.TemporaryDirectory(prefix='.tls-', dir=directory.parent) as staging:
        temporary = Path(staging)
        _protect_directory(temporary)
        cert_pem, key_pem = _generate(certificate_names(host, addresses))
        for name, content in ((key.name, key_pem), (cert.name, cert_pem)):
            descriptor = os.open(temporary / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, 'wb') as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
        context = load_context(temporary / cert.name, temporary / key.name)
        # mkdir acts as an exclusive startup lock. Interrupted publication leaves
        # an incomplete identity that fails closed on the next startup.
        directory.mkdir(mode=0o700)
        _protect_directory(directory)
        os.rename(temporary / key.name, key)
        os.rename(temporary / cert.name, cert)
    return context, cert, True


def fingerprint(cert):
    der = ssl.PEM_cert_to_DER_cert(Path(cert).read_text(encoding='ascii'))
    return ':'.join(f'{byte:02X}' for byte in hashlib.sha256(der).digest())
