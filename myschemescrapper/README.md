# myScheme Portal Scraper (myscheme.gov.in)

A fast, robust, and full-featured scraper for the official Government of India welfare schemes portal ([myscheme.gov.in](https://www.myscheme.gov.in/)).

It extracts exhaustive details for schemes across **all 15 categories** (over **5,000+ schemes**), including overview, benefits, eligibility criteria, step-by-step application procedures, required documents, FAQs, and official reference links.

---

## ✨ Features

- **⚡ High-Performance Direct API Client**: Connects directly to the underlying REST API endpoints used by the Next.js frontend (`/api/apisetu/search/schemes` and `/api/apisetu/schemes`), completing queries in milliseconds without needing slow headless browsers.
- **📂 Comprehensive Data Extraction**:
  - **Basic Details**: Scheme Name, Short Title/Acronym, Level (Central/State), Ministry, Department, Implementing Agency, Category, Sub-Category, DBT Status, Applicable States, Target Beneficiaries, Tags.
  - **Content & Benefits**: Brief Description, Detailed Markdown Description, Benefits Breakdown, Exclusions.
  - **Eligibility**: Eligibility Criteria (parsed to Markdown).
  - **Application Process**: Step-by-step instructions for both Online and Offline modes.
  - **Required Documents**: Full checklist of mandatory and optional documents.
  - **FAQs**: Complete Question & Answer lists for citizen queries.
  - **Official Links**: Application portal links, guidelines PDFs, and department URLs.
- **🔄 Checkpoint & Resume**: Automatically creates a `checkpoint.jsonl` file. If a large scrape is stopped or disconnected, restarting the command will pick up exactly where it left off without duplicating network calls.
- **💾 Multiple Export Formats**:
  - **JSON**: Full structured fidelity.
  - **JSONL**: Streaming and big-data friendly line-delimited JSON.
  - **CSV**: Flattened tabular view for data science, analysis, and SQL imports.
  - **Excel (`.xlsx`)**: Auto-formatted spreadsheets with optimized column widths.
  - **Markdown Dossiers**: Individual human-readable `.md` dossiers with Markdown tables and headings for every scheme.
- **🚀 Concurrent Multithreading**: Configurable worker threads (`--workers`) with built-in polite delays (`--delay`) and automatic retry backoff.
- **🖥️ Dual Mode**: Rich Command-Line Interface (CLI) + Interactive Text Menu (`python main.py`).

---

## 📋 Available Categories & Counts

| # | Category Name | Scheme Count |
|---|---|---|
| 1 | `Social welfare & Empowerment` | 1,517 |
| 2 | `Education & Learning` | 1,177 |
| 3 | `Agriculture,Rural & Environment` | 927 |
| 4 | `Business & Entrepreneurship` | 829 |
| 5 | `Women and Child` | 479 |
| 6 | `Skills & Employment` | 407 |
| 7 | `Banking,Financial Services and Insurance` | 358 |
| 8 | `Sports & Culture` | 306 |
| 9 | `Health & Wellness` | 296 |
| 10 | `Housing & Shelter` | 145 |
| 11 | `Transport & Infrastructure` | 144 |
| 12 | `Science, IT & Communications` | 134 |
| 13 | `Travel & Tourism` | 104 |
| 14 | `Utility & Sanitation` | 60 |
| 15 | `Public Safety,Law & Justice` | 35 |
| **Total** | **Unique Schemes Platform-wide** | **~5,093+** |

---

## 🛠️ Installation

1. Ensure Python 3.8+ is installed.
2. Install the required dependencies:

```bash
pip install -r requirements.txt
```

---

## 🚀 Quick Start & CLI Usage

### 1. Interactive Menu
Simply run:
```bash
python main.py
```
This opens an interactive guide to choose categories, set limits, worker threads, and export formats.

---

### 2. Scrape `Agriculture,Rural & Environment`
To scrape all schemes for your specified category:

```bash
python main.py --category "Agriculture,Rural & Environment"
```

To run a test scrape on just the first 10 schemes:
```bash
python main.py --category "Agriculture,Rural & Environment" --limit 10
```

---

### 3. Scrape ALL Schemes Across ALL Categories (Consolidated Dataset)
Scrapes all unique schemes across the entire portal into a unified database:

```bash
python main.py --all --workers 8 --output data/all_schemes
```

---

### 4. Scrape All Categories Individually (Grouped into Folders)
Saves each category into its own folder with its respective JSON, CSV, Excel, and Markdown files:

```bash
python main.py --all-categories --workers 6 --output data/by_category
```

---

### 5. List All Categories and Live Scheme Counts
```bash
python main.py --list-categories
```

---

## ⚙️ CLI Options & Flags

| Flag | Short | Default | Description |
|---|---|---|---|
| `--category` | `-c` | `None` | Scrape a specific category (case-sensitive) |
| `--all` | | `False` | Scrape all unique schemes platform-wide in one dataset |
| `--all-categories` | | `False` | Scrape each category into separate directories |
| `--list-categories` | | `False` | Print table of categories with scheme counts |
| `--limit` | `-l` | `None` (All) | Maximum number of schemes to scrape |
| `--workers` | `-w` | `5` | Number of concurrent worker threads |
| `--delay` | `-d` | `0.1` | Delay in seconds between requests to ensure politeness |
| `--output` | `-o` | `data` | Output destination folder |
| `--format` | `-f` | `all` | Formats: `all` or comma-separated (`json,csv,excel,markdown`) |
| `--no-resume` | | `False` | Disables reading from previous `checkpoint.jsonl` |

---

## 🐍 Python API Usage

You can also import and use the scraper inside your own scripts:

```python
from scraper import MySchemeScraper

# Initialize scraper
scraper = MySchemeScraper(delay=0.1)

# 1. Fetch category list
categories = scraper.get_categories()
print(categories)

# 2. Scrape specific category
schemes = scraper.scrape_category(
    category_name="Agriculture,Rural & Environment",
    limit=50,
    max_workers=5,
    output_dir="data",
    formats=["json", "csv", "excel", "markdown"]
)

# 3. Lookup individual scheme by slug
scheme = scraper.fetch_scheme_details("rkvp")
print(scheme["scheme_name"])
print(scheme["eligibility_criteria"])
```

---

## 📊 Extracted Data Schema

| Field Name | Type | Description |
|---|---|---|
| `id` | String | Internal MongoDB Object ID |
| `slug` | String | URL identifier slug (e.g., `cdpnerec`) |
| `url` | String | Direct canonical URL on myscheme.gov.in |
| `scheme_name` | String | Full name of the welfare scheme |
| `scheme_short_title`| String | Short acronym or code |
| `category` | String | Scheme category |
| `sub_category` | String | Scheme sub-category classifications |
| `level` | String | `Central` or `State` |
| `beneficiary_state` | String | Targeted State(s) or `All` |
| `nodal_ministry` | String | Responsible Central Ministry |
| `nodal_department` | String | Responsible Department |
| `implementing_agency`| String | Implementing agency/body |
| `scheme_type` | String | Central Sector / Centrally Sponsored / State |
| `scheme_for` | String | Target entity (`Individual`, etc.) |
| `dbt_scheme` | Boolean| Whether Direct Benefit Transfer is enabled |
| `target_beneficiaries`| String | Specific beneficiary segments |
| `tags` | String | Associated search tags |
| `brief_description` | String | Summary overview |
| `detailed_description`| Markdown| In-depth description and background |
| `benefits` | Markdown| Financial, material, or service benefits |
| `eligibility_criteria`| Markdown| Eligibility conditions |
| `exclusions` | Markdown| Exclusions and restrictions |
| `application_process`| Markdown| Step-by-step application walkthrough (Online/Offline) |
| `documents_required`| Markdown| Checklist of required documents |
| `faqs` | Markdown| Frequently Asked Questions & Answers |
| `references` | List | Official links, guidelines PDFs, and portal URLs |

---

## 📁 Output Structure Example

```
data/
└── Agriculture,Rural & Environment/
    ├── Agriculture,Rural & Environment.json      # Complete JSON data
    ├── Agriculture,Rural & Environment.csv       # Flattened CSV
    ├── Agriculture,Rural & Environment.xlsx      # Formatted Excel sheet
    ├── checkpoint.jsonl                          # Resume checkpoint
    └── Agriculture,Rural & Environment_markdown/ # Individual dossiers
        ├── cdpnerec.md
        ├── rkvp.md
        └── ...
```
