"""Scheduled jobs (free, runs on your own computer with APScheduler).

Default schedule (times in UTC):
* news          daily 06:00   startup news RSS feeds
* funding       daily 06:30   funding-focused RSS feeds and press-release wires
* sec           daily 07:00   SEC Form D filings from the previous business days
* community     every 6 hours Hacker News Show HN / Launch HN
* scores        Monday 08:00  investment score refresh

Each job holds a database lock, so the same job never runs twice at once, even if you
start the scheduler in two terminals. Each source inside a job is isolated: one failure is
logged and the rest continue.
"""
from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from .config import Settings
from .db import session_scope
from .models import JobRun, utcnow
from .pipeline import acquire_lock, release_lock, run_discovery
from .scoring import load_config, refresh_scores

log = logging.getLogger("vcdiscovery.scheduler")

JOBS = {
    "news": {"groups": ["news"], "trigger": CronTrigger(hour=6, minute=0)},
    "funding": {"groups": ["funding"], "trigger": CronTrigger(hour=6, minute=30)},
    "sec": {"groups": ["regulatory"], "trigger": CronTrigger(hour=7, minute=0)},
    "community": {"groups": ["community"], "trigger": CronTrigger(hour="*/6", minute=15)},
    "scores": {"groups": None, "trigger": CronTrigger(day_of_week="mon", hour=8, minute=0)},
}


def run_job(name: str, settings: Settings, trigger: str = "scheduled") -> dict:
    if name == "scores":
        return run_score_refresh(settings, trigger)
    job = JOBS[name]
    return run_discovery(settings, groups=job["groups"], trigger=trigger)


def run_score_refresh(settings: Settings, trigger: str = "scheduled") -> dict:
    with session_scope() as session:
        if not acquire_lock(session, "job:scores", settings.job_lock_minutes):
            return {"status": "skipped", "reason": "already running"}
        run = JobRun(job_name="score_refresh", trigger=trigger)
        session.add(run)
        session.commit()
        try:
            config = load_config(session, settings.load_json(settings.scoring_file))
            n = refresh_scores(session, config)
            run.status, run.items_new = "success", n
        except Exception as exc:
            session.rollback()
            run = session.merge(run)
            run.status, run.error_message = "failed", f"{type(exc).__name__}: {exc}"
            n = 0
        run.finished_at = utcnow()
        release_lock(session, "job:scores")
        return {"status": run.status, "scored": n}


def _safe(name: str, settings: Settings) -> None:
    try:
        log.info("Starting scheduled job %s", name)
        log.info("Finished %s: %s", name, run_job(name, settings))
    except Exception:  # never let one job crash the scheduler
        log.exception("Scheduled job %s failed", name)


def build_scheduler(settings: Settings, blocking: bool = False):
    scheduler = (BlockingScheduler if blocking else BackgroundScheduler)(timezone="UTC")
    for name, job in JOBS.items():
        scheduler.add_job(_safe, job["trigger"], args=[name, settings], id=name, max_instances=1, coalesce=True,
                          misfire_grace_time=3600, replace_existing=True)
    return scheduler


def describe() -> list[dict]:
    return [{"job": name, "schedule_utc": str(job["trigger"]), "groups": job["groups"]} for name, job in JOBS.items()]
