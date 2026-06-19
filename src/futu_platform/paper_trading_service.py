"""本地程式模擬交易唯讀服務（讀取 SQLite）。"""

from __future__ import annotations

from typing import Any, Dict, Optional

from paper_trading.repository import PaperTradingRepository
from paper_trading.settings import AppConfig, load_config


class PaperTradingService:
    """封裝 paper_trading 模組的唯讀查詢。"""

    def __init__(self, config: Optional[AppConfig] = None) -> None:
        self._config = config or load_config()
        log_path = self._config.runtime.data_dir / "paper_trading.log"
        self._repo = PaperTradingRepository(
            db_path=self._config.db_path,
            log_path=log_path,
            poll_interval_seconds=self._config.data.poll_interval_seconds,
        )

    @property
    def config(self) -> AppConfig:
        return self._config

    def _config_summary(self) -> Dict[str, Any]:
        c = self._config
        return {
            "symbol": c.data.symbol,
            "provider": c.data.provider,
            "interval": c.data.interval,
            "strategy": c.strategy.name,
            "base_currency": c.portfolio.base_currency,
            "poll_interval_seconds": c.data.poll_interval_seconds,
            "initial_cash": c.portfolio.initial_cash,
        }

    def overview(self) -> Dict[str, Any]:
        return self._repo.overview(
            initial_cash=self._config.portfolio.initial_cash,
            config_summary=self._config_summary(),
        )

    def snapshot(self) -> Optional[Dict[str, Any]]:
        return self._repo.get_latest_snapshot()

    def fills(self, limit: int = 100) -> list[Dict[str, Any]]:
        return self._repo.get_fills(limit=limit)

    def signals(self, limit: int = 50) -> list[Dict[str, Any]]:
        return self._repo.get_signals(limit=limit)

    def summary(self) -> Dict[str, Any]:
        return self._repo.get_equity_summary(self._config.portfolio.initial_cash)

    def status(self) -> Dict[str, Any]:
        return self._repo.get_run_status(self._config_summary()).to_dict()

    def chart_data(self, limit: int = 500) -> Dict[str, Any]:
        return self._repo.get_chart_data(limit=limit)
