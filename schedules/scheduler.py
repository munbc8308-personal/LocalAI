import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from . import db
from .runner import execute

logger = logging.getLogger(__name__)

_scheduler = AsyncIOScheduler(timezone="Asia/Seoul")


def start() -> None:
    schedules = db.list_schedules()
    active = [s for s in schedules if s.active]
    for s in active:
        _add_job(s)
    _scheduler.start()
    logger.info(f"[schedules] 스케줄러 시작 — {len(active)}개 활성")


def stop() -> None:
    if _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("[schedules] 스케줄러 종료")


def sync_job(schedule_id: int) -> None:
    """스케줄 생성·수정·삭제 후 APScheduler와 동기화."""
    s = db.get_schedule(schedule_id)
    if not s or not s.active:
        _remove_job(schedule_id)
    else:
        _add_job(s)


def _add_job(s: db.Schedule) -> None:
    _scheduler.add_job(
        execute,
        trigger=CronTrigger(hour=s.hour, minute=s.minute, timezone="Asia/Seoul"),
        id=str(s.id),
        kwargs={"schedule_id": s.id},
        replace_existing=True,
        misfire_grace_time=300,
    )
    logger.info(f"[schedules] 등록 id={s.id} '{s.name}' 매일 {s.hour:02d}:{s.minute:02d}")


def _remove_job(schedule_id: int) -> None:
    if _scheduler.get_job(str(schedule_id)):
        _scheduler.remove_job(str(schedule_id))
        logger.info(f"[schedules] 제거 id={schedule_id}")
