"""交易服務：下單、撤單、持倉、資金、訂單查詢（支援模擬/實盤並存）。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Optional

from futu import ModifyOrderOp, OrderType, RET_OK, TrdEnv, TrdSide

from .client import FutuClient, infer_market_from_code, parse_trd_env
from .quote_service import QuoteService
from .risk import RiskManager

TrdEnvName = Literal["SIMULATE", "REAL"]
VALID_ENVS: tuple[TrdEnvName, ...] = ("SIMULATE", "REAL")


def normalize_trd_env(env: str) -> TrdEnvName:
    return "REAL" if env and env.upper() == "REAL" else "SIMULATE"


@dataclass
class OrderRequest:
    code: str
    side: str  # BUY / SELL
    quantity: int
    price: Optional[float] = None
    order_type: str = "NORMAL"  # NORMAL / MARKET
    trd_env: TrdEnvName = "SIMULATE"
    acc_id: int = 0
    confirmed: bool = False


class TradeService:
    def __init__(self, client: Optional[FutuClient] = None) -> None:
        self.client = client or FutuClient()
        self.risk = RiskManager(self.client.settings)
        self.quote = QuoteService(self.client)

    def _ensure_ok(self, ret: int, data: Any, action: str) -> Any:
        if ret != RET_OK:
            raise RuntimeError(f"{action}失敗: {data}")
        return data

    def _resolve_acc_id(self, trd_env: TrdEnvName, acc_id: int) -> int:
        return acc_id if acc_id else self.client.acc_id

    def accounts(self, trd_env: Optional[TrdEnvName] = None) -> list[dict]:
        with self.client.trade() as ctx:
            ret, data = ctx.get_acc_list()
            self._ensure_ok(ret, data, "查詢帳戶")
            rows = data.to_dict(orient="records") if not data.empty else []
            if trd_env:
                env_name = normalize_trd_env(trd_env)
                rows = [r for r in rows if str(r.get("trd_env", "")).upper() == env_name]
            return rows

    def acc_info(self, trd_env: TrdEnvName = "SIMULATE", acc_id: int = 0) -> dict:
        env = parse_trd_env(trd_env)
        acc = self._resolve_acc_id(trd_env, acc_id)
        with self.client.trade() as ctx:
            ret, data = ctx.accinfo_query(trd_env=env, acc_id=acc)
            self._ensure_ok(ret, data, "查詢資金")
            if data is None or (hasattr(data, "empty") and data.empty):
                return {}
            row = data.iloc[0] if hasattr(data, "iloc") else data
            return row.to_dict() if hasattr(row, "to_dict") else dict(row)

    def portfolio(
        self,
        code: Optional[str] = None,
        trd_env: TrdEnvName = "SIMULATE",
        acc_id: int = 0,
    ) -> list[dict]:
        market = infer_market_from_code(code) if code else None
        env = parse_trd_env(trd_env)
        acc = self._resolve_acc_id(trd_env, acc_id)
        with self.client.trade(market) as ctx:
            ret, data = ctx.position_list_query(trd_env=env, acc_id=acc)
            self._ensure_ok(ret, data, "查詢持倉")
            return data.to_dict(orient="records") if not data.empty else []

    def orders(self, trd_env: TrdEnvName = "SIMULATE", acc_id: int = 0) -> list[dict]:
        env = parse_trd_env(trd_env)
        acc = self._resolve_acc_id(trd_env, acc_id)
        with self.client.trade() as ctx:
            ret, data = ctx.order_list_query(trd_env=env, acc_id=acc)
            self._ensure_ok(ret, data, "查詢訂單")
            return data.to_dict(orient="records") if not data.empty else []

    def env_summary(self, trd_env: TrdEnvName) -> dict:
        env_name = normalize_trd_env(trd_env)
        try:
            accounts = self.accounts(env_name)
            acc_info = self.acc_info(env_name)
            portfolio = self.portfolio(trd_env=env_name)
            orders = self.orders(trd_env=env_name)
            return {
                "trd_env": env_name,
                "accounts": accounts,
                "acc_info": acc_info,
                "portfolio": portfolio,
                "orders": orders,
                "portfolio_count": len(portfolio),
                "orders_count": len(orders),
                "error": None,
            }
        except Exception as exc:
            return {
                "trd_env": env_name,
                "accounts": [],
                "acc_info": {},
                "portfolio": [],
                "orders": [],
                "portfolio_count": 0,
                "orders_count": 0,
                "error": str(exc),
            }

    def overview(self) -> dict:
        return {
            "SIMULATE": self.env_summary("SIMULATE"),
            "REAL": self.env_summary("REAL"),
        }

    def risk_summary(self) -> dict:
        return self.risk.config_summary()

    def _estimate_order_price(self, code: str, order_type: str, price: Optional[float]) -> float:
        if order_type.upper() != "MARKET":
            return float(price or 0.0)
        snapshot = self.quote.snapshot([code])
        if not snapshot:
            return 0.0
        row = snapshot[0]
        for key in ("last_price", "price", "cur_price", "close_price"):
            val = row.get(key)
            if val not in (None, "", "N/A"):
                try:
                    return float(val)
                except (TypeError, ValueError):
                    continue
        return 0.0

    def place_order(self, req: OrderRequest) -> dict:
        trd_env_name = normalize_trd_env(req.trd_env)
        trd_env = parse_trd_env(trd_env_name)

        side = TrdSide.BUY if req.side.upper() == "BUY" else TrdSide.SELL
        if req.order_type.upper() == "MARKET":
            order_type = OrderType.MARKET
            price = 0.0
        else:
            order_type = OrderType.NORMAL
            if req.price is None:
                raise ValueError("限價單必須指定 price")
            price = float(req.price)

        estimated_price = self._estimate_order_price(req.code, req.order_type, req.price)
        decision = self.risk.validate_order(
            code=req.code,
            side=req.side,
            quantity=req.quantity,
            order_type=req.order_type,
            trd_env=trd_env_name,
            estimated_price=estimated_price,
            confirmed=req.confirmed,
        )
        if not decision.allowed:
            return {
                "status": "blocked",
                "message": decision.reason,
                "trd_env": trd_env_name,
                "code": req.code,
                "side": req.side,
                "quantity": req.quantity,
                "price": req.price,
                "estimated_price": estimated_price,
                "estimated_notional": decision.estimated_notional,
            }

        market = infer_market_from_code(req.code)
        acc = self._resolve_acc_id(trd_env_name, req.acc_id)
        with self.client.trade(market) as ctx:
            ret, data = ctx.place_order(
                price=price,
                qty=int(req.quantity),
                code=req.code,
                trd_side=side,
                order_type=order_type,
                trd_env=trd_env,
                acc_id=acc,
            )
            self._ensure_ok(ret, data, "下單")
            row = data.iloc[0] if hasattr(data, "iloc") else data
            order_id = row.get("order_id") if hasattr(row, "get") else str(data)
            return {
                "status": "submitted",
                "order_id": str(order_id),
                "code": req.code,
                "side": req.side.upper(),
                "quantity": req.quantity,
                "price": price,
                "trd_env": trd_env_name,
            }

    def cancel_order(
        self,
        order_id: str,
        code: str,
        trd_env: TrdEnvName = "SIMULATE",
        acc_id: int = 0,
    ) -> dict:
        market = infer_market_from_code(code)
        env = parse_trd_env(trd_env)
        acc = self._resolve_acc_id(trd_env, acc_id)
        with self.client.trade(market) as ctx:
            ret, data = ctx.modify_order(
                modify_order_op=ModifyOrderOp.CANCEL,
                order_id=order_id,
                qty=0,
                price=0,
                trd_env=env,
                acc_id=acc,
            )
            self._ensure_ok(ret, data, "撤單")
            return {"status": "cancelled", "order_id": order_id, "trd_env": normalize_trd_env(trd_env)}
