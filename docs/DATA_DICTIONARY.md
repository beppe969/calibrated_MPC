# Data dictionary

All CSV files have headers and use the decimal point. Blank numeric fields are
missing values. Gzip-compressed CSV files can be read directly by pandas.
NPZ files contain numeric arrays and can be loaded with `allow_pickle=False`.

The experiment units are the model's state/input units; the sample period is
implicit in the plant matrices. `t` and `episode` are zero-based.

## Stage records

Files matching `rollout_*.csv.gz` contain the main study. Additional records
use `ablation_rollout_*`, `shift_rollout_*` and `bound_ablation_EB_*`.
Each file has 500 missions and 20 stages per mission in the complete study.

| Column | Meaning |
|---|---|
| `method` | Implementation identifier; see `EXPERIMENTS.md` |
| `budget` | Requested initial mission budget |
| `gamma` | Prescribed within-context shift parameter |
| `episode` | Mission index within this method/configuration |
| `t` | Executed stage, from 0 through 19 |
| `context` | Measured-state context: L, M or H |
| `x_position`, `x_velocity` | Current state before the input and disturbance |
| `reference` | Current position reference; velocity reference is zero |
| `input` | Applied scalar control |
| `error_position`, `error_velocity` | Fresh additive disturbance selected for the current context |
| `next_position`, `next_velocity` | Actual successor state |
| `lambda` | Radius of the implemented uncertainty set; zero when no set was used |
| `target` | Pre-disturbance local risk target used by the method |
| `table_probability` | Probability assigned to a selected grid candidate; can remain recorded if its QP subsequently fails |
| `charged_probability` | Actual ledger debit; uncertified continuation has zero certificate debit |
| `budget_before`, `budget_after` | Remaining ledger balance before and after this debit |
| `certified_step` | One for a certified hard step of SC-MPC or its certified-ball ablation |
| `fallback` | One when uncertainty-set planning is abandoned or nominal-QP recovery requires saturated LQR |
| `was_certification_active` | Certification-active internal flag at the start of the step; interpreted for certified methods |
| `violation` | Integer physical state/input violation flag for the implemented first step |
| `miss` | Integer escape flag for an implemented set; `-1` when no set was implemented |
| `stage_cost` | Common realized quadratic state/input cost at the current state |
| `mpc_value` | Optimal nominal horizon objective of the accepted QP; missing on saturated-LQR recovery |
| `qp_ms` | Measured elapsed milliseconds for selection, QP calls and any recovery during this stage |
| `qp_primal_residual` | Maximum residual against unpadded constraints of the final accepted QP; negative means strict feasibility |

For empirical and reference-risk methods, a probability in a ledger represents
that method's probability estimate. `certified_step` identifies the steps that
receive the operational finite-sample certificate. A recovery QP can be hard
feasible while its step remains uncertified under the mission-risk construction.

## Episode records

`episodes.csv` contains 18,500 main-study missions. The other episode tables
aggregate the corresponding additional study, including reused main missions.

| Column | Meaning |
|---|---|
| `method`, `budget`, `gamma` | Method/configuration identity |
| `episode` | Mission index |
| `violation_count` | Sum of physical violation flags over all 20 executed stages |
| `miss_count_on_set_steps` | Sum of tube escapes over stages with an implemented set |
| `fallback_steps` | Number of stages flagged as fallback |
| `certified_steps` | Number of steps carrying a certificate |
| `hard_violation_count` | Sum of physical violations restricted to `certified_step=1` |
| `total_spend` | Sum of actual ledger debits |
| `minimum_budget` | Smallest remaining balance during the mission |
| `common_cost` | Average realized stage cost, normalized by 20 |
| `qp_ms` | Average stage timing in milliseconds |
| `hard_qp_failures` | Failed selected-radius QP attempts; a missing affordable radius is counted separately through the fallback flag |
| `complete_certificate` | One for 20 certified steps, zero for a stopped certificate, and `-1` for methods outside the certified family |

## Summary tables

`summary.csv` has 37 main rows: six budgets for each tube method and one
budget-independent nominal-MPC run. Other `*_summary.csv` tables have the same
metrics, with additional study identifiers where applicable.

| Column | Meaning |
|---|---|
| `method`, `budget`, `gamma` | Grouping keys |
| `episodes` | Number of missions in the row |
| `total_violations` | Integer physical violation total |
| `mean_violation_count` | Total violations divided by missions |
| `per_step_violation_rate` | Total violations divided by missions times 20 |
| `mean_set_miss_count` | Average mission tube-miss count |
| `common_cost` | Average of the episode common costs |
| `cost_standard_error` | Sample standard deviation of episode costs divided by square root of mission count |
| `fallback_step_rate` | Fallback stages divided by total stages |
| `complete_certificate_fraction` | Fraction of missions with 20 certified steps; missing for other methods |
| `mean_hard_violations` | Average stopped physical-violation count |
| `max_total_spend` | Largest mission ledger total |
| `minimum_budget` | Smallest recorded balance across missions |
| `mean_qp_ms` | Average measured stage timing |
| `certificate_rule` | `EB` or `combined` in the certificate-comparison summary |

