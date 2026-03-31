"""Google Sheets service via Apps Script web app — optional, gracefully skips if not configured."""

from __future__ import annotations

import logging
from datetime import date

import httpx

from bot.config import GOOGLE_APPS_SCRIPT_URL

logger = logging.getLogger(__name__)


class SheetsService:
    """Writes to the daily tracker sheet via a Google Apps Script web app.

    If GOOGLE_APPS_SCRIPT_URL is not set, all operations are no-ops.
    """

    def __init__(self) -> None:
        self._url = GOOGLE_APPS_SCRIPT_URL
        self._enabled = bool(self._url)
        if not self._enabled:
            logger.info("Google Sheets sync disabled (GOOGLE_APPS_SCRIPT_URL not set)")

    @property
    def enabled(self) -> bool:
        return self._enabled

    @staticmethod
    def _format_date(target_date: date) -> str:
        try:
            return target_date.strftime("%-d-%b")
        except ValueError:
            return target_date.strftime("%d-%b").lstrip("0")

    def find_row_for_date(self, target_date: date) -> str:
        return self._format_date(target_date)

    def write_daily_data(self, date_str: str, values: list) -> None:
        if not self._enabled:
            return

        safe_values = []
        for v in values:
            if v is None or v == "":
                safe_values.append("")
            elif isinstance(v, bool):
                safe_values.append("Yes" if v else "No")
            else:
                safe_values.append(v)

        payload = {"action": "write_row", "date": date_str, "values": safe_values}

        with httpx.Client(timeout=30, follow_redirects=True) as client:
            resp = client.post(self._url, json=payload)
            resp.raise_for_status()
            result = resp.json()

        if result.get("error"):
            logger.error("Apps Script error: %s", result["error"])
        else:
            logger.info("Wrote to sheet for date '%s' row %s", date_str, result.get("row", "?"))

    def update_single_field(self, date_str: str, column_letter: str, value) -> None:
        if not self._enabled:
            return

        payload = {
            "action": "update_cell",
            "date": date_str,
            "column": column_letter,
            "value": value if value is not None else "",
        }

        with httpx.Client(timeout=30, follow_redirects=True) as client:
            resp = client.post(self._url, json=payload)
            resp.raise_for_status()
