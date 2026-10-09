"""
myScheme Scraper Command-Line Interface and Interactive Menu.
"""

import sys
import argparse
from typing import List
from scraper import MySchemeScraper


def print_banner():
    banner = r"""
  __  __       ____       _                          
 |  \/  |_   _/ ___|  ___| |__   ___ _ __ ___   ___  
 | |\/| | | | \___ \ / __| '_ \ / _ \ '_ ` _ \ / _ \ 
 | |  | | |_| |___) | (__| | | |  __/ | | | | |  __/ 
 |_|  |_|\__, |____/ \___|_| |_|\___|_| |_| |_|\___| 
         |___/                                        
  ===================================================
     Official Government Welfare Schemes Scraper
  ===================================================
"""
    print(banner)


def list_categories(scraper: MySchemeScraper):
    print("\nFetching current categories from myscheme.gov.in...")
    categories = scraper.get_categories()
    total_schemes = sum(c['count'] for c in categories)

    print("\n" + "=" * 65)
    print(f" {'#':<3} | {'Category Name':<45} | {'Schemes':>8}")
    print("=" * 65)
    for idx, cat in enumerate(categories, 1):
        print(f" {idx:<3} | {cat['name']:<45} | {cat['count']:>8}")
    print("=" * 65)
    print(f" Total Unique Categories: {len(categories)}")
    print(f" Total Categorized Scheme Listings: {total_schemes}")
    print("=" * 65 + "\n")
    return categories


def interactive_menu(scraper: MySchemeScraper):
    print_banner()
    categories = scraper.get_categories()

    while True:
        print("\nChoose an option:")
        print("  1. Scrape 'Agriculture,Rural & Environment'")
        print("  2. Select another category from list")
        print("  3. Scrape ALL schemes across all categories (Consolidated dataset)")
        print("  4. Scrape all categories into individual folders")
        print("  5. View all categories & scheme counts")
        print("  6. Exit")

        choice = input("\nEnter choice (1-6) [default: 1]: ").strip()
        if not choice:
            choice = "1"

        if choice == "6":
            print("Exiting.")
            sys.exit(0)

        if choice == "5":
            list_categories(scraper)
            continue

        # Common configuration options
        limit_str = input("Limit number of schemes (press Enter for ALL schemes, or enter e.g. 10): ").strip()
        limit = int(limit_str) if limit_str.isdigit() else None

        workers_str = input("Number of concurrent workers (default 5): ").strip()
        workers = int(workers_str) if workers_str.isdigit() else 5

        formats_str = input("Export formats (all / json,csv,excel,markdown) [default: all]: ").strip()
        formats = [x.strip() for x in formats_str.split(",")] if formats_str else ["all"]

        output_dir = input("Output folder [default: data]: ").strip()
        if not output_dir:
            output_dir = "data"

        if choice == "1":
            target_cat = "Agriculture,Rural & Environment"
            print(f"\nStarting scrape for '{target_cat}'...")
            scraper.scrape_category(
                category_name=target_cat,
                limit=limit,
                max_workers=workers,
                output_dir=output_dir,
                formats=formats
            )
            print("\nScraping complete!")
            break

        elif choice == "2":
            print("\nAvailable Categories:")
            for idx, c in enumerate(categories, 1):
                print(f"  {idx}. {c['name']} ({c['count']} schemes)")
            cat_idx_str = input("\nEnter category number: ").strip()
            if not cat_idx_str.isdigit() or not (1 <= int(cat_idx_str) <= len(categories)):
                print("Invalid selection.")
                continue
            selected_cat = categories[int(cat_idx_str) - 1]['name']
            print(f"\nStarting scrape for '{selected_cat}'...")
            scraper.scrape_category(
                category_name=selected_cat,
                limit=limit,
                max_workers=workers,
                output_dir=output_dir,
                formats=formats
            )
            print("\nScraping complete!")
            break

        elif choice == "3":
            print("\nStarting consolidated scrape for ALL schemes platform-wide...")
            scraper.scrape_all_schemes(
                limit=limit,
                max_workers=workers,
                output_dir=output_dir,
                formats=formats
            )
            print("\nScraping complete!")
            break

        elif choice == "4":
            print("\nStarting scrape for all categories individually...")
            scraper.scrape_all_categories(
                limit_per_category=limit,
                max_workers=workers,
                output_dir=output_dir,
                formats=formats
            )
            print("\nScraping complete!")
            break

        else:
            print("Invalid choice. Please choose 1-6.")


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="myScheme.gov.in Government Schemes Scraper CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List all categories and counts:
  python main.py --list-categories

  # Scrape 'Agriculture,Rural & Environment' category (all formats):
  python main.py --category "Agriculture,Rural & Environment"

  # Scrape first 10 schemes from Agriculture for testing:
  python main.py --category "Agriculture,Rural & Environment" --limit 10

  # Scrape ALL ~5,000 schemes across the portal with 8 threads:
  python main.py --all --workers 8 --output data/all_schemes

  # Scrape each category into separate folders:
  python main.py --all-categories --limit 20
        """
    )

    parser.add_argument("-c", "--category", type=str, help="Name of specific category to scrape")
    parser.add_argument("--all-categories", action="store_true", help="Scrape all categories into separate folders")
    parser.add_argument("--all", action="store_true", help="Scrape all unique schemes platform-wide into one dataset")
    parser.add_argument("--list-categories", action="store_true", help="List all categories and exit")
    parser.add_argument("-l", "--limit", type=int, default=None, help="Maximum number of schemes to scrape")
    parser.add_argument("-w", "--workers", type=int, default=5, help="Number of concurrent worker threads (default: 5)")
    parser.add_argument("-d", "--delay", type=float, default=0.1, help="Delay between requests in seconds (default: 0.1)")
    parser.add_argument("-o", "--output", type=str, default="data", help="Output directory path (default: data)")
    parser.add_argument("-f", "--format", type=str, default="all", help="Output formats: all, json, csv, excel, markdown (comma-separated)")
    parser.add_argument("--no-resume", action="store_true", help="Do not resume from checkpoint file; scrape from scratch")

    return parser.parse_args()


def main():
    args = parse_arguments()
    scraper = MySchemeScraper(delay=args.delay)

    formats = [x.strip() for x in args.format.split(",")]
    resume = not args.no_resume

    if args.list_categories:
        list_categories(scraper)
        return

    if args.category:
        print_banner()
        print(f"Scraping category: '{args.category}' (Limit: {args.limit or 'All'})")
        scraper.scrape_category(
            category_name=args.category,
            limit=args.limit,
            max_workers=args.workers,
            output_dir=args.output,
            formats=formats,
            resume=resume
        )
        return

    if args.all_categories:
        print_banner()
        print(f"Scraping all categories individually (Limit per cat: {args.limit or 'All'})")
        scraper.scrape_all_categories(
            limit_per_category=args.limit,
            max_workers=args.workers,
            output_dir=args.output,
            formats=formats,
            resume=resume
        )
        return

    if args.all:
        print_banner()
        print(f"Scraping ALL schemes platform-wide (Limit: {args.limit or 'All'})")
        scraper.scrape_all_schemes(
            limit=args.limit,
            max_workers=args.workers,
            output_dir=args.output,
            formats=formats,
            resume=resume
        )
        return

    # If no flags passed, launch interactive mode
    try:
        interactive_menu(scraper)
    except KeyboardInterrupt:
        print("\n\nOperation cancelled by user.")
        sys.exit(0)


if __name__ == "__main__":
    main()
