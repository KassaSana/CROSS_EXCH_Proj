from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from soak import SoakReport, process_rss_bytes


def test_soak_report_tracks_recovery_and_counters() -> None:
    report = SoakReport("2026-09-05T00:00:00+00:00", 60, 5)
    adapter = {
        "exchange": "gemini",
        "reconnect_count": 2,
        "gap_count": 1,
        "last_message_age_ms": 50,
        "last_error": None,
    }
    eligible = {
        "exchange": "gemini",
        "pair": "BTC-USD",
        "eligible": True,
        "reason": None,
        "age_ms": 25,
    }
    ineligible = {**eligible, "eligible": False, "reason": "too_old", "age_ms": 31_000}
    readiness = {"status": "ready", "background_task_failures": []}
    report.observe(
        adapters=[adapter],
        books=[eligible],
        readiness=readiness,
        overview={"all_time_count": 10},
        elapsed_seconds=0,
        rss=100,
    )
    report.observe(
        adapters=[{**adapter, "reconnect_count": 3, "gap_count": 2}],
        books=[ineligible],
        readiness={"status": "not_ready", "background_task_failures": []},
        overview={"all_time_count": 12},
        elapsed_seconds=5,
        rss=110,
    )
    report.observe(
        adapters=[{**adapter, "reconnect_count": 3, "gap_count": 2}],
        books=[eligible],
        readiness=readiness,
        overview={"all_time_count": 13},
        elapsed_seconds=10,
        rss=105,
    )
    report.ended_at = "2026-09-05T00:01:00+00:00"
    report.actual_duration_seconds = 60

    markdown = report.markdown()

    assert "Opportunities observed: `3`" in markdown
    assert "| gemini | 1 | 1 | 50 ms | - |" in markdown
    assert "too_old=1" in markdown
    assert "5.0s" in markdown
    assert "Start-to-end change: `+0.00 MiB`" in markdown


def test_process_rss_reads_current_process() -> None:
    rss = process_rss_bytes(os.getpid())
    assert rss is not None
    assert rss > 0
