import os
import tempfile
import unittest

from bot import bot, build_coach_embed, build_match_recap_embed
from data_manager import StatsManager
from export_dashboard import _compile_payload_from_manager
from rating_engine import (
    build_player_coaching_report,
    build_squad_coaching_summary,
    score_player_in_match,
)
from riot_api import RiotAPIClient


class TestPerformanceCoaching(unittest.TestCase):
    def setUp(self):
        self.temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
        self.temp_file.close()
        self.stats_mgr = StatsManager(filepath=self.temp_file.name)
        self.client = RiotAPIClient(api_key="mock_key", region="americas")
        self.stats_mgr.link_riot_account("101", "João", "puuid-joao", "João#BR1")
        self.stats_mgr.link_riot_account("102", "Melanie", "puuid-mel", "Melanie#NA1")
        self.linked = self.stats_mgr.get_linked_puuids()

    def tearDown(self):
        if os.path.exists(self.temp_file.name):
            os.remove(self.temp_file.name)

    def _make_match_and_timeline(self, match_id="NA1_COACH_1", win=False):
        match_data = {
            "metadata": {"matchId": match_id},
            "info": {
                "queueId": 440,
                "gameMode": "CLASSIC",
                "gameDuration": 1800,  # 30 min
                "gameEndTimestamp": 1700000000000,
                "participants": [
                    {
                        "participantId": 1,
                        "puuid": "puuid-joao",
                        "teamId": 100,
                        "teamPosition": "BOTTOM",
                        "championName": "Jinx",
                        "kills": 2 if not win else 11,
                        "deaths": 9 if not win else 1,
                        "assists": 3 if not win else 9,
                        "win": win,
                        "totalDamageDealtToChampions": 12000 if not win else 32000,
                        "totalMinionsKilled": 140 if not win else 245,
                        "neutralMinionsKilled": 0,
                        "visionScore": 12 if not win else 32,
                        "wardsPlaced": 6,
                        "detectorWardsPlaced": 0 if not win else 3,
                    },
                    {
                        "participantId": 2,
                        "puuid": "puuid-mel",
                        "teamId": 100,
                        "teamPosition": "UTILITY",
                        "championName": "Lulu",
                        "kills": 1,
                        "deaths": 2,
                        "assists": 16,
                        "win": win,
                        "totalDamageDealtToChampions": 7000,
                        "totalMinionsKilled": 15,
                        "neutralMinionsKilled": 0,
                        "visionScore": 65,
                        "wardsPlaced": 28,
                        "detectorWardsPlaced": 4,
                    },
                    {
                        "participantId": 3,
                        "puuid": "random-top",
                        "teamId": 100,
                        "teamPosition": "TOP",
                        "championName": "Ornn",
                        "kills": 3,
                        "deaths": 6,
                        "assists": 5,
                        "win": win,
                        "riotIdGameName": "RandomTop",
                        "riotIdTagline": "NA1",
                    },
                    {
                        "participantId": 6,
                        "puuid": "enemy-adc",
                        "teamId": 200,
                        "teamPosition": "BOTTOM",
                        "championName": "Caitlyn",
                        "kills": 8,
                        "deaths": 2,
                        "assists": 6,
                        "win": not win,
                    },
                ],
            },
        }
        timeline_data = {
            "info": {
                "frames": [
                    {
                        "timestamp": 600_000,  # 10m
                        "participantFrames": {
                            "1": {"totalGold": 2800 if not win else 4100, "minionsKilled": 62 if not win else 88, "jungleMinionsKilled": 0},
                            "6": {"totalGold": 3500, "minionsKilled": 80, "jungleMinionsKilled": 0},
                        },
                        "events": [
                            {"type": "CHAMPION_KILL", "timestamp": 540_000, "victimId": 1},
                        ],
                    },
                    {
                        "timestamp": 900_000,  # 15m
                        "participantFrames": {
                            "1": {"totalGold": 4400 if not win else 6500, "minionsKilled": 95 if not win else 135, "jungleMinionsKilled": 0},
                            "6": {"totalGold": 5600, "minionsKilled": 120, "jungleMinionsKilled": 0},
                        },
                        "events": [
                            {"type": "CHAMPION_KILL", "timestamp": 1_100_000, "victimId": 1},
                            {"type": "ELITE_MONSTER_KILL", "timestamp": 1_130_000},
                            {"type": "CHAMPION_KILL", "timestamp": 1_550_000, "victimId": 1},
                            {"type": "ELITE_MONSTER_KILL", "timestamp": 1_585_000},
                            {"type": "CHAMPION_KILL", "timestamp": 1_650_000, "victimId": 1},
                        ],
                    },
                ]
            }
        }
        return match_data, timeline_data

    def test_timeline_extraction_and_per_match_coaching_diagnostics(self):
        match_data, timeline_data = self._make_match_and_timeline("NA1_LOSS_1", win=False)
        record = self.client.parse_squad_match(match_data, self.linked, min_squad_size=2, timeline_data=timeline_data)
        self.assertIsNotNone(record)

        bot_entry = record["lineup"]["Bot"]
        tl = bot_entry.get("timeline")
        self.assertIsNotNone(tl)
        self.assertEqual(tl["gold_diff_10"], -700)
        self.assertEqual(tl["cs_diff_10"], -18)
        self.assertEqual(tl["gold_diff_15"], -1200)
        self.assertEqual(tl["cs_diff_15"], -25)
        self.assertEqual(tl["early_deaths"], 1)
        self.assertEqual(tl["mid_deaths"], 1)
        self.assertEqual(tl["late_deaths"], 2)
        self.assertEqual(tl["pre_objective_deaths"], 2)

        coaching = bot_entry["coaching"]
        self.assertTrue(coaching["has_timeline"])
        self.assertGreater(coaching["death_penalty"], 0)
        lever_keys = [lv["key"] for lv in coaching["levers"]]
        self.assertIn("excess_deaths", lever_keys)
        self.assertTrue(bot_entry["short_tip"].startswith("↑ "))

        # Clean high-performing win should get a clean cue
        win_match, win_tl = self._make_match_and_timeline("NA1_WIN_1", win=True)
        win_rec = self.client.parse_squad_match(win_match, self.linked, min_squad_size=2, timeline_data=win_tl)
        self.assertTrue(win_rec["lineup"]["Bot"]["short_tip"].startswith("✓ Clean game"))

    def test_multi_game_player_and_squad_coaching_reports(self):
        loss_m, loss_tl = self._make_match_and_timeline("NA1_LOSS_2", win=False)
        win_m, win_tl = self._make_match_and_timeline("NA1_WIN_2", win=True)
        self.stats_mgr.log_match(self.client.parse_squad_match(loss_m, self.linked, timeline_data=loss_tl))
        self.stats_mgr.log_match(self.client.parse_squad_match(win_m, self.linked, timeline_data=win_tl))

        report = self.stats_mgr.get_player_coaching_report("João")
        self.assertEqual(report["games_analyzed"], 2)
        self.assertEqual(report["wins"], 1)
        self.assertEqual(report["losses"], 1)
        self.assertTrue(len(report["top_focus_areas"]) >= 1)
        self.assertIsNotNone(report["win_vs_loss"]["wins"])
        self.assertIsNotNone(report["win_vs_loss"]["losses"])
        self.assertIsNotNone(report["win_vs_loss"]["biggest_loss_drop"])
        self.assertIsNotNone(report["death_profile"])
        self.assertEqual(report["death_profile"]["games_with_timeline"], 2)

        squad_summary = self.stats_mgr.get_squad_coaching_summary()
        self.assertEqual(squad_summary["games_analyzed"], 2)
        self.assertTrue(len(squad_summary["top_leaks"]) >= 1)

    def test_discord_recap_inline_cue_and_coach_embed(self):
        loss_m, loss_tl = self._make_match_and_timeline("NA1_LOSS_3", win=False)
        win_m, win_tl = self._make_match_and_timeline("NA1_WIN_3", win=True)
        loss_rec = self.client.parse_squad_match(loss_m, self.linked, timeline_data=loss_tl)
        win_rec = self.client.parse_squad_match(win_m, self.linked, timeline_data=win_tl)
        self.stats_mgr.log_match(loss_rec)
        self.stats_mgr.log_match(win_rec)

        recap = build_match_recap_embed(loss_rec)
        lineup_field = next(f for f in recap.fields if f.name == "Squad Lineup")
        self.assertIn("↳ ", lineup_field.value)
        # Random top should not get a squad coaching cue
        self.assertNotIn("RandomTop", lineup_field.value.split("↳")[1])

        report = self.stats_mgr.get_player_coaching_report("João")
        coach_embed = build_coach_embed(report)
        self.assertIn("Performance Coaching — João", coach_embed.title)
        field_names = [f.name for f in coach_embed.fields]
        self.assertIn("🔥 Top Recurring Focus Areas", field_names)
        self.assertIn("⚖️ Win vs. Loss Splits", field_names)
        self.assertIn("⏱️ Laning & Death Timing (Timeline)", field_names)
        self.assertIn("🧭 Role & Champion Fit", field_names)

        # Verify /coach command is registered
        cmd_names = {cmd.name for cmd in bot.tree.get_commands()}
        self.assertIn("coach", cmd_names)

    def test_dashboard_payload_includes_coaching_data(self):
        loss_m, loss_tl = self._make_match_and_timeline("NA1_LOSS_4", win=False)
        win_m, win_tl = self._make_match_and_timeline("NA1_WIN_4", win=True)
        self.stats_mgr.log_match(self.client.parse_squad_match(loss_m, self.linked, timeline_data=loss_tl))
        self.stats_mgr.log_match(self.client.parse_squad_match(win_m, self.linked, timeline_data=win_tl))

        payload = _compile_payload_from_manager(self.stats_mgr, is_demo=False)
        self.assertIn("squad_coaching", payload)
        self.assertEqual(payload["squad_coaching"]["games_analyzed"], 2)
        self.assertTrue(len(payload["squad_coaching"]["top_leaks"]) >= 1)

        joao_prof = next(p for p in payload["players"] if p["name"] == "João")
        self.assertIn("coaching", joao_prof)
        self.assertEqual(joao_prof["coaching"]["games_analyzed"], 2)
        self.assertIn("short_tip", joao_prof["recent_matches"][0])
        self.assertIn("coaching", payload["matches"][0]["lineup"]["Bot"])


if __name__ == "__main__":
    unittest.main()
