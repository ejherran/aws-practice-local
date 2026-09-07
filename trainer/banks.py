"""Versioned question-bank ZIP contract and independent bank repository.

Untrusted ZIP files are inspected and read in memory, NEVER extracted. The
standard-library validator enforces the documented schema and semantic rules.
"""
from copy import deepcopy
import hashlib
import io
import json
import math
import re
import stat
import zipfile
import zlib
from urllib.parse import urlsplit
from .errors import AppError

MAX_ARCHIVE = 10 * 1024 * 1024
MAX_EXPANDED = 40 * 1024 * 1024
MAX_QUESTIONS = 5000
SUPPORTED_LANGUAGES = ('en', 'es')
ID_PATTERN = r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}'
BANK_ID_PATTERN = r'[a-z0-9][a-z0-9-]{1,63}'
VERSION_PATTERN = r'[0-9]+\.[0-9]+\.[0-9]+'


def dump(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def reject_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON key: ' + key)
        result[key] = value
    return result


def parse_json(raw):
    def reject_constant(value):
        raise ValueError('Non-finite JSON number: ' + value)
    return json.loads(raw.decode('utf-8-sig'), object_pairs_hook=reject_duplicates,
                      parse_constant=reject_constant)


def check(condition, path, rule):
    if not condition:
        raise AppError(400, 'invalid_bank', path=path, rule=rule)


def keys(value, required, optional, path):
    check(isinstance(value, dict), path, 'object_required')
    check(set(required) <= set(value), path, 'missing_fields')
    check(set(value) <= set(required) | set(optional), path, 'unknown_fields')


def text(value, path, maximum=20000):
    check(isinstance(value, str) and 0 < len(value) <= maximum and bool(value.strip()), path, 'invalid_text')
    check(not any(0xD800 <= ord(c) <= 0xDFFF or (ord(c) < 32 and c not in '\t\n\r')
                  for c in value), path, 'invalid_characters')


def identifier(value, path, pattern=ID_PATTERN):
    check(isinstance(value, str) and re.fullmatch(pattern, value) is not None,
          path, 'invalid_identifier')


def translated(value, languages, path, maximum=20000):
    keys(value, languages, [], path)
    for language in languages:
        text(value[language], path + '.' + language, maximum)


def integer(value, low, high, path):
    check(type(value) is int and low <= value <= high, path, 'integer_out_of_range')


def validate_settings(settings, question_count, domain_ids):
    keys(settings, ['quiz', 'exam', 'domain_weights'], ['rush'], 'settings')
    for kind in ('quiz', 'exam'):
        mode = settings[kind]
        path = 'settings.' + kind
        keys(mode, ['question_count', 'duration_seconds', 'unscored_count',
                    'time_mode', 'target_percentage'], [], path)
        integer(mode['question_count'], 1, min(500, question_count), path + '.question_count')
        integer(mode['duration_seconds'], 1, 86400, path + '.duration_seconds')
        integer(mode['unscored_count'], 0, mode['question_count'] - 1, path + '.unscored_count')
        check(mode['time_mode'] in (('fixed', 'proportional') if kind == 'quiz' else ('fixed',)),
              path + '.time_mode', 'invalid_time_mode')
        integer(mode['target_percentage'], 0, 100, path + '.target_percentage')
    if 'rush' in settings:
        mode = settings['rush']
        keys(mode, ['question_count', 'duration_seconds'], [], 'settings.rush')
        integer(mode['question_count'], 1, min(500, question_count), 'settings.rush.question_count')
        integer(mode['duration_seconds'], 1, 86400, 'settings.rush.duration_seconds')
    weights = settings['domain_weights']
    keys(weights, domain_ids, [], 'settings.domain_weights')
    for domain_id, weight in weights.items():
        integer(weight, 0, 100, 'settings.domain_weights.' + domain_id)
    check(sum(weights.values()) == 100, 'settings.domain_weights', 'weights_must_sum_100')
    result = deepcopy(settings)
    result.setdefault('rush', {'question_count': min(10, question_count), 'duration_seconds': 600})
    if result['quiz']['time_mode'] == 'proportional':
        exam = result['exam']
        seconds = exam['duration_seconds'] * result['quiz']['question_count'] / exam['question_count']
        result['quiz']['duration_seconds'] = max(1, math.floor(seconds + 0.5))
        integer(result['quiz']['duration_seconds'], 1, 86400, 'settings.quiz.duration_seconds')
    return result


def validate_bank(manifest, questions):
    keys(manifest, ['schema_version', 'bank_id', 'version', 'exam_code', 'title',
                    'description', 'languages', 'default_language', 'domains',
                    'defaults', 'references'], ['content_updated_at'], 'manifest')
    check(type(manifest['schema_version']) is int and manifest['schema_version'] in (1, 2),
          'manifest.schema_version', 'unsupported_schema')
    if manifest['schema_version'] == 1:
        check(isinstance(manifest['defaults'], dict) and 'rush' not in manifest['defaults'],
              'manifest.defaults', 'rush_requires_schema_2')
    identifier(manifest['bank_id'], 'manifest.bank_id', BANK_ID_PATTERN)
    identifier(manifest['version'], 'manifest.version', VERSION_PATTERN)
    text(manifest['exam_code'], 'manifest.exam_code', 80)
    languages = manifest['languages']
    check(isinstance(languages, list) and 1 <= len(languages) <= 2 and
          all(isinstance(x, str) and x in SUPPORTED_LANGUAGES for x in languages) and
          len(set(languages)) == len(languages), 'manifest.languages', 'invalid_languages')
    check(manifest['default_language'] in languages, 'manifest.default_language', 'invalid_language')
    translated(manifest['title'], languages, 'manifest.title', 160)
    translated(manifest['description'], languages, 'manifest.description', 4000)
    if 'content_updated_at' in manifest:
        check(isinstance(manifest['content_updated_at'], str) and
              re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', manifest['content_updated_at']) is not None,
              'manifest.content_updated_at', 'invalid_date')
        from datetime import date
        try:
            date.fromisoformat(manifest['content_updated_at'])
        except (TypeError, ValueError):
            check(False, 'manifest.content_updated_at', 'invalid_date')
    domains = manifest['domains']
    check(isinstance(domains, list) and 1 <= len(domains) <= 30, 'manifest.domains', 'invalid_domains')
    domain_ids = set()
    for i, domain in enumerate(domains):
        path = f'manifest.domains[{i}]'
        keys(domain, ['id', 'name'], [], path)
        identifier(domain['id'], path + '.id')
        check(domain['id'] not in domain_ids, path + '.id', 'duplicate_identifier')
        domain_ids.add(domain['id'])
        translated(domain['name'], languages, path + '.name', 160)
    refs = manifest['references']
    check(isinstance(refs, dict) and len(refs) <= 1000, 'manifest.references', 'invalid_references')
    for key, ref in refs.items():
        identifier(key, 'manifest.references.' + key)
        keys(ref, ['title', 'url'], [], 'manifest.references.' + key)
        translated(ref['title'], languages, 'manifest.references.' + key + '.title', 300)
        check(isinstance(ref['url'], str) and len(ref['url']) <= 2000, 'manifest.references.' + key, 'invalid_url')
        try:
            url = urlsplit(ref['url'])
            port = url.port  # Access validates malformed and out-of-range ports.
            valid = (url.scheme == 'https' and bool(url.hostname) and not url.username and not url.password
                     and not any(c.isspace() or ord(c) < 32 for c in ref['url'])
                     and (port is None or 1 <= port <= 65535))
        except ValueError:
            valid = False
        check(valid, 'manifest.references.' + key + '.url', 'invalid_url')
    check(isinstance(questions, list) and 1 <= len(questions) <= MAX_QUESTIONS,
          'questions', 'invalid_question_count')
    seen = set()
    prompts = {language: set() for language in languages}
    used_domains = set()
    for i, q in enumerate(questions):
        path = f'questions[{i}]'
        keys(q, ['id', 'domain_id', 'select_count', 'prompt', 'explanation', 'options', 'references'],
             ['task_id', 'notes'], path)
        identifier(q['id'], path + '.id')
        check(q['id'] not in seen, path + '.id', 'duplicate_identifier')
        seen.add(q['id'])
        check(isinstance(q['domain_id'], str) and q['domain_id'] in domain_ids,
              path + '.domain_id', 'unknown_domain')
        used_domains.add(q['domain_id'])
        if 'task_id' in q:
            text(q['task_id'], path + '.task_id', 80)
        translated(q['prompt'], languages, path + '.prompt')
        translated(q['explanation'], languages, path + '.explanation')
        if 'notes' in q:
            translated(q['notes'], languages, path + '.notes', 5000)
        for language in languages:
            normalized = ' '.join(q['prompt'][language].casefold().split())
            check(normalized not in prompts[language], path + '.prompt.' + language, 'duplicate_prompt')
            prompts[language].add(normalized)
        options = q['options']
        check(isinstance(options, list) and 2 <= len(options) <= 10, path + '.options', 'invalid_option_count')
        integer(q['select_count'], 1, len(options) - 1, path + '.select_count')
        option_ids = set()
        option_texts = {language: set() for language in languages}
        for j, option in enumerate(options):
            opath = path + f'.options[{j}]'
            keys(option, ['id', 'text', 'explanation', 'correct'], [], opath)
            identifier(option['id'], opath + '.id')
            check(option['id'] not in option_ids, opath + '.id', 'duplicate_identifier')
            option_ids.add(option['id'])
            translated(option['text'], languages, opath + '.text')
            translated(option['explanation'], languages, opath + '.explanation')
            check(type(option['correct']) is bool, opath + '.correct', 'boolean_required')
            for language in languages:
                normalized = ' '.join(option['text'][language].casefold().split())
                check(normalized not in option_texts[language], opath + '.text.' + language, 'duplicate_option')
                option_texts[language].add(normalized)
        check(sum(o['correct'] for o in options) == q['select_count'], path, 'answer_count_mismatch')
        check(isinstance(q['references'], list) and len(q['references']) <= 20 and
              all(isinstance(r, str) and r in refs for r in q['references']),
              path + '.references', 'unknown_reference')
    check(used_domains == domain_ids, 'manifest.domains', 'empty_domain')
    settings = validate_settings(manifest['defaults'], len(questions), domain_ids)
    return settings


def read_archive(raw):
    check(isinstance(raw, bytes) and 0 < len(raw) <= MAX_ARCHIVE, 'archive', 'archive_size')
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            members = archive.infolist()
            names = [member.filename for member in members]
            check(len(names) == 2 and set(names) == {'manifest.json', 'questions.json'},
                  'archive', 'exactly_two_json_files')
            check(sum(m.file_size for m in members) <= MAX_EXPANDED, 'archive', 'expanded_size')
            decoded = {}
            total = 0
            for member in members:
                check(not (member.flag_bits & 1), member.filename, 'encrypted_zip')
                check(member.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED),
                      member.filename, 'unsupported_compression')
                check(not stat.S_ISLNK(member.external_attr >> 16), member.filename, 'symlink_forbidden')
                check(member.file_size <= 500 * max(1, member.compress_size), member.filename, 'compression_ratio')
                with archive.open(member) as stream:
                    data = stream.read(MAX_EXPANDED - total + 1)
                total += len(data)
                check(total <= MAX_EXPANDED, 'archive', 'expanded_size')
                decoded[member.filename] = parse_json(data)
            manifest, questions = decoded['manifest.json'], decoded['questions.json']
            settings = validate_bank(manifest, questions)
            digest = hashlib.sha256(json.dumps([manifest, questions], sort_keys=True,
                                    ensure_ascii=False, allow_nan=False).encode()).hexdigest()
            return manifest, questions, settings, digest
    except AppError:
        raise
    except (ValueError, TypeError, KeyError, RecursionError, OverflowError, zipfile.BadZipFile,
            zlib.error, RuntimeError, NotImplementedError, EOFError) as exc:
        raise AppError(400, 'invalid_bank', path='archive', rule='invalid_zip_or_json') from exc


