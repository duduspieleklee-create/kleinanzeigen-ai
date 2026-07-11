"""Tests für die Prometheus-Export-Schicht (app/shared/metrics_prom.py)."""
from app.shared import metrics_prom as mp


def _sample(body: str, name: str) -> float:
    """Liest den Wert einer Metrik-Zeile aus dem Exposition-Text."""
    total = 0.0
    for line in body.splitlines():
        if line.startswith(name) and not line.startswith("#"):
            total += float(line.rsplit(" ", 1)[1])
    return total


def test_render_metrics_format():
    body, ctype = mp.render_metrics()
    assert "text/plain" in ctype
    assert "job_started_total" in body  # Metrik registriert (auch bei 0)


def test_prom_counter_increments_mapped_name():
    mp.prom_counter("notifications.push_sent", 3)
    body, _ = mp.render_metrics()
    assert _sample(body, "notifications_push_sent_total") >= 3


def test_prom_counter_with_label():
    mp.prom_counter("job.completed", 1, task="test.job")
    body, _ = mp.render_metrics()
    assert 'job_completed_total{task="test.job"}' in body


def test_prom_counter_unknown_name_is_noop():
    # darf nicht crashen und nichts registrieren
    mp.prom_counter("does.not.exist", 5)
    body, _ = mp.render_metrics()
    assert "does_not_exist" not in body


def test_gauge_set():
    mp.searches_active.set(42)
    body, _ = mp.render_metrics()
    assert _sample(body, "searches_active") == 42


def test_track_job_mirrors_to_prometheus():
    from app.shared.observability import track_job

    with track_job("test.mirror"):
        pass
    body, _ = mp.render_metrics()
    assert 'job_started_total{task="test.mirror"}' in body
    assert 'job_completed_total{task="test.mirror"}' in body
    # duration histogram sichtbar
    assert 'job_duration_seconds_count{task="test.mirror"}' in body


def test_track_job_failure_mirrors_failed():
    from app.shared.observability import track_job

    try:
        with track_job("test.boom"):
            raise ValueError("boom")
    except ValueError:
        pass
    body, _ = mp.render_metrics()
    assert 'job_failed_total{task="test.boom"}' in body
