"""World Monitor event scoring and guarded trade recommendations.

This module keeps the integration intentionally local: it reads public RSS/Atom
feeds with the standard library, scores finance and policy headlines, persists
SQLite snapshots, and never places live orders unless explicitly configured.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable, Optional
from urllib.parse import quote_plus
from urllib.request import Request, urlopen
from xml.etree import ElementTree

if TYPE_CHECKING:
    from apscheduler.schedulers.background import BackgroundScheduler

    from .config import Settings
    from .trade_service import TradeService

logger = logging.getLogger(__name__)


Signal = str

POSITIVE_TERMS: dict[str, float] = {
    "stimulus": 1.4,
    "cut rates": 1.6,
    "cut": 0.8,
    "rate cut": 1.6,
    "easing": 1.2,
    "dovish": 1.2,
    "deal": 1.0,
    "growth": 0.8,
    "earnings": 0.7,
    "beats": 0.8,
    "approval": 0.7,
    "support": 0.6,
    "降息": 1.6,
    "寬鬆": 1.2,
    "刺激": 1.2,
    "利好": 1.0,
    "復甦": 0.8,
}

NEGATIVE_TERMS: dict[str, float] = {
    "rate": -0.2,
    "tariff": -1.3,
    "sanction": -1.2,
    "ban": -1.1,
    "war": -1.5,
    "conflict": -1.1,
    "inflation": -1.0,
    "hawkish": -1.1,
    "rate hike": -1.5,
    "recession": -1.6,
    "regulation": -1.0,
    "default": -1.4,
    "misses": -0.8,
    "probe": -0.8,
    "關稅": -1.3,
    "制裁": -1.2,
    "加息": -1.5,
    "衰退": -1.6,
    "通脹": -1.0,
    "風險": -0.7,
}

SOURCE_TIERS = {
    "policy": 1,
    "central_bank": 1,
    "finance": 2,
    "market": 2,
    "news": 3,
}


@dataclass(frozen=True)
class MonitorSource:
    name: str
    url: str
    category: str = "news"


@dataclass
class MonitorEvent:
    event_id: str
    source: str
    category: str
    title: str
    link: str
    published_at: str
    fetched_at: str
    sentiment: float
    impact: float
    matched_terms: list[str] = field(default_factory=list)


@dataclass
class SignalQuality:
    confidence: float
    intensity: float
    expectation_gap: float
    timeliness: float
    composite: float
    tier: str


@dataclass
class WorldMonitorRecommendation:
    symbol: str
    signal: Signal
    score: float
    confidence: float
    reason: str
    generated_at: str
    order: Optional[dict[str, Any]] = None


@dataclass
class WorldMonitorRun:
    run_id: str
    started_at: str
    completed_at: str
    score: float
    signal_quality: SignalQuality
    event_count: int
    top_events: list[MonitorEvent]
    recommendations: list[WorldMonitorRecommendation]
    errors: list[str] = field(default_factory=list)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_now() -> str:
    return _utc_now().isoformat()


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _normalize_trd_env(env: str) -> str:
    return "REAL" if env and env.upper() == "REAL" else "SIMULATE"


def _asdict(obj: Any) -> dict[str, Any]:
    return asdict(obj)


def parse_sources(raw: str) -> list[MonitorSource]:
    """Parse env source config: ``category:name=url`` or ``category:url``."""
    sources: list[MonitorSource] = []
    for chunk in raw.split(","):
        token = chunk.strip()
        if not token:
            continue
        category = "news"
        rest = token
        if ":" in token and not token.lower().startswith(("http://", "https://")):
            category, rest = token.split(":", 1)
        name = category.strip() or "news"
        url = rest.strip()
        if "=" in rest and not rest.lower().startswith(("http://", "https://")):
            name, url = [part.strip() for part in rest.split("=", 1)]
        if url:
            sources.append(MonitorSource(name=name or category, url=url, category=category or "news"))
    return sources


def build_google_news_source(symbol: str) -> MonitorSource:
    query = quote_plus(symbol.replace(".", " "))
    return MonitorSource(
        name=f"{symbol} news",
        category="finance",
        url=f"https://news.google.com/rss/search?q={query}+stock+market&hl=en-US&gl=US&ceid=US:en",
    )


def score_text(text: str) -> tuple[float, list[str]]:
    normalized = text.lower()
    score = 0.0
    matches: list[str] = []
    for term, weight in POSITIVE_TERMS.items():
        if term.lower() in normalized:
            score += weight
            matches.append(term)
    for term, weight in NEGATIVE_TERMS.items():
        if term.lower() in normalized:
            score += weight
            matches.append(term)
    return round(_clamp(score, -5.0, 5.0), 3), matches


def compute_signal_quality(events: list[MonitorEvent]) -> SignalQuality:
    source_count = len({event.source for event in events})
    strongest = max((abs(event.impact) for event in events), default=0.0)
    tier = min((SOURCE_TIERS.get(event.category, 3) for event in events), default=3)
    confidence = _clamp(
        (1.0 if source_count >= 3 else 0.7 if source_count == 2 else 0.4 if source_count else 0.0)
        + (0.1 if tier <= 2 else 0.0),
        0.0,
        1.0,
    )
    intensity = _clamp(strongest / 5.0, 0.0, 1.0)
    expectation_gap = 0.7 if any(event.category in ("policy", "central_bank") for event in events) else 0.5
    timeliness = 1.0 if len(events) >= 5 else 0.6 if len(events) >= 2 else 0.2 if events else 0.0
    composite = (0.35 * confidence) + (0.30 * intensity) + (0.20 * expectation_gap) + (0.15 * timeliness)
    composite = round(_clamp(composite, 0.0, 1.0), 4)
    quality_tier = "strong" if composite >= 0.75 else "notable" if composite >= 0.5 else "weak" if composite >= 0.25 else "noise"
    return SignalQuality(
        confidence=round(confidence, 4),
        intensity=round(intensity, 4),
        expectation_gap=round(expectation_gap, 4),
        timeliness=round(timeliness, 4),
        composite=composite,
        tier=quality_tier,
    )


def _find_text(item: ElementTree.Element, names: Iterable[str]) -> str:
    normalized_names = {name.lower() for name in names}
    for name in names:
        child = item.find(name)
        if child is not None and child.text:
            return child.text.strip()
    for child in item:
        local = child.tag.rsplit("}", 1)[-1].lower()
        if local in normalized_names and child.text:
            return child.text.strip()
        if local in normalized_names and child.attrib.get("href"):
            return child.attrib["href"].strip()
    return ""


def parse_feed_events(xml_text: str, source: MonitorSource, fetched_at: str) -> list[MonitorEvent]:
    root = ElementTree.fromstring(xml_text)
    items = root.findall(".//item")
    if not items:
        items = root.findall(".//{http://www.w3.org/2005/Atom}entry")
    events: list[MonitorEvent] = []
    for item in items[:20]:
        title = _find_text(item, ("title",))
        link = _find_text(item, ("link", "id"))
        published = _find_text(item, ("pubdate", "published", "updated"))
        summary = _find_text(item, ("description", "summary"))
        if not title:
            continue
        sentiment, terms = score_text(f"{title} {summary}")
        if sentiment == 0:
            continue
        event_key = f"{source.name}|{title}|{link}"
        event_id = hashlib.sha1(event_key.encode("utf-8")).hexdigest()[:16]
        events.append(
            MonitorEvent(
                event_id=event_id,
                source=source.name,
                category=source.category,
                title=re.sub(r"\s+", " ", title).strip(),
                link=link,
                published_at=published or fetched_at,
                fetched_at=fetched_at,
                sentiment=sentiment,
                impact=sentiment * (1.1 if source.category in ("policy", "central_bank") else 1.0),
                matched_terms=terms,
            )
        )
    return events


class WorldMonitorStore:
    def __init__(self, data_dir: Path | str) -> None:
        self.data_dir = Path(data_dir)
        self.db_path = self.data_dir / "world_monitor.db"

    def _ensure_dir(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        self._ensure_dir()
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                event_id TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                category TEXT NOT NULL,
                title TEXT NOT NULL,
                link TEXT,
                published_at TEXT,
                fetched_at TEXT NOT NULL,
                sentiment REAL NOT NULL,
                impact REAL NOT NULL,
                matched_terms TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                started_at TEXT NOT NULL,
                completed_at TEXT NOT NULL,
                score REAL NOT NULL,
                event_count INTEGER NOT NULL,
                payload TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_events_fetched_at ON events(fetched_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_completed_at ON runs(completed_at)")
        conn.commit()
        return conn

    def append_events(self, events: list[MonitorEvent]) -> None:
        if not events:
            return
        with self._connect() as conn:
            for event in events:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO events (
                        event_id, source, category, title, link, published_at,
                        fetched_at, sentiment, impact, matched_terms
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event.event_id,
                        event.source,
                        event.category,
                        event.title,
                        event.link,
                        event.published_at,
                        event.fetched_at,
                        event.sentiment,
                        event.impact,
                        json.dumps(event.matched_terms, ensure_ascii=False),
                    ),
                )
            conn.commit()

    def append_run(self, run: WorldMonitorRun) -> None:
        payload = _asdict(run)
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO runs (
                    run_id, started_at, completed_at, score, event_count, payload
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    run.run_id,
                    run.started_at,
                    run.completed_at,
                    run.score,
                    run.event_count,
                    json.dumps(payload, ensure_ascii=False),
                ),
            )
            conn.commit()

    def _event_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        try:
            data["matched_terms"] = json.loads(data["matched_terms"])
        except (json.JSONDecodeError, TypeError):
            data["matched_terms"] = []
        return data

    def events(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM events ORDER BY fetched_at DESC, impact DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._event_from_row(row) for row in rows]

    def runs(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT payload FROM runs ORDER BY completed_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def latest(self) -> Optional[dict[str, Any]]:
        rows = self.runs(limit=1)
        return rows[0] if rows else None


class WorldMonitorService:
    def __init__(
        self,
        settings: Optional["Settings"] = None,
        trade_service: Optional["TradeService"] = None,
        http_client: Optional[Any] = None,
    ) -> None:
        if settings is None:
            from .config import get_settings

            settings = get_settings()
        self.settings = settings or get_settings()
        self.trade_service = trade_service
        self.http_client = http_client
        self.store = WorldMonitorStore(self.settings.world_monitor_data_dir)

    @property
    def symbols(self) -> list[str]:
        return [s.strip().upper() for s in self.settings.world_monitor_symbols.split(",") if s.strip()]

    @property
    def sources(self) -> list[MonitorSource]:
        configured = parse_sources(self.settings.world_monitor_sources)
        symbol_sources = [build_google_news_source(symbol) for symbol in self.symbols]
        return configured + symbol_sources

    def _fetch_source(self, source: MonitorSource, fetched_at: str) -> tuple[list[MonitorEvent], Optional[str]]:
        try:
            request = Request(source.url, headers={"User-Agent": "futu-trading-platform/0.2"})
            with urlopen(request, timeout=12) as response:
                content_type = response.headers.get_content_charset() or "utf-8"
                xml_text = response.read().decode(content_type, errors="replace")
            return parse_feed_events(xml_text, source, fetched_at), None
        except Exception as exc:
            logger.warning("World Monitor source failed %s: %s", source.name, exc)
            return [], f"{source.name}: {exc}"

    def _fetch_source_with_client(
        self,
        client: Any,
        source: MonitorSource,
        fetched_at: str,
    ) -> tuple[list[MonitorEvent], Optional[str]]:
        try:
            response = client.get(source.url, timeout=12.0, follow_redirects=True)
            response.raise_for_status()
            return parse_feed_events(response.text, source, fetched_at), None
        except Exception as exc:
            logger.warning("World Monitor source failed %s: %s", source.name, exc)
            return [], f"{source.name}: {exc}"

    def _mock_events(self, fetched_at: str) -> list[MonitorEvent]:
        title = "Mock fallback: inflation risk eases as stimulus and growth support markets"
        sentiment, terms = score_text(title)
        return [
            MonitorEvent(
                event_id=hashlib.sha1(f"mock|{fetched_at}|{title}".encode("utf-8")).hexdigest()[:16],
                source="mock-fallback",
                category="finance",
                title=title,
                link="",
                published_at=fetched_at,
                fetched_at=fetched_at,
                sentiment=sentiment,
                impact=sentiment,
                matched_terms=terms,
            )
        ]

    def collect_events(self) -> tuple[list[MonitorEvent], list[str]]:
        fetched_at = _iso_now()
        events: list[MonitorEvent] = []
        errors: list[str] = []
        if self.http_client:
            for source in self.sources:
                rows, err = self._fetch_source_with_client(self.http_client, source, fetched_at)
                events.extend(rows)
                if err:
                    errors.append(err)
        else:
            for source in self.sources:
                rows, err = self._fetch_source(source, fetched_at)
                events.extend(rows)
                if err:
                    errors.append(err)

        deduped = {event.event_id: event for event in events}
        collected = list(deduped.values())
        if not collected:
            collected = self._mock_events(fetched_at)
            errors.append("all RSS sources unavailable or no scored headlines; used mock fallback event")
        return collected, errors

    def _signal_from_score(self, score: float) -> Signal:
        if score >= self.settings.world_monitor_buy_threshold:
            return "BUY"
        if score <= self.settings.world_monitor_sell_threshold:
            return "SELL"
        return "HOLD"

    def build_recommendations(
        self,
        score: float,
        quality: SignalQuality,
        top_events: list[MonitorEvent],
    ) -> list[WorldMonitorRecommendation]:
        signal = self._signal_from_score(score)
        reason_bits = [event.title for event in top_events[:3]]
        reason = "；".join(reason_bits) if reason_bits else "未偵測到足夠重大財經/政策異動"
        generated_at = _iso_now()
        return [
            WorldMonitorRecommendation(
                symbol=symbol,
                signal=signal,
                score=round(score, 3),
                confidence=quality.composite,
                reason=reason,
                generated_at=generated_at,
            )
            for symbol in self.symbols
        ]

    def _maybe_execute(
        self,
        rec: WorldMonitorRecommendation,
        auto_trade: Optional[bool] = None,
    ) -> WorldMonitorRecommendation:
        should_trade = self.settings.world_monitor_auto_trade if auto_trade is None else auto_trade
        if not should_trade or rec.signal == "HOLD":
            rec.order = {"mode": "record_only", "reason": "World Monitor 預設只記錄，不自動下單"}
            return rec

        from .trade_service import OrderRequest, TradeService

        env = _normalize_trd_env(self.settings.world_monitor_trd_env)
        trade_service = self.trade_service or TradeService()
        try:
            rec.order = trade_service.place_order(
                OrderRequest(
                    code=rec.symbol,
                    side=rec.signal,
                    quantity=self.settings.world_monitor_quantity,
                    order_type="MARKET",
                    trd_env=env,
                    confirmed=False,
                )
            )
        except Exception as exc:
            rec.order = {"status": "error", "message": str(exc), "trd_env": env}
        return rec

    def run_once(self, auto_trade: Optional[bool] = None) -> dict[str, Any]:
        started_at = _iso_now()
        events, errors = self.collect_events()
        self.store.append_events(events)
        top_events = sorted(events, key=lambda event: abs(event.impact), reverse=True)[:10]
        weighted_score = sum(event.impact for event in top_events)
        score = round(_clamp(weighted_score, -10.0, 10.0), 3)
        quality = compute_signal_quality(top_events)
        recommendations = [
            self._maybe_execute(rec, auto_trade=auto_trade)
            for rec in self.build_recommendations(score, quality, top_events)
        ]
        completed_at = _iso_now()
        run = WorldMonitorRun(
            run_id=hashlib.sha1(f"{started_at}|{completed_at}|{score}".encode("utf-8")).hexdigest()[:16],
            started_at=started_at,
            completed_at=completed_at,
            score=score,
            signal_quality=quality,
            event_count=len(events),
            top_events=top_events,
            recommendations=recommendations,
            errors=errors,
        )
        self.store.append_run(run)
        return _asdict(run)

    def overview(self) -> dict[str, Any]:
        return {
            "enabled": self.settings.world_monitor_enabled,
            "auto_trade": self.settings.world_monitor_auto_trade,
            "interval_seconds": self.settings.world_monitor_interval_seconds,
            "trd_env": _normalize_trd_env(self.settings.world_monitor_trd_env),
            "symbols": self.symbols,
            "sources": [_asdict(source) for source in self.sources],
            "db_path": str(self.store.db_path),
            "latest": self.store.latest(),
            "events": self.store.events(limit=50),
            "runs": self.store.runs(limit=20),
        }


class WorldMonitorRunner:
    def __init__(self, service: Optional[WorldMonitorService] = None) -> None:
        self.service = service or WorldMonitorService()
        from apscheduler.schedulers.background import BackgroundScheduler

        self.scheduler: "BackgroundScheduler" = BackgroundScheduler()
        self.job_id = "world-monitor-hourly"

    def start(self) -> None:
        settings = self.service.settings
        if not settings.world_monitor_enabled:
            return
        if not self.scheduler.running:
            self.scheduler.start()
        if not self.scheduler.get_job(self.job_id):
            self.scheduler.add_job(
                self._run_safely,
                "interval",
                seconds=max(60, settings.world_monitor_interval_seconds),
                id=self.job_id,
                replace_existing=True,
            )

    def stop(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    def _run_safely(self) -> None:
        try:
            result = self.service.run_once()
            logger.info("World Monitor run completed: %s", result.get("run_id"))
        except Exception as exc:
            logger.exception("World Monitor run failed: %s", exc)

    def status(self) -> dict[str, Any]:
        job = self.scheduler.get_job(self.job_id) if self.scheduler.running else None
        return {
            "running": self.scheduler.running,
            "job_id": self.job_id if job else None,
            "next_run": job.next_run_time.isoformat() if job and job.next_run_time else None,
        }
