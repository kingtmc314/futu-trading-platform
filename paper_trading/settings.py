"""配置載入：YAML + 環境變數，禁止 hardcode。"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import yaml


def _load_yaml(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _env(key: str, default: Optional[str] = None) -> Optional[str]:
    return os.getenv(key, default)


@dataclass(frozen=True)
class DataConfig:
    provider: str
    symbol: str
    interval: str
    poll_interval_seconds: int
    kline_limit: int
    binance_base_url: str


@dataclass(frozen=True)
class StrategyConfig:
    name: str
    fast_period: int
    slow_period: int


@dataclass(frozen=True)
class PortfolioConfig:
    initial_cash: float
    base_currency: str
    commission_rate: float
    slippage_rate: float
    max_position_pct: float


@dataclass(frozen=True)
class ExecutionConfig:
    order_type: str
    min_order_qty: float


@dataclass(frozen=True)
class RuntimeConfig:
    run_duration_hours: float
    demo_duration_seconds: int
    log_level: str
    data_dir: Path
    db_filename: str


@dataclass(frozen=True)
class AppConfig:
    data: DataConfig
    strategy: StrategyConfig
    portfolio: PortfolioConfig
    execution: ExecutionConfig
    runtime: RuntimeConfig

    @property
    def db_path(self) -> Path:
        return self.runtime.data_dir / self.runtime.db_filename


def load_config(config_path: Optional[Path] = None) -> AppConfig:
    root = Path(__file__).resolve().parent
    path = config_path or Path(_env("PAPER_CONFIG", str(root / "config.yaml")))
    if not path.exists():
        example = root / "config.yaml.example"
        if example.exists():
            path = example
        else:
            raise FileNotFoundError(f"找不到配置檔: {path}")

    raw = _load_yaml(path)
    data_raw = raw.get("data", {})
    strategy_raw = raw.get("strategy", {})
    portfolio_raw = raw.get("portfolio", {})
    execution_raw = raw.get("execution", {})
    runtime_raw = raw.get("runtime", {})

    data_dir = Path(_env("PAPER_DATA_DIR", runtime_raw.get("data_dir", "data/paper_trading")))

    return AppConfig(
        data=DataConfig(
            provider=_env("PAPER_DATA_PROVIDER", data_raw.get("provider", "binance")),
            symbol=_env("PAPER_SYMBOL", data_raw.get("symbol", "BTCUSDT")),
            interval=_env("PAPER_INTERVAL", data_raw.get("interval", "1m")),
            poll_interval_seconds=int(_env("PAPER_POLL_SECONDS", data_raw.get("poll_interval_seconds", 60))),
            kline_limit=int(_env("PAPER_KLINE_LIMIT", data_raw.get("kline_limit", 200))),
            binance_base_url=_env("PAPER_BINANCE_URL", data_raw.get("binance_base_url", "https://api.binance.com")),
        ),
        strategy=StrategyConfig(
            name=_env("PAPER_STRATEGY", strategy_raw.get("name", "ma_cross")),
            fast_period=int(_env("PAPER_MA_FAST", strategy_raw.get("fast_period", 5))),
            slow_period=int(_env("PAPER_MA_SLOW", strategy_raw.get("slow_period", 20))),
        ),
        portfolio=PortfolioConfig(
            initial_cash=float(_env("PAPER_INITIAL_CASH", portfolio_raw.get("initial_cash", 100000.0))),
            base_currency=_env("PAPER_BASE_CURRENCY", portfolio_raw.get("base_currency", "USDT")),
            commission_rate=float(_env("PAPER_COMMISSION", portfolio_raw.get("commission_rate", 0.001))),
            slippage_rate=float(_env("PAPER_SLIPPAGE", portfolio_raw.get("slippage_rate", 0.0005))),
            max_position_pct=float(_env("PAPER_MAX_POSITION_PCT", portfolio_raw.get("max_position_pct", 0.95))),
        ),
        execution=ExecutionConfig(
            order_type=_env("PAPER_ORDER_TYPE", execution_raw.get("order_type", "market")),
            min_order_qty=float(_env("PAPER_MIN_QTY", execution_raw.get("min_order_qty", 0.0001))),
        ),
        runtime=RuntimeConfig(
            run_duration_hours=float(_env("PAPER_RUN_HOURS", runtime_raw.get("run_duration_hours", 24))),
            demo_duration_seconds=int(_env("PAPER_DEMO_SECONDS", runtime_raw.get("demo_duration_seconds", 120))),
            log_level=_env("PAPER_LOG_LEVEL", runtime_raw.get("log_level", "INFO")),
            data_dir=data_dir,
            db_filename=_env("PAPER_DB_FILE", runtime_raw.get("db_filename", "paper_trading.db")),
        ),
    )
