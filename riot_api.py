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


REMAKE_MAX_DURATION_SEC = 300  # 5 minutes


def is_remake_match(match_data: dict) -> bool:
    """
    Detects whether a Riot Match-v5 payload represents a remake:
    - Any participant has `gameEndedInEarlySurrender == True`, OR
    - `gameDuration` is positive and strictly under 5 minutes (300 seconds).
    """
    if not match_data or "info" not in match_data:
        return False
    info = match_data["info"]
    participants = info.get("participants", [])
    if any(bool(p.get("gameEndedInEarlySurrender")) for p in participants):
        return True
    game_duration_sec = info.get("gameDuration")
    if isinstance(game_duration_sec, (int, float)) and 0 < game_duration_sec < REMAKE_MAX_DURATION_SEC:
        return True
    return False


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
                elif resp.status in (401, 403):
                    print(f"[RiotAPI] Error {resp.status} in get_recent_match_ids: Riot API Key is invalid or expired.")
                    return []
                elif resp.status == 429:
                    retry_after = int(resp.headers.get("Retry-After", "5"))
                    print(f"[RiotAPI] Rate limit hit in get_recent_match_ids. Retrying after {retry_after}s...")
                    await asyncio.sleep(retry_after)
                    return await self.get_recent_match_ids(puuid, count=count, start_time=start_time)
                else:
                    text = await resp.text()
                    print(f"[RiotAPI] get_recent_match_ids error {resp.status}: {text[:200]}")
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
                elif resp.status in (401, 403):
                    print(f"[RiotAPI] Error {resp.status} in get_match_details ({match_id}): Riot API Key is invalid or expired.")
                    return None
                elif resp.status == 429:
                    retry_after = int(resp.headers.get("Retry-After", "5"))
                    await asyncio.sleep(retry_after)
                    return await self.get_match_details(match_id)
                else:
                    text = await resp.text()
                    print(f"[RiotAPI] get_match_details ({match_id}) error {resp.status}: {text[:200]}")
                    return None
        except Exception as e:
            print(f"[RiotAPI] Exception in get_match_details: {e}")
            return None

    async def get_match_timeline(self, match_id: str) -> Optional[dict]:
        """
        Fetches Match-v5 timeline JSON payload for a specific matchId.
        Endpoint: GET /lol/match/v5/matches/{matchId}/timeline
        """
        if not self.is_configured() or not match_id:
            return None

        url = f"{self.base_url}/lol/match/v5/matches/{match_id}/timeline"
        session = await self._get_session()
        try:
            async with session.get(url) as resp:
                if resp.status == 200:
                    return await resp.json()
                elif resp.status in (401, 403):
                    print(f"[RiotAPI] Error {resp.status} in get_match_timeline ({match_id}): Riot API Key is invalid or expired.")
                    return None
                elif resp.status == 429:
                    retry_after = int(resp.headers.get("Retry-After", "5"))
                    await asyncio.sleep(retry_after)
                    return await self.get_match_timeline(match_id)
                else:
                    text = await resp.text()
                    print(f"[RiotAPI] get_match_timeline ({match_id}) error {resp.status}: {text[:200]}")
                    return None
        except Exception as e:
            print(f"[RiotAPI] Exception in get_match_timeline: {e}")
            return None

    @staticmethod
    def extract_timeline_player_metrics(timeline_data: Optional[dict], match_data: dict) -> Dict[str, dict]:
        """
        Extracts per-PUUID laning differentials (10m & 15m gold/CS vs lane opponent)
        and death timing distribution (early <14m, mid 14-25m, late >=25m, pre-objective deaths)
        from a Riot Match-v5 timeline payload.
        """
        if not timeline_data or not match_data:
            return {}
        frames = (timeline_data.get("info") or {}).get("frames") or []
        participants = (match_data.get("info") or {}).get("participants") or []
        if not frames or not participants:
            return {}

        # Map participantId (1-10) -> participant metadata
        pid_to_puuid: Dict[int, str] = {}
        pid_to_team_pos: Dict[int, Tuple[int, str]] = {}
        pos_by_team: Dict[Tuple[int, str], int] = {}

        for idx, p in enumerate(participants, start=1):
            pid = int(p.get("participantId") or idx)
            puuid = p.get("puuid")
            if not puuid:
                continue
            team_id = int(p.get("teamId") or (100 if pid <= 5 else 200))
            pos = (p.get("teamPosition") or "").upper()
            pid_to_puuid[pid] = puuid
            pid_to_team_pos[pid] = (team_id, pos)
            if pos:
                pos_by_team[(team_id, pos)] = pid

        def _get_frame_at_minute(minute: int) -> Optional[dict]:
            target_ms = minute * 60_000
            best_frame = None
            best_diff = None
            for fr in frames:
                ts = fr.get("timestamp", 0)
                diff = abs(ts - target_ms)
                if best_diff is None or diff < best_diff:
                    best_diff = diff
                    best_frame = fr
            # Only accept frame if match actually reached close to that minute (within 45s)
            if best_frame is not None and best_diff is not None and best_diff <= 45_000:
                return best_frame
            return None

        frame_10 = _get_frame_at_minute(10)
        frame_15 = _get_frame_at_minute(15)

        def _extract_gold_cs(frame: Optional[dict], pid: int) -> Tuple[Optional[int], Optional[int]]:
            if not frame:
                return None, None
            pf = (frame.get("participantFrames") or {}).get(str(pid))
            if not isinstance(pf, dict):
                return None, None
            gold = pf.get("totalGold")
            cs = int(pf.get("minionsKilled", 0)) + int(pf.get("jungleMinionsKilled", 0))
            return (int(gold) if gold is not None else None), cs

        # Collect death timestamps per participant and elite monster kill timestamps
        death_timestamps: Dict[int, List[int]] = {pid: [] for pid in pid_to_puuid}
        elite_monster_timestamps: List[int] = []

        for fr in frames:
            for ev in fr.get("events") or []:
                ev_type = ev.get("type")
                ts = int(ev.get("timestamp") or 0)
                if ev_type == "CHAMPION_KILL":
                    victim_id = ev.get("victimId")
                    if victim_id in death_timestamps:
                        death_timestamps[victim_id].append(ts)
                elif ev_type == "ELITE_MONSTER_KILL":
                    elite_monster_timestamps.append(ts)

        metrics_by_puuid: Dict[str, dict] = {}
        for pid, puuid in pid_to_puuid.items():
            team_id, pos = pid_to_team_pos[pid]
            opp_team = 200 if team_id == 100 else 100
            opp_pid = pos_by_team.get((opp_team, pos)) if pos else None

            g10, cs10 = _extract_gold_cs(frame_10, pid)
            og10, ocs10 = _extract_gold_cs(frame_10, opp_pid) if opp_pid else (None, None)
            g15, cs15 = _extract_gold_cs(frame_15, pid)
            og15, ocs15 = _extract_gold_cs(frame_15, opp_pid) if opp_pid else (None, None)

            deaths_ts = death_timestamps.get(pid, [])
            early_deaths = sum(1 for ts in deaths_ts if ts < 14 * 60_000)
            mid_deaths = sum(1 for ts in deaths_ts if 14 * 60_000 <= ts < 25 * 60_000)
            late_deaths = sum(1 for ts in deaths_ts if ts >= 25 * 60_000)
            pre_obj_deaths = sum(
                1
                for d_ts in deaths_ts
                if any(0 <= (m_ts - d_ts) <= 60_000 for m_ts in elite_monster_timestamps)
            )

            entry: Dict[str, object] = {
                "early_deaths": early_deaths,
                "mid_deaths": mid_deaths,
                "late_deaths": late_deaths,
                "pre_objective_deaths": pre_obj_deaths,
            }
            if g10 is not None and og10 is not None:
                entry["gold_diff_10"] = g10 - og10
            if cs10 is not None and ocs10 is not None:
                entry["cs_diff_10"] = cs10 - ocs10
            if g15 is not None and og15 is not None:
                entry["gold_diff_15"] = g15 - og15
            if cs15 is not None and ocs15 is not None:
                entry["cs_diff_15"] = cs15 - ocs15

            metrics_by_puuid[puuid] = entry

        return metrics_by_puuid

    def parse_squad_match(
        self,
        match_data: dict,
        linked_puuids: Dict[str, dict],
        min_squad_size: int = 2,
        timeline_data: Optional[dict] = None,
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

        # Determine outcome (remakes are tracked separately from proper wins/losses)
        is_remake = is_remake_match(match_data)
        win = target_squad[0].get("win", False)
        result_str = "REMAKE" if is_remake else ("WIN" if win else "LOSS")

        # Map players and determine roles
        lineup = {}
        team_kills = sum(p.get("kills", 0) for p in full_team)
        timeline_metrics = (
            self.extract_timeline_player_metrics(timeline_data, match_data)
            if timeline_data and not is_remake
            else {}
        )

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

            entry = {
                "player": player_display_name,
                "puuid": puuid,
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
            if puuid and puuid in timeline_metrics:
                entry["timeline"] = timeline_metrics[puuid]
            lineup[role] = entry

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
            "is_remake": is_remake,
            "duration_min": duration_min,
            "mvp": "N/A" if is_remake else target_squad[0].get("riotIdGameName", "Squad"),
            "squad_players": list(dict.fromkeys(linked_puuids[p["puuid"]]["name"] for p in target_squad)),
            "lineup": lineup
        }

        if not is_remake:
            evaluate_match_lineup_and_mvp(record)
        return record
