"""
Scheduler Service.
Configures and runs daily scheduled jobs for scrapers using APScheduler
with a fallback to native Python datetime looping.
"""

import time
import logging
import signal
import sys
from datetime import datetime, timedelta
from typing import Optional

from config import Config
from scheduler.jobs import run_all_daily_jobs, run_getfund_job, run_myscheme_job

logger = logging.getLogger("FloraScheme.Scheduler")

# Check APScheduler availability
try:
    from apscheduler.schedulers.blocking import BlockingScheduler
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    HAS_APSCHEDULER = True
except ImportError:
    HAS_APSCHEDULER = False


class DailyScraperScheduler:
    """
    Manages daily automated runs of GetFunding and myScheme scrapers.
    """

    def __init__(self):
        self.hour, self.minute = Config.get_daily_hour_minute()
        self.timezone = Config.SCHEDULER_TIMEZONE
        self.apscheduler_instance = None
        self._is_running = False

    def start(self, run_immediately_on_start: bool = False) -> None:
        """
        Starts the scheduler loop. Blocks until interrupted.
        """
        logger.info("=========================================================")
        logger.info(" FloraScheme Daily Scrapers Scheduler")
        logger.info(" Target Daily Run Time: %02d:%02d (%s)", self.hour, self.minute, self.timezone)
        logger.info(" Database Backend: MySQL (%s:%d/%s)", Config.MYSQL_HOST, Config.MYSQL_PORT, Config.MYSQL_DATABASE)
        logger.info("=========================================================")

        if run_immediately_on_start:
            logger.info("Running initial immediate scrape before waiting for schedule...")
            try:
                run_all_daily_jobs()
            except Exception as e:
                logger.error("Initial run encountered error: %s", e)

        if HAS_APSCHEDULER:
            self._start_apscheduler()
        else:
            self._start_native_scheduler()

    def _start_apscheduler(self) -> None:
        """Starts daily scheduler using APScheduler BlockingScheduler."""
        logger.info("Using APScheduler 3 engine with CronTrigger.")
        self.apscheduler_instance = BlockingScheduler(timezone=self.timezone)

        trigger = CronTrigger(
            hour=self.hour,
            minute=self.minute,
            timezone=self.timezone
        )

        self.apscheduler_instance.add_job(
            func=run_all_daily_jobs,
            trigger=trigger,
            id="daily_all_scrapers",
            name="Daily Scrapers Pipeline",
            misfire_grace_time=3600,
            replace_existing=True
        )

        job = self.apscheduler_instance.get_job("daily_all_scrapers")
        logger.info("Next scheduled run time: %s", job.next_run_time if job else "Calculating...")

        # Setup signal handler
        def _handle_exit(sig, frame):
            logger.info("Shutdown signal received. Stopping scheduler...")
            if self.apscheduler_instance and self.apscheduler_instance.running:
                self.apscheduler_instance.shutdown(wait=False)
            sys.exit(0)

        signal.signal(signal.SIGINT, _handle_exit)
        signal.signal(signal.SIGTERM, _handle_exit)

        try:
            self._is_running = True
            self.apscheduler_instance.start()
        except (KeyboardInterrupt, SystemExit):
            logger.info("Scheduler exited cleanly.")
        finally:
            self._is_running = False

    def _start_native_scheduler(self) -> None:
        """Fallback daily scheduler using native Python standard library."""
        logger.info("Using standard library native daily scheduler.")
        self._is_running = True

        def _calculate_sleep_seconds() -> float:
            now = datetime.now()
            target = now.replace(hour=self.hour, minute=self.minute, second=0, microsecond=0)
            if target <= now:
                target += timedelta(days=1)
            delta = (target - now).total_seconds()
            logger.info("Next run at: %s (in %d seconds / %.1f hours)", target.strftime("%Y-%m-%d %H:%M:%S"), int(delta), delta / 3600)
            return delta

        try:
            while self._is_running:
                sleep_sec = _calculate_sleep_seconds()
                # Sleep in short increments for responsive interrupt handling
                slept = 0.0
                while slept < sleep_sec and self._is_running:
                    chunk = min(5.0, sleep_sec - slept)
                    time.sleep(chunk)
                    slept += chunk

                if not self._is_running:
                    break

                logger.info("Scheduled time reached! Executing daily scrape batch...")
                try:
                    run_all_daily_jobs()
                except Exception as e:
                    logger.error("Daily scrape execution error: %s", e)

        except (KeyboardInterrupt, SystemExit):
            logger.info("Native scheduler stopped.")
        finally:
            self._is_running = False
