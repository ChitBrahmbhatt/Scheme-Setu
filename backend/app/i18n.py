"""Translation lookup helper (CLAUDE.md rule 9, §8).

/recommend and /calculate return reason/caveat codes only, never prose —
the frontend maps codes to strings itself (FRONTEND_BRIEF.md §5). This
helper exists for any internal use that needs the actual bundle text (e.g.
future /assist/explain narration ingredients) without ever hardcoding
English/Hindi prose in Python.
"""
import logging

from app.loader import LoadedData

logger = logging.getLogger(__name__)

FALLBACK_LOCALE = "en"


def translate(data: LoadedData, locale: str, key: str) -> str:
    bundle = data.i18n.get(locale) or data.i18n[FALLBACK_LOCALE]
    if key in bundle.root:
        return bundle.root[key]

    logger.warning("missing i18n key '%s' for locale '%s'; falling back to %s", key, locale, FALLBACK_LOCALE)
    fallback_bundle = data.i18n[FALLBACK_LOCALE]
    return fallback_bundle.root.get(key, key)
