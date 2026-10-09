"""
FloraScheme CLI & Daily Scheduler Entrypoint.
Orchestrates daily scraping runs for GetFunding & myScheme with dynamic MySQL persistence.

Usage Examples:
  # 1. Start the daily scheduler daemon (runs at DAILY_RUN_TIME every day):
  python run_scheduler.py --daemon

  # 2. Run both scrapers immediately (one-time execution):
  python run_scheduler.py --now

  # 3. Run individual scraper:
  python run_scheduler.py --run getfund
  python run_scheduler.py --run myscheme --limit 10

  # 4. Test MySQL connectivity and auto-create database/tables:
  python run_scheduler.py --test-db

  # 5. Show database statistics and audit history:
  python run_scheduler.py --stats

  # 6. Generate Windows Task Scheduler batch script:
  python run_scheduler.py --windows-task
"""

import os
import sys
import argparse
import logging
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] (%(name)s) %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("FloraScheme.CLI")

from config import Config
from db.connection import db_manager
from db.repository import scheme_repo
from scheduler.service import DailyScraperScheduler
from scheduler.jobs import run_all_daily_jobs, run_getfund_job, run_myscheme_job


def print_banner():
    banner = r"""
  =============================================================
   ___ _                   ____       _                          
  | __| |___ _ _ __ _     / ___|  ___| |__   ___ _ __ ___   ___  
  | _|| / _ \ '_/ _` |    \___ \ / __| '_ \ / _ \ '_ ` _ \ / _ \ 
  |_| |_\___/_| \__,_|    |___) | (__| | | |  __/ | | | | |  __/ 
                          |____/ \___|_| |_|\___|_| |_| |_|\___| 
  =============================================================
     FloraScheme Automated Scrapers & Dynamic MySQL System
  =============================================================
"""
    print(banner)


def cmd_test_db():
    """Validates MySQL connectivity, creates database/tables if needed."""
    print("\n--- Testing MySQL Connection ---")
    cfg = Config.get_mysql_config()
    print(f"Target Host:     {cfg['host']}:{cfg['port']}")
    print(f"User:            {cfg['user']}")
    print(f"Database:        {cfg['database']}")
    print(f"Strict Backend:  MySQL 5.7+ / 8.0+")

    res = db_manager.test_connection()
    if res["success"]:
        print(f"\n[OK] Connected to MySQL Server version: {res['server_version']}")
        if res["database_exists"]:
            print(f"[OK] Database '{cfg['database']}' exists.")
            print(f"[OK] Existing tables: {', '.join(res['tables']) if res['tables'] else 'None'}")
        else:
            print(f"[!] Database '{cfg['database']}' does not exist yet. Initializing now...")
            db_manager.init_database()
            print("[OK] Database and schema initialized successfully!")
    else:
        print(f"\n[FAIL] Could not connect to MySQL: {res['error']}")
        print("\nPlease check your credentials in '.env':")
        print("  MYSQL_HOST=localhost")
        print("  MYSQL_PORT=3306")
        print("  MYSQL_USER=root")
        print("  MYSQL_PASSWORD=<your_mysql_password>")
        print(f"  MYSQL_DATABASE={Config.MYSQL_DATABASE}\n")
        return False
    return True


def cmd_stats():
    """Prints stats on stored schemes and recent scraper runs."""
    try:
        stats = scheme_repo.get_stats()
        print("\n" + "=" * 65)
        print(" FLORASCHEME MYSQL DATABASE STATISTICS")
        print("=" * 65)
        print(f" Total Schemes Stored: {stats['total_schemes']}")
        print("\n Breakdown by Scraper Source:")
        for s in stats["by_source"]:
            print(f"  - {s['source']:<15}: {s['count']:>6} schemes (Last scraped: {s['last_scraped'] or 'N/A'})")

        if stats["top_categories"]:
            print("\n Top Categories:")
            for c in stats["top_categories"]:
                print(f"  - {c['category'][:45]:<45}: {c['count']:>5} schemes")

        if stats["recent_runs"]:
            print("\n Scrapers Status & Metrics:")
            for r in stats["recent_runs"]:
                print(f"  - [{r.get('started_at') or 'N/A'}] Source: {r.get('source', ''):<12} Status: {r.get('status', ''):<8} "
                      f"Total: {r.get('total_schemes_count', 0):<5} New: {r.get('inserted_count', 0):<4} Updated: {r.get('updated_count', 0):<4} "
                      f"Soft-Del: {r.get('soft_deleted_count', 0):<3} Time: {r.get('duration_seconds', 0)}s")
        print("=" * 65 + "\n")
    except Exception as e:
        print(f"[Error] Failed to fetch statistics: {e}")


