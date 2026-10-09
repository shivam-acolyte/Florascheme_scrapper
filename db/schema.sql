-- =============================================================================
-- FloraScheme MySQL Schema
-- STRICT REQUIREMENT: Only MySQL 5.7+ / 8.0+ supported
-- Character set: utf8mb4 (supports Indian languages & emojis)
-- =============================================================================
-- Note: Target database is dynamically managed via MYSQL_DATABASE in .env
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. Grant Scheme Table (Unified Scheme Model with Dynamic Fields & Soft Deletes)
-- Stores canonical attributes + dynamic JSON + auto-evolved columns + deleted_at
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `grant_scheme` (
    `id` BIGINT AUTO_INCREMENT PRIMARY KEY,
    `source` VARCHAR(64) NOT NULL COMMENT 'Identifier of scraper source (e.g. getfunding, myscheme, future_portal)',
    `source_id` VARCHAR(255) NOT NULL COMMENT 'Unique identifier provided by the source portal',
    `slug` VARCHAR(255) NULL COMMENT 'URL slug if available',
    `scheme_name` VARCHAR(500) NOT NULL COMMENT 'Standardized title / name of the scheme',
    `scheme_short_title` VARCHAR(255) NULL COMMENT 'Short acronym or abbreviation',
    `source_url` VARCHAR(1000) NULL COMMENT 'Direct link to scheme on portal',
    `category` VARCHAR(500) NULL COMMENT 'Primary category',
    `sub_category` MEDIUMTEXT NULL COMMENT 'Sub category or sector',
    `level` VARCHAR(100) NULL COMMENT 'Jurisdiction level: Central, State, UT, District',
    `state` VARCHAR(500) NULL COMMENT 'Target state / UT or All',
    `scheme_type` VARCHAR(255) NULL COMMENT 'Central Sector, Centrally Sponsored, State Scheme, etc.',
    `nodal_ministry` VARCHAR(500) NULL COMMENT 'Ministry in charge',
    `nodal_department` VARCHAR(500) NULL COMMENT 'Department in charge',
    `brief_description` MEDIUMTEXT NULL COMMENT 'Summary / about snippet',
    `detailed_description` LONGTEXT NULL COMMENT 'Comprehensive description in Markdown/HTML/Plaintext',
    `benefits` MEDIUMTEXT NULL COMMENT 'Financial or non-financial benefits',
    `eligibility_criteria` MEDIUMTEXT NULL COMMENT 'Eligibility rules and requirements',
    `application_process` MEDIUMTEXT NULL COMMENT 'How to apply / process steps',
    
    -- Dynamic & Future-Proofing Fields
    `raw_data` JSON NOT NULL COMMENT 'Full unaltered raw payload from the scraper (lossless)',
    `extra_fields` JSON NOT NULL COMMENT 'Scraper-specific & dynamic fields not covered by core columns',
    `data_hash` VARCHAR(64) NOT NULL COMMENT 'SHA-256 hash of payload for change detection',
    
    -- Timestamps & Soft Deletion
    `scraped_at` DATETIME NOT NULL COMMENT 'Timestamp when scraped',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    `deleted_at` DATETIME NULL DEFAULT NULL COMMENT 'Timestamp when soft deleted',

    -- Constraints & Indexes
    UNIQUE KEY `uq_source_record` (`source`, `source_id`),
    INDEX `idx_source` (`source`),
    INDEX `idx_category` (`category`(191)),
    INDEX `idx_state` (`state`(191)),
    INDEX `idx_scheme_type` (`scheme_type`),
    INDEX `idx_created_at` (`created_at`),
    INDEX `idx_updated_at` (`updated_at`),
    INDEX `idx_deleted_at` (`deleted_at`),
    FULLTEXT KEY `ft_scheme_search` (`scheme_name`, `brief_description`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- -----------------------------------------------------------------------------
-- 2. Scheme Scrapper Registry & Audit
-- Tracks registered scrapers, schedule, execution status, and last run metrics
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `scheme_scrapper` (
    `id` INT AUTO_INCREMENT PRIMARY KEY,
    `source_name` VARCHAR(64) UNIQUE NOT NULL,
    `display_name` VARCHAR(255) NOT NULL,
    `is_active` BOOLEAN NOT NULL DEFAULT TRUE,
    `schedule_cron` VARCHAR(64) DEFAULT '0 2 * * *',
    `last_run_at` DATETIME NULL,
    `last_status` VARCHAR(32) DEFAULT 'PENDING' COMMENT 'PENDING, RUNNING, SUCCESS, FAILED',
    `total_schemes_count` INT NOT NULL DEFAULT 0,
    `last_duration_seconds` FLOAT NOT NULL DEFAULT 0,
    `last_inserted_count` INT NOT NULL DEFAULT 0,
    `last_updated_count` INT NOT NULL DEFAULT 0,
    `last_unchanged_count` INT NOT NULL DEFAULT 0,
    `last_soft_deleted_count` INT NOT NULL DEFAULT 0,
    `last_failed_count` INT NOT NULL DEFAULT 0,
    `last_error_message` TEXT NULL,
    `metadata` JSON NULL,
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Initialize default scrapers
INSERT INTO `scheme_scrapper` (`source_name`, `display_name`, `is_active`)
VALUES 
    ('getfunding', 'GetFunding Government Schemes Portal', TRUE),
    ('myscheme', 'myScheme.gov.in Official Welfare Schemes', TRUE)
ON DUPLICATE KEY UPDATE `display_name` = VALUES(`display_name`);
