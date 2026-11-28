import sys
import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, List

from judge_10pt import CACHE_PATH, FRAMEWORK_VERSION, load_cache, save_cache
from validate import normalize_nfc, verify_passage

STORE_DIRS = [Path("store/lxx"), Path("store/nt")]


def normalize_ref(s: str) -> str:
    s = normalize_nfc(s).lower().strip()
    s = s.replace("\u2013", "-").replace("\u2014", "-")
    s = re.sub(r"[:.]", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s


def load_store_passages() -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    for sdir in STORE_DIRS:
        if not sdir.exists():
            continue
        for json_file in sorted(sdir.glob("*.json")):
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
            except Exception:
                continue
            passages = data.get("passages")
            if not isinstance(passages, list):
                continue
            corpus = data.get("corpus", "")
            for p in passages:
                if not isinstance(p, dict):
                    continue
                records.append({
                    "corpus": corpus,
                    "source_file": str(json_file),
                    "passage": p,
                })
    return records


def search_passages(query: str, limit: int = 5) -> List[Dict[str, Any]]:
    raw_q = normalize_nfc(query).lower().strip()
    norm_q = normalize_ref(query)
    all_records = load_store_passages()

    exact_matches = []
    partial_matches = []

    for rec in all_records:
        p = rec["passage"]
        ref = str(p.get("reference", ""))
        gref = str(p.get("greek_reference", ""))
        anchor = str(p.get("verse_anchor", ""))
        greek = str(p.get("greek_text", ""))
        eng = str(p.get("english_translation", ""))

        norm_ref = normalize_ref(ref)
        norm_anchor = normalize_ref(anchor)

        if norm_q == norm_ref or norm_q == norm_anchor:
            exact_matches.append(rec)
        elif (
            norm_q in norm_ref
            or norm_q in norm_anchor
            or raw_q in normalize_nfc(ref).lower()
            or raw_q in normalize_nfc(gref).lower()
            or raw_q in normalize_nfc(greek).lower()
            or raw_q in normalize_nfc(eng).lower()
        ):
            partial_matches.append(rec)

    return (exact_matches + partial_matches)[:limit]


def judge_via_framework(rec: Dict[str, Any], force_rejudge: bool = False) -> Dict[str, Any]:
    p = rec["passage"]
    lookup_ref = str(p.get("reference") or p.get("verse_anchor") or "").strip()
    cache_key = normalize_ref(lookup_ref).upper()
    cache = load_cache(CACHE_PATH)

    if not force_rejudge and cache_key in cache:
        cached = cache[cache_key]
        if cached.get("framework_version") == FRAMEWORK_VERSION and "analysis" in cached:
            return cached

    try:
        analysis = verify_passage(lookup_ref)
        entry = {
            "reference": lookup_ref,
            "verse_anchor": p.get("verse_anchor", ""),
            "source_file": rec["source_file"],
            "framework_version": FRAMEWORK_VERSION,
            "overall_verdict": analysis.get("overall_verdict"),
            "failed_criteria": analysis.get("failed_criteria", []),
            "failure_reasons": analysis.get("failure_reasons", []),
            "criteria_evaluations": analysis.get("criteria_evaluations", []),
            "citations": analysis.get("citations", []),
            "english_translation": p.get("english_translation", ""),
            "analysis": analysis,
        }
    except Exception as exc:
        entry = {
            "reference": lookup_ref,
            "verse_anchor": p.get("verse_anchor", ""),
            "source_file": rec["source_file"],
            "framework_version": FRAMEWORK_VERSION,
            "overall_verdict": "FAIL",
            "failed_criteria": [],
            "failure_reasons": [f"{type(exc).__name__}: {exc}"],
            "criteria_evaluations": [],
            "citations": [],
            "english_translation": p.get("english_translation", ""),
            "error": str(exc),
        }

    cache[cache_key] = entry
    save_cache(cache, CACHE_PATH)
    return entry


def format_for_ai(results: List[Dict[str, Any]]) -> str:
    blocks = []
    for r in results:
        lines = [
            f"REFERENCE: {r.get('reference')} ({r.get('verse_anchor')})",
            f"SOURCE: {r.get('source_file')}",
            f"OVERALL_VERDICT: {r.get('overall_verdict')}",
            f"FAILED_CRITERIA: {r.get('failed_criteria')}",
            f"FAILURE_REASONS: {r.get('failure_reasons')}",
            f"ENGLISH: {r.get('english_translation')}",
        ]
        cites = r.get("citations") or []
        if cites:
            lines.append(f"GREEK_EXCERPT: {cites[0].get('greek_excerpt', '')}")
            lines.append(f"CITATION_ANCHOR: {cites[0].get('file', '')} :: {cites[0].get('anchor', '')}")
        lines.append("CRITERIA_1_TO_10:")
        for c in r.get("criteria_evaluations") or []:
            lines.append(
                f"  - C{c.get('criterion_id')} ({c.get('criterion_name')}): "
                f"{c.get('status')} - {c.get('rationale')}"
            )
        blocks.append("\n".join(lines))
    return "\n\n---\n\n".join(blocks)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        parser = argparse.ArgumentParser(description="Search Graphē store and run framework verification.")
    parser.add_argument("--query", required=True, help="Verse reference, anchor, or Greek/English text")
    parser.add_argument("--rejudge", action="store_true", help="Force re-evaluation ignoring cache")
    parser.add_argument("--status", default="", help="Filter by overall_verdict (e.g. PASS or FAIL)")
    parser.add_argument("--limit", type=int, default=5, help="Max passages to evaluate/display")
    parser.add_argument("--ai", action="store_true", help="Output compact AI-ready summary")
    args = parser.parse_args()

    matched = search_passages(args.query, limit=args.limit)
    if not matched:
        print(f"No matching passages found in store/ for query: {args.query}")
        return

    results = [judge_via_framework(m, force_rejudge=args.rejudge) for m in matched]
    if args.status:
        wanted = args.status.strip().upper()
        results = [r for r in results if str(r.get("overall_verdict", "")).upper() == wanted]

    if args.ai:
        print(format_for_ai(results))
    else:
        print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
