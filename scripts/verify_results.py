#!/usr/bin/env python3
"""Reconstruct physical outcomes, costs and risk ledgers from every stored stage."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
import certified_benchmark as b


def require(condition, message: str) -> None:
    if not bool(condition):
        raise AssertionError(message)


def close(a, c, message: str, atol: float = 2e-12, rtol: float = 2e-12) -> float:
    a, c = np.asarray(a), np.asarray(c)
    require(a.shape == c.shape, message + ': shape mismatch')
    require(np.allclose(a, c, atol=atol, rtol=rtol, equal_nan=True), message)
    finite = np.isfinite(a) & np.isfinite(c)
    return float(np.max(np.abs(a[finite] - c[finite]))) if finite.any() else 0.


def check_summary(episodes: pd.DataFrame, summary: pd.DataFrame) -> None:
    expected = b.summarize(episodes)
    keys = ['method', 'budget', 'gamma']
    expected = expected.sort_values(keys).reset_index(drop=True)
    actual = summary.sort_values(keys).reset_index(drop=True)
    require(expected.shape == actual.shape, 'Summary dimensions')
    require(expected[keys].equals(actual[keys]), 'Summary identity keys')
    for column in expected:
        if column not in keys + ['mean_qp_ms']:
            close(expected[column], actual[column], f'Summary column {column}')


def verify(results: Path, output: Path, smoke: bool = False) -> dict:
    results = results.resolve()
    cfg = json.loads((results / 'configuration.json').read_text())
    n = int(cfg['episodes'])
    require(n >= 2, 'At least two missions')
    if not smoke:
        require(n == 500, 'Full verification requires 500 missions per method/budget')
    geo, design = b.designs()
    for key in ['geometry_M', 'shift_M', 'sample_covariance']:
        if isinstance(design[key], dict):
            for name in design[key]:
                close(design[key][name], cfg[key][name], f'Frozen {key}/{name}')
        else:
            close(design[key], cfg[key], f'Frozen {key}')
    require(cfg['seeds'] == b.SEEDS, 'Seed configuration')
    require(cfg['H'] == b.H and cfg['T'] == b.T, 'Mission and prediction horizons')
    require(cfg['lambda_grid'] == b.GRID.tolist(), 'Radius grid')
    streams = {1.: b.exogenous(n)}
    with np.load(results / 'exogenous_inputs.npz', allow_pickle=False) as arrays:
        for key, generated in zip(['x0', 'references', 'disturbances'], streams[1.]):
            require(np.array_equal(arrays[key], generated), f'Exogenous array {key} exactly regenerated')
    episodes = pd.read_csv(results / 'episodes.csv', float_precision='round_trip')
    check_summary(episodes, pd.read_csv(results / 'summary.csv', float_precision='round_trip'))
    entries = [(f, episodes) for f in sorted(results.glob('rollout_*.csv.gz'))]
    if not smoke:
        abl = pd.read_csv(results / 'ablation_episodes.csv', float_precision='round_trip')
        shift = pd.read_csv(results / 'shift_episodes.csv', float_precision='round_trip')
        check_summary(abl, pd.read_csv(results / 'ablation_summary.csv', float_precision='round_trip'))
        check_summary(shift, pd.read_csv(results / 'shift_summary.csv', float_precision='round_trip'))
        entries += [(f, abl) for f in sorted(results.glob('ablation_rollout_*.csv.gz'))]
        entries += [(f, shift) for f in sorted(results.glob('shift_rollout_*.csv.gz'))]
        for eps in [.05, .12]:
            entries.append((results / f'bound_ablation_EB_{eps:.2f}.csv.gz',
                            pd.read_csv(results / f'bound_ablation_EB_episodes_{eps:.2f}.csv', float_precision='round_trip')))
    table_cache = {}
    report = {'status': 'PASS', 'mode': 'smoke' if smoke else 'full',
              'rollout_files': len(entries), 'executed_stages_checked': 0,
              'main_stages_checked': 0, 'main_missions_checked': len(episodes),
              'calibration_max_abs_error': 0., 'max_recomputed_stage_cost_error': 0.,
              'max_recomputed_dynamics_error': 0., 'checks': []}
    geometry_for = {'oracle': 'ellipsoid', 'certified': 'ellipsoid', 'global_fixed': 'global',
                    'worstcase': 'worstcase', 'ball_backloaded': 'ball', 'ellipsoid_fixed': 'ellipsoid',
                    'ball_fixed': 'ball', 'ball_decision': 'ball', 'cert_ball': 'ball'}
    for filename, epdata in entries:
        st = pd.read_csv(filename, float_precision='round_trip')
        require(len(st) == n * b.T, filename.name + ': complete stage count')
        require(not st.duplicated(['episode', 't']).any(), filename.name + ': unique episode/time keys')
        st = st.sort_values(['episode', 't']).reset_index(drop=True)
        require(np.array_equal(st.t, np.tile(np.arange(b.T), n)), 'Consecutive time indices')
        require(np.array_equal(st.episode, np.repeat(np.arange(n), b.T)), 'Consecutive mission indices')
        method, eps, gamma = st.method.iloc[0], float(st.budget.iloc[0]), float(st.gamma.iloc[0])
        require(st.method.nunique() == st.budget.nunique() == st.gamma.nunique() == 1, 'Single rollout identity')
        if gamma not in streams:
            streams[gamma] = b.exogenous(n, gamma=gamma)
        x0, refs, shocks = streams[gamma]
        x = st[['x_position', 'x_velocity']].to_numpy()
        e = st[['error_position', 'error_velocity']].to_numpy()
        xn = st[['next_position', 'next_velocity']].to_numpy()
        gi = np.array([b.context(row) for row in x])
        require(np.array_equal(np.array(b.CONTEXTS)[gi], st.context), 'Measured-state context rule')
        close(x.reshape(n, b.T, 2)[:, 0], x0, 'Initial states')
        close(st.reference.to_numpy().reshape(n, b.T), refs, 'Reference schedule')
        close(e, shocks[st.episode, st.t, gi], 'Common fresh shocks')
        error = close(xn, x @ b.A.T + st.input.to_numpy()[:, None] * b.B + e, 'Plant dynamics')
        report['max_recomputed_dynamics_error'] = max(report['max_recomputed_dynamics_error'], error)
        close(x.reshape(n, b.T, 2)[:, 1:], xn.reshape(n, b.T, 2)[:, :-1], 'State continuity')
        cost = (st.x_position - st.reference)**2 + .2 * st.x_velocity**2 + .08 * st.input**2
        error = close(cost, st.stage_cost, 'Common realized stage cost')
        report['max_recomputed_stage_cost_error'] = max(report['max_recomputed_stage_cost_error'], error)
        viol = ((np.abs(xn) > b.XB).any(axis=1) | (abs(st.input.to_numpy()) > b.UB + 1e-12)).astype(int)
        require(np.array_equal(viol, st.violation), 'Integer physical violation flags')
        close(st.budget_before - st.charged_probability, st.budget_after, 'Unclipped per-step risk ledger')
        budgets = st.budget_before.to_numpy().reshape(n, b.T)
        after = st.budget_after.to_numpy().reshape(n, b.T)
        close(budgets[:, 0], np.full(n, eps), 'Initial risk budget')
        close(budgets[:, 1:], after[:, :-1], 'Budget continuity')
        require(st.budget_after.min() >= -1e-12, 'Affordable risk ledger')
        set_steps = st['lambda'].to_numpy() > 0
        require((st.loc[~set_steps, 'miss'] == -1).all(), 'Unselected-set sentinel')
        if method != 'nominal':
            matrices = geo[geometry_for[method]][gi]
            scores = np.linalg.norm(np.einsum('nij,nj->ni', matrices, e), axis=1)
            require(np.array_equal((scores[set_steps] > st['lambda'].to_numpy()[set_steps]).astype(int),
                                   st.loc[set_steps, 'miss']), 'Tube-escape flags')
        accepted = st.qp_primal_residual.notna()
        require((st.loc[accepted, 'qp_primal_residual'] <= 1e-10).all(), 'Stored hard-QP primal residuals')
        active = st.certified_step.to_numpy() == 1
        if method in ['certified', 'cert_ball']:
            require((st.loc[active, 'fallback'] == 0).all(), 'Certified steps use a hard plan')
            require((st.loc[active, 'violation'] <= st.loc[active, 'miss']).all(), 'First-step robust implication')
            require((st.groupby('episode').certified_step.diff().fillna(0) <= 0).all(), 'Permanent stopping rule')
            require((st.loc[~active, 'charged_probability'] == 0).all(), 'Uncertified continuation charge')
            require((st.loc[active, 'charged_probability'] <= st.loc[active, 'target'] + 1e-12).all(), 'Local target')
            if gamma not in table_cache:
                name = 'operational_risk_table.csv' if gamma == 1 else f'shift_{gamma:.1f}_risk_table.csv'
                table_cache[gamma] = pd.read_csv(results / name, float_precision='round_trip')
            table = table_cache[gamma]
            col = 'eb_standalone_probability' if filename.name.startswith('bound_ablation_EB_') else 'certified_probability'
            lookup = table[table.geometry == geometry_for[method]][['context', 'lambda', col]]
            merged = st.loc[active].merge(lookup, on=['context', 'lambda'], how='left', validate='many_to_one')
            require(merged[col].notna().all(), 'Operational table query exists')
            close(merged.charged_probability, merged[col], 'Certificate equals operational table entry')
            if active.any():
                nominal_next = x[active] @ b.A.T + st.loc[active, 'input'].to_numpy()[:, None] * b.B
                supports = np.array([[np.linalg.norm(np.linalg.solve(geo[geometry_for[method]][g].T, c))
                                      for c in np.eye(2)] for g in gi[active]])
                require((np.abs(nominal_next) + st.loc[active, 'lambda'].to_numpy()[:, None] * supports <= b.XB + 1e-9).all(),
                        'Independent first-step tightened-state constraint')
        selected = epdata[(epdata.method == method) & (epdata.budget == eps) & (epdata.gamma == gamma)].sort_values('episode')
        require(len(selected) == n, 'Episode record count')
        grouped = st.groupby('episode', sort=True)
        for step_col, episode_col in [('violation', 'violation_count'), ('fallback', 'fallback_steps'),
                                     ('certified_step', 'certified_steps')]:
            require(np.array_equal(grouped[step_col].sum(), selected[episode_col]), episode_col)
        close(grouped.stage_cost.mean(), selected.common_cost, 'Mean episode cost')
        close(grouped.charged_probability.sum(), selected.total_spend, 'Total mission spend')
        close(grouped.budget_after.min(), selected.minimum_budget, 'Minimum mission budget')
        expected_miss = st.assign(counted_miss=np.maximum(st['miss'], 0)).groupby('episode').counted_miss.sum()
        require(np.array_equal(expected_miss, selected.miss_count_on_set_steps), 'Mission tube-miss count')
        hard = (st.violation * st.certified_step).groupby(st.episode).sum()
        require(np.array_equal(hard, selected.hard_violation_count), 'Stopped physical count')
        if method in ['certified', 'cert_ball']:
            require(np.array_equal((grouped.certified_step.sum() == b.T).astype(int), selected.complete_certificate),
                    'Mission certificate completion flag')
        report['executed_stages_checked'] += len(st)
        if filename.name.startswith('rollout_'):
            report['main_stages_checked'] += len(st)
    report['checks'].append('All stored rollouts: dynamics, contexts, costs, physical flags, tube misses, ledgers and episode aggregation')
    # Regenerate each calibration realization with its fixed design and seed.
    prefixes = [('operational', 32768, 1.)]
    if not smoke:
        prefixes += [(f'sample_n{k}', k, 1.) for k in [128, 256, 512, 2048, 8192, 32768]]
        prefixes += [(f'shift_{gamma:.1f}', 32768, gamma) for gamma in [.5, 1.5, 2.]]
    fields = {'empirical': 'empirical_envelope', 'certified': 'certified_probability',
              'sample_variance': 'sample_variance', 'eb_split': 'eb_split_probability',
              'binomial_split': 'binomial_split_probability', 'eb_standalone': 'eb_standalone_probability'}
    for prefix, nbase, gamma in prefixes:
        maps, details = b.calibration(geo, nbase=nbase, gamma=gamma, compute_reference=False)
        require(details['delta_empirical_bernstein'] + details['delta_binomial'] == b.DELTA, 'Confidence split')
        saved = pd.read_csv(results / f'{prefix}_risk_table.csv', float_precision='round_trip')
        metadata = json.loads((results / f'{prefix}_metadata.json').read_text())
        for key in ['counts', 'context_caps', 'binomial_failure_per_cell']:
            close(details[key], metadata[key], f'Calibration metadata {prefix}/{key}')
        for name, mp in maps.items():
            for g, context in enumerate(b.CONTEXTS):
                rows = saved[(saved.geometry == name) & (saved.context == context)].sort_values('lambda')
                require(np.array_equal(rows.miss_count, mp['miss_count'][g]), 'Integer calibration misses')
                for field, column in fields.items():
                    error = close(rows[column], mp[field][g], f'{prefix}/{name}/{context}/{field}', atol=2e-14, rtol=2e-14)
                    report['calibration_max_abs_error'] = max(report['calibration_max_abs_error'], error)
                require((np.diff(rows.certified_probability) <= 1e-14).all(), 'Monotone risk map')
        require((saved.certified_probability <= saved.eb_split_probability + 1e-14).all(), 'Combined <= EB component')
        require((saved.certified_probability <= saved.binomial_split_probability + 1e-14).all(), 'Combined <= binomial component')
    report['calibration_tables_regenerated'] = len(prefixes)
    report['checks'].append('Independent design and exogenous streams; every calibration component regenerated')
    if not smoke:
        pairs = pd.read_csv(results / 'paired_mpc_values.csv', float_precision='round_trip')
        queries = pd.read_csv(results / 'paired_queries.csv', float_precision='round_trip')
        require(len(queries) == 240 and not queries.duplicated(['episode', 't']).any(), '240 unique fixed queries')
        joined = pairs.merge(queries[['episode', 't', 'target']], on=['episode', 't'], validate='many_to_one')
        require(len(joined) == 1440, 'Six sample sizes retain all 240 queries')
        close(joined.alpha, joined.target, 'Identical paired local targets')
        feasible = pairs.both_feasible == 1
        close(pairs.loc[feasible, 'gap'], pairs.loc[feasible, 'J_certified'] - pairs.loc[feasible, 'J_reference'],
              'Same-problem value gaps')
        require(pairs.loc[feasible, 'gap'].min() >= -1e-7, 'Value ordering within solver tolerance')
        require(pairs.loc[~feasible, ['J_certified', 'J_reference', 'gap']].isna().all().all(), 'Failed-pair values remain missing')
        sweep = pd.read_csv(results / 'paired_sweep.csv', float_precision='round_trip')
        for _, row in sweep.iterrows():
            subset = pairs[pairs.nbase == row.nbase]
            require(len(subset) == int(row.queries), 'Paired denominator')
            require(int(subset.both_feasible.sum()) == int(row.feasible_queries), 'Paired feasible count')
            close(subset.loc[subset.both_feasible == 1, 'gap'].mean(), row.mean_same_problem_gap, 'Paired mean value gap')
        cmp = pd.read_csv(results / 'certificate_comparison_paired.csv', float_precision='round_trip')
        join = pairs.merge(cmp, on=['nbase', 'episode', 't'], suffixes=('_main', '_bound'), validate='one_to_one')
        require(len(join) == 1440, 'Bound-comparison query count')
        close(join.alpha_main, join.alpha_bound, 'Bound-comparison targets')
        require(np.array_equal(join.both_feasible, join.hybrid_feasible), 'Bound-comparison feasibility flags')
        good = join.both_feasible == 1
        close(join.loc[good, 'J_certified'], join.loc[good, 'J_hybrid'], 'Bound-comparison hybrid values')
        close(join.loc[good, 'J_reference_main'], join.loc[good, 'J_reference_bound'], 'Bound-comparison reference values')
        report['matched_queries'] = len(queries)
        report['matched_comparisons_per_rule'] = len(pairs)
        report['checks'].append('Fixed paired-query identity, failed-query retention and paired value gaps')
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--results', type=Path, default=ROOT / 'reference/results')
    parser.add_argument('--output', type=Path, default=ROOT / 'build/verification.json')
    parser.add_argument('--smoke', action='store_true')
    args = parser.parse_args()
    report = verify(args.results, args.output, args.smoke)
    print(f"PASS: {report['executed_stages_checked']} executed stages; {report['calibration_tables_regenerated']} regenerated calibration tables")


if __name__ == '__main__':
    main()
