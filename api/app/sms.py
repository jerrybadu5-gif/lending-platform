"""SMS sending. Only the console sender exists for now; Digicel PNG and Vodafone PNG adapters
are added at shipping time behind the same `SmsSender` interface (send(to, text))."""

from __future__ import annotations

import logging
from typing import Protocol

log = logging.getLogger("mclender.sms")


class SmsSender(Protocol):
    async def send(self, to: str, text: str) -> None: ...


class ConsoleSms:
    """Development sender: writes the message to the log and keeps the last few for tests."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    async def send(self, to: str, text: str) -> None:
        self.sent = (self.sent + [(to, text)])[-50:]
        log.info("SMS to %s: %s", to, text)


def make_sms(provider: str) -> SmsSender:
    if provider == "console":
        return ConsoleSms()
    raise ValueError(f"Unknown SMS provider {provider!r}")
