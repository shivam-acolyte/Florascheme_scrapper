"""
Utility functions for text processing, Slate AST conversion, and data export.
"""

import os
import json
import html
import re
import pandas as pd
from typing import Dict, Any, List, Optional


def unescape_text(text: Optional[str]) -> str:
    """Decodes HTML entities (even if doubly encoded) and normalizes whitespace."""
    if not text:
        return ""
    if not isinstance(text, str):
        text = str(text)

    # Decode multiple levels of HTML encoding if present (e.g. &amp;quot; -> &quot; -> ")
    for _ in range(3):
        decoded = html.unescape(text)
        if decoded == text:
            break
        text = decoded

    return text.strip()


def slate_node_to_markdown(node: Any) -> str:
    """Recursively converts a Slate rich-text node / AST to Markdown with proper spacing."""
    if not isinstance(node, dict):
        return unescape_text(str(node)) if node is not None else ""

    # Leaf text node
    if 'text' in node:
        text = unescape_text(node['text'])
        if not text:
            return ""
        # Keep leading/trailing space outside formatting marks
        l_space = " " if text.startswith(" ") else ""
        r_space = " " if text.endswith(" ") else ""
        clean_text = text.strip()

        if not clean_text:
            return " "

        if node.get('bold'):
            clean_text = f"**{clean_text}**"
        if node.get('italic'):
            clean_text = f"*{clean_text}*"
        if node.get('underline'):
            clean_text = f"__{clean_text}__"

        return f"{l_space}{clean_text}{r_space}"

    children = node.get('children', [])
    children_text = "".join(slate_node_to_markdown(child) for child in children)
    node_type = node.get('type', '')

    if node_type == 'link':
        url = node.get('link') or node.get('url', '')
        link_text = children_text.strip()
        if not link_text:
            return ""
        l_sp = " " if children_text.startswith(" ") else ""
        r_sp = " " if children_text.endswith(" ") else ""
        return f"{l_sp}[{link_text}]({url}){r_sp}" if url else children_text
    elif node_type == 'paragraph':
        cleaned = children_text.strip()
        return f"{cleaned}\n\n" if cleaned else ""
    elif node_type == 'heading-one':
        return f"\n# {children_text.strip()}\n\n"
    elif node_type == 'heading-two':
        return f"\n## {children_text.strip()}\n\n"
    elif node_type == 'heading-three':
        return f"\n### {children_text.strip()}\n\n"
    elif node_type == 'block_quote':
        return f"\n> {children_text.strip()}\n\n"
    elif node_type in ('numbered-list', 'bulleted-list'):
        return f"{children_text}\n"
    elif node_type == 'list-item':
        return f"- {children_text.strip()}\n"
    else:
        return children_text


def extract_label(val: Any) -> Any:
    """Extracts a human-readable string from nested label/value dicts or lists."""
    if val is None:
        return ""
    if isinstance(val, str):
        return unescape_text(val)
    if isinstance(val, dict):
        if 'label' in val:
            return unescape_text(str(val['label']))
        if 'name' in val:
            return unescape_text(str(val['name']))
        if 'value' in val:
            return unescape_text(str(val['value']))
        return json.dumps(val, ensure_ascii=False)
    if isinstance(val, list):
        extracted = [extract_label(item) for item in val if item is not None]
        # Return comma-separated if elements are strings
        if all(isinstance(x, str) for x in extracted):
            return ", ".join([x for x in extracted if x])
        return extracted
    return str(val)


def sanitize_filename(name: str) -> str:
    """Replaces invalid characters for safe file naming."""
    name = re.sub(r'[\\/*?:"<>|]', '_', name)
    name = name.strip()
    return name[:120] if len(name) > 120 else name


