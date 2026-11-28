from __future__ import annotations

import ast
import json
import re
from pathlib import Path
import pymupdf

PDF_FILES = [
    "ABP Old Testament Volume 1 .pdf",
    "ABP Old Testament Volume 2.pdf",
    "ABP New Testament Volume 3.pdf",
]

# Canonical search patterns for finding the start page of a book in a PDF.
# Add or adjust phrases here if any book header in your PDF uses a different title.
BOOK_SEARCH_PATTERNS: dict[str, list[str]] = {
    # Old Testament / LXX
    "Genesis": [r"\bGENESIS\b"],
    "Exodus": [r"\bEXODUS\b"],
    "Leviticus": [r"\bLEVITICUS\b"],
    "Numbers": [r"\bNUMBERS\b"],
    "Deuteronomy": [r"\bDEUTERONOMY\b"],
    "Joshua": [r"\bJOSHUA\b"],
    "Judges": [r"\bJUDGES\b"],
    "Ruth": [r"\bRUTH\b"],
    "1 Samuel": [r"\b1\s+SAMUEL\b", r"\bI\s+SAMUEL\b", r"\b1\s+KINGDOMS\b"],
    "2 Samuel": [r"\b2\s+SAMUEL\b", r"\bII\s+SAMUEL\b", r"\b2\s+KINGDOMS\b"],
    "1 Kings": [r"\b1\s+KINGS\b", r"\bI\s+KINGS\b", r"\b3\s+KINGDOMS\b"],
    "2 Kings": [r"\b2\s+KINGS\b", r"\bII\s+KINGS\b", r"\b4\s+KINGDOMS\b"],
    "1 Chronicles": [r"\b1\s+CHRONICLES\b", r"\bI\s+CHRONICLES\b"],
    "2 Chronicles": [r"\b2\s+CHRONICLES\b", r"\bII\s+CHRONICLES\b"],
    "Ezra": [r"\bEZRA\b"],
    "Nehemiah": [r"\bNEHEMIAH\b"],
    "Esther": [r"\bESTHER\b"],
    "Job": [r"\bJOB\b"],
    "Psalms": [r"\bPSALMS?\b"],
    "Proverbs": [r"\bPROVERBS\b"],
    "Ecclesiastes": [r"\bECCLESIASTES\b"],
    "Song of Solomon": [r"\bSONG OF SOLOMON\b", r"\bSONG OF SONGS\b"],
    "Isaiah": [r"\bISAIAH\b"],
    "Jeremiah": [r"\bJEREMIAH\b"],
    "Lamentations": [r"\bLAMENTATIONS\b"],
    "Ezekiel": [r"\bEZEKIEL\b"],
    "Daniel": [r"\bDANIEL\b"],
    "Hosea": [r"\bHOSEA\b"],
    "Joel": [r"\bJOEL\b"],
    "Amos": [r"\bAMOS\b"],
    "Obadiah": [r"\bOBADIAH\b"],
    "Jonah": [r"\bJONAH\b"],
    "Micah": [r"\bMICAH\b"],
    "Nahum": [r"\bNAHUM\b"],
    "Habakkuk": [r"\bHABAKKUK\b"],
    "Zephaniah": [r"\bZEPHANIAH\b"],
    "Haggai": [r"\bHAGGAI\b"],
    "Zechariah": [r"\bZECHARIAH\b"],
    "Malachi": [r"\bMALACHI\b"],
    # New Testament (ordered starting with Matthew)
    "Matthew": [r"\bMATTHEW\b"],
    "Mark": [r"\bMARK\b"],
    "Luke": [r"\bLUKE\b"],
    "John": [r"\bJOHN\b(?!\s+(?:1|2|3|I|II|III))"],
    "Acts": [r"\bACTS\b"],
    "Romans": [r"\bROMANS\b"],
    "1 Corinthians": [r"\b1\s+CORINTHIANS\b", r"\bI\s+CORINTHIANS\b"],
    "2 Corinthians": [r"\b2\s+CORINTHIANS\b", r"\bII\s+CORINTHIANS\b"],
    "Galatians": [r"\bGALATIANS\b"],
    "Ephesians": [r"\bEPHESIANS\b"],
    "Philippians": [r"\bPHILIPPIANS\b"],
    "Colossians": [r"\bCOLOSSIANS\b"],
    "1 Thessalonians": [r"\b1\s+THESSALONIANS\b", r"\bI\s+THESSALONIANS\b"],
    "2 Thessalonians": [r"\b2\s+THESSALONIANS\b", r"\bII\s+THESSALONIANS\b"],
    "1 Timothy": [r"\b1\s+TIMOTHY\b", r"\bI\s+TIMOTHY\b"],
    "2 Timothy": [r"\b2\s+TIMOTHY\b", r"\bII\s+TIMOTHY\b"],
    "Titus": [r"\bTITUS\b"],
    "Philemon": [r"\bPHILEMON\b"],
    "Hebrews": [r"\bHEBREWS\b"],
    "James": [r"\bJAMES\b"],
    "1 Peter": [r"\b1\s+PETER\b", r"\bI\s+PETER\b"],
    "2 Peter": [r"\b2\s+PETER\b", r"\bII\s+PETER\b"],
    "1 John": [r"\b1\s+JOHN\b", r"\bI\s+JOHN\b"],
    "2 John": [r"\b2\s+JOHN\b", r"\bII\s+JOHN\b"],
    "3 John": [r"\b3\s+JOHN\b", r"\bIII\s+JOHN\b"],
    "Jude": [r"\bJUDE\b"],
    "Revelation": [r"\bREVELATION\b"],
}


