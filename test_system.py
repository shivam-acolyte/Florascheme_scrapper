"""
FloraScheme Test Suite.
Validates:
1. Dynamic Scheme Model with canonical field aliasing and dynamic extra fields.
2. Handling of arbitrary future scraper fields.
3. SHA-256 change detection and idempotency.
4. Strict MySQL enforcement.
5. Scheduler registration and job orchestration.
6. Live MySQL integration (if connection available).
"""

import sys
import unittest
from datetime import datetime
from pathlib import Path

# Add project root to sys.path
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from config import Config
from db.dynamic_model import DynamicSchemeModel
from scheduler.jobs import register_scraper, CUSTOM_SCRAPERS


class TestDynamicModel(unittest.TestCase):
    """Tests the dynamic schema engine and future-field handling."""

    def setUp(self):
        # Auto-evolve set to False during pure in-memory unit tests
        self.model = DynamicSchemeModel(auto_evolve=False)

    def test_strict_mysql_enforcement(self):
        """Verifies that only MySQL is permitted."""
        self.assertEqual(Config.DB_TYPE.lower(), "mysql")

    def test_getfunding_normalization(self):
        """Tests ingestion of GetFunding record structure."""
        sample_getfund = {
            "sid": 101,
            "unique_id": "getfund_12345",
            "name": "Biotech Innovation Grant",
            "full_name": "BIRAC Biotechnology Ignition Grant (BIG)",
            "scheme_type": "Central Government",
            "state": "National",
            "fund_type": "Grant",
            "investment_size": "₹50,00,000",
            "stage": "Idea to POC",
            "startup_category": "Biotechnology",
            "about": "Short about snippet",
            "description": "Full detailed description of the BIG scheme",
            "eligibility_criteria": "Early stage biotech startups",
            "application_process": "Apply via online portal twice a year",
            "website": "https://birac.nic.in/big.php",
            "contact_details": "info@birac.nic.in"
        }

        normalized = self.model.normalize_record("getfunding", sample_getfund)

        # Core fields mapped via aliases
        self.assertEqual(normalized["source"], "getfunding")
        self.assertEqual(normalized["source_id"], "getfund_12345")
        self.assertEqual(normalized["scheme_name"], "Biotech Innovation Grant")
        self.assertEqual(normalized["category"], "Biotechnology")
        self.assertEqual(normalized["brief_description"], "Short about snippet")
        self.assertEqual(normalized["detailed_description"], "Full detailed description of the BIG scheme")

        # Dynamic extra fields preserved
        extras = normalized["extra_fields"]
        self.assertIn("investment_size", extras)
        self.assertEqual(extras["investment_size"], "₹50,00,000")
        self.assertIn("stage", extras)
        self.assertEqual(extras["stage"], "Idea to POC")
        self.assertIn("contact_details", extras)

        # Raw data preserved lossless
        self.assertEqual(normalized["raw_data"]["sid"], 101)
        self.assertTrue(len(normalized["data_hash"]) == 64)

    def test_myscheme_normalization(self):
        """Tests ingestion of myScheme.gov.in record structure."""
        sample_myscheme = {
            "id": "myscheme_9876",
            "slug": "coffee-dev-prog",
            "url": "https://myscheme.gov.in/schemes/coffee-dev",
            "scheme_name": "Coffee Development Programme",
            "category": "Agriculture",
            "sub_category": "Agricultural Inputs",
            "level": "Central",
            "beneficiary_state": "All",
            "nodal_ministry": "Ministry of Commerce",
            "brief_description": "Promotes coffee cultivation",
            "detailed_description": "Full details on coffee subsidies",
            "dbt_scheme": True,
            "target_beneficiaries": "Tribal farmers",
            "documents_required": "Land deed, Aadhaar card",
            "faqs": "Q: Who can apply? A: Tribal growers."
        }

        normalized = self.model.normalize_record("myscheme", sample_myscheme)

        self.assertEqual(normalized["source"], "myscheme")
        self.assertEqual(normalized["source_id"], "myscheme_9876")
        self.assertEqual(normalized["scheme_name"], "Coffee Development Programme")
        self.assertEqual(normalized["state"], "All")
        self.assertEqual(normalized["nodal_ministry"], "Ministry of Commerce")

        # Dynamic extra fields
        extras = normalized["extra_fields"]
        self.assertIn("dbt_scheme", extras)
        self.assertEqual(extras["dbt_scheme"], True)
        self.assertIn("target_beneficiaries", extras)
        self.assertEqual(extras["target_beneficiaries"], "Tribal farmers")
        self.assertIn("documents_required", extras)
        self.assertIn("faqs", extras)

    def test_future_scraper_arbitrary_fields(self):
        """
        Tests ingestion of a completely new, hypothetical FUTURE scraper
        with unannounced fields like subsidy_rate, annual_turnover_ceiling, etc.
        """
        future_record = {
            "portal_code": "KA_STARTUP_2026",
            "title": "Karnataka Elevate 2026 Innovation Scheme",
            "web_link": "https://missionstartup.karnataka.gov.in",
            "summary": "State seed fund for deep tech startups",
            "state_name": "Karnataka",
            # Brand new, future fields:
            "subsidy_percentage": 75.5,
            "annual_turnover_ceiling": 50000000,
            "patent_mandate": True,
            "districts_covered": ["Bangalore Urban", "Mysore", "Hubli"],
            "nodal_officer_email": "director@karnataka.gov.in",
            "scoring_matrix": {"innovation": 40, "viability": 30, "social_impact": 30}
        }

        normalized = self.model.normalize_record("karnataka_portal", future_record)

        # Core fields auto-resolved by aliases
        self.assertEqual(normalized["source"], "karnataka_portal")
        self.assertEqual(normalized["source_id"], "KA_STARTUP_2026")
        self.assertEqual(normalized["scheme_name"], "Karnataka Elevate 2026 Innovation Scheme")
        self.assertEqual(normalized["source_url"], "https://missionstartup.karnataka.gov.in")
        self.assertEqual(normalized["brief_description"], "State seed fund for deep tech startups")
        self.assertEqual(normalized["state"], "Karnataka")

        # All future fields isolated into extra_fields
        extras = normalized["extra_fields"]
        self.assertEqual(extras["subsidy_percentage"], 75.5)
        self.assertEqual(extras["annual_turnover_ceiling"], 50000000)
        self.assertEqual(extras["patent_mandate"], True)
        self.assertEqual(extras["districts_covered"], ["Bangalore Urban", "Mysore", "Hubli"])
        self.assertEqual(extras["nodal_officer_email"], "director@karnataka.gov.in")
        self.assertIsInstance(extras["scoring_matrix"], dict)

        # Test EAV conversion for future fields
        eav = self.model.extract_eav_attributes(scheme_id=999, source="karnataka_portal", extra_fields=extras)
        eav_keys = {item["attribute_key"]: item for item in eav}

        self.assertIn("subsidy_percentage", eav_keys)
        self.assertEqual(eav_keys["subsidy_percentage"]["data_type"], "number")
        self.assertIn("patent_mandate", eav_keys)
        self.assertEqual(eav_keys["patent_mandate"]["data_type"], "boolean")
        self.assertIn("districts_covered", eav_keys)
        self.assertEqual(eav_keys["districts_covered"]["data_type"], "list")
        self.assertIn("scoring_matrix", eav_keys)
        self.assertEqual(eav_keys["scoring_matrix"]["data_type"], "json")

    def test_change_detection_hash(self):
        """Verifies SHA-256 change detection for duplicate vs updated records."""
        rec_v1 = {"id": "1", "name": "Scheme A", "desc": "Original"}
        rec_v2 = {"id": "1", "name": "Scheme A", "desc": "Original"}
        rec_v3 = {"id": "1", "name": "Scheme A", "desc": "Modified Description"}

        norm1 = self.model.normalize_record("src", rec_v1)
        norm2 = self.model.normalize_record("src", rec_v2)
        norm3 = self.model.normalize_record("src", rec_v3)

        self.assertEqual(norm1["data_hash"], norm2["data_hash"])
        self.assertNotEqual(norm1["data_hash"], norm3["data_hash"])

    def test_column_sanitization_and_type_inference(self):
        """Tests column name cleaning and MySQL data type inference."""
        self.assertEqual(self.model.sanitize_column_name("investment_size ($)"), "investment_size____")
        self.assertEqual(self.model.sanitize_column_name("1st_installment"), "col_1st_installment")

        self.assertEqual(self.model.infer_mysql_column_type(True), "TINYINT(1)")
        self.assertEqual(self.model.infer_mysql_column_type(12345), "BIGINT")
        self.assertEqual(self.model.infer_mysql_column_type(99.9), "DOUBLE")
        self.assertEqual(self.model.infer_mysql_column_type({"a": 1}), "JSON")
        self.assertEqual(self.model.infer_mysql_column_type(["x", "y"]), "JSON")
        self.assertEqual(self.model.infer_mysql_column_type("short"), "VARCHAR(255)")
        self.assertEqual(self.model.infer_mysql_column_type("a" * 300), "MEDIUMTEXT")


