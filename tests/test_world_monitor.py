from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from futu_platform.world_monitor import (
    MonitorSource,
    WorldMonitorService,
    compute_signal_quality,
    parse_feed_events,
    score_text,
)


class WorldMonitorScoringTest(unittest.TestCase):
    def test_score_text_detects_policy_and_market_terms(self) -> None:
        score, terms = score_text("Fed signals rate cut while tariff risk fades")

        self.assertGreater(score, 0)
        self.assertIn("rate cut", terms)
        self.assertIn("tariff", terms)

    def test_parse_feed_events_returns_impacted_events(self) -> None:
        xml = """<?xml version="1.0"?>
        <rss><channel>
          <item>
            <title>Central bank announces rate cut and stimulus plan</title>
            <link>https://example.test/policy</link>
            <pubDate>Fri, 19 Jun 2026 01:00:00 GMT</pubDate>
          </item>
          <item>
            <title>Weekend calendar is quiet</title>
            <link>https://example.test/quiet</link>
          </item>
        </channel></rss>
        """
        source = MonitorSource(name="policy", category="policy", url="https://example.test/rss")

        events = parse_feed_events(xml, source, "2026-06-19T00:00:00+00:00")

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].category, "policy")
        self.assertGreater(events[0].impact, 0)

    def test_signal_quality_is_bounded(self) -> None:
        source = MonitorSource(name="finance", category="finance", url="https://example.test/rss")
        events = parse_feed_events(
            "<rss><channel><item><title>Markets rally on stimulus deal</title></item></channel></rss>",
            source,
            "2026-06-19T00:00:00+00:00",
        )

        quality = compute_signal_quality(events)

        self.assertGreaterEqual(quality.composite, 0)
        self.assertLessEqual(quality.composite, 1)
        self.assertIn(quality.tier, {"strong", "notable", "weak", "noise"})


class WorldMonitorServiceTest(unittest.TestCase):
    def test_default_run_records_without_ordering(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = SimpleNamespace(
                world_monitor_data_dir=str(Path(tmp)),
                world_monitor_symbols="US.SPY",
                world_monitor_sources="",
                world_monitor_buy_threshold=1.0,
                world_monitor_sell_threshold=-1.0,
                world_monitor_auto_trade=False,
                world_monitor_trd_env="SIMULATE",
                world_monitor_quantity=1,
                world_monitor_enabled=True,
                world_monitor_interval_seconds=3600,
            )
            service = WorldMonitorService(settings=settings, trade_service=object())
            source = MonitorSource(name="policy", category="policy", url="https://example.test/rss")
            service.collect_events = lambda: (
                parse_feed_events(
                    "<rss><channel><item><title>Fed rate cut stimulus supports market</title></item></channel></rss>",
                    source,
                    "2026-06-19T00:00:00+00:00",
                ),
                [],
            )

            result = service.run_once()

            self.assertEqual(result["recommendations"][0]["signal"], "BUY")
            self.assertEqual(result["recommendations"][0]["order"]["mode"], "record_only")
            self.assertTrue((Path(tmp) / "world_monitor.db").is_file())


if __name__ == "__main__":
    unittest.main()
