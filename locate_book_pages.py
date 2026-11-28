from __future__ import annotations

import re
import sys
from pathlib import Path
import pymupdf

CHAPTER_ONE_RE = re.compile(r"\b1:1\b")


def scan_pdf(pdf_path: Path, query: str) -> None:
    if not pdf_path.exists():
        print(f"Missing PDF: {pdf_path}", file=sys.stderr)
        return

    doc = pymupdf.open(pdf_path)
    q_upper = query.strip().upper()
    print(f"=== {pdf_path.name} ({len(doc)} pages) | query='{query}' ===")

    matches = 0
    for page_num, page in enumerate(doc, start=1):
        lines = [ln.strip() for ln in page.get_text("text").splitlines() if ln.strip()]
        joined_upper = "\n".join(lines).upper()
        has_query = q_upper in joined_upper if q_upper else False
        has_ch1 = any(CHAPTER_ONE_RE.search(ln) for ln in lines)

        if has_query or (not q_upper and has_ch1):
            sample = [ln[:70] for ln in lines if (q_upper and q_upper in ln.upper()) or CHAPTER_ONE_RE.search(ln)]
            print(f"  Page {page_num}: {' | '.join(sample[:3])}")
            matches += 1

    if matches == 0:
        print("  No matching pages found.")


def main() -> int:
    if len(sys.argv) < 2:
        print(
            'Usage: python locate_book_pages.py "<pdf_path>" ["<BOOK_HEADER_OR_SEARCH>"]',
            file=sys.stderr,
        )
        return 1

    pdf_path = Path(sys.argv[1])
    query = sys.argv[2] if len(sys.argv) >= 3 else ""
    scan_pdf(pdf_path, query)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())