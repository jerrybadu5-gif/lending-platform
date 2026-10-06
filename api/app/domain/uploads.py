"""Checks on uploaded KYC files: size, and real file type from the first bytes (not the name)."""

from __future__ import annotations

import re
from urllib.parse import quote

SIGNATURES = [
    (b"%PDF-", "application/pdf", ".pdf"),
    (b"\xff\xd8\xff", "image/jpeg", ".jpg"),
    (b"\x89PNG\r\n\x1a\n", "image/png", ".png"),
]


class UploadRejected(ValueError):
    pass


def sniff(data: bytes) -> tuple[str, str]:
    """Content type and extension for a PDF, JPEG or PNG; anything else is refused."""
    for magic, ctype, ext in SIGNATURES:
        if data.startswith(magic):
            return ctype, ext
    # Not WEBP or HEIC: Fineract's default document whitelist refuses them.
    raise UploadRejected("Upload a PDF, JPG or PNG file.")


def safe_file_name(name: str, ext: str) -> str:
    """Keep a readable name but only safe characters, and the extension that matches the content."""
    base = re.split(r"[\\/]", name or "")[-1]  # drop any folder part, from Windows or elsewhere
    stem = re.sub(r"[^A-Za-z0-9._ -]", "_", base.rsplit(".", 1)[0]).strip(" ._") or "document"
    return stem[:80] + ext


def content_disposition(name: str) -> str:
    """A download header that is always valid: a plain ASCII name plus the original as UTF-8 (RFC 6266),
    so names with quotes, dashes or other characters (e.g. uploaded through Mifos X) can't break it."""
    ext = "." + name.rsplit(".", 1)[1] if "." in name else ""
    ascii_name = safe_file_name(
        name.encode("ascii", "replace").decode().replace("?", "_"), re.sub(r"[^A-Za-z0-9.]", "", ext)
    )
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(name, safe='')}"


def check_upload(name: str, data: bytes, max_bytes: int) -> tuple[str, str]:
    if not data:
        raise UploadRejected("The file is empty.")
    if len(data) > max_bytes:
        raise UploadRejected(f"The file is too big. The limit is {max_bytes // (1024 * 1024)} MB.")
    ctype, ext = sniff(data)
    return safe_file_name(name, ext), ctype
