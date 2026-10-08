"""Read an uploaded ID card: crop the holder's photo and suggest details from the printed text.

Nothing here changes a borrower record. Staff see the photo and the suggestions, check them
against the card, and choose what to keep. The heavy libraries (OpenCV, Tesseract, PDFium) are
optional: without them the scan still returns what it can, and says what it couldn't do.
"""

from __future__ import annotations

import io
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import date
from typing import Any

log = logging.getLogger("mclender.idcard")

PHOTO_SIZE = (300, 375)  # 4:5 portrait, enough for a profile and small enough to store
OCR_BUDGET_SECONDS = 25.0
MAX_PIXELS = 40_000_000  # refuse decompression bombs


class ScanError(Exception):
    pass


@dataclass
class IdSuggestions:
    national_id: str | None = None  # only from a national ID card, never a passport or licence number
    first_name: str | None = None
    last_name: str | None = None
    date_of_birth: date | None = None
    gender: str | None = None  # "female" | "male"
    document_type: str | None = None  # "passport" | "national_id" | "licence" when it can tell
    document_number: str | None = None  # the passport or licence number


@dataclass
class IdScan:
    photo: bytes | None = None  # JPEG portrait, or None when no face was found
    suggestions: IdSuggestions = field(default_factory=IdSuggestions)
    text_read: bool = False
    problems: list[str] = field(default_factory=list)


# ----------------------------------------------------------------- image
def _open(data: bytes) -> Any:
    """A JPEG or PNG, refused before decoding if it would unpack to more than MAX_PIXELS (a small file can
    hold a huge picture)."""
    from PIL import Image

    try:
        img = Image.open(io.BytesIO(data), formats=["JPEG", "PNG"])
    except Exception as e:
        raise ScanError("This picture couldn't be opened.") from e
    if img.width * img.height > MAX_PIXELS:
        raise ScanError("This picture is too large. Use a photo under 40 megapixels.")
    try:
        img.load()
    except Exception as e:
        raise ScanError("This picture couldn't be opened.") from e
    return img


def pdf_pages(data: bytes, limit: int = 2) -> list[tuple[Any, str]]:
    """The first pages of a PDF as (RGB image, text layer). A scanned PDF has no text layer (""); a PDF made
    on a computer has one, which is more accurate than reading the picture."""
    try:
        import pypdfium2 as pdfium
    except ImportError as e:
        raise ScanError("Reading a PDF needs pypdfium2. Upload a photo of the card instead.") from e
    out: list[tuple[Any, str]] = []
    try:
        pdf = pdfium.PdfDocument(data)
    except Exception as e:  # damaged, or protected with a password
        raise ScanError("This PDF couldn't be opened. If it has a password, upload a copy without one.") from e
    try:
        for i in range(min(limit, len(pdf))):
            page = pdf[i]
            try:
                # About 3000 px on the long side: a passport page scanned on A4 still has readable text.
                w, h = page.get_size()
                scale = min(6.0, 3000 / max(w, h, 1))
                img = page.render(scale=scale).to_pil().convert("RGB")
                textpage = page.get_textpage()
                try:
                    text = textpage.get_text_range() or ""
                finally:
                    textpage.close()
            finally:
                page.close()
            out.append((img, text))
    except Exception as e:
        raise ScanError("This PDF couldn't be read.") from e
    finally:
        pdf.close()
    if not out:
        raise ScanError("This PDF has no pages.")
    return out


def load_image(data: bytes, content_type: str) -> Any:
    """The card as an RGB PIL image. A PDF is rendered from its first page."""
    from PIL import Image

    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    if content_type == "application/pdf":
        return pdf_pages(data, limit=1)[0][0]
    img = _open(data)
    from PIL import ImageOps

    img = ImageOps.exif_transpose(img)  # phone photos are often stored sideways
    return img.convert("RGB")


def find_face(img: Any) -> tuple[int, int, int, int] | None:
    """The largest face on the card as (x, y, w, h), or None."""
    import cv2 as _cv2
    import numpy as np

    cv2: Any = _cv2  # OpenCV's type stubs miss CascadeClassifier and cv2.data

    grey = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2GRAY)
    long_side = max(grey.shape)
    ratio = 1.0
    if long_side > 1600:  # detection is quicker and no worse on a smaller copy
        ratio = 1600 / long_side
        grey = cv2.resize(grey, None, fx=ratio, fy=ratio, interpolation=cv2.INTER_AREA)
    grey = cv2.equalizeHist(grey)
    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    smallest = max(32, int(min(grey.shape) * 0.04))  # a passport photo on an A4 scan is small
    faces = cascade.detectMultiScale(grey, scaleFactor=1.1, minNeighbors=6, minSize=(smallest, smallest))
    if len(faces) == 0:
        return None
    x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
    return int(x / ratio), int(y / ratio), int(w / ratio), int(h / ratio)


