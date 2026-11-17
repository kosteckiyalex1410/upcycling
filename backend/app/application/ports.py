"""Interfaces the application layer depends on; implemented in `app.infrastructure`."""

from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import BinaryIO, Protocol

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


@dataclass(frozen=True, slots=True)
class StoredObject:
    key: str
    size_bytes: int
    last_modified: datetime


class StorageUnavailableError(Exception):
    """The object store could not be reached or failed; the operation may be retried."""


class ObjectStorage(Protocol):
    """Private S3-compatible object store (ADR-0006). Keys are opaque UUID paths."""

    def presign_put(
        self, key: str, *, content_type: str, size_bytes: int, sha256_b64: str, expires_in: int
    ) -> tuple[str, dict[str, str]]:
        """URL and headers for one browser PUT whose type, length and SHA-256 are fixed."""
        ...

    async def head(self, key: str) -> StoredObject | None: ...

    async def download(self, key: str, destination: BinaryIO, *, max_bytes: int) -> int:
        """Copy an object into `destination`; returns bytes written. Raises
        `ObjectTooLargeError` past `max_bytes` and `ObjectMissingError` if absent."""
        ...

    async def upload(self, key: str, source: BinaryIO, *, content_type: str) -> None: ...

    async def put_bytes(self, key: str, data: bytes, *, content_type: str) -> None: ...

    async def open_stream(
        self, key: str, *, byte_range: tuple[int, int] | None = None
    ) -> AsyncIterator[bytes]:
        """Start reading an object, or the inclusive `byte_range` of it (raises
        `ObjectMissingError` if absent); iterate the result for its bytes."""
        ...

    async def read_bytes(self, key: str) -> bytes: ...

    async def delete_many(self, keys: list[str]) -> None:
        """Delete objects; missing keys are not an error."""
        ...

    async def list_objects(self, prefix: str) -> list[StoredObject]: ...


class ObjectMissingError(Exception):
    pass


class ObjectTooLargeError(Exception):
    pass
