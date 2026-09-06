from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal
from enum import Enum
from typing import Literal


class EventKind(str, Enum):
    SNAPSHOT = "snapshot"
    DELTA = "delta"


class Side(str, Enum):
    BID = "bid"
    ASK = "ask"


@dataclass(frozen=True)
class PriceLevel:
    price: Decimal
    size: Decimal


@dataclass(frozen=True)
class MarketEvent:
    exchange: str
    pair: str
    kind: EventKind
    sequence: int
    timestamp_ns: int
    bids: tuple[PriceLevel, ...] = ()
    asks: tuple[PriceLevel, ...] = ()
    raw_timestamp_ms: int | None = None
    exchange_first_sequence: int | None = None
    exchange_last_sequence: int | None = None
    received_monotonic_ns: int | None = None


@dataclass(frozen=True)
class TopOfBook:
    exchange: str
    pair: str
    best_bid_price: Decimal
    best_bid_size: Decimal
    best_ask_price: Decimal
    best_ask_size: Decimal
    sequence: int
    timestamp_ns: int

    def as_payload(self) -> dict[str, object]:
        return {
            "exchange": self.exchange,
            "pair": self.pair,
            "best_bid_price": str(self.best_bid_price),
            "best_bid_size": str(self.best_bid_size),
            "best_ask_price": str(self.best_ask_price),
            "best_ask_size": str(self.best_ask_size),
            "sequence": self.sequence,
            "timestamp_ns": self.timestamp_ns,
        }


@dataclass(frozen=True)
class ArbitrageOpportunity:
    timestamp_ns: int
    pair: str
    buy_exchange: str
    sell_exchange: str
    buy_price: Decimal
    sell_price: Decimal
    spread_pct: Decimal
    max_size: Decimal
    theoretical_profit_usd: Decimal

    def as_payload(self) -> dict[str, object]:
        payload = asdict(self)
        return {
            key: str(value) if isinstance(value, Decimal) else value
            for key, value in payload.items()
        }


@dataclass(frozen=True)
class BookUpdateResult:
    accepted: bool
    reason: str | None = None
    top_of_book: TopOfBook | None = None
    stale: bool = False


@dataclass(frozen=True)
class BookEligibility:
    exchange: str
    pair: str
    initialized: bool
    continuous: bool
    connected: bool
    age_ns: int | None
    max_age_ns: int
    eligible: bool
    reason: str | None = None

    def as_payload(self) -> dict[str, object]:
        return {
            "exchange": self.exchange,
            "pair": self.pair,
            "initialized": self.initialized,
            "continuous": self.continuous,
            "connected": self.connected,
            "age_ms": None if self.age_ns is None else self.age_ns // 1_000_000,
            "max_age_ms": self.max_age_ns // 1_000_000,
            "eligible": self.eligible,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class LiveMessage:
    type: Literal["top_of_book", "opportunity", "book_status", "state_snapshot"]
    payload: dict[str, object]


@dataclass
class BookStateSnapshot:
    exchange: str
    pair: str
    sequence: int | None
    stale: bool
    initialized: bool = False
    continuous: bool = False
    connected: bool = False
    age_ns: int | None = None
    eligible: bool = False
    top_of_book: TopOfBook | None = None
