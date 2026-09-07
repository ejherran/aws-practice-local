"""Question-bank contract and immutable repository tests."""
from copy import deepcopy
import io
import json
import stat
import zipfile
import unittest
from trainer.banks import (MAX_ARCHIVE, BankRepository, make_archive, parse_json,
                           read_archive, validate_bank, validate_settings)
from trainer.errors import AppError
from tests.helpers import ROOT, Fixture, bank_data


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.manifest, self.questions = bank_data()

    def invalid(self, manifest=None, questions=None):
        with self.assertRaises(AppError) as error:
            read_archive(make_archive(manifest if manifest is not None else self.manifest,
                                      questions if questions is not None else self.questions))
        self.assertEqual(error.exception.code, 'invalid_bank')

    def test_round_trip(self):
        m, q, settings, digest = read_archive(make_archive(self.manifest, self.questions))
        self.assertEqual(m, self.manifest)
        self.assertEqual(q, self.questions)
        self.assertEqual(settings['quiz']['duration_seconds'], 300)
        self.assertEqual(len(digest), 64)

    def test_bundled_bank_all_bilingual_content(self):
        m, q, s, _ = read_archive((ROOT / 'banks/aws-clf-c02-3.0.0.zip').read_bytes())
        self.assertEqual(len(q), 260)
        self.assertEqual(sum(len(x['options']) for x in q), 1093)
        self.assertEqual(sum(x['select_count'] == 2 for x in q), 53)
        self.assertEqual(m['languages'], ['en', 'es'])
        self.assertEqual(s['quiz']['duration_seconds'], 831)
        self.assertEqual(s['exam']['unscored_count'], 15)
        for question in q:
            if question['select_count'] > 1:
                self.assertIn('TWO', question['prompt']['en'])
                self.assertIn('DOS', question['prompt']['es'])

    def test_missing_translation(self):
        del self.questions[0]['options'][0]['explanation']['en']
        self.invalid()

    def test_blank_translation(self):
        self.questions[0]['prompt']['en'] = '  '
        self.invalid()

    def test_undeclared_language(self):
        self.questions[0]['prompt']['fr'] = 'Unexpected'
        self.invalid()

    def test_monolingual_bank(self):
        def transform(item):
            if isinstance(item, dict):
                if set(item) == {'en', 'es'}:
                    return {'en': item['en']}
                return {k: transform(v) for k, v in item.items()}
            if isinstance(item, list):
                return [transform(v) for v in item]
            return item
        m, q = transform(self.manifest), transform(self.questions)
        m['languages'], m['default_language'] = ['en'], 'en'
        read_archive(make_archive(m, q))

    def test_language_must_be_supported(self):
        self.manifest['languages'] = ['fr']
        self.invalid()

    def test_default_language_must_be_declared(self):
        self.manifest['default_language'] = 'fr'
        self.invalid()

    def test_missing_manifest_field(self):
        del self.manifest['version']
        self.invalid()

    def test_unknown_manifest_field(self):
        self.manifest['administrator'] = True
        self.invalid()

    def test_unknown_question_field(self):
        self.questions[0]['difficulty'] = 'easy'
        self.invalid()

    def test_wrong_correct_answer_count(self):
        self.questions[0]['select_count'] = 1
        self.invalid()

    def test_at_least_one_distractor(self):
        self.questions[0]['select_count'] = 4
        for o in self.questions[0]['options']:
            o['correct'] = True
        self.invalid()

    def test_correctness_is_boolean_not_integer(self):
        self.questions[0]['options'][0]['correct'] = 1
        self.invalid()

    def test_duplicate_question_identifier(self):
        self.questions[1]['id'] = self.questions[0]['id']
        self.invalid()

    def test_duplicate_prompt_ignores_case_and_spaces(self):
        self.questions[1]['prompt']['en'] = '  ' + self.questions[0]['prompt']['en'].upper() + ' '
        self.invalid()

    def test_duplicate_option_identifier(self):
        self.questions[0]['options'][1]['id'] = self.questions[0]['options'][0]['id']
        self.invalid()

    def test_duplicate_option_text(self):
        self.questions[0]['options'][1]['text']['en'] = self.questions[0]['options'][0]['text']['en']
        self.invalid()

    def test_unknown_domain(self):
        self.questions[0]['domain_id'] = 'not-a-domain'
        self.invalid()

    def test_empty_domain(self):
        for q in self.questions:
            q['domain_id'] = 'd1'
        self.invalid()

    def test_unknown_reference(self):
        self.questions[0]['references'] = ['missing']
        self.invalid()

    def test_javascript_reference_rejected(self):
        self.manifest['references']['example']['url'] = 'javascript:alert(1)'
        self.invalid()

    def test_reference_credentials_rejected(self):
        self.manifest['references']['example']['url'] = 'https://user:secret@example.org'
        self.invalid()

    def test_bad_date(self):
        self.manifest['content_updated_at'] = '2026-02-31'
        self.invalid()

    def test_compact_date_rejected(self):
        self.manifest['content_updated_at'] = '20260906'
        self.invalid()

    def test_reference_invalid_port_rejected(self):
        self.manifest['references']['example']['url'] = 'https://example.org:bad'
        self.invalid()

    def test_bad_bank_identifier(self):
        self.manifest['bank_id'] = '../unsafe'
        self.invalid()

    def test_bad_version(self):
        self.manifest['version'] = 'latest'
        self.invalid()

    def test_unsupported_schema(self):
        self.manifest['schema_version'] = 3
        self.invalid()

    def test_bool_not_valid_schema_version(self):
        self.manifest['schema_version'] = True
        self.invalid()

    def test_invalid_unicode(self):
        self.questions[0]['prompt']['en'] = '\ud800'
        with self.assertRaises(AppError):
            validate_bank(self.manifest, self.questions)

    def test_invalid_control_character(self):
        self.questions[0]['prompt']['en'] = 'Text\x00'
        self.invalid()

    def test_question_count_exceeds_available(self):
        self.manifest['defaults']['exam']['question_count'] = 21
        self.invalid()

    def test_all_questions_cannot_be_unscored(self):
        self.manifest['defaults']['exam']['unscored_count'] = 10
        self.invalid()

    def test_weights_must_sum_to_100(self):
        self.manifest['defaults']['domain_weights']['d1'] = 49
        self.invalid()

    def test_weights_must_have_all_domains(self):
        del self.manifest['defaults']['domain_weights']['d2']
        self.invalid()

    def test_exam_timing_must_be_fixed(self):
        self.manifest['defaults']['exam']['time_mode'] = 'proportional'
        self.invalid()

    def test_integer_fields_reject_booleans(self):
        self.manifest['defaults']['quiz']['question_count'] = True
        self.invalid()

    def test_proportional_rounding(self):
        m, q = bank_data(count=65, quiz=10, exam=65)
        m['defaults']['exam']['duration_seconds'] = 5400
        self.assertEqual(validate_bank(m, q)['quiz']['duration_seconds'], 831)

    def test_fixed_quiz_duration_preserved(self):
        self.manifest['defaults']['quiz']['time_mode'] = 'fixed'
        self.manifest['defaults']['quiz']['duration_seconds'] = 42
        self.assertEqual(validate_bank(self.manifest, self.questions)['quiz']['duration_seconds'], 42)

    def test_extra_zip_member_rejected(self):
        stream = io.BytesIO(make_archive(self.manifest, self.questions))
        with zipfile.ZipFile(stream, 'a') as z:
            z.writestr('README.md', 'Not a bank entry')
        with self.assertRaises(AppError):
            read_archive(stream.getvalue())

    def test_directory_wrapping_rejected(self):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as z:
            z.writestr('bank/manifest.json', json.dumps(self.manifest))
            z.writestr('bank/questions.json', json.dumps(self.questions))
        with self.assertRaises(AppError):
            read_archive(stream.getvalue())

    def test_path_traversal_rejected(self):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as z:
            z.writestr('../manifest.json', '{}')
            z.writestr('questions.json', '[]')
        with self.assertRaises(AppError):
            read_archive(stream.getvalue())

    def test_symlink_rejected(self):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w') as z:
            info = zipfile.ZipInfo('manifest.json')
            info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            z.writestr(info, 'target')
            z.writestr('questions.json', '[]')
        with self.assertRaises(AppError):
            read_archive(stream.getvalue())

    def test_compression_bomb_rejected(self):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as z:
            z.writestr('manifest.json', ' ' * 1_000_000)
            z.writestr('questions.json', '[]')
        with self.assertRaises(AppError):
            read_archive(stream.getvalue())

    def test_archive_limit(self):
        with self.assertRaises(AppError):
            read_archive(b'x' * (MAX_ARCHIVE + 1))

    def test_invalid_archive(self):
        with self.assertRaises(AppError):
            read_archive(b'not a ZIP')

    def test_duplicate_json_keys_rejected(self):
        with self.assertRaises(ValueError):
            parse_json(b'{"key": 1, "key": 2}')

    def test_nonfinite_json_rejected(self):
        with self.assertRaises(ValueError):
            parse_json(b'{"key": NaN}')

    def test_utf8_bom_supported(self):
        self.assertEqual(parse_json(b'\xef\xbb\xbf{"key": 1}'), {'key': 1})

    def test_authoring_example_is_importable(self):
        m, q, _, _ = read_archive((ROOT / 'docs/example-bank.zip').read_bytes())
        self.assertEqual(m['bank_id'], 'example-cert')
        self.assertEqual(len(q), 4)

    def test_authoring_kit_is_not_a_bank(self):
        with self.assertRaises(AppError):
            read_archive((ROOT / 'schema/question-bank-authoring-kit.zip').read_bytes())

    def test_locale_keys_and_placeholders_match(self):
        import re
        en = json.loads((ROOT / 'web/locales/en.json').read_text(encoding='utf-8'))
        es = json.loads((ROOT / 'web/locales/es.json').read_text(encoding='utf-8'))
        self.assertEqual(set(en), set(es))
        for key in en:
            self.assertEqual(set(re.findall(r'\{(\w+)\}', en[key])), set(re.findall(r'\{(\w+)\}', es[key])), key)


