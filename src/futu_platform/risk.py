"""實盤交易風控閘門。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .config import Settings, get_settings


@dataclass(frozen=True)
class RiskDecision:
    allowed: bool
    reason: str
    estimated_notional: float = 0.0


class RiskManager:
    """集中管理下單前風控。

    模擬交易只做基本數量檢查；實盤交易預設關閉，並限制市場、數量與單筆金額。
    """

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self._settings = settings or get_settings()

    @property
    def allowed_prefixes(self) -> list[str]:
        raw = self._settings.futu_real_allowed_prefixes
        return [p.strip().upper() for p in raw.split(",") if p.strip()]

    def config_summary(self) -> dict:
        return {
            "real_trading_enabled": self._settings.futu_real_trading_enabled,
            "real_max_order_value": self._settings.futu_real_max_order_value,
            "real_max_quantity": self._settings.futu_real_max_quantity,
            "real_allowed_prefixes": self.allowed_prefixes,
            "real_market_order_allowed": self._settings.futu_real_market_order_allowed,
        }

    def validate_order(
        self,
        *,
        code: str,
        side: str,
        quantity: int,
        order_type: str,
        trd_env: str,
        estimated_price: float,
        confirmed: bool,
    ) -> RiskDecision:
        if quantity <= 0:
            return RiskDecision(False, "下單數量必須大於 0")

        env = trd_env.upper()
        if env != "REAL":
            return RiskDecision(True, "模擬交易通過基本風控")

        if not confirmed:
            return RiskDecision(False, "實盤下單必須勾選確認")

        if not self._settings.futu_real_trading_enabled:
            return RiskDecision(False, "實盤下單目前被風控關閉，請在 .env 設 FUTU_REAL_TRADING_ENABLED=true")

        prefix = code.split(".", 1)[0].upper() if "." in code else ""
        if prefix not in self.allowed_prefixes:
            return RiskDecision(False, f"市場 {prefix or code} 不在允許清單: {', '.join(self.allowed_prefixes)}")

        if quantity > self._settings.futu_real_max_quantity:
            return RiskDecision(False, f"數量 {quantity} 超過單筆上限 {self._settings.futu_real_max_quantity}")

        if order_type.upper() == "MARKET" and not self._settings.futu_real_market_order_allowed:
            return RiskDecision(False, "實盤市價單目前被風控關閉，請使用限價單或開啟 FUTU_REAL_MARKET_ORDER_ALLOWED")

        if estimated_price <= 0:
            return RiskDecision(False, "無法估算下單價格，拒絕實盤下單")

        notional = estimated_price * quantity
        if notional > self._settings.futu_real_max_order_value:
            return RiskDecision(
                False,
                f"單筆估算金額 {notional:.2f} 超過上限 {self._settings.futu_real_max_order_value:.2f}",
                notional,
            )

        return RiskDecision(True, "實盤風控通過", notional)
