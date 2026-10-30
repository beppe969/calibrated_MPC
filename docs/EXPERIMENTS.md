# Experiment specification

## Plant and controller

The constant model is

```text
A = [[1, 0.15], [0, 1]]
B = [0.01125, 0.15]
Q = diag(1, 0.2)
R = 0.08
prediction horizon H = 8
mission length T = 20
state bounds = [4, 2]
input bound = 1
```

The terminal cost and feedback gain are obtained from the discrete algebraic
Riccati equation. Their full-precision values are in
`reference/results/configuration.json`. Every optimization is a condensed
convex QP in eight nominal inputs. It uses the measured state as its initial
condition and freezes the current context throughout its horizon. The candidate
radius is common to all prediction stages.

For a disturbance ellipsoid defined by `||M e|| <= lambda`, the support in
direction `c` is `lambda * ||solve(M.T, c)||`. State and input supports are
propagated for the full horizon. This includes the stage-7 input tightening and
the stage-8 terminal state constraint.

SLSQP uses analytic derivatives, `ftol=1e-9` and at most 100 iterations.
Constraints are padded inward by `1e-6`. Acceptance requires the solver's success
flag together with an independent unpadded primal-residual check at `1e-10`.
A shifted preceding solution provides the warm start during each mission.
A selected grid radius is the smallest one meeting the risk target. Monotonic
constraint tightening makes this choice consistent with the smallest-radius
optimal-value tie break.

## Contexts and disturbances

The context statistic is `max(abs(x_position)/4, abs(x_velocity)/2)`.
The low-context boundary is inclusive at `0.4`, and the medium-context boundary
is inclusive at `0.75`. The remaining states have high context.

Errors are `E=0.05*xi_g`, where `xi_g` has a bivariate Student-t distribution
with degrees of freedom `(12, 8, 5)` and these scale matrices:

```text
L: [[0.0025, 0.0002], [0.0002, 0.0030]]
M: [[0.0055, 0.0006], [0.0006, 0.0045]]
H: [[0.0120, 0.0016], [0.0016, 0.0070]]
```

These are scale matrices. Their corresponding covariance matrices include the
factor `nu/(nu-2)`.

The prescribed within-context shift uses

```text
a_g = min(0.45, b_g*gamma),  b = (0.06, 0.14, 0.28)
w_g(e) = 1 + a_g*tanh((||D_g e|| - 1)/0.45)
D_g = diag(1 / (alpha_g * sqrt(Var(E_k))))
alpha = (3.6, 2.8, 2.2)
```

Fresh rejection sampling generates the density proportional to `w_g` relative
to the calibration law. At every mission/time pair, a fresh error is generated
for each possible context. A controller selects the error indexed by its current
context. All methods share these exogenous arrays, so their context-dependent
executed errors can differ when their state trajectories visit different contexts.

The upper density-ratio envelope used for calibration is `w_g/(1-a_g)`.
Its deterministic cap is `(1+a_g)/(1-a_g)`. The normalizer is bounded below by
`1-a_g`. Angular/radial numerical quadrature supplies a reference miss curve;
the certified table depends only on the calibration samples and this envelope.

## Independent design and calibration

There are 4096 design samples per context. The main calibration counts are
`(131072, 65536, 32768)`. The radius grid is

```text
0.4, 0.6, 0.8, 1.0, 1.3, 1.6, 1.9, 2.2, 2.6, 3.0, 3.5
```

The design covariance determines the fixed ellipsoid matrix through
`inv(cholesky(alpha_g**2 * covariance_g + 1e-6*I))`.
Context balls use factors `(3, 2.4, 2)` multiplying
`sqrt(trace(covariance_g)/2)`. The global ball uses factor `2.5` and the pooled
design covariance. Full matrices appear in `configuration.json`.

The operational certificate is the prefix minimum of the pointwise minimum
of two upper bounds, capped at one. One component is empirical Bernstein for
the envelope-weighted miss variable. The other is the context cap multiplied
by a one-sided exact-binomial upper limit for the integer unweighted miss count.

The total error allocation is `delta=0.1` for each fixed geometry and shift
configuration. Each component family receives `0.05`. Within a family the
allocation is uniform across the `3*11` context/radius cells. Joint adaptive
selection across different geometry families or shift configurations would
require an additional confidence allocation.

