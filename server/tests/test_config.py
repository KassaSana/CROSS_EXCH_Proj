from __future__ import annotations

from pathlib import Path

import pytest
from arb.config import load_config

VALID_CONFIG = """
[detector]
threshold_pct = 0.25

[exchanges]
gemini = ["btcusd", "ethusd"]
coinbase = ["BTC-USD"]
binance = ["BTCUSDT"]

[server]
host = "0.0.0.0"
port = 8000
database_path = "arb.sqlite3"

[persistence]
batch_size = 500
flush_interval_seconds = 1.0
queue_maxsize = 1000

[order_books]
max_age_seconds = 12.5
"""


def test_load_config_parses_all_sections(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(VALID_CONFIG)
    config = load_config(path)
    assert config.detector.threshold_pct == 0.25
    assert config.exchanges["gemini"] == ["btcusd", "ethusd"]
    assert config.exchanges["binance"] == ["BTCUSDT"]
    assert config.server.host == "0.0.0.0"
    assert config.server.port == 8000
    assert config.server.database_path == "arb.sqlite3"
    assert config.persistence.batch_size == 500
    assert config.persistence.flush_interval_seconds == 1.0
    assert config.persistence.queue_maxsize == 1000
    assert config.order_books.max_age_seconds == 12.5


def test_load_config_defaults_queue_maxsize_when_missing(tmp_path: Path) -> None:
    config_text = VALID_CONFIG.replace("queue_maxsize = 1000\n", "")
    path = tmp_path / "config.toml"
    path.write_text(config_text)
    config = load_config(path)
    assert config.persistence.queue_maxsize == 10_000


def test_load_config_defaults_book_age_when_section_missing(tmp_path: Path) -> None:
    config_text = VALID_CONFIG.replace("\n[order_books]\nmax_age_seconds = 12.5\n", "")
    path = tmp_path / "config.toml"
    path.write_text(config_text)
    config = load_config(path)
    assert config.order_books.max_age_seconds == 30.0


def test_load_config_raises_on_missing_section(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text("[detector]\nthreshold_pct = 0.1\n")
    with pytest.raises(KeyError):
        load_config(path)
