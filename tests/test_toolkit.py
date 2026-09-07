"""Validate that the delivered authoring tools are standalone and rebuildable."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile
from trainer.banks import read_archive
from tests.helpers import ROOT


class AuthoringToolkitTests(unittest.TestCase):
    def test_embedded_validator_matches_current_source(self):
        expected = (ROOT / 'trainer/banks.py').read_text(encoding='utf-8').split('\nclass BankRepository:', 1)[0] + '\n'
        with zipfile.ZipFile(ROOT / 'schema/question-bank-authoring-kit.zip') as archive:
            self.assertEqual(archive.read('validator/banks.py').decode('utf-8'), expected)
            self.assertEqual(archive.read('validator/errors.py'), (ROOT / 'trainer/errors.py').read_bytes())

    def test_authoring_kit_rebuild(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'kit.zip'
            result = subprocess.run([sys.executable, str(ROOT / 'tools/build_authoring_kit.py'), '--output', str(output)],
                                    capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            with zipfile.ZipFile(output) as archive:
                self.assertIn('AGENTS.md', archive.namelist())
                self.assertEqual(len(read_archive(archive.read('example-bank.zip'))[1]), 4)

    def test_standalone_builder_and_validator(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            # This is our trusted, shipped toolkit, not an uploaded bank ZIP.
            with zipfile.ZipFile(ROOT / 'schema/question-bank-authoring-kit.zip') as archive:
                archive.extractall(work)
            result = subprocess.run([sys.executable, 'build_bank.py', 'example', 'rebuilt.zip'], cwd=work,
                                    capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([sys.executable, 'validate_bank.py', 'rebuilt.zip'], cwd=work,
                                    capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('VALID: example-cert', result.stdout)
            self.assertEqual(len(read_archive((work / 'rebuilt.zip').read_bytes())[1]), 4)
