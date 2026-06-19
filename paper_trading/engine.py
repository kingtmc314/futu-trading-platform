"""交易引擎：協調 Data / Strategy / Portfolio / Execution。"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Optional

from .data import DataHandler, create_data_handler
from .execution import ExecutionHandler
from .logging_setup import get_logger, setup_logging
from .models import SignalType
from .portfolio import PaperTradingAccount
from .settings import AppConfig, load_config
from .storage import SQLiteStorage
from .strategy import Strategy, create_strategy

logger = get_logger("paper_trading.engine")


class TradingEngine:
    def __init__(self, config: Optional[AppConfig] = None) -> None:
        self._config = config or load_config()
        self._logger = setup_logging(
            self._config.runtime.data_dir,
            self._config.runtime.log_level,
        )
        self._storage = SQLiteStorage(self._config.db_path)
        self._storage.initialize()

        self._data: DataHandler = create_data_handler(self._config.data)
        self._strategy: Strategy = create_strategy(self._config.strategy)
        self._account = PaperTradingAccount(self._config.portfolio, self._config.execution)
        self._execution = ExecutionHandler(self._account, self._storage)

    @property
    def config(self) -> AppConfig:
        return self._config

    def run_cycle(self) -> None:
        symbol = self._config.data.symbol
        df = self._data.fetch_klines()
        self._storage.save_bars(self._data.bars_from_df(df.tail(5)))

        ticker = self._data.fetch_latest_ticker()
        signal = self._strategy.generate_signal(df, symbol)

        if signal.signal_type != SignalType.HOLD:
            self._execution.on_signal(signal, ticker.last_price)

        snapshot = self._account.snapshot({symbol: ticker.last_price})
        self._storage.save_snapshot(snapshot)
        logger.info(
            "週期完成 | equity=%.2f cash=%.2f unrealized=%.2f realized=%.2f signal=%s",
            snapshot.equity,
            snapshot.cash,
            snapshot.unrealized_pnl,
            snapshot.realized_pnl,
            signal.signal_type.value,
        )

    def run(self, duration_seconds: Optional[float] = None) -> None:
        cfg = self._config.runtime
        if duration_seconds is None:
            if os.getenv("PAPER_DEMO", "").lower() in ("1", "true", "yes"):
                duration_seconds = float(cfg.demo_duration_seconds)
            else:
                duration_seconds = cfg.run_duration_hours * 3600.0

        poll = self._config.data.poll_interval_seconds
        end_ts = time.time() + duration_seconds
        logger.info(
            "啟動模擬交易 | provider=%s symbol=%s duration=%.0fs poll=%ds",
            self._config.data.provider,
            self._config.data.symbol,
            duration_seconds,
            poll,
        )

        try:
            while time.time() < end_ts:
                try:
                    self.run_cycle()
                except Exception as exc:
                    logger.exception("週期執行錯誤: %s", exc)
                remaining = end_ts - time.time()
                if remaining <= 0:
                    break
                time.sleep(min(poll, remaining))
        except KeyboardInterrupt:
            logger.info("收到中斷信號，停止運行")

        csv_path = self._config.runtime.data_dir / "fills_export.csv"
        self._storage.export_fills_csv(csv_path)
        final = self._account.snapshot(
            {self._config.data.symbol: self._data.fetch_latest_ticker().last_price}
        )
        logger.info(
            "運行結束 | 最終淨值=%.2f 已實現PnL=%.2f 未實現PnL=%.2f | CSV=%s",
            final.equity,
            final.realized_pnl,
            final.unrealized_pnl,
            csv_path,
        )
