"""Opt-out keyword detection for inbound WhatsApp text messages (P2 T2.5b).

When a customer replies with ``STOP``, ``UNSUBSCRIBE``, ``احذفني``, etc.
we tag the message as ``is_opt_out`` and the bridge subscriber (P7) flips
``res.partner.x_htf_opted_out=True`` + creates an ``htf.dnc`` row.

Matching strategy: **strict whole-message match, case-insensitive,
Unicode-normalised, Arabic-diacritic-stripped**. This is intentionally
conservative — a substring match would trigger on legitimate replies
like "Stop, that's the wrong account number." Numo Higher prefers
missing a few real opt-outs over annoying customers who didn't intend
to opt out.

The keyword list is configurable via ``htf.config.dnc_keywords``
(comma-separated). The defaults cover English + Saudi Arabic conventions
documented in WhatsApp Business policy + Meta's healthcare templates.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from typing import Iterable

_logger = logging.getLogger(__name__)

# Defaults — admin can override via htf.config.dnc_keywords.
# Each entry is matched as a WHOLE-MESSAGE token after normalisation;
# strings with spaces ARE supported (matched as a phrase, not per-word).
DEFAULT_OPT_OUT_KEYWORDS: tuple[str, ...] = (
    # English
    'stop',
    'unsubscribe',
    'remove me',
    'opt out',
    'opt-out',
    'optout',
    'cancel',
    'quit',
    # Saudi Arabic (matched after diacritic removal)
    'احذفني',
    'الغ',
    'الغ الاشتراك',
    'الغاء',
    'الغاء الاشتراك',
    'إلغاء',
    'إلغاء الاشتراك',
    'ايقاف',
    'إيقاف',
    'لا اريد',
    'لا أريد',
    'توقف',
)

# Trailing punctuation / whitespace that shouldn't defeat a STOP match.
_TRAILING = re.compile(r'[\s\.\!\?\،\؛\:\;\,\-\_\)\(\[\]\{\}\*\+\=\>\<‏‎]+')


def _normalize(text: str) -> str:
    """Lowercase + strip Arabic diacritics + collapse whitespace.

    NFKD strips combining marks (Arabic kasra/fatha/damma/shadda),
    which lets ``إلغاء`` match ``الغاء`` and similar diacritic variations.
    """
    if not text:
        return ''
    norm = unicodedata.normalize('NFKD', text)
    # Drop combining marks (category 'Mn').
    norm = ''.join(c for c in norm if unicodedata.category(c) != 'Mn')
    # Normalise alefs to bare alef so ``إلغاء`` → ``الغاء``.
    norm = norm.replace('أ', 'ا').replace('إ', 'ا').replace('آ', 'ا')
    norm = norm.lower().strip()
    # Strip surrounding punctuation/zero-width marks.
    norm = _TRAILING.sub(' ', norm).strip()
    # Collapse multiple spaces.
    norm = re.sub(r'\s+', ' ', norm)
    return norm


def is_opt_out(text: str, keywords: Iterable[str] | None = None) -> bool:
    """Return True iff ``text`` is a whole-message opt-out token/phrase.

    >>> is_opt_out('STOP')
    True
    >>> is_opt_out('  Stop. ')
    True
    >>> is_opt_out('Stop, that is the wrong account')
    False
    >>> is_opt_out('احذفني')
    True
    >>> is_opt_out('إلغاء الاشتراك')
    True
    """
    if not text:
        return False
    normalized = _normalize(text)
    if not normalized:
        return False
    candidates = list(keywords) if keywords else list(DEFAULT_OPT_OUT_KEYWORDS)
    for kw in candidates:
        if not kw:
            continue
        kw_norm = _normalize(kw)
        if not kw_norm:
            continue
        if normalized == kw_norm:
            return True
    return False


def load_keywords(env) -> tuple[str, ...]:
    """Pull configured keywords from htf.config (comma-separated).

    Falls back to ``DEFAULT_OPT_OUT_KEYWORDS`` when not configured.
    """
    raw = ''
    try:
        raw = env['htf.config'].sudo().get_param('dnc_keywords') or ''
    except Exception:  # noqa: BLE001 — defensive at boundary
        _logger.debug("[htf-wa] dnc_keywords param read failed; using defaults",
                      exc_info=True)
    if not raw:
        return DEFAULT_OPT_OUT_KEYWORDS
    parts = tuple(p.strip() for p in raw.split(',') if p.strip())
    return parts or DEFAULT_OPT_OUT_KEYWORDS
