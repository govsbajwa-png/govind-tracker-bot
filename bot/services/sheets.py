"""Google Sheets service via Apps Script web app — no service account needed."""

from __future__ import annotations

import logging
from datetime import date

import httpx

from bot.config import GOOGLE_APPS_SCRIPT_URL, TIMEZONE

logger = logging.getLogger(__name__)


class SheetsService:
    """Writes to the daily tracker sheet via a Google Apps Script web app.

    This avoids the need for a Google Cloud service account entirely.
    The user deploys a simple Apps Script on their sheet and provides the URL.
    """

    def __init__(self) -> None:
        self._url = GOOGLE_APPS_SCRIPT_URL
        if not self._url:
            raise RuntimeError(
                "GOOGLE_APPS_SCRIPT_URL not set. Deploy the Apps Script first."
            )

    @staticmethod
    def _format_date(target_date: date) -> str:
        """Format date to match the sheet's column B format: '31-Mar', '1-Apr'."""
        try:
            return target_date.strftime("%-d-%b")
        except ValueError:
            return target_date.strftime("%d-%b").lstrip("0")

    def find_row_for_date(self, target_date: date) -> str:
        """Return the formatted date string (row lookup happens in Apps Script)."""
        return self._format_date(target_date)

    def write_daily_data(self, date_str: str, values: list) -> None:
        """Write all columns C-U for the given date via Apps Script."""
        # Convert any Python objects to JSON-safe values
        safe_values = []
        for v in values:
            if v is None or v == "":
                safe_values.append("")
            elif isinstance(v, bool):
                safe_values.append("Yes" if v else "No")
            else:
                safe_values.append(v)

        payload = {
            "action": "write_row",
            "date": date_str,
            "values": safe_values,
        }

        with httpx.Client(timeout=30, follow_redirects=True) as client:
            resp = client.post(self._url, json=payload)
            resp.raise_for_status()
            result = resp.json()

        if result.get("error"):
            logger.error("Apps Script error: %s", result["error"])
            raise RuntimeError(f"Sheet write failed: {result['error']}")

        logger.info(
            "Wrote %d values for date '%s' to row %s",
            len(values),
            date_str,
            result.get("row", "?"),
        )

    def update_single_field(self, date_str: str, column_letter: str, value) -> None:
        """Update one cell for the given date."""
        payload = {
            "action": "update_cell",
            "date": date_str,
            "column": column_letter,
            "value": value if value is not None else "",
        }

        with httpx.Client(timeout=30, follow_redirects=True) as client:
            resp = client.post(self._url, json=payload)
            resp.raise_for_status()
            result = resp.json()

        if result.get("error"):
            logger.error("Apps Script error: %s", result["error"])
        else:
            logger.info("Updated %s for date '%s'", column_letter, date_str)
