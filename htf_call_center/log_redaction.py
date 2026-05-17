"""Strip bearer tokens and webhook secrets from log records.

Installed once at module load. The filter mutates the formatted message + args
of any LogRecord so secrets never reach stdout, files, or ir.logging rows.
"""

import logging
import re

# Match `Authorization: Bearer <token>`, case-insensitive, in headers dicts and
# free-form text. Group 1 keeps the prefix so the redaction is readable.
_BEARER_RE = re.compile(
    r'((?:Authorization|authorization)\s*[:=]\s*[\'"]?Bearer\s+)[A-Za-z0-9._~+/=\-]+',
    re.IGNORECASE,
)

# Match webhook-secret-ish keys. Catches webhook_secret_current,
# webhook_secret_previous, client_secret, etc.
_SECRET_KV_RE = re.compile(
    r'((?:webhook_secret\w*|client_secret|access_token|refresh_token)\s*[:=]\s*[\'"]?)'
    r'([^\s\'"]+)',
    re.IGNORECASE,
)

_REDACTED = '***REDACTED***'


def _redact(text: str) -> str:
    if not text or '*' in text and 'REDACTED' in text:
        return text
    text = _BEARER_RE.sub(r'\1' + _REDACTED, text)
    text = _SECRET_KV_RE.sub(r'\1' + _REDACTED, text)
    return text


class HtfSecretRedactionFilter(logging.Filter):
    """Logging filter that masks bearer tokens and webhook secrets."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            if isinstance(record.msg, str):
                record.msg = _redact(record.msg)
            if record.args:
                if isinstance(record.args, dict):
                    record.args = {k: _redact(v) if isinstance(v, str) else v
                                   for k, v in record.args.items()}
                elif isinstance(record.args, tuple):
                    record.args = tuple(
                        _redact(a) if isinstance(a, str) else a
                        for a in record.args
                    )
        except Exception:  # pragma: no cover — never let logging itself break
            pass
        return True


_INSTALLED = False


def install() -> None:
    """Attach the redaction filter to the root logger. Idempotent."""
    global _INSTALLED
    if _INSTALLED:
        return
    root = logging.getLogger()
    root.addFilter(HtfSecretRedactionFilter())
    _INSTALLED = True
