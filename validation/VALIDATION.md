# Validation record

## Complete local reproduction

The public `python reproduce.py all` command completed successfully in the
recorded environment. Its elapsed time was **272.1 seconds** on this machine.
The numerical experiment used 432,070 QP calls, and the certificate comparison
used 20,712 additional calls, for **452,782 QP calls** in total.

All **84 numerical results files** matched the supplied records. Every compared
CSV numerical discrepancy was **zero**. Integer flags and selected radii matched;
the exogenous NPZ arrays matched exactly. Wall-clock timing columns were excluded.

The independent verifier reconciled **450,000 executed stages**. This comprises
370,000 main-study stages and 80,000 additional stages. It regenerated all ten
calibration-table configurations with maximum discrepancy **zero**. Reconstructing
stage costs from the stored states produced a maximum floating-point difference
of `3.55e-15`; the dynamics reconstruction difference was `8.88e-16`.

The **13 unit tests** passed. All **17 paper numerical-input files** were recreated
byte-for-byte from the supplied results. The four figures were compiled to vector
PDF and rendered as PNG for inspection. The final supplied manuscript is an
**eight-page** PDF; manuscript source is intentionally excluded from the repository.

## Environment and scope

Python 3.13.5, NumPy 2.3.5, SciPy 1.17.0 and pandas 2.2.3 were used, with
single-thread numerical-library settings. Complete environment details are in
`environment.json`. The exact transitive versions are in `requirements.lock`.

A fresh dependency-download installation was attempted and was blocked by the
execution environment's DNS/network restrictions. The full computations and all
local command checks used the recorded installed versions, which match the lock
file. `setup_checks.json` records this distinction. The GitHub workflow is supplied
for execution after repository publication; a remote workflow run was outside
this local verification.

## Machine-readable reports

| File | Content |
|---|---|
| `end_to_end_report.json` | Public full-command status and elapsed time |
| `full_rerun_comparison.json` | Per-file and per-column numerical comparisons |
| `reference_verification.json` | Independent checks on supplied records |
| `rerun_verification.json` | Independent checks on freshly generated records |
| `unit_tests.log` | Unit-suite results |
| `rendering_checks.json` | Figure inspection and final-manuscript page count |
| `source_integrity.json` | Scientific-source hashes and final-PDF hash |
| `manifest.json` | Package SHA-256 integrity manifest |

These checks establish implementation consistency for this environment and these
records. The paper's probabilistic guarantees retain their mathematical assumptions.
