"""Whoop API service — direct HTTP calls via httpx for full control."""

from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta, timezone

import httpx

from bot.config import (
    WHOOP_API_BASE,
    WHOOP_CLIENT_ID,
    WHOOP_CLIENT_SECRET,
    WHOOP_TOKEN_URL,
    TIMEZONE,
)
from bot.sport_mapping import get_sport_name
from bot.services.supabase_client import get_whoop_tokens, save_whoop_tokens

logger = logging.getLogger(__name__)


class WhoopService:
    """Pulls daily biometrics from the Whoop developer API."""

    def __init__(self) -> None:
        tokens = get_whoop_tokens()
        if not tokens:
            raise RuntimeError(
                "No Whoop tokens found in Supabase. Run OAuth flow first."
            )
        self._access_token: str = tokens["access_token"]
        self._refresh_token: str = tokens["refresh_token"]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_headers(self) -> dict:
        return {"Authorization": f"Bearer {self._access_token}"}

    async def _refresh(self) -> None:
        """Exchange the refresh token for a new access token."""
        logger.info("Refreshing Whoop access token")
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                WHOOP_TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": self._refresh_token,
                    "client_id": WHOOP_CLIENT_ID,
                    "client_secret": WHOOP_CLIENT_SECRET,
                },
            )
            resp.raise_for_status()
            data = resp.json()

        self._access_token = data["access_token"]
        self._refresh_token = data["refresh_token"]
        from datetime import timezone as tz

        expires_in = data.get("expires_in", 3600)
        expires_at = (
            datetime.now(tz.utc) + timedelta(seconds=expires_in)
        ).isoformat()
        save_whoop_tokens(
            access_token=self._access_token,
            refresh_token=self._refresh_token,
            expires_at=expires_at,
        )
        logger.info("Whoop tokens refreshed and saved")

    async def _request(
        self, endpoint: str, params: dict | None = None
    ) -> dict:
        """GET a Whoop API endpoint. Auto-refreshes on 401."""
        url = f"{WHOOP_API_BASE}{endpoint}"
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                url, headers=self._get_headers(), params=params
            )

            if resp.status_code == 401:
                logger.warning("Whoop 401 — attempting token refresh")
                await self._refresh()
                resp = await client.get(
                    url, headers=self._get_headers(), params=params
                )

            resp.raise_for_status()
            return resp.json()

    # ------------------------------------------------------------------
    # Date-range helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _day_range_iso(target_date: date) -> tuple[str, str]:
        """Return ISO-8601 start/end strings covering the full target day
        in UTC (Whoop API expects UTC timestamps)."""
        start_dt = datetime(
            target_date.year,
            target_date.month,
            target_date.day,
            tzinfo=TIMEZONE,
        )
        end_dt = start_dt + timedelta(days=1)
        start_utc = start_dt.astimezone(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%S.000Z"
        )
        end_utc = end_dt.astimezone(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%S.000Z"
        )
        return start_utc, end_utc

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def pull_daily_data(self, target_date: date) -> dict:
        """Pull cycles, sleep, and workout data for *target_date*.

        Returns a dict whose keys match DailyRecord field names.
        Missing data is simply omitted (callers merge partial dicts).
        """
        start_iso, end_iso = self._day_range_iso(target_date)
        params = {"start": start_iso, "end": end_iso}
        result: dict = {}

        # ---- Cycles (HR, HRV, strain) --------------------------------
        try:
            cycles = await self._request("/cycle", params=params)
            records = cycles.get("records", [])
            if records:
                score = records[0].get("score", {})
                rhr = score.get("resting_heart_rate")
                hrv = score.get("hrv", {}).get("rmssd") if isinstance(
                    score.get("hrv"), dict
                ) else score.get("hrv_rmssd")
                if rhr is not None:
                    result["resting_hr"] = int(rhr)
                if hrv is not None:
                    result["hrv_rmssd"] = float(hrv)
        except Exception:
            logger.exception("Failed to fetch Whoop cycles")

        # ---- Sleep ----------------------------------------------------
        try:
            sleep = await self._request("/activity/sleep", params=params)
            records = sleep.get("records", [])
            if records:
                rec = records[0]
                score = rec.get("score", {})

                # Bed-time (convert to local timezone)
                start_str = rec.get("start")
                if start_str:
                    bed_dt = datetime.fromisoformat(
                        start_str.replace("Z", "+00:00")
                    ).astimezone(TIMEZONE)
                    result["bed_time"] = time(bed_dt.hour, bed_dt.minute)

                # Total sleep duration
                total_seconds = score.get(
                    "total_sleep_duration",
                    score.get("sleep_duration_seconds"),
                )
                if total_seconds is not None:
                    result["sleep_duration_minutes"] = int(
                        total_seconds
                    ) // 60

                # Deep + REM
                deep = score.get(
                    "deep_sleep_duration",
                    score.get("deep_sleep_duration_seconds", 0),
                ) or 0
                rem = score.get(
                    "rem_sleep_duration",
                    score.get("rem_sleep_duration_seconds", 0),
                ) or 0
                if deep or rem:
                    result["deep_rem_minutes"] = (int(deep) + int(rem)) // 60
        except Exception:
            logger.exception("Failed to fetch Whoop sleep")

        # ---- Workouts -------------------------------------------------
        try:
            workouts = await self._request(
                "/activity/workout", params=params
            )
            records = workouts.get("records", [])
            if records:
                names: list[str] = []
                total_duration_sec = 0
                for w in records:
                    sport_id = w.get("sport_id", -1)
                    names.append(get_sport_name(sport_id))
                    score = w.get("score", {})
                    dur = score.get("duration_seconds", 0) or 0
                    total_duration_sec += int(dur)

                result["session_performed"] = ", ".join(names)
                if total_duration_sec:
                    result["cardio_duration_min"] = total_duration_sec // 60
        except Exception:
            logger.exception("Failed to fetch Whoop workouts")

        logger.info(
            "Whoop data for %s: %d fields pulled", target_date, len(result)
        )
        return result
