"""User identity concepts. Language-neutral identifiers only; no UI text."""

import uuid
from dataclasses import dataclass
from enum import StrEnum


class Locale(StrEnum):
    """Supported UI locales. Values are persisted and exposed via the API."""

    UK = "uk"
    EN = "en"


DEFAULT_LOCALE = Locale.UK


def normalize_email(email: str) -> str:
    return email.strip().lower()


@dataclass(frozen=True, slots=True)
class User:
    id: uuid.UUID
    email: str
    preferred_locale: Locale
    is_active: bool
