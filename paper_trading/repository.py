"""SQLite 唯讀查詢（供 Web API 使用）。"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def _parse_ts(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    return dict(row)


@dataclass(frozen=True)
class RunStatus:
    db_exists: bool
    has_data: bool
    db_path: str
    log_path: str
    log_updated_at: Optional[str]
    last_snapshot_at: Optional[str]
    snapshot_age_seconds: Optional[float]
    likely_running: bool
    config: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "db_exists": self.db_exists,
            "has_data": self.has_data,
            "db_path": self.db_path,
            "log_path": self.log_path,
            "log_updated_at": self.log_updated_at,
            "last_snapshot_at": self.last_snapshot_at,
            "snapshot_age_seconds": self.snapshot_age_seconds,
            "likely_running": self.likely_running,
            "config": self.config,
        }


class PaperTradingRepository:
    """從 SQLite 讀取模擬交易結果。"""

    def __init__(self, db_path: Path, log_path: Path, poll_interval_seconds: int = 60) -> None:
        self._db_path = db_path
        self._log_path = log_path
        self._poll_interval_seconds = poll_interval_seconds

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def db_exists(self) -> bool:
        return self._db_path.is_file()

    def get_latest_snapshot(self) -> Optional[Dict[str, Any]]:
        if not self.db_exists():
            return None
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, timestamp, cash, equity, unrealized_pnl, realized_pnl, positions_json
                FROM portfolio_snapshots
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()
        if not row:
            return None
        data = _row_to_dict(row)
        positions_raw = data.pop("positions_json", "{}") or "{}"
        try:
            positions = json.loads(positions_raw)
        except json.JSONDecodeError:
            positions = {}
        data["positions"] = [
            {
                "symbol": sym,
                "quantity": pos.get("quantity", 0),
                "avg_cost": pos.get("avg_cost", 0),
                "market_value": float(pos.get("quantity", 0)) * float(pos.get("avg_cost", 0)),
            }
            for sym, pos in positions.items()
            if float(pos.get("quantity", 0)) != 0
        ]
        return data

    def get_fills(self, limit: int = 100) -> List[Dict[str, Any]]:
        if not self.db_exists():
            return []
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT order_id, symbol, side, quantity, fill_price, commission,
                       slippage, timestamp, status, reason
                FROM fills
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [_row_to_dict(r) for r in rows]

    def get_signals(self, limit: int = 50) -> List[Dict[str, Any]]:
        if not self.db_exists():
            return []
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, symbol, signal_type, timestamp, price, reason, metadata
                FROM signals
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        result: List[Dict[str, Any]] = []
        for row in rows:
            item = _row_to_dict(row)
            meta_raw = item.pop("metadata", None)
            if meta_raw:
                try:
                    item["metadata"] = json.loads(meta_raw)
                except json.JSONDecodeError:
                    item["metadata"] = meta_raw
            result.append(item)
        return result

    def get_equity_summary(self, initial_cash: float) -> Dict[str, Any]:
        snap = self.get_latest_snapshot()
        if not snap:
            return {
                "initial_cash": initial_cash,
                "cash": None,
                "equity": None,
                "realized_pnl": None,
                "unrealized_pnl": None,
                "total_pnl": None,
                "return_pct": None,
                "timestamp": None,
                "position_count": 0,
            }
        equity = float(snap.get("equity") or 0)
        total_pnl = equity - initial_cash
        return_pct = (total_pnl / initial_cash * 100) if initial_cash else None
        positions = snap.get("positions") or []
        return {
            "initial_cash": initial_cash,
            "cash": snap.get("cash"),
            "equity": snap.get("equity"),
            "realized_pnl": snap.get("realized_pnl"),
            "unrealized_pnl": snap.get("unrealized_pnl"),
            "total_pnl": total_pnl,
            "return_pct": return_pct,
            "timestamp": snap.get("timestamp"),
            "position_count": len(positions),
        }

    def get_run_status(self, config_summary: Dict[str, Any]) -> RunStatus:
        db_exists = self.db_exists()
        snap = self.get_latest_snapshot() if db_exists else None
        last_ts = _parse_ts(snap.get("timestamp") if snap else None)
        now = datetime.now(timezone.utc)
        if last_ts and last_ts.tzinfo is None:
            last_ts = last_ts.replace(tzinfo=timezone.utc)
        age: Optional[float] = None
        if last_ts:
            age = (now - last_ts.astimezone(timezone.utc)).total_seconds()
        poll = max(self._poll_interval_seconds, 1)
        likely_running = age is not None and age <= poll * 2.5

        log_updated: Optional[str] = None
        if self._log_path.is_file():
            mtime = datetime.fromtimestamp(self._log_path.stat().st_mtime, tz=timezone.utc)
            log_updated = mtime.isoformat()

        return RunStatus(
            db_exists=db_exists,
            has_data=snap is not None,
            db_path=str(self._db_path),
            log_path=str(self._log_path),
            log_updated_at=log_updated,
            last_snapshot_at=snap.get("timestamp") if snap else None,
            snapshot_age_seconds=age,
            likely_running=likely_running,
            config=config_summary,
        )

    def overview(self, initial_cash: float, config_summary: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "status": self.get_run_status(config_summary).to_dict(),
            "summary": self.get_equity_summary(initial_cash),
            "snapshot": self.get_latest_snapshot(),
            "fills": self.get_fills(),
            "signals": self.get_signals(),
        }
