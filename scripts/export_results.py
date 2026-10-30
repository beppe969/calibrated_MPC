#!/usr/bin/env python3
"""Generate the paper's numerical inputs and tables from one results directory."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
LABELS = {
    'oracle': 'Reference risk', 'certified': 'SC-MPC',
    'global_fixed': 'Fixed global ball', 'worstcase': 'Fixed region',
    'ball_backloaded': 'Backloaded balls', 'ellipsoid_fixed': 'Fixed ellipsoids',
    'nominal': 'Nominal MPC', 'ball_fixed': 'Fixed context balls',
    'ball_decision': 'Budgeted empirical balls', 'cert_ball': 'Certified context balls',
}
MAIN = tuple(LABELS)[:7]


def scientific_tex(value: float, digits: int = 4) -> str:
    mantissa, exponent = f'{value:.{digits}e}'.split('e')
    return mantissa + r'\times10^{' + str(int(exponent)) + '}'


def export(results: Path, output: Path) -> dict:
    """Write CSV and LaTeX inputs; leave the supplied records unchanged."""
    results, output = results.resolve(), output.resolve()
    if results == output or results in output.parents:
        raise ValueError('Export output must be outside the results directory.')
    required = ['summary.csv', 'operational_risk_table.csv', 'paired_sweep.csv',
                'budget_example.csv', 'certificate_comparison_sweep.csv',
                'certificate_comparison_validation.json', 'validation.json',
                'shift_0.5_risk_table.csv', 'shift_1.5_risk_table.csv',
                'shift_2.0_risk_table.csv', 'paired_mpc_values.csv']
    absent = [name for name in required if not (results / name).is_file()]
    if absent:
        raise FileNotFoundError('Full experiment records required; missing: ' + '; '.join(absent))
    data = output / 'data'
    tables = output / 'tables'
    data.mkdir(parents=True, exist_ok=True)
    tables.mkdir(parents=True, exist_ok=True)
    summary = pd.read_csv(results / 'summary.csv')
    risks = pd.read_csv(results / 'operational_risk_table.csv')
    for context, label in [('L', 'low'), ('M', 'med'), ('H', 'high')]:
        selected = risks[(risks.geometry == 'ellipsoid') & (risks.context == context)]
        selected[['lambda', 'reference_probability', 'certified_probability', 'eb_split_probability']].rename(
            columns={'reference_probability': 'true', 'certified_probability': 'upper',
                     'eb_split_probability': 'eb'}).to_csv(data / f'riskmap_{label}.csv', index=False)
    budgets = sorted(summary[summary.method == 'certified'].budget.unique())
    if len(budgets) != 6:
        raise ValueError('The paper export requires the complete six-budget experiment.')
    for method in MAIN:
        selected = summary[summary.method == method][
            ['budget', 'common_cost', 'mean_violation_count', 'complete_certificate_fraction']].copy()
        if method == 'nominal':
            selected = pd.concat([selected.assign(budget=eps) for eps in budgets], ignore_index=True)
        selected.to_csv(data / f'cost_{method}.csv', index=False)
    paired = pd.read_csv(results / 'paired_sweep.csv')
    paired.to_csv(data / 'paired_attainability.csv', index=False)
    bound = pd.read_csv(results / 'certificate_comparison_sweep.csv')
    bound.to_csv(data / 'bound_attainability.csv', index=False)
    ledger = pd.read_csv(results / 'budget_example.csv')
    horizon = len(ledger)
    if horizon != 20 or ledger.episode.nunique() != 1:
        raise ValueError('Expected one complete 20-step mission in budget_example.csv.')
    eps = float(ledger.budget_before.iloc[0])
    pd.DataFrame({'t': np.arange(horizon + 1),
                  'actual': np.r_[eps, ledger.budget_after],
                  'equal': eps * (1 - np.arange(horizon + 1) / horizon)}).to_csv(
                      data / 'remaining_budget.csv', index=False)
    shifts = []
    for gamma in [.5, 1., 1.5, 2.]:
        filename = 'operational_risk_table.csv' if gamma == 1 else f'shift_{gamma:.1f}_risk_table.csv'
        frame = pd.read_csv(results / filename)
        row = frame[(frame.geometry == 'ellipsoid') & (frame.context == 'H') & (frame['lambda'] == 3.5)].iloc[0]
        shifts.append({'gamma': gamma, 'reference': row.reference_probability,
                       'certified': row.certified_probability})
    pd.DataFrame(shifts).to_csv(data / 'shift_high_certificate.csv', index=False)
    selected = summary[(summary.budget == .12) | (summary.method == 'nominal')]
    main = pd.concat([selected[selected.method == method] for method in MAIN], ignore_index=True)
    if len(main) != 7:
        raise ValueError('Expected exactly seven methods for Table II.')
    main.to_csv(tables / 'table_2_benchmark.csv', index=False)
    rows, md = [], [
        '| Method | Mean physical violations | Mean tube misses | Common cost | Fallback step rate |',
        '|---|---:|---:|---:|---:|',
    ]
    for _, row in main.iterrows():
        miss = '---' if row.method == 'nominal' else f'{row.mean_set_miss_count:.3f}'
        rows.append(f'{LABELS[row.method]} & {row.mean_violation_count:.3f} & {miss} & '
                    f'{row.common_cost:.5f} & {row.fallback_step_rate:.4f} ' + r'\\')
        md.append(f'| {LABELS[row.method]} | {row.mean_violation_count:.3f} | {miss} | '
                  f'{row.common_cost:.5f} | {row.fallback_step_rate:.4f} |')
    rowtext = '\n'.join(rows) + '\n'
    (data / 'benchmark_rows.tex').write_text(rowtext, encoding='utf-8')
    (tables / 'table_2_benchmark.tex').write_text(rowtext, encoding='utf-8')
    (tables / 'table_2_benchmark.md').write_text('\n'.join(md) + '\n', encoding='utf-8')
    main_sc = main[main.method == 'certified'].iloc[0]
    main_ref = main[main.method == 'oracle'].iloc[0]
    small_sc = summary[(summary.method == 'certified') & (summary.budget == .05)].iloc[0]
    endpoints = risks[(risks.geometry == 'ellipsoid') & (risks['lambda'] == 3.5)].set_index('context')
    pair_records = pd.read_csv(results / 'paired_mpc_values.csv')
    full_paired = paired[paired.nbase == 32768].iloc[0]
    validation = json.loads((results / 'validation.json').read_text())
    bound_validation = json.loads((results / 'certificate_comparison_validation.json').read_text())
    values = {
        'RiskLow': scientific_tex(endpoints.loc['L', 'certified_probability']),
        'RiskMed': scientific_tex(endpoints.loc['M', 'certified_probability']),
        'RiskHigh': f"{endpoints.loc['H', 'certified_probability']:.6f}",
        'MaxSpendMain': f'{main_sc.max_total_spend:.6f}',
        'MaxSpendSmall': f'{small_sc.max_total_spend:.6f}',
        'FullPairedGap': f'{full_paired.mean_same_problem_gap:.6f}',
        'MinimumPairedGap': scientific_tex(pair_records.gap.min(), 2),
        'ClosedLoopCostDifference': f'{main_sc.common_cost - main_ref.common_cost:.6f}',
        'QPCalls': str(validation['QP_calls']),
        'BoundQPCalls': str(bound_validation['QP_calls']),
        'LedgerEpisode': str(int(ledger.episode.iloc[0])),
    }
    prose = '\n'.join('\\newcommand{\\' + key + '}{' + value + '}' for key, value in values.items()) + '\n'
    (data / 'numerical_prose.tex').write_text(prose, encoding='utf-8')
    (data / 'benchmark_macro.tex').write_text(
        '\\newcommand{\\BenchmarkRows}{%\n' + rowtext + '}\n' +
        r'\input{data/numerical_prose.tex}' + '\n', encoding='utf-8')
    for filename in ['ablation_summary.csv', 'shift_summary.csv',
                     'certificate_comparison_summary.csv', 'certificate_comparison_sweep.csv',
                     'paired_sweep.csv', 'operational_risk_table.csv']:
        pd.read_csv(results / filename).to_csv(tables / filename, index=False)
    metrics = {
        'episodes_per_method_and_budget': int(main_sc.episodes),
        'steps_per_mission': horizon,
        'certificate_at_largest_radius': endpoints.certified_probability.to_dict(),
        'max_spend_budget_012': float(main_sc.max_total_spend),
        'max_spend_budget_005': float(small_sc.max_total_spend),
        'full_size_paired_mean_value_gap': float(full_paired.mean_same_problem_gap),
        'paired_feasible_counts': {str(int(row.nbase)): int(row.feasible_queries)
                                   for _, row in paired.iterrows()},
        'main_qp_calls': int(validation['QP_calls']),
        'bound_comparison_qp_calls': int(bound_validation['QP_calls']),
        'plotted_ledger_episode': int(ledger.episode.iloc[0]),
    }
    (output / 'metrics.json').write_text(json.dumps(metrics, indent=2) + '\n', encoding='utf-8')
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results', type=Path, default=ROOT / 'reference/results')
    parser.add_argument('--output', type=Path, default=ROOT / 'build/export')
    args = parser.parse_args()
    print(json.dumps(export(args.results, args.output), indent=2))


if __name__ == '__main__':
    main()
