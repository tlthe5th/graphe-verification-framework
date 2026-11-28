from __future__ import annotations

import json
from pathlib import Path

from build_full_corpus import BOOK_ROUTING, EXCLUDED_BOOKS
from generate_exact_manifest import VOLUME_SPECS

EXCLUDED_ALL: set[str] = set(EXCLUDED_BOOKS) | {
    "Song of Solomon",
    "Hebrews",
    "James",
    "Jude",
    "Revelation",
}


def main() -> int:
    expected_books: set[str] = set(BOOK_ROUTING.keys())
    for _, _, toc_items in VOLUME_SPECS:
        for book_name, _ in toc_items:
            if book_name not in EXCLUDED_ALL:
                expected_books.add(book_name)

    missing_route: list[str] = []
    missing_store: list[tuple[str, str, int]] = []
    present: list[tuple[str, str, int]] = []

    for book_name in sorted(expected_books):
        if book_name in EXCLUDED_ALL:
            continue

        route_info = BOOK_ROUTING.get(book_name)
        if not route_info:
            missing_route.append(book_name)
            continue

        store_rel = str(route_info[0])
        anchor_prefix = str(route_info[2]).lower()
        store_path = Path(store_rel)

        count = 0
        if store_path.exists():
            data = json.loads(store_path.read_text(encoding="utf-8"))
            for p in data.get("passages", []):
                if not isinstance(p, dict):
                    continue
                ref = str(p.get("reference", "")).lower().strip()
                anchor = str(p.get("verse_anchor", "")).lower().strip()
                if ref.startswith(book_name.lower() + " ") or anchor.startswith(anchor_prefix + "."):
                    count += 1

        if count == 0:
            missing_store.append((book_name, store_rel, count))
        else:
            present.append((book_name, store_rel, count))

    print(f"Present non-excluded books: {len(present)}")
    for b, f, c in present:
        print(f"  [OK]            {b:18s} -> {f} ({c} passages)")

    print(f"\nMissing / 0-passage routed books: {len(missing_store)}")
    for b, f, c in missing_store:
        print(f"  [MISSING STORE] {b:18s} -> {f} ({c} passages)")

    print(f"\nBooks in volume specs but not in BOOK_ROUTING: {len(missing_route)}")
    for b in missing_route:
        print(f"  [UNROUTED]      {b}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())