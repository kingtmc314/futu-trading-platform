"""Paper Trading 帳戶：資金、持倉、PnL。"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Dict, Optional

from ..logging_setup import get_logger
from ..models import (
    FillRecord,
    OrderSide,
    OrderStatus,
    PortfolioSnapshot,
    Position,
    Signal,
    SignalType,
)
from ..settings import ExecutionConfig, PortfolioConfig

logger = get_logger("paper_trading.portfolio")


class PaperTradingAccount:
    def __init__(self, portfolio_config: PortfolioConfig, execution_config: ExecutionConfig) -> None:
        self._portfolio_cfg = portfolio_config
        self._execution_cfg = execution_config
        self._cash: float = portfolio_config.initial_cash
        self._realized_pnl: float = 0.0
        self._positions: Dict[str, Position] = {}

    @property
    def cash(self) -> float:
        return self._cash

    @property
    def positions(self) -> Dict[str, Position]:
        return dict(self._positions)

    def get_position_qty(self, symbol: str) -> float:
        pos = self._positions.get(symbol)
        return pos.quantity if pos else 0.0

    def _apply_slippage(self, side: OrderSide, price: float) -> float:
        rate = self._portfolio_cfg.slippage_rate
        if side == OrderSide.BUY:
            return price * (1.0 + rate)
        return price * (1.0 - rate)

    def _commission(self, notional: float) -> float:
        return notional * self._portfolio_cfg.commission_rate

    def simulate_fill(
        self,
        signal: Signal,
        market_price: float,
        quantity: Optional[float] = None,
    ) -> FillRecord:
        order_id = str(uuid.uuid4())
        ts = signal.timestamp

        if signal.signal_type == SignalType.HOLD:
            return FillRecord(
                order_id=order_id,
                symbol=signal.symbol,
                side=OrderSide.BUY,
                quantity=0.0,
                fill_price=market_price,
                commission=0.0,
                slippage=0.0,
                timestamp=ts,
                status=OrderStatus.SKIPPED,
                reason="HOLD 信號不下單",
            )

        side = OrderSide.BUY if signal.signal_type == SignalType.BUY else OrderSide.SELL
        fill_price = self._apply_slippage(side, market_price)
        slippage_cost = abs(fill_price - market_price)

        if quantity is None:
            quantity = self._calc_order_qty(signal.symbol, side, fill_price)

        if quantity < self._execution_cfg.min_order_qty:
            logger.warning("數量過小拒絕 | qty=%.8f min=%.8f", quantity, self._execution_cfg.min_order_qty)
            return FillRecord(
                order_id=order_id,
                symbol=signal.symbol,
                side=side,
                quantity=0.0,
                fill_price=fill_price,
                commission=0.0,
                slippage=slippage_cost,
                timestamp=ts,
                status=OrderStatus.REJECTED,
                reason="數量低於最小下單量",
            )

        notional = quantity * fill_price
        commission = self._commission(notional)

        if side == OrderSide.BUY:
            total_cost = notional + commission
            if total_cost > self._cash:
                logger.warning("資金不足 | need=%.2f cash=%.2f", total_cost, self._cash)
                return FillRecord(
                    order_id=order_id,
                    symbol=signal.symbol,
                    side=side,
                    quantity=0.0,
                    fill_price=fill_price,
                    commission=0.0,
                    slippage=slippage_cost,
                    timestamp=ts,
                    status=OrderStatus.REJECTED,
                    reason="資金不足",
                )
            self._cash -= total_cost
            self._update_position_buy(signal.symbol, quantity, fill_price)
            logger.info(
                "模擬買入 | %s qty=%.6f price=%.2f commission=%.4f",
                signal.symbol,
                quantity,
                fill_price,
                commission,
            )
        else:
            held = self.get_position_qty(signal.symbol)
            sell_qty = min(quantity, held)
            if sell_qty <= 0:
                logger.warning("無持倉可賣 | symbol=%s", signal.symbol)
                return FillRecord(
                    order_id=order_id,
                    symbol=signal.symbol,
                    side=side,
                    quantity=0.0,
                    fill_price=fill_price,
                    commission=0.0,
                    slippage=slippage_cost,
                    timestamp=ts,
                    status=OrderStatus.REJECTED,
                    reason="無持倉可賣",
                )
            proceeds = sell_qty * fill_price - self._commission(sell_qty * fill_price)
            commission = self._commission(sell_qty * fill_price)
            pnl = self._update_position_sell(signal.symbol, sell_qty, fill_price)
            self._cash += proceeds
            self._realized_pnl += pnl
            quantity = sell_qty
            logger.info(
                "模擬賣出 | %s qty=%.6f price=%.2f pnl=%.2f commission=%.4f",
                signal.symbol,
                sell_qty,
                fill_price,
                pnl,
                commission,
            )

        return FillRecord(
            order_id=order_id,
            symbol=signal.symbol,
            side=side,
            quantity=quantity,
            fill_price=fill_price,
            commission=commission if side == OrderSide.BUY else self._commission(quantity * fill_price),
            slippage=slippage_cost * quantity,
            timestamp=ts,
            status=OrderStatus.FILLED,
            reason=signal.reason,
        )

    def _calc_order_qty(self, symbol: str, side: OrderSide, price: float) -> float:
        if side == OrderSide.SELL:
            return self.get_position_qty(symbol)
        max_spend = self._cash * self._portfolio_cfg.max_position_pct
        if price <= 0:
            return 0.0
        qty = max_spend / price
        return round(qty, 8)

    def _update_position_buy(self, symbol: str, qty: float, price: float) -> None:
        pos = self._positions.get(symbol)
        if pos is None:
            self._positions[symbol] = Position(symbol=symbol, quantity=qty, avg_cost=price)
            return
        total_qty = pos.quantity + qty
        pos.avg_cost = (pos.quantity * pos.avg_cost + qty * price) / total_qty
        pos.quantity = total_qty

    def _update_position_sell(self, symbol: str, qty: float, price: float) -> float:
        pos = self._positions[symbol]
        pnl = (price - pos.avg_cost) * qty
        pos.quantity -= qty
        if pos.quantity <= self._execution_cfg.min_order_qty:
            del self._positions[symbol]
        return pnl

    def snapshot(self, mark_prices: Dict[str, float], ts: Optional[datetime] = None) -> PortfolioSnapshot:
        from datetime import timezone

        timestamp = ts or datetime.now(tz=timezone.utc)
        unrealized = 0.0
        equity = self._cash
        for sym, pos in self._positions.items():
            mark = mark_prices.get(sym, pos.avg_cost)
            unrealized += (mark - pos.avg_cost) * pos.quantity
            equity += mark * pos.quantity
        return PortfolioSnapshot(
            timestamp=timestamp,
            cash=self._cash,
            equity=equity,
            unrealized_pnl=unrealized,
            realized_pnl=self._realized_pnl,
            positions=dict(self._positions),
            metadata={"base_currency": self._portfolio_cfg.base_currency},
        )
