import unittest
import os
import json
import tempfile
from riot_api import RiotAPIClient
from data_manager import StatsManager

class TestRiotIntegration(unittest.TestCase):
    def setUp(self):
        self.temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
        self.temp_file.close()
        self.stats_mgr = StatsManager(filepath=self.temp_file.name)
        self.client = RiotAPIClient(api_key="mock_key", region="americas")

    def tearDown(self):
        if os.path.exists(self.temp_file.name):
            os.remove(self.temp_file.name)

    def test_account_linking(self):
        info = self.stats_mgr.link_riot_account(
            discord_id="123456789",
            display_name="Doublelift",
            puuid="puuid-dl-123",
            riot_id="Doublelift#NA1"
        )
        self.assertEqual(info["puuid"], "puuid-dl-123")
        self.assertEqual(info["riot_id"], "Doublelift#NA1")

        linked = self.stats_mgr.get_linked_puuids()
        self.assertIn("puuid-dl-123", linked)
        self.assertEqual(linked["puuid-dl-123"]["name"], "Doublelift")

    def test_parse_squad_match_and_dedup(self):
        # Register 2 squad members (Bot and Support)
        self.stats_mgr.link_riot_account("101", "João", "puuid-joao", "João#BR1")
        self.stats_mgr.link_riot_account("102", "Melanie", "puuid-mel", "Melanie#NA1")
        linked = self.stats_mgr.get_linked_puuids()

        mock_match = {
            "metadata": {
                "matchId": "NA1_50000001"
            },
            "info": {
                "queueId": 440,
                "gameMode": "CLASSIC",
                "gameDuration": 1800,
                "gameEndTimestamp": 1700000000000,
                "participants": [
                    {
                        "puuid": "puuid-joao",
                        "teamId": 100,
                        "teamPosition": "BOTTOM",
                        "championName": "Jinx",
                        "kills": 10,
                        "deaths": 1,
                        "assists": 8,
                        "win": True,
                        "totalDamageDealtToChampions": 25000,
                        "totalMinionsKilled": 200,
                        "neutralMinionsKilled": 10,
                        "visionScore": 25
                    },
                    {
                        "puuid": "puuid-mel",
                        "teamId": 100,
                        "teamPosition": "UTILITY",
                        "championName": "Lulu",
                        "kills": 1,
                        "deaths": 2,
                        "assists": 18,
                        "win": True,
                        "totalDamageDealtToChampions": 8000,
                        "totalMinionsKilled": 20,
                        "neutralMinionsKilled": 0,
                        "visionScore": 55
                    },
                    {
                        "puuid": "other-top",
                        "teamId": 100,
                        "teamPosition": "TOP",
                        "championName": "Ornn",
                        "kills": 3,
                        "deaths": 2,
                        "assists": 10,
                        "win": True,
                        "riotIdGameName": "RandomTop",
                        "riotIdTagline": "NA1"
                    },
                    {
                        "puuid": "enemy-1",
                        "teamId": 200,
                        "teamPosition": "BOTTOM",
                        "championName": "Ezreal",
                        "kills": 2,
                        "deaths": 6,
                        "assists": 1,
                        "win": False
                    }
                ]
            }
        }

        record = self.client.parse_squad_match(mock_match, linked, min_squad_size=2)
        self.assertIsNotNone(record)
        self.assertEqual(record["match_id"], "NA1_50000001")
        self.assertEqual(record["result"], "WIN")
        self.assertEqual(record["mode"], "Ranked Flex")
        self.assertEqual(record["mvp"], "João")
        self.assertIn("Bot", record["lineup"])
        self.assertIn("Support", record["lineup"])
        self.assertEqual(record["lineup"]["Bot"]["champion"], "Jinx")
        self.assertEqual(record["lineup"]["Support"]["champion"], "Lulu")

        # Test logging match
        is_new, saved = self.stats_mgr.log_match(record)
        self.assertTrue(is_new)
        self.assertEqual(len(self.stats_mgr.data["match_history"]), 1)

        # Test de-duplication: logging the same match_id again
        is_new_again, duplicate = self.stats_mgr.log_match(record)
        self.assertFalse(is_new_again)
        self.assertEqual(len(self.stats_mgr.data["match_history"]), 1)

        # Test synergy calculation from auto-logged match
        synergies = self.stats_mgr.get_botlane_synergies()
        self.assertEqual(len(synergies), 1)
        self.assertEqual(synergies[0]["adc"], "João")
        self.assertEqual(synergies[0]["support"], "Melanie")
        self.assertEqual(synergies[0]["wins"], 1)
        self.assertEqual(synergies[0]["losses"], 0)
        self.assertEqual(synergies[0]["win_rate"], 100.0)
        self.assertEqual(synergies[0]["tier"], "S Tier")

        # Test player leaderboard
        leaderboard = self.stats_mgr.get_player_leaderboard()
        joao_entry = next((p for p in leaderboard if p["name"] == "João"), None)
        self.assertIsNotNone(joao_entry)
        self.assertEqual(joao_entry["wins"], 1)
        self.assertEqual(joao_entry["mvps"], 1)

if __name__ == "__main__":
    unittest.main()
