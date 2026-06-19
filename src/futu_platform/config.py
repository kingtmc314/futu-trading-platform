from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    futu_opend_host: str = "127.0.0.1"
    futu_opend_port: int = 11111
    futu_trd_env: str = "SIMULATE"
    futu_default_market: str = "HK"
    futu_acc_id: int = 0
    futu_security_firm: Optional[str] = None

    web_host: str = "127.0.0.1"
    web_port: int = 8080

    # 實盤風控：預設不允許實盤下單，必須在 .env 明確開啟。
    futu_real_trading_enabled: bool = False
    futu_real_max_order_value: float = 10000.0
    futu_real_max_quantity: int = 1000
    futu_real_allowed_prefixes: str = "HK,US"
    futu_real_market_order_allowed: bool = False

    # World Monitor：每小時監控財經/政策異動並產生交易信號。
    world_monitor_enabled: bool = True
    world_monitor_auto_trade: bool = False
    world_monitor_interval_seconds: int = 3600
    world_monitor_trd_env: str = "SIMULATE"
    world_monitor_symbols: str = "US.SPY,US.QQQ,HK.02800"
    world_monitor_quantity: int = 1
    world_monitor_buy_threshold: float = 3.0
    world_monitor_sell_threshold: float = -3.0
    world_monitor_data_dir: str = "data/world_monitor"
    world_monitor_sources: str = (
        "finance:https://feeds.finance.yahoo.com/rss/2.0/headline?s=%5EGSPC&region=US&lang=en-US,"
        "policy:https://www.federalreserve.gov/feeds/press_all.xml"
    )

    @property
    def is_simulate(self) -> bool:
        return self.futu_trd_env.upper() != "REAL"


@lru_cache
def get_settings() -> Settings:
    return Settings()
