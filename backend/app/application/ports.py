"""Interfaces the application layer depends on; implemented in `app.infrastructure`."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

Clock = Callable[[], datetime]


def system_clock() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class EmailMessage:
    to: str
    subject: str
    text_body: str


class EmailSender(Protocol):
    async def send(self, message: EmailMessage) -> None: ...
