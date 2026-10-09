"""
GetFunding Government Schemes Scraper
Scrapes all government schemes details from https://getfunding.co.in/government-schemes
Saves output to JSON, CSV, and Excel formats.
"""

import sys
import time
import json
import logging
from typing import Dict, Any, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
import pandas as pd
from tqdm import tqdm

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("GetFundingScraper")

BASE_API_URL = "https://api.getfunding.co.in/api/government-schemes"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://getfunding.co.in/government-schemes",
    "Origin": "https://getfunding.co.in"
}


def create_session() -> requests.Session:
    """Create a requests session with retry strategy and connection pooling."""
    session = requests.Session()
    retries = Retry(
        total=5,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        raise_on_status=False
    )
    adapter = HTTPAdapter(max_retries=retries, pool_connections=20, pool_maxsize=20)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update(HEADERS)
    return session


def clean_text(text: Any) -> Any:
    """Clean whitespace, zero-width characters, and fix protocol-relative links."""
    if not isinstance(text, str):
        return text
    text = text.replace("\u200b", "").replace("\ufeff", "")
    text = text.strip()
    return text


def clean_url(url: Any) -> str:
    """Format and normalize image / link URLs."""
    if not isinstance(url, str) or not url.strip():
        return ""
    url = url.strip()
    if url.startswith("//"):
        return f"https:{url}"
    return url


def fetch_all_schemes_list(session: requests.Session) -> List[Dict[str, Any]]:
    """Fetch the master list of all government schemes."""
    logger.info("Fetching schemes list from %s...", BASE_API_URL)
    resp = session.get(BASE_API_URL, timeout=30)
    resp.raise_for_status()
    payload = resp.json()

    if payload.get("status") != "SUCCESS":
        raise ValueError(f"API returned non-success status: {payload.get('status')}")

    data = payload.get("data", {})
    total = data.get("total", 0)
    items = data.get("items", [])
    logger.info("Found %d total schemes reported by API (received %d items).", total, len(items))
    return items


def fetch_scheme_detail(session: requests.Session, item: Dict[str, Any]) -> Dict[str, Any]:
    """Fetch comprehensive details for an individual scheme using its unique_id."""
    unique_id = item.get("unique_id")
    name = item.get("name", "Unknown")

    if not unique_id:
        logger.warning("No unique_id found for %s, using listing data", name)
        return item

    detail_url = f"{BASE_API_URL}/{unique_id}"
    try:
        resp = session.get(detail_url, timeout=30)
        if resp.status_code == 200:
            payload = resp.json()
            if payload.get("status") == "SUCCESS" and payload.get("data"):
                detail_data = payload["data"]
                # Merge: detail_data overrides item, keeping any extra attributes
                merged = {**item, **detail_data}
                return merged
            else:
                logger.warning("Failed payload for '%s' (%s): %s", name, unique_id, payload)
        else:
            logger.warning("HTTP %d for '%s' (%s)", resp.status_code, name, unique_id)
    except Exception as e:
        logger.error("Error fetching details for '%s' (%s): %s", name, unique_id, e)

    # Fallback to list item data if detail call failed
    return item


def normalize_record(rec: Dict[str, Any]) -> Dict[str, Any]:
    """Clean all fields and ensure consistent keys in the record."""
    cleaned = {}
    for k, v in rec.items():
        if isinstance(v, str):
            v_clean = clean_text(v)
            if k in ("logo", "image", "website", "scheme_guidelines", "registration_guidelines"):
                v_clean = clean_url(v_clean)
            cleaned[k] = v_clean
        else:
            cleaned[k] = v

    # Order preferred fields for logical readability
    primary_order = [
        "sid",
        "unique_id",
        "name",
        "full_name",
        "scheme_type",
        "state",
        "fund_type",
        "investment_size",
        "stage",
        "startup_category",
        "startup_industry",
        "functioning_status",
        "application_open",
        "reservation",
        "about",
        "description",
        "who_can_apply",
        "eligibility_criteria",
        "application_process",
        "scheme_guidelines",
        "registration_guidelines",
        "website",
        "relevant_links",
        "incubators_list",
        "thrust_areas",
        "contact_details",
        "email",
        "phone_no",
        "logo",
        "image",
        "instagram_url",
        "youtube_link",
        "creation_date",
        "modified_date",
        "creator",
        "slug"
    ]

    ordered = {}
    for k in primary_order:
        if k in cleaned:
            ordered[k] = cleaned[k]
    for k, v in cleaned.items():
        if k not in ordered:
            ordered[k] = v

    return ordered


