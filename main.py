#!/usr/bin/env python3
"""
模擬程式交易系統入口。

用法:
  # 演示模式（約 2 分鐘，Mock 數據）
  PAPER_DEMO=1 PAPER_DATA_PROVIDER=mock python main.py

  # 24 小時 Binance 真實報價模擬交易
  PAPER_DATA_PROVIDER=binance python main.py

  # 自訂配置
  PAPER_CONFIG=paper_trading/config.yaml python main.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from paper_trading.engine import TradingEngine  # noqa: E402


def main() -> None:
    engine = TradingEngine()
    engine.run()


if __name__ == "__main__":
    main()
