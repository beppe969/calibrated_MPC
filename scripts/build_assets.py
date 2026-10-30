#!/usr/bin/env python3
"""Compile the paper's TikZ/PGFPlots figures from exported numerical inputs."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
FIGURES = {
    'figure_1_architecture': 'fig_architecture.tex',
    'figure_2_risk_maps': 'fig_risk_maps.tex',
    'figure_3_tradeoff_attainability': 'fig_tradeoff_gap.tex',
    'figure_4_budget_shift': 'fig_budget_shift.tex',
}
PREAMBLE = r'''\documentclass[journal]{IEEEtran}
\usepackage[T1]{fontenc}
\usepackage[utf8]{inputenc}
\usepackage{amsmath,amssymb,mathtools,bm}
\usepackage{graphicx,xcolor}
\usepackage{tikz,pgfplots,pgfplotstable}
\usetikzlibrary{positioning,arrows.meta,calc}
\usepgfplotslibrary{groupplots}
\definecolor{revisioncolor}{rgb}{0,0,0}
\usepackage[active,tightpage]{preview}
\setlength\PreviewBorder{4pt}
\pagestyle{empty}
\begin{document}
\begin{preview}
\begin{minipage}{\textwidth}\centering
'''
END = '\n\\end{minipage}\n\\end{preview}\n\\end{document}\n'


def check_tools(png: bool = True) -> None:
    tools = ['pdflatex'] + (['pdftoppm'] if png else [])
    absent = [name for name in tools if shutil.which(name) is None]
    if absent:
        raise RuntimeError('Install the TeX/Poppler tools listed in README.md; missing: ' + ', '.join(absent))


def compile_tex(work: Path, filename: str, log: Path, passes: int = 3) -> None:
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open('w', encoding='utf-8') as stream:
        for i in range(passes):
            stream.write(f'LaTeX pass {i + 1}\n'); stream.flush()
            proc = subprocess.run(['pdflatex', '-interaction=nonstopmode', '-halt-on-error',
                                   '-file-line-error', filename], cwd=work,
                                  stdout=stream, stderr=subprocess.STDOUT, check=False)
            if proc.returncode:
                raise RuntimeError(f'LaTeX compilation failed. See {log}')
    final_log = (work / (Path(filename).stem + '.log')).read_text(errors='replace')
    for text in ['There were undefined references', 'undefined citations', 'LaTeX Error:']:
        if text in final_log:
            raise RuntimeError(f'Unresolved LaTeX content ({text}). See {log}')


def build(data: Path, output: Path, png: bool = True) -> dict:
    check_tools(png)
    data, output = data.resolve(), output.resolve()
    if not (data / 'benchmark_macro.tex').is_file():
        raise FileNotFoundError('Export the experiment records before compiling figures.')
    output.mkdir(parents=True, exist_ok=True)
    logs = output / 'logs'
    logs.mkdir(exist_ok=True)
    report = {'status': 'PASS', 'figures': [],
              'renderer': 'pdftoppm at 200 dpi' if png else None}
    with tempfile.TemporaryDirectory(prefix='tube-mpc-tex-') as tmp:
        work = Path(tmp)
        shutil.copytree(ROOT / 'paper/figures', work / 'figures')
        shutil.copytree(data, work / 'data')
        for target, source in FIGURES.items():
            body = r'\input{figures/' + source + '}'
            if target == 'figure_1_architecture':
                body = r'\resizebox{.98\textwidth}{!}{' + body + '}'
            tex = work / f'{target}.tex'
            tex.write_text(PREAMBLE + body + END, encoding='utf-8')
            compile_tex(work, tex.name, logs / f'{target}.log')
            shutil.copy2(work / f'{target}.pdf', output / f'{target}.pdf')
            # Retain the standalone entry points; their inputs live in paper/.
            (output / f'{target}.tex').write_text(PREAMBLE + body + END, encoding='utf-8')
            if png:
                subprocess.run(['pdftoppm', '-r', '200', '-singlefile', '-png',
                                str(output / f'{target}.pdf'), str(output / target)], check=True)
            report['figures'].append({'pdf': f'{target}.pdf', 'source': f'paper/figures/{source}',
                                      'png': f'{target}.png' if png else None})
    (output / 'build_report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, default=ROOT / 'paper/data')
    parser.add_argument('--output', type=Path, default=ROOT / 'build/figures')
    parser.add_argument('--no-png', action='store_true')
    args = parser.parse_args()
    print(json.dumps(build(args.data, args.output, not args.no_png), indent=2))


if __name__ == '__main__':
    main()
