"""策略框架：可插拔策略與執行引擎。"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from ..quote_service import QuoteService
from ..trade_service import OrderRequest, TradeService

logger = logging.getLogger(__name__)


class Signal(str, Enum):
    HOLD = "HOLD"
    BUY = "BUY"
    SELL = "SELL"


@dataclass
class StrategyContext:
    code: str
    klines: list[dict] = field(default_factory=list)
    snapshot: dict | None = None
    position_qty: int = 0


@dataclass
class StrategyResult:
    signal: Signal
    reason: str
    metadata: dict[str, Any] = field(default_factory=dict)


class Strategy(ABC):
    name: str = "base"

    @abstractmethod
    def evaluate(self, ctx: StrategyContext) -> StrategyResult:
        ...


class StrategyEngine:
    def __init__(
        self,
        quote: QuoteService | None = None,
        trade: TradeService | None = None,
    ) -> None:
        self.quote = quote or QuoteService()
        self.trade = trade or TradeService()
        self._strategies: dict[str, Strategy] = {}

    def register(self, strategy: Strategy) -> None:
        self._strategies[strategy.name] = strategy

    def list_strategies(self) -> list[str]:
        return list(self._strategies.keys())

    def _position_qty(self, code: str, trd_env: str = "SIMULATE") -> int:
        try:
            positions = self.trade.portfolio(code, trd_env=trd_env)
            for pos in positions:
                if pos.get("code") == code:
                    return int(float(pos.get("qty", 0) or 0))
        except Exception as exc:
            logger.warning("查詢持倉失敗: %s", exc)
        return 0

    def build_context(
        self,
        code: str,
        ktype: str = "K_DAY",
        count: int = 120,
        trd_env: str = "SIMULATE",
    ) -> StrategyContext:
        klines = self.quote.kline(code, ktype=ktype, count=count)
        snapshot_list = self.quote.snapshot([code])
        snapshot = snapshot_list[0] if snapshot_list else None
        return StrategyContext(
            code=code,
            klines=klines,
            snapshot=snapshot,
            position_qty=self._position_qty(code, trd_env),
        )

    def run_once(
        self,
        strategy_name: str,
        code: str,
        *,
        quantity: int = 100,
        auto_trade: bool = False,
        confirmed: bool = False,
        trd_env: str = "SIMULATE",
        ktype: str = "K_DAY",
    ) -> dict:
        strategy = self._strategies.get(strategy_name)
        if not strategy:
            raise KeyError(f"未知策略: {strategy_name}")

        ctx = self.build_context(code, ktype=ktype, trd_env=trd_env)
        result = strategy.evaluate(ctx)
        output: dict[str, Any] = {
            "timestamp": datetime.now().isoformat(),
            "strategy": strategy_name,
            "code": code,
            "trd_env": trd_env.upper(),
            "signal": result.signal.value,
            "reason": result.reason,
            "position_qty": ctx.position_qty,
            "metadata": result.metadata,
            "order": None,
        }

        if auto_trade and result.signal in (Signal.BUY, Signal.SELL):
            if result.signal == Signal.BUY and ctx.position_qty > 0:
                output["order"] = {"skipped": True, "reason": "已有持倉"}
            elif result.signal == Signal.SELL and ctx.position_qty <= 0:
                output["order"] = {"skipped": True, "reason": "無持倉可賣"}
            else:
                qty = quantity if result.signal == Signal.BUY else min(quantity, ctx.position_qty)
                order = self.trade.place_order(
                    OrderRequest(
                        code=code,
                        side=result.signal.value,
                        quantity=qty,
                        order_type="MARKET",
                        trd_env=trd_env.upper(),
                        confirmed=confirmed,
                    )
                )
                output["order"] = order

        return output
