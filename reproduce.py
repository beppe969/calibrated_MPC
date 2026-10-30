#!/usr/bin/env python3
"""Run, verify and render the reproducibility package from any working directory."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

# Set before importing numerical modules, and inherit in all subprocesses.
for name in ['OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS',
             'VECLIB_MAXIMUM_THREADS', 'NUMEXPR_NUM_THREADS']:
    os.environ[name] = '1'
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'scripts'))


def generated_path(path: Path) -> Path:
    path = path.resolve()
    for name in ['reference', 'paper', 'src', 'scripts', 'tests', 'validation', 'artifacts', '.github']:
        protected = (ROOT / name).resolve()
        if path == protected or protected in path.parents or path in protected.parents:
            raise ValueError(f'Choose an output directory outside the packaged sources: {path}')
    return path


def run(command: list[str], log: Path) -> None:
    log.parent.mkdir(parents=True, exist_ok=True)
    print('Running:', ' '.join(command), flush=True)
    with log.open('w', encoding='utf-8') as stream:
        proc = subprocess.run(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, check=False)
    if proc.returncode:
        tail = '\n'.join(log.read_text(errors='replace').splitlines()[-20:])
        raise RuntimeError(f'Command failed (exit {proc.returncode}); log: {log}\n{tail}')
    print('Completed; log:', log, flush=True)


def verify_manifest() -> dict:
    path = ROOT / 'validation/manifest.json'
    if not path.is_file():
        raise FileNotFoundError('Release integrity manifest is missing.')
    values = json.loads(path.read_text())
    failures = []
    for name, expected in values['files'].items():
        file = ROOT / name
        if not file.is_file() or hashlib.sha256(file.read_bytes()).hexdigest() != expected['sha256']:
            failures.append(name)
    if failures:
        raise AssertionError('Packaged files changed or missing: ' + '; '.join(failures[:10]))
    return {'status': 'PASS', 'files_checked': len(values['files'])}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['verify', 'smoke', 'run', 'all', 'export', 'figures', 'inputs', 'integrity'])
    parser.add_argument('--results', type=Path, default=ROOT / 'reference/results',
                        help='Input records for verify/export/figures/paper; default: supplied reference')
    parser.add_argument('--output', type=Path, help='Generated output directory; default: build/COMMAND')
    parser.add_argument('--episodes', type=int, default=10, help='Number of smoke missions only (default: 10)')
    parser.add_argument('--no-png', action='store_true', help='Compile PDFs without Poppler PNG previews')
    args = parser.parse_args()
    output = generated_path(args.output or ROOT / 'build' / args.command)
    output.mkdir(parents=True, exist_ok=True)
    start = time.perf_counter()
    from environment import record_environment
    record_environment(output / 'environment.json')
    if args.command == 'integrity':
        report = verify_manifest()
        (output / 'integrity.json').write_text(json.dumps(report, indent=2) + '\n')
        print(f"PASS: {report['files_checked']} packaged file hashes")
        return
    if args.command in ['all', 'figures']:
        from build_assets import check_tools
        check_tools(not args.no_png)
    if args.command in ['verify', 'all', 'smoke']:
        run([sys.executable, '-m', 'unittest', 'discover', '-s', str(ROOT / 'tests'), '-v'], output / 'logs/unit_tests.log')
    if args.command == 'verify':
        from verify_results import verify
        report = verify(args.results, output / 'verification.json')
        from export_results import export
        export(args.results, output / 'export')
        # Check every plotted CSV and numeric macro against the supplied paper inputs.
        if args.results.resolve() == (ROOT / 'reference/results').resolve():
            for source in (ROOT / 'paper/data').iterdir():
                target = output / 'export/data' / source.name
                if source.read_bytes() != target.read_bytes():
                    raise AssertionError(f'Paper input differs: {source.name}')
        print(f"PASS: {report['executed_stages_checked']} stages; exported paper inputs checked")
    elif args.command in ['run', 'all', 'smoke']:
        results = output / 'results'
        if results.exists() and any(results.iterdir()):
            raise FileExistsError(f'Results already exist: {results}. Use a fresh --output directory.')
        command = [sys.executable, str(ROOT / 'src/certified_benchmark.py'), '--output', str(results),
                   '--episodes', str(args.episodes if args.command == 'smoke' else 500)]
        if args.command == 'smoke':
            if args.episodes < 2:
                raise ValueError('--episodes must be at least 2')
            command += ['--smoke']
        run(command, output / 'logs/simulation.log')
        from verify_results import verify
        if args.command == 'smoke':
            verify(results, output / 'verification.json', smoke=True)
        else:
            run([sys.executable, str(ROOT / 'src/compare_certificates.py'), '--results', str(results)], output / 'logs/certificate_comparison.log')
            verify(results, output / 'verification.json')
            from compare_results import compare
            compare(ROOT / 'reference/results', results, output / 'comparison.json')
            from materialize_inputs import materialize
            materialize(output / 'inputs')
            from export_results import export
            export(results, output / 'export')
            if args.command == 'all':
                from build_assets import build
                build(output / 'export/data', output / 'figures', png=not args.no_png)
    elif args.command in ['export', 'figures']:
        from export_results import export
        export_dir = output if args.command == 'export' else output / 'export'
        export(args.results, export_dir)
        if args.command != 'export':
            from build_assets import build
            build(export_dir / 'data', output, png=not args.no_png)
    elif args.command == 'inputs':
        from materialize_inputs import materialize
        materialize(output)
    report = {'status': 'PASS', 'command': args.command, 'elapsed_seconds': time.perf_counter() - start}
    (output / 'run_report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(f"PASS: {args.command}; {report['elapsed_seconds']:.1f} seconds; outputs: {output}")


if __name__ == '__main__':
    try:
        main()
    except (ValueError, RuntimeError, FileNotFoundError, FileExistsError, AssertionError) as error:
        print(f'ERROR: {error}', file=sys.stderr)
        sys.exit(1)