def cmd_generate_windows_task():
    """Generates Windows Task Scheduler setup script for daily background execution."""
    python_exe = sys.executable
    script_path = str(Path(__file__).resolve())
    work_dir = str(Path(__file__).resolve().parent)
    hour, minute = Config.get_daily_hour_minute()
    time_str = f"{hour:02d}:{minute:02d}"

    bat_content = f"""@echo off
REM =============================================================
REM FloraScheme Daily Scraper Task Runner for Windows
REM =============================================================
cd /d "{work_dir}"
"{python_exe}" "{script_path}" --now >> "{work_dir}\\data\\daily_task.log" 2>&1
"""

    bat_path = Path(work_dir) / "run_daily_scrape.bat"
    with open(bat_path, "w", encoding="utf-8") as f:
        f.write(bat_content)

    print(f"\nCreated Windows Runner Batch File: {bat_path}")
    print("\nTo schedule this task to run daily at " + time_str + " in Windows Task Scheduler, run this command in Administrator PowerShell or Command Prompt:")
    print("-" * 75)
    print(f'schtasks /create /tn "FloraScheme_Daily_Scraper" /tr "\"{bat_path}\"" /sc daily /st {time_str} /f')
    print("-" * 75)
    print("Or keep the Python daemon running with: python run_scheduler.py --daemon\n")


def parse_args():
    parser = argparse.ArgumentParser(
        description="FloraScheme Automated Daily Scrapers & Dynamic MySQL Persistence",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument("--daemon", "--start", action="store_true", help="Start the continuous daily scheduler daemon")
    parser.add_argument("--now", "--run-all", action="store_true", help="Run both scrapers immediately once and persist to MySQL")
    parser.add_argument("--run", type=str, choices=["getfund", "myscheme"], help="Run a specific scraper immediately ('getfund' or 'myscheme')")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of schemes to scrape (useful for quick testing)")
    parser.add_argument("--workers", type=int, default=None, help="Number of concurrent worker threads")
    parser.add_argument("--test-db", action="store_true", help="Test MySQL connection and initialize database schema")
    parser.add_argument("--init-db", action="store_true", help="Initialize/verify database and tables")
    parser.add_argument("--stats", action="store_true", help="Display MySQL database metrics and scrape audit history")
    parser.add_argument("--sql", action="store_true", help="Print MySQL DDL creation script dynamically rendered with database name from .env")
    parser.add_argument("--windows-task", action="store_true", help="Generate Windows Task Scheduler script")

    return parser.parse_args()


def main():
    args = parse_args()
    print_banner()

    # If no flags passed, display help
    if not any(vars(args).values()):
        print("No action specified. Choose an option:")
        print("  python run_scheduler.py --daemon        # Start continuous daily scheduler")
        print("  python run_scheduler.py --now           # Scrape both sources immediately")
        print("  python run_scheduler.py --run getfund   # Scrape GetFunding source only")
        print("  python run_scheduler.py --run myscheme  # Scrape myScheme source only")
        print("  python run_scheduler.py --test-db       # Test MySQL connection")
        print("  python run_scheduler.py --stats         # View stored schemes statistics")
        print("  python run_scheduler.py --windows-task  # Setup Windows Task Scheduler")
        return

    if args.test_db or args.init_db:
        cmd_test_db()
        return

    if args.stats:
        cmd_stats()
        return

    if args.sql:
        print(db_manager.get_rendered_schema_sql())
        return

    if args.windows_task:
        cmd_generate_windows_task()
        return

    # Check database before running scrapers
    db_check = db_manager.test_connection()
    if not db_check["success"]:
        print(f"\n[Warning] MySQL is not currently accessible: {db_check['error']}")
        print("Please check your .env MySQL credentials (host, user, password, port).")
        proceed = input("Do you want to continue anyway? (y/N): ").strip().lower()
        if proceed != "y":
            return
    elif not db_check["database_exists"]:
        print(f"Auto-initializing database '{Config.MYSQL_DATABASE}'...")
        db_manager.init_database()

    if args.run == "getfund":
        print("\nStarting GetFunding Scraper run...")
        res = run_getfund_job(workers=args.workers)
        print("\nGetFunding Scraper completed:")
        print(f" Status: {res['status']}, Scraped: {res['total_scraped']}, New: {res['inserted']}, Updated: {res['updated']}, Time: {res['duration_seconds']}s")
        return

    if args.run == "myscheme":
        print(f"\nStarting myScheme Scraper run (Limit: {args.limit or 'ALL'})...")
        res = run_myscheme_job(workers=args.workers, limit=args.limit)
        print("\nmyScheme Scraper completed:")
        print(f" Status: {res['status']}, Scraped: {res['total_scraped']}, New: {res['inserted']}, Updated: {res['updated']}, Time: {res['duration_seconds']}s")
        return

    if args.now:
        print("\nStarting immediate scrape of BOTH scrapers...")
        results = run_all_daily_jobs()
        print("\nAll Scrapers completed. Summary:")
        for src, r in results.items():
            print(f" - {src:<12}: Status={r['status']}, Scraped={r['total_scraped']}, New={r['inserted']}, Updated={r['updated']}")
        return

    if args.daemon:
        scheduler = DailyScraperScheduler()
        scheduler.start()


if __name__ == "__main__":
    main()
