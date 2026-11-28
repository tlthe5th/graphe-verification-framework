from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from build_full_corpus import BOOK_ROUTING, EXCLUDED_BOOKS
from extract_abp_nt_clean import extract_book

EXCLUDED_ALL: set[str] = set(EXCLUDED_BOOKS) | {
    "Song of Solomon",
    "Hebrews",
    "James",
    "Jude",
    "Revelation",
}


def run_cmd(args: list[str]) -> int:
    print(">", " ".join(args))
    return subprocess.run(args, check=False).returncode


def main() -> int:
    manifest_path = Path("book_manifest.json")
    if not manifest_path.exists():
        print("Run generate_exact_manifest.py first.", file=sys.stderr)
        return 1

    entries = json.loads(manifest_path.read_text(encoding="utf-8"))
    Path("extracted").mkdir(parents=True, exist_ok=True)

    for item in entries:
        book_name = str(item["book_name"])
        if book_name in EXCLUDED_ALL or book_name not in BOOK_ROUTING:
            print(f"[SKIP EXCLUDED] {book_name}")
            continue

        pdf_path = Path(str(item["pdf_file"]))
        start_page = int(item["start_page"])
        end_page = int(item["end_page"])
        out_txt = Path(str(item["out_txt"]))
        out_txt.parent.mkdir(parents=True, exist_ok=True)

        if not pdf_path.exists():
            print(f"[SKIP MISSING PDF] {book_name}: {pdf_path}")
            continue

        print(f"\n=== [{book_name}] {pdf_path.name} pp. {start_page}-{end_page} ===")
        extract_book(
            pdf_path=pdf_path,
            book_name=book_name,
            start_page=start_page,
            end_page=end_page,
            output_txt=out_txt,
        )

        rc = run_cmd([sys.executable, "build_full_corpus.py", str(out_txt)])
        if rc != 0:
            print(f"[ERROR] build_full_corpus.py failed on {out_txt} (code {rc})", file=sys.stderr)
            return rc

        ref = f"{book_name} 1:1"
        if out_txt.exists():
            lines = [ln for ln in out_txt.read_text(encoding="utf-8").splitlines() if ln.strip()]
            if lines:
                cols = lines[0].split("|")
                if len(cols) >= 3:
                    ref = f"{cols[0]} {cols[1]}:{cols[2]}"

        run_cmd([sys.executable, "validate.py", ref])

    print("\n=== Running pytest ===")
    return run_cmd([sys.executable, "-m", "pytest"])


if __name__ == "__main__":
    raise SystemExit(main())