"""
Scheduler Jobs Module.
Implements execution pipelines for:
- getfundscrapper (GetFunding Government Schemes)
- myschemescrapper (myScheme.gov.in Official Welfare Schemes)
- Generic/Future Scrapers (pluggable scraper registry)
All scrapers automatically persist data into MySQL using the Dynamic Model.
"""

import sys
import os
import time
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable

from config import Config
from db.repository import scheme_repo

logger = logging.getLogger("FloraScheme.Jobs")

# Add scraper subdirectories to sys.path so their internal modules can be imported
ROOT_DIR = Path(__file__).resolve().parent.parent
GETFUND_DIR = ROOT_DIR / "getfundscrapper"
MYSCHEME_DIR = ROOT_DIR / "myschemescrapper"

if str(GETFUND_DIR) not in sys.path:
    sys.path.insert(0, str(GETFUND_DIR))
if str(MYSCHEME_DIR) not in sys.path:
    sys.path.insert(0, str(MYSCHEME_DIR))


def get_getfund_module():
    """Dynamically loads getfundscrapper/scraper.py without sys.modules collisions."""
    import importlib.util
    file_path = GETFUND_DIR / "scraper.py"
    spec = importlib.util.spec_from_file_location("getfund_scraper_module", file_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["getfund_scraper_module"] = module
    spec.loader.exec_module(module)
    return module


def get_myscheme_scraper_class():
    """Dynamically loads myschemescrapper/scraper.py without sys.modules collisions."""
    import importlib.util
    file_path = MYSCHEME_DIR / "scraper.py"
    spec = importlib.util.spec_from_file_location("myscheme_scraper_module", file_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["myscheme_scraper_module"] = module
    spec.loader.exec_module(module)
    return module.MySchemeScraper


def save_backup_file(source: str, data: List[Dict[str, Any]]) -> None:
    """Saves a dated snapshot of scraped data to local backup directory."""
    if not Config.BACKUP_LOCAL_FILES:
        return

    try:
        backup_dir = Config.BACKUP_DIR / source
        backup_dir.mkdir(parents=True, exist_ok=True)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filepath = backup_dir / f"{source}_{timestamp}.json"

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        logger.info("Saved local backup snapshot: %s", filepath)
    except Exception as e:
        logger.warning("Failed to save local backup for %s: %s", source, e)


def run_getfund_job(workers: Optional[int] = None) -> Dict[str, Any]:
    """
    Executes the GetFunding scraper pipeline:
    1. Audits run start in MySQL `scrapers` table.
    2. Fetches all schemes from GetFunding API.
    3. Persists records to MySQL using Dynamic Model (handles investment_size, stage, etc.).
    4. Records execution status, duration, and metrics in `scrapers` table.
    """
    source = "getfunding"
    workers = workers or Config.GETFUND_WORKERS
    start_time = time.time()
    logger.info(">>> Starting scheduled job: %s (workers=%d) <<<", source, workers)

    run_id = None
    try:
        run_id = scheme_repo.start_scrape_run(source)
    except Exception as e:
        logger.warning("Could not record start of scrape run in database: %s", e)

    status = "SUCCESS"
    err_msg = None
    batch_result = {"total": 0, "inserted": 0, "updated": 0, "unchanged": 0, "failed": 0}
    scraped_records = []

    try:
        # Import scraper dynamically with isolated namespace
        getfund_module = get_getfund_module()
        scraped_records = getfund_module.scrape_all_schemes(max_workers=workers)
        logger.info("GetFunding scraper fetched %d records.", len(scraped_records))

        # Save backup snapshot
        save_backup_file(source, scraped_records)

        # Batch upsert into MySQL with abandoned schemes reconciliation
        batch_result = scheme_repo.save_schemes_batch(source, scraped_records, soft_delete_missing=True)
        if batch_result["failed"] > 0 and batch_result["inserted"] == 0 and batch_result["updated"] == 0:
            status = "FAILED"
            err_msg = f"{batch_result['failed']} records failed database persistence"

    except Exception as e:
        status = "FAILED"
        err_msg = str(e)
        logger.error("Job '%s' encountered an error: %s", source, e, exc_info=True)

    duration = time.time() - start_time
    if run_id:
        try:
            scheme_repo.finish_scrape_run(
                run_id=run_id,
                source=source,
                status=status,
                total=len(scraped_records),
                inserted=batch_result["inserted"],
                updated=batch_result["updated"],
                unchanged=batch_result["unchanged"],
                failed=batch_result["failed"],
                duration=duration,
                error_msg=err_msg,
                soft_deleted=batch_result.get("soft_deleted", 0)
            )
        except Exception as e:
            logger.warning("Could not update finish status of scrape run in database: %s", e)

    logger.info(
        ">>> Job '%s' finished: status=%s, total=%d, new=%d, updated=%d, unchanged=%d, soft_deleted=%d, time=%.2fs <<<",
        source, status, len(scraped_records), batch_result["inserted"], batch_result["updated"], batch_result["unchanged"], batch_result.get("soft_deleted", 0), duration
    )

    return {
        "source": source,
        "status": status,
        "total_scraped": len(scraped_records),
        "inserted": batch_result["inserted"],
        "updated": batch_result["updated"],
        "unchanged": batch_result["unchanged"],
        "soft_deleted": batch_result.get("soft_deleted", 0),
        "failed": batch_result["failed"],
        "duration_seconds": duration,
        "error": err_msg
    }


def run_myscheme_job(workers: Optional[int] = None, limit: Optional[int] = None) -> Dict[str, Any]:
    """
    Executes the myScheme scraper pipeline:
    1. Audits run start in MySQL `scrapers` table.
    2. Fetches schemes from myScheme.gov.in API.
    3. Persists records to MySQL using Dynamic Model (handles nodal ministry, faqs, documents, etc.).
    4. Records execution status, duration, and metrics in `scrapers` table.
    """
    source = "myscheme"
    workers = workers or Config.MYSCHEME_WORKERS
    limit = limit if limit is not None else (None if Config.MYSCHEME_LIMIT <= 0 else Config.MYSCHEME_LIMIT)
    start_time = time.time()
    logger.info(">>> Starting scheduled job: %s (workers=%d, limit=%s) <<<", source, workers, limit or "ALL")

    run_id = None
    try:
        run_id = scheme_repo.start_scrape_run(source)
    except Exception as e:
        logger.warning("Could not record start of scrape run in database: %s", e)

    status = "SUCCESS"
    err_msg = None
    batch_result = {"total": 0, "inserted": 0, "updated": 0, "unchanged": 0, "failed": 0}
    scraped_records = []

    try:
        # Import myScheme scraper with isolated namespace
        MySchemeScraper = get_myscheme_scraper_class()
        scraper = MySchemeScraper(delay=0.1)

        # Scrape all unique schemes platform-wide
        output_dir = str(Config.BACKUP_DIR / "myscheme_cache")
        scraped_records = scraper.scrape_all_schemes(
            limit=limit,
            max_workers=workers,
            output_dir=output_dir,
            formats=["json"],
            resume=True
        )
        logger.info("myScheme scraper fetched %d records.", len(scraped_records))

        # Save backup snapshot
        save_backup_file(source, scraped_records)

        # Batch upsert into MySQL with abandoned schemes reconciliation on full scrapes
        is_full_scrape = (limit is None or limit <= 0)
        batch_result = scheme_repo.save_schemes_batch(source, scraped_records, soft_delete_missing=is_full_scrape)
        if batch_result["failed"] > 0 and batch_result["inserted"] == 0 and batch_result["updated"] == 0:
            status = "FAILED"
            err_msg = f"{batch_result['failed']} records failed database persistence"

    except Exception as e:
        status = "FAILED"
        err_msg = str(e)
        logger.error("Job '%s' encountered an error: %s", source, e, exc_info=True)

    duration = time.time() - start_time
    if run_id:
        try:
            scheme_repo.finish_scrape_run(
                run_id=run_id,
                source=source,
                status=status,
                total=len(scraped_records),
                inserted=batch_result["inserted"],
                updated=batch_result["updated"],
                unchanged=batch_result["unchanged"],
                failed=batch_result["failed"],
                duration=duration,
                error_msg=err_msg,
                soft_deleted=batch_result.get("soft_deleted", 0)
            )
        except Exception as e:
            logger.warning("Could not update finish status of scrape run in database: %s", e)

    logger.info(
        ">>> Job '%s' finished: status=%s, total=%d, new=%d, updated=%d, unchanged=%d, soft_deleted=%d, time=%.2fs <<<",
        source, status, len(scraped_records), batch_result["inserted"], batch_result["updated"], batch_result["unchanged"], batch_result.get("soft_deleted", 0), duration
    )

    return {
        "source": source,
        "status": status,
        "total_scraped": len(scraped_records),
        "inserted": batch_result["inserted"],
        "updated": batch_result["updated"],
        "unchanged": batch_result["unchanged"],
        "soft_deleted": batch_result.get("soft_deleted", 0),
        "failed": batch_result["failed"],
        "duration_seconds": duration,
        "error": err_msg
    }


def run_all_daily_jobs() -> Dict[str, Any]:
    """
    Sequential daily execution orchestrator.
    Runs getfunding first, followed by myscheme.
    """
    logger.info("================================================================")
    logger.info("Starting Daily Scrapers Batch Execution (%s)", time.strftime("%Y-%m-%d %H:%M:%S"))
    logger.info("================================================================")

    results = {}
    if Config.GETFUND_ENABLED:
        results["getfunding"] = run_getfund_job()
    else:
        logger.info("GetFunding scraper is disabled in configuration.")

    if Config.MYSCHEME_ENABLED:
        results["myscheme"] = run_myscheme_job()
    else:
        logger.info("myScheme scraper is disabled in configuration.")

    logger.info("================================================================")
    logger.info("Daily Scrapers Batch Execution Finished")
    logger.info("================================================================")
    return results


# ------------------------------------------------------------------------------
# Future Scraper Pluggable Registry
# ------------------------------------------------------------------------------
CUSTOM_SCRAPERS: Dict[str, Callable[[], List[Dict[str, Any]]]] = {}


def register_scraper(source_name: str, scraper_func: Callable[[], List[Dict[str, Any]]]) -> None:
    """
    Registers a custom/future scraper into the automated pipeline.
    scraper_func must return a List[Dict[str, Any]].
    The Dynamic Model will automatically adapt MySQL to any fields returned!
    """
    CUSTOM_SCRAPERS[source_name.lower()] = scraper_func
    logger.info("Registered custom scraper: %s", source_name)


def run_custom_job(source_name: str) -> Dict[str, Any]:
    """Executes a registered custom/future scraper."""
    src = source_name.lower()
    if src not in CUSTOM_SCRAPERS:
        raise ValueError(f"No custom scraper registered under '{src}'")

    start_time = time.time()
    run_id = None
    try:
        run_id = scheme_repo.start_scrape_run(src)
    except Exception as e:
        logger.warning("Could not record start of scrape run in database: %s", e)

    status = "SUCCESS"
    err_msg = None
    batch_result = {"total": 0, "inserted": 0, "updated": 0, "unchanged": 0, "failed": 0}
    scraped_records = []

    try:
        func = CUSTOM_SCRAPERS[src]
        scraped_records = func()
        save_backup_file(src, scraped_records)
        batch_result = scheme_repo.save_schemes_batch(src, scraped_records, soft_delete_missing=True)
    except Exception as e:
        status = "FAILED"
        err_msg = str(e)
        logger.error("Custom scraper '%s' failed: %s", src, e)

    duration = time.time() - start_time
    if run_id:
        try:
            scheme_repo.finish_scrape_run(
                run_id=run_id,
                source=src,
                status=status,
                total=len(scraped_records),
                inserted=batch_result["inserted"],
                updated=batch_result["updated"],
                unchanged=batch_result["unchanged"],
                failed=batch_result["failed"],
                duration=duration,
                error_msg=err_msg,
                soft_deleted=batch_result.get("soft_deleted", 0)
            )
        except Exception as e:
            logger.warning("Could not update finish status of scrape run in database: %s", e)
    return {
        "source": src,
        "status": status,
        "total_scraped": len(scraped_records),
        "inserted": batch_result["inserted"],
        "updated": batch_result["updated"],
        "unchanged": batch_result["unchanged"],
        "soft_deleted": batch_result.get("soft_deleted", 0),
        "failed": batch_result["failed"],
        "duration_seconds": duration,
        "error": err_msg
    }
