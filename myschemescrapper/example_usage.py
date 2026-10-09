"""
Quick Example: Using the myScheme Scraper as a Python module
"""

from scraper import MySchemeScraper

def main():
    # Initialize scraper
    scraper = MySchemeScraper(delay=0.1)

    # 1. Fetch available categories
    print("--- 1. Listing Categories ---")
    categories = scraper.get_categories()
    for cat in categories:
        print(f"  • {cat['name']}: {cat['count']} schemes")

    # 2. Scrape a specific category (e.g. 5 schemes for quick demo)
    print("\n--- 2. Scraping sample schemes from 'Agriculture,Rural & Environment' ---")
    scraper.scrape_category(
        category_name="Agriculture,Rural & Environment",
        limit=5,
        max_workers=3,
        output_dir="sample_data",
        formats=["json", "csv", "excel", "markdown"]
    )

    # 3. Fetch single scheme details directly
    print("\n--- 3. Direct Scheme Lookup by Slug ('cdpnerec') ---")
    scheme = scraper.fetch_scheme_details("cdpnerec")
    if scheme:
        print(f"Scheme Name : {scheme['scheme_name']}")
        print(f"Ministry    : {scheme['nodal_ministry']}")
        print(f"Level       : {scheme['level']}")
        print(f"DBT Scheme  : {scheme['dbt_scheme']}")
        print(f"URL         : {scheme['url']}")

if __name__ == "__main__":
    main()
