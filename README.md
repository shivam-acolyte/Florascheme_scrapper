# FloraScheme: Automated Daily Scraper Scheduler & Dynamic MySQL Engine

FloraScheme is an automated scraping, scheduling, and database persistence system designed for government welfare and funding schemes across India. It orchestrates daily runs for **GetFunding** (`getfundscrapper`) and **myScheme** (`myschemescrapper`), with support for arbitrary **future scrapers** through a dynamic, self-evolving MySQL database model.

---

## Key Features

1. **Daily Automated Scheduler**:
   - Configurable daily run time (e.g. `DAILY_RUN_TIME=02:00` in `.env`).
   - Runs as a Python background daemon (`APScheduler` or built-in fallback) or via **Windows Task Scheduler** batch script (`run_daily_scrape.bat`).
   - Supports immediate one-off execution via CLI (`--now`, `--run getfund`, `--run myscheme`).

2. **Unified Dynamic Database Model (Strictly MySQL 5.7+ / 8.0+)**:
   - **Streamlined 2-Table Schema**:
     - `grant_scheme`: Single unified table storing all canonical scheme attributes, lossless `raw_data` JSON, dynamic `extra_fields` JSON, auto-evolved dynamic columns, and a `deleted_at` timestamp for soft deletions.
     - `scheme_scrapper`: Master scraper registry tracking schedules, status (`PENDING`, `RUNNING`, `SUCCESS`, `FAILED`), and last run metrics.
   - **Canonical Field Normalization & Aliasing**: Smartly maps varied scraper field naming (e.g., `portal_code`, `unique_id`, `sid`, `title`, `full_name`, `web_link`) into standard canonical columns.
   - **Automatic Schema Evolution**: Detects brand-new, unannounced fields from future scrapers and dynamically issues safe `ALTER TABLE ADD COLUMN` statements with automatic SQL type inference (`TINYINT`, `BIGINT`, `DOUBLE`, `JSON`, `MEDIUMTEXT`, `VARCHAR`).
   - **Automatic Abandoned Scheme Soft Deletion**: Whenever a daily scraper runs, schemes previously active in MySQL that are no longer returned by the portal (abandoned, discontinued, or delisted) are automatically soft-deleted (`deleted_at = NOW()`). If an abandoned scheme reappears in a future run, it is automatically restored (`deleted_at = NULL`).
   - **Soft Deletion APIs**: Built-in support for `deleted_at` timestamping, with `soft_delete_scheme`, `restore_scheme`, and `soft_delete_missing_schemes` repository methods.
   - **Lossless Storage**: Full raw response payload is preserved in `raw_data` (`JSON`), ensuring zero data loss.
   - **SHA-256 Change Detection**: Generates cryptographic hashes over normalized payloads. Unchanged records are detected immediately to prevent redundant database writes.

3. **Pluggable Scraper Architecture**:
   - Easily register future scrapers with `register_scraper("portal_name", scraper_callable)`.
   - Automated run auditing with start/finish timestamps, durations, and metrics (`inserted`, `updated`, `unchanged`, `failed`) tracked directly in `scrapers`.
   - Dual storage: Persists to MySQL and generates timestamped local JSON backups (`data/backups/`).

---

## Project Architecture

```
d:/florascheme/
├── .env                     # Environment settings (MySQL credentials, schedule time)
├── .env.example             # Template for configuration
├── config.py                # Configuration loader & MySQL enforcement
├── run_scheduler.py         # Main CLI and scheduler entrypoint
├── run_daily_scrape.bat     # Windows Task Scheduler batch runner
├── test_system.py           # Unit test suite (Dynamic model, aliases, scheduler, mocks)
│
├── db/
│   ├── connection.py        # MySQL connection manager & health checks
│   ├── dynamic_model.py     # Dynamic schema engine, type inference & aliasing
│   ├── repository.py        # SchemeRepository (CRUD, batch upsert, soft deletes, stats)
│   └── schema.sql           # MySQL DDL for schemes and scrapers tables
│
├── scheduler/
│   ├── service.py           # DailyScraperScheduler daemon service
│   ├── jobs.py              # Execution pipelines for getfund, myscheme, and custom scrapers
│   └── __init__.py
│
├── getfundscrapper/         # GetFunding Government schemes scraper
└── myschemescrapper/        # myScheme.gov.in official schemes scraper
```

