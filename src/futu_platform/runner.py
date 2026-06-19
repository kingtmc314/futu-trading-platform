"""定時策略調度器。"""

from __future__ import annotations

import logging
from typing import Callable

from apscheduler.schedulers.background import BackgroundScheduler

from .strategy import create_engine

logger = logging.getLogger(__name__)


class StrategyRunner:
    def __init__(self) -> None:
        self.engine = create_engine()
        self.scheduler = BackgroundScheduler()
        self._jobs: dict[str, str] = {}

    def start(self) -> None:
        if not self.scheduler.running:
            self.scheduler.start()

    def stop(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    def schedule(
        self,
        job_id: str,
        strategy: str,
        code: str,
        interval_seconds: int = 60,
        *,
        quantity: int = 100,
        auto_trade: bool = False,
        confirmed: bool = False,
        trd_env: str = "SIMULATE",
    ) -> dict:
        def _run() -> None:
            try:
                result = self.engine.run_once(
                    strategy,
                    code,
                    quantity=quantity,
                    auto_trade=auto_trade,
                    confirmed=confirmed,
                    trd_env=trd_env,
                )
                logger.info("策略執行 %s: %s", job_id, result)
            except Exception as exc:
                logger.exception("策略執行失敗 %s: %s", job_id, exc)

        if job_id in self._jobs:
            self.scheduler.remove_job(job_id)

        self.scheduler.add_job(_run, "interval", seconds=interval_seconds, id=job_id, replace_existing=True)
        self._jobs[job_id] = strategy
        self.start()
        return {
            "job_id": job_id,
            "strategy": strategy,
            "code": code,
            "interval_seconds": interval_seconds,
            "trd_env": trd_env.upper(),
        }

    def unschedule(self, job_id: str) -> bool:
        if job_id not in self._jobs:
            return False
        self.scheduler.remove_job(job_id)
        del self._jobs[job_id]
        return True

    def status(self) -> list[dict]:
        jobs = []
        for job in self.scheduler.get_jobs():
            jobs.append(
                {
                    "id": job.id,
                    "strategy": self._jobs.get(job.id),
                    "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
                }
            )
        return jobs
