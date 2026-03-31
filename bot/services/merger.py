"""Data merger — combines Telegram, voice, and Whoop sources into one DailyRecord."""

from __future__ import annotations

import logging
from datetime import date, time

from bot.models.daily_record import DailyRecord

logger = logging.getLogger(__name__)


def merge_all_sources(
    telegram_data: dict,
    voice_data: dict,
    whoop_data: dict,
    target_date: date,
) -> DailyRecord:
    """Merge three data sources into a single :class:`DailyRecord`.

    Priority (last writer wins):
        1. Whoop data — objective device measurements (applied first)
        2. Voice data — extracted from the user's voice note (overrides Whoop)
        3. Telegram data — explicit button taps (overrides everything)

    Only non-``None`` values from each source are applied.
    """
    record = DailyRecord(record_date=target_date)

    # Gather the set of valid DailyRecord field names for safety
    valid_fields = set(record.model_fields.keys())

    # Layer 1: Whoop (objective measurements)
    _apply_source(record, whoop_data, valid_fields)

    # Layer 2: Voice note extraction
    _apply_source(record, voice_data, valid_fields)

    # Layer 3: Telegram button taps (highest priority)
    _apply_source(record, telegram_data, valid_fields)

    # Mark Whoop sync status
    if any(v is not None for v in whoop_data.values()):
        record.whoop_synced = True

    logger.info(
        "Merged record for %s — whoop=%d fields, voice=%d fields, "
        "telegram=%d fields",
        target_date,
        _count_non_none(whoop_data),
        _count_non_none(voice_data),
        _count_non_none(telegram_data),
    )
    return record


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------


def _apply_source(
    record: DailyRecord, source: dict, valid_fields: set[str]
) -> None:
    """Set fields on *record* from *source*, skipping None values and
    metadata fields that shouldn't be overwritten by sources."""
    skip = {"record_date", "whoop_synced", "sheet_synced"}
    for key, value in source.items():
        if value is None:
            continue
        if key in skip:
            continue
        if key not in valid_fields:
            logger.debug("Ignoring unknown field '%s' from source", key)
            continue
        setattr(record, key, value)


def _count_non_none(d: dict) -> int:
    return sum(1 for v in d.values() if v is not None)
