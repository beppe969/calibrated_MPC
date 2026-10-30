#!/usr/bin/env python3
"""Refresh the release manifest after intentional, reviewed package changes."""
from pathlib import Path
import hashlib
import json
ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_DIRS = {'.git', '.venv', '__pycache__', 'build'}
EXCLUDED_SUFFIXES = {'.pyc', '.pyo', '.aux', '.out', '.synctex.gz'}


def main() -> None:
    manifest = ROOT / 'validation/manifest.json'
    records = {}
    for file in sorted(ROOT.rglob('*')):
        rel = file.relative_to(ROOT)
        if not file.is_file() or file == manifest or any(part in EXCLUDED_DIRS for part in rel.parts):
            continue
        if file.name == '.DS_Store' or file.suffix in EXCLUDED_SUFFIXES:
            continue
        # Rendering build logs are transient; the release report carries their outcomes.
        if 'logs' in rel.parts:
            continue
        data = file.read_bytes()
        records[rel.as_posix()] = {'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps({'hash': 'sha256', 'files': records}, indent=2) + '\n', encoding='utf-8')
    print(f'Manifest updated: {len(records)} files')


if __name__ == '__main__':
    main()
