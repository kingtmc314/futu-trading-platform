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

    @property
    def is_simulate(self) -> bool:
        return self.futu_trd_env.upper() != "REAL"


@lru_cache
def get_settings() -> Settings:
    return Settings()