---

## Configuration (`.env`)

Configure your MySQL connection and scheduling preferences in `.env`:

```ini
# Strictly MySQL Only
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=root
MYSQL_PASSWORD=your_password_here
MYSQL_DATABASE=florascheme_db
MYSQL_CHARSET=utf8mb4

# Dynamic Schema Evolution (auto-creates new MySQL columns on new scraper fields)
AUTO_EVOLVE_SCHEMA=true

# Daily Scheduler Execution Time (HH:MM in 24-hr format)
DAILY_RUN_TIME=02:00
SCHEDULER_TIMEZONE=Asia/Kolkata

# Scrapers Configuration
GETFUND_ENABLED=true
GETFUND_WORKERS=10

MYSCHEME_ENABLED=true
MYSCHEME_WORKERS=5
MYSCHEME_LIMIT=0   # 0 = Scrape all schemes; >0 = test limit

# Local Backup Snapshots
BACKUP_LOCAL_FILES=true
```

---

## Usage & Commands

### 1. Run the Test Suite (Offline / No Live DB Required)
The test suite validates schema dynamic aliasing, arbitrary future scraper ingestion, SHA-256 change detection, soft deletion (`deleted_at`), mock database repository workflows, and scheduler time parsing:

```bash
python test_system.py
```

### 2. Check CLI Options
```bash
python run_scheduler.py --help
```

### 3. Test MySQL Connection & Initialize Tables
```bash
python run_scheduler.py --test-db
```

### 4. Start the Continuous Daily Scheduler Daemon
Runs in the background and executes the scraping pipeline every day at `DAILY_RUN_TIME`:
```bash
python run_scheduler.py --daemon
```

### 5. Run Immediate Scrapes (One-Time Execution)
- Run both scrapers immediately:
  ```bash
  python run_scheduler.py --now
  ```
- Run individual scraper:
  ```bash
  python run_scheduler.py --run getfund
  python run_scheduler.py --run myscheme --limit 10
  ```

### 6. View Database Statistics & Audit Runs
```bash
python run_scheduler.py --stats
```

### 7. Setup as a Windows Scheduled Task
Generate the Windows Task batch runner:
```bash
python run_scheduler.py --windows-task
```
Then register the scheduled task in Windows (Run PowerShell as Administrator):
```powershell
schtasks /create /tn "FloraScheme_Daily_Scraper" /tr "\"D:\florascheme\run_daily_scrape.bat\"" /sc daily /st 02:00 /f
```

---

## Adding Future Scrapers

To integrate a new portal/scraper, register it with `scheduler.jobs.register_scraper`:

```python
from scheduler.jobs import register_scraper

def my_new_portal_scraper():
    # Fetch from API or web
    return [
        {
            "portal_code": "MH_AGRI_2026",
            "title": "Maharashtra Farmer Solar Pump Scheme",
            "web_link": "https://agri.maharashtra.gov.in",
            "subsidy_rate": 80.0,            # Dynamically evolved field
            "eligible_acres": 5,             # Dynamically evolved field
            "solar_capacity_kw": 7.5         # Dynamically evolved field
        }
    ]

register_scraper("maharashtra_portal", my_new_portal_scraper)
```
When executed, FloraScheme will:
1. Normalize core fields (name, source, URL) automatically.
2. Dynamically add `subsidy_rate (DOUBLE)`, `eligible_acres (BIGINT)`, `solar_capacity_kw (DOUBLE)` to the `grant_scheme` MySQL table.
3. Store dynamic extra fields in `extra_fields` JSON and full payload in `raw_data`.
4. Compute change detection hash for idempotent upserts.
