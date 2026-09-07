#!/usr/bin/env python3
"""Create a validated bank ZIP from a directory containing the two JSON files."""
import argparse
from pathlib import Path
import sys
from validator.banks import make_archive, parse_json, read_archive
from validator.errors import AppError

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    try:
        manifest = parse_json((args.directory / "manifest.json").read_bytes())
        questions = parse_json((args.directory / "questions.json").read_bytes())
        archive = make_archive(manifest, questions)
        read_archive(archive)
        args.output.write_bytes(archive)
    except (AppError, OSError, ValueError, TypeError, RecursionError) as error:
        print("INVALID:", error, getattr(error, "details", {}), file=sys.stderr)
        return 1
    print("Created:", args.output)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
