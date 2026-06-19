"""ExecutionHandler：接收信號並執行模擬下單。"""

from __future__ import annotations

from typing import Optional

from ..logging_setup import get_logger
from ..models import FillRecord, Signal, SignalType
from ..portfolio.paper import PaperTradingAccount
from ..storage import StorageBackend

logger = get_logger("paper_trading.execution")


class ExecutionHandler:
    def __init__(self, account: PaperTradingAccount, storage: StorageBackend) -> None:
        self._account = account
        self._storage = storage

    def on_signal(self, signal: Signal, market_price: float, quantity: Optional[float] = None) -> FillRecord:
        self._storage.save_signal(signal)
        logger.info(
            "收到信號 | %s %s @ %.2f | %s",
            signal.symbol,
            signal.signal_type.value,
            market_price,
            signal.reason,
        )

        if signal.signal_type == SignalType.HOLD:
            fill = self._account.simulate_fill(signal, market_price, quantity=0.0)
            return fill

        fill = self._account.simulate_fill(signal, market_price, quantity=quantity)
        if fill.status.value != "SKIPPED":
            self._storage.save_fill(fill)
        return fill
