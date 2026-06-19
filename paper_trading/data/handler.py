"""DataHandler 抽象與實作。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import List, Optional

import httpx
import pandas as pd

from ..logging_setup import get_logger
from ..models import MarketBar, TickerQuote
from ..settings import DataConfig

logger = get_logger("paper_trading.data")


class DataHandler(ABC):
    @abstractmethod
    def fetch_klines(self, limit: Optional[int] = None) -> pd.DataFrame:
        ...

    @abstractmethod
    def fetch_latest_ticker(self) -> TickerQuote:
        ...

    def bars_from_df(self, df: pd.DataFrame) -> List[MarketBar]:
        bars: List[MarketBar] = []
        for _, row in df.iterrows():
            bars.append(
                MarketBar(
                    symbol=str(row["symbol"]),
                    timestamp=row["timestamp"].to_pydatetime()
                    if hasattr(row["timestamp"], "to_pydatetime")
                    else row["timestamp"],
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row["volume"]),
                )
            )
        return bars


class BinanceDataHandler(DataHandler):
    def __init__(self, config: DataConfig) -> None:
        self._config = config
        self._client = httpx.Client(base_url=config.binance_base_url, timeout=30.0)
        self._memory: pd.DataFrame = pd.DataFrame()

    def fetch_klines(self, limit: Optional[int] = None) -> pd.DataFrame:
        req_limit = limit or self._config.kline_limit
        params = {
            "symbol": self._config.symbol,
            "interval": self._config.interval,
            "limit": req_limit,
        }
        try:
            resp = self._client.get("/api/v3/klines", params=params)
            resp.raise_for_status()
            raw = resp.json()
        except httpx.HTTPError as exc:
            logger.error("Binance K 線請求失敗: %s", exc)
            raise

        rows = []
        for item in raw:
            rows.append(
                {
                    "symbol": self._config.symbol,
                    "timestamp": datetime.fromtimestamp(item[0] / 1000, tz=timezone.utc),
                    "open": float(item[1]),
                    "high": float(item[2]),
                    "low": float(item[3]),
                    "close": float(item[4]),
                    "volume": float(item[5]),
                }
            )
        df = pd.DataFrame(rows)
        self._memory = df
        logger.info("取得 K 線 %s 條 | symbol=%s", len(df), self._config.symbol)
        return df

    def fetch_latest_ticker(self) -> TickerQuote:
        params = {"symbol": self._config.symbol}
        resp = self._client.get("/api/v3/ticker/bookTicker", params=params)
        resp.raise_for_status()
        data = resp.json()
        bid = float(data["bidPrice"])
        ask = float(data["askPrice"])
        last = (bid + ask) / 2.0
        return TickerQuote(
            symbol=self._config.symbol,
            timestamp=datetime.now(tz=timezone.utc),
            last_price=last,
            bid=bid,
            ask=ask,
            volume=0.0,
        )

    @property
    def memory(self) -> pd.DataFrame:
        return self._memory.copy()


class MockDataHandler(DataHandler):
    """離線測試用：生成可重現的隨機漫步價格。"""

    def __init__(self, config: DataConfig, seed: int = 42) -> None:
        self._config = config
        self._seed = seed
        self._step = 0
        self._memory: pd.DataFrame = pd.DataFrame()

    def fetch_klines(self, limit: Optional[int] = None) -> pd.DataFrame:
        import numpy as np

        req_limit = limit or self._config.kline_limit
        rng = np.random.default_rng(self._seed + self._step)
        self._step += 1
        base = 50000.0 + self._step * 10.0
        closes = base + np.cumsum(rng.normal(0, 50, req_limit))
        timestamps = pd.date_range(
            end=datetime.now(tz=timezone.utc),
            periods=req_limit,
            freq="min",
        )
        df = pd.DataFrame(
            {
                "symbol": self._config.symbol,
                "timestamp": timestamps,
                "open": closes - rng.uniform(0, 20, req_limit),
                "high": closes + rng.uniform(0, 30, req_limit),
                "low": closes - rng.uniform(0, 30, req_limit),
                "close": closes,
                "volume": rng.uniform(100, 1000, req_limit),
            }
        )
        self._memory = df
        logger.info("Mock K 線生成 %s 條", len(df))
        return df

    def fetch_latest_ticker(self) -> TickerQuote:
        if self._memory.empty:
            self.fetch_klines(limit=50)
        last_close = float(self._memory.iloc[-1]["close"])
        now = datetime.now(tz=timezone.utc)
        return TickerQuote(
            symbol=self._config.symbol,
            timestamp=now,
            last_price=last_close,
            bid=last_close * 0.9999,
            ask=last_close * 1.0001,
            volume=float(self._memory.iloc[-1]["volume"]),
        )


def create_data_handler(config: DataConfig) -> DataHandler:
    provider = config.provider.lower()
    if provider == "binance":
        return BinanceDataHandler(config)
    if provider == "mock":
        return MockDataHandler(config)
    raise ValueError(f"不支援的 data provider: {provider}")
