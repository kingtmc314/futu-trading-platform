"""Strategy 抽象與均線交叉實作。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict

import pandas as pd

from ..logging_setup import get_logger
from ..models import Signal, SignalType
from ..settings import StrategyConfig

logger = get_logger("paper_trading.strategy")


class Strategy(ABC):
    name: str = "base"

    @abstractmethod
    def generate_signal(self, df: pd.DataFrame, symbol: str) -> Signal:
        ...


class MovingAverageCrossStrategy(Strategy):
    name = "ma_cross"

    def __init__(self, config: StrategyConfig) -> None:
        self._config = config

    def generate_signal(self, df: pd.DataFrame, symbol: str) -> Signal:
        min_len = self._config.slow_period + 2
        now = datetime.now(tz=timezone.utc)
        if len(df) < min_len:
            return Signal(
                symbol=symbol,
                signal_type=SignalType.HOLD,
                timestamp=now,
                price=float(df.iloc[-1]["close"]) if not df.empty else 0.0,
                reason=f"K 線不足 {min_len} 根",
            )

        closes = df["close"].astype(float)
        fast = closes.rolling(self._config.fast_period).mean()
        slow = closes.rolling(self._config.slow_period).mean()
        prev_fast, curr_fast = fast.iloc[-2], fast.iloc[-1]
        prev_slow, curr_slow = slow.iloc[-2], slow.iloc[-1]
        price = float(closes.iloc[-1])
        meta: Dict[str, Any] = {
            "fast_ma": round(float(curr_fast), 4),
            "slow_ma": round(float(curr_slow), 4),
            "fast_period": self._config.fast_period,
            "slow_period": self._config.slow_period,
        }

        if prev_fast <= prev_slow and curr_fast > curr_slow:
            logger.info("金叉信號 | price=%.2f fast=%.2f slow=%.2f", price, curr_fast, curr_slow)
            return Signal(
                symbol=symbol,
                signal_type=SignalType.BUY,
                timestamp=now,
                price=price,
                reason="快線上穿慢線（金叉）",
                metadata=meta,
            )
        if prev_fast >= prev_slow and curr_fast < curr_slow:
            logger.info("死叉信號 | price=%.2f fast=%.2f slow=%.2f", price, curr_fast, curr_slow)
            return Signal(
                symbol=symbol,
                signal_type=SignalType.SELL,
                timestamp=now,
                price=price,
                reason="快線下穿慢線（死叉）",
                metadata=meta,
            )
        return Signal(
            symbol=symbol,
            signal_type=SignalType.HOLD,
            timestamp=now,
            price=price,
            reason="無交叉信號",
            metadata=meta,
        )


def create_strategy(config: StrategyConfig) -> Strategy:
    if config.name == "ma_cross":
        return MovingAverageCrossStrategy(config)
    raise ValueError(f"未知策略: {config.name}")
