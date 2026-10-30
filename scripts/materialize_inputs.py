#!/usr/bin/env python3
"""Save the independent main design/calibration samples as portable NPZ arrays."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
import certified_benchmark as b


def materialize(output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    arrays = {}
    design_rng = np.random.default_rng(b.SEEDS['design'])
    calibration_rng = np.random.default_rng(b.SEEDS['calibration'])
    for g, label in enumerate(b.CONTEXTS):
        arrays[f'design_{label}'] = b.student(g, b.DESIGN_N, design_rng)
    for g, label in enumerate(b.CONTEXTS):
        arrays[f'calibration_{label}'] = b.student(g, int(np.array([4, 2, 1])[g] * b.CAL_N), calibration_rng)
    np.savez_compressed(output / 'design_calibration.npz', **arrays)
    metadata = {'seeds': {name: b.SEEDS[name] for name in ['design', 'calibration']},
                'dtype': 'float64', 'array_shapes': {key: list(value.shape) for key, value in arrays.items()}}
    (output / 'metadata.json').write_text(json.dumps(metadata, indent=2) + '\n', encoding='utf-8')
    return metadata


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, default=ROOT / 'build/inputs')
    print(json.dumps(materialize(p.parse_args().output), indent=2))