def make_archive(manifest, questions):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2))
        archive.writestr('questions.json', json.dumps(questions, ensure_ascii=False, indent=2))
    return stream.getvalue()


class BankRepository:
    def __init__(self, storage):
        self.storage = storage

    @staticmethod
    def current(con, bank_id, allow_disabled=False):
        row = con.execute('''SELECT b.*, v.manifest, v.questions, v.imported_at FROM banks b
              JOIN bank_versions v ON v.bank_id=b.id AND v.version=b.current_version WHERE b.id=?''',
                          (bank_id,)).fetchone()
        if not row or (not row['enabled'] and not allow_disabled):
            raise AppError(404, 'bank_unavailable')
        return row

    @staticmethod
    def summary(row):
        manifest = json.loads(row['manifest'])
        return {'id': row['id'], 'version': row['current_version'], 'enabled': bool(row['enabled']),
                'manifest': manifest, 'settings': validate_settings(json.loads(row['settings']),
                    len(json.loads(row['questions'])), {d['id'] for d in manifest['domains']}),
                'question_count': len(json.loads(row['questions'])), 'imported_at': row['imported_at']}

    def list(self, admin=False):
        with self.storage.connection() as con:
            rows = con.execute('''SELECT b.*, v.manifest, v.questions, v.imported_at FROM banks b
                   JOIN bank_versions v ON v.bank_id=b.id AND v.version=b.current_version
                   ORDER BY b.id''').fetchall()
            return [self.summary(row) for row in rows if admin or row['enabled']]

    def import_archive(self, raw, user_id=None, replace=False, dry_run=False):
        manifest, questions, settings, digest = read_archive(raw)
        bank_id, version = manifest['bank_id'], manifest['version']
        with self.storage.connection() as con:
            existing = con.execute('SELECT current_version FROM banks WHERE id=?', (bank_id,)).fetchone()
            duplicate = con.execute('SELECT 1 FROM bank_versions WHERE bank_id=? AND version=?',
                                    (bank_id, version)).fetchone()
            if duplicate:
                raise AppError(409, 'version_exists')
            preview = {'bank_id': bank_id, 'version': version, 'title': manifest['title'],
                       'question_count': len(questions), 'languages': manifest['languages'],
                       'replaces': existing['current_version'] if existing else None, 'settings': settings}
            if dry_run:
                return preview
            if existing and not replace:
                raise AppError(409, 'replacement_confirmation_required')
            con.execute('INSERT INTO bank_versions VALUES(?,?,?,?,?,?)',
                        (bank_id, version, dump(manifest), dump(questions), digest, self.storage.clock()))
            if existing:
                con.execute('UPDATE banks SET current_version=?,settings=? WHERE id=?',
                            (version, dump(settings), bank_id))
            else:
                con.execute('INSERT INTO banks(id,current_version,settings) VALUES(?,?,?)',
                            (bank_id, version, dump(settings)))
            con.execute('INSERT INTO audit(user_id,action,bank_id,details,created_at) VALUES(?,?,?,?,?)',
                        (user_id, 'bank_import', bank_id, dump(preview), self.storage.clock()))
            return preview

    def configure(self, bank_id, settings, enabled, user_id):
        check(type(enabled) is bool, 'enabled', 'boolean_required')
        with self.storage.connection() as con:
            row = self.current(con, bank_id, allow_disabled=True)
            manifest = json.loads(row['manifest'])
            settings = validate_settings(settings, len(json.loads(row['questions'])),
                                         {d['id'] for d in manifest['domains']})
            con.execute('UPDATE banks SET settings=?,enabled=? WHERE id=?', (dump(settings), enabled, bank_id))
            con.execute('INSERT INTO audit(user_id,action,bank_id,details,created_at) VALUES(?,?,?,?,?)',
                        (user_id, 'bank_configure', bank_id, dump({'settings': settings, 'enabled': enabled}),
                         self.storage.clock()))
            return self.summary(self.current(con, bank_id, allow_disabled=True))

    def export(self, bank_id):
        with self.storage.connection() as con:
            row = self.current(con, bank_id, allow_disabled=True)
            manifest = json.loads(row['manifest'])
            # Export current administrator settings, not stale import defaults.
            manifest['schema_version'] = 2
            manifest['defaults'] = self.summary(row)['settings']
            return make_archive(manifest, json.loads(row['questions']))
