"""Formal benchmarks with regression gates.

Each bench module measures a hot-path operation and compares the
result against a JSON baseline in ``tests/benchmarks/baselines/``.
Regressions >50% over baseline fail the test, surfacing performance
issues at PR-quality time instead of in production.

Baselines are intentionally generous (~3-5× actual measured value at
authoring time) so CI runners with different hardware budgets pass
consistently, but a true regression — code suddenly 2× slower —
trips the gate. Refresh baselines deliberately by editing the JSON
file when the slower path is intentional.
"""
