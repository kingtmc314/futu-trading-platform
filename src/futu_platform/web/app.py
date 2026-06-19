"""FastAPI Web 控制台與 REST API（模擬 + 實盤並存）。"""

from __future__ import annotations

from pathlib import Path
from typing import Literal, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from ..client import FutuClient
from ..config import get_settings
from ..paper_trading_service import PaperTradingService
from ..quote_service import QuoteService
from ..runner import StrategyRunner
from ..strategy import create_engine
from ..trade_service import OrderRequest, TradeService, normalize_trd_env

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="Futu Trading Platform", version="0.2.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

quote_service = QuoteService()
trade_service = TradeService()
paper_trading_service = PaperTradingService()
strategy_engine = create_engine()
strategy_runner = StrategyRunner()


class OrderBody(BaseModel):
    code: str
    side: str = Field(pattern="^(BUY|SELL)$")
    quantity: int = Field(gt=0)
    price: Optional[float] = None
    order_type: str = "NORMAL"
    trd_env: Literal["SIMULATE", "REAL"] = "SIMULATE"
    acc_id: int = 0
    confirmed: bool = False


class CancelBody(BaseModel):
    order_id: str
    code: str
    trd_env: Literal["SIMULATE", "REAL"] = "SIMULATE"
    acc_id: int = 0


class ScheduleBody(BaseModel):
    job_id: str
    strategy: str
    code: str
    interval_seconds: int = Field(default=60, ge=10)
    quantity: int = Field(default=100, gt=0)
    auto_trade: bool = False
    confirmed: bool = False
    trd_env: Literal["SIMULATE", "REAL"] = "SIMULATE"


@app.get("/", response_class=HTMLResponse)
def dashboard() -> HTMLResponse:
    return HTMLResponse((STATIC_DIR / "index.html").read_text(encoding="utf-8"))


@app.get("/api/health")
def health() -> dict:
    try:
        FutuClient().check_opend()
        return {
            "status": "ok",
            "opend": "connected",
            "default_trd_env": get_settings().futu_trd_env,
            "modes": ["SIMULATE", "REAL"],
        }
    except ConnectionError as exc:
        return {"status": "degraded", "opend": "disconnected", "error": str(exc)}


@app.get("/api/trade/overview")
def api_overview() -> dict:
    try:
        return trade_service.overview()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/risk/config")
def api_risk_config() -> dict:
    return {"data": trade_service.risk_summary()}


@app.get("/api/quote/snapshot")
def api_snapshot(codes: str) -> dict:
    code_list = [c.strip() for c in codes.split(",") if c.strip()]
    try:
        return {"data": quote_service.snapshot(code_list)}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/quote/kline")
def api_kline(code: str, ktype: str = "K_DAY", count: int = 100) -> dict:
    try:
        return {"data": quote_service.kline(code, ktype=ktype, count=count)}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/trade/accounts")
def api_accounts(trd_env: Optional[str] = Query(None)) -> dict:
    try:
        env = normalize_trd_env(trd_env) if trd_env else None
        return {"data": trade_service.accounts(env)}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/trade/acc-info")
def api_acc_info(trd_env: str = "SIMULATE", acc_id: int = 0) -> dict:
    try:
        return {"data": trade_service.acc_info(normalize_trd_env(trd_env), acc_id)}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/trade/portfolio")
def api_portfolio(
    code: Optional[str] = None,
    trd_env: str = "SIMULATE",
    acc_id: int = 0,
) -> dict:
    try:
        return {
            "trd_env": normalize_trd_env(trd_env),
            "data": trade_service.portfolio(code, trd_env=normalize_trd_env(trd_env), acc_id=acc_id),
        }
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/trade/orders")
def api_orders(trd_env: str = "SIMULATE", acc_id: int = 0) -> dict:
    try:
        return {
            "trd_env": normalize_trd_env(trd_env),
            "data": trade_service.orders(trd_env=normalize_trd_env(trd_env), acc_id=acc_id),
        }
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/trade/order")
def api_place_order(body: OrderBody) -> dict:
    try:
        return trade_service.place_order(
            OrderRequest(
                code=body.code,
                side=body.side,
                quantity=body.quantity,
                price=body.price,
                order_type=body.order_type,
                trd_env=body.trd_env,
                acc_id=body.acc_id,
                confirmed=body.confirmed,
            )
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/trade/cancel")
def api_cancel_order(body: CancelBody) -> dict:
    try:
        return trade_service.cancel_order(
            body.order_id,
            body.code,
            trd_env=body.trd_env,
            acc_id=body.acc_id,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/strategies")
def api_strategies() -> dict:
    return {"data": strategy_engine.list_strategies()}


@app.get("/api/strategy/run")
def api_run_strategy(
    strategy: str,
    code: str,
    quantity: int = 100,
    auto_trade: bool = False,
    confirmed: bool = False,
    trd_env: str = "SIMULATE",
) -> dict:
    try:
        return strategy_engine.run_once(
            strategy,
            code,
            quantity=quantity,
            auto_trade=auto_trade,
            confirmed=confirmed,
            trd_env=trd_env,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/strategy/schedule")
def api_schedule(body: ScheduleBody) -> dict:
    if body.strategy not in strategy_engine.list_strategies():
        raise HTTPException(status_code=404, detail=f"未知策略: {body.strategy}")
    return strategy_runner.schedule(
        body.job_id,
        body.strategy,
        body.code,
        body.interval_seconds,
        quantity=body.quantity,
        auto_trade=body.auto_trade,
        confirmed=body.confirmed,
        trd_env=body.trd_env,
    )


@app.get("/api/strategy/jobs")
def api_jobs() -> dict:
    return {"data": strategy_runner.status()}


@app.delete("/api/strategy/jobs/{job_id}")
def api_unschedule(job_id: str) -> dict:
    ok = strategy_runner.unschedule(job_id)
    if not ok:
        raise HTTPException(status_code=404, detail="任務不存在")
    return {"status": "removed", "job_id": job_id}


@app.get("/api/paper-trading/overview")
def api_paper_overview() -> dict:
    try:
        return paper_trading_service.overview()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/paper-trading/snapshot")
def api_paper_snapshot() -> dict:
    try:
        data = paper_trading_service.snapshot()
        if data is None:
            return {"data": None, "message": "尚無快照資料，請先執行 python main.py"}
        return {"data": data}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/paper-trading/fills")
def api_paper_fills(limit: int = Query(100, ge=1, le=500)) -> dict:
    try:
        return {"data": paper_trading_service.fills(limit=limit)}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/paper-trading/signals")
def api_paper_signals(limit: int = Query(50, ge=1, le=200)) -> dict:
    try:
        return {"data": paper_trading_service.signals(limit=limit)}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/paper-trading/summary")
def api_paper_summary() -> dict:
    try:
        return {"data": paper_trading_service.summary()}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/paper-trading/status")
def api_paper_status() -> dict:
    try:
        return {"data": paper_trading_service.status()}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


def create_app() -> FastAPI:
    return app
