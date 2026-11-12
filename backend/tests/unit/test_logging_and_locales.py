import json
import logging
import string

from app.application.i18n import load_catalog, translate
from app.domain.users import Locale
from app.infrastructure.logging import JsonFormatter, redact, request_id_var


def test_redact_removes_tokens_codes_and_emails() -> None:
    text = (
        "GET /x?token=abc123&code=654321 session=s3cr3t "
        "Authorization: Bearer eyJhbGciOi.payload.sig user=expert@example.com"
    )
    redacted = redact(text)
    for secret in ("abc123", "654321", "s3cr3t", "eyJhbGciOi", "expert@example.com"):
        assert secret not in redacted


def test_json_formatter_includes_request_id_and_redacts() -> None:
    token = request_id_var.set("req-12345678")
    try:
        record = logging.LogRecord("t", logging.INFO, __file__, 1, "sent to a@b.co", None, None)
        payload = json.loads(JsonFormatter().format(record))
    finally:
        request_id_var.reset(token)
    assert payload["request_id"] == "req-12345678"
    assert "a@b.co" not in payload["message"]


def _placeholders(template: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(template) if name}


def test_backend_locales_have_identical_keys_and_placeholders() -> None:
    uk, en = load_catalog(Locale.UK), load_catalog(Locale.EN)
    assert uk.keys() == en.keys()
    for group, messages in uk.items():
        assert messages.keys() == en[group].keys(), group
        for key, template in messages.items():
            assert _placeholders(template) == _placeholders(en[group][key]), f"{group}.{key}"


def test_translate_formats_parameters() -> None:
    body = translate(Locale.UK, "login_email.body", link="L", code="123456", minutes=15)
    assert "L" in body
    assert "123456" in body
    assert "15" in body
