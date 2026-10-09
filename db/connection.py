"""
MySQL Database Connection Manager.
STRICT REQUIREMENT: Exclusively supports MySQL 5.7+ / 8.0+.
Provides connection pooling, database auto-initialization, and query execution.
"""

import logging
from typing import Dict, Any, Optional, List, Tuple
from contextlib import contextmanager
import pymysql
from pymysql.cursors import DictCursor

from config import Config

logger = logging.getLogger("FloraScheme.DB")


class MySQLManager:
    """Manages MySQL connections and schema initialization."""

    def __init__(self):
        # Strict validation
        if Config.DB_TYPE.lower() != "mysql":
            raise RuntimeError(
                f"STRICT REQUIREMENT VIOLATION: Database type is set to '{Config.DB_TYPE}'. "
                "Only MySQL is supported by this application!"
            )
        self.cfg = Config.get_mysql_config()

    def get_raw_connection(self, include_db: bool = True) -> pymysql.connections.Connection:
        """
        Creates and returns a raw pymysql connection.
        If include_db is False, connects to the server without selecting the target database
        (useful for CREATE DATABASE IF NOT EXISTS).
        """
        params = self.cfg.copy()
        if not include_db:
            params.pop("database", None)

        try:
            conn = pymysql.connect(
                **params,
                cursorclass=DictCursor,
                autocommit=True
            )
            # Verify server is MySQL
            server_info = conn.get_server_info().lower()
            if "mariadb" in server_info:
                logger.info("Connected to MariaDB/MySQL compatible server: %s", server_info)
            else:
                logger.debug("Connected to MySQL Server: %s", server_info)
            return conn
        except pymysql.MySQLError as err:
            logger.error("Failed to connect to MySQL (%s:%s): %s", self.cfg["host"], self.cfg["port"], err)
            raise

    @contextmanager
    def get_connection(self):
        """Context manager yielding an active connection."""
        conn = self.get_raw_connection(include_db=True)
        try:
            yield conn
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def test_connection(self) -> Dict[str, Any]:
        """
        Performs a health check against the MySQL instance.
        Returns a dictionary with status and diagnostic info.
        """
        result = {
            "success": False,
            "host": self.cfg["host"],
            "port": self.cfg["port"],
            "user": self.cfg["user"],
            "database": self.cfg["database"],
            "server_version": None,
            "database_exists": False,
            "tables": [],
            "error": None
        }
        try:
            # First check server connectivity without database
            conn = self.get_raw_connection(include_db=False)
            with conn.cursor() as cur:
                cur.execute("SELECT VERSION() AS ver, DATABASE() AS cur_db;")
                row = cur.fetchone()
                result["server_version"] = row["ver"] if row else "Unknown"

                cur.execute(f"SHOW DATABASES LIKE '{self.cfg['database']}';")
                db_row = cur.fetchone()
                if db_row:
                    result["database_exists"] = True
            conn.close()

            # Next check target database if it exists
            if result["database_exists"]:
                with self.get_connection() as db_conn:
                    with db_conn.cursor() as cur:
                        cur.execute("SHOW TABLES;")
                        rows = cur.fetchall()
                        result["tables"] = [list(r.values())[0] for r in rows]

            result["success"] = True
            return result
        except Exception as e:
            result["error"] = str(e)
            return result

    def get_rendered_schema_sql(self, schema_file: Optional[str] = None) -> str:
        """
        Returns the complete SQL script with the dynamic database name injected from .env.
        """
        from pathlib import Path
        if not schema_file:
            schema_file = str(Path(__file__).resolve().parent / "schema.sql")

        with open(schema_file, "r", encoding="utf-8") as f:
            table_sql = f.read().strip()

        header = f"""-- =============================================================================
-- FloraScheme MySQL Schema (Dynamically configured from .env)
-- Database Name: `{self.cfg['database']}`
-- =============================================================================

CREATE DATABASE IF NOT EXISTS `{self.cfg['database']}` 
  CHARACTER SET {self.cfg['charset']} 
  COLLATE {self.cfg['charset']}_unicode_ci;

USE `{self.cfg['database']}`;

"""
        return header + table_sql

    def init_database(self, schema_file: Optional[str] = None) -> bool:
        """
        Ensures the database exists (using dynamic MYSQL_DATABASE from .env)
        and executes table creation queries in that database.
        """
        from pathlib import Path
        if not schema_file:
            schema_file = str(Path(__file__).resolve().parent / "schema.sql")

        logger.info("Initializing MySQL database '%s' from .env configuration...", self.cfg["database"])

        # 1. Ensure database exists dynamically from .env
        server_conn = self.get_raw_connection(include_db=False)
        try:
            with server_conn.cursor() as cur:
                cur.execute(
                    f"CREATE DATABASE IF NOT EXISTS `{self.cfg['database']}` "
                    f"CHARACTER SET {self.cfg['charset']} "
                    f"COLLATE {self.cfg['charset']}_unicode_ci;"
                )
        finally:
            server_conn.close()

        # 2. Run schema queries in target database
        with open(schema_file, "r", encoding="utf-8") as f:
            content = f.read()

        # Split commands cleanly by semicolon, skipping comments
        statements = []
        current = []
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("--") or stripped.startswith("/*") or not stripped:
                continue
            current.append(line)
            if stripped.endswith(";"):
                statements.append("\n".join(current))
                current = []

        with self.get_connection() as conn:
            with conn.cursor() as cur:
                # Ensure the dynamic database from .env is active
                cur.execute(f"USE `{self.cfg['database']}`;")
                for stmt in statements:
                    stmt = stmt.strip()
                    if stmt:
                        try:
                            cur.execute(stmt)
                        except pymysql.MySQLError as err:
                            # Ignore benign table/trigger already exists warnings
                            if err.args[0] in (1050, 1060, 1061):
                                continue
                            logger.error("Error executing statement: %s\nStatement was: %s", err, stmt[:100])
                            raise

        logger.info("MySQL database '%s' schema verified successfully.", self.cfg["database"])
        return True


# Global manager instance
db_manager = MySQLManager()
