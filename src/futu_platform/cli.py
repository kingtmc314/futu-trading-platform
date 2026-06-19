"""命令列介面。"""

from __future__ import annotations

import argparse
import json
import sys

from .world_monitor import WorldMonitorService


def _print(data: object) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2, default=str))


def cmd_health(_: argparse.Namespace) -> None:
    from .client import FutuClient
    from .config import get_settings

    try:
        FutuClient().check_opend()
        _print({"status": "ok", "opend": "connected", **get_settings().model_dump()})
    except ConnectionError as exc:
        _print({"status": "error", "error": str(exc)})
        sys.exit(1)


def cmd_overview(_: argparse.Namespace) -> None:
    from .trade_service import TradeService

    _print(TradeService().overview())


def cmd_snapshot(args: argparse.Namespace) -> None:
    from .quote_service import QuoteService

    data = QuoteService().snapshot(args.codes.split(","))
    _print({"data": data})


def cmd_kline(args: argparse.Namespace) -> None:
    from .quote_service import QuoteService

    data = QuoteService().kline(args.code, ktype=args.ktype, count=args.count)
    _print({"data": data})


def cmd_portfolio(args: argparse.Namespace) -> None:
    from .trade_service import TradeService, normalize_trd_env

    env = normalize_trd_env(args.trd_env)
    _print({"trd_env": env, "data": TradeService().portfolio(args.code, trd_env=env)})


def cmd_order(args: argparse.Namespace) -> None:
    from .trade_service import OrderRequest, TradeService, normalize_trd_env

    result = TradeService().place_order(
        OrderRequest(
            code=args.code,
            side=args.side,
            quantity=args.quantity,
            price=args.price,
            order_type=args.order_type,
            trd_env=normalize_trd_env(args.trd_env),
            confirmed=args.confirmed,
        )
    )
    _print(result)


def cmd_strategy(args: argparse.Namespace) -> None:
    from .strategy import create_engine

    engine = create_engine()
    result = engine.run_once(
        args.name,
        args.code,
        quantity=args.quantity,
        auto_trade=args.auto_trade,
        confirmed=args.confirmed,
        trd_env=args.trd_env,
    )
    _print(result)


def cmd_serve(args: argparse.Namespace) -> None:
    import uvicorn

    from .config import get_settings

    settings = get_settings()
    uvicorn.run(
        "futu_platform.web.app:app",
        host=args.host or settings.web_host,
        port=args.port or settings.web_port,
        reload=False,
    )


def cmd_desktop(args: argparse.Namespace) -> None:
    from .desktop import run_desktop

    run_desktop(host=args.host, port=args.port)


def cmd_world_monitor(args: argparse.Namespace) -> None:
    service = WorldMonitorService()
    if args.action in {"once", "run"}:
        _print(service.run_once(auto_trade=False))
    else:
        _print(service.overview())


def cmd_world_monitor_once(_: argparse.Namespace) -> None:
    _print(WorldMonitorService().run_once(auto_trade=False))


def main() -> None:
    parser = argparse.ArgumentParser(description="富途 OpenAPI 自動交易平台")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("health", help="檢查 OpenD 連線").set_defaults(func=cmd_health)
    sub.add_parser("overview", help="模擬+實盤總覽").set_defaults(func=cmd_overview)

    p = sub.add_parser("snapshot", help="行情快照")
    p.add_argument("codes", help="逗號分隔代碼，如 HK.00700,US.AAPL")
    p.set_defaults(func=cmd_snapshot)

    p = sub.add_parser("kline", help="K 線")
    p.add_argument("code")
    p.add_argument("--ktype", default="K_DAY")
    p.add_argument("--count", type=int, default=100)
    p.set_defaults(func=cmd_kline)

    p = sub.add_parser("portfolio", help="持倉")
    p.add_argument("--code", default=None)
    p.add_argument("--trd-env", default="SIMULATE", choices=["SIMULATE", "REAL"])
    p.set_defaults(func=cmd_portfolio)

    p = sub.add_parser("order", help="下單")
    p.add_argument("code")
    p.add_argument("side", choices=["BUY", "SELL"])
    p.add_argument("quantity", type=int)
    p.add_argument("--price", type=float)
    p.add_argument("--order-type", default="MARKET", choices=["NORMAL", "MARKET"])
    p.add_argument("--trd-env", default="SIMULATE", choices=["SIMULATE", "REAL"])
    p.add_argument("--confirmed", action="store_true")
    p.set_defaults(func=cmd_order)

    p = sub.add_parser("strategy", help="執行策略")
    p.add_argument("name", choices=["ma_cross", "rsi"])
    p.add_argument("code")
    p.add_argument("--quantity", type=int, default=100)
    p.add_argument("--trd-env", default="SIMULATE", choices=["SIMULATE", "REAL"])
    p.add_argument("--auto-trade", action="store_true")
    p.add_argument("--confirmed", action="store_true")
    p.set_defaults(func=cmd_strategy)

    p = sub.add_parser("serve", help="啟動 Web 控制台")
    p.add_argument("--host")
    p.add_argument("--port", type=int)
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser("desktop", help="啟動桌面版（內嵌 Web）")
    p.add_argument("--host")
    p.add_argument("--port", type=int)
    p.set_defaults(func=cmd_desktop)

    p = sub.add_parser("world-monitor", help="World Monitor 財經/政策事件監控")
    p.add_argument("action", choices=["overview", "once", "run"])
    p.set_defaults(func=cmd_world_monitor)

    sub.add_parser("world-monitor-once", help="執行一次 World Monitor（只記錄，不下單）").set_defaults(
        func=cmd_world_monitor_once
    )

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
