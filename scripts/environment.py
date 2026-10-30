"""Record the numerical and rendering environment of a reproduction run."""
from __future__ import annotations
import contextlib
import importlib.metadata
import io
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys


def record_environment(output: Path) -> dict:
    import numpy as np
    packages = ['numpy', 'scipy', 'pandas', 'python-dateutil', 'pytz', 'tzdata', 'six']
    versions = {name: importlib.metadata.version(name) for name in packages}
    text = io.StringIO()
    with contextlib.redirect_stdout(text):
        np.show_config()
    tools = {}
    for name in ['pdflatex', 'pdftoppm', 'git']:
        if shutil.which(name):
            flag = '-v' if name == 'pdftoppm' else '--version'
            result = subprocess.run([name, flag], text=True, capture_output=True, check=False)
            tools[name] = (result.stdout or result.stderr).splitlines()[0]
    cpu = platform.processor()
    if Path('/proc/cpuinfo').is_file():
        for line in Path('/proc/cpuinfo').read_text().splitlines():
            if line.startswith('model name'):
                cpu = line.split(':', 1)[1].strip()
                break
    report = {'python': platform.python_version(), 'implementation': platform.python_implementation(),
              'platform': platform.platform(), 'machine': platform.machine(), 'cpu': cpu,
              'packages': versions, 'numpy_build_configuration': text.getvalue(), 'tools': tools,
              'threads': {name: os.environ.get(name) for name in
                          ['OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS',
                           'VECLIB_MAXIMUM_THREADS', 'NUMEXPR_NUM_THREADS']}}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return report
