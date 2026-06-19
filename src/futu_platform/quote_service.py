"""行情服務：快照、K 線、訂閱。"""

from __future__ import annotations

from typing import Any

import pandas as pd
from futu import AuType, KLType, RET_OK, SubType

from .client import FutuClient


class QuoteService:
    def __init__(self, client: FutuClient | None = None) -> None:
        self.client = client or FutuClient()

    def _ensure_ok(self, ret: int, data: Any, action: str) -> Any:
        if ret != RET_OK:
            raise RuntimeError(f"{action}失敗: {data}")
        return data

    def snapshot(self, codes: list[str]) -> list[dict]:
        with self.client.quote() as ctx:
            ret, data = ctx.get_market_snapshot(codes)
            self._ensure_ok(ret, data, "取得快照")
            return data.to_dict(orient="records") if not data.empty else []

    def kline(
        self,
        code: str,
        ktype: str = "K_DAY",
        count: int = 100,
    ) -> list[dict]:
        kl_map = {
            "K_1M": KLType.K_1M,
            "K_5M": KLType.K_5M,
            "K_15M": KLType.K_15M,
            "K_30M": KLType.K_30M,
            "K_60M": KLType.K_60M,
            "K_DAY": KLType.K_DAY,
            "K_WEEK": KLType.K_WEEK,
            "K_MON": KLType.K_MON,
        }
        kl = kl_map.get(ktype.upper(), KLType.K_DAY)
        with self.client.quote() as ctx:
            ret, data, _ = ctx.request_history_kline(
                code, ktype=kl, autype=AuType.QFQ, max_count=count
            )
            self._ensure_ok(ret, data, "取得 K 線")
            return data.to_dict(orient="records") if data is not None and not data.empty else []

    def subscribe_quote(self, codes: list[str]) -> dict:
        with self.client.quote() as ctx:
            ret, err = ctx.subscribe(codes, [SubType.QUOTE])
            self._ensure_ok(ret, err, "訂閱報價")
            return {"subscribed": codes, "type": "QUOTE"}

    def kline_df(self, code: str, ktype: str = "K_DAY", count: int = 100) -> pd.DataFrame:
        rows = self.kline(code, ktype=ktype, count=count)
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows)
        if "close" in df.columns:
            df["close"] = pd.to_numeric(df["close"], errors="coerce")
        return df
