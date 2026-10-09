"""
FloraScheme Configuration Module.
Loads configuration from environment variables and .env file.
Strictly configured for MySQL database backend.
"""

import os
from pathlib import Path
from typing import Dict, Any
from dotenv import load_dotenv

# Base Directory
BASE_DIR = Path(__file__).resolve().parent

# Load .env file
load_dotenv(BASE_DIR / ".env")


class Config:
    """Central configuration class."""

    # -------------------------------------------------------------
    # Database Settings (STRICTLY MYSQL)
    # -------------------------------------------------------------
    DB_TYPE: str = "mysql"  # STRICT: only MySQL is supported
    MYSQL_HOST: str = os.getenv("MYSQL_HOST", "localhost")
    MYSQL_PORT: int = int(os.getenv("MYSQL_PORT", "3306"))
    MYSQL_USER: str = os.getenv("MYSQL_USER", "root")
    MYSQL_PASSWORD: str = os.getenv("MYSQL_PASSWORD", "")
    MYSQL_DATABASE: str = os.getenv("MYSQL_DATABASE", "florascheme_db")
    MYSQL_CHARSET: str = os.getenv("MYSQL_CHARSET", "utf8mb4")

    # Dynamic Schema Engine
    AUTO_EVOLVE_SCHEMA: bool = os.getenv("AUTO_EVOLVE_SCHEMA", "true").lower() in ("true", "1", "yes")

    # Connection pool options
    DB_POOL_SIZE: int = int(os.getenv("DB_POOL_SIZE", "5"))
    DB_CONNECT_TIMEOUT: int = int(os.getenv("DB_CONNECT_TIMEOUT", "10"))

    # -------------------------------------------------------------
    # Scheduler Settings
    # -------------------------------------------------------------
    # Daily execution time in HH:MM format (24-hour clock, e.g. "02:00" for 2 AM)
    DAILY_RUN_TIME: str = os.getenv("DAILY_RUN_TIME", "02:00")
    
    # Timezone (e.g. "Asia/Kolkata", "UTC")
    SCHEDULER_TIMEZONE: str = os.getenv("SCHEDULER_TIMEZONE", "Asia/Kolkata")

    # Scraper settings
    GETFUND_ENABLED: bool = os.getenv("GETFUND_ENABLED", "true").lower() in ("true", "1", "yes")
    GETFUND_WORKERS: int = int(os.getenv("GETFUND_WORKERS", "10"))

    MYSCHEME_ENABLED: bool = os.getenv("MYSCHEME_ENABLED", "true").lower() in ("true", "1", "yes")
    MYSCHEME_WORKERS: int = int(os.getenv("MYSCHEME_WORKERS", "5"))
    MYSCHEME_LIMIT: int = int(os.getenv("MYSCHEME_LIMIT", "0"))  # 0 means ALL schemes

    # Backup & Export
    BACKUP_LOCAL_FILES: bool = os.getenv("BACKUP_LOCAL_FILES", "true").lower() in ("true", "1", "yes")
    BACKUP_DIR: Path = BASE_DIR / "data" / "backups"

    @classmethod
    def get_mysql_config(cls) -> Dict[str, Any]:
        """Returns connection parameters for PyMySQL / MySQL drivers."""
        if cls.DB_TYPE.lower() != "mysql":
            raise ValueError(
                f"Unsupported database type '{cls.DB_TYPE}'. This application STRICTLY supports MySQL only!"
            )
        return {
            "host": cls.MYSQL_HOST,
            "port": cls.MYSQL_PORT,
            "user": cls.MYSQL_USER,
            "password": cls.MYSQL_PASSWORD,
            "database": cls.MYSQL_DATABASE,
            "charset": cls.MYSQL_CHARSET,
            "connect_timeout": cls.DB_CONNECT_TIMEOUT,
        }

    @classmethod
    def get_daily_hour_minute(cls) -> tuple[int, int]:
        """Parses DAILY_RUN_TIME (HH:MM) into (hour, minute)."""
        try:
            parts = cls.DAILY_RUN_TIME.strip().split(":")
            hour = int(parts[0])
            minute = int(parts[1]) if len(parts) > 1 else 0
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError
            return hour, minute
        except Exception:
            return 2, 0  # default 02:00 AM
