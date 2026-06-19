"""內建策略集合。"""

from .engine import StrategyEngine
from .ma_cross import MACrossStrategy
from .rsi import RSIStrategy


def create_engine() -> StrategyEngine:
    engine = StrategyEngine()
    engine.register(MACrossStrategy())
    engine.register(RSIStrategy())
    return engine
