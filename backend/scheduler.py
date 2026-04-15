"""
Content calendar scheduler.

Runs as a background thread, checking schedule rules every 30s and
queuing Flux generations when due.
"""

import logging
import threading
import time
from datetime import datetime, timezone, timedelta

from croniter import croniter

logger = logging.getLogger(__name__)

_scheduler_thread = None
_stop_event = threading.Event()


def _next_run(cron_expr: str, base: datetime | None = None) -> datetime:
    """Calculate the next run time from a cron expression."""
    base = base or datetime.now(timezone.utc)
    # croniter needs naive datetimes
    naive = base.replace(tzinfo=None)
    cron = croniter(cron_expr, naive)
    return cron.get_next(datetime).replace(tzinfo=timezone.utc)


def _scheduler_loop():
    """Main scheduler loop — runs in background thread."""
    from database import SessionLocal, Schedule, Persona, Content
    import comfy_api

    logger.info("Scheduler started")

    while not _stop_event.is_set():
        try:
            db = SessionLocal()
            now = datetime.now(timezone.utc)

            schedules = db.query(Schedule).filter(Schedule.enabled == True).all()

            for sched in schedules:
                # Initialize next_run if not set
                if sched.next_run is None:
                    sched.next_run = _next_run(sched.cron_expression)
                    db.commit()
                    continue

                # Make comparison tz-aware
                next_dt = sched.next_run
                if next_dt.tzinfo is None:
                    next_dt = next_dt.replace(tzinfo=timezone.utc)

                if now >= next_dt:
                    persona = db.query(Persona).filter(Persona.id == sched.persona_id).first()
                    if not persona:
                        continue

                    full_prompt = f"{persona.prompt_base}, {sched.prompt_template}"
                    logger.info(
                        "Scheduler: generating %d image(s) for %s",
                        sched.batch_size, persona.name,
                    )

                    for _ in range(sched.batch_size):
                        comfy_resp = comfy_api.queue_prompt(full_prompt, persona.lora_name)
                        status = "failed" if "error" in comfy_resp else "generating"
                        content = Content(
                            persona_id=persona.id,
                            prompt_used=full_prompt,
                            comfy_job_id=comfy_resp.get("prompt_id"),
                            status=status,
                        )
                        db.add(content)

                    sched.last_run = now
                    sched.next_run = _next_run(sched.cron_expression, now)
                    db.commit()

            db.close()
        except Exception as e:
            logger.error("Scheduler error: %s", e)

        _stop_event.wait(30)  # Check every 30 seconds

    logger.info("Scheduler stopped")


def start_scheduler():
    """Start the background scheduler thread."""
    global _scheduler_thread
    if _scheduler_thread is not None and _scheduler_thread.is_alive():
        return

    _stop_event.clear()
    _scheduler_thread = threading.Thread(target=_scheduler_loop, daemon=True, name="empire-scheduler")
    _scheduler_thread.start()


def stop_scheduler():
    """Signal the scheduler to stop."""
    _stop_event.set()
    if _scheduler_thread is not None:
        _scheduler_thread.join(timeout=5)
