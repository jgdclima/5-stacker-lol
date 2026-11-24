import os
import tempfile
import unittest

from bot import build_match_recap_embed, build_session_embed
from data_manager import StatsManager, is_remake_record
from export_dashboard import _compile_payload_from_manager, sanitize_live_payload
from riot_api import RiotAPIClient, is_remake_match


class TestRemakeHandling(unittest.TestCase):
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

    def _make_riot_match(self, match_id, duration_sec=1800, early_surrender=False, win=True):
        return {
            "metadata": {"matchId": match_id},
            "info": {
                "queueId": 440,
                "gameMode": "CLASSIC",
                "gameDuration": duration_sec,
                "gameEndTimestamp": 1700000000000,
                "participants": [
                    {
                        "puuid": "puuid-joao",
                        "teamId": 100,
                        "teamPosition": "BOTTOM",
                        "championName": "Jinx",
                        "kills": 0 if early_surrender else 8,
                        "deaths": 0 if early_surrender else 2,
                        "assists": 0 if early_surrender else 6,
                        "win": win,
                        "gameEndedInEarlySurrender": early_surrender,
                        "totalDamageDealtToChampions": 200 if early_surrender else 22000,
                        "totalMinionsKilled": 10 if early_surrender else 190,
                        "neutralMinionsKilled": 0,
                        "visionScore": 2 if early_surrender else 24,
                    },
                    {
                        "puuid": "puuid-mel",
                        "teamId": 100,
                        "teamPosition": "UTILITY",
                        "championName": "Lulu",
                        "kills": 0 if early_surrender else 1,
                        "deaths": 0 if early_surrender else 1,
                        "assists": 0 if early_surrender else 14,
                        "win": win,
                        "gameEndedInEarlySurrender": early_surrender,
                        "totalDamageDealtToChampions": 100 if early_surrender else 7500,
                        "totalMinionsKilled": 1 if early_surrender else 18,
                        "neutralMinionsKilled": 0,
                        "visionScore": 3 if early_surrender else 50,
                    },
                ],
            },
        }

    def test_riot_api_detects_early_surrender_and_short_duration_remakes(self):
        early_ff = self._make_riot_match("NA1_REMAKE_1", duration_sec=195, early_surrender=True, win=False)
        short_dur = self._make_riot_match("NA1_REMAKE_2", duration_sec=210, early_surrender=False, win=False)
        normal = self._make_riot_match("NA1_NORMAL_1", duration_sec=1800, early_surrender=False, win=True)

        self.assertTrue(is_remake_match(early_ff))
        self.assertTrue(is_remake_match(short_dur))
        self.assertFalse(is_remake_match(normal))

        rec_remake = self.client.parse_squad_match(early_ff, self.linked, min_squad_size=2)
        self.assertIsNotNone(rec_remake)
        self.assertTrue(rec_remake["is_remake"])
        self.assertEqual(rec_remake["result"], "REMAKE")
        self.assertEqual(rec_remake["mvp"], "N/A")
        self.assertNotIn("rating", rec_remake["lineup"]["Bot"])

        rec_short = self.client.parse_squad_match(short_dur, self.linked, min_squad_size=2)
        self.assertTrue(rec_short["is_remake"])
        self.assertEqual(rec_short["result"], "REMAKE")

        rec_normal = self.client.parse_squad_match(normal, self.linked, min_squad_size=2)
        self.assertFalse(rec_normal["is_remake"])
        self.assertEqual(rec_normal["result"], "WIN")
        self.assertIn("rating", rec_normal["lineup"]["Bot"])

    def test_data_manager_excludes_remakes_from_leaderboard_and_synergies(self):
        normal = self.client.parse_squad_match(
            self._make_riot_match("NA1_WIN_1", duration_sec=1800, early_surrender=False, win=True),
            self.linked,
        )
        remake = self.client.parse_squad_match(
            self._make_riot_match("NA1_REM_1", duration_sec=185, early_surrender=True, win=False),
            self.linked,
        )
        # Also simulate a legacy pre-fix remake stored as LOSS with duration_min < 5
        legacy_remake = {
            "match_id": "NA1_LEGACY_REM",
            "date": "2026-11-20 21:00",
            "mode": "Ranked Flex",
            "result": "LOSS",
            "duration_min": 3.1,
            "mvp": "João",
            "squad_players": ["João", "Melanie"],
            "lineup": {
                "Bot": {"player": "João", "is_squad": True, "champion": "Jinx", "kills": 0, "deaths": 0, "assists": 0},
                "Support": {"player": "Melanie", "is_squad": True, "champion": "Lulu", "kills": 0, "deaths": 0, "assists": 0},
            },
        }

        self.stats_mgr.log_match(normal)
        self.stats_mgr.log_match(remake)
        self.stats_mgr.log_match(legacy_remake)

        self.assertTrue(self.stats_mgr.is_match_logged("NA1_REM_1"))
        self.assertTrue(is_remake_record(legacy_remake))
        self.assertEqual(legacy_remake["result"], "REMAKE")

        leaderboard = self.stats_mgr.get_player_leaderboard()
        joao = next(p for p in leaderboard if p["name"] == "João")
        self.assertEqual(joao["games"], 1)
        self.assertEqual(joao["wins"], 1)
        self.assertEqual(joao["losses"], 0)
        self.assertEqual(joao["win_rate"], 100.0)

        synergies = self.stats_mgr.get_botlane_synergies()
        self.assertEqual(len(synergies), 1)
        self.assertEqual(synergies[0]["games"], 1)
        self.assertEqual(synergies[0]["wins"], 1)
        self.assertEqual(synergies[0]["losses"], 0)

    def test_bot_session_and_recap_embeds_handle_remakes_separately(self):
        session = self.stats_mgr.create_session("sess-remake", "Tonight 8:00 PM", "Ranked Flex", False, "João")
        normal = self.client.parse_squad_match(
            self._make_riot_match("NA1_WIN_2", duration_sec=1800, early_surrender=False, win=True),
            self.linked,
        )
        remake = self.client.parse_squad_match(
            self._make_riot_match("NA1_REM_2", duration_sec=185, early_surrender=True, win=False),
            self.linked,
        )
        self.stats_mgr.attach_match_to_active_session(normal)
        updated_session = self.stats_mgr.attach_match_to_active_session(remake)

        sess_embed = build_session_embed(updated_session)
        match_log_field = next(f for f in sess_embed.fields if f.name.startswith("🎮 Session Match Log"))
        self.assertIn("1W - 0L • 1 Remake", match_log_field.name)
        self.assertIn("🔄 REMAKE", match_log_field.value)

        recap_embed = build_match_recap_embed(remake)
        self.assertTrue(recap_embed.title.startswith("🔄 Remake"))
        self.assertIn("Excluded from W-L", recap_embed.description)
        self.assertFalse(any("Botlane Synergy" in f.name for f in recap_embed.fields))

    def test_export_dashboard_excludes_remakes_from_kpis_and_sanitizes_remake_matches(self):
        normal = self.client.parse_squad_match(
            self._make_riot_match("NA1_WIN_3", duration_sec=1800, early_surrender=False, win=True),
            self.linked,
        )
        remake = self.client.parse_squad_match(
            self._make_riot_match("NA1_REM_3", duration_sec=190, early_surrender=True, win=False),
            self.linked,
        )
        self.stats_mgr.log_match(normal)
        self.stats_mgr.log_match(remake)

        payload = _compile_payload_from_manager(self.stats_mgr, is_demo=False)
        self.assertEqual(payload["kpis"]["total_matches"], 1)
        self.assertEqual(payload["kpis"]["remakes"], 1)
        self.assertEqual(payload["kpis"]["wins"], 1)
        self.assertEqual(payload["kpis"]["losses"], 0)
        self.assertEqual(payload["kpis"]["win_rate"], 100.0)
        self.assertEqual(payload["kpis"]["streak_type"], "WIN")
        self.assertEqual(payload["kpis"]["streak_count"], 1)
        self.assertEqual(len(payload["matches"]), 1)
        self.assertEqual(len(payload["remake_matches"]), 1)
        self.assertEqual(payload["remake_matches"][0]["result"], "REMAKE")

        sanitized = sanitize_live_payload(payload)
        for pdata in sanitized["remake_matches"][0]["lineup"].values():
            self.assertNotIn("puuid", pdata)


if __name__ == "__main__":
    unittest.main()
