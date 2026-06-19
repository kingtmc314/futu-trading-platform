"""SQLite 與 CSV 持久化。"""

from __future__ import annotations

import csv
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional

from .models import FillRecord, MarketBar, PortfolioSnapshot, Signal


class StorageBackend:
    def initialize(self) -> None:
        raise NotImplementedError

    def save_bars(self, bars: Iterable[MarketBar]) -> None:
        raise NotImplementedError

    def save_signal(self, signal: Signal) -> None:
        raise NotImplementedError

    def save_fill(self, fill: FillRecord) -> None:
        raise NotImplementedError

    def save_snapshot(self, snapshot: PortfolioSnapshot) -> None:
        raise NotImplementedError

    def export_fills_csv(self, csv_path: Path) -> None:
        raise NotImplementedError


class SQLiteStorage(StorageBackend):
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def initialize(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS market_bars (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    open REAL, high REAL, low REAL, close REAL, volume REAL
                );
                CREATE TABLE IF NOT EXISTS signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT, signal_type TEXT, timestamp TEXT,
                    price REAL, reason TEXT, metadata TEXT
                );
                CREATE TABLE IF NOT EXISTS fills (
                    order_id TEXT PRIMARY KEY,
                    symbol TEXT, side TEXT, quantity REAL,
                    fill_price REAL, commission REAL, slippage REAL,
                    timestamp TEXT, status TEXT, reason TEXT
                );
                CREATE TABLE IF NOT EXISTS portfolio_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT, cash REAL, equity REAL,
                    unrealized_pnl REAL, realized_pnl REAL, positions_json TEXT
                );
                """
            )

    def save_bars(self, bars: Iterable[MarketBar]) -> None:
        rows = [
            (b.symbol, b.timestamp.isoformat(), b.open, b.high, b.low, b.close, b.volume)
            for b in bars
        ]
        if not rows:
            return
        with self._connect() as conn:
            conn.executemany(
                "INSERT INTO market_bars (symbol,timestamp,open,high,low,close,volume) VALUES (?,?,?,?,?,?,?)",
                rows,
            )

    def save_signal(self, signal: Signal) -> None:
        import json

        with self._connect() as conn:
            conn.execute(
                "INSERT INTO signals (symbol,signal_type,timestamp,price,reason,metadata) VALUES (?,?,?,?,?,?)",
                (
                    signal.symbol,
                    signal.signal_type.value,
                    signal.timestamp.isoformat(),
                    signal.price,
                    signal.reason,
                    json.dumps(signal.metadata, ensure_ascii=False),
                ),
            )

    def save_fill(self, fill: FillRecord) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO fills
                (order_id,symbol,side,quantity,fill_price,commission,slippage,timestamp,status,reason)
                VALUES (?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    fill.order_id,
                    fill.symbol,
                    fill.side.value,
                    fill.quantity,
                    fill.fill_price,
                    fill.commission,
                    fill.slippage,
                    fill.timestamp.isoformat(),
                    fill.status.value,
                    fill.reason,
                ),
            )

    def save_snapshot(self, snapshot: PortfolioSnapshot) -> None:
        import json

        positions = {
            sym: {"quantity": pos.quantity, "avg_cost": pos.avg_cost}
            for sym, pos in snapshot.positions.items()
        }
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO portfolio_snapshots
                (timestamp,cash,equity,unrealized_pnl,realized_pnl,positions_json)
                VALUES (?,?,?,?,?,?)
                """,
                (
                    snapshot.timestamp.isoformat(),
                    snapshot.cash,
                    snapshot.equity,
                    snapshot.unrealized_pnl,
                    snapshot.realized_pnl,
                    json.dumps(positions, ensure_ascii=False),
                ),
            )

    def export_fills_csv(self, csv_path: Path) -> None:
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            rows: List[sqlite3.Row] = conn.execute("SELECT * FROM fills ORDER BY timestamp").fetchall()
        if not rows:
            return
        with csv_path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows([dict(r) for r in rows])
