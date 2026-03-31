from __future__ import annotations

from datetime import date, time
from typing import Optional

from pydantic import BaseModel, Field


class DailyRecord(BaseModel):
    """All 21 fields for one day in the tracker."""

    record_date: date = Field(default_factory=date.today)

    # Anthropometric
    weight_kg: Optional[float] = None

    # CV Health (Whoop)
    resting_hr: Optional[int] = None
    hrv_rmssd: Optional[float] = None

    # Fluids
    water_liters: Optional[float] = None
    body_fat_pct: Optional[float] = None

    # Daily Activity
    session_performed: Optional[str] = None
    strength_rating: Optional[int] = Field(None, ge=1, le=10)
    cardio_duration_min: Optional[int] = None
    daily_steps: Optional[int] = None

    # Biofeedback
    morning_readiness: Optional[int] = Field(None, ge=1, le=10)
    energy: Optional[int] = Field(None, ge=1, le=10)
    hunger: Optional[int] = Field(None, ge=1, le=10)
    stress: Optional[int] = Field(None, ge=1, le=10)
    illness: Optional[bool] = None

    # Digestion
    digestion_issue: Optional[str] = None  # "None", "Yes - Minor", "Yes - Major"

    # Sleep (Whoop)
    bed_time: Optional[time] = None
    sleep_duration_minutes: Optional[int] = None
    deep_rem_minutes: Optional[int] = None

    # Plan Adherence
    stuck_to_plan: Optional[bool] = None

    # Sync status
    whoop_synced: bool = False
    sheet_synced: bool = False

    def merge(self, other: DailyRecord) -> DailyRecord:
        """Merge another record into this one. Non-None values from other override."""
        data = self.model_dump()
        for key, value in other.model_dump().items():
            if value is not None and key not in ("record_date", "whoop_synced", "sheet_synced"):
                data[key] = value
        return DailyRecord(**data)

    def to_sheet_row(self) -> list:
        """Convert to a list of values for columns C through U."""

        def fmt_duration(minutes: Optional[int]) -> str:
            if minutes is None:
                return ""
            h, m = divmod(minutes, 60)
            return f"{h}h {m}m"

        def fmt_time(t: Optional[time]) -> str:
            if t is None:
                return ""
            return t.strftime("%H:%M")

        def fmt_bool_yn(val: Optional[bool]) -> str:
            if val is None:
                return ""
            return "Yes" if val else "No"

        return [
            self.weight_kg if self.weight_kg is not None else "",
            self.resting_hr if self.resting_hr is not None else "",
            round(self.hrv_rmssd, 1) if self.hrv_rmssd is not None else "",
            self.water_liters if self.water_liters is not None else "",
            self.body_fat_pct if self.body_fat_pct is not None else "",
            self.session_performed or "",
            self.strength_rating if self.strength_rating is not None else "",
            self.cardio_duration_min if self.cardio_duration_min is not None else "",
            self.daily_steps if self.daily_steps is not None else "",
            self.morning_readiness if self.morning_readiness is not None else "",
            self.energy if self.energy is not None else "",
            self.hunger if self.hunger is not None else "",
            self.stress if self.stress is not None else "",
            fmt_bool_yn(self.illness) if self.illness is not None else "",
            self.digestion_issue or "",
            fmt_time(self.bed_time),
            fmt_duration(self.sleep_duration_minutes),
            fmt_duration(self.deep_rem_minutes),
            fmt_bool_yn(self.stuck_to_plan) if self.stuck_to_plan is not None else "",
        ]

    def to_supabase_dict(self) -> dict:
        """Convert to dict for Supabase upsert."""
        return {
            "date": self.record_date.isoformat(),
            "weight_kg": self.weight_kg,
            "resting_hr": self.resting_hr,
            "hrv_rmssd": self.hrv_rmssd,
            "water_liters": self.water_liters,
            "body_fat_pct": self.body_fat_pct,
            "session_performed": self.session_performed,
            "strength_rating": self.strength_rating,
            "cardio_duration_min": self.cardio_duration_min,
            "daily_steps": self.daily_steps,
            "morning_readiness": self.morning_readiness,
            "energy": self.energy,
            "hunger": self.hunger,
            "stress": self.stress,
            "illness": self.illness,
            "digestion_issue": self.digestion_issue,
            "bed_time": self.bed_time.isoformat() if self.bed_time else None,
            "sleep_duration_minutes": self.sleep_duration_minutes,
            "deep_rem_minutes": self.deep_rem_minutes,
            "stuck_to_plan": self.stuck_to_plan,
            "whoop_synced": self.whoop_synced,
            "sheet_synced": self.sheet_synced,
        }
