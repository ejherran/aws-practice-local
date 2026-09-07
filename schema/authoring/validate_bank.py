#!/usr/bin/env python3
"""Validate a question bank with Python 3.10+ and no dependencies."""
import argparse
from pathlib import Path
import sys
from validator.banks import read_archive
from validator.errors import AppError

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    args = parser.parse_args()
    try:
        manifest, questions, _, _ = read_archive(args.archive.read_bytes())
    except (AppError, OSError) as error:
        print("INVALID:", error, getattr(error, "details", {}), file=sys.stderr)
        return 1
    print(f"VALID: {manifest['bank_id']} {manifest['version']} | {len(questions)} questions | {', '.join(manifest['languages'])}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
