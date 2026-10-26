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
        can_success, can_session, affected = self.stats_mgr.cancel_session("s456")
        self.assertTrue(can_success)
        self.assertEqual(can_session["status"], "CANCELLED")
        self.assertEqual(set(affected), {"Player1", "Player2"})

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

    def test_session_message_tracking(self):
        s = self.stats_mgr.create_session("s_msg", "Tonight 9pm", "Ranked Flex", False, "Organizer", creator_id="12345")
        self.assertEqual(s["creator_id"], "12345")
        self.assertIsNone(s["message_id"])

        self.stats_mgr.set_session_message("s_msg", channel_id=9876, message_id=54321)
        fetched = self.stats_mgr.get_session("s_msg")
        self.assertEqual(fetched["channel_id"], 9876)
        self.assertEqual(fetched["message_id"], 54321)

    def test_session_complete_manual(self):
        s = self.stats_mgr.create_session("s_comp", "Tonight 9pm", "Ranked Flex", False, "Organizer")
        self.assertEqual(s["status"], "POLLING")

        success, completed = self.stats_mgr.complete_session("s_comp")
        self.assertTrue(success)
        self.assertEqual(completed["status"], "COMPLETED")

    def test_session_lifecycle_and_low_player_count(self):
        tz = pytz.timezone("America/Vancouver")
        now = datetime.now(tz)
        target_now = now - timedelta(minutes=5)
        target_expired = now - timedelta(hours=5)

        # 1. Session with 2 players whose start time has arrived -> transitions to IN_PROGRESS, not expired!
        s1 = self.stats_mgr.create_session("s_live", "Now", "Flex", False, "Leader", scheduled_iso=target_now.isoformat())
        self.stats_mgr.register_player("s_live", "PlayerA", "CONFIRMED", "Top")
        self.stats_mgr.register_player("s_live", "PlayerB", "CONFIRMED", "Mid")
        self.assertEqual(s1["status"], "POLLING")

        # 2. Session 5 hours past start time -> transitions to COMPLETED
        s2 = self.stats_mgr.create_session("s_past", "Past", "Flex", False, "Leader", scheduled_iso=target_expired.isoformat())

        changed = self.stats_mgr.check_session_lifecycle(now)
        changed_ids = {c["session_id"]: c["status"] for c in changed}

        self.assertIn("s_live", changed_ids)
        self.assertEqual(changed_ids["s_live"], "IN_PROGRESS")

        self.assertIn("s_past", changed_ids)
        self.assertEqual(changed_ids["s_past"], "COMPLETED")

    def test_get_active_sessions(self):
        self.stats_mgr.create_session("act1", "Today 8pm", "Flex", False, "Admin")
        self.stats_mgr.create_session("act2", "Today 9pm", "Flex", False, "Admin")
        self.stats_mgr.create_session("canc1", "Today 10pm", "Flex", False, "Admin")
        self.stats_mgr.cancel_session("canc1")

        active = self.stats_mgr.get_active_sessions()
        active_ids = [s["session_id"] for s in active]
        self.assertIn("act1", active_ids)
        self.assertIn("act2", active_ids)
        self.assertNotIn("canc1", active_ids)

    def test_build_session_embed_statuses(self):
        from bot import build_session_embed

        s_polling = {"session_id": "test1", "status": "POLLING", "confirmed_players": [], "creator": "Faker"}
        e1 = build_session_embed(s_polling)
        self.assertIn("RECRUITING", e1.description)
        self.assertIn("Faker", e1.description)

        s_ready = {"session_id": "test2", "status": "READY", "confirmed_players": [{"name": f"P{i}", "role_pref": "Fill"} for i in range(5)], "creator": "Faker"}
        e2 = build_session_embed(s_ready)
        self.assertIn("LOBBY READY", e2.description)

        s_progress = {"session_id": "test3", "status": "IN_PROGRESS", "confirmed_players": [], "creator": "Faker"}
        e3 = build_session_embed(s_progress)
        self.assertIn("IN PROGRESS", e3.description)

        s_completed = {"session_id": "test4", "status": "COMPLETED", "confirmed_players": [], "creator": "Faker"}
        e4 = build_session_embed(s_completed)
        self.assertIn("COMPLETED", e4.description)

        s_cancelled = {"session_id": "test5", "status": "CANCELLED", "confirmed_players": [], "creator": "Faker"}
        e5 = build_session_embed(s_cancelled)
        self.assertIn("CANCELLED", e5.description)

    def test_is_session_organizer_or_admin(self):
        from unittest.mock import MagicMock
        from bot import is_session_organizer_or_admin
        import discord

        session = {"creator": "Leader", "creator_id": "999"}

        # Member matching creator_id
        m1 = MagicMock(spec=discord.Member)
        m1.id = 999
        m1.display_name = "DifferentName"
        m1.guild_permissions.administrator = False
        m1.guild_permissions.manage_guild = False
        m1.guild_permissions.manage_channels = False
        self.assertTrue(is_session_organizer_or_admin(m1, session))

        # Member matching display name
        m2 = MagicMock(spec=discord.Member)
        m2.id = 888
        m2.display_name = "Leader"
        m2.guild_permissions.administrator = False
        m2.guild_permissions.manage_guild = False
        m2.guild_permissions.manage_channels = False
        self.assertTrue(is_session_organizer_or_admin(m2, session))

        # Admin member
        m3 = MagicMock(spec=discord.Member)
        m3.id = 777
        m3.display_name = "AdminUser"
        m3.guild_permissions.administrator = True
        self.assertTrue(is_session_organizer_or_admin(m3, session))

        # Random user without match or admin
        m4 = MagicMock(spec=discord.Member)
        m4.id = 111
        m4.display_name = "RandomUser"
        m4.name = "RandomUser"
        m4.guild_permissions.administrator = False
        m4.guild_permissions.manage_guild = False
        m4.guild_permissions.manage_channels = False
        self.assertFalse(is_session_organizer_or_admin(m4, session))

if __name__ == "__main__":
    unittest.main()
