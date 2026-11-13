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

    def test_slash_command_change_detection(self):
        import json
        from bot import (
            bot,
            detect_slash_command_changes,
            save_slash_command_state,
            compute_commands_hash,
        )

        state_file = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
        state_file.close()
        os.remove(state_file.name)

        try:
            # 1. First run (no state file exists) -> changed=True, first_run=True
            diff1 = detect_slash_command_changes(bot.tree, state_file=state_file.name)
            self.assertTrue(diff1["changed"])
            self.assertTrue(diff1["first_run"])
            self.assertGreaterEqual(len(diff1["added"]), 12)

            # Save state
            save_slash_command_state(diff1["payloads"], diff1["current_hash"], state_file=state_file.name)

            # 2. Second check with identical tree -> changed=False
            diff2 = detect_slash_command_changes(bot.tree, state_file=state_file.name)
            self.assertFalse(diff2["changed"])
            self.assertFalse(diff2["first_run"])
            self.assertEqual(diff2["added"], [])
            self.assertEqual(diff2["modified"], [])
            self.assertEqual(diff2["removed"], [])

            # 3. Simulate a modified command description and a removed command in saved state
            with open(state_file.name, "r", encoding="utf-8") as f:
                saved = json.load(f)
            saved["commands"]["session"]["description"] = "Old description"
            saved["commands"]["legacy-cmd"] = {"name": "legacy-cmd", "description": "Old"}
            del saved["commands"]["roster"]
            saved["hash"] = compute_commands_hash(list(saved["commands"].values()))
            with open(state_file.name, "w", encoding="utf-8") as f:
                json.dump(saved, f)

            diff3 = detect_slash_command_changes(bot.tree, state_file=state_file.name)
            self.assertTrue(diff3["changed"])
            self.assertEqual(diff3["added"], ["roster"])
            self.assertEqual(diff3["modified"], ["session"])
            self.assertEqual(diff3["removed"], ["legacy-cmd"])
        finally:
            if os.path.exists(state_file.name):
                os.remove(state_file.name)

    def test_hybrid_session_activity_and_matches(self):
        from bot import build_session_embed

        s = self.stats_mgr.create_session("s_hyb", "Tonight 8:30 PM", "Ranked Flex", False, "Faker")
        self.stats_mgr.set_session_thread("s_hyb", 1122334455)
        self.stats_mgr.append_session_activity("s_hyb", "🔄 Rescheduled to Tonight 9:00 PM")

        # Attach a match to the active session
        matched = self.stats_mgr.attach_match_to_active_session({
            "match_id": "M_HYB_1",
            "result": "WIN",
            "mode": "Ranked Flex",
            "mvp": "Faker"
        })
        self.assertIsNotNone(matched)
        self.assertEqual(matched["session_id"], "s_hyb")
        self.assertEqual(len(matched["session_matches"]), 1)

        embed = build_session_embed(matched)
        self.assertIn("<#1122334455>", embed.description)
        field_names = [f.name for f in embed.fields]
        self.assertTrue(any("Session Match Log (1W - 0L)" in n for n in field_names))
        self.assertTrue(any("Recent Session Updates" in n for n in field_names))

    def test_living_synergy_thread_state_and_embed(self):
        from bot import build_synergy_embed

        self.stats_mgr.set_synergy_thread_state("botlane", thread_id=998877, message_id=665544)
        state = self.stats_mgr.get_synergy_thread_state("botlane")
        self.assertIsNotNone(state)
        self.assertEqual(state["thread_id"], 998877)
        self.assertEqual(state["message_id"], 665544)

        embed = build_synergy_embed("botlane", is_living_thread=True)
        self.assertIn("Botlane", embed.title)

    def test_github_feedback_formatting_and_rate_limit(self):
        from github_tickets import GitHubTicketClient

        client = GitHubTicketClient(repo="jgdclima/5-stacker-lol")
        payload = client.format_issue_payload(
            category="Bug Report",
            title="Duplicate messages on edit",
            description="Editing a session created a second card.",
            reporter_name="Doublelift",
            reporter_id="12345",
            session_id="abc12345",
        )
        self.assertEqual(payload["title"], "[Bug] Duplicate messages on edit")
        self.assertIn("bug", payload["labels"])
        self.assertIn("abc12345", payload["body"])
        self.assertIn("Doublelift", payload["body"])

        # Rate-limit check (default 5 per hour)
        for i in range(5):
            allowed, _ = self.stats_mgr.can_submit_feedback("user_99", max_per_hour=5)
            self.assertTrue(allowed)
            self.stats_mgr.record_feedback(
                user_id="user_99",
                user_name="Tester",
                category="Feature",
                title=f"Idea {i}",
                description="Details",
                issue_url=f"https://github.com/jgdclima/5-stacker-lol/issues/{i+1}",
                issue_number=i + 1,
            )

        allowed_after, remaining = self.stats_mgr.can_submit_feedback("user_99", max_per_hour=5)
        self.assertFalse(allowed_after)
        self.assertEqual(remaining, 0)

    def test_channel_and_thread_restriction_helper(self):
        from unittest.mock import MagicMock
        from bot import is_allowed_coordination_channel, COORDINATION_CHANNEL

        ch_main = MagicMock()
        ch_main.name = COORDINATION_CHANNEL
        ch_main.parent = None
        self.assertTrue(is_allowed_coordination_channel(ch_main))

        ch_thread = MagicMock()
        ch_thread.name = "🎮 Session 123"
        ch_thread.parent = ch_main
        self.assertTrue(is_allowed_coordination_channel(ch_thread))

        ch_other = MagicMock()
        ch_other.name = "general"
        ch_other.parent = None
        self.assertFalse(is_allowed_coordination_channel(ch_other))

    def test_synergy_excludes_non_lolers_and_reconciles_linked_players(self):
        # Log a match where Mid + Jungle has one @LOLers member (Ryan) and one random stranger (RandomMid#NA1)
        # and Bot + Support has a player recorded by raw Riot ID before linking (enkryptos#NA1) + Aditya
        match = {
            "match_id": "M_FILTER_TEST",
            "date": "2026-10-27 15:00",
            "mode": "Normal Draft",
            "result": "WIN",
            "mvp": "Ryan",
            "squad_players": ["Ryan", "Aditya"],
            "lineup": {
                "Top": {"player": "RandomTop#NA1", "is_squad": False, "champion": "Garen", "kills": 2, "deaths": 4, "assists": 3},
                "Jungle": {"player": "Ryan", "is_squad": True, "champion": "Sejuani", "kills": 5, "deaths": 2, "assists": 12},
                "Mid": {"player": "RandomMid#NA1", "is_squad": False, "champion": "Xerath", "kills": 10, "deaths": 1, "assists": 8},
                "Bot": {"player": "Aditya", "is_squad": True, "champion": "Sivir", "kills": 8, "deaths": 3, "assists": 9},
                "Support": {"player": "enkryptos#NA1", "is_squad": False, "champion": "Braum", "kills": 1, "deaths": 2, "assists": 15},
            }
        }
        self.stats_mgr.log_match(match)

        # 1. Before linking enkryptos#NA1:
        #    - Mid + Jungle must be empty (RandomMid#NA1 is not a @LOLers squad member)
        #    - Top + Jungle must be empty (RandomTop#NA1 is not a @LOLers squad member)
        #    - Botlane must be empty (enkryptos#NA1 has is_squad=False)
        self.assertEqual(self.stats_mgr.get_mid_jungle_synergies(), [])
        self.assertEqual(self.stats_mgr.get_top_jungle_synergies(), [])
        self.assertEqual(self.stats_mgr.get_botlane_synergies(), [])

        # 2. Now enkryptos links their Riot account (enkryptos#NA1) -> retroactively reconciled!
        self.stats_mgr.link_riot_account("19468", "enkryptos", "puuid-enk", "enkryptos#NA1")

        # Botlane (Aditya + enkryptos) and Support+Jungle (enkryptos + Ryan) now appear,
        # while RandomMid#NA1 and RandomTop#NA1 remain strictly excluded!
        bot_duos = self.stats_mgr.get_botlane_synergies()
        self.assertEqual(len(bot_duos), 1)
        self.assertEqual(bot_duos[0]["player_a"], "Aditya")
        self.assertEqual(bot_duos[0]["player_b"], "enkryptos")

        sj_duos = self.stats_mgr.get_support_jungle_synergies()
        self.assertEqual(len(sj_duos), 1)
        self.assertEqual(sj_duos[0]["player_a"], "enkryptos")
        self.assertEqual(sj_duos[0]["player_b"], "Ryan")

        self.assertEqual(self.stats_mgr.get_mid_jungle_synergies(), [])
        self.assertEqual(self.stats_mgr.get_top_jungle_synergies(), [])

        # 3. Verify min_games=3 threshold filters out pairs with < 3 games
        self.assertEqual(self.stats_mgr.get_botlane_synergies(min_games=3), [])
        for idx in (2, 3):
            extra = dict(match)
            extra["match_id"] = f"M_FILTER_TEST_{idx}"
            self.stats_mgr.log_match(extra)

        qualifying_bot = self.stats_mgr.get_botlane_synergies(min_games=3)
        self.assertEqual(len(qualifying_bot), 1)
        self.assertEqual(qualifying_bot[0]["games"], 3)

    def test_holistic_role_and_champion_rating_and_synergy(self):
        from rating_engine import evaluate_match_lineup_and_mvp

        record = {
            "match_id": "M_HOLISTIC_1",
            "date": "2026-10-27 18:00",
            "mode": "Ranked Flex",
            "result": "WIN",
            "duration_min": 30.0,
            "squad_players": ["Julian", "Ryan", "Aditya", "Joao/Brazil"],
            "lineup": {
                "Top": {
                    "player": "Julian",
                    "is_squad": True,
                    "champion": "Yorick",
                    "kills": 6,
                    "deaths": 2,
                    "assists": 5,
                    "damage": 28000,
                    "cs": 255,
                    "vision": 24,
                    "turret_damage": 14500,
                    "turret_takedowns": 5,
                    "turret_plates": 4,
                    "damage_taken": 26000,
                    "damage_mitigated": 32000,
                    "solo_kills": 2,
                },
                "Jungle": {
                    "player": "Ryan",
                    "is_squad": True,
                    "champion": "Sejuani",
                    "kills": 4,
                    "deaths": 2,
                    "assists": 18,
                    "damage": 16500,
                    "cs": 185,
                    "vision": 42,
                    "objective_damage": 28000,
                    "dragon_takedowns": 3,
                    "baron_takedowns": 1,
                    "void_monster_kills": 5,
                    "damage_taken": 31000,
                    "damage_mitigated": 45000,
                    "cc_score": 48,
                    "immobilize_and_kill_with_ally": 9,
                },
                "Mid": {
                    "player": "RandomCarry#NA1",
                    "is_squad": False,
                    "champion": "Xerath",
                    "kills": 19,
                    "deaths": 0,
                    "assists": 12,
                    "damage": 55000,
                    "cs": 300,
                    "vision": 35,
                },
                "Bot": {
                    "player": "Aditya",
                    "is_squad": True,
                    "champion": "Jinx",
                    "kills": 11,
                    "deaths": 2,
                    "assists": 10,
                    "damage": 34000,
                    "cs": 265,
                    "vision": 26,
                    "turret_damage": 6500,
                },
                "Support": {
                    "player": "Joao/Brazil",
                    "is_squad": True,
                    "champion": "Soraka",
                    "kills": 1,
                    "deaths": 1,
                    "assists": 24,
                    "damage": 6200,
                    "cs": 28,
                    "vision": 78,
                    "effective_heal_shield": 14500,
                    "save_ally_from_death": 4,
                    "wards_killed": 9,
                    "control_wards_placed": 5,
                },
            },
        }

        mvp, mvp_rating, lineup = evaluate_match_lineup_and_mvp(record)
        self.assertNotEqual(mvp, "RandomCarry#NA1")
        self.assertIn(mvp, ["Julian", "Ryan", "Aditya", "Joao/Brazil"])
        self.assertGreaterEqual(mvp_rating, 80.0)

        self.assertEqual(lineup["Top"]["archetype"], "splitpusher")
        self.assertEqual(lineup["Top"]["highlight"], "Splitpush Titan")
        self.assertEqual(lineup["Jungle"]["archetype"], "tank")
        self.assertEqual(lineup["Jungle"]["highlight"], "Objective Commander")
        self.assertEqual(lineup["Support"]["archetype"], "enchanter")
        self.assertEqual(lineup["Support"]["highlight"], "Peel & Enchanter Carry")
        self.assertGreaterEqual(lineup["Support"]["rating"], 82.0)

    def test_dynamic_discord_timestamp_formatting(self):
        from bot import get_session_timestamp, format_session_time, build_session_embed

        iso_str = "2026-11-06T20:00:00-07:00"
        dt = datetime.fromisoformat(iso_str)
        expected_ts = int(dt.timestamp())

        session_with_iso = {
            "session_id": "test_time_1",
            "scheduled_time": "Friday Nov 06 at 08:00 PM MST",
            "scheduled_iso": iso_str,
            "status": "POLLING",
            "confirmed_players": [],
            "creator": "Faker",
        }

        # 1. Timestamp extraction
        self.assertEqual(get_session_timestamp(session_with_iso), expected_ts)

        # 2. Formatted output styles
        card_fmt = format_session_time(session_with_iso, style="card")
        self.assertEqual(card_fmt, f"<t:{expected_ts}:F> (<t:{expected_ts}:R>)")

        short_fmt = format_session_time(session_with_iso, style="short")
        self.assertEqual(short_fmt, f"<t:{expected_ts}:f> (<t:{expected_ts}:R>)")

        list_fmt = format_session_time(session_with_iso, style="list")
        self.assertEqual(list_fmt, f"<t:{expected_ts}:f>")

        time_fmt = format_session_time(session_with_iso, style="time")
        self.assertEqual(time_fmt, f"<t:{expected_ts}:t>")

        # 3. Fallback when scheduled_iso is missing or invalid
        session_fallback = {
            "session_id": "test_time_2",
            "scheduled_time": "Tomorrow at 8pm",
            "status": "POLLING",
            "confirmed_players": [],
            "creator": "Faker",
        }
        self.assertIsNone(get_session_timestamp(session_fallback))
        self.assertEqual(format_session_time(session_fallback, style="card"), "Tomorrow at 8pm")

        # 4. Session embed uses dynamic timestamp and does not wrap it in backticks
        embed = build_session_embed(session_with_iso)
        self.assertIn(f"**Target Window**: <t:{expected_ts}:F> (<t:{expected_ts}:R>)", embed.description)
        # Ensure backticks are NOT present around the timestamp tag (backticks break Discord timestamp parsing)
        self.assertNotIn(f"`<t:{expected_ts}:F>`", embed.description)

    def test_append_session_activity_uses_discord_timestamp(self):
        s = self.stats_mgr.create_session("s_act", "Tonight 8:00 PM", "Ranked Flex", False, "Leader")
        updated = self.stats_mgr.append_session_activity("s_act", "Player confirmed")
        self.assertIsNotNone(updated)
        log = updated.get("activity_log", [])
        self.assertEqual(len(log), 1)
        # Verify it has <t:...:t> format
        import re
        self.assertTrue(re.match(r"^<t:\d+:t> Player confirmed$", log[0]))

    def test_evaluate_time_returns_timestamps(self):
        eval_res = self.scheduler.evaluate_time()
        self.assertIn("target_timestamp", eval_res)
        self.assertIsInstance(eval_res["target_timestamp"], int)
        if eval_res.get("next_window_start") != "N/A":
            self.assertIn("next_window_timestamp", eval_res)
            self.assertIsInstance(eval_res["next_window_timestamp"], int)

    def test_static_dashboard_export_and_faq_content(self):
        from export_dashboard import build_dashboard_payload, generate_dashboard

        # Create a session and log a match
        self.stats_mgr.create_session("dash_s1", "Friday 9:00 PM", "Ranked 5s", True, "João")
        self.stats_mgr.register_player("dash_s1", "João", "CONFIRMED", "Bot")
        self.stats_mgr.register_player("dash_s1", "Melanie", "CONFIRMED", "Support")

        match = {
            "match_id": "DASH_MATCH_1",
            "date": "2026-11-10 21:00",
            "mode": "Ranked 5s",
            "result": "WIN",
            "duration_min": 30.0,
            "lineup": {
                "Top": {"player": "David", "champion": "Ornn", "kills": 3, "deaths": 1, "assists": 12, "damage": 16000, "cs": 200, "vision": 25},
                "Jungle": {"player": "Marcus", "champion": "Vi", "kills": 7, "deaths": 2, "assists": 10, "damage": 21000, "cs": 175, "vision": 32},
                "Mid": {"player": "Elena", "champion": "Ahri", "kills": 9, "deaths": 1, "assists": 8, "damage": 27000, "cs": 225, "vision": 28},
                "Bot": {"player": "João", "champion": "Jinx", "kills": 12, "deaths": 1, "assists": 7, "damage": 35000, "cs": 250, "vision": 24},
                "Support": {"player": "Melanie", "champion": "Lulu", "kills": 1, "deaths": 1, "assists": 21, "damage": 6500, "cs": 30, "vision": 68},
            },
        }
        self.stats_mgr.log_match(match)

        payload = build_dashboard_payload(stats_mgr=self.stats_mgr)
        self.assertTrue(payload["has_live_matches"])
        self.assertEqual(payload["live"]["kpis"]["total_matches"], 1)
        self.assertEqual(payload["live"]["kpis"]["win_rate"], 100.0)
        self.assertGreaterEqual(len(payload["live"]["champions"]), 5)
        self.assertGreaterEqual(len(payload["live"]["synergies"]["botlane"]), 1)
        self.assertIn("role_weights", payload["rating_formulas"])
        self.assertIn("archetype_weights", payload["rating_formulas"])

        # Generate HTML file in temp location
        out_html = tempfile.NamedTemporaryFile(delete=False, suffix=".html")
        out_html.close()
        try:
            generated_path = generate_dashboard(stats_mgr=self.stats_mgr, output_path=out_html.name)
            self.assertTrue(os.path.exists(generated_path))
            with open(generated_path, "r", encoding="utf-8") as f:
                html_text = f.read()
            self.assertIn("DASH_MATCH_1", html_text)
            self.assertIn("How the Bot Gets Its Data", html_text)
            self.assertIn("Holistic Individual Performance Rating Engine", html_text)
            self.assertIn("issues/new", html_text)
        finally:
            if os.path.exists(out_html.name):
                os.remove(out_html.name)

    def test_dashboard_excludes_demo_data_outside_demo_preview(self):
        import json
        from export_dashboard import build_dashboard_payload, generate_dashboard

        # 1. Fresh StatsManager starts in live mode with empty players and no demo group name
        fresh_payload = build_dashboard_payload(stats_mgr=self.stats_mgr)
        self.assertFalse(fresh_payload["has_live_matches"])
        self.assertEqual(fresh_payload["live"]["group_name"], "5 Stackers")
        self.assertEqual(fresh_payload["live"]["players"], [])
        self.assertEqual(fresh_payload["live"]["matches"], [])
        self.assertEqual(fresh_payload["live"]["sessions"], [])

        # Demo payload remains populated for Demo Preview
        self.assertEqual(fresh_payload["demo"]["group_name"], "The Summoner's Ten")
        self.assertEqual(len(fresh_payload["demo"]["players"]), 10)
        self.assertGreater(len(fresh_payload["demo"]["matches"]), 0)

        # 2. Legacy persisted JSON with unlinked demo seed members strips them from live data
        legacy_file = tempfile.NamedTemporaryFile(delete=False, suffix=".json", mode="w", encoding="utf-8")
        json.dump({
            "group_name": "The Summoner's Ten",
            "members": [
                {"id": "1", "name": "João", "discord_tag": "Joao#1234", "primary_role": "Bot", "secondary_role": "Mid", "fav_champs": ["Jinx"]},
                {"id": "2", "name": "Melanie", "discord_tag": "Melanie#5678", "primary_role": "Support", "secondary_role": "Top", "fav_champs": ["Nami"]},
                {"id": "11", "name": "RealPlayer", "discord_id": "999999", "discord_tag": "RealPlayer", "riot_id": "Real#NA1", "puuid": "p-real", "primary_role": "Flex", "secondary_role": "Flex", "fav_champs": []},
            ],
            "active_sessions": {},
            "match_history": [],
        }, legacy_file)
        legacy_file.close()

        out_html = tempfile.NamedTemporaryFile(delete=False, suffix=".html")
        out_html.close()
        try:
            legacy_mgr = StatsManager(filepath=legacy_file.name)
            live_payload = build_dashboard_payload(stats_mgr=legacy_mgr)["live"]
            self.assertEqual(live_payload["group_name"], "5 Stackers")
            self.assertEqual([p["name"] for p in live_payload["players"]], ["RealPlayer"])

            generate_dashboard(stats_mgr=legacy_mgr, output_path=out_html.name)
            with open(out_html.name, "r", encoding="utf-8") as f:
                html_text = f.read()
            self.assertIn('<script id="dashboard-data" type="application/json">', html_text)
            self.assertIn('"RealPlayer"', html_text)

            with open(os.path.join("web", "js", "app.js"), "r", encoding="utf-8") as f:
                app_js = f.read()
            self.assertIn("let datasetMode = 'demo';", app_js)
            self.assertIn("requestedMode === 'live' ? 'live' : 'demo'", app_js)
        finally:
            if os.path.exists(legacy_file.name):
                os.remove(legacy_file.name)
            if os.path.exists(out_html.name):
                os.remove(out_html.name)

    def test_live_payload_privacy_sanitization(self):
        from export_dashboard import build_dashboard_payload

        self.stats_mgr.link_riot_account("123456789012345678", "SanitizedUser", "secret-puuid-123", "Sanitized#NA1")
        self.stats_mgr.create_session(
            "sess_priv",
            "Friday 9:00 PM",
            "Ranked 5s",
            True,
            "SanitizedUser",
            creator_id="123456789012345678",
        )
        self.stats_mgr.set_session_message("sess_priv", 9876543210, 1122334455)
        self.stats_mgr.set_session_thread("sess_priv", 5566778899)
        self.stats_mgr.log_match({
            "match_id": "PRIV_MATCH_1",
            "date": "2026-11-13 20:00",
            "mode": "Ranked 5s",
            "result": "WIN",
            "duration_min": 29.0,
            "lineup": {
                "Bot": {
                    "player": "SanitizedUser",
                    "puuid": "secret-puuid-123",
                    "is_squad": True,
                    "champion": "Jinx",
                    "kills": 9,
                    "deaths": 2,
                    "assists": 10,
                    "damage": 31000,
                    "cs": 230,
                    "vision": 24,
                }
            },
        })

        payload = build_dashboard_payload(stats_mgr=self.stats_mgr)
        live = payload["live"]

        player = next((p for p in live["players"] if p["name"] == "SanitizedUser"), None)
        self.assertIsNotNone(player)
        self.assertEqual(player["id"], "")
        self.assertNotIn("discord_id", player)
        self.assertEqual(len(player["accounts"]), 1)
        self.assertEqual(player["accounts"][0]["riot_id"], "Sanitized#NA1")
        self.assertNotIn("puuid", player["accounts"][0])

        sess = next((s for s in live["sessions"] if s["session_id"] == "sess_priv"), None)
        self.assertIsNotNone(sess)
        self.assertEqual(sess["creator"], "SanitizedUser")
        for key in ("creator_id", "channel_id", "message_id", "thread_id"):
            self.assertNotIn(key, sess)

        match = live["matches"][0]
        self.assertEqual(match["match_id"], "PRIV_MATCH_1")
        self.assertNotIn("puuid", match["lineup"]["Bot"])

    def test_modular_web_assets_and_json_export(self):
        import json
        import shutil
        from export_dashboard import export_dashboard_data, generate_dashboard

        required_files = [
            os.path.join("web", "index.html"),
            os.path.join("web", "case-study.html"),
            os.path.join("web", "css", "styles.css"),
            os.path.join("web", "js", "app.js"),
            os.path.join("web", "js", "data-loader.js"),
            os.path.join("web", "js", "squad-builder.js"),
            os.path.join("web", "js", "insights.js"),
            os.path.join("web", "js", "charts.js"),
            os.path.join("web", "js", "views.js"),
            os.path.join("web", "js", "utils.js"),
        ]
        for path in required_files:
            self.assertTrue(os.path.exists(path), f"Missing modular web asset: {path}")
            self.assertGreater(os.path.getsize(path), 0, f"Empty modular web asset: {path}")

        with open(os.path.join("web", "index.html"), "r", encoding="utf-8") as f:
            original_index = f.read()

        temp_dir = tempfile.mkdtemp()
        try:
            res = export_dashboard_data(stats_mgr=self.stats_mgr, data_dir=temp_dir)
            self.assertTrue(os.path.exists(res["live_path"]))
            self.assertTrue(os.path.exists(res["demo_path"]))
            self.assertTrue(os.path.exists(res["bundle_path"]))

            with open(res["live_path"], "r", encoding="utf-8") as f:
                live_doc = json.load(f)
            with open(res["demo_path"], "r", encoding="utf-8") as f:
                demo_doc = json.load(f)
            with open(res["bundle_path"], "r", encoding="utf-8") as f:
                bundle_js = f.read()

            self.assertIn("dataset", live_doc)
            self.assertIn("rating_formulas", live_doc)
            self.assertEqual(len(demo_doc["dataset"]["players"]), 10)
            self.assertTrue(bundle_js.startswith("window.__DASHBOARD_BUNDLE__ = "))

            # generate_dashboard targeting web/index.html must never overwrite the modular HTML shell
            generate_dashboard(stats_mgr=self.stats_mgr, output_path="web/index.html", data_dir=temp_dir)
            with open(os.path.join("web", "index.html"), "r", encoding="utf-8") as f:
                after_index = f.read()
            self.assertEqual(original_index, after_index)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_github_pages_match_sync_client(self):
        import asyncio
        import base64
        import json
        from unittest.mock import patch
        from export_dashboard import build_dashboard_payload, build_live_payload_document, sync_live_payload_to_github_pages

        # 1. Skips gracefully without token
        skip_res = asyncio.run(sync_live_payload_to_github_pages(stats_mgr=self.stats_mgr, token=""))
        self.assertFalse(skip_res["success"])
        self.assertTrue(skip_res["skipped"])

        # 2. Mocks aiohttp.ClientSession for create (404 -> PUT 201) and unchanged (200 -> skip PUT)
        recorded_calls = []

        class MockResponse:
            def __init__(self, status, payload):
                self.status = status
                self._payload = payload

            async def json(self):
                return self._payload

            async def text(self):
                return json.dumps(self._payload)

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

        def make_session_cls(get_status, get_payload, put_status=201):
            class MockSession:
                async def __aenter__(self):
                    return self

                async def __aexit__(self, exc_type, exc, tb):
                    return False

                def get(self, url, **kwargs):
                    recorded_calls.append(("GET", url, kwargs))
                    return MockResponse(get_status, get_payload)

                def put(self, url, **kwargs):
                    recorded_calls.append(("PUT", url, kwargs))
                    return MockResponse(put_status, {"content": {"html_url": "https://github.com/jgdclima/5-stacker-lol/blob/gh-pages/data/live_payload.json"}})

            return MockSession

        with patch("export_dashboard.aiohttp.ClientSession", make_session_cls(404, {"message": "Not Found"})):
            res = asyncio.run(
                sync_live_payload_to_github_pages(
                    stats_mgr=self.stats_mgr,
                    repo="jgdclima/5-stacker-lol",
                    token="ghp_mock_token",
                )
            )
        self.assertTrue(res["success"])
        self.assertFalse(res["unchanged"])
        put_call = next(c for c in recorded_calls if c[0] == "PUT")
        self.assertEqual(put_call[1], "https://api.github.com/repos/jgdclima/5-stacker-lol/contents/data/live_payload.json")
        put_json = put_call[2]["json"]
        self.assertEqual(put_json["branch"], "gh-pages")
        decoded_doc = json.loads(base64.b64decode(put_json["content"]).decode("utf-8"))
        self.assertIn("dataset", decoded_doc)

        # Case B: Existing remote dataset matches -> skip PUT
        recorded_calls.clear()
        expected_doc = build_live_payload_document(build_dashboard_payload(stats_mgr=self.stats_mgr))
        existing_b64 = base64.b64encode(json.dumps(expected_doc).encode("utf-8")).decode("ascii")
        with patch(
            "export_dashboard.aiohttp.ClientSession",
            make_session_cls(200, {"sha": "abc123", "content": existing_b64, "html_url": "https://example.com/live.json"}),
        ):
            res_unchanged = asyncio.run(
                sync_live_payload_to_github_pages(
                    stats_mgr=self.stats_mgr,
                    repo="jgdclima/5-stacker-lol",
                    token="ghp_mock_token",
                )
            )
        self.assertTrue(res_unchanged["success"])
        self.assertTrue(res_unchanged["unchanged"])
        self.assertFalse(any(c[0] == "PUT" for c in recorded_calls))

    def test_dashboard_infers_primary_and_secondary_roles_from_history(self):
        from export_dashboard import build_dashboard_payload

        self.stats_mgr.link_riot_account("101", "BotMain", "puuid-101", "BotMain#NA1")
        self.stats_mgr.link_riot_account("102", "JngOTP", "puuid-102", "JngOTP#NA1")
        self.stats_mgr.link_riot_account("103", "ZeroGames", "puuid-103", "ZeroGames#NA1")

        # BotMain: 2 Bot games, 1 Top game -> primary=Bot, secondary=Top
        # JngOTP: 3 Jungle games -> primary=Jungle, secondary=Fill
        # ZeroGames: 0 games -> primary=Flex, secondary=Flex
        matches = [
            ("ROLE_M1", "WIN", "Bot", "Jinx", "Jungle", "Vi"),
            ("ROLE_M2", "WIN", "Bot", "Kai'Sa", "Jungle", "Jarvan IV"),
            ("ROLE_M3", "LOSS", "Top", "Ornn", "Jungle", "Sejuani"),
        ]
        for idx, (mid, res, r1, c1, r2, c2) in enumerate(matches, start=1):
            self.stats_mgr.log_match({
                "match_id": mid,
                "date": f"2026-11-1{idx} 20:00",
                "mode": "Ranked Flex",
                "result": res,
                "duration_min": 30.0,
                "lineup": {
                    r1: {"player": "BotMain", "puuid": "puuid-101", "is_squad": True, "champion": c1, "kills": 7, "deaths": 2, "assists": 8, "damage": 24000, "cs": 210, "vision": 20},
                    r2: {"player": "JngOTP", "puuid": "puuid-102", "is_squad": True, "champion": c2, "kills": 5, "deaths": 3, "assists": 12, "damage": 18000, "cs": 170, "vision": 30},
                },
            })

        live = build_dashboard_payload(stats_mgr=self.stats_mgr)["live"]
        by_name = {p["name"]: p for p in live["players"]}

        self.assertEqual(by_name["BotMain"]["primary_role"], "Bot")
        self.assertEqual(by_name["BotMain"]["secondary_role"], "Top")
        self.assertEqual(by_name["BotMain"]["main_role"], "Bot")

        self.assertEqual(by_name["JngOTP"]["primary_role"], "Jungle")
        self.assertEqual(by_name["JngOTP"]["secondary_role"], "Fill")
        self.assertEqual(by_name["JngOTP"]["main_role"], "Jungle")

        self.assertEqual(by_name["ZeroGames"]["primary_role"], "Flex")
        self.assertEqual(by_name["ZeroGames"]["secondary_role"], "Flex")

    def test_dashboard_splits_champion_stats_by_role(self):
        from export_dashboard import build_dashboard_payload

        self.stats_mgr.link_riot_account("201", "FlexThresh", "puuid-201", "FlexThresh#NA1")
        self.stats_mgr.link_riot_account("202", "BotPartner", "puuid-202", "BotPartner#NA1")

        # FlexThresh plays Thresh Support (WIN) and Thresh Top (LOSS)
        self.stats_mgr.log_match({
            "match_id": "CHAMP_ROLE_1",
            "date": "2026-11-12 20:00",
            "mode": "Ranked Flex",
            "result": "WIN",
            "duration_min": 30.0,
            "lineup": {
                "Support": {"player": "FlexThresh", "puuid": "puuid-201", "is_squad": True, "champion": "Thresh", "kills": 1, "deaths": 2, "assists": 18, "damage": 7500, "cs": 30, "vision": 65},
                "Bot": {"player": "BotPartner", "puuid": "puuid-202", "is_squad": True, "champion": "Jinx", "kills": 10, "deaths": 2, "assists": 7, "damage": 32000, "cs": 230, "vision": 22},
            },
        })
        self.stats_mgr.log_match({
            "match_id": "CHAMP_ROLE_2",
            "date": "2026-11-12 21:00",
            "mode": "Ranked Flex",
            "result": "LOSS",
            "duration_min": 30.0,
            "lineup": {
                "Top": {"player": "FlexThresh", "puuid": "puuid-201", "is_squad": True, "champion": "Thresh", "kills": 4, "deaths": 5, "assists": 5, "damage": 19000, "cs": 185, "vision": 24},
                "Bot": {"player": "BotPartner", "puuid": "puuid-202", "is_squad": True, "champion": "Jinx", "kills": 6, "deaths": 4, "assists": 4, "damage": 24000, "cs": 210, "vision": 20},
            },
        })

        live = build_dashboard_payload(stats_mgr=self.stats_mgr)["live"]
        thresh_entries = {(c["champion"], c["role"]): c for c in live["champions"] if c["champion"] == "Thresh"}
        self.assertEqual(set(thresh_entries.keys()), {("Thresh", "Support"), ("Thresh", "Top")})
        self.assertEqual(thresh_entries[("Thresh", "Support")]["picks"], 1)
        self.assertEqual(thresh_entries[("Thresh", "Support")]["win_rate"], 100.0)
        self.assertEqual(thresh_entries[("Thresh", "Top")]["picks"], 1)
        self.assertEqual(thresh_entries[("Thresh", "Top")]["win_rate"], 0.0)

        flex_player = next(p for p in live["players"] if p["name"] == "FlexThresh")
        pool_entries = {(c["champion"], c["role"]): c for c in flex_player["champion_pool"]}
        self.assertEqual(set(pool_entries.keys()), {("Thresh", "Support"), ("Thresh", "Top")})
        self.assertEqual(pool_entries[("Thresh", "Support")]["wins"], 1)
        self.assertEqual(pool_entries[("Thresh", "Top")]["losses"], 1)


if __name__ == "__main__":
    unittest.main()
