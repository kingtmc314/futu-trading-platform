"""OpenD 連線管理：行情與交易 Context 生命週期。"""

from __future__ import annotations

import socket
from contextlib import contextmanager
from typing import Iterator

from futu import OpenQuoteContext, OpenSecTradeContext, SecurityFirm, TrdEnv, TrdMarket

from .config import Settings, get_settings

_CODE_PREFIX_TO_MARKET = {
    "US": TrdMarket.US,
    "HK": TrdMarket.HK,
    "SH": TrdMarket.CN,
    "SZ": TrdMarket.CN,
    "SG": TrdMarket.SG,
    "MY": getattr(TrdMarket, "MY", TrdMarket.US),
    "JP": getattr(TrdMarket, "JP", TrdMarket.US),
}


def infer_market_from_code(code: str) -> TrdMarket:
    prefix = code.split(".")[0].upper() if "." in code else ""
    return _CODE_PREFIX_TO_MARKET.get(prefix, TrdMarket.HK)


def parse_trd_env(env: str) -> TrdEnv:
    return TrdEnv.REAL if env and env.upper() == "REAL" else TrdEnv.SIMULATE


def parse_security_firm(firm: str | None) -> SecurityFirm | None:
    if not firm:
        return None
    key = firm.strip().upper()
    return getattr(SecurityFirm, key, None)


class FutuClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def check_opend(self) -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        try:
            sock.connect((self.settings.futu_opend_host, self.settings.futu_opend_port))
        except OSError as exc:
            raise ConnectionError(
                f"無法連接 OpenD ({self.settings.futu_opend_host}:"
                f"{self.settings.futu_opend_port})，請先啟動並登入 OpenD"
            ) from exc
        finally:
            sock.close()

    def _ctx_kwargs(self) -> dict:
        kwargs = {
            "host": self.settings.futu_opend_host,
            "port": self.settings.futu_opend_port,
        }
        try:
            kwargs["ai_type"] = 1
        except TypeError:
            pass
        return kwargs

    @contextmanager
    def quote(self) -> Iterator[OpenQuoteContext]:
        self.check_opend()
        ctx = OpenQuoteContext(**self._ctx_kwargs())
        try:
            yield ctx
        finally:
            ctx.close()

    @contextmanager
    def trade(self, market: TrdMarket | str | None = None) -> Iterator[OpenSecTradeContext]:
        self.check_opend()
        if isinstance(market, str):
            market = _CODE_PREFIX_TO_MARKET.get(market.upper(), TrdMarket.HK)
        trd_market = market or _CODE_PREFIX_TO_MARKET.get(
            self.settings.futu_default_market.upper(), TrdMarket.HK
        )
        firm = parse_security_firm(self.settings.futu_security_firm) or SecurityFirm.NONE
        kwargs = {**self._ctx_kwargs(), "filter_trdmarket": trd_market, "security_firm": firm}
        ctx = OpenSecTradeContext(**kwargs)
        try:
            yield ctx
        finally:
            ctx.close()

    @property
    def trd_env(self) -> TrdEnv:
        return parse_trd_env(self.settings.futu_trd_env)

    @property
    def acc_id(self) -> int:
        return self.settings.futu_acc_id
