# Futu 程式化自動交易平台

基於 [富途 OpenAPI](https://openapi.futunn.com/futu-api-doc/hk/intro/intro.html) 的 Python 自動交易平台，整合官方 Skills 與完整 API 文檔。

## 功能

- **雙環境並存**：同一介面同時查看/操作 **模擬 (SIMULATE)** 與 **實盤 (REAL)**
- **行情**：快照、歷史 K 線、報價訂閱
- **交易**：下單、撤單、持倉、資金、訂單
- **策略引擎**：可插拔策略 + 定時調度（可指定模擬或實盤）
- **Web 控制台**：雙欄對比 UI
- **桌面版（可選）**：pywebview 內嵌 Web，獨立視窗體驗

## 前置條件

1. 安裝並登入 [OpenD](https://openapi.futunn.com/futu-api-doc/hk/quick/opend-base.html)
2. Python 3.10+
3. 模擬交易可直接使用；實盤需在 OpenD 解鎖交易並設 `FUTU_TRD_ENV=REAL`

## 快速開始

```bash
cd ~/Projects/futu-trading-platform
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

cp .env.example .env
# 編輯 .env（預設已指向 127.0.0.1:11111 模擬環境）

# 檢查 OpenD 連線
futu-trade health

# 查詢騰訊快照
futu-trade snapshot HK.00700

# 執行雙均線策略（僅信號，不下單）
futu-trade strategy ma_cross HK.00700

# 啟動 Web 控制台（模擬+實盤雙欄）
futu-trade serve
# 瀏覽 http://127.0.0.1:8080

# 或啟動桌面版（獨立視窗）
pip install -e ".[desktop]"
futu-trade desktop

# CLI 查看雙環境總覽
futu-trade overview
```

## 專案結構

```
futu-trading-platform/
├── docs/                    # 官方 API Markdown 文檔（737KB）
├── vendor/skills/           # 官方 OpenD Skills（行情/交易腳本）
├── .cursor/skills/          # Cursor 技能包
├── src/futu_platform/
│   ├── client.py            # OpenD 連線
│   ├── quote_service.py     # 行情
│   ├── trade_service.py       # 交易
│   ├── strategy/            # 策略框架
│   ├── runner.py            # 定時調度
│   ├── web/                 # FastAPI + 控制台
│   └── cli.py               # 命令列
└── strategies/default.yaml  # 策略配置範例
```

## 已下載資源

| 資源 | 路徑 | 來源 |
|------|------|------|
| API 文檔 (繁中 Python) | `docs/Futu-API-Doc-hk-Python.md` | [Markdown 下載](https://openapi.futunn.com/mds/Futu-API-Doc-hk-Python.md) |
| OpenD Skills | `vendor/skills/` | [opend-skills.zip](https://openapi.futunn.com/skills/opend-skills.zip) |
| futuapi 技能 | `.cursor/skills/futuapi/` | 同上 |
| install-futu-opend 技能 | `.cursor/skills/install-futu-opend/` | 同上 |

## API 端點（Web）

| 方法 | 路徑 | 說明 |
|------|------|------|
| GET | `/api/health` | OpenD 連線狀態 |
| GET | `/api/quote/snapshot?codes=HK.00700` | 快照 |
| GET | `/api/quote/kline?code=HK.00700` | K 線 |
| GET | `/api/trade/portfolio` | 持倉 |
| POST | `/api/trade/order` | 下單 |
| GET | `/api/strategy/run?strategy=ma_cross&code=HK.00700` | 執行策略 |
| POST | `/api/strategy/schedule` | 定時策略 |

## 安全提示

- **預設使用模擬環境** (`FUTU_TRD_ENV=SIMULATE`)
- 實盤下單需明確設 `confirmed=true` 並在 OpenD 解鎖交易
- 遵守 API 限頻（下單 15 次/30 秒）
- 交易涉及真實資金，請先在模擬環境充分測試

## 授權

本平台代碼為示例用途。富途 API 使用須遵守 `vendor/skills/LEGAL_*.md` 中的條款。
