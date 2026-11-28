import json
import sys
import unicodedata
from pathlib import Path


def normalize_nfc(obj):
    if isinstance(obj, str):
        return unicodedata.normalize("NFC", obj)
    if isinstance(obj, list):
        return [normalize_nfc(item) for item in obj]
    if isinstance(obj, dict):
        return {k: normalize_nfc(v) for k, v in obj.items()}
    return obj


def upsert_passages(target_path: Path, new_passages: list[dict]) -> int:
    data = json.loads(target_path.read_text(encoding="utf-8"))
    existing = data.setdefault("passages", [])
    index_by_anchor = {
        p.get("verse_anchor"): idx
        for idx, p in enumerate(existing)
        if p.get("verse_anchor")
    }

    added_or_updated = 0
    for passage in new_passages:
        cleaned = normalize_nfc(passage)
        for morph in cleaned.get("morphology", []):
            morph.setdefault("source_file", str(target_path).replace("\\", "/"))
            morph.setdefault("verse_anchor", cleaned.get("verse_anchor", ""))

        anchor = cleaned.get("verse_anchor")
        if anchor and anchor in index_by_anchor:
            existing[index_by_anchor[anchor]] = cleaned
        else:
            existing.append(cleaned)
            if anchor:
                index_by_anchor[anchor] = len(existing) - 1
        added_or_updated += 1

    normalized_data = normalize_nfc(data)
    target_path.write_text(
        json.dumps(normalized_data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return added_or_updated


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python import_passages.py <batch_input.json>")
        sys.exit(1)

    batch_file = Path(sys.argv[1])
    payload = json.loads(batch_file.read_text(encoding="utf-8"))

    # Expected format:
    # {
    #   "store/nt/gospels.json": [ { ...passage... }, ... ],
    #   "store/nt/acts.json": [ { ...passage... }, ... ]
    # }
    total = 0
    for rel_path, passages in payload.items():
        target = Path(rel_path)
        if not target.exists():
            print(f"Skipping missing target store: {rel_path}")
            continue
        count = upsert_passages(target, passages)
        total += count
        print(f"Updated {rel_path}: {count} passage(s)")

    print(f"Done. Processed {total} passage(s) with Unicode NFC normalization.")


if __name__ == "__main__":
    main()