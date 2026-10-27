"""
Riot Games Developer API Client for League 5-Stack Coordinator.
Interacts with:
- Account-v1 (Riot ID to PUUID resolution)
- Match-v5 (Match lists and Match detail parsing)
"""

import aiohttp
import asyncio
from typing import Dict, List, Optional, Tuple
import urllib.parse
from datetime import datetime
from rating_engine import evaluate_match_lineup_and_mvp

QUEUE_NAMES = {
    400: "Normal Draft",
    420: "Ranked Solo/Duo",
    430: "Blind Pick",
    440: "Ranked Flex",
    490: "Quickplay",
    700: "Clash",
    720: "ARAM Clash",
    830: "Co-op vs AI",
    840: "Co-op vs AI",
    850: "Co-op vs AI",
    900: "ARAM",
    1700: "Arena",
    1900: "Pick URF",
}

POSITION_MAP = {
    "TOP": "Top",
    "JUNGLE": "Jungle",
    "MIDDLE": "Mid",
    "BOTTOM": "Bot",
    "UTILITY": "Support"
}


class RiotAPIClient:
    def __init__(self, api_key: str, region: str = "americas"):
        self.api_key = api_key.strip() if api_key else ""
        self.region = region.lower().strip() or "americas"
        self.base_url = f"https://{self.region}.api.riotgames.com"
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={"X-Riot-Token": self.api_key}
            )
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    def is_configured(self) -> bool:
        return bool(self.api_key and not self.api_key.startswith("RGAPI-your-riot"))

    async def get_account_by_riot_id(self, game_name: str, tag_line: str) -> Optional[dict]:
        """
        Fetches Riot account details (puuid, gameName, tagLine).
        Endpoint: GET /riot/account/v1/accounts/by-riot-id/{gameName}/{tagLine}
        """
        if not self.is_configured():
            return None

        clean_game_name = urllib.parse.quote(game_name.strip())
        clean_tag_line = urllib.parse.quote(tag_line.strip().lstrip("#"))
        url = f"{self.base_url}/riot/account/v1/accounts/by-riot-id/{clean_game_name}/{clean_tag_line}"

        session = await self._get_session()
        try:
            async with session.get(url) as resp:
                if resp.status == 200:
                    return await resp.json()
                elif resp.status == 404:
                    return None
                elif resp.status == 403:
                    print("[RiotAPI] Error 403: Riot API Key is invalid or expired.")
                    return None
                elif resp.status == 429:
                    retry_after = resp.headers.get("Retry-After", "5")
                    print(f"[RiotAPI] Rate limit hit. Retry after: {retry_after}s")
                    return None
                else:
                    text = await resp.text()
                    print(f"[RiotAPI] get_account_by_riot_id error {resp.status}: {text}")
                    return None
        except Exception as e:
            print(f"[RiotAPI] Exception in get_account_by_riot_id: {e}")
            return None

    async def get_recent_match_ids(self, puuid: str, count: int = 5, start_time: Optional[int] = None) -> List[str]:
        """
        Fetches list of recent match IDs for a player's PUUID.
        Endpoint: GET /lol/match/v5/matches/by-puuid/{puuid}/ids
        """
        if not self.is_configured() or not puuid:
            return []

        url = f"{self.base_url}/lol/match/v5/matches/by-puuid/{puuid}/ids?count={count}"
        if start_time:
            url += f"&startTime={start_time}"

        session = await self._get_session()
        try:
            async with session.get(url) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    return []
        except Exception as e:
            print(f"[RiotAPI] Exception in get_recent_match_ids: {e}")
            return []

    async def get_match_details(self, match_id: str) -> Optional[dict]:
        """
        Fetches detailed match JSON payload for a specific matchId.
        Endpoint: GET /lol/match/v5/matches/{matchId}
        """
        if not self.is_configured() or not match_id:
            return None

        url = f"{self.base_url}/lol/match/v5/matches/{match_id}"
        session = await self._get_session()
        try:
            async with session.get(url) as resp:
                if resp.status == 200:
                    return await resp.json()
                elif resp.status == 429:
                    retry_after = int(resp.headers.get("Retry-After", "5"))
                    await asyncio.sleep(retry_after)
                    return await self.get_match_details(match_id)
                else:
                    return None
        except Exception as e:
            print(f"[RiotAPI] Exception in get_match_details: {e}")
            return None

    def parse_squad_match(
        self,
        match_data: dict,
        linked_puuids: Dict[str, dict],
        min_squad_size: int = 2
    ) -> Optional[dict]:
        """
        Analyzes a match payload to check if members of the squad played together on the same team.
        Returns formatted match record for StatsManager.log_match, or None if not a squad match.

        Parameters:
        - match_data: Complete Match-v5 API payload.
        - linked_puuids: Map of PUUID -> {"name": discord/group_name, ...}
        - min_squad_size: Minimum number of linked players required on the same team (default: 2)
        """
        if not match_data or "info" not in match_data:
            return None

        info = match_data["info"]
        participants = info.get("participants", [])
        if not participants:
            return None

        match_id = match_data.get("metadata", {}).get("matchId", "")
        queue_id = info.get("queueId", 0)
        mode_name = QUEUE_NAMES.get(queue_id, info.get("gameMode", "Custom/Normal"))
        game_duration_sec = info.get("gameDuration", 0)
        duration_min = round(game_duration_sec / 60, 1)

        # Separate participants into Team 100 (Blue) and Team 200 (Red)
        team_100 = [p for p in participants if p.get("teamId") == 100]
        team_200 = [p for p in participants if p.get("teamId") == 200]

        # Find squad members on each team
        squad_team_100 = [p for p in team_100 if p.get("puuid") in linked_puuids]
        squad_team_200 = [p for p in team_200 if p.get("puuid") in linked_puuids]

        # Choose the team that contains the squad
        target_squad = squad_team_100 if len(squad_team_100) >= len(squad_team_200) else squad_team_200
        full_team = team_100 if target_squad is squad_team_100 else team_200

        if len(target_squad) < min_squad_size:
            return None

        # Determine outcome
        win = target_squad[0].get("win", False)
        result_str = "WIN" if win else "LOSS"

        # Map players and determine roles
        lineup = {}
        team_kills = sum(p.get("kills", 0) for p in full_team)

        mvp_candidate = None
        highest_score = -1.0

        for p in full_team:
            puuid = p.get("puuid")
            is_squad_member = puuid in linked_puuids
            player_display_name = (
                linked_puuids[puuid]["name"]
                if is_squad_member
                else f"{p.get('riotIdGameName', 'Player')}#{p.get('riotIdTagline', '')}"
            )

            raw_pos = p.get("teamPosition", "").upper()
            role = POSITION_MAP.get(raw_pos, raw_pos or "Flex")

            kills = p.get("kills", 0)
            deaths = p.get("deaths", 0)
            assists = p.get("assists", 0)
            champ = p.get("championName", "Unknown")
            damage = p.get("totalDamageDealtToChampions", 0)
            challenges = p.get("challenges") or {}

            heal_shield = (
                challenges.get("effectiveHealAndShielding")
                or (p.get("totalHealsOnTeammates", 0) + p.get("totalDamageShieldedOnTeammates", 0))
            )

            lineup[role] = {
                "player": player_display_name,
                "is_squad": is_squad_member,
                "champion": champ,
                "kills": kills,
                "deaths": deaths,
                "assists": assists,
                "damage": damage,
                "cs": p.get("totalMinionsKilled", 0) + p.get("neutralMinionsKilled", 0),
                "vision": p.get("visionScore", 0),
                "gold_earned": p.get("goldEarned", 0),
                "damage_taken": p.get("totalDamageTaken", 0),
                "damage_mitigated": p.get("damageSelfMitigated", 0),
                "objective_damage": p.get("damageDealtToObjectives", 0),
                "turret_damage": p.get("damageDealtToTurrets", 0),
                "turret_takedowns": p.get("turretTakedowns", 0),
                "turret_plates": challenges.get("turretPlatesTaken", 0),
                "cc_score": p.get("timeCCingOthers", 0),
                "effective_heal_shield": round(float(heal_shield or 0), 1),
                "wards_placed": p.get("wardsPlaced", 0),
                "wards_killed": p.get("wardsKilled", challenges.get("wardTakedowns", 0)),
                "control_wards_placed": challenges.get("controlWardsPlaced", p.get("detectorWardsPlaced", 0)),
                "kill_participation": round(float(challenges.get("killParticipation", (kills + assists) / max(1, team_kills))), 3),
                "team_damage_pct": round(float(challenges.get("teamDamagePercentage", 0.0)), 3),
                "damage_taken_pct": round(float(challenges.get("damageTakenOnTeamPercentage", 0.0)), 3),
                "solo_kills": challenges.get("soloKills", 0),
                "outnumbered_kills": challenges.get("outnumberedKills", 0),
                "dragon_takedowns": challenges.get("dragonTakedowns", 0),
                "baron_takedowns": challenges.get("baronTakedowns", 0),
                "rift_herald_takedowns": challenges.get("riftHeraldTakedowns", 0),
                "void_monster_kills": challenges.get("voidMonsterKill", 0),
                "objectives_stolen": p.get("objectivesStolen", challenges.get("epicMonsterSteals", 0)),
                "save_ally_from_death": challenges.get("saveAllyFromDeath", 0),
                "immobilize_and_kill_with_ally": challenges.get("immobilizeAndKillWithAlly", 0),
                "pick_kill_with_ally": challenges.get("pickKillWithAlly", 0),
                "laning_gold_xp_advantage": challenges.get("laningPhaseGoldExpAdvantage", 0),
                "max_cs_advantage": round(float(challenges.get("maxCsAdvantageOnLaneOpponent", 0.0)), 1),
                "max_level_lead": challenges.get("maxLevelLeadLaneOpponent", 0),
            }

        # Timestamp formatting
        game_end_ts = info.get("gameEndTimestamp") or info.get("gameStartTimestamp") or 0
        if game_end_ts:
            match_date = datetime.fromtimestamp(game_end_ts / 1000).strftime("%Y-%m-%d %H:%M")
        else:
            match_date = datetime.now().strftime("%Y-%m-%d %H:%M")

        # Assemble normalized match record
        record = {
            "match_id": match_id,
            "date": match_date,
            "mode": mode_name,
            "queue_id": queue_id,
            "result": result_str,
            "duration_min": duration_min,
            "mvp": target_squad[0].get("riotIdGameName", "Squad"),
            "squad_players": [linked_puuids[p["puuid"]]["name"] for p in target_squad],
            "lineup": lineup
        }

        evaluate_match_lineup_and_mvp(record)
        return record
