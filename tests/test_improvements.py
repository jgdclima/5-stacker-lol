import unittest
import os
import tempfile
from datetime import datetime, timedelta
import pytz

from schedule_checker import RankedSchedule
from data_manager import StatsManager

class TestAppImprovements(unittest.TestCase):
    def setUp(self):
        self.temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
        self.temp_file.close()
        self.stats_mgr = StatsManager(filepath=self.temp_file.name)
        self.scheduler = RankedSchedule(timezone_str="America/Vancouver")

    def tearDown(self):
        if os.path.exists(self.temp_file.name):
            os.remove(self.temp_file.name)

    def test_natural_language_time_parsing(self):
        # 1. Friday 9pm
        target_dt, display, ok = self.scheduler.parse_target_time("Friday 9pm")
        self.assertTrue(ok)
        self.assertEqual(target_dt.weekday(), 4)  # Friday
        self.assertEqual(target_dt.hour, 21)

        # 2. Evaluate that Friday 9pm falls inside Ranked 5s window
        eval_res = self.scheduler.evaluate_time(target_dt)
        self.assertTrue(eval_res["is_ranked_5s"])
        self.assertEqual(eval_res["mode"], "Ranked 5s (Weekend Queue)")

        # 3. Tuesday 3pm falls into Flex fallback
        # Construct next Tuesday 3pm
        now = datetime.now(self.scheduler.tz)
        days_ahead = (1 - now.weekday()) % 7
        if days_ahead == 0:
            days_ahead = 7
        tuesday_dt = (now + timedelta(days=days_ahead)).replace(hour=15, minute=0, second=0)
        tuesday_res = self.scheduler.evaluate_time(tuesday_dt)
        self.assertFalse(tuesday_res["is_ranked_5s"])
        self.assertEqual(tuesday_res["mode"], "Ranked Flex (Fallback)")

    def test_auto_promotion_from_bench(self):
        s = self.stats_mgr.create_session("s123", "Tonight 8:00 PM", "Ranked Flex", False, "Creator")
        
        # Add 5 starters
        for i in range(1, 6):
            self.stats_mgr.register_player("s123", f"Player{i}", "CONFIRMED", "Fill")
        
        # Add 2 substitutes
        self.stats_mgr.register_player("s123", "Sub1", "CONFIRMED", "Mid")
        self.stats_mgr.register_player("s123", "Sub2", "CONFIRMED", "Top")

        session = self.stats_mgr.data["active_sessions"]["s123"]
        self.assertEqual(len(session["confirmed_players"]), 5)
        self.assertEqual(len(session["bench_substitutes"]), 2)
        self.assertEqual(session["bench_substitutes"][0]["name"], "Sub1")

        # Starter Player2 declines!
        is_ready, session, promoted = self.stats_mgr.register_player("s123", "Player2", "DECLINED")
        self.assertTrue(is_ready)
        self.assertIsNotNone(promoted)
        self.assertEqual(promoted["name"], "Sub1")

        # Confirm Sub1 was moved into starters
        starter_names = [p["name"] for p in session["confirmed_players"]]
        self.assertIn("Sub1", starter_names)
        self.assertNotIn("Player2", starter_names)
        self.assertEqual(len(session["confirmed_players"]), 5)
        self.assertEqual(len(session["bench_substitutes"]), 1)
        self.assertEqual(session["bench_substitutes"][0]["name"], "Sub2")

    def test_session_reschedule_and_cancel(self):
        s = self.stats_mgr.create_session("s456", "Tonight 8pm", "Ranked Flex", False, "Leader")
        self.stats_mgr.register_player("s456", "Player1", "CONFIRMED", "Bot")
        self.stats_mgr.register_player("s456", "Player2", "BENCH", "Support")

        # Reschedule
        success, session, affected = self.stats_mgr.edit_session_time(
            "s456",
            new_scheduled_time="Friday Oct 30 at 9:00 PM PDT",
            new_scheduled_iso="2026-10-30T21:00:00-07:00",
            new_mode="Ranked 5s (Weekend Queue)",
            is_ranked_5s=True
        )
        self.assertTrue(success)
        self.assertEqual(session["scheduled_time"], "Friday Oct 30 at 9:00 PM PDT")
        self.assertEqual(session["mode"], "Ranked 5s (Weekend Queue)")
        self.assertEqual(set(affected), {"Player1", "Player2"})

        # Cancel
        can_success, can_session = self.stats_mgr.cancel_session("s456")
        self.assertTrue(can_success)
        self.assertEqual(can_session["status"], "CANCELLED")

    def test_15_minute_reminders(self):
        now = datetime.now(pytz.timezone("America/Vancouver"))
        target_in_10 = now + timedelta(minutes=10)
        target_in_40 = now + timedelta(minutes=40)

        # Session 1: in 10 minutes (should trigger)
        self.stats_mgr.create_session(
            "rem1",
            "Soon",
            "Flex",
            False,
            "Admin",
            scheduled_iso=target_in_10.isoformat()
        )

        # Session 2: in 40 minutes (should not trigger yet)
        self.stats_mgr.create_session(
            "rem2",
            "Later",
            "Flex",
            False,
            "Admin",
            scheduled_iso=target_in_40.isoformat()
        )

        pending = self.stats_mgr.get_pending_reminders(now)
        pending_ids = [p["session_id"] for p in pending]
        self.assertIn("rem1", pending_ids)
        self.assertNotIn("rem2", pending_ids)

        # Mark rem1 sent
        self.stats_mgr.mark_reminder_sent("rem1")
        pending_after = self.stats_mgr.get_pending_reminders(now)
        self.assertEqual(len(pending_after), 0)

    def test_multi_pair_synergies(self):
        # Create a match with complete lineup
        match = {
            "match_id": "TEST_MATCH_001",
            "date": "2026-10-26 14:00",
            "mode": "Ranked Flex",
            "result": "WIN",
            "lineup": {
                "Top": {"player": "David", "champion": "Ornn", "kills": 2, "deaths": 1, "assists": 8},
                "Jungle": {"player": "Marcus", "champion": "Vi", "kills": 6, "deaths": 2, "assists": 10},
                "Mid": {"player": "Elena", "champion": "Ahri", "kills": 8, "deaths": 1, "assists": 6},
                "Bot": {"player": "João", "champion": "Jinx", "kills": 12, "deaths": 2, "assists": 5},
                "Support": {"player": "Melanie", "champion": "Lulu", "kills": 1, "deaths": 1, "assists": 16},
            }
        }
        self.stats_mgr.log_match(match)

        # Botlane
        bot_duos = self.stats_mgr.get_botlane_synergies()
        self.assertEqual(len(bot_duos), 1)
        self.assertEqual(bot_duos[0]["player_a"], "João")
        self.assertEqual(bot_duos[0]["player_b"], "Melanie")
        self.assertEqual(bot_duos[0]["wins"], 1)

        # Mid + Jungle
        mj_duos = self.stats_mgr.get_mid_jungle_synergies()
        self.assertEqual(len(mj_duos), 1)
        self.assertEqual(mj_duos[0]["player_a"], "Elena")
        self.assertEqual(mj_duos[0]["player_b"], "Marcus")
        self.assertEqual(mj_duos[0]["wins"], 1)

        # Top + Jungle
        tj_duos = self.stats_mgr.get_top_jungle_synergies()
        self.assertEqual(len(tj_duos), 1)
        self.assertEqual(tj_duos[0]["player_a"], "David")
        self.assertEqual(tj_duos[0]["player_b"], "Marcus")

        # Support + Jungle
        sj_duos = self.stats_mgr.get_support_jungle_synergies()
        self.assertEqual(len(sj_duos), 1)
        self.assertEqual(sj_duos[0]["player_a"], "Melanie")
        self.assertEqual(sj_duos[0]["player_b"], "Marcus")

if __name__ == "__main__":
    unittest.main()
