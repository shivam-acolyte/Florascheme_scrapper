"""
FloraScheme Scheduler Module.
Automates daily scraping runs for GetFunding, myScheme, and future portals.
"""

from scheduler.jobs import (
    run_all_daily_jobs,
    run_getfund_job,
    run_myscheme_job,
    register_scraper,
    run_custom_job,
)
from scheduler.service import DailyScraperScheduler

__all__ = [
    "run_all_daily_jobs",
    "run_getfund_job",
    "run_myscheme_job",
    "register_scraper",
    "run_custom_job",
    "DailyScraperScheduler",
]
