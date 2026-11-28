import re
import sys
import unicodedata
from pathlib import Path
import pymupdf

VERSE_MARKER_RE = re.compile(r"^(\d+):(\d+)$")
STRONG_NUM_RE = re.compile(r"^\d+(?:[.-]\d+)*$")

NEWPORT_BASE_MAP = {
    "a": "α", "b": "β", "g": "γ", "d": "δ", "e": "ε", "z": "ζ",
    "h": "η", "q": "θ", "i": "ι", "k": "κ", "l": "λ", "m": "μ",
    "n": "ν", "c": "ξ", "o": "ο", "p": "π", "r": "ρ", "s": "σ",
    "V": "ς", "t": "τ", "u": "υ", "y": "ψ", "f": "φ", "x": "χ", "w": "ω",
    "A": "Α", "B": "Β", "G": "Γ", "D": "Δ", "E": "Ε", "Z": "Ζ",
    "H": "Η", "Q": "Θ", "I": "Ι", "K": "Κ", "L": "Λ", "M": "Μ",
    "N": "Ν", "C": "Ξ", "P": "Π", "R": "Ρ", "S": "Σ", "T": "Τ",
    "U": "Υ", "F": "Φ", "X": "Χ", "W": "Ω",
}

GREEK_VOWELS_FOR_BREATHING = {
    "α": "ἀ", "ε": "ἐ", "η": "ἠ", "ι": "ἰ", "ο": "ὀ", "υ": "ὐ", "ω": "ὠ",
    "Α": "Ἀ", "Ε": "Ἐ", "Η": "Ἠ", "Ι": "Ἰ", "Ο": "Ὀ", "Υ": "Υ", "Ω": "Ὠ",
}


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s).strip()


def decode_newport_greek(raw: str) -> str:
    """Convert legacy Newport font text into Unicode Greek, handling '¢' diacritic markers."""
    s = nfc(raw)
    out_chars: list[str] = []
    pending_accent_or_breathing = False

    for ch in s:
        if ch == "¢":
            # Apply smooth breathing + acute on preceding or upcoming vowel when possible
            if out_chars and out_chars[-1] in GREEK_VOWELS_FOR_BREATHING:
                base = out_chars[-1]
                out_chars[-1] = unicodedata.normalize("NFC", GREEK_VOWELS_FOR_BREATHING[base] + "\u0301")
            else:
                pending_accent_or_breathing = True
            continue

        mapped = NEWPORT_BASE_MAP.get(ch, ch)
        if pending_accent_or_breathing and mapped in GREEK_VOWELS_FOR_BREATHING:
            mapped = unicodedata.normalize("NFC", GREEK_VOWELS_FOR_BREATHING[mapped] + "\u0301")
            pending_accent_or_breathing = False
        elif pending_accent_or_breathing and mapped in "αεηιουωΑΕΗΙΟΥΩ":
            mapped = unicodedata.normalize("NFC", mapped + "\u0301")
            pending_accent_or_breathing = False

        out_chars.append(mapped)

    result = "".join(out_chars)
    # Fix final sigma if 'σ' sits at the end of a word
    result = re.sub(r"σ(?=$|[\s,.;·'’\"“”()\[\]])", "ς", result)
    return unicodedata.normalize("NFC", result)


def extract_interlinear_verses(
    pdf_path: Path,
    book_name: str,
    start_page: int,
    end_page: int,
    out_txt: Path,
) -> None:
    doc = pymupdf.open(pdf_path)
    verses: dict[tuple[int, int], dict[str, list[str]]] = {}
    current_cv: tuple[int, int] | None = None

    for pno in range(start_page - 1, min(end_page, len(doc))):
        page = doc[pno]
        mid_x = page.rect.width / 2.0
        page_dict = page.get_text("dict")

        # Collect spans: (x0, y0, font, text)
        spans_list: list[tuple[float, float, str, str]] = []
        for b in page_dict.get("blocks", []):
            if "lines" not in b:
                continue
            for l in b["lines"]:
                for s in l.get("spans", []):
                    txt = nfc(s.get("text", ""))
                    if not txt:
                        continue
                    x0, y0, _, _ = s["bbox"]
                    spans_list.append((x0, y0, s.get("font", ""), txt))

        left_spans = [sp for sp in spans_list if sp[0] < mid_x]
        right_spans = [sp for sp in spans_list if sp[0] >= mid_x]

        for col_spans in (left_spans, right_spans):
            col_sorted = sorted(col_spans, key=lambda sp: (round(sp[1] / 3.5), sp[0]))
            rows: list[list[tuple[float, float, str, str]]] = []
            for sp in col_sorted:
                if not rows or abs(sp[1] - rows[-1][0][1]) > 3.5:
                    rows.append([sp])
                else:
                    rows[-1].append(sp)
            for r in rows:
                r.sort(key=lambda sp: sp[0])

            for r in rows:
                for _, _, font, txt in r:
                    m = VERSE_MARKER_RE.match(txt)
                    if m:
                        current_cv = (int(m.group(1)), int(m.group(2)))
                        verses.setdefault(current_cv, {"greek": [], "english": []})

                if current_cv is None:
                    continue

                for _, _, font, txt in r:
                    if VERSE_MARKER_RE.match(txt) or STRONG_NUM_RE.match(txt):
                        continue
                    if font == "Newport":
                        # Skip isolated single-letter manuscript sigla like O, U, A, H, N
                        if txt in {"O", "U", "A", "H", "N"}:
                            continue
                        for part in txt.split():
                            decoded = decode_newport_greek(part)
                            if decoded:
                                verses[current_cv]["greek"].append(decoded)
                    elif font.startswith("TimesTen") or font == "Times-Roman":
                        if txt in {"CP", "Ald."}:
                            continue
                        verses[current_cv]["english"].append(txt)

    lines_out: list[str] = []
    for (chap, ver) in sorted(verses.keys()):
        grk = " ".join(verses[(chap, ver)]["greek"]).strip()
        eng = " ".join(verses[(chap, ver)]["english"]).strip()
        eng = re.sub(r"\s+([,.;:!?])", r"\1", eng)
        if grk or eng:
            lines_out.append(f"{book_name}|{chap}|{ver}|{grk}|{eng}")

    out_txt.write_text("\n".join(lines_out) + ("\n" if lines_out else ""), encoding="utf-8")
    print(f"Wrote {len(lines_out)} verses for {book_name} to {out_txt}")


if __name__ == "__main__":
    if len(sys.argv) != 6:
        print(
            "Usage: python extract_abp_nt.py <pdf_path> <BookName> <start_page> <end_page> <out_txt>"
        )
        raise SystemExit(1)
    extract_interlinear_verses(
        Path(sys.argv[1]),
        sys.argv[2],
        int(sys.argv[3]),
        int(sys.argv[4]),
        Path(sys.argv[5]),
    )