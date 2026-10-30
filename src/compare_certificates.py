#!/usr/bin/env python3
"""Compare empirical-Bernstein and combined certificates on identical data.

Run after certified_benchmark.py. This comparison keeps every model parameter
and random draw fixed. Each standalone EB table has its own 1-delta statement;
the operational combined table allocates delta/2 to each constituent family.
"""
from pathlib import Path
import argparse, json
import numpy as np
import pandas as pd
import certified_benchmark as b


def main() -> None:
    parser=argparse.ArgumentParser()
    parser.add_argument('--results',type=Path,default=Path('results'))
    args=parser.parse_args(); out=args.results
    cfg=json.loads((out/'configuration.json').read_text())
    z=np.load(out/'exogenous_inputs.npz'); x0=z['x0']; refs=z['references']; disturbances=z['disturbances']
    geo,_=b.designs(); solver=b.TubeQP(geo)
    maps,_=b.calibration(geo,compute_reference=False)
    for table in maps.values(): table['certified']=table['eb_standalone']
    summary=[]
    main_summary=pd.read_csv(out/'summary.csv')
    for eps in [.05,.12]:
        ep,st=b.run({'gamma':1.},maps,geo,'certified',eps,x0,refs,disturbances,solver)
        st.to_csv(out/f'bound_ablation_EB_{eps:.2f}.csv.gz',index=False,compression='gzip')
        ep.to_csv(out/f'bound_ablation_EB_episodes_{eps:.2f}.csv',index=False)
        se=b.summarize(ep); se['certificate_rule']='EB'; summary.append(se)
        h=main_summary[(main_summary.method=='certified')&(main_summary.budget==eps)].copy()
        h['certificate_rule']='combined';summary.append(h)
    comparison=pd.concat(summary,ignore_index=True)
    comparison.to_csv(out/'certificate_comparison_summary.csv',index=False)
    # The same fixed queries are used for both bound rules and every sample size.
    queries=pd.read_csv(out/'paired_queries.csv'); matched=pd.read_csv(out/'paired_mpc_values.csv')
    records=[]
    for nbase in sorted(matched.nbase.unique()):
        table=pd.read_csv(out/f'sample_n{nbase}_risk_table.csv')
        table=table[table.geometry=='ellipsoid']
        for _,q in queries.iterrows():
            g=b.CONTEXTS.index(q.context); ep=int(q.episode); t=int(q.t)
            curve=table[table.context==q.context].sort_values('lambda').eb_standalone_probability.to_numpy()
            i=b.choose(curve,q.target)
            mm=matched[(matched.nbase==nbase)&(matched.episode==ep)&(matched.t==t)].iloc[0]
            rec={'nbase':int(nbase),'episode':ep,'t':t,'alpha':q.target,
                'hybrid_feasible':int(mm.both_feasible),'EB_feasible':0,
                'J_hybrid':mm.J_certified,'J_reference':mm.J_reference,'J_EB':np.nan,
                'gap_hybrid':mm.gap,'gap_EB':np.nan}
            if i is not None and mm.both_feasible:
                r=refs[ep,np.minimum(np.arange(t,t+b.H+1),b.T-1)]
                result=solver.solve(np.array([q.x_position,q.x_velocity]),r,'ellipsoid',g,float(b.GRID[i]))
                if result['ok']:
                    rec.update(EB_feasible=1,J_EB=result['J'],gap_EB=result['J']-mm.J_reference)
            # If only EB is affordable, explicitly evaluate reference and EB.
            elif i is not None:
                truecurve=table[table.context==q.context].sort_values('lambda').reference_probability.to_numpy()
                oi=b.choose(truecurve,q.target)
                if oi is not None:
                    r=refs[ep,np.minimum(np.arange(t,t+b.H+1),b.T-1)]
                    xx=np.array([q.x_position,q.x_velocity])
                    rr=solver.solve(xx,r,'ellipsoid',g,float(b.GRID[oi]))
                    ee=solver.solve(xx,r,'ellipsoid',g,float(b.GRID[i]))
                    if rr['ok'] and ee['ok']:
                        rec.update(EB_feasible=1,J_EB=ee['J'],J_reference=rr['J'],gap_EB=ee['J']-rr['J'])
            records.append(rec)
    pairs=pd.DataFrame(records);pairs.to_csv(out/'certificate_comparison_paired.csv',index=False)
    rows=[]
    for n,s in pairs.groupby('nbase'):
        both=s[(s.hybrid_feasible==1)&(s.EB_feasible==1)]
        rows.append({'nbase':int(n),'queries':len(s),'hybrid_feasible':int(s.hybrid_feasible.sum()),
            'EB_feasible':int(s.EB_feasible.sum()),'hybrid_fraction':s.hybrid_feasible.mean(),
            'EB_fraction':s.EB_feasible.mean(),'joint_pairs':len(both),
            'mean_hybrid_gap_on_joint_pairs':both.gap_hybrid.mean(),
            'mean_EB_gap_on_joint_pairs':both.gap_EB.mean()})
    pd.DataFrame(rows).to_csv(out/'certificate_comparison_sweep.csv',index=False)
    (out/'certificate_comparison_validation.json').write_text(json.dumps({
        'QP_calls':solver.calls,'QP_failures':solver.failures,
        'max_accepted_primal_residual':solver.max_primal_residual,
        'full_size_mean_gap_difference':float(pairs[pairs.nbase==32768].gap_EB.mean()-pairs[pairs.nbase==32768].gap_hybrid.mean())},indent=2))
    print(comparison.to_string(index=False));print(pd.DataFrame(rows).to_string(index=False))

if __name__=='__main__': main()