The standalone empirical-Bernstein comparison uses the full `delta=0.1` with
the common cap `16/9`. Consequently that comparison changes both the component
combination and the treatment of the context caps. The design samples and
calibration observations remain common.

## Methods

| Code identifier | Definition |
|---|---|
| `oracle` | Context ellipsoids; numerical reference risk; remaining-budget equal-share target |
| `certified` | Context ellipsoids; combined certificate; remaining-budget equal-share target |
| `global_fixed` | Global ball; pooled upper-weighted empirical quantile at `eps/T` |
| `worstcase` | High-context ellipsoid at every state; high-context empirical curve at `eps/(T-t)` |
| `ball_backloaded` | Context balls; empirical curve; remaining budget allocated with powers `(t+1)^1.6` |
| `ellipsoid_fixed` | Context ellipsoids; empirical quantile at fixed target `eps/T` |
| `nominal` | Same QP with zero disturbance tube |
| `ball_fixed` | Context balls; empirical quantile at `eps/T`; ablation |
| `ball_decision` | Context balls; empirical curve with remaining-budget equal-share target; ablation |
| `cert_ball` | Context balls; combined certificate and remaining-budget equal-share target; ablation |

A fixed-quantile method uses a constant target; a context-specific radius can
still change when the context changes. The empirical-risk comparator methods
carry no finite-sample certification claim. Risk ledgers for `oracle` and the
budgeted empirical comparators use their corresponding numerical or empirical
probabilities.

SC-MPC stops certification permanently if its target is unattainable or its
hard QP fails. The subsequent moves use nominal-QP recovery, followed by
saturated LQR when that QP fails. Uncertified continuation has zero certificate
charge and remains included in the realized cost and physical violation counts.
The complete-mission certificate flag records whether all 20 steps stayed
certified. The physical safety theorem retains its hard-feasibility and
conditional-law hypotheses.

## Study definitions

| Study | Configuration | Records |
|---|---|---|
| Main tradeoff | 500 missions; six budgets from 0.05 to 0.24; seven methods | `episodes.csv`, `summary.csv`, 37 main rollout files |
| Calibration size | Base counts 128, 256, 512, 2048, 8192 and 32768; 240 fixed queries | `paired_*`, `sample_n*` |
| Geometry/selection ablation | Six method variants at budget 0.12; 500 missions each | `ablation_*` |
| Prescribed shift | Gamma 0.5, 1, 1.5 and 2; SC-MPC at budget 0.12 | `shift_*` |
| Certificate comparison | Standalone EB and combined certificates at budgets 0.05 and 0.12; same fixed-query set | `certificate_comparison_*`, `bound_ablation_EB_*` |

Nominal MPC is budget-independent, so its single main run is reused at every
budget in Figure 3. Several ablation and shift rows likewise reuse the relevant
main-study records. Their identity is retained in the aggregate episode files.

The paired queries are a deterministic, uniformly indexed selection of 240
certified stages at budget 0.12. Every sample size uses exactly these states and
targets. Failed comparisons remain in the denominator. The reported optimal-value
gap uses the two QPs at the same query; closed-loop costs use each method's own
executed trajectory.

Each sample-size configuration resets the calibration seed and generates arrays
with that configuration's sample counts. Random generation depends on the call
shapes. The reference records preserve the resulting samples through their seeds
and risk-table sufficient statistics.

## Seeds and metrics

| Stream | Seed |
|---|---:|
| Independent geometry design | 101 |
| Calibration | 2 |
| Reference signals | 42 |
| Initial states | 43 |
| Deployment shocks for context index `g=0,1,2` | `7 + 1000*g` |

Initial position is uniform on `[-0.8,0.8]`; initial velocity is uniform on
`[-0.35,0.35]`. Each known reference is constant over steps 0--6, 7--13 and
14--19. A segment has probability 0.75 of using a random-sign uniform magnitude
in `[2.2,3.7]`; otherwise it is uniform on `[-1.2,1.2]`. Beyond the mission,
planning holds the last reference constant.

Physical violations count `x_(t+1)` outside its box or the applied input outside
its bound. The mission count is the sum of integer flags. Table II reports the
mean count over 500 missions. Tube misses count selected-set escapes separately.
Fallback rate divides fallback stages by the total number of executed stages.

The common realized cost is the average over all executed stages of
`(x_position-reference)^2 + 0.2*x_velocity^2 + 0.08*input^2`.
The recorded `mpc_value` also includes the horizon's terminal cost and has a
different meaning from this realized metric.
