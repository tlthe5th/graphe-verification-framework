import json
import os
from pathlib import Path
from typing import Any, Dict, List

CACHE_PATH = Path("data/judgments_10pt_cache.json")
FRAMEWORK_VERSION = "1.0"

CRITERIA_ORDER = [
    ("C1", "Pattern Consistency"),
    ("C2", "Narrative Coherence"),
    ("C3", "Who Benefits?"),
    ("C4", "Structural Integrity"),
    ("C5", "Manuscript & Historical Evidence"),
    ("C6", "2 Timothy 3:16-17 Test"),
    ("C7", "Hebrews 4:12 Test"),
    ("C8", "Iesous Christos / Apostolic Citation Test"),
    ("C9", "Christos Character Match"),
    ("C10", "Pneuma Fruit Test"),
]

SYSTEM_PROMPT = """You are the Graphe 10-Point Verification Evaluator.
Evaluate the target verse strictly through all 10 criteria in order (C1 through C10).
Do not skip any criterion.
- C1: Pattern Consistency (measure-for-measure, leadership/consequence, alignment with established scriptural patterns).
- C2: Narrative Coherence (tensions/contradictions with related passages, characterizations, theological principles).
- C3: Who Benefits? (explicitly state if triggered by C1/C2 or assessed for political, institutional, theological, or silencing gain).
- C4: Structural Integrity (literary/narrative flow; whether removal improves, damages, or leaves flow unclear/integrated).
- C5: Manuscript & Historical Evidence (LXX/MT/variants/early citations/historical notes).
- C6: 2 Timothy 3:16-17 Test (didaskalia, elegmos, epanorthosis, paideia en dikaiosyne).
- C7: Hebrews 4:12 Test (living/active logos penetrating/exposing/judging vs. confusion/obscurity; label interpretive/discernment).
- C8: Iesous Christos / Apostolic Citation Test (Gospel or apostolic citations, allusions, or non-canonical/pseudepigraphal links).
- C9: Christos Character Match (alignment with the Father revealed in Iesous Christos: John 14:9, Luke 9:55-56, Matt 5:43-48, John 8:44).
- C10: Pneuma Fruit Test (Gal 5:22-23 fruit of the Spirit vs. Gal 5:19-21 works of the flesh).

Return ONLY valid JSON matching this schema:
{
  "reference": "string",
  "framework_version": "1.0",
  "criteria": {
    "C1": {"finding": "PASS|NOTE|FLAG|FAIL", "rationale": "string"},
    "C2": {"finding": "PASS|NOTE|FLAG|FAIL", "rationale": "string"},
    "C3": {"finding": "PASS|NOTE|FLAG|FAIL", "rationale": "string"},
    "C4": {"finding": "PASS|NOTE|FLAG|FAIL", "rationale": "string"},
    "C5": {"finding": "PASS|NOTE|FLAG|FAIL", "rationale": "string"},
    "C6": {"finding": "PASS|NOTE|FLAG|FAIL", "rationale": "string"},
    "C7": {"finding": "PASS|NOTE|FLAG|FAIL", "rationale": "string"},
    "C8": {"finding": "PASS|NOTE|FLAG|FAIL", "rationale": "string"},
    "C9": {"finding": "PASS|NOTE|FLAG|FAIL", "rationale": "string"},
    "C10": {"finding": "PASS|NOTE|FLAG|FAIL", "rationale": "string"}
  },
  "criteria_showing_problems": ["C1", ...],
  "status": "HOLDS|HOLDS WITH NOTES|FLAGGED|FAILS|PENDING",
  "confidence": "HIGH|MODERATE|LOWER|FLAGGED FOR STUDY",
  "recommendation": "string"
}
"""

# Attach canonical Greek labels alongside ASCII-safe keys so terminals never garble output
CRITERIA_GREEK_LABELS = {
    "C6": "2 Timothy 3:16\u201317 Test (didaskalia, elegmos, epanorth\u014dsis, paideia en dikaiosyn\u0113)",
    "C8": "\u1f38\u03b7\u03c3\u03bf\u1fe6\u03c2 \u03a7\u03c1\u03b9\u03c3\u03c4\u03cc\u03c2 / Apostolic Citation Test",
    "C9": "\u03a7\u03c1\u03b9\u03c3\u03c4\u03cc\u03c2 Character Match",
    "C10": "\u03a0\u03bd\u03b5\u1fe6\u03bc\u03b1 Fruit Test",
}


def load_cache(path: Path = CACHE_PATH) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_cache(cache: Dict[str, Any], path: Path = CACHE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")


def is_complete_judgment(record: Dict[str, Any] | None) -> bool:
    if not isinstance(record, dict):
        return False
    if record.get("framework_version") != FRAMEWORK_VERSION:
        return False
    criteria = record.get("criteria")
    if not isinstance(criteria, dict):
        return False
    for code, _ in CRITERIA_ORDER:
        item = criteria.get(code)
        if not isinstance(item, dict) or not item.get("finding") or not item.get("rationale"):
            return False
    return bool(record.get("status") and record.get("confidence") and record.get("recommendation"))


def call_llm_10pt(payload: Dict[str, Any]) -> Dict[str, Any]:
    from openai import OpenAI

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    resp = client.chat.completions.create(
        model=os.environ.get("GRAPHE_JUDGE_MODEL", "gpt-4.1"),
        temperature=0.1,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
    )
    return json.loads(resp.choices[0].message.content)


def judge_verse(verse_obj: Dict[str, Any], force_rejudge: bool = False) -> Dict[str, Any]:
    ref = verse_obj["reference"].strip().upper()
    cache = load_cache()

    if not force_rejudge and is_complete_judgment(cache.get(ref)):
        return cache[ref]

    result = call_llm_10pt(verse_obj)
    result["reference"] = ref
    result["framework_version"] = FRAMEWORK_VERSION

    flagged = [
        code for code, _ in CRITERIA_ORDER
        if result.get("criteria", {}).get(code, {}).get("finding") in {"FLAG", "FAIL"}
    ]
    result["criteria_showing_problems"] = flagged

    if not is_complete_judgment(result):
        raise ValueError(f"Incomplete 10-point judgment returned for {ref}")

    cache[ref] = result
    save_cache(cache)
    return result


def judge_search_results(verses: List[Dict[str, Any]], force_rejudge: bool = False) -> List[Dict[str, Any]]:
    enriched = []
    for v in verses:
        judgment = judge_verse(v, force_rejudge=force_rejudge)
        enriched.append({**v, "judgment_10pt": judgment})
    return enriched
