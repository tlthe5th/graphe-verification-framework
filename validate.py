"""Core citation-enforced verification engine for graphe-verification-framework.

This module implements:
1. Strict Unicode NFC normalization for Greek strings.
2. Character-set validation for Greek text fields ONLY (U+0370-U+03FF, U+1F00-U+1FFF,
   plus allowed punctuation and whitespace), never restricting English fields or user input.
3. Bilingual reference normalization (English and Greek book/passage queries).
4. Fail-closed gatekeeping against `gate/exclusions.json` FIRST before running analysis.
5. Citation-enforced lookup against `store/lxx/*.json` and `store/nt/*.json`.
6. Strict JSON Schema validation against `schema/analysis.json`.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, ValidationError


REPO_ROOT = Path(__file__).resolve().parent
SCHEMA_PATH = REPO_ROOT / "schema" / "analysis.json"
RULES_PATH = REPO_ROOT / "gate" / "rules.json"
EXCLUSIONS_PATH = REPO_ROOT / "gate" / "exclusions.json"
STORE_DIRS = [REPO_ROOT / "store" / "lxx", REPO_ROOT / "store" / "nt"]

# Greek & Coptic (U+0370-U+03FF) and Greek Extended (U+1F00-U+1FFF),
# plus numbers, whitespace, and standard punctuation used in Greek text/excerpts.
GREEK_FIELD_PATTERN = re.compile(
    r"^[\u0370-\u03FF\u1F00-\u1FFF0-9\s.,;:·'’\"“”\-–—()\[\]]+$"
)

# Stricter pattern for Greek morphological surface_form and lemma tokens.
GREEK_TOKEN_PATTERN = re.compile(r"^[\u0370-\u03FF\u1F00-\u1FFF'’\-]+$")

# Book alias map supporting English and Greek references (normalized to NFC and lowercase).
BOOK_ALIASES: dict[str, tuple[str, str]] = {
    # LXX Old Testament books in store
    "genesis": ("Genesis", "Γένεσις"),
    "gen": ("Genesis", "Γένεσις"),
    "γένεσις": ("Genesis", "Γένεσις"),
    "γένεσιν": ("Genesis", "Γένεσις"),
    "deuteronomy": ("Deuteronomy", "Δευτερονόμιον"),
    "deut": ("Deuteronomy", "Δευτερονόμιον"),
    "δευτερονόμιον": ("Deuteronomy", "Δευτερονόμιον"),
    "1 samuel": ("1 Samuel", "Βασιλειῶν Α"),
    "1sam": ("1 Samuel", "Βασιλειῶν Α"),
    "1 sam": ("1 Samuel", "Βασιλειῶν Α"),
    "first samuel": ("1 Samuel", "Βασιλειῶν Α"),
    "βασιλειῶν α": ("1 Samuel", "Βασιλειῶν Α"),
    "βασιλειων α": ("1 Samuel", "Βασιλειῶν Α"),
    # NT books in store
    "matthew": ("Matthew", "Κατὰ Ματθαῖον"),
    "matt": ("Matthew", "Κατὰ Ματθαῖον"),
    "ματθαῖος": ("Matthew", "Κατὰ Ματθαῖον"),
    "κατὰ ματθαῖον": ("Matthew", "Κατὰ Ματθαῖον"),
    "mark": ("Mark", "Κατὰ Μάρκον"),
    "mk": ("Mark", "Κατὰ Μάρκον"),
    "μάρκος": ("Mark", "Κατὰ Μάρκον"),
    "κατὰ μάρκον": ("Mark", "Κατὰ Μάρκον"),
    "luke": ("Luke", "Κατὰ Λουκᾶν"),
    "lk": ("Luke", "Κατὰ Λουκᾶν"),
    "λουκᾶς": ("Luke", "Κατὰ Λουκᾶν"),
    "κατὰ λουκᾶν": ("Luke", "Κατὰ Λουκᾶν"),
    "john": ("John", "Κατὰ Ἰωάννην"),
    "jn": ("John", "Κατὰ Ἰωάννην"),
    "ἰωάννης": ("John", "Κατὰ Ἰωάννην"),
    "κατὰ ἰωάννην": ("John", "Κατὰ Ἰωάννην"),
    "acts": ("Acts", "Πράξεις Ἀποστόλων"),
    "πράξεις": ("Acts", "Πράξεις Ἀποστόλων"),
    "πράξεις ἀποστόλων": ("Acts", "Πράξεις Ἀποστόλων"),
    "romans": ("Romans", "Πρὸς Ῥωμαίους"),
    "rom": ("Romans", "Πρὸς Ῥωμαίους"),
    "πρὸς ῥωμαίους": ("Romans", "Πρὸς Ῥωμαίους"),
    "2 timothy": ("2 Timothy", "Πρὸς Τιμόθεον Β"),
    "2tim": ("2 Timothy", "Πρὸς Τιμόθεον Β"),
    "2 tim": ("2 Timothy", "Πρὸς Τιμόθεον Β"),
    "πρὸς τιμόθεον β": ("2 Timothy", "Πρὸς Τιμόθεον Β"),
    "1 peter": ("1 Peter", "Πέτρου Α"),
    "1pet": ("1 Peter", "Πέτρου Α"),
    "1 pet": ("1 Peter", "Πέτρου Α"),
    "πέτρου α": ("1 Peter", "Πέτρου Α"),
    "2 peter": ("2 Peter", "Πέτρου Β"),
    "2pet": ("2 Peter", "Πέτρου Β"),
    "2 pet": ("2 Peter", "Πέτρου Β"),
    "πέτρου β": ("2 Peter", "Πέτρου Β"),
    "1 john": ("1 John", "Ἰωάννου Α"),
    "1john": ("1 John", "Ἰωάννου Α"),
    "1 jn": ("1 John", "Ἰωάννου Α"),
    "ἰωάννου α": ("1 John", "Ἰωάννου Α"),
    # Excluded books (must fail closed at exclusion gate)
    "song of solomon": ("Song of Solomon", "Ἆσμα Ἀσμάτων"),
    "song of songs": ("Song of Solomon", "Ἆσμα Ἀσμάτων"),
    "Ἆσμα ἀσμάτων": ("Song of Solomon", "Ἆσμα Ἀσμάτων"),
    "ἆσμα ἀσμάτων": ("Song of Solomon", "Ἆσμα Ἀσμάτων"),
    "jude": ("Jude", "Ἰούδα"),
    "ἰούδα": ("Jude", "Ἰούδα"),
    "james": ("James", "Ἰακώβου"),
    "ἰακώβου": ("James", "Ἰακώβου"),
    "hebrews": ("Hebrews", "Πρὸς Ἑβραίους"),
    "heb": ("Hebrews", "Πρὸς Ἑβραίους"),
    "πρὸς ἑβραίους": ("Hebrews", "Πρὸς Ἑβραίους"),
    "revelation": ("Revelation", "Ἀποκάλυψις Ἰωάννου"),
    "rev": ("Revelation", "Ἀποκάλυψις Ἰωάννου"),
    "ἀποκάλυψις": ("Revelation", "Ἀποκάλυψις Ἰωάννου"),
    "ἀποκάλυψις ἰωάννου": ("Revelation", "Ἀποκάλυψις Ἰωάννου"),
}


class VerificationEngineError(Exception):
    """Raised when an internal configuration, schema, or fail-closed invariant fails."""


def normalize_nfc(text: str) -> str:
    """Normalize any string to Unicode Normalization Form C (NFC)."""
    if not isinstance(text, str):
        raise VerificationEngineError("Expected string input for NFC normalization.")
    return unicodedata.normalize("NFC", text)


def validate_greek_text_field(text: str, field_name: str) -> str:
    """Normalize a Greek text field to NFC and enforce Greek Unicode range validation."""
    normalized = normalize_nfc(text).strip()
    if not normalized:
        raise VerificationEngineError(f"Greek field '{field_name}' cannot be empty.")
    if not GREEK_FIELD_PATTERN.match(normalized):
        raise VerificationEngineError(
            f"Greek field '{field_name}' contains characters outside allowed Greek/punctuation set: {normalized!r}"
        )
    return normalized


def validate_greek_token_field(text: str, field_name: str) -> str:
    """Normalize a Greek morphological token (surface_form or lemma) to NFC and validate."""
    normalized = normalize_nfc(text).strip()
    if not normalized:
        raise VerificationEngineError(f"Greek token field '{field_name}' cannot be empty.")
    if not GREEK_TOKEN_PATTERN.match(normalized):
        raise VerificationEngineError(
            f"Greek token field '{field_name}' contains invalid characters: {normalized!r}"
        )
    return normalized


def load_json_file(path: Path) -> dict[str, Any]:
    """Load a UTF-8 JSON file from disk and return its parsed dictionary."""
    if not path.exists():
        raise VerificationEngineError(f"Required JSON file is missing: {path}")
    try:
        raw_text = path.read_text(encoding="utf-8")
        data = json.loads(raw_text)
    except (OSError, json.JSONDecodeError) as exc:
        raise VerificationEngineError(f"Failed to read/parse JSON file '{path}': {exc}") from exc
    if not isinstance(data, dict):
        raise VerificationEngineError(f"Top-level JSON in '{path}' must be an object.")
    return data


def load_rules() -> list[dict[str, Any]]:
    """Load and validate the 10 framework criteria from gate/rules.json."""
    rules_data = load_json_file(RULES_PATH)
    criteria = rules_data.get("criteria")
    if not isinstance(criteria, list) or len(criteria) != 10:
        raise VerificationEngineError("gate/rules.json must define exactly 10 criteria.")
    sorted_criteria = sorted(criteria, key=lambda item: int(item["id"]))
    expected_ids = list(range(1, 11))
    actual_ids = [int(item["id"]) for item in sorted_criteria]
    if actual_ids != expected_ids:
        raise VerificationEngineError(f"Expected criteria IDs 1..10, got {actual_ids}.")
    return sorted_criteria


def load_exclusions() -> dict[str, Any]:
    """Load gate/exclusions.json."""
    return load_json_file(EXCLUSIONS_PATH)


def load_schema_validator() -> Draft202012Validator:
    """Load schema/analysis.json and compile a Draft 2020-12 validator."""
    schema_data = load_json_file(SCHEMA_PATH)
    try:
        Draft202012Validator.check_schema(schema_data)
        return Draft202012Validator(schema_data)
    except Exception as exc:
        raise VerificationEngineError(f"Invalid JSON schema in {SCHEMA_PATH}: {exc}") from exc


def _normalize_dash_and_spacing(value: str) -> str:
    """Normalize dashes, colons, and whitespace for flexible reference matching."""
    cleaned = normalize_nfc(value).lower()
    cleaned = cleaned.replace("–", "-").replace("—", "-").replace("−", "-")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def parse_reference_query(raw_query: str) -> tuple[str, str, str]:
    """Parse a user query in English or Greek into (canonical_english_book, canonical_greek_book, verse_part).

    Note: User input is normalized to NFC and stripped/lowercased for matching, NEVER
    passed through the Greek-only character set restriction so English queries work cleanly.
    """
    if not isinstance(raw_query, str) or not raw_query.strip():
        raise VerificationEngineError("Query reference cannot be empty.")

    normalized_query = _normalize_dash_and_spacing(raw_query)

    # Match numbered books like "1 samuel 15:3", "2 peter 2:7-8", "1 john 5:7-8"
    numbered_match = re.match(
        r"^([123]\s+[a-z\u0370-\u03ff\u1f00-\u1fff]+(?:\s+[a-z\u0370-\u03ff\u1f00-\u1fff]+)?)\s*(.*)$",
        normalized_query,
    )
    if numbered_match:
        book_part = _normalize_dash_and_spacing(numbered_match.group(1))
        verse_part = _normalize_dash_and_spacing(numbered_match.group(2))
        if book_part in BOOK_ALIASES:
            eng_book, grk_book = BOOK_ALIASES[book_part]
            return eng_book, grk_book, verse_part

    # Match Greek prefixed multi-word titles like "κατὰ ἰωάννην 6:63", "πρὸς ῥωμαίους 13:1-7"
    greek_prep_match = re.match(
        r"^((?:κατὰ|πρὸς|πράξεις|ἆσμα)\s+[a-z\u0370-\u03ff\u1f00-\u1fff]+(?:\s+[αβγ])?)\s*(.*)$",
        normalized_query,
    )
    if greek_prep_match:
        book_part = _normalize_dash_and_spacing(greek_prep_match.group(1))
        verse_part = _normalize_dash_and_spacing(greek_prep_match.group(2))
        if book_part in BOOK_ALIASES:
            eng_book, grk_book = BOOK_ALIASES[book_part]
            return eng_book, grk_book, verse_part

    # Match single-word or multi-word English/Greek book titles
    # Try longest matching prefix from BOOK_ALIASES first.
    for alias in sorted(BOOK_ALIASES.keys(), key=len, reverse=True):
        if normalized_query == alias:
            eng_book, grk_book = BOOK_ALIASES[alias]
            return eng_book, grk_book, ""
        if normalized_query.startswith(alias + " ") or normalized_query.startswith(alias + ":"):
            remainder = normalized_query[len(alias) :].lstrip(" :").strip()
            eng_book, grk_book = BOOK_ALIASES[alias]
            return eng_book, grk_book, remainder

    raise VerificationEngineError(
        f"Unrecognized or unsupported scripture reference: {raw_query!r}"
    )


def _match_verse_part(passage: dict[str, Any], verse_part: str) -> bool:
    """Return True if a stored passage matches the requested chapter/verse string."""
    if not verse_part:
        return True
    target = _normalize_dash_and_spacing(verse_part).replace(" ", "")
    candidates = [
        passage.get("reference", ""),
        passage.get("greek_reference", ""),
        passage.get("verse_anchor", ""),
    ]
    for cand in candidates:
        norm_cand = _normalize_dash_and_spacing(cand).replace(" ", "")
        if norm_cand.endswith(target) or target in norm_cand:
            return True
    return False


def find_stored_passage(
    eng_book: str, grk_book: str, verse_part: str
) -> tuple[str, str, dict[str, Any]] | None:
    """Search store/lxx/*.json and store/nt/*.json for a matching passage.

    Returns (rel_source_file, corpus, passage_dict) or None if not found.
    """
    for store_dir in STORE_DIRS:
        if not store_dir.exists():
            continue
        for json_path in sorted(store_dir.glob("*.json")):
            data = load_json_file(json_path)
            corpus = normalize_nfc(str(data.get("corpus", "")))
            rel_source = f"store/{store_dir.name}/{json_path.name}"
            book_eng = normalize_nfc(str(data.get("book_english", "")))
            book_grk = normalize_nfc(str(data.get("book_greek", "")))
            books_covered = [normalize_nfc(str(b)) for b in data.get("books_covered", [])]
            books_greek = [normalize_nfc(str(b)) for b in data.get("books_greek", [])]

            book_matches = (
                eng_book in {book_eng, *books_covered}
                or grk_book in {book_grk, *books_greek}
            )
            if not book_matches:
                continue

            for passage in data.get("passages", []):
                if not isinstance(passage, dict):
                    continue
                if _match_verse_part(passage, verse_part):
                    return rel_source, corpus, passage
    return None


def check_exclusions_first(
    eng_book: str, grk_book: str, verse_part: str, exclusions_data: dict[str, Any]
) -> dict[str, Any] | None:
    """Check gate/exclusions.json FIRST before evaluating any passage.

    Returns an exclusion match dict if excluded, otherwise None.
    """
    eng_norm = _normalize_dash_and_spacing(eng_book)
    grk_norm = _normalize_dash_and_spacing(grk_book)
    verse_norm = _normalize_dash_and_spacing(verse_part).replace(" ", "")

    # 1. Check excluded books first (e.g., Song of Solomon, Jude, James, Hebrews, Revelation)
    for book_entry in exclusions_data.get("excluded_books", []):
        entry_eng = _normalize_dash_and_spacing(str(book_entry.get("book_english", "")))
        entry_grk = _normalize_dash_and_spacing(str(book_entry.get("book_greek", "")))
        if eng_norm == entry_eng or grk_norm == entry_grk:
            return {
                "exclusion_type": "book",
                "entry": book_entry,
            }

    # 2. Check excluded passages (e.g., John 7:53-8:11, Mark 16:9-20, Romans 13:1-7, 1 John 5:7-8,
    #    Deuteronomy 20:16-18, 1 Samuel 15:3, Genesis 9:20-27, Genesis 19:6-8)
    for passage_entry in exclusions_data.get("excluded_passages", []):
        ref_eng = _normalize_dash_and_spacing(str(passage_entry.get("reference", "")))
        ref_grk = _normalize_dash_and_spacing(str(passage_entry.get("greek_reference", "")))
        anchor = _normalize_dash_and_spacing(str(passage_entry.get("verse_anchor", "")))

        if verse_norm:
            if (
                verse_norm in ref_eng.replace(" ", "")
                and eng_norm in ref_eng
            ) or (
                verse_norm in ref_grk.replace(" ", "")
                and grk_norm in ref_grk
            ) or (
                verse_norm.replace(":", ".").replace("–", "-") in anchor.lower()
                and eng_norm.split()[0] in anchor.lower()
            ):
                return {
                    "exclusion_type": "passage",
                    "entry": passage_entry,
                }

    return None


def _build_criteria_evaluations(
    rules: list[dict[str, Any]],
    stored_evaluations: dict[str, Any] | None,
    default_status: str,
    default_rationale: str,
    citation_obj: dict[str, str],
) -> list[dict[str, Any]]:
    """Build the mandatory 10-element criteria_evaluations list with citations."""
    evaluations: list[dict[str, Any]] = []
    for rule in rules:
        cid = int(rule["id"])
        cname = normalize_nfc(str(rule["name"]))
        if stored_evaluations and str(cid) in stored_evaluations:
            entry = stored_evaluations[str(cid)]
            status = str(entry.get("status", default_status)).upper()
            if status not in {"PASS", "FAIL"}:
                raise VerificationEngineError(
                    f"Invalid criterion status '{status}' for criterion {cid}."
                )
            rationale = normalize_nfc(str(entry.get("rationale", default_rationale))).strip()
            if not rationale:
                raise VerificationEngineError(f"Missing rationale for criterion {cid}.")
        else:
            status = default_status
            rationale = default_rationale

        evaluations.append(
            {
                "criterion_id": cid,
                "criterion_name": cname,
                "status": status,
                "rationale": rationale,
                "citations": [citation_obj],
            }
        )
    return evaluations


def verify_passage(query: str) -> dict[str, Any]:
    """Verify a scripture reference query under the 10-point Γραφή framework.

    Enforces:
    - Exclusion check FIRST (`gate/exclusions.json`)
    - Citation enforcement from `store/` (or explicit exclusion record in `gate/exclusions.json`)
    - Fail-closed verdict (`FAIL`) whenever excluded, uncited/missing in store, or any criterion fails
    - Strict JSON Schema validation against `schema/analysis.json`
    """
    clean_query = normalize_nfc(query).strip()
    rules = load_rules()
    exclusions_data = load_exclusions()
    validator = load_schema_validator()

    eng_book, grk_book, verse_part = parse_reference_query(clean_query)
    normalized_ref = (
        f"{eng_book} {verse_part}".strip() if verse_part else eng_book
    )

    # STEP 1: Check gate/exclusions.json FIRST before evaluating any passage.
    exclusion_hit = check_exclusions_first(eng_book, grk_book, verse_part, exclusions_data)
    stored_match = find_stored_passage(eng_book, grk_book, verse_part)

    if exclusion_hit is not None:
        hit_type = exclusion_hit["exclusion_type"]
        entry = exclusion_hit["entry"]
        reason = normalize_nfc(str(entry.get("reason", "Excluded by framework gate."))).strip()
        failed_ids = sorted(
            {int(x) for x in entry.get("failed_criteria", [5, 8]) if 1 <= int(x) <= 10}
        )
        if not failed_ids:
            failed_ids = [5, 8]

        if hit_type == "book":
            anchor = f"ExcludedBook.{eng_book.replace(' ', '')}"
            greek_sample = validate_greek_text_field(
                str(entry.get("book_greek", grk_book)), "excluded_book.book_greek"
            )
            citation_obj = {
                "file": "gate/exclusions.json",
                "anchor": anchor,
                "greek_excerpt": greek_sample,
            }
            payload: dict[str, Any] = {
                "schema_version": "1.0.0",
                "query": clean_query,
                "normalized_reference": normalized_ref,
                "corpus": "excluded_unknown",
                "source_file": "gate/exclusions.json",
                "verse_anchor": anchor,
                "greek_text": greek_sample,
                "excluded": True,
                "overall_verdict": "FAIL",
                "failed_criteria": failed_ids,
                "failure_reasons": [reason],
                "citations": [citation_obj],
                "morphology": [],
                "criteria_evaluations": _build_criteria_evaluations(
                    rules=rules,
                    stored_evaluations=None,
                    default_status="FAIL",
                    default_rationale=f"Excluded book gate triggered: {reason}",
                    citation_obj=citation_obj,
                ),
            }
        else:
            # Excluded passage: pull cited Greek text and morphology from store if present,
            # while enforcing fail-closed exclusion status.
            anchor = normalize_nfc(str(entry.get("verse_anchor", "ExcludedPassage")))
            if stored_match is not None:
                store_file, store_corpus, passage_obj = stored_match
                greek_text = validate_greek_text_field(
                    str(passage_obj["greek_text"]), "passage.greek_text"
                )
                corpus = store_corpus if store_corpus in {"lxx", "nt"} else "excluded_unknown"
                citation_obj = {
                    "file": store_file,
                    "anchor": anchor,
                    "greek_excerpt": greek_text,
                }
                morph_list: list[dict[str, str]] = []
                for m in passage_obj.get("morphology", []):
                    morph_list.append(
                        {
                            "surface_form": validate_greek_token_field(
                                str(m["surface_form"]), "morphology.surface_form"
                            ),
                            "lemma": validate_greek_token_field(
                                str(m["lemma"]), "morphology.lemma"
                            ),
                            "strongs": normalize_nfc(str(m["strongs"])).strip(),
                            "english_gloss": normalize_nfc(str(m["english_gloss"])).strip(),
                            "source_file": store_file,
                            "verse_anchor": anchor,
                        }
                    )
                stored_evals = passage_obj.get("criteria_evaluations", {})
            else:
                greek_text = validate_greek_text_field(
                    str(entry.get("greek_reference", grk_book)),
                    "excluded_passage.greek_reference",
                )
                corpus = str(entry.get("corpus", "excluded_unknown"))
                if corpus not in {"lxx", "nt", "excluded_unknown"}:
                    corpus = "excluded_unknown"
                citation_obj = {
                    "file": "gate/exclusions.json",
                    "anchor": anchor,
                    "greek_excerpt": greek_text,
                }
                morph_list = []
                stored_evals = None

            payload = {
                "schema_version": "1.0.0",
                "query": clean_query,
                "normalized_reference": normalized_ref,
                "corpus": corpus,
                "source_file": citation_obj["file"],
                "verse_anchor": anchor,
                "greek_text": greek_text,
                "excluded": True,
                "overall_verdict": "FAIL",
                "failed_criteria": failed_ids,
                "failure_reasons": [reason],
                "citations": [citation_obj],
                "morphology": morph_list,
                "criteria_evaluations": _build_criteria_evaluations(
                    rules=rules,
                    stored_evaluations=stored_evals,
                    default_status="FAIL",
                    default_rationale=f"Excluded passage gate triggered: {reason}",
                    citation_obj=citation_obj,
                ),
            }

        _enforce_schema_or_raise(validator, payload)
        return payload

    # STEP 2: No citation, no claim — if not in store/ and not in gate/exclusions.json,
    # fail closed rather than inventing or guessing content.
    if stored_match is None:
        fail_reason = (
            f"No citation found in store/ for reference '{normalized_ref}'. "
            "Fail-closed policy prohibits unverified or uncited claims."
        )
        greek_fallback = validate_greek_text_field(grk_book, "fallback.greek_book")
        citation_obj = {
            "file": "gate/exclusions.json",
            "anchor": f"Uncited.{normalized_ref.replace(' ', '_')}",
            "greek_excerpt": greek_fallback,
        }
        payload = {
            "schema_version": "1.0.0",
            "query": clean_query,
            "normalized_reference": normalized_ref,
            "corpus": "excluded_unknown",
            "source_file": "gate/exclusions.json",
            "verse_anchor": citation_obj["anchor"],
            "greek_text": greek_fallback,
            "excluded": False,
            "overall_verdict": "FAIL",
            "failed_criteria": [5],
            "failure_reasons": [fail_reason],
            "citations": [citation_obj],
            "morphology": [],
            "criteria_evaluations": _build_criteria_evaluations(
                rules=rules,
                stored_evaluations=None,
                default_status="FAIL",
                default_rationale=fail_reason,
                citation_obj=citation_obj,
            ),
        }
        _enforce_schema_or_raise(validator, payload)
        return payload

    # STEP 3: Evaluate stored passage against all 10 criteria (fail-closed on any FAIL).
    store_file, corpus, passage_obj = stored_match
    if corpus not in {"lxx", "nt"}:
        raise VerificationEngineError(f"Invalid corpus '{corpus}' in {store_file}.")

    anchor = normalize_nfc(str(passage_obj["verse_anchor"])).strip()
    greek_text = validate_greek_text_field(str(passage_obj["greek_text"]), "passage.greek_text")
    citation_obj = {
        "file": store_file,
        "anchor": anchor,
        "greek_excerpt": greek_text,
    }

    morph_entries: list[dict[str, str]] = []
    for m in passage_obj.get("morphology", []):
        morph_entries.append(
            {
                "surface_form": validate_greek_token_field(
                    str(m["surface_form"]), "morphology.surface_form"
                ),
                "lemma": validate_greek_token_field(str(m["lemma"]), "morphology.lemma"),
                "strongs": normalize_nfc(str(m["strongs"])).strip(),
                "english_gloss": normalize_nfc(str(m["english_gloss"])).strip(),
                "source_file": store_file,
                "verse_anchor": anchor,
            }
        )

    stored_evals = passage_obj.get("criteria_evaluations")
    if not isinstance(stored_evals, dict):
        raise VerificationEngineError(
            f"Passage '{anchor}' in '{store_file}' is missing criteria_evaluations."
        )

    criteria_list = _build_criteria_evaluations(
        rules=rules,
        stored_evaluations=stored_evals,
        default_status="FAIL",
        default_rationale="Missing criterion evaluation in store; failing closed.",
        citation_obj=citation_obj,
    )

    failed_criteria: list[int] = []
    failure_reasons: list[str] = []
    for item in criteria_list:
        if item["status"] == "FAIL":
            cid = int(item["criterion_id"])
            failed_criteria.append(cid)
            failure_reasons.append(
                f"Criterion {cid} ({item['criterion_name']}) FAILED: {item['rationale']}"
            )

    overall_verdict = "FAIL" if failed_criteria else "PASS"

    payload = {
        "schema_version": "1.0.0",
        "query": clean_query,
        "normalized_reference": normalized_ref,
        "corpus": corpus,
        "source_file": store_file,
        "verse_anchor": anchor,
        "greek_text": greek_text,
        "excluded": False,
        "overall_verdict": overall_verdict,
        "failed_criteria": failed_criteria,
        "failure_reasons": failure_reasons,
        "citations": [citation_obj],
        "morphology": morph_entries,
        "criteria_evaluations": criteria_list,
    }

    _enforce_schema_or_raise(validator, payload)
    return payload


def _enforce_schema_or_raise(validator: Draft202012Validator, payload: dict[str, Any]) -> None:
    """Validate payload against schema/analysis.json or raise a clear VerificationEngineError."""
    errors = sorted(validator.iter_errors(payload), key=lambda err: list(err.path))
    if errors:
        formatted = "; ".join(
            f"{'/'.join(str(p) for p in err.path) or '<root>'}: {err.message}"
            for err in errors
        )
        raise VerificationEngineError(
            f"Output failed schema/analysis.json validation: {formatted}"
        )


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for verifying a Greek or English scripture reference."""
    parser = argparse.ArgumentParser(
        description="Verify a scripture reference against the 10-point Γραφή Verification Framework."
    )
    parser.add_argument(
        "reference",
        help="Scripture reference in English or Greek (e.g., 'John 6:63' or 'Ἰωάννης 6:63').",
    )
    args = parser.parse_args(argv)

    try:
        result = verify_passage(args.reference)
    except (VerificationEngineError, ValidationError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["overall_verdict"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
