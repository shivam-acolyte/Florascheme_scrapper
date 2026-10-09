"""
FloraScheme Database Repository.
Provides high-level CRUD, bulk upserts, change detection, soft deletion,
and dynamic attribute querying against MySQL.
Unified model: Merged dynamic attributes into `grant_scheme` table, with scraper metrics in `scheme_scrapper`.
"""

import json
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
import pymysql

from config import Config
from db.connection import db_manager
from db.dynamic_model import DynamicSchemeModel

logger = logging.getLogger("FloraScheme.Repository")


class SchemeRepository:
    """Repository handling MySQL persistence for dynamic scheme records."""

    def __init__(self):
        self.model = DynamicSchemeModel(auto_evolve=Config.AUTO_EVOLVE_SCHEMA)

    def save_scheme(
        self,
        source: str,
        raw_record: Dict[str, Any],
        conn: Optional[Any] = None,
        normalized_record: Optional[Dict[str, Any]] = None,
        existing_record: Optional[Dict[str, Any]] = None
    ) -> Tuple[Optional[int], str]:
        """
        Ingests a single scheme record.
        Returns (scheme_id, status) where status is 'INSERTED', 'UPDATED', 'UNCHANGED', or 'FAILED'.
        """
        if conn is None:
            with db_manager.get_connection() as c:
                return self._save_scheme_with_conn(c, source, raw_record, normalized_record, existing_record)
        else:
            return self._save_scheme_with_conn(conn, source, raw_record, normalized_record, existing_record)

    def _save_scheme_with_conn(
        self,
        conn: Any,
        source: str,
        raw_record: Dict[str, Any],
        normalized_record: Optional[Dict[str, Any]] = None,
        existing_record: Optional[Dict[str, Any]] = None
    ) -> Tuple[Optional[int], str]:
        try:
            record = normalized_record or self.model.normalize_record(source, raw_record)
            src = record["source"]
            src_id = record["source_id"]
            new_hash = record["data_hash"]

            with conn.cursor() as cur:
                # Use pre-fetched existing record if available, else query DB
                if existing_record is not None:
                    existing = existing_record
                else:
                    cur.execute(
                        "SELECT id, data_hash, deleted_at FROM `grant_scheme` WHERE `source` = %s AND `source_id` = %s;",
                        (src, src_id)
                    )
                    existing = cur.fetchone()

                if existing and existing.get("id"):
                    scheme_id = existing["id"]
                    old_hash = existing["data_hash"]
                    was_deleted = existing.get("deleted_at") is not None

                    # Check if data actually changed and not previously soft-deleted
                    if old_hash == new_hash and not was_deleted:
                        cur.execute(
                            "UPDATE `grant_scheme` SET `scraped_at` = %s WHERE `id` = %s;",
                            (record["scraped_at"], scheme_id)
                        )
                        return scheme_id, "UNCHANGED"

                    # Perform UPDATE
                    update_cols = [
                        "slug = %s",
                        "scheme_name = %s",
                        "scheme_short_title = %s",
                        "source_url = %s",
                        "category = %s",
                        "sub_category = %s",
                        "level = %s",
                        "state = %s",
                        "scheme_type = %s",
                        "nodal_ministry = %s",
                        "nodal_department = %s",
                        "brief_description = %s",
                        "detailed_description = %s",
                        "benefits = %s",
                        "eligibility_criteria = %s",
                        "application_process = %s",
                        "raw_data = %s",
                        "extra_fields = %s",
                        "data_hash = %s",
                        "scraped_at = %s",
                        "deleted_at = NULL",
                        "updated_at = NOW()"
                    ]
                    params = [
                        record.get("slug"),
                        record.get("scheme_name"),
                        record.get("scheme_short_title"),
                        record.get("source_url"),
                        record.get("category"),
                        record.get("sub_category"),
                        record.get("level"),
                        record.get("state"),
                        record.get("scheme_type"),
                        record.get("nodal_ministry"),
                        record.get("nodal_department"),
                        record.get("brief_description"),
                        record.get("detailed_description"),
                        record.get("benefits"),
                        record.get("eligibility_criteria"),
                        record.get("application_process"),
                        json.dumps(record["raw_data"], ensure_ascii=False),
                        json.dumps(record["extra_fields"], ensure_ascii=False),
                        new_hash,
                        record["scraped_at"],
                    ]

                    # Populate evolved dynamic columns if active
                    existing_cols = self.model.get_existing_columns()
                    for extra_k, extra_v in record["extra_fields"].items():
                        sanitized = self.model.sanitize_column_name(extra_k)
                        if sanitized in existing_cols and sanitized not in self.model.CORE_COLUMNS:
                            update_cols.append(f"`{sanitized}` = %s")
                            col_val = json.dumps(extra_v, ensure_ascii=False) if isinstance(extra_v, (dict, list)) else extra_v
                            params.append(col_val)

                    params.append(scheme_id)
                    sql = f"UPDATE `grant_scheme` SET {', '.join(update_cols)} WHERE `id` = %s;"
                    cur.execute(sql, params)
                    return scheme_id, "UPDATED"

                else:
                    # Perform INSERT
                    insert_cols = [
                        "`source`", "`source_id`", "`slug`", "`scheme_name`", "`scheme_short_title`",
                        "`source_url`", "`category`", "`sub_category`", "`level`", "`state`",
                        "`scheme_type`", "`nodal_ministry`", "`nodal_department`", "`brief_description`",
                        "`detailed_description`", "`benefits`", "`eligibility_criteria`", "`application_process`",
                        "`raw_data`", "`extra_fields`", "`data_hash`", "`scraped_at`", "`deleted_at`"
                    ]
                    placeholders = ["%s"] * len(insert_cols)
                    params = [
                        src,
                        src_id,
                        record.get("slug"),
                        record.get("scheme_name"),
                        record.get("scheme_short_title"),
                        record.get("source_url"),
                        record.get("category"),
                        record.get("sub_category"),
                        record.get("level"),
                        record.get("state"),
                        record.get("scheme_type"),
                        record.get("nodal_ministry"),
                        record.get("nodal_department"),
                        record.get("brief_description"),
                        record.get("detailed_description"),
                        record.get("benefits"),
                        record.get("eligibility_criteria"),
                        record.get("application_process"),
                        json.dumps(record["raw_data"], ensure_ascii=False),
                        json.dumps(record["extra_fields"], ensure_ascii=False),
                        new_hash,
                        record["scraped_at"],
                        None,  # deleted_at is NULL on creation
                    ]

                    # Populate evolved dynamic columns if active
                    existing_cols = self.model.get_existing_columns()
                    for extra_k, extra_v in record["extra_fields"].items():
                        sanitized = self.model.sanitize_column_name(extra_k)
                        if sanitized in existing_cols and sanitized not in self.model.CORE_COLUMNS:
                            insert_cols.append(f"`{sanitized}`")
                            placeholders.append("%s")
                            col_val = json.dumps(extra_v, ensure_ascii=False) if isinstance(extra_v, (dict, list)) else extra_v
                            params.append(col_val)

                    sql = f"INSERT INTO `grant_scheme` ({', '.join(insert_cols)}) VALUES ({', '.join(placeholders)});"
                    cur.execute(sql, params)
                    scheme_id = cur.lastrowid
                    return scheme_id, "INSERTED"

        except Exception as e:
            logger.error("Error saving scheme from '%s': %s", source, e, exc_info=True)
            return None, "FAILED"

    def soft_delete_scheme(self, scheme_id: int) -> bool:
        """Marks a scheme as soft-deleted by setting deleted_at = NOW()."""
        try:
            with db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("UPDATE `grant_scheme` SET `deleted_at` = NOW() WHERE `id` = %s;", (scheme_id,))
                    return cur.rowcount > 0
        except Exception as e:
            logger.error("Error soft deleting scheme id=%s: %s", scheme_id, e)
            return False

    def restore_scheme(self, scheme_id: int) -> bool:
        """Restores a soft-deleted scheme by resetting deleted_at = NULL."""
        try:
            with db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("UPDATE `grant_scheme` SET `deleted_at` = NULL WHERE `id` = %s;", (scheme_id,))
                    return cur.rowcount > 0
        except Exception as e:
            logger.error("Error restoring scheme id=%s: %s", scheme_id, e)
            return False

    def soft_delete_missing_schemes(self, source: str, active_source_ids: set) -> int:
        """
        Soft-deletes schemes belonging to `source` that are currently active in DB
        but were NOT present in `active_source_ids` (i.e. removed, delisted, or abandoned).
        Returns the number of schemes soft-deleted.
        """
        if not active_source_ids:
            # Safety safeguard: never soft delete all records if scraper returned 0 items
            return 0

        try:
            with db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT `source_id` FROM `grant_scheme` WHERE `source` = %s AND `deleted_at` IS NULL;",
                        (source,)
                    )
                    rows = cur.fetchall()
                    db_ids = {str(row["source_id"]) for row in rows}
                    missing_ids = list(db_ids - {str(x) for x in active_source_ids})

                    if not missing_ids:
                        return 0

                    # Batch update in chunks of 500
                    chunk_size = 500
                    total_soft_deleted = 0
                    for i in range(0, len(missing_ids), chunk_size):
                        chunk = missing_ids[i:i + chunk_size]
                        placeholders = ", ".join(["%s"] * len(chunk))
                        sql = f"UPDATE `grant_scheme` SET `deleted_at` = NOW() WHERE `source` = %s AND `source_id` IN ({placeholders});"
                        cur.execute(sql, [source] + chunk)
                        total_soft_deleted += cur.rowcount

                    logger.info("Soft-deleted %d abandoned/delisted schemes for source '%s'", total_soft_deleted, source)
                    return total_soft_deleted
        except Exception as e:
            logger.error("Error soft-deleting missing schemes for source '%s': %s", source, e)
            return 0

    def save_schemes_batch(
        self,
        source: str,
        records: List[Dict[str, Any]],
        soft_delete_missing: bool = True
    ) -> Dict[str, int]:
        """
        Batch processing wrapper that handles a collection of scraped records.
        If soft_delete_missing is True, schemes active in DB that were NOT in `records`
        (i.e. removed or abandoned from portal) are automatically soft-deleted.
        """
        summary = {
            "total": len(records),
            "inserted": 0,
            "updated": 0,
            "unchanged": 0,
            "failed": 0,
            "soft_deleted": 0
        }
        seen_source_ids = set()

        if not records:
            return summary

        # 1. Pre-evolve schema across the entire batch in a single pass (massive performance boost)
        if self.model.auto_evolve:
            all_extra_fields: Dict[str, Any] = {}
            for rec in records:
                for k, v in rec.items():
                    if k not in all_extra_fields:
                        all_extra_fields[k] = v
                    elif isinstance(v, str) and (all_extra_fields[k] is None or len(v) > len(str(all_extra_fields[k]))):
                        all_extra_fields[k] = v
            self.model.evolve_schema_for_fields(all_extra_fields)

        # 2. Reuse a single database connection and pre-fetch existing records to avoid round trips
        with db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT id, source_id, data_hash, deleted_at FROM `grant_scheme` WHERE `source` = %s;",
                    (source,)
                )
                existing_cache = {str(r["source_id"]): r for r in cur.fetchall()}

            for idx, rec in enumerate(records, 1):
                norm = self.model.normalize_record(source, rec)
                src_id = norm.get("source_id")
                if src_id:
                    seen_source_ids.add(str(src_id))

                existing_rec = existing_cache.get(str(src_id)) if src_id else None
                scheme_id, status = self.save_scheme(
                    source,
                    rec,
                    conn=conn,
                    normalized_record=norm,
                    existing_record=existing_rec
                )

                if status == "INSERTED":
                    summary["inserted"] += 1
                    if src_id and scheme_id:
                        existing_cache[str(src_id)] = {
                            "id": scheme_id,
                            "source_id": str(src_id),
                            "data_hash": norm["data_hash"],
                            "deleted_at": None
                        }
                elif status == "UPDATED":
                    summary["updated"] += 1
                    if src_id:
                        existing_cache[str(src_id)] = {
                            "id": scheme_id or (existing_rec["id"] if existing_rec else None),
                            "source_id": str(src_id),
                            "data_hash": norm["data_hash"],
                            "deleted_at": None
                        }
                elif status == "UNCHANGED":
                    summary["unchanged"] += 1
                else:
                    summary["failed"] += 1

                if idx % 500 == 0 or idx == len(records):
                    logger.info("Persisted %d/%d schemes to MySQL for source '%s'...", idx, len(records), source)

        # 3. Reconcile abandoned/missing schemes
        if soft_delete_missing and seen_source_ids:
            summary["soft_deleted"] = self.soft_delete_missing_schemes(source, seen_source_ids)

        logger.info(
            "Batch Ingestion Complete for '%s': Total=%d, New=%d, Updated=%d, Unchanged=%d, Soft-Deleted=%d, Failed=%d",
            source, summary["total"], summary["inserted"], summary["updated"], summary["unchanged"], summary["soft_deleted"], summary["failed"]
        )
        return summary

    # --------------------------------------------------------------------------
    # Scraper Run Status & Audit Tracking (Stored in `scheme_scrapper` Table)
    # --------------------------------------------------------------------------
    def start_scrape_run(self, source: str) -> Optional[int]:
        """Logs the beginning of a scraper run directly on the scheme_scrapper table."""
        with db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO `scheme_scrapper` (`source_name`, `display_name`, `last_run_at`, `last_status`)
                    VALUES (%s, %s, NOW(), 'RUNNING')
                    ON DUPLICATE KEY UPDATE `last_run_at` = NOW(), `last_status` = 'RUNNING';
                    """,
                    (source, source.capitalize())
                )
                cur.execute("SELECT `id` FROM `scheme_scrapper` WHERE `source_name` = %s;", (source,))
                row = cur.fetchone()
                return row["id"] if row else None

    def finish_scrape_run(
        self,
        run_id: Optional[int],
        source: str,
        status: str,
        total: int,
        inserted: int,
        updated: int,
        unchanged: int,
        failed: int,
        duration: float,
        error_msg: Optional[str] = None,
        soft_deleted: int = 0
    ) -> None:
        """Updates the scheme_scrapper table with run metrics."""
        with db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                # Count non-deleted schemes
                cur.execute(
                    "SELECT COUNT(*) AS total_schemes FROM `grant_scheme` WHERE `source` = %s AND `deleted_at` IS NULL;",
                    (source,)
                )
                row = cur.fetchone()
                total_schemes = row["total_schemes"] if row else 0

                cur.execute(
                    """
                    UPDATE `scheme_scrapper`
                    SET `last_run_at` = NOW(),
                        `last_status` = %s,
                        `total_schemes_count` = %s,
                        `last_duration_seconds` = %s,
                        `last_inserted_count` = %s,
                        `last_updated_count` = %s,
                        `last_unchanged_count` = %s,
                        `last_soft_deleted_count` = %s,
                        `last_failed_count` = %s,
                        `last_error_message` = %s
                    WHERE `source_name` = %s;
                    """,
                    (
                        status,
                        total_schemes,
                        round(duration, 2),
                        inserted,
                        updated,
                        unchanged,
                        soft_deleted,
                        failed,
                        error_msg,
                        source
                    )
                )

    # --------------------------------------------------------------------------
    # Query Engine (Supports Core Columns + Any Dynamic Field in JSON / Columns)
    # --------------------------------------------------------------------------
    def query_schemes(
        self,
        source: Optional[str] = None,
        category: Optional[str] = None,
        state: Optional[str] = None,
        search: Optional[str] = None,
        dynamic_attributes: Optional[Dict[str, str]] = None,
        include_deleted: bool = False,
        page: int = 1,
        page_size: int = 50
    ) -> Dict[str, Any]:
        """
        Flexible search supporting standard fields AND any dynamic future field via JSON.
        dynamic_attributes: e.g. {"investment_size": "₹50,00,000", "fund_type": "Grant"}
        """
        page = max(1, page)
        page_size = min(max(1, page_size), 500)
        offset = (page - 1) * page_size

        where_clauses = ["1=1"]
        params: List[Any] = []

        if not include_deleted:
            where_clauses.append("s.`deleted_at` IS NULL")

        if source:
            where_clauses.append("s.`source` = %s")
            params.append(source)
        if category:
            where_clauses.append("s.`category` LIKE %s")
            params.append(f"%{category}%")
        if state:
            where_clauses.append("s.`state` LIKE %s")
            params.append(f"%{state}%")
        if search:
            where_clauses.append("(s.`scheme_name` LIKE %s OR s.`brief_description` LIKE %s)")
            params.extend([f"%{search}%", f"%{search}%"])

        # Dynamic attribute filters: query directly from extra_fields JSON document
        if dynamic_attributes:
            for attr_key, attr_val in dynamic_attributes.items():
                where_clauses.append("JSON_UNQUOTE(JSON_EXTRACT(s.`extra_fields`, %s)) LIKE %s")
                params.append(f"$.{attr_key}")
                params.append(f"%{attr_val}%")

        where_sql = " AND ".join(where_clauses)

        with db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                count_sql = f"SELECT COUNT(*) AS total FROM `grant_scheme` s WHERE {where_sql};"
                cur.execute(count_sql, params)
                total_count = cur.fetchone()["total"]

                fetch_sql = f"""
                    SELECT s.* 
                    FROM `grant_scheme` s 
                    WHERE {where_sql} 
                    ORDER BY s.id DESC 
                    LIMIT %s OFFSET %s;
                """
                cur.execute(fetch_sql, params + [page_size, offset])
                items = cur.fetchall()

        return {
            "total": total_count,
            "page": page,
            "page_size": page_size,
            "total_pages": (total_count + page_size - 1) // page_size if total_count > 0 else 1,
            "items": items
        }

    def get_stats(self) -> Dict[str, Any]:
        """Returns consolidated database statistics."""
        with db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                # Total active schemes
                cur.execute("SELECT COUNT(*) AS total FROM `grant_scheme` WHERE `deleted_at` IS NULL;")
                total = cur.fetchone()["total"]

                # By source
                cur.execute(
                    "SELECT `source`, COUNT(*) AS count, MAX(`scraped_at`) AS last_scraped "
                    "FROM `grant_scheme` WHERE `deleted_at` IS NULL GROUP BY `source`;"
                )
                by_source = cur.fetchall()

                # By category
                cur.execute(
                    "SELECT `category`, COUNT(*) AS count FROM `grant_scheme` "
                    "WHERE `category` IS NOT NULL AND `category` != '' AND `deleted_at` IS NULL "
                    "GROUP BY `category` ORDER BY count DESC LIMIT 10;"
                )
                top_categories = cur.fetchall()

                # Scraper statuses & metrics from `scheme_scrapper` table
                cur.execute(
                    "SELECT `source_name` AS source, `last_run_at` AS started_at, `last_status` AS status, "
                    "`total_schemes_count`, `last_inserted_count` AS inserted_count, `last_updated_count` AS updated_count, "
                    "`last_soft_deleted_count` AS soft_deleted_count, `last_duration_seconds` AS duration_seconds FROM `scheme_scrapper` ORDER BY `updated_at` DESC;"
                )
                recent_runs = cur.fetchall()

                return {
                    "total_schemes": total,
                    "by_source": by_source,
                    "top_categories": top_categories,
                    "recent_runs": recent_runs
                }


# Global repository instance
scheme_repo = SchemeRepository()
