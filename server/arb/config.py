from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DetectorConfig:
    threshold_pct: float


@dataclass(frozen=True)
class ServerConfig:
    host: str
    port: int
    database_path: str


@dataclass(frozen=True)
class PersistenceConfig:
    batch_size: int
    flush_interval_seconds: float
    queue_maxsize: int


@dataclass(frozen=True)
class AppConfig:
    detector: DetectorConfig
    exchanges: dict[str, list[str]]
    server: ServerConfig
    persistence: PersistenceConfig


def load_config(path: str | Path = "config.toml") -> AppConfig:
    raw = tomllib.loads(Path(path).read_text())
    return AppConfig(
        detector=DetectorConfig(threshold_pct=float(raw["detector"]["threshold_pct"])),
        exchanges={name: list(symbols) for name, symbols in raw["exchanges"].items()},
        server=ServerConfig(
            host=raw["server"]["host"],
            port=int(raw["server"]["port"]),
            database_path=raw["server"]["database_path"],
        ),
        persistence=PersistenceConfig(
            batch_size=int(raw["persistence"]["batch_size"]),
            flush_interval_seconds=float(raw["persistence"]["flush_interval_seconds"]),
            queue_maxsize=int(raw["persistence"].get("queue_maxsize", 10_000)),
        ),
    )
