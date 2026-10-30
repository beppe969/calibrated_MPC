"""Mathematical and controller unit tests, independent of archived rollout files."""
from pathlib import Path
import sys
import unittest
import numpy as np
from scipy.stats import binom

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import certified_benchmark as b


class CoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.geo, cls.detail = b.designs()
        cls.qp = b.TubeQP(cls.geo)

    def test_nonsymmetric_ellipsoid_support(self):
        M = np.array([[1., 0.], [1., 1.]])
        c = np.array([0., 1.])
        self.assertAlmostEqual(np.linalg.norm(np.linalg.solve(M.T, c)), np.sqrt(2), places=14)
        v = np.linalg.solve(M.T, c)
        e = np.linalg.solve(M, v / np.linalg.norm(v))
        self.assertAlmostEqual(np.linalg.norm(M @ e), 1., places=14)
        self.assertAlmostEqual(c @ e, np.sqrt(2), places=14)

    def test_finite_sum_tube_support(self):
        c = np.array([.7, -.3]); M = self.geo['ellipsoid'][1]
        attained, support = 0., 0.
        for j in range(5):
            power = np.linalg.matrix_power(b.AK, j)
            v = np.linalg.solve(M.T, power.T @ c)
            e = np.linalg.solve(M, v / np.linalg.norm(v))
            attained += c @ power @ e
            support += np.linalg.norm(v)
        self.assertAlmostEqual(attained, support, places=14)

    def test_riccati_equation_and_closed_loop_stability(self):
        residual = b.A.T @ b.P @ b.A - b.P + b.Q - np.outer(b.A.T @ b.P @ b.B, b.B @ b.P @ b.A) / (b.R + b.B @ b.P @ b.B)
        self.assertLess(np.max(np.abs(residual)), 1e-12)
        self.assertLess(np.max(np.abs(np.linalg.eigvals(b.AK))), 1.)

    def test_condensed_dynamics_cost_and_gradient(self):
        x = np.array([.3, -.1]); u = np.random.default_rng(120).uniform(-.3, .3, b.H)
        direct = [x.copy()]
        for v in u:
            direct.append(b.A @ direct[-1] + b.B * v)
        direct = np.array(direct)
        condensed = np.einsum('lij,j->li', self.qp.F, x) + np.einsum('lij,j->li', self.qp.S, u)
        np.testing.assert_allclose(condensed, direct, atol=2e-15, rtol=0.)
        ref = np.column_stack([np.linspace(.5, 2., b.H + 1), np.zeros(b.H + 1)])
        e = np.einsum('lij,j->li', self.qp.F, x) - ref
        q = 2 * np.einsum('lij,lik,lk->j', self.qp.S, self.qp.W, e)
        const = np.einsum('li,lij,lj->', e, self.qp.W, e)
        f = lambda v: .5 * v @ self.qp.Qh @ v + q @ v + const
        cost = sum((direct[j] - ref[j]) @ self.qp.W[j] @ (direct[j] - ref[j]) for j in range(b.H + 1)) + b.R * (u @ u)
        self.assertAlmostEqual(f(u), cost, places=11)
        h = 1e-5
        gradient = np.array([(f(u + h * ei) - f(u - h * ei)) / (2 * h) for ei in np.eye(b.H)])
        np.testing.assert_allclose(gradient, self.qp.Qh @ u + q, atol=1e-8, rtol=1e-8)

    def test_nested_radius_value_and_primal_check(self):
        values = []
        for radius in b.GRID:
            result = self.qp.solve(np.array([.3, -.1]), np.linspace(.5, 2., b.H + 1), 'ellipsoid', 0, float(radius))
            self.assertTrue(result['ok'])
            self.assertLessEqual(result['primal_residual'], -b.PADDING + 1e-10)
            values.append(result['J'])
        self.assertGreaterEqual(min(np.diff(values)), -1e-7)

    def test_geometric_infeasibility(self):
        result = self.qp.solve(np.array([4.1, 0.]), np.zeros(b.H + 1), None, 0, 0.)
        self.assertFalse(result['ok'])
        self.assertEqual(result['reason'], 'geometric_infeasibility')
        result = self.qp.solve(np.zeros(2), np.zeros(b.H + 1), 'ellipsoid', 2, 100.)
        self.assertFalse(result['ok'])

    def test_grid_attainability_and_tie_break(self):
        self.assertIsNone(b.choose(np.array([.3, .2, .1]), .09))
        self.assertEqual(b.choose(np.array([.3, .2, .1]), .2), 1)
        self.assertEqual(b.choose(np.array([.1, .1, .1]), .1), 0)

    def test_binomial_endpoints_and_inverted_tails(self):
        tau = b.DELTA / (2 * 3 * len(b.GRID))
        for n in (1, 2, 5, 20, 80):
            k = np.arange(n + 1)
            for failure in (.05, .01, tau):
                upper = b.binomial_upper(k, n, failure)
                self.assertTrue(np.all(np.diff(upper) >= 0))
                self.assertEqual(upper[-1], 1.)
                self.assertAlmostEqual(upper[0], -np.expm1(np.log(failure) / n), places=14)
                np.testing.assert_allclose(binom.cdf(k[:-1], n, upper[:-1]), failure, atol=2e-13, rtol=0.)
                q = np.linspace(0., 1., 401)
                probability = np.sum(binom.pmf(k[:, None], n, q[None, :]) * (q[None, :] > upper[:, None]), axis=0)
                self.assertLessEqual(probability.max(), failure + 2e-13)

    def test_binomial_input_validation(self):
        for counts, n, failure in [(np.array([.5]), 20, .05), (np.array([-1]), 20, .05),
                                   (np.array([21]), 20, .05), (np.array([0]), 0, .05),
                                   (np.array([0]), 20, 0.)]:
            with self.assertRaises(ValueError):
                b.binomial_upper(counts, n, failure)

    def test_frozen_design_reproducibility(self):
        again, detail = b.designs()
        for name in self.geo:
            np.testing.assert_array_equal(self.geo[name], again[name])
        self.assertEqual(self.detail, detail)

    def test_context_boundaries(self):
        self.assertEqual(b.context(np.array([1.6, 0.])), 0)
        self.assertEqual(b.context(np.array([1.61, 0.])), 1)
        self.assertEqual(b.context(np.array([3., 0.])), 1)
        self.assertEqual(b.context(np.array([3.01, 0.])), 2)

    def test_full_horizon_input_margin(self):
        halfwidths = [1 - 3.5 * self.qp.margins[('ellipsoid', g)][1][7] for g in range(3)]
        self.assertGreater(min(halfwidths), .4621)
        self.assertLess(min(halfwidths), .4623)

    def test_recovery_preserves_unspent_ledger(self):
        # Force unattainability while retaining a feasible nominal recovery QP.
        maps = {'ellipsoid': {'certified': np.full((3, len(b.GRID)), .1)}}
        x0 = np.zeros((2, 2)); refs = np.zeros((2, b.T)); shocks = np.zeros((2, b.T, 3, 2))
        ep, steps = b.run({'gamma': 1.}, maps, self.geo, 'certified', .05,
                          x0, refs, shocks, self.qp)
        self.assertTrue((steps.certified_step == 0).all())
        self.assertTrue((steps.fallback == 1).all())
        self.assertTrue((steps.charged_probability == 0.).all())
        self.assertTrue((steps.budget_after == .05).all())
        self.assertTrue((ep.complete_certificate == 0).all())
        self.assertTrue((ep.violation_count == 0).all())


if __name__ == '__main__':
    unittest.main(verbosity=2)
