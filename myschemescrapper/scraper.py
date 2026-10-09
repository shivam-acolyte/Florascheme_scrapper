"""
MyScheme Scraper Core Module
Handles network requests, pagination, concurrency, checkpointing, and details extraction.
"""

import os
import time
import json
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Any, List, Optional
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from tqdm import tqdm

from utils import (
    unescape_text,
    slate_node_to_markdown,
    extract_label,
    sanitize_filename,
    export_data
)


class MySchemeScraper:
    BASE_URL = "https://www.myscheme.gov.in"
    API_SEARCH = f"{BASE_URL}/api/apisetu/search/schemes"
    API_SCHEME = f"{BASE_URL}/api/apisetu/schemes"

    def __init__(self, delay: float = 0.1, timeout: int = 20, max_retries: int = 4):
        self.delay = delay
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": f"{self.BASE_URL}/",
        })

        retries = Retry(
            total=max_retries,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            raise_on_status=False
        )
        adapter = HTTPAdapter(max_retries=retries, pool_connections=25, pool_maxsize=25)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def get_categories(self) -> List[Dict[str, Any]]:
        """
        Dynamically fetches all available scheme categories and their total counts.
        """
        params = {
            "lang": "en",
            "q": "[]",
            "keyword": "",
            "sort": "",
            "from": 0,
            "size": 1
        }
        res = self.session.get(self.API_SEARCH, params=params, timeout=self.timeout)
        res.raise_for_status()
        data = res.json().get('data', {})
        facets = data.get('facets', [])

        categories = []
        for facet in facets:
            if facet.get('identifier') == 'schemeCategory':
                for entry in facet.get('entries', []):
                    categories.append({
                        "name": entry.get('label'),
                        "count": entry.get('count')
                    })
        return categories

    def fetch_scheme_list(self, category: Optional[str] = None, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Paginates through search results to collect all matching schemes' metadata and slugs.
        """
        items: List[Dict[str, Any]] = []
        page_size = 100
        offset = 0

        # Construct query filter
        q_filter = []
        if category:
            q_filter.append({"identifier": "schemeCategory", "value": category})
        q_param = json.dumps(q_filter)

        # First request to get total count
        params = {
            "lang": "en",
            "q": q_param,
            "keyword": "",
            "sort": "",
            "from": offset,
            "size": page_size
        }

        res = self.session.get(self.API_SEARCH, params=params, timeout=self.timeout)
        res.raise_for_status()
        data = res.json().get('data', {})
        total_available = data.get('summary', {}).get('total', 0)

        target_total = min(limit, total_available) if limit is not None else total_available
        cat_display = f"'{category}'" if category else "All Categories"
        print(f"[List] Found {total_available} total schemes for {cat_display}. Fetching {target_total} items...")

        first_items = data.get('hits', {}).get('items', [])
        items.extend(first_items)

        with tqdm(total=target_total, desc="Fetching Scheme List", unit="scheme") as pbar:
            pbar.update(min(len(first_items), target_total))

            while len(items) < target_total:
                offset += page_size
                if offset >= total_available:
                    break

                batch_size = min(page_size, target_total - len(items))
                params["from"] = offset
                params["size"] = batch_size

                time.sleep(self.delay)
                try:
                    res = self.session.get(self.API_SEARCH, params=params, timeout=self.timeout)
                    if res.status_code != 200:
                        print(f"\n[Warning] Batch at offset {offset} failed with status {res.status_code}")
                        break
                    batch_data = res.json().get('data', {}).get('hits', {}).get('items', [])
                    if not batch_data:
                        break
                    items.extend(batch_data)
                    pbar.update(len(batch_data))
                except Exception as e:
                    print(f"\n[Error] Exception during pagination at offset {offset}: {e}")
                    break

        return items[:target_total]

    def fetch_scheme_details(self, slug: str, summary_fields: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """
        Fetches full scheme details: basic info, eligibility, benefits, application process, documents, FAQs.
        """
        if summary_fields is None:
            summary_fields = {}

        # 1. Main Scheme Info
        scheme_url = f"{self.API_SCHEME}?slug={slug}&lang=en"
        try:
            r = self.session.get(scheme_url, timeout=self.timeout)
            if r.status_code != 200:
                return None
            res_json = r.json()
            if not isinstance(res_json, dict):
                return None
            raw_data = res_json.get('data') or {}
            if not isinstance(raw_data, dict) or not raw_data:
                return None
        except Exception:
            return None

        scheme_id = raw_data.get('_id')
        en = raw_data.get('en') or {}
        basic = en.get('basicDetails') or {}
        content = en.get('schemeContent') or {}
        eligibility = en.get('eligibilityCriteria') or {}
        app_proc = en.get('applicationProcess') or []

        # Parse application process
        app_proc_texts = []
        for proc in app_proc:
            mode = proc.get('mode', 'General')
            steps = []
            for block in proc.get('process', []):
                rendered = slate_node_to_markdown(block)
                if rendered.strip():
                    steps.append(rendered.strip())
            if steps:
                app_proc_texts.append(f"### Mode: {mode}\n\n" + "\n\n".join(steps))

        # 2. Documents
        docs_text = ""
        if scheme_id:
            try:
                time.sleep(self.delay / 2)
                doc_url = f"{self.API_SCHEME}/{scheme_id}/documents?lang=en"
                r_doc = self.session.get(doc_url, timeout=self.timeout)
                if r_doc.status_code == 200:
                    doc_json = r_doc.json()
                    doc_data = (doc_json.get('data') or {}) if isinstance(doc_json, dict) else {}
                    doc_en = doc_data.get('en') or {}
                    docs_text = unescape_text(doc_en.get('documentsRequired_md', ''))
            except Exception:
                pass

        # 3. FAQs
        faqs_list = []
        if scheme_id:
            try:
                time.sleep(self.delay / 2)
                faq_url = f"{self.API_SCHEME}/{scheme_id}/faqs?lang=en"
                r_faq = self.session.get(faq_url, timeout=self.timeout)
                if r_faq.status_code == 200:
                    faq_json = r_faq.json()
                    faq_data = (faq_json.get('data') or {}) if isinstance(faq_json, dict) else {}
                    faq_items = (faq_data.get('en') or {}).get('faqs') or []
                    for item in faq_items:
                        if isinstance(item, dict):
                            q = unescape_text(item.get('question', ''))
                            a = unescape_text(item.get('answer_md', ''))
                            if q:
                                faqs_list.append(f"**Q: {q}**\n\nA: {a}")
            except Exception:
                pass

        # Beneficiary states: fallback to summary fields if not in basicDetails
        states = basic.get('beneficiaryState') or summary_fields.get('beneficiaryState')

        record = {
            "id": scheme_id or summary_fields.get('id', ''),
            "slug": slug,
            "url": f"{self.BASE_URL}/schemes/{slug}",
            "scheme_name": unescape_text(basic.get('schemeName') or summary_fields.get('schemeName', '')),
            "scheme_short_title": unescape_text(basic.get('schemeShortTitle') or summary_fields.get('schemeShortTitle', '')),
            "category": extract_label(basic.get('schemeCategory') or summary_fields.get('schemeCategory')),
            "sub_category": extract_label(basic.get('schemeSubCategory')),
            "level": extract_label(basic.get('level') or summary_fields.get('level')),
            "beneficiary_state": extract_label(states),
            "nodal_ministry": extract_label(basic.get('nodalMinistryName') or summary_fields.get('nodalMinistryName')),
            "nodal_department": extract_label(basic.get('nodalDepartmentName')),
            "implementing_agency": extract_label(basic.get('implementingAgency')),
            "scheme_type": extract_label(basic.get('schemeType')),
            "scheme_for": extract_label(basic.get('schemeFor') or summary_fields.get('schemeFor')),
            "dbt_scheme": basic.get('dbtScheme'),
            "target_beneficiaries": extract_label(basic.get('targetBeneficiaries')),
            "scheme_open_date": basic.get('schemeOpenDate'),
            "scheme_close_date": basic.get('schemeCloseDate') or summary_fields.get('schemeCloseDate'),
            "tags": extract_label(basic.get('tags') or summary_fields.get('tags')),
            "brief_description": unescape_text(content.get('briefDescription') or summary_fields.get('briefDescription', '')),
            "detailed_description": unescape_text(content.get('detailedDescription_md', '')),
            "benefits": unescape_text(content.get('benefits_md', '')),
            "eligibility_criteria": unescape_text(eligibility.get('eligibilityDescription_md', '')),
            "exclusions": unescape_text(content.get('exclusions_md', '')),
            "application_process": "\n\n".join(app_proc_texts),
            "documents_required": docs_text,
            "faqs": "\n\n---\n\n".join(faqs_list),
            "references": [
                ref.get('url') for ref in content.get('references', [])
                if isinstance(ref, dict) and ref.get('url')
            ],
            "scheme_image_url": content.get('schemeImageUrl')
        }
        return record

    def scrape_schemes(
        self,
        scheme_list: List[Dict[str, Any]],
        max_workers: int = 5,
        checkpoint_path: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Concurrently scrapes details for each scheme item with automatic progress and checkpointing.
        """
        results: Dict[str, Dict[str, Any]] = {}

        # Load existing checkpoint if available
        if checkpoint_path and os.path.exists(checkpoint_path):
            try:
                with open(checkpoint_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.strip():
                            rec = json.loads(line)
                            if 'slug' in rec:
                                results[rec['slug']] = rec
                print(f"[Checkpoint] Resumed {len(results)} already scraped schemes from {checkpoint_path}")
            except Exception as e:
                print(f"[Checkpoint Warning] Could not read checkpoint file ({e}). Starting fresh.")

        # Filter pending items
        pending_items = []
        for item in scheme_list:
            slug = item.get('fields', {}).get('slug') or item.get('slug')
            if slug and slug not in results:
                pending_items.append(item)

        print(f"[Scrape] Total schemes: {len(scheme_list)} | Already completed: {len(results)} | To scrape: {len(pending_items)}")

        if not pending_items:
            return list(results.values())

        # Checkpoint writer
        checkpoint_file = None
        if checkpoint_path:
            os.makedirs(os.path.dirname(os.path.abspath(checkpoint_path)), exist_ok=True)
            checkpoint_file = open(checkpoint_path, 'a', encoding='utf-8')

        def worker(item):
            fields = item.get('fields', {})
            slug = fields.get('slug') or item.get('slug')
            if not slug:
                return None
            time.sleep(self.delay)
            record = self.fetch_scheme_details(slug, summary_fields=fields)
            return record

        try:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {executor.submit(worker, item): item for item in pending_items}
                with tqdm(total=len(pending_items), desc="Downloading Details", unit="scheme") as pbar:
                    for future in as_completed(futures):
                        try:
                            record = future.result()
                            if record:
                                slug = record['slug']
                                results[slug] = record
                                if checkpoint_file:
                                    checkpoint_file.write(json.dumps(record, ensure_ascii=False) + "\n")
                                    checkpoint_file.flush()
                        except Exception as e:
                            print(f"\n[Worker Error]: {e}")
                        finally:
                            pbar.update(1)
        finally:
            if checkpoint_file:
                checkpoint_file.close()

        # Preserve original order from scheme_list
        ordered_results = []
        for item in scheme_list:
            slug = item.get('fields', {}).get('slug') or item.get('slug')
            if slug in results:
                ordered_results.append(results[slug])

        return ordered_results

    def scrape_category(
        self,
        category_name: str,
        limit: Optional[int] = None,
        max_workers: int = 5,
        output_dir: str = "output",
        formats: Optional[List[str]] = None,
        resume: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Scrapes all schemes belonging to a specific category.
        """
        safe_name = sanitize_filename(category_name)
        cat_dir = os.path.join(output_dir, safe_name)
        os.makedirs(cat_dir, exist_ok=True)
        checkpoint_path = os.path.join(cat_dir, "checkpoint.jsonl") if resume else None

        scheme_list = self.fetch_scheme_list(category=category_name, limit=limit)
        if not scheme_list:
            print(f"[Error] No schemes found for category: {category_name}")
            return []

        scraped_data = self.scrape_schemes(
            scheme_list,
            max_workers=max_workers,
            checkpoint_path=checkpoint_path
        )

        base_output = os.path.join(cat_dir, safe_name)
        export_data(scraped_data, base_output, formats=formats)
        return scraped_data

    def scrape_all_categories(
        self,
        limit_per_category: Optional[int] = None,
        max_workers: int = 5,
        output_dir: str = "output",
        formats: Optional[List[str]] = None,
        resume: bool = True
    ):
        """
        Scrapes schemes category-by-category.
        """
        categories = self.get_categories()
        print(f"[All Categories] Found {len(categories)} categories to scrape.")
        for idx, cat in enumerate(categories, 1):
            name = cat['name']
            count = cat['count']
            print(f"\n{'='*70}\n[{idx}/{len(categories)}] Category: {name} ({count} schemes)\n{'='*70}")
            self.scrape_category(
                category_name=name,
                limit=limit_per_category,
                max_workers=max_workers,
                output_dir=output_dir,
                formats=formats,
                resume=resume
            )

    def scrape_all_schemes(
        self,
        limit: Optional[int] = None,
        max_workers: int = 5,
        output_dir: str = "output",
        formats: Optional[List[str]] = None,
        resume: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Scrapes all unique schemes across the entire platform in a single consolidated dataset.
        """
        os.makedirs(output_dir, exist_ok=True)
        checkpoint_path = os.path.join(output_dir, "checkpoint_all.jsonl") if resume else None

        scheme_list = self.fetch_scheme_list(category=None, limit=limit)
        if not scheme_list:
            print("[Error] No schemes found on portal.")
            return []

        scraped_data = self.scrape_schemes(
            scheme_list,
            max_workers=max_workers,
            checkpoint_path=checkpoint_path
        )

        base_output = os.path.join(output_dir, "all_myscheme_schemes")
        export_data(scraped_data, base_output, formats=formats)
        return scraped_data