class RepositoryTests(Fixture):
    def test_dry_run_makes_no_changes(self):
        m, q = bank_data(bank_id='other-cert')
        preview = self.banks.import_archive(make_archive(m, q), 1, dry_run=True)
        self.assertEqual(preview['bank_id'], 'other-cert')
        self.assertEqual(len(self.banks.list()), 1)

    def test_duplicate_version_rejected(self):
        self.assertCode('version_exists', self.banks.import_archive, make_archive(self.manifest, self.questions), 1, True)

    def test_replacement_requires_confirmation(self):
        m = deepcopy(self.manifest)
        m['version'] = '1.1.0'
        self.assertCode('replacement_confirmation_required', self.banks.import_archive, make_archive(m, self.questions), 1)
        self.assertEqual(self.banks.list()[0]['version'], '1.0.0')

    def test_new_version_preserves_old_record(self):
        m = deepcopy(self.manifest)
        m['version'] = '1.1.0'
        self.banks.import_archive(make_archive(m, self.questions), 1, replace=True)
        with self.storage.connection() as con:
            self.assertEqual(con.execute('SELECT COUNT(*) FROM bank_versions').fetchone()[0], 2)
        self.assertEqual(self.banks.list()[0]['version'], '1.1.0')

    def test_export_uses_current_settings(self):
        settings = self.settings()
        settings['exam']['duration_seconds'] = 1000
        self.configure(settings)
        m, q, s, _ = read_archive(self.banks.export('test-cert'))
        self.assertEqual(s['exam']['duration_seconds'], 1000)
        self.assertEqual(s['quiz']['duration_seconds'], 500)
        self.assertEqual(q, self.questions)

    def test_disabled_bank_only_listed_for_admin(self):
        self.configure(self.settings(), False)
        self.assertEqual(self.banks.list(), [])
        self.assertEqual(len(self.banks.list(admin=True)), 1)

    def test_invalid_settings_do_not_mutate(self):
        before = self.settings()
        settings = deepcopy(before)
        settings['exam']['unscored_count'] = 99
        self.assertCode('invalid_bank', self.configure, settings)
        self.assertEqual(self.settings(), before)

    def test_import_and_configuration_are_audited(self):
        self.configure(self.settings())
        with self.storage.connection() as con:
            rows = con.execute('SELECT action FROM audit ORDER BY id').fetchall()
        self.assertEqual([r[0] for r in rows], ['bank_import', 'bank_configure'])
