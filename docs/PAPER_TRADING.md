# 模擬程式交易系統 (Paper Trading)

基於 OOP 的模組化模擬交易框架，串接真實報價 API，在本地模擬帳戶中執行策略並記錄績效。

## 系統架構

```mermaid
flowchart TB
    subgraph Input
        CFG[config.yaml / 環境變數]
        API[Binance / Mock API]
    end

    subgraph Core
        DH[DataHandler]
        ST[Strategy]
        PF[PaperTradingAccount]
        EX[ExecutionHandler]
        ENG[TradingEngine]
    end

    subgraph Output
        LOG[Logging]
        SQL[(SQLite)]
        CSV[fills_export.csv]
    end

    CFG --> ENG
    API --> DH
    ENG --> DH
    ENG --> ST
    ENG --> EX
    EX --> PF
    EX --> SQL
    DH --> ST
    ST -->|Signal| EX
    PF -->|Snapshot| SQL
    ENG --> LOG
    ENG --> CSV
```

## 運行流程

```mermaid
sequenceDiagram
    participant E as TradingEngine
    participant D as DataHandler
    participant S as Strategy
    participant X as ExecutionHandler
    participant P as PaperTradingAccount
    participant DB as SQLiteStorage

    loop 每 poll_interval 秒
        E->>D: fetch_klines()
        E->>D: fetch_latest_ticker()
        E->>S: generate_signal(df)
        alt BUY / SELL
            E->>X: on_signal(signal, price)
            X->>P: simulate_fill()
            X->>DB: save_fill()
        end
        E->>P: snapshot()
        E->>DB: save_snapshot()
    end
```

## 模組說明

| 模組 | 檔案 | 職責 |
|------|------|------|
| DataHandler | `paper_trading/data/handler.py` | Binance / Mock K 線與 Ticker |
| Strategy | `paper_trading/strategy/base.py` | 均線交叉 + 可擴充介面 |
| Portfolio | `paper_trading/portfolio/paper.py` | 虛擬資金、持倉、手續費、滑點、PnL |
| ExecutionHandler | `paper_trading/execution/handler.py` | 模擬下單與交易日誌 |
| Storage | `paper_trading/storage.py` | SQLite + CSV 匯出 |
| Engine | `paper_trading/engine.py` | 主迴圈協調 |

## 快速開始

```bash
cd ~/Projects/futu-trading-platform
source .venv/bin/activate
pip install pyyaml httpx pandas

# 演示（Mock 數據，約 2 分鐘）
PAPER_DEMO=1 PAPER_DATA_PROVIDER=mock python main.py

# 24 小時 Binance 真實報價模擬
PAPER_DATA_PROVIDER=binance python main.py
```

## 環境變數

| 變數 | 說明 |
|------|------|
| `PAPER_DEMO` | `1` 時使用演示時長 |
| `PAPER_DATA_PROVIDER` | `binance` / `mock` |
| `PAPER_SYMBOL` | 交易對，如 `BTCUSDT` |
| `PAPER_RUN_HOURS` | 運行時長（小時） |
| `PAPER_CONFIG` | 配置檔路徑 |

## 自訂策略

繼承 `Strategy` 並實作 `generate_signal()`，在 `create_strategy()` 註冊即可。
