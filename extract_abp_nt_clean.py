from __future__ import annotations

import re
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

VERSE_MARKER_RE = re.compile(r"^(\d+):(\d+)$")
STRONG_OR_NUM_RE = re.compile(r"^\d+(?:[.-]\d+)*$")

NEWPORT_CHAR_MAP: dict[str, str] = {
    "a": "α", "b": "β", "g": "γ", "d": "δ", "e": "ε", "z": "ζ",
    "h": "η", "q": "θ", "i": "ι", "k": "κ", "l": "λ", "m": "μ",
    "n": "ν", "c": "ξ", "o": "ο", "p": "π", "r": "ρ", "s": "σ",
    "V": "ς", "t": "τ", "u": "υ", "y": "ψ", "f": "φ", "x": "χ", "w": "ω",
    "A": "Α", "B": "Β", "G": "Γ", "D": "Δ", "E": "Ε", "Z": "Ζ",
    "H": "Η", "Q": "Θ", "I": "Ι", "K": "Κ", "L": "Λ", "M": "Μ",
    "N": "Ν", "C": "Ξ", "P": "Π", "R": "Ρ", "S": "Σ", "T": "Τ",
    "U": "Υ", "F": "Φ", "X": "Χ", "W": "Ω",
}

SMOOTH_BREATHING_ACUTE: dict[str, str] = {
    "α": "ἄ", "ε": "ἔ", "η": "ἤ", "ι": "ἴ", "ο": "ὅ", "υ": "ὔ", "ω": "ὤ",
    "Α": "Ἄ", "Ε": "Ἔ", "Η": "Ἤ", "Ι": "Ἴ", "Ο": "Ὅ", "Υ": "Ὕ", "Ω": "Ὤ",
}

ALL_GREEK_VOWELS = set("αεηιουωΑΕΗΙΟΥΩἄἔἤἴὅὔὤἌἜἬἼὍὝὬ")
MANUSCRIPT_SIGLA = {"O", "U", "A", "H", "N"}
APPARATUS_TOKENS = {"CP", "Ald.", "†", "*"}


@dataclass
class SpanItem:
    x0: float
    y0: float
    x1: float
    font: str
    text: str


@dataclass
class VerseBuffer:
    greek_chunks: list[tuple[float, float, str]] = field(default_factory=list)
    english_chunks: list[tuple[float, float, str]] = field(default_factory=list)


def normalize_nfc(value: str) -> str:
    return unicodedata.normalize("NFC", value).strip()


def decode_newport_segment(segment: str) -> str:
    """Decode a Newport font segment into normalized NFC Unicode Greek."""
    cleaned = re.sub(r"\s*¢\s*", "¢", normalize_nfc(segment))
    if not cleaned:
        return ""

    chars: list[str] = []
    apply_next_vowel = False

    for ch in cleaned:
        if ch == "¢":
            if chars and chars[-1] in SMOOTH_BREATHING_ACUTE:
                chars[-1] = unicodedata.normalize(
                    "NFC", SMOOTH_BREATHING_ACUTE[chars[-1]]
                )
            else:
                apply_next_vowel = True
            continue

        mapped = NEWPORT_CHAR_MAP.get(ch, ch)
        if apply_next_vowel and mapped in SMOOTH_BREATHING_ACUTE:
            mapped = unicodedata.normalize("NFC", SMOOTH_BREATHING_ACUTE[mapped])
            apply_next_vowel = False
        elif apply_next_vowel and mapped in ALL_GREEK_VOWELS:
            mapped = unicodedata.normalize("NFC", mapped + "\u0301")
            apply_next_vowel = False

        chars.append(mapped)

    text = "".join(chars)
    text = re.sub(r"σ(?=$|[\s,.;·'’\"“”()\[\]])", "ς", text)
    return unicodedata.normalize("NFC", text)


def merge_greek_chunks(chunks: list[tuple[float, float, str]]) -> str:
    """Join decoded Greek chunks, avoiding artificial spaces when spans touch closely."""
    if not chunks:
        return ""

    parts: list[str] = []
    prev_x1: float | None = None
    prev_y0: float | None = None

    for x0, y0, piece in chunks:
        piece = normalize_nfc(piece)
        if not piece:
            continue

        if not parts:
            parts.append(piece)
        else:
            same_line = prev_y0 is not None and abs(y0 - prev_y0) <= 3.5
            gap = (x0 - prev_x1) if (same_line and prev_x1 is not None) else 999.0
            # Close small horizontal gaps between adjacent syllables of the same word
            if same_line and 0 <= gap <= 2.2 and not parts[-1].endswith(("'", "’")):
                parts[-1] = unicodedata.normalize("NFC", parts[-1] + piece)
            else:
                parts.append(piece)

        prev_x1 = x0 + max(len(piece) * 4.0, 4.0)
        prev_y0 = y0

    joined = " ".join(parts)
    joined = re.sub(r"\s+([,.;·:!?])", r"\1", joined)
    return unicodedata.normalize("NFC", joined).strip()