def scheme_to_markdown_document(scheme: Dict[str, Any]) -> str:
    """Generates a complete, beautiful Markdown dossier for a single scheme."""
    title = scheme.get('scheme_name') or scheme.get('slug', 'Scheme')
    category = scheme.get('category') or "General"
    level = scheme.get('level') or "N/A"
    ministry = scheme.get('nodal_ministry') or "N/A"
    dept = scheme.get('nodal_department') or "N/A"
    beneficiaries = scheme.get('target_beneficiaries') or "N/A"
    scheme_type = scheme.get('scheme_type') or "N/A"
    dbt = "Yes" if scheme.get('dbt_scheme') else "No"
    url = scheme.get('url', '')

    md_lines = [
        f"# {title}\n",
        f"**Official Portal URL**: [{url}]({url})\n",
        f"| Attribute | Details |",
        f"| :--- | :--- |",
        f"| **Scheme Code / Short Title** | {scheme.get('scheme_short_title', 'N/A')} |",
        f"| **Category** | {category} |",
        f"| **Sub-Category** | {scheme.get('sub_category', 'N/A')} |",
        f"| **Level** | {level} |",
        f"| **Applicable State(s)** | {scheme.get('beneficiary_state', 'All')} |",
        f"| **Nodal Ministry** | {ministry} |",
        f"| **Department** | {dept} |",
        f"| **Implementing Agency** | {scheme.get('implementing_agency') or 'N/A'} |",
        f"| **Scheme Type** | {scheme_type} |",
        f"| **Direct Benefit Transfer (DBT)** | {dbt} |",
        f"| **Target Beneficiaries** | {beneficiaries} |",
        f"| **Tags** | {scheme.get('tags', 'N/A')} |",
        "\n---\n",
        "## 1. Overview & Brief Description\n",
        scheme.get('brief_description', 'No brief description available.').strip() + "\n",
    ]

    if scheme.get('detailed_description'):
        md_lines.extend([
            "## 2. Detailed Description\n",
            scheme['detailed_description'].strip() + "\n"
        ])

    if scheme.get('benefits'):
        md_lines.extend([
            "## 3. Benefits Offered\n",
            scheme['benefits'].strip() + "\n"
        ])

    if scheme.get('eligibility_criteria'):
        md_lines.extend([
            "## 4. Eligibility Criteria\n",
            scheme['eligibility_criteria'].strip() + "\n"
        ])

    if scheme.get('exclusions'):
        md_lines.extend([
            "## 5. Exclusions\n",
            scheme['exclusions'].strip() + "\n"
        ])

    if scheme.get('application_process'):
        md_lines.extend([
            "## 6. Application Process\n",
            scheme['application_process'].strip() + "\n"
        ])

    if scheme.get('documents_required'):
        md_lines.extend([
            "## 7. Required Documents\n",
            scheme['documents_required'].strip() + "\n"
        ])

    if scheme.get('faqs'):
        md_lines.extend([
            "## 8. Frequently Asked Questions (FAQs)\n",
            scheme['faqs'].strip() + "\n"
        ])

    references = scheme.get('references')
    if references:
        md_lines.append("## 9. References & Official Links\n")
        if isinstance(references, list):
            for ref in references:
                if isinstance(ref, dict):
                    t = ref.get('title') or ref.get('url') or 'Link'
                    u = ref.get('url', '')
                    md_lines.append(f"- [{t}]({u})")
                elif isinstance(ref, str):
                    md_lines.append(f"- <{ref}>")
        else:
            md_lines.append(str(references))
        md_lines.append("\n")

    return "\n".join(md_lines)


def export_data(schemes: List[Dict[str, Any]], output_base: str, formats: List[str] = None):
    """
    Exports scraped schemes into JSON, CSV, Excel, and Markdown files.
    """
    if formats is None:
        formats = ['json', 'csv', 'excel', 'markdown']
    formats = [f.lower().strip() for f in formats]
    if 'all' in formats:
        formats = ['json', 'csv', 'excel', 'markdown']

    os.makedirs(os.path.dirname(os.path.abspath(output_base)), exist_ok=True)

    # 1. JSON Export (Complete structured fidelity)
    if 'json' in formats:
        json_path = f"{output_base}.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(schemes, f, indent=2, ensure_ascii=False)
        print(f"[Export] Saved JSON ({len(schemes)} items): {json_path}")

    # 2. JSON Lines Export (Streaming friendly)
    if 'jsonl' in formats:
        jsonl_path = f"{output_base}.jsonl"
        with open(jsonl_path, 'w', encoding='utf-8') as f:
            for s in schemes:
                f.write(json.dumps(s, ensure_ascii=False) + "\n")
        print(f"[Export] Saved JSONL ({len(schemes)} items): {jsonl_path}")

    # 3. CSV & Excel Export
    if 'csv' in formats or 'excel' in formats:
        # Prepare tabular rows
        tabular_rows = []
        for s in schemes:
            row = dict(s)
            # Flatten lists or dicts for spreadsheet
            for k, v in row.items():
                if isinstance(v, (list, dict)):
                    row[k] = extract_label(v)
            tabular_rows.append(row)

        df = pd.DataFrame(tabular_rows)

        if 'csv' in formats:
            csv_path = f"{output_base}.csv"
            df.to_csv(csv_path, index=False, encoding='utf-8-sig')
            print(f"[Export] Saved CSV ({len(schemes)} items): {csv_path}")

        if 'excel' in formats:
            excel_path = f"{output_base}.xlsx"
            try:
                with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:
                    df.to_excel(writer, index=False, sheet_name='Schemes')
                    # Auto-fit column widths (with safety cap)
                    ws = writer.sheets['Schemes']
                    for col in ws.columns:
                        max_len = max(len(str(cell.value or '')) for cell in col[:50])
                        col_letter = col[0].column_letter
                        ws.column_dimensions[col_letter].width = min(max(max_len + 2, 12), 60)
                print(f"[Export] Saved Excel ({len(schemes)} items): {excel_path}")
            except Exception as e:
                print(f"[Export Warning] Excel export failed ({e}). CSV was generated.")

    # 4. Individual Markdown Dossiers
    if 'markdown' in formats:
        md_dir = f"{output_base}_markdown"
        os.makedirs(md_dir, exist_ok=True)
        for s in schemes:
            slug = s.get('slug') or sanitize_filename(s.get('scheme_name', 'scheme'))
            safe_slug = sanitize_filename(slug)
            file_path = os.path.join(md_dir, f"{safe_slug}.md")
            doc = scheme_to_markdown_document(s)
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(doc)
        print(f"[Export] Saved Markdown Dossiers ({len(schemes)} files): {md_dir}/")
