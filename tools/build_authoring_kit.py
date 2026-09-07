#!/usr/bin/env python3
"""Rebuild the portable authoring kit from editable source, without dependencies."""
import argparse
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from trainer.banks import make_archive, parse_json, read_archive
from trainer.errors import AppError


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    default_output = ROOT / 'schema/question-bank-authoring-kit.zip'
    parser.add_argument('--output', type=Path, default=default_output)
    args = parser.parse_args(argv)
    source = ROOT / 'schema/authoring'
    try:
        entries = {}
        for name in ('README.md', 'AGENTS.md', 'build_bank.py', 'validate_bank.py',
                     'example/manifest.json', 'example/questions.json'):
            entries[name] = (source / name).read_bytes()
        for name in ('manifest.schema.json', 'questions.schema.json'):
            entries[name] = (ROOT / 'schema' / name).read_bytes()
        manifest = parse_json(entries['example/manifest.json'])
        questions = parse_json(entries['example/questions.json'])
        example = make_archive(manifest, questions)
        read_archive(example)
        entries['example-bank.zip'] = example
        contract_source = (ROOT / 'trainer/banks.py').read_text(encoding='utf-8')
        marker = '\nclass BankRepository:'
        if marker not in contract_source:
            raise ValueError('The validator/repository boundary changed. Update this builder explicitly.')
        entries['validator/banks.py'] = (contract_source.split(marker, 1)[0] + '\n').encode('utf-8')
        entries['validator/errors.py'] = (ROOT / 'trainer/errors.py').read_bytes()
        entries['validator/__init__.py'] = b'"""Standard-library bank validation helpers."""\n'
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(args.output, 'w', zipfile.ZIP_DEFLATED) as archive:
            for name in sorted(entries):
                archive.writestr(name, entries[name])
        if args.output.resolve() == default_output.resolve():
            (ROOT / 'docs/example-bank.zip').write_bytes(example)
    except (AppError, OSError, ValueError, TypeError, RecursionError) as error:
        print('Build failed:', error, getattr(error, 'details', {}), file=sys.stderr)
        return 1
    print('Created:', args.output)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
