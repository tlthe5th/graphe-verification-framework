from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from extract_abp_nt_clean import extract_book


# Edit this list with (pdf_file, book_name, start_page, end_page, txt_file)
JOBS: list[tuple[str, str, int, int, str]] = [
    # Example entries — replace or add books from BOOK_ROUTING with verified page ranges:
    # ("ABP New Testament Volume 3.pdf", "2 John", 400, 401, "2john.txt"),
    # ("ABP New Testament Volume 3.pdf", "3 John", 401, 402, "3john.txt"),
]


def run_cmd(args: list[str]) -> int:
    print(">", " ".join(args))
    completed = subprocess.run(args, check=False)
    return completed.returncode


def main() -> int:
    if not JOBS:
        print("JOBS list is empty. Add (pdf_file, book_name, start_page, end_page, txt_file) tuples first.")
        return 1

    for pdf_name, book_name, start_p, end_p, out_name in JOBS:
        pdf_path = Path(pdf_name)
        out_txt = Path(out_name)

        if not pdf_path.exists():
            print(f"Skipping {book_name}: PDF not found at {pdf_path}", file=sys.stderr)
            continue

        extract_book(
            pdf_path=pdf_path,
            book_name=book_name,
            start_page=start_p,
            end_page=end_p,
            output_txt=out_txt,
        )

        rc = run_cmd([sys.executable, "build_full_corpus.py", str(out_txt)])
        if rc != 0:
            print(f"build_full_corpus.py exited with code {rc} for {out_txt}", file=sys.stderr)
            return rc

        run_cmd([sys.executable, "validate.py", f"{book_name} 1:1"])

    return run_cmd(["pytest"])


if __name__ == "__main__":
    raise SystemExit(main())