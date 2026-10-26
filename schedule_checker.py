"""
Schedule Checker for League of Legends 5-Stack Sessions.
Determines whether a proposed session falls inside the official Ranked 5s queue window,
or whether it automatically falls back to Ranked Flex (5-player premade).
Supports natural language time parsing via dateparser.
"""

from datetime import datetime, time, timedelta
from typing import Optional, Tuple
import pytz
import dateparser

class RankedSchedule:
    def __init__(self, timezone_str: str = "America/Vancouver", start_hour: int = 20, end_hour: int = 1):
        self.timezone_str = timezone_str
        self.tz = pytz.timezone(timezone_str)
        # Default Riot 2026 Ranked 5s windows: Friday, Saturday, Sunday 20:00 - 01:00 (next day)
        # Weekdays: 4=Friday, 5=Saturday, 6=Sunday
        self.active_days = [4, 5, 6]
        self.window_start_hour = start_hour  # 8:00 PM
        self.window_end_hour = end_hour      # 1:00 AM next day

    def parse_target_time(self, time_str: str) -> Tuple[datetime, str, bool]:
        """
        Parses a natural language time string into an aware datetime and formatted display string.
        Returns: (target_dt, display_str, is_parsed_successfully)
        """
        if not time_str or not time_str.strip():
            now = datetime.now(self.tz)
            return now, now.strftime("%A %b %d at %I:%M %p %Z"), False

        normalized = time_str.strip()
        # Handle 'tonight' edge-cases
        if "tonight" in normalized.lower():
            sub = normalized.lower().replace("tonight", "").strip()
            if not sub:
                normalized = f"today {self.window_start_hour}:00"
            else:
                normalized = f"today {sub}"

        parsed = dateparser.parse(
            normalized,
            settings={
                "TIMEZONE": self.timezone_str,
                "TO_TIMEZONE": self.timezone_str,
                "RETURN_AS_TIMEZONE_AWARE": True,
                "PREFER_DATES_FROM": "future",
            }
        )

        now = datetime.now(self.tz)
        if parsed:
            # If parsed time is earlier today by more than 30 mins, roll forward to tomorrow or next week
            if parsed < now and (now - parsed).total_seconds() > 1800:
                parsed = parsed + timedelta(days=1)
            display = parsed.strftime("%A %b %d at %I:%M %p %Z")
            return parsed, display, True
        else:
            return now, time_str.strip(), False

    def evaluate_time(self, dt: Optional[datetime] = None) -> dict:
        """
        Evaluate if a given datetime is within the Ranked 5s active window.
        Returns a dictionary with status, recommended mode, reason, target ISO, and next window.
        """
        if dt is None:
            dt = datetime.now(self.tz)
        elif dt.tzinfo is None:
            dt = self.tz.localize(dt)
        else:
            dt = dt.astimezone(self.tz)

        weekday = dt.weekday()
        current_time = dt.time()

        is_ranked_5s = False

        # Case 1: Friday, Saturday, or Sunday between 20:00 and 23:59:59
        if weekday in [4, 5, 6] and current_time >= time(self.window_start_hour, 0):
            is_ranked_5s = True
        # Case 2: Saturday, Sunday, or Monday between 00:00 and 01:00:00 (overflow from previous night)
        elif weekday in [5, 6, 0] and current_time < time(self.window_end_hour, 0):
            is_ranked_5s = True

        if is_ranked_5s:
            mode = "Ranked 5s (Weekend Queue)"
            status = "OPEN"
            desc = "✅ Ranked 5s window is ACTIVE! Tournament draft enabled."
        else:
            mode = "Ranked Flex (Fallback)"
            status = "FALLBACK"
            desc = "⚠️ Ranked 5s window closed. Falling back to 5-Stack Ranked Flex (24/7 Queue)."

        next_window = self.get_next_window(dt)

        return {
            "is_ranked_5s": is_ranked_5s,
            "mode": mode,
            "status": status,
            "description": desc,
            "evaluated_time": dt.strftime("%Y-%m-%d %I:%M %p %Z"),
            "target_iso": dt.isoformat(),
            "next_window_start": next_window.strftime("%A %b %d at %I:%M %p %Z") if next_window else "N/A"
        }

    def get_next_window(self, dt: Optional[datetime] = None) -> Optional[datetime]:
        """Find the start of the next Ranked 5s window from dt."""
        if dt is None:
            dt = datetime.now(self.tz)
        elif dt.tzinfo is None:
            dt = self.tz.localize(dt)
        else:
            dt = dt.astimezone(self.tz)

        # Check the next 7 days for the next Friday, Saturday, or Sunday at window_start_hour
        for day_offset in range(8):
            candidate_date = (dt + timedelta(days=day_offset)).date()
            candidate_dt = self.tz.localize(datetime.combine(candidate_date, time(self.window_start_hour, 0)))
            if candidate_dt.weekday() in [4, 5, 6] and candidate_dt > dt:
                return candidate_dt
        return None
