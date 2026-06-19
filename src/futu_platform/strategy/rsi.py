"""RSI 超買超賣策略。"""

from __future__ import annotations

import pandas as pd

from .engine import Signal, Strategy, StrategyContext, StrategyResult


def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, pd.NA)
    return 100 - (100 / (1 + rs))


class RSIStrategy(Strategy):
    name = "rsi"

    def __init__(self, period: int = 14, oversold: float = 30, overbought: float = 70) -> None:
        self.period = period
        self.oversold = oversold
        self.overbought = overbought

    def evaluate(self, ctx: StrategyContext) -> StrategyResult:
        if len(ctx.klines) < self.period + 2:
            return StrategyResult(Signal.HOLD, f"K 線不足 {self.period + 2} 根")

        closes = pd.to_numeric(pd.DataFrame(ctx.klines)["close"], errors="coerce").dropna()
        rsi = _rsi(closes, self.period)
        curr = float(rsi.iloc[-1])
        prev = float(rsi.iloc[-2])
        meta = {"rsi": round(curr, 2), "period": self.period}

        if prev >= self.oversold and curr < self.oversold:
            return StrategyResult(Signal.BUY, f"RSI 進入超賣區 ({curr:.1f})", meta)
        if prev <= self.overbought and curr > self.overbought:
            return StrategyResult(Signal.SELL, f"RSI 進入超買區 ({curr:.1f})", meta)
        if curr < self.oversold:
            return StrategyResult(Signal.BUY, f"RSI 超賣 ({curr:.1f})", meta)
        if curr > self.overbought:
            return StrategyResult(Signal.SELL, f"RSI 超買 ({curr:.1f})", meta)
        return StrategyResult(Signal.HOLD, f"RSI 中性 ({curr:.1f})", meta)