def crop_portrait(img: Any, box: tuple[int, int, int, int]) -> bytes:
    """Head and shoulders around the face, 4:5, as a JPEG."""
    x, y, w, h = box
    cx, cy = x + w / 2, y + h / 2 + h * 0.15  # a little below the face centre, to include the chin and neck
    out_h = h * 2.0
    out_w = out_h * PHOTO_SIZE[0] / PHOTO_SIZE[1]
    left, top = max(0, cx - out_w / 2), max(0, cy - out_h / 2)
    right, bottom = min(img.width, left + out_w), min(img.height, top + out_h)
    crop = img.crop((int(left), int(top), int(right), int(bottom)))
    from PIL import Image

    crop.thumbnail((PHOTO_SIZE[0] * 2, PHOTO_SIZE[1] * 2))
    canvas = crop.resize(PHOTO_SIZE, Image.Resampling.LANCZOS) if crop.width >= 60 else crop
    buf = io.BytesIO()
    canvas.save(buf, "JPEG", quality=88)
    return buf.getvalue()


def read_text(img: Any, psm: int = 6, timeout: float = OCR_BUDGET_SECONDS) -> str | None:
    """The card's printed text, or None when Tesseract isn't installed."""
    try:
        import pytesseract
    except ImportError:
        return None
    try:
        grey = img.convert("L")
        if max(grey.size) > 3000:  # bigger is slower without reading better
            grey.thumbnail((3000, 3000))
        if max(grey.size) < 1400:  # small photos read better enlarged
            f = 1400 / max(grey.size)
            grey = grey.resize((int(grey.width * f), int(grey.height * f)))
        return str(pytesseract.image_to_string(grey, config=f"--psm {psm}", timeout=timeout))
    except (pytesseract.TesseractNotFoundError, OSError):
        return None
    except RuntimeError:  # timed out
        log.warning("Reading the ID card text took too long")
        return ""


# ----------------------------------------------------------------- passports (machine-readable zone)
def _mrz_lines(text: str) -> list[str]:
    """The two (passport) or three (ID card) lines of <<< code at the bottom of the document."""
    out = []
    for raw in text.splitlines():
        line = raw.upper().replace("«", "<").replace(" ", "").replace("‹", "<")
        line = re.sub(r"[^A-Z0-9<]", "", line)
        if len(line) >= 28 and line.count("<") >= 2:
            out.append(line)
    return out


def _mrz_date(yymmdd: str, past: bool = True) -> date | None:
    digits = yymmdd.replace("O", "0").replace("I", "1")
    if not re.fullmatch(r"\d{6}", digits):
        return None
    yy, mm, dd = int(digits[:2]), int(digits[2:4]), int(digits[4:])
    century = 2000 if 2000 + yy <= date.today().year else 1900
    try:
        return date(century + yy if past else 2000 + yy, mm, dd)
    except ValueError:
        return None


def _mrz_names(field_: str) -> tuple[str | None, str | None]:
    surname, _, given = field_.partition("<<")
    tidy = lambda v: " ".join(w.capitalize() for w in v.replace("<", " ").split()) or None  # noqa: E731
    return tidy(given), tidy(surname)


def parse_mrz(text: str) -> IdSuggestions | None:
    """Details from a passport's machine-readable zone (ICAO 9303 TD3), or a TD1 ID card's."""
    lines = _mrz_lines(text)
    for i in range(len(lines) - 1):
        a, b = lines[i], lines[i + 1]
        if a.startswith("P") and len(b) >= 28:  # passport: P<PNGSURNAME<<GIVEN<NAMES / number, dob, sex
            first, last = _mrz_names(a[5:])
            number = b[0:9].replace("<", "") or None
            sex = b[20:21]
            return IdSuggestions(
                first_name=first,
                last_name=last,
                date_of_birth=_mrz_date(b[13:19]),
                gender="female" if sex == "F" else "male" if sex == "M" else None,
                document_type="passport",
                document_number=number,
            )
        if a[:1] in "IAC" and i + 2 < len(lines):  # ID card, three lines
            c = lines[i + 2]
            first, last = _mrz_names(c)
            sex = b[7:8]
            return IdSuggestions(
                first_name=first,
                last_name=last,
                date_of_birth=_mrz_date(b[0:6]),
                gender="female" if sex == "F" else "male" if sex == "M" else None,
                document_type="national_id",
                document_number=a[5:14].replace("<", "") or None,
            )
    return None


