"""AI-Verse one-product Distribution layer."""

import json
from importlib import resources

from .core_promotion import CorePromotionError, validate_core_promotion_governance


__version__ = "0.1.0b1"


def _validate_packaged_core_promotions() -> None:
    """Fail closed before any packaged promotion ledger can become a release channel."""
    try:
        raw = resources.files("aiverse_distribution.catalog").joinpath(
            "core_promotions.json"
        ).read_text(encoding="utf-8")
        promotions = json.loads(raw)
    except (OSError, ValueError) as exc:
        raise CorePromotionError("packaged Core promotion ledger is unreadable") from exc
    if not isinstance(promotions, dict):
        raise CorePromotionError("packaged Core promotion ledger must be a JSON object")
    validate_core_promotion_governance(promotions)


_validate_packaged_core_promotions()
