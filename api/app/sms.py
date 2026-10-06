"""SMS sending. Only the console sender exists for now; Digicel PNG and Vodafone PNG adapters
are added at shipping time behind the same `SmsSender` interface (send(to, text))."""

from __future__ import annotations

import logging
from typing import Protocol

log = logging.getLogger("mclender.sms")


class SmsSender(Protocol):
    async def send(self, to: str, text: str) -> None: ...


def mask_phone(to: str) -> str:
    return "*" * max(len(to) - 3, 0) + to[-3:]


class ConsoleSms:
    """Development sender: writes the message to the log and keeps the last few for tests.

    With reveal=False (anything but sample data) the log shows only a masked number and the
    message length, so sign-in codes and borrower details never land in log files."""

    def __init__(self, reveal: bool = True) -> None:
        self.reveal = reveal
        self.sent: list[tuple[str, str]] = []

    async def send(self, to: str, text: str) -> None:
        self.sent = (self.sent + [(to, text)])[-50:]
        if self.reveal:
            log.info("SMS to %s: %s", to, text)
        else:
            log.info("SMS to %s (%d characters, not shown)", mask_phone(to), len(text))


def make_sms(provider: str, reveal: bool = False) -> SmsSender:
    if provider == "console":
        return ConsoleSms(reveal=reveal)
    raise ValueError(f"Unknown SMS provider {provider!r}")
