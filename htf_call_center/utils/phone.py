"""Phone E.164 normalization.

All numbers stored in the wrapper are E.164 (``+9665…``). Use
``normalize_e164`` at every boundary: webhook intake, API call out,
wizard form submit, vCard import. Anything that fails to normalize is
rejected at the source instead of being passed downstream as a partial
match risk.

Saudi mobile prefixes covered: 050, 052, 053, 054, 055, 056, 058, 059.
KSA landline numbers also accepted.
"""

from __future__ import annotations

import logging
from typing import Optional

import phonenumbers

_logger = logging.getLogger(__name__)

DEFAULT_REGION = 'SA'  # KSA — vast majority of Numo contacts


def normalize_e164(raw: Optional[str], default_region: str = DEFAULT_REGION) -> Optional[str]:
    """Return raw as an E.164 number (``+9665…``) or None.

    Accepts: ``+966 50 123 4567``, ``00966501234567``, ``0501234567``,
    ``966501234567``, ``050-123-4567``, etc.

    Rejects (returns None) for: empty / whitespace-only, unparseable
    junk, or numbers that parse but fail the strict ``is_valid_number``
    check (e.g. short codes, malformed prefixes).
    """
    if raw is None:
        return None
    if not isinstance(raw, str):
        raw = str(raw)
    raw = raw.strip()
    if not raw:
        return None

    # phonenumbers is happier when "+" is already present.
    candidate = raw
    if candidate.startswith('00'):
        candidate = '+' + candidate[2:]

    try:
        parsed = phonenumbers.parse(candidate, default_region)
    except phonenumbers.NumberParseException as exc:
        _logger.debug("[htf.phone] parse failed for %r: %s", raw, exc)
        return None

    if not phonenumbers.is_valid_number(parsed):
        _logger.debug("[htf.phone] %r parsed but invalid", raw)
        return None

    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


def normalize_e164_strict(raw: Optional[str], default_region: str = DEFAULT_REGION) -> str:
    """Same as ``normalize_e164`` but raises ``ValueError`` instead of None.

    Used at the API boundary where a bad number should fail loudly
    (e.g. send WhatsApp pre-flight check).
    """
    out = normalize_e164(raw, default_region)
    if out is None:
        raise ValueError(f"Cannot normalize {raw!r} to E.164 (region {default_region})")
    return out