The reported standard error conditions on the recorded design/calibration
realization. Each method's trajectories use the common exogenous random inputs.

## Risk tables and metadata

`operational_risk_table.csv` is the main table. Files `sample_n*_risk_table.csv`
refer to calibration-size configurations. Files `shift_*_risk_table.csv` refer
to prescribed-shift configurations. Each has 132 rows across four geometry
families, three contexts and eleven radii.

| Column | Meaning |
|---|---|
| `geometry` | `ellipsoid`, `ball`, `global` or `worstcase` |
| `context` | Residual-law context |
| `lambda` | Candidate radius |
| `empirical_envelope` | Mean of upper-envelope-weighted miss variables |
| `certified_probability` | Operational combined bound after capping and prefix minima |
| `reference_probability` | Numerical deployment-law risk from Student-t quadrature |
| `miss_count` | Unweighted integer calibration miss count |
| `sample_variance` | Unbiased sample variance of the envelope-weighted miss variable |
| `eb_split_probability` | Prefix-closed EB component using half the confidence allocation |
| `binomial_split_probability` | Prefix-closed context-cap-scaled exact-binomial component |
| `eb_standalone_probability` | Standalone EB comparison using full delta and a common context cap |

The matching `*_metadata.json` records sample counts and confidence allocations.
It includes deterministic weight caps together with quadrature normalizers and
error estimates. `configuration.json` contains the model and frozen geometry.

## Matched queries and calibration-size records

`paired_queries.csv` contains the 240 selected SC-MPC stage records at budget
0.12. `paired_mpc_values.csv` contains every query at six calibration sizes.

| Column | Meaning |
|---|---|
| `nbase` | Base calibration size; context counts are `(4,2,1)*nbase` |
| `episode`, `t`, `context` | Identity of the fixed query |
| `alpha` | Fixed local target for that query |
| `certified_index`, `reference_index` | Zero-based chosen grid indices; `-1` denotes unavailable radius |
| `both_feasible` | One when both same-query QPs were solved successfully |
| `J_certified`, `J_reference` | Optimal QP values on the same state/target/reference query |
| `gap` | `J_certified-J_reference`; missing when a comparison is unavailable |

`paired_sweep.csv` reports `queries` and `feasible_queries` at each `nbase`.
It includes the feasible fraction and the mean/minimum gaps on the feasible
subset. `zero_miss_floor_best_mission` is 20 times the smallest zero-miss
exact-binomial component across contexts at that calibration size.

`certificate_comparison_paired.csv` records the same query keys and targets.
Its feasibility columns are `hybrid_feasible` and `EB_feasible`. Value columns
are `J_hybrid`, `J_reference` and `J_EB`; corresponding differences are
`gap_hybrid` and `gap_EB`.

`certificate_comparison_sweep.csv` retains the full denominator in `queries`.
It reports the two feasible counts and fractions. `joint_pairs` counts their
intersection; both `mean_*_gap_on_joint_pairs` fields use that same intersection.

## NumPy inputs

`reference/results/exogenous_inputs.npz` contains:

| Array | Shape | Meaning |
|---|---|---|
| `x0` | `(500,2)` | Initial state of every mission |
| `references` | `(500,20)` | Position reference at each executed stage |
| `disturbances` | `(500,20,3,2)` | Fresh main-setting shock for each potential context |

`reference/inputs/design_calibration.npz` contains the independent raw samples:

| Array | Shape |
|---|---|
| `design_L`, `design_M`, `design_H` | Each `(4096,2)` |
| `calibration_L` | `(131072,2)` |
| `calibration_M` | `(65536,2)` |
| `calibration_H` | `(32768,2)` |

Their metadata record the seeds and shapes. The source generation routines
recreate these arrays. Shift-study shock arrays are regenerated by `exogenous()`;
the executed entries are also present in their rollout CSV files.

## Validation files

The numerical engine writes `validation.json` and
`certificate_comparison_validation.json` inside each results directory.
QP-call counts include attempts that fail and the matched-query optimizations.

The top-level `validation/` directory contains the package verification reports.
`full_rerun_comparison.json` gives per-column maximum discrepancies for all 84
results files. Timing columns are explicitly excluded. The manifest supplies
SHA-256 hashes for the delivered reference records and package sources.
