"""
Dynamic Scheme Model Engine for MySQL.
Supports arbitrary future scraper fields through:
1. Canonical field normalization & smart alias resolution.
2. Dynamic schema evolution (automatically adds new columns to MySQL `schemes` table).
3. Dynamic EAV indexing (in `scheme_attributes` table).
4. Lossless JSON document storage (`raw_data` and `extra_fields`).
5. SHA-256 change detection for idempotent upserts.
"""

import json
import hashlib
import logging
import re
from datetime import datetime
from typing import Dict, Any, List, Optional, Set, Tuple
import pymysql

from config import Config
from db.connection import db_manager

logger = logging.getLogger("FloraScheme.DynamicModel")


class DynamicSchemeModel:
    """
    Dynamic schema engine for ingesting scheme records from any source portal.
    Adapts on the fly to new fields without requiring manual migrations.
    """

    # Core canonical fields mapped to standard columns in `schemes` table
    CORE_COLUMNS: Set[str] = {
        "id",
        "source",
        "source_id",
        "slug",
        "scheme_name",
        "scheme_short_title",
        "source_url",
        "category",
        "sub_category",
        "level",
        "state",
        "scheme_type",
        "nodal_ministry",
        "nodal_department",
        "brief_description",
        "detailed_description",
        "benefits",
        "eligibility_criteria",
        "application_process",
        "raw_data",
        "extra_fields",
        "data_hash",
        "scraped_at",
        "created_at",
        "updated_at",
        "deleted_at",
    }

    # Smart alias mapping to resolve diverse field names from different portals
    FIELD_ALIASES: Dict[str, List[str]] = {
        "source_id": ["source_id", "unique_id", "id", "scheme_id", "sid", "code", "portal_code", "portal_id", "identifier"],
        "scheme_name": ["scheme_name", "name", "title", "full_name", "scheme_title"],
        "scheme_short_title": ["scheme_short_title", "short_title", "abbreviation", "acronym"],
        "source_url": ["source_url", "url", "website", "link", "web_link", "web_url", "permalink"],
        "category": ["category", "startup_category", "sector", "domain", "category_name"],
        "sub_category": ["sub_category", "sub_sector", "startup_industry", "industry"],
        "level": ["level", "jurisdiction", "tier"],
        "state": ["state", "beneficiary_state", "region", "target_state", "state_name"],
        "scheme_type": ["scheme_type", "type", "fund_type"],
        "nodal_ministry": ["nodal_ministry", "ministry"],
        "nodal_department": ["nodal_department", "department", "implementing_agency"],
        "brief_description": ["brief_description", "about", "short_description", "summary"],
        "detailed_description": ["detailed_description", "description", "details", "full_description"],
        "benefits": ["benefits", "benefit_details", "financial_support", "incentives"],
        "eligibility_criteria": ["eligibility_criteria", "eligibility", "who_can_apply", "criteria"],
        "application_process": ["application_process", "how_to_apply", "process", "registration_guidelines"],
        "slug": ["slug"],
    }

    def __init__(self, auto_evolve: bool = Config.AUTO_EVOLVE_SCHEMA):
        self.auto_evolve = auto_evolve
        self._cached_columns: Optional[Set[str]] = None
        self._cached_column_types: Optional[Dict[str, str]] = None

    def get_existing_column_types(self, refresh: bool = False) -> Dict[str, str]:
        """Fetches and caches the column names and data types in the `grant_scheme` table."""
        if self._cached_column_types is not None and not refresh:
            return self._cached_column_types

        col_types: Dict[str, str] = {}
        try:
            with db_manager.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("DESCRIBE `grant_scheme`;")
                    for row in cur.fetchall():
                        col_types[row["Field"].lower()] = row["Type"].lower()
            self._cached_column_types = col_types
            self._cached_columns = set(col_types.keys())
        except Exception as e:
            logger.warning("Could not fetch table columns (table may not be initialized yet): %s", e)
            return {c: "mediumtext" for c in self.CORE_COLUMNS}

        return self._cached_column_types

    def get_existing_columns(self, refresh: bool = False) -> Set[str]:
        """Fetches and caches the current set of columns in the `grant_scheme` table."""
        if self._cached_columns is not None and not refresh:
            return self._cached_columns
        return set(self.get_existing_column_types(refresh=refresh).keys())

    @staticmethod
    def sanitize_column_name(field_name: str) -> str:
        """Sanitizes an incoming arbitrary key name to be a safe MySQL column identifier."""
        cleaned = re.sub(r"[^a-zA-Z0-9_]", "_", field_name.strip().lower())
        # Column names cannot start with a digit
        if cleaned and cleaned[0].isdigit():
            cleaned = f"col_{cleaned}"
        # Truncate to MySQL 64 char identifier limit
        return cleaned[:64]

    @staticmethod
    def infer_mysql_column_type(value: Any) -> str:
        """Infers appropriate MySQL column data type based on python value."""
        if value is None:
            return "VARCHAR(255)"
        if isinstance(value, bool):
            return "TINYINT(1)"
        if isinstance(value, int):
            return "BIGINT"
        if isinstance(value, float):
            return "DOUBLE"
        if isinstance(value, (dict, list)):
            return "JSON"
        if isinstance(value, str):
            if len(value) > 255:
                return "MEDIUMTEXT"
            return "VARCHAR(255)"
        return "VARCHAR(255)"

    def evolve_schema_for_fields(self, field_value_pairs: Dict[str, Any]) -> None:
        """
        Dynamically adds any new fields as columns in `grant_scheme` table if not already present,
        and auto-widens existing VARCHAR columns to MEDIUMTEXT if incoming text exceeds 255 chars.
        Ensures thread-safe/idempotent column creation.
        """
        if not self.auto_evolve:
            return

        existing_types = self.get_existing_column_types()
        new_cols_to_add: List[Tuple[str, str]] = []
        cols_to_widen: List[str] = []

        for field, val in field_value_pairs.items():
            sanitized = self.sanitize_column_name(field)
            if not sanitized or sanitized in self.CORE_COLUMNS:
                continue

            if sanitized not in existing_types:
                col_type = self.infer_mysql_column_type(val)
                new_cols_to_add.append((sanitized, col_type))
            else:
                # Column already exists: check if it needs widening from VARCHAR to MEDIUMTEXT
                curr_type = existing_types.get(sanitized, "")
                if "varchar" in curr_type and isinstance(val, str) and len(val) > 255:
                    cols_to_widen.append(sanitized)

        if not new_cols_to_add and not cols_to_widen:
            return

        with db_manager.get_connection() as conn:
            with conn.cursor() as cur:
                # Add new columns
                for col_name, col_type in new_cols_to_add:
                    try:
                        sql = f"ALTER TABLE `grant_scheme` ADD COLUMN `{col_name}` {col_type} NULL;"
                        cur.execute(sql)
                        logger.info("Dynamic Schema Evolution: Added new column `%s` (%s) to `grant_scheme`", col_name, col_type)
                        existing_types[col_name] = col_type.lower()
                    except pymysql.MySQLError as err:
                        # 1060: Duplicate column name (if created concurrently)
                        if err.args[0] == 1060:
                            existing_types[col_name] = col_type.lower()
                        else:
                            logger.error("Failed to dynamically add column `%s`: %s", col_name, err)

                # Widen existing columns
                for col_name in cols_to_widen:
                    try:
                        sql = f"ALTER TABLE `grant_scheme` MODIFY COLUMN `{col_name}` MEDIUMTEXT NULL;"
                        cur.execute(sql)
                        logger.info("Dynamic Schema Evolution: Auto-widened column `%s` from VARCHAR to MEDIUMTEXT", col_name)
                        existing_types[col_name] = "mediumtext"
                    except pymysql.MySQLError as err:
                        logger.error("Failed to widen column `%s`: %s", col_name, err)

        self._cached_column_types = existing_types
        self._cached_columns = set(existing_types.keys())

    def normalize_record(self, source: str, raw_record: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transforms an arbitrary scraper dictionary into a structured record:
        - Resolves canonical core fields using smart aliases.
        - Isolates dynamic extra fields.
        - Generates SHA-256 hash.
        - Evolves database schema if new fields are present.
        """
        raw_copy = dict(raw_record)
        normalized: Dict[str, Any] = {
            "source": str(source).strip().lower(),
            "scraped_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        # Resolve core fields using aliases
        used_keys = set()
        for core_field, aliases in self.FIELD_ALIASES.items():
            value = None
            for alias in aliases:
                if alias in raw_copy and raw_copy[alias] is not None and str(raw_copy[alias]).strip() != "":
                    value = raw_copy[alias]
                    used_keys.add(alias)
                    break
            normalized[core_field] = value

        # Ensure source_id is non-empty
        if not normalized.get("source_id"):
            # Fallback to slug or hash of name
            name_val = str(normalized.get("scheme_name") or "unknown")
            normalized["source_id"] = normalized.get("slug") or hashlib.md5(name_val.encode()).hexdigest()

        # Format descriptions / strings cleanly
        for text_field in ["scheme_name", "brief_description", "detailed_description", "benefits", "eligibility_criteria", "application_process", "sub_category"]:
            val = normalized.get(text_field)
            if val is not None and not isinstance(val, str):
                normalized[text_field] = str(val)

        # Bound VARCHAR core columns to prevent MySQL 1406 DataError
        varchar_limits = {
            "source_id": 255,
            "slug": 255,
            "scheme_name": 500,
            "scheme_short_title": 255,
            "source_url": 1000,
            "level": 100,
            "scheme_type": 255,
            "nodal_ministry": 500,
            "nodal_department": 500,
            "category": 500,
            "state": 500,
        }
        for field, max_len in varchar_limits.items():
            val = normalized.get(field)
            if val is not None:
                s_val = str(val).strip()
                normalized[field] = s_val[:max_len] if len(s_val) > max_len else s_val

        # Dynamic extra fields: all keys not assigned to canonical core columns
        extra_fields: Dict[str, Any] = {}
        for k, v in raw_copy.items():
            if k not in used_keys and k not in self.CORE_COLUMNS:
                extra_fields[k] = v

        normalized["extra_fields"] = extra_fields
        normalized["raw_data"] = raw_copy

        # Compute content hash over raw_data for change detection
        serialized = json.dumps(raw_copy, sort_keys=True, ensure_ascii=False, default=str)
        normalized["data_hash"] = hashlib.sha256(serialized.encode("utf-8")).hexdigest()

        # Dynamic Schema Evolution: check and add new columns if enabled
        if self.auto_evolve and extra_fields:
            self.evolve_schema_for_fields(extra_fields)

        return normalized

    @staticmethod
    def extract_eav_attributes(scheme_id: int, source: str, extra_fields: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Converts dynamic extra_fields into EAV records for `scheme_attributes` table.
        """
        eav_records = []
        for key, val in extra_fields.items():
            if val is None:
                continue

            # Determine type and serialized string value
            data_type = "string"
            str_val = ""
            if isinstance(val, bool):
                data_type = "boolean"
                str_val = "1" if val else "0"
            elif isinstance(val, (int, float)):
                data_type = "number"
                str_val = str(val)
            elif isinstance(val, list):
                data_type = "list"
                str_val = ", ".join(str(x) for x in val) if all(isinstance(x, (str, int, float)) for x in val) else json.dumps(val, ensure_ascii=False)
            elif isinstance(val, dict):
                data_type = "json"
                str_val = json.dumps(val, ensure_ascii=False)
            else:
                str_val = str(val).strip()

            eav_records.append({
                "scheme_id": scheme_id,
                "source": source,
                "attribute_key": key[:128],
                "attribute_value": str_val,
                "data_type": data_type
            })

        return eav_records
