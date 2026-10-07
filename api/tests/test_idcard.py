import io
import shutil
from datetime import date

import pytest
from PIL import Image, ImageDraw, ImageFont

from app.domain import idcard

PNG_NID = """PAPUA NEW GUINEA
NATIONAL IDENTITY CARD
NID No: 2011 0488 7712
Surname: WAMBI
Given Names: PETER JOHN
Sex: M
Date of Birth: 14/03/1986
Date of Issue: 02/05/2019
"""

LICENCE = """DRIVER LICENCE
Name
MARY KILA
Licence No 88120455
DOB 07 Jun 1990
Expiry 07 Jun 2027
"""


def test_reads_a_png_nid_card():
    s = idcard.parse_card_text(PNG_NID)
    assert s.national_id == "2011 0488 7712"
    assert (s.first_name, s.last_name) == ("Peter John", "Wambi")
    assert s.gender == "male" and s.date_of_birth == date(1986, 3, 14)


def test_reads_a_licence_with_labels_on_their_own_lines():
    s = idcard.parse_card_text(LICENCE)
    assert (s.first_name, s.last_name) == ("Mary", "Kila")
    assert s.date_of_birth == date(1990, 6, 7)  # the earliest adult date, not the expiry
    assert s.national_id == "88120455"


def test_rubbish_text_suggests_nothing():
    s = idcard.parse_card_text("~~ ## blurry ::")
    assert vars(s) == vars(idcard.IdSuggestions())


def card(text: str, size=(1400, 880)) -> bytes:
    img = Image.new("RGB", size, "white")
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default(size=44)
    draw.multiline_text((60, 60), text, fill="black", font=font, spacing=18)
    draw.rectangle((1000, 260, 1300, 640), fill=(150, 120, 100))  # where the photo would be
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


@pytest.mark.skipif(not shutil.which("tesseract"), reason="Tesseract is not installed")
def test_scan_reads_printed_card_and_crops_the_face(monkeypatch):
    monkeypatch.setattr(idcard, "find_face", lambda img: (1060, 300, 180, 220))
    out = idcard.scan(card(PNG_NID), "image/png")
    assert out.suggestions.national_id == "2011 0488 7712" and out.suggestions.last_name == "Wambi"
    assert out.text_read and out.problems == []
    photo = Image.open(io.BytesIO(out.photo))
    assert photo.format == "JPEG" and photo.size == idcard.PHOTO_SIZE


def test_scan_without_a_face_says_so(monkeypatch):
    monkeypatch.setattr(idcard, "find_face", lambda img: None)
    monkeypatch.setattr(idcard, "read_text", lambda img: None)
    out = idcard.scan(card("x"), "image/png")
    assert out.photo is None and len(out.problems) == 2 and "No face" in out.problems[0]


def test_unreadable_files_are_refused():
    with pytest.raises(idcard.ScanError):
        idcard.scan(b"\x89PNG\r\n\x1a\n not really", "image/png")
    with pytest.raises(idcard.ScanError):
        idcard.clean_photo(b"%PDF-1.4")


def test_clean_photo_redraws_as_a_portrait_jpeg():
    out = idcard.clean_photo(card("hello", size=(800, 800)))
    img = Image.open(io.BytesIO(out))
    assert img.format == "JPEG" and img.size == idcard.PHOTO_SIZE and not img.info.get("exif")


def test_scan_and_save_photo_through_the_api(staff, monkeypatch):
    monkeypatch.setattr(idcard, "find_face", lambda img: (1060, 300, 180, 220))
    monkeypatch.setattr(idcard, "read_text", lambda img: PNG_NID)
    up = staff.post(
        "/api/staff/borrowers/8/documents", data={"kind": "id"}, files={"file": ("nid.png", card("x"), "image/png")}
    ).json()
    r = staff.post(f"/api/staff/borrowers/8/documents/{up['id']}/scan")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["photo"].startswith("data:image/jpeg;base64,") and body["suggestions"]["gender"] == "male"
    assert body["suggestions"]["date_of_birth"] == "1986-03-14"
    assert staff.get("/api/staff/borrowers/8/photo").status_code == 404
    import base64

    jpeg = base64.b64decode(body["photo"].split(",", 1)[1])
    assert staff.put("/api/staff/borrowers/8/photo", files={"file": ("p.jpg", jpeg, "image/jpeg")}).status_code == 204
    got = staff.get("/api/staff/borrowers/8/photo")
    assert got.status_code == 200 and got.headers["content-type"] == "image/jpeg"
    profile = staff.get("/api/staff/borrowers/8").json()
    assert profile["borrower"]["has_photo"] is True and profile["notes"][0]["text"].startswith("Photo updated")


def test_only_id_documents_are_scanned(staff):
    docs = staff.get("/api/staff/borrowers/8").json()["documents"]
    payslip = next(d for d in docs if d["kind"] == "payslip")
    assert staff.post(f"/api/staff/borrowers/8/documents/{payslip['id']}/scan").status_code == 422


def test_huge_pictures_are_refused_before_decoding():
    buf = io.BytesIO()
    Image.new("1", (8000, 6000)).save(buf, "PNG")  # tiny file, 48 megapixels
    with pytest.raises(idcard.ScanError, match="too large"):
        idcard.scan(buf.getvalue(), "image/png")
    with pytest.raises(idcard.ScanError, match="too large"):
        idcard.clean_photo(buf.getvalue())