def merge_english_chunks(chunks: list[tuple[float, float, str]]) -> str:
    """Join English gloss/text chunks cleanly."""
    if not chunks:
        return ""

    raw = " ".join(normalize_nfc(piece) for _, _, piece in chunks if normalize_nfc(piece))
    raw = re.sub(r"\s+([,.;:!?\]\)])", r"\1", raw)
    raw = re.sub(r"([\[\(])\s+", r"\1", raw)
    return normalize_nfc(raw)


def collect_page_spans(page: pymupdf.Page) -> list[SpanItem]:
    page_dict = page.get_text("dict")
    items: list[SpanItem] = []

    for block in page_dict.get("blocks", []):
        if "lines" not in block:
            continue
        for line in block["lines"]:
            for span in line.get("spans", []):
                txt = normalize_nfc(span.get("text", ""))
                if not txt:
                    continue
                x0, y0, x1, _ = span["bbox"]
                items.append(
                    SpanItem(
                        x0=float(x0),
                        y0=float(y0),
                        x1=float(x1),
                        font=str(span.get("font", "")),
                        text=txt,
                    )
                )
    return items


def group_into_rows(spans: list[SpanItem], y_tol: float = 3.5) -> list[list[SpanItem]]:
    ordered = sorted(spans, key=lambda s: (round(s.y0 / y_tol), s.x0))
    rows: list[list[SpanItem]] = []
    for sp in ordered:
        if not rows or abs(sp.y0 - rows[-1][0].y0) > y_tol:
            rows.append([sp])
        else:
            rows[-1].append(sp)
    for row in rows:
        row.sort(key=lambda s: s.x0)
    return rows


def extract_book(
    pdf_path: Path,
    book_name: str,
    start_page: int,
    end_page: int,
    output_txt: Path,
) -> None:
    doc = pymupdf.open(pdf_path)
    verses: dict[tuple[int, int], VerseBuffer] = {}
    current_cv: tuple[int, int] | None = None

    last_page = min(end_page, len(doc))
    for page_idx in range(start_page - 1, last_page):
        page = doc[page_idx]
        mid_x = page.rect.width / 2.0
        spans = collect_page_spans(page)

        left_col = [s for s in spans if s.x0 < mid_x]
        right_col = [s for s in spans if s.x0 >= mid_x]

        for col in (left_col, right_col):
            for row in group_into_rows(col):
                # Detect chapter:verse markers on the row
                for sp in row:
                    match = VERSE_MARKER_RE.match(sp.text)
                    if match:
                        current_cv = (int(match.group(1)), int(match.group(2)))
                        verses.setdefault(current_cv, VerseBuffer())

                if current_cv is None:
                    continue

                buf = verses[current_cv]
                for sp in row:
                    txt = sp.text
                    if VERSE_MARKER_RE.match(txt) or STRONG_OR_NUM_RE.match(txt):
                        continue
                    if txt in APPARATUS_TOKENS:
                        continue

                    if sp.font == "Newport":
                        if txt in MANUSCRIPT_SIGLA:
                            continue
                        decoded = decode_newport_segment(txt)
                        if decoded:
                            buf.greek_chunks.append((sp.x0, sp.y0, decoded))
                    elif sp.font.startswith("TimesTen") or sp.font in {"Times-Roman", "Times-Italic"}:
                        buf.english_chunks.append((sp.x0, sp.y0, txt))

    out_lines: list[str] = []
    for chap, ver in sorted(verses.keys()):
        buf = verses[(chap, ver)]
        greek_str = merge_greek_chunks(buf.greek_chunks)
        english_str = merge_english_chunks(buf.english_chunks)
        if greek_str or english_str:
            out_lines.append(f"{book_name}|{chap}|{ver}|{greek_str}|{english_str}")

    output_txt.write_text(
        "\n".join(out_lines) + ("\n" if out_lines else ""),
        encoding="utf-8",
    )
    print(f"Wrote {len(out_lines)} verses for {book_name} -> {output_txt}")


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 5:
        print(
            "Usage: python extract_abp_nt_clean.py <pdf_path> <BookName> <start_page> <end_page> <out_txt>",
            file=sys.stderr,
        )
        return 1

    extract_book(
        pdf_path=Path(args[0]),
        book_name=args[1],
        start_page=int(args[2]),
        end_page=int(args[3]),
        output_txt=Path(args[4]),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())