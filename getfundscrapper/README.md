# GetFunding Government Schemes Scraper

This tool extracts all government funding schemes and their comprehensive details from [GetFunding](https://getfunding.co.in/government-schemes).

---

## 📁 Generated Files

| File | Description | Records |
| :--- | :--- | :--- |
| [`schemes_details.json`](file:///d:/getfundscrapper/schemes_details.json) | Complete dataset in formatted JSON with all 36 attributes | 147 |
| [`schemes_details.csv`](file:///d:/getfundscrapper/schemes_details.csv) | Full tabular CSV file with UTF-8 BOM (compatible with Excel & Pandas) | 147 |
| [`schemes_details.xlsx`](file:///d:/getfundscrapper/schemes_details.xlsx) | Auto-formatted Excel workbook with column auto-widths | 147 |
| [`scraper.py`](file:///d:/getfundscrapper/scraper.py) | Standalone Python scraper script with multithreading and retry handling | - |

---

## 📊 Extracted Data Fields (36 Columns)

- **Identification:** `sid`, `unique_id`, `name`, `full_name`, `slug`
- **Categorization:** `scheme_type` (Central, State, CGPS Undertaking), `state`, `startup_category`, `startup_industry`, `stage`, `reservation`
- **Funding & Financials:** `fund_type` (Grant, Loan, Equity, Subsidy, etc.), `investment_size`
- **Operational Status:** `functioning_status`, `application_open`
- **Core Scheme Content:**
  - `about`
  - `description`
  - `who_can_apply`
  - `eligibility_criteria`
  - `application_process`
- **Official Links & Documents:**
  - `website`
  - `scheme_guidelines`
  - `registration_guidelines`
  - `relevant_links`
- **Contact & Incubation:**
  - `contact_details`
  - `email`
  - `phone_no`
  - `incubators_list`
  - `thrust_areas`
- **Media & Metadata:**
  - `logo`, `image`, `instagram_url`, `youtube_link`
  - `creation_date`, `modified_date`, `creator`

---

## 🚀 How to Re-run the Scraper

To fetch updated data at any time:

```bash
python scraper.py
```
