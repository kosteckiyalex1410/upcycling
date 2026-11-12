"""Server-generated user-facing text (e.g. emails) from `app/locales/{uk,en}.json`.

The API itself returns language-neutral codes; only content the server delivers
directly to a person (email) is localized here.
"""

import json
from functools import lru_cache
from pathlib import Path

from app.domain.users import Locale

LOCALES_DIR = Path(__file__).resolve().parents[1] / "locales"


@lru_cache
def load_catalog(locale: Locale) -> dict[str, dict[str, str]]:
    data: dict[str, dict[str, str]] = json.loads(
        (LOCALES_DIR / f"{locale.value}.json").read_text(encoding="utf-8")
    )
    return data


def translate(locale: Locale, key: str, **params: object) -> str:
    group, name = key.split(".", 1)
    return load_catalog(locale)[group][name].format(**params)
