"""
Data Manager for League of Legends 5-Stack Discord Bot.
Stores player profiles, active sessions, and match records.
Calculates duo synergy stats (specifically Bot + Support synergy), team chemistry, and player win rates.
"""

import json
import os
from typing import Dict, List, Optional
from datetime import datetime

DEFAULT_DATA_PATH = "data/league_stats.json"

class StatsManager:
    def __init__(self, filepath: str = DEFAULT_DATA_PATH):
        self.filepath = filepath
        self._ensure_dir()
        self.data = self._load()

    def _ensure_dir(self):
        dirname = os.path.dirname(self.filepath)
        if dirname and not os.path.exists(dirname):
            os.makedirs(dirname, exist_ok=True)

    def _load(self) -> dict:
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return self._default_initial_state()

    def _default_initial_state(self) -> dict:
        return {
            "group_name": "The Summoner's Ten",
            "members": [
                {"id": "1", "name": "João", "discord_tag": "Joao#1234", "primary_role": "Bot", "secondary_role": "Mid", "fav_champs": ["Jinx", "Kai'Sa", "Jhin"]},
                {"id": "2", "name": "Melanie", "discord_tag": "Melanie#5678", "primary_role": "Support", "secondary_role": "Top", "fav_champs": ["Nami", "Leona", "Lulu"]},
                {"id": "3", "name": "Marcus", "discord_tag": "Marcus#9012", "primary_role": "Jungle", "secondary_role": "Top", "fav_champs": ["Vi", "Jarvan IV", "Sejuani"]},
                {"id": "4", "name": "Elena", "discord_tag": "Elena#3456", "primary_role": "Mid", "secondary_role": "Support", "fav_champs": ["Ahri", "Orianna", "Syndra"]},
                {"id": "5", "name": "David", "discord_tag": "David#7890", "primary_role": "Top", "secondary_role": "Jungle", "fav_champs": ["Ornn", "Aatrox", "Shen"]},
                {"id": "6", "name": "Sarah", "discord_tag": "Sarah#2345", "primary_role": "Support", "secondary_role": "Mid", "fav_champs": ["Thresh", "Nautilus", "Rakan"]},
                {"id": "7", "name": "Leo", "discord_tag": "Leo#6789", "primary_role": "Bot", "secondary_role": "Top", "fav_champs": ["Ezreal", "Ashe", "Varus"]},
                {"id": "8", "name": "Chloe", "discord_tag": "Chloe#0123", "primary_role": "Mid", "secondary_role": "Bot", "fav_champs": ["Viktor", "Sylas", "Hwei"]},
                {"id": "9", "name": "Alex", "discord_tag": "Alex#4567", "primary_role": "Jungle", "secondary_role": "Support", "fav_champs": ["Xin Zhao", "Amumu", "Zac"]},
                {"id": "10", "name": "Sam", "discord_tag": "Sam#8901", "primary_role": "Top", "secondary_role": "Mid", "fav_champs": ["Gnar", "Jax", "Malphite"]}
            ],
            "active_sessions": {},
            "match_history": []
        }

    def save(self):
        with open(self.filepath, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2)

    # Session Management
    def create_session(self, session_id: str, scheduled_time: str, mode: str, is_ranked_5s: bool, creator: str) -> dict:
        session = {
            "session_id": session_id,
            "created_at": datetime.now().isoformat(),
            "scheduled_time": scheduled_time,
            "mode": mode,
            "is_ranked_5s": is_ranked_5s,
            "creator": creator,
            "status": "POLLING",  # POLLING, READY, IN_PROGRESS, COMPLETED, CANCELLED
            "confirmed_players": [],  # list of {name, role_pref}
            "bench_substitutes": [],
            "declined": []
        }
        self.data["active_sessions"][session_id] = session
        self.save()
        return session

    def register_player(self, session_id: str, player_name: str, status: str = "CONFIRMED", role_pref: str = "Fill") -> tuple:
        """
        Adds player to session. If status == 'CONFIRMED':
        - First 5 players are confirmed starters
        - 6th and onward go to bench_substitutes
        Returns (is_ready, session)
        """
        session = self.data["active_sessions"].get(session_id)
        if not session:
            return False, None

        # Clean existing entries for this player
        session["confirmed_players"] = [p for p in session["confirmed_players"] if p["name"] != player_name]
        session["bench_substitutes"] = [p for p in session["bench_substitutes"] if p["name"] != player_name]
        session["declined"] = [p for p in session["declined"] if p != player_name]

        if status == "CONFIRMED":
            if len(session["confirmed_players"]) < 5:
                session["confirmed_players"].append({"name": player_name, "role_pref": role_pref})
            else:
                session["bench_substitutes"].append({"name": player_name, "role_pref": role_pref})
        elif status == "BENCH":
            session["bench_substitutes"].append({"name": player_name, "role_pref": role_pref})
        elif status == "DECLINED":
            session["declined"].append(player_name)

        # Quorum threshold check (minimum 5 players)
        quorum_met = len(session["confirmed_players"]) >= 5
        if quorum_met and session["status"] == "POLLING":
            session["status"] = "READY"

        self.save()
        return quorum_met, session

    def log_match(self, match_record: dict) -> dict:
        """
        Log a finished match record.
        Expected keys:
        - match_id, date, mode (Ranked 5s / Ranked Flex), result ("WIN" / "LOSS"), duration_min
        - lineup: dict of role -> {player, champion, kills, deaths, assists, cs, vision}
        - mvp: player name
        - notes: string
        """
        self.data["match_history"].insert(0, match_record)
        self.save()
        return match_record

    # Synergy Analytics Engine
    def get_botlane_synergies(self) -> List[dict]:
        """
        Analyzes all matches to compute Bot + Support duo chemistry.
        Returns sorted list of duo pairs with games, win rate, KDA, and chemistry rating.
        """
        duo_stats = {}

        for match in self.data.get("match_history", []):
            lineup = match.get("lineup", {})
            bot = lineup.get("Bot")
            sup = lineup.get("Support")
            if not bot or not sup:
                continue

            bot_name = bot.get("player")
            sup_name = sup.get("player")
            if not bot_name or not sup_name:
                continue

            pair_key = f"{bot_name} (ADC) & {sup_name} (SUP)"
            if pair_key not in duo_stats:
                duo_stats[pair_key] = {
                    "pair": pair_key,
                    "adc": bot_name,
                    "support": sup_name,
                    "games": 0,
                    "wins": 0,
                    "losses": 0,
                    "total_kills": 0,
                    "total_deaths": 0,
                    "total_assists": 0,
                    "champions_played": []
                }

            entry = duo_stats[pair_key]
            entry["games"] += 1
            if match.get("result") == "WIN":
                entry["wins"] += 1
            else:
                entry["losses"] += 1

            k = bot.get("kills", 0) + sup.get("kills", 0)
            d = bot.get("deaths", 0) + sup.get("deaths", 0)
            a = bot.get("assists", 0) + sup.get("assists", 0)
            entry["total_kills"] += k
            entry["total_deaths"] += d
            entry["total_assists"] += a
            entry["champions_played"].append(f"{bot.get('champion')} + {sup.get('champion')}")

        result = []
        for key, s in duo_stats.items():
            win_rate = (s["wins"] / s["games"]) * 100 if s["games"] > 0 else 0
            kda = (s["total_kills"] + s["total_assists"]) / max(1, s["total_deaths"])
            
            # Synergy index (0-100 scale: combines win rate weight + KDA efficiency)
            score = round(min(100.0, (win_rate * 0.6) + (min(kda, 6.0) / 6.0 * 40.0)), 1)
            
            tier = "S Tier" if score >= 80 else ("A Tier" if score >= 65 else "B Tier")
            tag = "Lethal 2v2 Duo" if kda >= 4.0 else ("Objective Anchors" if win_rate >= 60 else "Developing Synergy")

            result.append({
                "pair": key,
                "adc": s["adc"],
                "support": s["support"],
                "games": s["games"],
                "wins": s["wins"],
                "losses": s["losses"],
                "win_rate": round(win_rate, 1),
                "combined_kda": round(kda, 2),
                "synergy_score": score,
                "tier": tier,
                "tag": tag,
                "favorite_combo": max(set(s["champions_played"]), key=s["champions_played"].count) if s["champions_played"] else "N/A"
            })

        return sorted(result, key=lambda x: (x["games"], x["synergy_score"]), reverse=True)

    def get_player_leaderboard(self) -> List[dict]:
        """Calculates win rate and performance stats for each of the 10 group players."""
        stats = {m["name"]: {"name": m["name"], "games": 0, "wins": 0, "kills": 0, "deaths": 0, "assists": 0, "mvps": 0, "roles": {}} for m in self.data["members"]}

        for match in self.data.get("match_history", []):
            is_win = match.get("result") == "WIN"
            mvp = match.get("mvp")
            if mvp and mvp in stats:
                stats[mvp]["mvps"] += 1

            for role, pdata in match.get("lineup", {}).items():
                pname = pdata.get("player")
                if pname in stats:
                    stats[pname]["games"] += 1
                    if is_win:
                        stats[pname]["wins"] += 1
                    stats[pname]["kills"] += pdata.get("kills", 0)
                    stats[pname]["deaths"] += pdata.get("deaths", 0)
                    stats[pname]["assists"] += pdata.get("assists", 0)
                    stats[pname]["roles"][role] = stats[pname]["roles"].get(role, 0) + 1

        leaderboard = []
        for name, p in stats.items():
            wr = round((p["wins"] / p["games"] * 100), 1) if p["games"] > 0 else 0
            kda = round((p["kills"] + p["assists"]) / max(1, p["deaths"]), 2) if p["games"] > 0 else 0.0
            most_played_role = max(p["roles"], key=p["roles"].get) if p["roles"] else "Flex"
            leaderboard.append({
                "name": name,
                "games": p["games"],
                "wins": p["wins"],
                "losses": p["games"] - p["wins"],
                "win_rate": wr,
                "kda": kda,
                "mvps": p["mvps"],
                "main_role": most_played_role
            })

        return sorted(leaderboard, key=lambda x: (x["win_rate"], x["games"]), reverse=True)