# ----------------------------------------------------------------- text
MONTHS = {
    m: i
    for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)
}
_DATE = re.compile(r"\b(\d{1,2})[\s./-]+([A-Za-z]{3,9}|\d{1,2})[\s./-]+(\d{4})\b")
_LABELS = {
    "last_name": re.compile(r"\b(surname|last\s*name|family\s*name)\b", re.I),
    "first_name": re.compile(r"\b(given\s*names?|first\s*names?|other\s*names?|forenames?)\b", re.I),
    "full_name": re.compile(r"^\s*(full\s*)?name\b", re.I),
    "dob": re.compile(r"\b(date\s*of\s*birth|birth\s*date|d\.?\s*o\.?\s*b)\b", re.I),
    "sex": re.compile(r"\b(sex|gender)\b", re.I),
    "nid": re.compile(r"\b(nid|national\s*id(entity)?|id\s*(no|number|num)|card\s*(no|number)|pin)\b", re.I),
}


def _after_label(lines: list[str], i: int, label: re.Pattern[str], shortest: int = 2) -> str:
    """The value on a labelled line ("Surname: KILA"), or on the next line when the label stands alone."""
    rest = label.split(lines[i], maxsplit=1)[-1]
    rest = re.sub(r"^[\s:.\-|/]+", "", rest)
    rest = re.sub(r"^(no|number)\b[\s:.]*", "", rest, flags=re.I).strip()
    if len(re.sub(r"[^A-Za-z0-9]", "", rest)) >= shortest:
        return rest
    return lines[i + 1].strip() if i + 1 < len(lines) else ""


def _name(value: str) -> str | None:
    words = re.findall(r"[A-Za-z][A-Za-z'\-]+", value)
    words = [w for w in words if w.lower() not in {"name", "names", "surname", "given", "first", "sex"}]
    if not words:
        return None
    return " ".join(w.capitalize() if w.isupper() or w.islower() else w for w in words[:3])


def parse_date(value: str) -> date | None:
    for d, m, y in _DATE.findall(value):
        month = int(m) if m.isdigit() else MONTHS.get(m[:3].lower())
        try:
            when = date(int(y), month or 0, int(d))
        except ValueError:
            continue
        if 1900 < when.year <= date.today().year:
            return when
    return None


def parse_card_text(text: str) -> IdSuggestions:
    """Best guesses from an ID card's text (PNG NID card, driver's licence or passport). Every value is a
    suggestion for staff to check, never written without them."""
    found = _parse_labels(text)
    mrz = parse_mrz(text)
    if mrz:  # the machine-readable zone is the most reliable; printed labels fill any gaps
        for k, v in vars(found).items():
            if getattr(mrz, k) is None and k != "national_id":
                setattr(mrz, k, v)
        return mrz
    if re.search(r"\bpassport\b", text, re.I):
        found.document_type = "passport"
        found.document_number, found.national_id = found.national_id, None
    elif re.search(r"\b(driver|driving|licen[cs]e)\b", text, re.I):
        found.document_type = "licence"
        found.document_number, found.national_id = found.national_id, None
    elif found.national_id:
        found.document_type = "national_id"
    return found


def _parse_labels(text: str) -> IdSuggestions:
    out = IdSuggestions()
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    for i, line in enumerate(lines):
        if out.last_name is None and _LABELS["last_name"].search(line):
            out.last_name = _name(_after_label(lines, i, _LABELS["last_name"]))
        elif out.first_name is None and _LABELS["first_name"].search(line):
            out.first_name = _name(_after_label(lines, i, _LABELS["first_name"]))
        elif out.first_name is None and out.last_name is None and _LABELS["full_name"].search(line):
            full = _name(_after_label(lines, i, _LABELS["full_name"]))
            if full and " " in full:
                *first, last = full.split()
                out.first_name, out.last_name = " ".join(first), last
        if out.date_of_birth is None and _LABELS["dob"].search(line):
            out.date_of_birth = parse_date(_after_label(lines, i, _LABELS["dob"])) or parse_date(line)
        if out.gender is None and _LABELS["sex"].search(line):
            v = _after_label(lines, i, _LABELS["sex"], shortest=1).strip().upper()
            if v.startswith(("F", "FEMALE")):
                out.gender = "female"
            elif v.startswith(("M", "MALE")):
                out.gender = "male"
        if out.national_id is None and _LABELS["nid"].search(line):
            out.national_id = _number(_after_label(lines, i, _LABELS["nid"]))
    if out.national_id is None:  # no label read: the longest run of digits that isn't a date
        runs = [r for r in re.findall(r"\d[\d -]{6,}\d", text) if not _DATE.search(r)]
        best = max((r for r in runs if 8 <= len(re.sub(r"\D", "", r)) <= 16), key=len, default=None)
        out.national_id = _number(best) if best else None
    if out.date_of_birth is None:  # the earliest plausible date on the card is usually the birth date
        dates = [d for d in (parse_date(m.group(0)) for m in _DATE.finditer(text)) if d]
        adult = [d for d in dates if (date.today() - d).days > 18 * 365]
        out.date_of_birth = min(adult) if adult else None
    return out


