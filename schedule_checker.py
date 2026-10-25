"""
Schedule Checker for League of Legends 5-Stack Sessions.
Determines whether a proposed session falls inside the official Ranked 5s queue window,
or whether it automatically falls back to Ranked Flex (5-player premade).
"""

from datetime import datetime, time, timedelta
import pytz

class RankedSchedule:
    def __init__(self, timezone_str="America/Vancouver", start_hour: int = 20, end_hour: int = 1):
        self.tz = pytz.timezone(timezone_str)
        # Default Riot 2026 Ranked 5s windows: Friday, Saturday, Sunday 20:00 - 01:00 (next day)
        # Weekdays: 4=Friday, 5=Saturday, 6=Sunday
        self.active_days = [4, 5, 6]
        self.window_start_hour = start_hour  # 8:00 PM
        self.window_end_hour = end_hour      # 1:00 AM next day

    def evaluate_time(self, dt: datetime = None):
        """
        Evaluate if a given datetime is within the Ranked 5s active window.
        Returns a dictionary with status, recommended mode, reason, and next window.
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
        # Case 2: Saturday, Sunday, or Monday between 00:00 and 01:00:00 (the overflow from previous night)
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
            "next_window_start": next_window.strftime("%A %b %d at %I:%M %p %Z") if next_window else "N/A"
        }

    def get_next_window(self, dt: datetime = None) -> datetime:
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
