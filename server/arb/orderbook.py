from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass, field
from decimal import Decimal

from arb.types import (
    BookStateSnapshot,
    BookUpdateResult,
    EventKind,
    MarketEvent,
    PriceLevel,
    TopOfBook,
)


class SortedLevels:
    """Maintains sorted price levels with deterministic top-of-book lookup."""

    def __init__(self, descending: bool) -> None:
        self.descending = descending
        self._prices: list[Decimal] = []
        self._sizes: dict[Decimal, Decimal] = {}

    def clear(self) -> None:
        self._prices.clear()
        self._sizes.clear()

    def set_level(self, price: Decimal, size: Decimal) -> None:
        if size <= Decimal("0"):
            self.remove(price)
            return

        if price not in self._sizes:
            idx = bisect_left(self._prices, price)
            self._prices.insert(idx, price)
        self._sizes[price] = size

    def remove(self, price: Decimal) -> None:
        if price not in self._sizes:
            return
        del self._sizes[price]
        idx = bisect_left(self._prices, price)
        if idx < len(self._prices) and self._prices[idx] == price:
            self._prices.pop(idx)

    def best(self) -> PriceLevel | None:
        if not self._prices:
            return None
        price = self._prices[-1] if self.descending else self._prices[0]
        return PriceLevel(price=price, size=self._sizes[price])

    def top_n(self, limit: int) -> list[PriceLevel]:
        if self.descending:
            prices = list(reversed(self._prices[-limit:]))
        else:
            prices = self._prices[:limit]
        return [PriceLevel(price=price, size=self._sizes[price]) for price in prices]


@dataclass
class OrderBook:
    bids: SortedLevels = field(default_factory=lambda: SortedLevels(descending=True))
    asks: SortedLevels = field(default_factory=lambda: SortedLevels(descending=False))
    sequence: int | None = None
    stale: bool = True
    last_timestamp_ns: int = 0

    def clear(self) -> None:
        self.bids.clear()
        self.asks.clear()
        self.sequence = None
        self.stale = True
        self.last_timestamp_ns = 0


class OrderBookManager:
    def __init__(self) -> None:
        self._books: dict[tuple[str, str], OrderBook] = {}

    def apply(self, event: MarketEvent) -> BookUpdateResult:
        key = (event.exchange, event.pair)
        book = self._books.setdefault(key, OrderBook())

        if event.kind is EventKind.SNAPSHOT:
            self._apply_snapshot(book, event)
            top = self.top_of_book(event.exchange, event.pair)
            return BookUpdateResult(accepted=True, top_of_book=top)

        if book.stale or book.sequence is None:
            return BookUpdateResult(accepted=False, reason="book_stale", stale=True)

        if event.sequence <= book.sequence:
            return BookUpdateResult(accepted=False, reason="out_of_order")

        if event.sequence != book.sequence + 1:
            book.clear()
            return BookUpdateResult(accepted=False, reason="sequence_gap", stale=True)

        self._apply_delta(book, event)
        top = self.top_of_book(event.exchange, event.pair)
        if top is None:
            return BookUpdateResult(accepted=False, reason="book_incomplete")
        if top.best_bid_price >= top.best_ask_price:
            book.clear()
            return BookUpdateResult(accepted=False, reason="crossed_book", stale=True)
        return BookUpdateResult(accepted=True, top_of_book=top)

    def best_bid(self, exchange: str, pair: str) -> Decimal | None:
        book = self._books.get((exchange, pair))
        if not book:
            return None
        best = book.bids.best()
        return best.price if best else None

    def best_ask(self, exchange: str, pair: str) -> Decimal | None:
        book = self._books.get((exchange, pair))
        if not book:
            return None
        best = book.asks.best()
        return best.price if best else None

    def top_of_book(self, exchange: str, pair: str) -> TopOfBook | None:
        book = self._books.get((exchange, pair))
        if not book or book.stale or book.sequence is None:
            return None
        best_bid = book.bids.best()
        best_ask = book.asks.best()
        if best_bid is None or best_ask is None:
            return None
        return TopOfBook(
            exchange=exchange,
            pair=pair,
            best_bid_price=best_bid.price,
            best_bid_size=best_bid.size,
            best_ask_price=best_ask.price,
            best_ask_size=best_ask.size,
            sequence=book.sequence,
            timestamp_ns=book.last_timestamp_ns,
        )

    def snapshot(self, exchange: str, pair: str) -> BookStateSnapshot:
        book = self._books.get((exchange, pair))
        if not book:
            return BookStateSnapshot(exchange=exchange, pair=pair, sequence=None, stale=True)
        return BookStateSnapshot(
            exchange=exchange,
            pair=pair,
            sequence=book.sequence,
            stale=book.stale,
            top_of_book=self.top_of_book(exchange, pair),
        )

    def known_pairs(self) -> list[tuple[str, str]]:
        return sorted(self._books.keys())

    def level_snapshot(self, exchange: str, pair: str, limit: int = 10) -> tuple[list[PriceLevel], list[PriceLevel]] | None:
        book = self._books.get((exchange, pair))
        if not book or book.stale or book.sequence is None:
            return None
        return (book.bids.top_n(limit), book.asks.top_n(limit))

    def _apply_snapshot(self, book: OrderBook, event: MarketEvent) -> None:
        book.clear()
        for level in event.bids:
            book.bids.set_level(level.price, level.size)
        for level in event.asks:
            book.asks.set_level(level.price, level.size)
        book.sequence = event.sequence
        book.stale = False
        book.last_timestamp_ns = event.timestamp_ns

    def _apply_delta(self, book: OrderBook, event: MarketEvent) -> None:
        for level in event.bids:
            book.bids.set_level(level.price, level.size)
        for level in event.asks:
            book.asks.set_level(level.price, level.size)
        book.sequence = event.sequence
        book.last_timestamp_ns = event.timestamp_ns
