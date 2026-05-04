"""Alerts.yml must reference real metrics only.

Without this gate, an operator copy-pasting alerts from a tutorial
ends up with rules that silently never fire because the metric they
reference doesn't exist. The test parses the alert expressions and
asserts each ``koda_*`` metric appears in ``koda/services/metrics.py``.
Postgres-exporter and Prometheus built-in metrics are explicitly
allowlisted.

Future-you adding a new alert: add the underlying metric to metrics.py
first; this test enforces it.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ALERTS_PATH = REPO_ROOT / "docs" / "operations" / "alerts.yml"
METRICS_PATH = REPO_ROOT / "koda" / "services" / "metrics.py"

# Metrics provided by external exporters in the observability compose
# overlay. These are intentionally not defined in koda's own metrics
# module.
EXTERNAL_METRICS = {
    # Postgres exporter
    "pg_stat_activity_count",
    "pg_settings_max_connections",
    # Prometheus built-ins
    "up",
    # node-exporter (only referenced if/when the operator adds it)
    "node_filesystem_avail_bytes",
    "node_filesystem_size_bytes",
}


def _koda_metrics_in_source() -> set[str]:
    """Extract ``koda_*`` metric names from the constructor calls in
    ``metrics.py`` (e.g. ``Counter("koda_requests_total", ...)``).
    """
    src = METRICS_PATH.read_text(encoding="utf-8")
    pattern = re.compile(r'(?:Counter|Gauge|Histogram|Summary)\(\s*"(koda_[a-zA-Z0-9_]+)"')
    return set(pattern.findall(src))


def _metric_names_in_alerts() -> set[str]:
    """Pull every identifier of the form ``koda_<word>`` / ``pg_<word>``
    / ``node_<word>`` / ``up`` from the alerts.yml ``expr`` fields.

    Parses the YAML properly. A previous regex-only version missed
    block-scalar ``expr: |`` bodies and silently passed every alert
    file (returning an empty set). YAML parsing is the right tool —
    the alerts file is YAML by definition.
    """
    import yaml

    payload = yaml.safe_load(ALERTS_PATH.read_text(encoding="utf-8"))
    metrics: set[str] = set()
    for group in payload.get("groups", []):
        for rule in group.get("rules", []):
            expr = str(rule.get("expr") or "")
            for ident in re.findall(r"\b([a-z_][a-z0-9_]+)\b", expr):
                if ident.startswith(("koda_", "pg_", "node_")) or ident == "up":
                    metrics.add(ident)
    return metrics


def test_every_alert_metric_is_emitted_by_koda_or_an_allowed_exporter() -> None:
    declared = _koda_metrics_in_source() | EXTERNAL_METRICS
    used = _metric_names_in_alerts()
    suffix_strip = (
        {m + "_bucket": m for m in declared} | {m + "_count": m for m in declared} | {m + "_sum": m for m in declared}
    )

    missing: list[str] = []
    for metric in sorted(used):
        if metric in declared:
            continue
        # Histograms expose <name>_bucket / _count / _sum derived metrics.
        if metric in suffix_strip:
            continue
        missing.append(metric)

    assert not missing, (
        "alerts.yml references metrics that are not emitted by "
        "koda/services/metrics.py and are not in the external-exporter "
        "allowlist:\n  "
        + "\n  ".join(missing)
        + "\n\nAdd the metric to koda/services/metrics.py before adding the alert, "
        "or extend the EXTERNAL_METRICS allowlist if the metric comes from a "
        "documented exporter that the observability compose overlay deploys."
    )


def test_alerts_yaml_is_parseable() -> None:
    """Catch typos that would otherwise silently break Prometheus
    rule loading at runtime."""
    import yaml

    payload = yaml.safe_load(ALERTS_PATH.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    groups = payload.get("groups")
    assert isinstance(groups, list) and groups
    for group in groups:
        assert "name" in group
        assert "rules" in group
        for rule in group["rules"]:
            assert "alert" in rule
            assert "expr" in rule
            assert "labels" in rule
            assert "annotations" in rule


def test_grafana_dashboard_targets_only_existing_metrics() -> None:
    """Same gate against the Grafana overview dashboard — no
    speculative metrics."""
    import json

    dashboard = json.loads(
        (REPO_ROOT / "docs" / "operations" / "grafana" / "dashboards" / "koda-overview.json").read_text(
            encoding="utf-8"
        )
    )
    declared = _koda_metrics_in_source() | EXTERNAL_METRICS
    suffix_strip_set = set()
    for m in declared:
        suffix_strip_set.update({m + "_bucket", m + "_count", m + "_sum"})

    referenced: set[str] = set()
    for panel in dashboard.get("panels", []):
        for target in panel.get("targets", []):
            expr = str(target.get("expr") or "")
            for ident in re.findall(r"\b([a-z_][a-z0-9_]+)\b", expr):
                if ident.startswith(("koda_", "pg_", "node_")) or ident == "up":
                    referenced.add(ident)

    missing = [m for m in sorted(referenced) if m not in declared and m not in suffix_strip_set]
    assert not missing, "koda-overview.json dashboard references unknown metrics:\n  " + "\n  ".join(missing)
