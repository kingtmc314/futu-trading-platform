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

    @property
    def is_simulate(self) -> bool:
        return self.futu_trd_env.upper() != "REAL"


@lru_cache
def get_settings() -> Settings:
    return Settings()
