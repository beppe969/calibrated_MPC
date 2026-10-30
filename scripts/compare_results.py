#!/usr/bin/env python3
"""Compare scientific records while excluding measured wall-clock timings."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
TIMING_COLUMNS = {'qp_ms', 'mean_qp_ms'}
ENVIRONMENT_KEYS = {'python', 'numpy', 'scipy', 'pandas'}


def compare(reference: Path, candidate: Path, output: Path,
            atol: float = 1e-8, rtol: float = 1e-9) -> dict:
    reference, candidate = reference.resolve(), candidate.resolve()
    if reference == candidate:
        raise ValueError('Choose distinct reference and candidate directories.')
    report = {'status': 'PASS', 'atol': atol, 'rtol': rtol,
              'excluded_csv_columns': sorted(TIMING_COLUMNS),
              'excluded_configuration_keys': sorted(ENVIRONMENT_KEYS),
              'csv_files': {}, 'npz_files': {}, 'json_files': {}, 'failures': []}

    def failure(message: str) -> None:
        report['status'] = 'FAIL'
        report['failures'].append(message)

    def compare_json(a, b, location: str, filename: str) -> None:
        if isinstance(a, dict):
            if not isinstance(b, dict) or set(a) != set(b):
                failure(f'{filename}:{location}: JSON keys differ')
                return
            for key in a:
                if filename == 'configuration.json' and key in ENVIRONMENT_KEYS:
                    continue
                compare_json(a[key], b[key], f'{location}/{key}', filename)
        elif isinstance(a, list):
            if not isinstance(b, list) or len(a) != len(b):
                failure(f'{filename}:{location}: JSON array length differs')
                return
            for i, (av, bv) in enumerate(zip(a, b)):
                compare_json(av, bv, f'{location}/{i}', filename)
        elif isinstance(a, float):
            if not isinstance(b, (int, float)) or not np.isclose(a, b, atol=atol, rtol=rtol, equal_nan=True):
                failure(f'{filename}:{location}: {a!r} != {b!r}')
        elif a != b:
            failure(f'{filename}:{location}: {a!r} != {b!r}')

    for source in sorted(reference.iterdir()):
        if not source.is_file() or not (source.name.endswith(('.csv', '.csv.gz', '.npz', '.json'))):
            continue
        dest = candidate / source.name
        if not dest.is_file():
            failure(f'{source.name}: missing candidate file')
            continue
        if source.name.endswith(('.csv', '.csv.gz')):
            a = pd.read_csv(source, float_precision='round_trip')
            b = pd.read_csv(dest, float_precision='round_trip')
            if a.shape != b.shape or list(a.columns) != list(b.columns):
                failure(f'{source.name}: CSV shape or columns differ')
                continue
            errors, exact = {}, True
            for col in a:
                if col in TIMING_COLUMNS:
                    continue
                av, bv = a[col].to_numpy(), b[col].to_numpy()
                if pd.api.types.is_numeric_dtype(a[col]) and pd.api.types.is_numeric_dtype(b[col]):
                    if pd.api.types.is_integer_dtype(a[col]):
                        ok = np.array_equal(av, bv)
                    else:
                        ok = np.allclose(av, bv, atol=atol, rtol=rtol, equal_nan=True)
                    finite = np.isfinite(av) & np.isfinite(bv)
                    error = float(np.max(np.abs(av[finite] - bv[finite]))) if finite.any() else 0.
                    errors[col] = error
                    exact = exact and np.array_equal(av, bv, equal_nan=True)
                else:
                    ok = a[col].fillna('<NA>').equals(b[col].fillna('<NA>'))
                    exact = exact and ok
                if not ok:
                    failure(f'{source.name}:{col}: values differ beyond tolerance')
            report['csv_files'][source.name] = {
                'rows': len(a), 'non_timing_values_exact': bool(exact),
                'max_abs_error': max(errors.values(), default=0.),
                'column_max_abs_errors': errors,
            }
        elif source.suffix == '.npz':
            with np.load(source, allow_pickle=False) as a, np.load(dest, allow_pickle=False) as b:
                ok = sorted(a.files) == sorted(b.files)
                errors = {}
                for key in a.files if ok else []:
                    same = a[key].shape == b[key].shape
                    if same:
                        same = np.array_equal(a[key], b[key])
                        errors[key] = float(np.max(np.abs(a[key] - b[key])))
                    ok = ok and same
                if not ok:
                    failure(f'{source.name}: exogenous arrays must match exactly')
                report['npz_files'][source.name] = {'exact': bool(ok), 'max_abs_errors': errors}
        else:
            before = len(report['failures'])
            compare_json(json.loads(source.read_text()), json.loads(dest.read_text()), '', source.name)
            report['json_files'][source.name] = {'match': len(report['failures']) == before}
    report['compared_file_count'] = sum(len(report[k]) for k in ('csv_files', 'npz_files', 'json_files'))
    report['max_csv_abs_error'] = max((v['max_abs_error'] for v in report['csv_files'].values()), default=0.)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    if report['failures']:
        raise AssertionError(f"{len(report['failures'])} comparison failure(s); details: {output}")
    return report


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reference', type=Path, default=ROOT / 'reference/results')
    p.add_argument('--candidate', type=Path, required=True)
    p.add_argument('--output', type=Path, default=ROOT / 'build/comparison.json')
    p.add_argument('--atol', type=float, default=1e-8)
    p.add_argument('--rtol', type=float, default=1e-9)
    a = p.parse_args()
    report = compare(a.reference, a.candidate, a.output, a.atol, a.rtol)
    print(f"PASS: {report['compared_file_count']} files; maximum CSV discrepancy {report['max_csv_abs_error']:.3g}")


if __name__ == '__main__':
    main()