def _number(value: str | None) -> str | None:
    if not value:
        return None
    m = re.search(r"[A-Z]{0,2}\d[\d -]{5,}\d", value.upper())
    if not m:
        return None
    clean = re.sub(r"[\s-]+", " ", m.group(0)).strip()
    return clean if 6 <= len(re.sub(r"\D", "", clean)) <= 16 else None


def clean_photo(data: bytes) -> bytes:
    """Any JPEG or PNG re-drawn as a plain portrait JPEG: no metadata or anything else rides along."""
    from PIL import Image, ImageOps

    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    if not (data.startswith(b"\xff\xd8\xff") or data.startswith(b"\x89PNG\r\n\x1a\n")):
        raise ScanError("The photo must be a JPEG or PNG picture.")
    img = _open(data)
    portrait = ImageOps.fit(ImageOps.exif_transpose(img).convert("RGB"), PHOTO_SIZE, Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    portrait.save(buf, "JPEG", quality=88)
    return buf.getvalue()


# ----------------------------------------------------------------- scan
def _score(s: IdSuggestions) -> int:
    return sum(v is not None for v in vars(s).values())


def _read(
    img: Any, pdf_text: str = "", layouts: tuple[int, ...] = (6, 11), deadline: float | None = None
) -> tuple[IdSuggestions, bool]:
    """The best reading of one page: its PDF text layer if it has one, else OCR in two layouts. Returns
    (suggestions, whether text reading is installed)."""
    best = parse_card_text(pdf_text) if pdf_text.strip() else IdSuggestions()
    if _score(best) >= 4:
        return best, True
    available = True
    for psm in layouts:  # 6: a block of text (labels, the passport code); 11: scattered words on a card
        remaining = deadline - time.monotonic() if deadline is not None else OCR_BUDGET_SECONDS
        if remaining <= 0:
            break
        text = read_text(img, psm, timeout=remaining)
        if text is None:
            available = False
            break
        found = parse_card_text(text)
        if _score(found) > _score(best):
            best = found
        if _score(best) >= 4:
            break
    return best, available


def _turns(img: Any) -> list[Any]:
    return [img, img.rotate(90, expand=True), img.rotate(270, expand=True), img.rotate(180, expand=True)]


def scan(data: bytes, content_type: str) -> IdScan:
    out = IdScan()
    deadline = time.monotonic() + OCR_BUDGET_SECONDS
    pdf = content_type == "application/pdf"
    pages = pdf_pages(data) if pdf else [(load_image(data, content_type), "")]

    face_ok = True
    text_ok = True
    best = IdSuggestions()
    for img, pdf_text in pages:
        # A scan is often sideways or upside down: try each way round until the face and the text are found.
        for turned in _turns(img):
            if out.photo is None and face_ok:
                try:
                    box = find_face(turned)
                except ImportError:
                    face_ok = False
                    box = None
                if box:
                    out.photo = crop_portrait(turned, box)
            if _score(best) < 4 and text_ok:
                upright = turned is img
                found, text_ok = _read(turned, pdf_text if upright else "", (6, 11) if upright else (6,), deadline)
                if _score(found) > _score(best):
                    best = found
            if out.photo is not None and (_score(best) >= 4 or not text_ok):
                break
        if out.photo is not None and _score(best) >= 4:
            break

    if not face_ok:
        out.problems.append("Face finding isn't installed on this server (opencv-python-headless).")
    elif out.photo is None:
        out.problems.append("No face was found. Use a clear, straight scan or photo of the page with the photo.")
    if not text_ok and _score(best) == 0:
        out.problems.append("Text reading isn't installed on this server (Tesseract), so no details were read.")
    else:
        out.suggestions = best
        out.text_read = _score(best) > 0
        if not out.text_read:
            out.problems.append("No details could be read. Type them in from the document.")
    return out
