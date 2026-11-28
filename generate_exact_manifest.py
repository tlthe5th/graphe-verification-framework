from __future__ import annotations

import json
import re
from pathlib import Path
import pymupdf

from build_full_corpus import BOOK_ROUTING, EXCLUDED_BOOKS

EXCLUDED_ALL: set[str] = set(EXCLUDED_BOOKS) | {
    "Song of Solomon",
    "Hebrews",
    "James",
    "Jude",
    "Revelation",
}

# (pdf_filename, pdf_page_offset_from_toc_page, [(book_name, toc_start_page), ...])
VOLUME_SPECS: list[tuple[str, int, list[tuple[str, int]]]] = [
    (
        "ABP Old Testament Volume 1 .pdf",
        16,  # TOC p. 1 (Genesis) is PDF p. 17 -> offset +16
        [
            ("Genesis", 1),
            ("Exodus", 88),
            ("Leviticus", 162),
            ("Numbers", 217),
            ("Deuteronomy", 290),
            ("Joshua", 355),
            ("Judges", 399),
            ("Ruth", 443),
            ("1 Samuel", 449),
            ("2 Samuel", 508),
            ("1 Kings", 556),
            ("2 Kings", 611),
        ],
    ),
    (
        "ABP Old Testament Volume 2.pdf",
        6,  # TOC p. 1 (1 Chronicles) is PDF p. 7 -> offset +6
        [
            ("1 Chronicles", 1),
            ("2 Chronicles", 48),
            ("Ezra", 108),
            ("Nehemiah", 124),
            ("Esther", 148),
            ("Job", 160),
            ("Psalms", 203),
            ("Proverbs", 310),
            ("Ecclesiastes", 349),
            ("Song of Solomon", 362),  # Excluded boundary marker so Isaiah stops cleanly
            ("Isaiah", 369),
            ("Jeremiah", 454),
            ("Lamentations", 547),
            ("Ezekiel", 555),
            ("Daniel", 645),
            ("Hosea", 672),
            ("Joel", 684),
            ("Amos", 689),
            ("Obadiah", 700),
            ("Jonah", 702),
            ("Micah", 705),
            ("Nahum", 713),
            ("Habakkuk", 716),
            ("Zephaniah", 720),
            ("Haggai", 724),
            ("Zechariah", 727),
            ("Malachi", 742),
        ],
    ),
    (
        "ABP New Testament Volume 3.pdf",
        4,  # TOC p. 1 (Matthew) is PDF p. 5 -> offset +4
        [
            ("Matthew", 1),
            ("Mark", 57),
            ("Luke", 93),
            ("John", 152),
            ("Acts", 196),
            ("Romans", 254),
            ("1 Corinthians", 276),
            ("2 Corinthians", 298),
            ("Galatians", 312),
            ("Ephesians", 319),
            ("Philippians", 327),
            ("Colossians", 332),
            ("1 Thessalonians", 337),
            ("2 Thessalonians", 342),
            ("1 Timothy", 344),
            ("2 Timothy", 350),
            ("Titus", 355),
            ("Philemon", 357),
            ("Hebrews", 359),     # Excluded boundary marker
            ("James", 376),       # Excluded boundary marker
            ("1 Peter", 382),
            ("2 Peter", 388),
            ("1 John", 392),
            ("2 John", 398),
            ("3 John", 399),
            ("Jude", 400),        # Excluded boundary marker
            ("Revelation", 402),  # Excluded boundary marker
        ],
    ),
]


def slugify(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_").lower()


def main() -> int:
    manifest: list[dict[str, object]] = []

    for pdf_name, offset, toc_items in VOLUME_SPECS:
        pdf_path = Path(pdf_name)
        if not pdf_path.exists():
            print(f"[WARN] Missing PDF: {pdf_name}")
            continue

        doc = pymupdf.open(pdf_path)
        total_pages = len(doc)

        # Convert TOC start pages to 1-based PDF pages
        pdf_starts: list[tuple[int, str]] = [
            (min(total_pages, max(1, toc_page + offset)), book)
            for book, toc_page in toc_items
        ]

        for idx, (start_p, book) in enumerate(pdf_starts):
            if idx + 1 < len(pdf_starts):
                next_start = pdf_starts[idx + 1][0]
                end_p = max(start_p, next_start - 1)
            else:
                end_p = total_pages

            if book in EXCLUDED_ALL or book not in BOOK_ROUTING:
                continue

            manifest.append(
                {
                    "pdf_file": pdf_name,
                    "book_name": book,
                    "start_page": start_p,
                    "end_page": end_p,
                    "out_txt": f"extracted/{slugify(book)}.txt",
                }
            )

    out_file = Path("book_manifest.json")
    out_file.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Generated {out_file} with {len(manifest)} routed books (excluded books omitted):")
    for row in manifest:
        print(
            f"  {str(row['book_name']):18s} | {str(row['pdf_file']):32s} | "
            f"pp. {row['start_page']}–{row['end_page']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())