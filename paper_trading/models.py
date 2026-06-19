"""模擬程式交易系統 - 類型定義與資料模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional


class SignalType(str, Enum):
    HOLD = "HOLD"
    BUY = "BUY"
    SELL = "SELL"


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(str, Enum):
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    SKIPPED = "SKIPPED"


@dataclass(frozen=True)
class MarketBar:
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class TickerQuote:
    symbol: str
    timestamp: datetime
    last_price: float
    bid: float
    ask: float
    volume: float


@dataclass
class Signal:
    symbol: str
    signal_type: SignalType
    timestamp: datetime
    price: float
    reason: str
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class OrderRequest:
    symbol: str
    side: OrderSide
    quantity: float
    price: float
    timestamp: datetime
    signal_reason: str


@dataclass
class FillRecord:
    order_id: str
    symbol: str
    side: OrderSide
    quantity: float
    fill_price: float
    commission: float
    slippage: float
    timestamp: datetime
    status: OrderStatus
    reason: str


@dataclass
class Position:
    symbol: str
    quantity: float
    avg_cost: float

    @property
    def market_value(self) -> float:
        return self.quantity * self.avg_cost


@dataclass
class PortfolioSnapshot:
    timestamp: datetime
    cash: float
    equity: float
    unrealized_pnl: float
    realized_pnl: float
    positions: Dict[str, Position]
    metadata: Dict[str, Any] = field(default_factory=dict)
