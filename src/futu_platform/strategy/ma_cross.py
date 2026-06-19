"""雙均線交叉策略。"""

from __future__ import annotations

import pandas as pd

from .engine import Signal, Strategy, StrategyContext, StrategyResult


class MACrossStrategy(Strategy):
    name = "ma_cross"

    def __init__(self, fast: int = 5, slow: int = 20) -> None:
        self.fast = fast
        self.slow = slow

    def evaluate(self, ctx: StrategyContext) -> StrategyResult:
        if len(ctx.klines) < self.slow + 1:
            return StrategyResult(Signal.HOLD, f"K 線不足 {self.slow + 1} 根")

        df = pd.DataFrame(ctx.klines)
        closes = pd.to_numeric(df["close"], errors="coerce").dropna()
        if len(closes) < self.slow + 1:
            return StrategyResult(Signal.HOLD, "收盤價數據不足")

        fast_ma = closes.rolling(self.fast).mean()
        slow_ma = closes.rolling(self.slow).mean()
        prev_fast, curr_fast = fast_ma.iloc[-2], fast_ma.iloc[-1]
        prev_slow, curr_slow = slow_ma.iloc[-2], slow_ma.iloc[-1]

        meta = {
            "fast_ma": round(float(curr_fast), 4),
            "slow_ma": round(float(curr_slow), 4),
            "fast_period": self.fast,
            "slow_period": self.slow,
        }

        if prev_fast <= prev_slow and curr_fast > curr_slow:
            return StrategyResult(Signal.BUY, "快線上穿慢線（金叉）", meta)
        if prev_fast >= prev_slow and curr_fast < curr_slow:
            return StrategyResult(Signal.SELL, "快線下穿慢線（死叉）", meta)
        return StrategyResult(Signal.HOLD, "無交叉信號", meta)