def load_routing_and_exclusions() -> tuple[list[str], set[str]]:
    routed_books: list[str] = []
    excluded: set[str] = set()

    corpus_script = Path("build_full_corpus.py")
    if corpus_script.exists():
        tree = ast.parse(corpus_script.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "BOOK_ROUTING":
                        val = ast.literal_eval(node.value)
                        if isinstance(val, dict):
                            routed_books = list(val.keys())
                    elif isinstance(target, ast.Name) and target.id == "EXCLUDED_BOOKS":
                        val = ast.literal_eval(node.value)
                        if isinstance(val, (set, list, tuple)):
                            excluded.update(str(x) for x in val)

    excl_json = Path("gate/exclusions.json")
    if excl_json.exists():
        data = json.loads(excl_json.read_text(encoding="utf-8"))
        if isinstance(data, list):
            excluded.update(str(x) for x in data)
        elif isinstance(data, dict):
            for key in ("excluded_books", "books", "exclusions"):
                if isinstance(data.get(key), list):
                    excluded.update(str(x) for x in data[key])

    return routed_books, excluded


def find_first_page(doc: pymupdf.Document, patterns: list[str], min_page: int = 1) -> int | None:
    compiled = [re.compile(pat, re.IGNORECASE) for pat in patterns]
    for page_num in range(max(1, min_page), len(doc) + 1):
        # Check top lines / full text for book heading
        text = doc[page_num - 1].get_text("text")
        header_slice = "\n".join(text.splitlines()[:12])
        if any(rx.search(header_slice) for rx in compiled):
            return page_num
    for page_num in range(max(1, min_page), len(doc) + 1):
        text = doc[page_num - 1].get_text("text")
        if any(rx.search(text) for rx in compiled):
            return page_num
    return None


def main() -> int:
    routed_books, excluded = load_routing_and_exclusions()
    candidate_books = routed_books or list(BOOK_SEARCH_PATTERNS.keys())
    active_books = [b for b in candidate_books if b not in excluded]

    manifest: list[dict[str, object]] = []

    for pdf_name in PDF_FILES:
        pdf_path = Path(pdf_name)
        if not pdf_path.exists():
            print(f"[WARN] Missing PDF: {pdf_name}")
            continue

        doc = pymupdf.open(pdf_path)
        total_pages = len(doc)
        hits: list[tuple[int, str]] = []

        for book in active_books:
            patterns = BOOK_SEARCH_PATTERNS.get(book)
            if not patterns:
                continue
            start_p = find_first_page(doc, patterns, min_page=1)
            if start_p is not None:
                hits.append((start_p, book))

        hits.sort(key=lambda item: item[0])

        for idx, (start_p, book) in enumerate(hits):
            if idx + 1 < len(hits):
                next_start = hits[idx + 1][0]
                end_p = max(start_p, next_start - 1)
            else:
                end_p = total_pages

            manifest.append(
                {
                    "pdf_file": pdf_name,
                    "book_name": book,
                    "start_page": start_p,
                    "end_page": end_p,
                    "out_txt": f"extracted/{re.sub(r'[^A-Za-z0-9]+', '_', book).strip('_').lower()}.txt",
                }
            )

    out_path = Path("book_manifest.json")
    out_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {len(manifest)} book entries to {out_path}")
    for entry in manifest:
        print(
            f"  {entry['book_name']:18s} | {entry['pdf_file']:32s} | "
            f"pp. {entry['start_page']}–{entry['end_page']} -> {entry['out_txt']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())