def scrape_all_schemes(max_workers: int = 10) -> List[Dict[str, Any]]:
    """Fetch list of all schemes and scrape detailed information for each."""
    session = create_session()
    raw_items = fetch_all_schemes_list(session)

    results: List[Dict[str, Any]] = []
    logger.info("Fetching details for all %d schemes using %d threads...", len(raw_items), max_workers)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_item = {
            executor.submit(fetch_scheme_detail, session, item): item
            for item in raw_items
        }

        with tqdm(total=len(raw_items), desc="Scraping schemes", unit="scheme") as pbar:
            for future in as_completed(future_to_item):
                item = future_to_item[future]
                try:
                    detail = future.result()
                    normalized = normalize_record(detail)
                    results.append(normalized)
                except Exception as e:
                    logger.error("Exception processing item %s: %s", item.get("name"), e)
                    results.append(normalize_record(item))
                finally:
                    pbar.update(1)

    # Sort results by sid (or name if sid is null)
    results.sort(key=lambda x: (x.get("sid") is None, x.get("sid") or 0, x.get("name") or ""))
    return results


def save_data(data: List[Dict[str, Any]], base_filename: str = "schemes_details") -> None:
    """Save scraped data to JSON, CSV, and Excel."""
    json_path = f"{base_filename}.json"
    csv_path = f"{base_filename}.csv"
    xlsx_path = f"{base_filename}.xlsx"

    logger.info("Saving JSON to %s...", json_path)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    logger.info("Saving CSV and Excel to %s and %s...", csv_path, xlsx_path)
    df = pd.DataFrame(data)

    df.to_csv(csv_path, index=False, encoding="utf-8-sig")

    try:
        with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Government Schemes")
            worksheet = writer.sheets["Government Schemes"]
            # Auto-adjust column widths
            for col in worksheet.columns:
                max_len = 0
                col_letter = col[0].column_letter
                for cell in col:
                    val = str(cell.value or "")
                    if len(val) > max_len:
                        max_len = len(val)
                worksheet.column_dimensions[col_letter].width = min(max(max_len + 2, 12), 50)
    except Exception as e:
        logger.warning("Could not auto-format Excel worksheet columns: %s", e)
        df.to_excel(xlsx_path, index=False, sheet_name="Government Schemes")

    logger.info("Successfully exported all files!")


def print_summary(data: List[Dict[str, Any]]) -> None:
    """Print high-level statistics of the scraped dataset."""
    df = pd.DataFrame(data)
    print("\n" + "=" * 60)
    print("SCRAPING COMPLETED SUCCESSFULLY")
    print("=" * 60)
    print(f"Total schemes scraped: {len(df)}")
    
    if "scheme_type" in df.columns:
        print("\nBreakdown by Scheme Type:")
        print(df["scheme_type"].value_counts().to_string())

    if "fund_type" in df.columns:
        print("\nBreakdown by Fund Type:")
        print(df["fund_type"].value_counts().to_string())

    if "state" in df.columns:
        state_counts = df[df["state"].str.strip() != ""]["state"].value_counts()
        if not state_counts.empty:
            print(f"\nState-Specific Schemes ({len(state_counts)} States/UTs):")
            print(state_counts.head(10).to_string())

    print("\nOutput Files Created:")
    print(" - schemes_details.json (Complete structured JSON)")
    print(" - schemes_details.csv  (Tabular CSV with UTF-8 BOM)")
    print(" - schemes_details.xlsx (Formatted Excel spreadsheet)")
    print("=" * 60 + "\n")


def main():
    start_time = time.time()
    logger.info("Starting GetFunding government schemes scraper...")
    schemes = scrape_all_schemes(max_workers=10)
    save_data(schemes)
    print_summary(schemes)
    elapsed = round(time.time() - start_time, 2)
    logger.info("Done in %s seconds.", elapsed)


if __name__ == "__main__":
    main()