class TestSchedulerRegistry(unittest.TestCase):
    """Tests scheduler extensibility and custom scraper registration."""

    def test_custom_scraper_registration(self):
        def dummy_scraper():
            return [{"id": "d1", "name": "Dummy Scheme", "custom_tag": "test"}]

        register_scraper("custom_test_source", dummy_scraper)
        self.assertIn("custom_test_source", CUSTOM_SCRAPERS)
        self.assertEqual(CUSTOM_SCRAPERS["custom_test_source"](), [{"id": "d1", "name": "Dummy Scheme", "custom_tag": "test"}])


from unittest.mock import MagicMock, patch
from db.repository import SchemeRepository


class TestRepositoryOffline(unittest.TestCase):
    """Tests SchemeRepository MySQL persistence logic using mocks (no live DB connection needed)."""

    def setUp(self):
        self.repo = SchemeRepository()
        self.repo.model.auto_evolve = False

    @patch("db.repository.db_manager.get_connection")
    def test_save_scheme_insert(self, mock_get_conn):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_get_conn.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur

        # Record does not exist
        mock_cur.fetchone.return_value = None
        mock_cur.lastrowid = 101

        sample = {"id": "scheme_abc", "name": "Test Scheme", "category": "Tech"}
        scheme_id, status = self.repo.save_scheme("unit_test", sample)

        self.assertEqual(scheme_id, 101)
        self.assertEqual(status, "INSERTED")
        # Verify an INSERT INTO `grant_scheme` query was executed
        executed_sqls = [call[0][0] for call in mock_cur.execute.call_args_list]
        self.assertTrue(any("INSERT INTO `grant_scheme`" in sql for sql in executed_sqls))

    @patch("db.repository.db_manager.get_connection")
    def test_save_scheme_unchanged(self, mock_get_conn):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_get_conn.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur

        sample = {"id": "scheme_abc", "name": "Test Scheme"}
        norm = self.repo.model.normalize_record("unit_test", sample)

        # Record exists with identical hash
        mock_cur.fetchone.return_value = {"id": 101, "data_hash": norm["data_hash"]}

        scheme_id, status = self.repo.save_scheme("unit_test", sample)
        self.assertEqual(scheme_id, 101)
        self.assertEqual(status, "UNCHANGED")

    @patch("db.repository.db_manager.get_connection")
    def test_save_scheme_updated(self, mock_get_conn):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_get_conn.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur

        sample = {"id": "scheme_abc", "name": "Test Scheme Updated"}

        # Record exists with different hash
        mock_cur.fetchone.return_value = {"id": 101, "data_hash": "old_outdated_hash_value"}

        scheme_id, status = self.repo.save_scheme("unit_test", sample)
        self.assertEqual(scheme_id, 101)
        self.assertEqual(status, "UPDATED")
        executed_sqls = [call[0][0] for call in mock_cur.execute.call_args_list]
        self.assertTrue(any("UPDATE `grant_scheme` SET" in sql for sql in executed_sqls))

    @patch("db.repository.db_manager.get_connection")
    def test_soft_delete_and_restore(self, mock_get_conn):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_get_conn.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_cur.rowcount = 1

        self.assertTrue(self.repo.soft_delete_scheme(101))
        # Verify UPDATE with `deleted_at` = NOW() was executed
        self.assertTrue(any("deleted_at" in call[0][0] and "NOW()" in call[0][0] for call in mock_cur.execute.call_args_list))

        self.assertTrue(self.repo.restore_scheme(101))
        # Verify UPDATE with `deleted_at` = NULL was executed
        self.assertTrue(any("deleted_at" in call[0][0] and "NULL" in call[0][0] for call in mock_cur.execute.call_args_list))

    def test_deleted_at_in_core_columns(self):
        self.assertIn("deleted_at", self.repo.model.CORE_COLUMNS)

    @patch("db.repository.db_manager.get_connection")
    def test_soft_delete_missing_abandoned_schemes(self, mock_get_conn):
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_get_conn.return_value.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur

        # DB currently has s1, s2, and an abandoned scheme s3
        mock_cur.fetchall.return_value = [{"source_id": "s1"}, {"source_id": "s2"}, {"source_id": "s3"}]
        mock_cur.rowcount = 1

        # Current scrape only returned s1 and s2 (s3 was abandoned / no longer present)
        active_scraped_ids = {"s1", "s2"}
        deleted_count = self.repo.soft_delete_missing_schemes("test_source", active_scraped_ids)

        self.assertEqual(deleted_count, 1)
        # Verify UPDATE with deleted_at = NOW() was called for missing scheme s3
        update_calls = [c for c in mock_cur.execute.call_args_list if "deleted_at" in c[0][0] and "NOW()" in c[0][0]]
        self.assertTrue(len(update_calls) > 0)
        self.assertIn("s3", update_calls[0][0][1])

    @patch("db.repository.db_manager.get_connection")
    def test_soft_delete_missing_safety_guard(self, mock_get_conn):
        # Safeguard: if scraper returned 0 items due to error, do NOT soft delete all DB schemes
        deleted_count = self.repo.soft_delete_missing_schemes("test_source", set())
        self.assertEqual(deleted_count, 0)
        mock_get_conn.assert_not_called()


class TestSchedulerConfig(unittest.TestCase):
    """Tests scheduler timing parser and configuration."""

    def test_daily_hour_minute_parsing(self):
        original = Config.DAILY_RUN_TIME
        try:
            Config.DAILY_RUN_TIME = "04:30"
            h, m = Config.get_daily_hour_minute()
            self.assertEqual((h, m), (4, 30))

            Config.DAILY_RUN_TIME = "23:59"
            h, m = Config.get_daily_hour_minute()
            self.assertEqual((h, m), (23, 59))

            # Invalid fallback to (2, 0)
            Config.DAILY_RUN_TIME = "invalid_string"
            h, m = Config.get_daily_hour_minute()
            self.assertEqual((h, m), (2, 0))
        finally:
            Config.DAILY_RUN_TIME = original


if __name__ == "__main__":
    unittest.main()
