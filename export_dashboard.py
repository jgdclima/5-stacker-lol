"""
Static Interactive Web Dashboard Generator for 5-Stack Coordinator.

Generates a single self-contained Hextech-themed HTML file (`web/index.html`)
with embedded JSON data from `StatsManager` (`data/league_stats.json`).
Works seamlessly over `file://`, GitHub Pages, Synology Web Station, or Nginx,
and includes an optional built-in preview HTTP server (`--serve`).
"""

import argparse
import functools
import http.server
import json
import os
import socketserver
from datetime import datetime
from typing import Any, Dict, List, Optional

from data_manager import DEFAULT_DATA_PATH, StatsManager
from rating_engine import (
    ARCHETYPE_DPM_BENCHMARK,
    ARCHETYPE_PILLAR_WEIGHTS,
    ROLE_CSPM_BENCHMARK,
    ROLE_PILLAR_WEIGHTS,
    ROLE_VSPM_BENCHMARK,
    get_champion_archetype,
    rating_to_grade,
    score_player_in_match,
)

DEFAULT_OUTPUT_PATH = "web/index.html"
DEFAULT_GITHUB_REPO = "jgdclima/5-stacker-lol"


def _build_demo_dataset() -> Dict[str, Any]:
    """
    Constructs a rich, realistic demonstration dataset for 'The Summoner's Ten'
    so the dashboard can be explored interactively even before live matches are logged
    or whenever the user toggles 'Demo Data Mode' in the UI.
    """
    temp_mgr = StatsManager(filepath=":memory_demo:")
    # Prevent writing to disk for demo state
    temp_mgr.save = lambda: None  # type: ignore

    # Link sample Riot accounts for roster members
    demo_riot_links = {
        "João": [("JoaoADC#NA1", "puuid-joao-1"), ("JinxOnFire#NA1", "puuid-joao-2")],
        "Melanie": [("MelEnchanter#NA1", "puuid-mel-1")],
        "Marcus": [("MarcusJNG#NA1", "puuid-marcus-1")],
        "Elena": [("ElenaMid#NA1", "puuid-elena-1")],
        "David": [("OrnnHub#NA1", "puuid-david-1")],
        "Sarah": [("HookCity#NA1", "puuid-sarah-1")],
        "Leo": [("EzrealMuseum#NA1", "puuid-leo-1")],
        "Chloe": [("HweiArtist#NA1", "puuid-chloe-1")],
        "Alex": [("ZacBounce#NA1", "puuid-alex-1")],
        "Sam": [("MegaGnar#NA1", "puuid-sam-1")],
    }
    for m in temp_mgr.data.get("members", []):
        name = m["name"]
        if name in demo_riot_links:
            m["accounts"] = [
                {"riot_id": rid, "puuid": puuid, "linked_at": "2026-10-01T19:00:00"}
                for rid, puuid in demo_riot_links[name]
            ]
            m["riot_id"] = demo_riot_links[name][0][0]
            m["puuid"] = demo_riot_links[name][0][1]

    # Sample active & historical sessions
    temp_mgr.data["active_sessions"] = {
        "sess-fri-9pm": {
            "session_id": "sess-fri-9pm",
            "created_at": "2026-11-10T17:30:00",
            "scheduled_time": "Friday 9:00 PM PST",
            "scheduled_iso": "2026-11-13T21:00:00-08:00",
            "mode": "Ranked 5s (Weekend Queue)",
            "is_ranked_5s": True,
            "creator": "João",
            "creator_id": "1",
            "status": "READY",
            "confirmed_players": [
                {"name": "João", "role_pref": "Bot"},
                {"name": "Melanie", "role_pref": "Support"},
                {"name": "Marcus", "role_pref": "Jungle"},
                {"name": "Elena", "role_pref": "Mid"},
                {"name": "David", "role_pref": "Top"},
            ],
            "bench_substitutes": [
                {"name": "Sarah", "role_pref": "Support"},
                {"name": "Leo", "role_pref": "Bot"},
            ],
            "declined": ["Sam"],
            "reminder_sent": False,
            "activity_log": [
                "17:32 ✅ João joined as starter (Bot)",
                "17:35 ✅ Melanie joined as starter (Support)",
                "17:41 ✅ Marcus joined as starter (Jungle)",
                "17:48 ✅ Elena joined as starter (Mid)",
                "18:02 🏆 David locked in (Top) — 5/5 Lobby READY!",
                "18:10 🛡️ Sarah joined Bench Substitute #1 (Support)",
            ],
            "session_matches": [
                {"match_id": "NA1_510012", "result": "WIN", "mode": "Ranked Flex", "mvp": "João"},
                {"match_id": "NA1_510011", "result": "WIN", "mode": "Ranked Flex", "mvp": "Elena"},
            ],
        },
        "sess-tue-flex": {
            "session_id": "sess-tue-flex",
            "created_at": "2026-11-10T12:00:00",
            "scheduled_time": "Tonight 8:30 PM PST",
            "scheduled_iso": "2026-11-10T20:30:00-08:00",
            "mode": "Ranked Flex (Fallback)",
            "is_ranked_5s": False,
            "creator": "Elena",
            "creator_id": "4",
            "status": "POLLING",
            "confirmed_players": [
                {"name": "Elena", "role_pref": "Mid"},
                {"name": "Alex", "role_pref": "Jungle"},
                {"name": "Chloe", "role_pref": "Bot"},
            ],
            "bench_substitutes": [],
            "declined": ["David"],
            "reminder_sent": False,
            "activity_log": [
                "12:01 ✅ Elena created session for Tonight 8:30 PM PST",
                "12:15 ✅ Alex joined as starter (Jungle)",
                "12:40 ✅ Chloe joined as starter (Bot) — 3/5 Trio viable!",
            ],
            "session_matches": [],
        },
        "sess-sun-clash": {
            "session_id": "sess-sun-clash",
            "created_at": "2026-11-08T18:00:00",
            "scheduled_time": "Sunday 7:00 PM PST",
            "scheduled_iso": "2026-11-08T19:00:00-08:00",
            "mode": "Ranked 5s (Weekend Queue)",
            "is_ranked_5s": True,
            "creator": "Marcus",
            "creator_id": "3",
            "status": "COMPLETED",
            "confirmed_players": [
                {"name": "David", "role_pref": "Top"},
                {"name": "Marcus", "role_pref": "Jungle"},
                {"name": "Elena", "role_pref": "Mid"},
                {"name": "João", "role_pref": "Bot"},
                {"name": "Melanie", "role_pref": "Support"},
            ],
            "bench_substitutes": [{"name": "Sam", "role_pref": "Top"}],
            "declined": [],
            "reminder_sent": True,
            "activity_log": [
                "18:50 ⏰ 15-minute reminder sent to 5 starters",
                "19:00 🔥 Session transitioned to IN_PROGRESS",
                "22:15 🏁 Session completed with 3W - 1L record",
            ],
            "session_matches": [
                {"match_id": "NA1_510010", "result": "WIN", "mode": "Ranked 5s", "mvp": "Marcus"},
                {"match_id": "NA1_510009", "result": "LOSS", "mode": "Ranked 5s", "mvp": "João"},
                {"match_id": "NA1_510008", "result": "WIN", "mode": "Ranked 5s", "mvp": "Melanie"},
                {"match_id": "NA1_510007", "result": "WIN", "mode": "Ranked 5s", "mvp": "David"},
            ],
        },
    }

    demo_matches = [
        {
            "match_id": "NA1_510012",
            "date": "2026-11-10 21:40",
            "mode": "Ranked 5s",
            "queue_id": 440,
            "result": "WIN",
            "duration_min": 31.5,
            "lineup": {
                "Top": {"player": "David", "is_squad": True, "champion": "Ornn", "kills": 3, "deaths": 1, "assists": 16, "damage": 18400, "cs": 212, "vision": 28, "damage_taken": 34500, "damage_mitigated": 46200, "turret_damage": 4200, "turret_takedowns": 2, "cc_score": 48, "immobilize_and_kill_with_ally": 7},
                "Jungle": {"player": "Marcus", "is_squad": True, "champion": "Vi", "kills": 8, "deaths": 2, "assists": 14, "damage": 22100, "cs": 188, "vision": 36, "damage_taken": 28900, "damage_mitigated": 24100, "objective_damage": 31200, "dragon_takedowns": 3, "baron_takedowns": 1, "rift_herald_takedowns": 1, "void_monster_kills": 5, "cc_score": 32, "pick_kill_with_ally": 6},
                "Mid": {"player": "Elena", "is_squad": True, "champion": "Ahri", "kills": 9, "deaths": 1, "assists": 12, "damage": 28600, "cs": 234, "vision": 31, "damage_taken": 14200, "turret_damage": 5100, "solo_kills": 2, "cc_score": 26, "pick_kill_with_ally": 5},
                "Bot": {"player": "João", "is_squad": True, "champion": "Jinx", "kills": 14, "deaths": 2, "assists": 9, "damage": 38900, "cs": 258, "vision": 26, "damage_taken": 15800, "turret_damage": 9400, "turret_takedowns": 4, "solo_kills": 1},
                "Support": {"player": "Melanie", "is_squad": True, "champion": "Lulu", "kills": 1, "deaths": 1, "assists": 26, "damage": 6800, "cs": 34, "vision": 74, "effective_heal_shield": 11400, "cc_score": 29, "save_ally_from_death": 3, "wards_killed": 11, "control_wards_placed": 6},
            },
        },
        {
            "match_id": "NA1_510011",
            "date": "2026-11-10 20:55",
            "mode": "Ranked 5s",
            "queue_id": 440,
            "result": "WIN",
            "duration_min": 28.0,
            "lineup": {
                "Top": {"player": "David", "is_squad": True, "champion": "Aatrox", "kills": 7, "deaths": 2, "assists": 8, "damage": 24500, "cs": 198, "vision": 22, "damage_taken": 29400, "damage_mitigated": 27800, "turret_damage": 5600, "solo_kills": 2},
                "Jungle": {"player": "Marcus", "is_squad": True, "champion": "Jarvan IV", "kills": 5, "deaths": 2, "assists": 18, "damage": 16800, "cs": 162, "vision": 34, "damage_taken": 26100, "damage_mitigated": 25300, "objective_damage": 26800, "dragon_takedowns": 3, "baron_takedowns": 1, "void_monster_kills": 4, "immobilize_and_kill_with_ally": 8},
                "Mid": {"player": "Elena", "is_squad": True, "champion": "Orianna", "kills": 11, "deaths": 1, "assists": 13, "damage": 31200, "cs": 226, "vision": 29, "effective_heal_shield": 4200, "cc_score": 31, "solo_kills": 2},
                "Bot": {"player": "João", "is_squad": True, "champion": "Kai'Sa", "kills": 10, "deaths": 2, "assists": 8, "damage": 27400, "cs": 218, "vision": 23, "turret_damage": 6200},
                "Support": {"player": "Melanie", "is_squad": True, "champion": "Nami", "kills": 2, "deaths": 2, "assists": 22, "damage": 8100, "cs": 28, "vision": 66, "effective_heal_shield": 9800, "cc_score": 34, "save_ally_from_death": 2},
            },
        },
        {
            "match_id": "NA1_510010",
            "date": "2026-11-08 21:30",
            "mode": "Ranked 5s",
            "queue_id": 440,
            "result": "WIN",
            "duration_min": 34.2,
            "lineup": {
                "Top": {"player": "Sam", "is_squad": True, "champion": "Gnar", "kills": 5, "deaths": 3, "assists": 11, "damage": 21900, "cs": 228, "vision": 26, "damage_taken": 28400, "damage_mitigated": 26100, "turret_damage": 6800, "cc_score": 36},
                "Jungle": {"player": "Marcus", "is_squad": True, "champion": "Sejuani", "kills": 4, "deaths": 1, "assists": 21, "damage": 17200, "cs": 184, "vision": 42, "damage_taken": 38200, "damage_mitigated": 44900, "objective_damage": 29500, "dragon_takedowns": 4, "baron_takedowns": 1, "cc_score": 52, "immobilize_and_kill_with_ally": 10},
                "Mid": {"player": "Chloe", "is_squad": True, "champion": "Viktor", "kills": 9, "deaths": 2, "assists": 10, "damage": 33800, "cs": 254, "vision": 28, "turret_damage": 4800},
                "Bot": {"player": "Leo", "is_squad": True, "champion": "Ezreal", "kills": 11, "deaths": 1, "assists": 9, "damage": 35400, "cs": 248, "vision": 25, "turret_damage": 5900},
                "Support": {"player": "Sarah", "is_squad": True, "champion": "Thresh", "kills": 2, "deaths": 2, "assists": 23, "damage": 7400, "cs": 35, "vision": 78, "cc_score": 49, "pick_kill_with_ally": 8, "save_ally_from_death": 3},
            },
        },
        {
            "match_id": "NA1_510009",
            "date": "2026-11-08 20:40",
            "mode": "Ranked 5s",
            "queue_id": 440,
            "result": "LOSS",
            "duration_min": 36.8,
            "lineup": {
                "Top": {"player": "David", "is_squad": True, "champion": "Ornn", "kills": 2, "deaths": 5, "assists": 10, "damage": 16500, "cs": 219, "vision": 27, "damage_taken": 41200, "damage_mitigated": 48900, "cc_score": 41},
                "Jungle": {"player": "Alex", "is_squad": True, "champion": "Zac", "kills": 3, "deaths": 6, "assists": 12, "damage": 15900, "cs": 176, "vision": 35, "damage_taken": 39400, "damage_mitigated": 36200, "dragon_takedowns": 1, "cc_score": 44},
                "Mid": {"player": "Elena", "is_squad": True, "champion": "Syndra", "kills": 6, "deaths": 4, "assists": 7, "damage": 26800, "cs": 242, "vision": 28, "solo_kills": 1},
                "Bot": {"player": "João", "is_squad": True, "champion": "Jinx", "kills": 9, "deaths": 3, "assists": 6, "damage": 34200, "cs": 278, "vision": 29, "turret_damage": 5400},
                "Support": {"player": "Melanie", "is_squad": True, "champion": "Lulu", "kills": 0, "deaths": 4, "assists": 16, "damage": 5200, "cs": 31, "vision": 68, "effective_heal_shield": 10200, "save_ally_from_death": 2},
            },
        },
        {
            "match_id": "NA1_510008",
            "date": "2026-11-08 19:50",
            "mode": "Ranked Flex",
            "queue_id": 440,
            "result": "WIN",
            "duration_min": 29.4,
            "lineup": {
                "Top": {"player": "David", "is_squad": True, "champion": "Shen", "kills": 4, "deaths": 1, "assists": 19, "damage": 15200, "cs": 182, "vision": 28, "damage_taken": 27500, "damage_mitigated": 33400, "effective_heal_shield": 6400, "save_ally_from_death": 4},
                "Jungle": {"player": "Marcus", "is_squad": True, "champion": "Vi", "kills": 9, "deaths": 2, "assists": 12, "damage": 21800, "cs": 179, "vision": 33, "objective_damage": 28400, "dragon_takedowns": 3, "baron_takedowns": 1, "rift_herald_takedowns": 1},
                "Mid": {"player": "Elena", "is_squad": True, "champion": "Ahri", "kills": 8, "deaths": 1, "assists": 14, "damage": 25900, "cs": 215, "vision": 30, "solo_kills": 2, "pick_kill_with_ally": 6},
                "Bot": {"player": "João", "is_squad": True, "champion": "Jhin", "kills": 12, "deaths": 1, "assists": 11, "damage": 29800, "cs": 224, "vision": 27, "turret_damage": 7800, "turret_takedowns": 3},
                "Support": {"player": "Melanie", "is_squad": True, "champion": "Leona", "kills": 2, "deaths": 2, "assists": 23, "damage": 8900, "cs": 32, "vision": 71, "damage_taken": 24800, "damage_mitigated": 31200, "cc_score": 56, "immobilize_and_kill_with_ally": 11},
            },
        },
        {
            "match_id": "NA1_510007",
            "date": "2026-11-06 22:15",
            "mode": "Ranked Flex",
            "queue_id": 440,
            "result": "WIN",
            "duration_min": 32.0,
            "lineup": {
                "Top": {"player": "Sam", "is_squad": True, "champion": "Jax", "kills": 8, "deaths": 2, "assists": 6, "damage": 26400, "cs": 244, "vision": 24, "damage_taken": 29100, "damage_mitigated": 28400, "turret_damage": 11800, "turret_takedowns": 5, "solo_kills": 3},
                "Jungle": {"player": "Alex", "is_squad": True, "champion": "Amumu", "kills": 4, "deaths": 2, "assists": 19, "damage": 16400, "cs": 172, "vision": 37, "damage_taken": 31200, "damage_mitigated": 35800, "dragon_takedowns": 3, "baron_takedowns": 1, "cc_score": 49},
                "Mid": {"player": "Chloe", "is_squad": True, "champion": "Hwei", "kills": 7, "deaths": 2, "assists": 15, "damage": 31500, "cs": 230, "vision": 31, "cc_score": 33},
                "Bot": {"player": "Leo", "is_squad": True, "champion": "Ashe", "kills": 9, "deaths": 2, "assists": 14, "damage": 28100, "cs": 238, "vision": 32, "cc_score": 38, "pick_kill_with_ally": 5},
                "Support": {"player": "Sarah", "is_squad": True, "champion": "Nautilus", "kills": 1, "deaths": 3, "assists": 21, "damage": 7800, "cs": 30, "vision": 69, "damage_taken": 26400, "damage_mitigated": 29500, "cc_score": 54, "immobilize_and_kill_with_ally": 9},
            },
        },
        {
            "match_id": "NA1_510006",
            "date": "2026-11-05 21:05",
            "mode": "Normal Draft",
            "queue_id": 400,
            "result": "WIN",
            "duration_min": 26.5,
            "lineup": {
                "Top": {"player": "David", "is_squad": True, "champion": "Ornn", "kills": 3, "deaths": 1, "assists": 14, "damage": 15800, "cs": 179, "vision": 23, "damage_taken": 26800, "damage_mitigated": 34100, "cc_score": 39},
                "Jungle": {"player": "Marcus", "is_squad": True, "champion": "Vi", "kills": 10, "deaths": 2, "assists": 11, "damage": 23400, "cs": 168, "vision": 29, "objective_damage": 25900, "dragon_takedowns": 3, "rift_herald_takedowns": 1, "solo_kills": 2},
                "Mid": {"player": "Elena", "is_squad": True, "champion": "Ahri", "kills": 7, "deaths": 1, "assists": 13, "damage": 24100, "cs": 204, "vision": 27, "pick_kill_with_ally": 6},
                "Bot": {"player": "João", "is_squad": True, "champion": "Jinx", "kills": 13, "deaths": 1, "assists": 8, "damage": 33600, "cs": 219, "vision": 24, "turret_damage": 8900, "turret_takedowns": 4},
                "Support": {"player": "Melanie", "is_squad": True, "champion": "Lulu", "kills": 1, "deaths": 1, "assists": 23, "damage": 6100, "cs": 26, "vision": 62, "effective_heal_shield": 9600, "save_ally_from_death": 2},
            },
        },
        {
            "match_id": "NA1_510005",
            "date": "2026-11-04 20:20",
            "mode": "Ranked Flex",
            "queue_id": 440,
            "result": "LOSS",
            "duration_min": 33.5,
            "lineup": {
                "Top": {"player": "Sam", "is_squad": True, "champion": "Malphite", "kills": 2, "deaths": 5, "assists": 9, "damage": 14800, "cs": 195, "vision": 21, "damage_taken": 33400, "damage_mitigated": 39800, "cc_score": 31},
                "Jungle": {"player": "Alex", "is_squad": True, "champion": "Xin Zhao", "kills": 5, "deaths": 6, "assists": 7, "damage": 17900, "cs": 164, "vision": 28, "damage_taken": 31800, "dragon_takedowns": 1},
                "Mid": {"player": "Chloe", "is_squad": True, "champion": "Sylas", "kills": 8, "deaths": 5, "assists": 6, "damage": 26400, "cs": 212, "vision": 24, "solo_kills": 2},
                "Bot": {"player": "Leo", "is_squad": True, "champion": "Varus", "kills": 6, "deaths": 4, "assists": 7, "damage": 25800, "cs": 229, "vision": 25},
                "Support": {"player": "Sarah", "is_squad": True, "champion": "Rakan", "kills": 1, "deaths": 5, "assists": 14, "damage": 5900, "cs": 28, "vision": 64, "effective_heal_shield": 5400, "cc_score": 35},
            },
        },
    ]

    for m in reversed(demo_matches):
        temp_mgr.log_match(m)

    return _compile_payload_from_manager(temp_mgr, is_demo=True)


def _compile_payload_from_manager(stats_mgr: StatsManager, is_demo: bool = False) -> Dict[str, Any]:
    """
    Extracts and pre-aggregates all session, player, synergy, champion trend,
    and rating engine metadata from a `StatsManager` instance.
    """
    raw_data = stats_mgr.data
    members = raw_data.get("members", [])
    matches = raw_data.get("match_history", [])
    sessions_map = raw_data.get("active_sessions", {})

    # Ensure every match lineup has full pillar & rating evaluations
    enriched_matches: List[dict] = []
    for m in matches:
        m_copy = json.loads(json.dumps(m))
        lineup = m_copy.get("lineup", {})
        for role, pdata in lineup.items():
            if isinstance(pdata, dict):
                eval_res = score_player_in_match(role, pdata, m_copy)
                pdata["rating"] = eval_res["rating"]
                pdata["grade"] = eval_res["grade"]
                pdata["archetype"] = eval_res["archetype"]
                pdata["highlight"] = eval_res["highlight"]
                pdata["pillars"] = eval_res["pillars"]
        enriched_matches.append(m_copy)

    # Sessions list sorted by status priority then created_at descending
    status_order = {"IN_PROGRESS": 0, "READY": 1, "POLLING": 2, "COMPLETED": 3, "CANCELLED": 4}
    sessions_list = sorted(
        list(sessions_map.values()),
        key=lambda s: (
            status_order.get(s.get("status", "POLLING"), 5),
            -(int(datetime.fromisoformat(s["created_at"]).timestamp()) if s.get("created_at") else 0),
        ),
    )

    # Player leaderboard & detailed player profiles
    leaderboard = stats_mgr.get_player_leaderboard()
    leaderboard_by_name = {p["name"]: p for p in leaderboard}

    player_profiles: Dict[str, Dict[str, Any]] = {}
    for member in members:
        name = member["name"]
        lb = leaderboard_by_name.get(name, {
            "name": name,
            "games": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": 0.0,
            "kda": 0.0,
            "avg_rating": 0.0,
            "grade": "N/A",
            "mvps": 0,
            "main_role": member.get("primary_role", "Flex"),
        })
        accounts = StatsManager._extract_accounts(member)
        player_profiles[name] = {
            "id": member.get("id", ""),
            "name": name,
            "discord_tag": member.get("discord_tag", ""),
            "primary_role": member.get("primary_role", "Flex"),
            "secondary_role": member.get("secondary_role", "Fill"),
            "fav_champs": member.get("fav_champs", []),
            "accounts": accounts,
            "games": lb["games"],
            "wins": lb["wins"],
            "losses": lb["losses"],
            "win_rate": lb["win_rate"],
            "kda": lb["kda"],
            "avg_rating": lb["avg_rating"],
            "grade": lb["grade"],
            "mvps": lb["mvps"],
            "main_role": lb["main_role"],
            "kills": 0,
            "deaths": 0,
            "assists": 0,
            "pillar_totals": {},
            "pillar_counts": {},
            "roles_played": {},
            "champions": {},
            "recent_matches": [],
        }

    # Aggregate champion trends, role stats, archetype stats, and per-player details
    champ_stats: Dict[str, Dict[str, Any]] = {}
    role_distribution: Dict[str, Dict[str, int]] = {
        r: {"games": 0, "wins": 0} for r in ["Top", "Jungle", "Mid", "Bot", "Support"]
    }
    archetype_stats: Dict[str, Dict[str, Any]] = {}

    for match in enriched_matches:
        is_win = match.get("result") == "WIN"
        dur = float(match.get("duration_min") or 30.0)
        mode = match.get("mode", "Match")
        lineup = match.get("lineup", {})

        for role, pdata in lineup.items():
            if not isinstance(pdata, dict):
                continue
            pname = pdata.get("player", "Unknown")
            champ = pdata.get("champion", "Unknown")
            kills = int(pdata.get("kills", 0))
            deaths = int(pdata.get("deaths", 0))
            assists = int(pdata.get("assists", 0))
            damage = int(pdata.get("damage", 0))
            cs = int(pdata.get("cs", 0))
            vision = int(pdata.get("vision", 0))
            rating = float(pdata.get("rating", 65.0))
            arch = pdata.get("archetype") or get_champion_archetype(champ, role, pdata)
            pillars = pdata.get("pillars") or {}

            if role in role_distribution:
                role_distribution[role]["games"] += 1
                if is_win:
                    role_distribution[role]["wins"] += 1

            # Archetype aggregation
            if arch not in archetype_stats:
                archetype_stats[arch] = {"archetype": arch, "picks": 0, "wins": 0, "total_rating": 0.0}
            archetype_stats[arch]["picks"] += 1
            if is_win:
                archetype_stats[arch]["wins"] += 1
            archetype_stats[arch]["total_rating"] += rating

            # Champion aggregation
            if champ not in champ_stats:
                champ_stats[champ] = {
                    "champion": champ,
                    "archetype": arch,
                    "picks": 0,
                    "wins": 0,
                    "losses": 0,
                    "kills": 0,
                    "deaths": 0,
                    "assists": 0,
                    "damage": 0,
                    "cs": 0,
                    "vision": 0,
                    "duration_min": 0.0,
                    "total_rating": 0.0,
                    "roles": {},
                    "pilots": {},
                    "modes": {},
                }
            cs_entry = champ_stats[champ]
            cs_entry["picks"] += 1
            if is_win:
                cs_entry["wins"] += 1
            else:
                cs_entry["losses"] += 1
            cs_entry["kills"] += kills
            cs_entry["deaths"] += deaths
            cs_entry["assists"] += assists
            cs_entry["damage"] += damage
            cs_entry["cs"] += cs
            cs_entry["vision"] += vision
            cs_entry["duration_min"] += dur
            cs_entry["total_rating"] += rating
            cs_entry["roles"][role] = cs_entry["roles"].get(role, 0) + 1
            cs_entry["pilots"][pname] = cs_entry["pilots"].get(pname, 0) + 1
            cs_entry["modes"][mode] = cs_entry["modes"].get(mode, 0) + 1

            # Per-player aggregation
            if pname in player_profiles:
                prof = player_profiles[pname]
                prof["kills"] += kills
                prof["deaths"] += deaths
                prof["assists"] += assists
                prof["roles_played"][role] = prof["roles_played"].get(role, 0) + 1
                for pil_k, pil_v in pillars.items():
                    prof["pillar_totals"][pil_k] = prof["pillar_totals"].get(pil_k, 0.0) + float(pil_v)
                    prof["pillar_counts"][pil_k] = prof["pillar_counts"].get(pil_k, 0) + 1

                if champ not in prof["champions"]:
                    prof["champions"][champ] = {
                        "champion": champ,
                        "archetype": arch,
                        "games": 0,
                        "wins": 0,
                        "kills": 0,
                        "deaths": 0,
                        "assists": 0,
                        "total_rating": 0.0,
                        "roles": {},
                    }
                pc = prof["champions"][champ]
                pc["games"] += 1
                if is_win:
                    pc["wins"] += 1
                pc["kills"] += kills
                pc["deaths"] += deaths
                pc["assists"] += assists
                pc["total_rating"] += rating
                pc["roles"][role] = pc["roles"].get(role, 0) + 1

                prof["recent_matches"].append({
                    "match_id": match.get("match_id"),
                    "date": match.get("date"),
                    "mode": mode,
                    "result": match.get("result"),
                    "role": role,
                    "champion": champ,
                    "kills": kills,
                    "deaths": deaths,
                    "assists": assists,
                    "rating": rating,
                    "grade": pdata.get("grade", rating_to_grade(rating)),
                    "highlight": pdata.get("highlight", ""),
                    "is_mvp": match.get("mvp") == pname,
                })

    # Finalize player profiles
    final_players: List[Dict[str, Any]] = []
    for name, prof in player_profiles.items():
        pillars_avg = {}
        for pk in ["combat", "damage", "objective", "frontline", "utility", "macro_vision"]:
            cnt = prof["pillar_counts"].get(pk, 0)
            pillars_avg[pk] = round(prof["pillar_totals"].get(pk, 0.0) / cnt, 1) if cnt > 0 else 0.0
        prof["pillars_avg"] = pillars_avg
        prof.pop("pillar_totals", None)
        prof.pop("pillar_counts", None)

        champ_list = []
        for cname, cdata in prof["champions"].items():
            g = cdata["games"]
            champ_list.append({
                "champion": cname,
                "archetype": cdata["archetype"],
                "games": g,
                "wins": cdata["wins"],
                "losses": g - cdata["wins"],
                "win_rate": round((cdata["wins"] / g) * 100, 1) if g > 0 else 0.0,
                "kda": round((cdata["kills"] + cdata["assists"]) / max(1, cdata["deaths"]), 2),
                "avg_kills": round(cdata["kills"] / g, 1),
                "avg_deaths": round(cdata["deaths"] / g, 1),
                "avg_assists": round(cdata["assists"] / g, 1),
                "avg_rating": round(cdata["total_rating"] / g, 1),
                "primary_role": max(cdata["roles"], key=cdata["roles"].get) if cdata["roles"] else "Flex",
            })
        prof["champion_pool"] = sorted(champ_list, key=lambda x: (x["games"], x["avg_rating"]), reverse=True)
        prof.pop("champions", None)
        final_players.append(prof)

    final_players.sort(key=lambda x: (x["avg_rating"], x["win_rate"], x["games"]), reverse=True)

    # Finalize champion summary list
    champions_list: List[Dict[str, Any]] = []
    for cname, c in champ_stats.items():
        g = c["picks"]
        dur_total = max(1.0, c["duration_min"])
        avg_r = round(c["total_rating"] / g, 1) if g > 0 else 0.0
        champions_list.append({
            "champion": cname,
            "archetype": c["archetype"],
            "picks": g,
            "wins": c["wins"],
            "losses": c["losses"],
            "win_rate": round((c["wins"] / g) * 100, 1) if g > 0 else 0.0,
            "kda": round((c["kills"] + c["assists"]) / max(1, c["deaths"]), 2),
            "avg_kills": round(c["kills"] / g, 1),
            "avg_deaths": round(c["deaths"] / g, 1),
            "avg_assists": round(c["assists"] / g, 1),
            "dpm": round(c["damage"] / dur_total, 0),
            "cspm": round(c["cs"] / dur_total, 1),
            "vspm": round(c["vision"] / dur_total, 2),
            "avg_rating": avg_r,
            "grade": rating_to_grade(avg_r),
            "primary_role": max(c["roles"], key=c["roles"].get) if c["roles"] else "Flex",
            "roles": c["roles"],
            "top_pilot": max(c["pilots"], key=c["pilots"].get) if c["pilots"] else "N/A",
            "pilots": c["pilots"],
        })
    champions_list.sort(key=lambda x: (x["picks"], x["win_rate"], x["avg_rating"]), reverse=True)

    # Archetype summary list
    archetypes_list = []
    for ak, av in archetype_stats.items():
        p = av["picks"]
        archetypes_list.append({
            "archetype": ak,
            "picks": p,
            "wins": av["wins"],
            "win_rate": round((av["wins"] / p) * 100, 1) if p > 0 else 0.0,
            "avg_rating": round(av["total_rating"] / p, 1) if p > 0 else 0.0,
        })
    archetypes_list.sort(key=lambda x: x["picks"], reverse=True)

    # Synergies across all 4 duo pairs
    synergies = {
        "botlane": stats_mgr.get_botlane_synergies(min_games=1),
        "mid_jungle": stats_mgr.get_mid_jungle_synergies(min_games=1),
        "top_jungle": stats_mgr.get_top_jungle_synergies(min_games=1),
        "support_jungle": stats_mgr.get_support_jungle_synergies(min_games=1),
    }

    # Overall Squad KPIs
    total_matches = len(enriched_matches)
    total_wins = sum(1 for m in enriched_matches if m.get("result") == "WIN")
    total_losses = total_matches - total_wins
    overall_wr = round((total_wins / total_matches) * 100, 1) if total_matches > 0 else 0.0

    # Calculate current streak
    streak_count = 0
    streak_type = "NONE"
    for m in enriched_matches:
        res = m.get("result", "WIN")
        if streak_type == "NONE":
            streak_type = res
            streak_count = 1
        elif res == streak_type:
            streak_count += 1
        else:
            break

    return {
        "is_demo": is_demo,
        "group_name": raw_data.get("group_name", "The Summoner's Ten"),
        "kpis": {
            "total_matches": total_matches,
            "wins": total_wins,
            "losses": total_losses,
            "win_rate": overall_wr,
            "streak_type": streak_type,
            "streak_count": streak_count,
            "active_sessions_count": len(stats_mgr.get_active_sessions()),
            "total_sessions_count": len(sessions_list),
        },
        "sessions": sessions_list,
        "matches": enriched_matches,
        "players": final_players,
        "synergies": synergies,
        "champions": champions_list,
        "archetypes": archetypes_list,
        "role_distribution": role_distribution,
    }


def build_dashboard_payload(stats_mgr: Optional[StatsManager] = None, filepath: str = DEFAULT_DATA_PATH) -> Dict[str, Any]:
    """
    Builds the complete JSON payload embedded into `web/index.html`, containing both:
    - `live`: Live data from `data/league_stats.json`
    - `demo`: Rich demonstration data for interactive previewing when live data is empty or toggled
    - `meta`: Rating engine benchmarks, weights, and GitHub feedback configuration
    """
    mgr = stats_mgr or StatsManager(filepath=filepath)
    live_payload = _compile_payload_from_manager(mgr, is_demo=False)
    demo_payload = _build_demo_dataset()

    github_repo = (os.getenv("GITHUB_REPO") or DEFAULT_GITHUB_REPO).strip()

    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "github_repo": github_repo,
        "has_live_matches": len(live_payload["matches"]) > 0 or len(live_payload["sessions"]) > 0,
        "live": live_payload,
        "demo": demo_payload,
        "rating_formulas": {
            "role_weights": ROLE_PILLAR_WEIGHTS,
            "archetype_weights": ARCHETYPE_PILLAR_WEIGHTS,
            "dpm_benchmarks": ARCHETYPE_DPM_BENCHMARK,
            "cspm_benchmarks": ROLE_CSPM_BENCHMARK,
            "vspm_benchmarks": ROLE_VSPM_BENCHMARK,
        },
    }


DASHBOARD_HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>5-Stack Coordinator — Hextech Command Center</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
  <style>
    :root {
      --bg-deep: #060d18;
      --bg-primary: #091428;
      --bg-card: rgba(15, 25, 35, 0.86);
      --bg-card-hover: rgba(22, 36, 52, 0.95);
      --bg-elevated: #111f30;
      --gold-bright: #f0e6d2;
      --gold-primary: #c8aa6e;
      --gold-muted: #785a28;
      --gold-glow: rgba(200, 170, 110, 0.25);
      --cyan-bright: #0ac8b9;
      --cyan-deep: #005a82;
      --cyan-glow: rgba(10, 200, 185, 0.22);
      --win-green: #2ecc71;
      --loss-red: #e74c3c;
      --purple-accent: #9b59b6;
      --text-main: #e8e4dc;
      --text-muted: #94a3b8;
      --text-dim: #64748b;
      --border-gold: rgba(200, 170, 110, 0.32);
      --border-subtle: rgba(148, 163, 184, 0.16);
      --radius-md: 10px;
      --radius-lg: 14px;
      --shadow-card: 0 10px 30px -5px rgba(0, 0, 0, 0.6);
    }

    * {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }

    body {
      background-color: var(--bg-deep);
      background-image:
        radial-gradient(circle at 12% 10%, rgba(10, 200, 185, 0.09) 0%, transparent 40%),
        radial-gradient(circle at 88% 15%, rgba(200, 170, 110, 0.10) 0%, transparent 45%),
        linear-gradient(180deg, #091428 0%, #060d18 100%);
      color: var(--text-main);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
      min-height: 100vh;
      line-height: 1.5;
    }

    a {
      color: var(--cyan-bright);
      text-decoration: none;
    }
    a:hover {
      text-decoration: underline;
    }

    /* Top Header */
    .top-header {
      position: sticky;
      top: 0;
      z-index: 100;
      background: rgba(9, 20, 40, 0.92);
      backdrop-filter: blur(14px);
      border-bottom: 1px solid var(--border-gold);
      padding: 0.85rem 1.5rem;
    }

    .header-inner {
      max-width: 1440px;
      margin: 0 auto;
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 1rem;
    }

    .brand {
      display: flex;
      align-items: center;
      gap: 0.85rem;
    }

    .brand-crest {
      width: 42px;
      height: 42px;
      border-radius: 10px;
      background: linear-gradient(135deg, #c8aa6e 0%, #785a28 100%);
      display: flex;
      align-items: center;
      justify-content: center;
      font-weight: 800;
      font-size: 1.2rem;
      color: #091428;
      box-shadow: 0 0 15px var(--gold-glow);
      border: 1px solid var(--gold-bright);
    }

    .brand-title {
      font-size: 1.2rem;
      font-weight: 800;
      letter-spacing: 0.04em;
      color: var(--gold-bright);
      text-transform: uppercase;
    }

    .brand-subtitle {
      font-size: 0.78rem;
      color: var(--text-muted);
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }

    /* Nav Tabs */
    .nav-tabs {
      display: flex;
      flex-wrap: wrap;
      gap: 0.35rem;
      background: rgba(6, 13, 24, 0.65);
      padding: 0.3rem;
      border-radius: var(--radius-md);
      border: 1px solid var(--border-subtle);
    }

    .nav-tab {
      background: transparent;
      border: 1px solid transparent;
      color: var(--text-muted);
      padding: 0.5rem 0.95rem;
      border-radius: 7px;
      font-size: 0.86rem;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.18s ease;
      display: flex;
      align-items: center;
      gap: 0.45rem;
    }

    .nav-tab:hover {
      color: var(--gold-bright);
      background: rgba(200, 170, 110, 0.08);
    }

    .nav-tab.active {
      background: linear-gradient(135deg, rgba(200, 170, 110, 0.22), rgba(10, 200, 185, 0.12));
      color: var(--gold-bright);
      border-color: var(--gold-primary);
      box-shadow: 0 0 12px rgba(200, 170, 110, 0.18);
    }

    /* Header Right Controls */
    .header-controls {
      display: flex;
      align-items: center;
      gap: 0.75rem;
      flex-wrap: wrap;
    }

    .data-mode-switch {
      display: inline-flex;
      align-items: center;
      background: rgba(15, 25, 35, 0.9);
      border: 1px solid var(--border-gold);
      border-radius: 8px;
      padding: 0.2rem;
      gap: 0.2rem;
    }

    .mode-btn {
      border: none;
      background: transparent;
      color: var(--text-muted);
      font-size: 0.76rem;
      font-weight: 700;
      padding: 0.32rem 0.68rem;
      border-radius: 6px;
      cursor: pointer;
      transition: all 0.15s;
    }

    .mode-btn.active {
      background: var(--gold-primary);
      color: #091428;
    }

    .gh-feedback-top-btn {
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
      background: linear-gradient(135deg, rgba(10, 200, 185, 0.18), rgba(0, 90, 130, 0.35));
      border: 1px solid var(--cyan-bright);
      color: var(--gold-bright);
      padding: 0.42rem 0.85rem;
      border-radius: 8px;
      font-size: 0.8rem;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.18s;
    }

    .gh-feedback-top-btn:hover {
      background: rgba(10, 200, 185, 0.28);
      box-shadow: 0 0 12px var(--cyan-glow);
      text-decoration: none;
    }

    /* Main Container */
    .main-container {
      max-width: 1440px;
      margin: 0 auto;
      padding: 1.5rem;
    }

    /* Demo Notice Banner */
    .demo-banner {
      background: linear-gradient(90deg, rgba(200, 170, 110, 0.16), rgba(10, 200, 185, 0.12));
      border: 1px solid var(--gold-primary);
      border-radius: var(--radius-md);
      padding: 0.75rem 1.1rem;
      margin-bottom: 1.25rem;
      display: flex;
      align-items: center;
      justify-content: space-between;
      flex-wrap: wrap;
      gap: 0.75rem;
      font-size: 0.86rem;
    }

    /* Global Filter Bar */
    .filter-bar {
      background: var(--bg-card);
      border: 1px solid var(--border-subtle);
      border-radius: var(--radius-lg);
      padding: 0.9rem 1.2rem;
      margin-bottom: 1.4rem;
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 1rem;
      box-shadow: var(--shadow-card);
    }

    .filter-group {
      display: flex;
      align-items: center;
      gap: 0.55rem;
      flex-wrap: wrap;
    }

    .filter-label {
      font-size: 0.75rem;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      color: var(--gold-primary);
      font-weight: 700;
    }

    .role-pills {
      display: inline-flex;
      background: rgba(6, 13, 24, 0.75);
      border: 1px solid var(--border-subtle);
      border-radius: 8px;
      padding: 0.18rem;
      gap: 0.18rem;
      flex-wrap: wrap;
    }

    .role-pill {
      border: none;
      background: transparent;
      color: var(--text-muted);
      padding: 0.32rem 0.65rem;
      border-radius: 6px;
      font-size: 0.78rem;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.15s;
    }

    .role-pill:hover {
      color: var(--gold-bright);
    }

    .role-pill.active {
      background: rgba(10, 200, 185, 0.22);
      color: var(--cyan-bright);
      border: 1px solid rgba(10, 200, 185, 0.45);
    }

    .hex-select, .hex-input {
      background: rgba(6, 13, 24, 0.85);
      border: 1px solid var(--border-subtle);
      color: var(--text-main);
      padding: 0.42rem 0.75rem;
      border-radius: 7px;
      font-size: 0.82rem;
      outline: none;
      transition: border-color 0.15s;
    }

    .hex-select:focus, .hex-input:focus {
      border-color: var(--gold-primary);
    }

    .range-wrap {
      display: flex;
      align-items: center;
      gap: 0.45rem;
      font-size: 0.82rem;
    }

    input[type="range"] {
      accent-color: var(--gold-primary);
      cursor: pointer;
    }

    .reset-btn {
      background: rgba(231, 76, 60, 0.12);
      border: 1px solid rgba(231, 76, 60, 0.35);
      color: #f87171;
      padding: 0.38rem 0.72rem;
      border-radius: 7px;
      font-size: 0.78rem;
      font-weight: 600;
      cursor: pointer;
    }
    .reset-btn:hover {
      background: rgba(231, 76, 60, 0.22);
    }

    /* Tab Panels */
    .tab-panel {
      display: none;
      animation: fadeIn 0.22s ease;
    }

    .tab-panel.active {
      display: block;
    }

    @keyframes fadeIn {
      from { opacity: 0; transform: translateY(4px); }
      to { opacity: 1; transform: translateY(0); }
    }

    /* KPI Grid */
    .kpi-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 1rem;
      margin-bottom: 1.5rem;
    }

    .kpi-card {
      background: var(--bg-card);
      border: 1px solid var(--border-subtle);
      border-top: 2px solid var(--gold-primary);
      border-radius: var(--radius-md);
      padding: 1.05rem 1.2rem;
      box-shadow: var(--shadow-card);
      position: relative;
      overflow: hidden;
    }

    .kpi-card.cyan-top {
      border-top-color: var(--cyan-bright);
    }

    .kpi-label {
      font-size: 0.74rem;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      color: var(--text-muted);
      margin-bottom: 0.35rem;
      font-weight: 600;
    }

    .kpi-value {
      font-size: 1.65rem;
      font-weight: 800;
      color: var(--gold-bright);
      line-height: 1.2;
    }

    .kpi-sub {
      font-size: 0.78rem;
      color: var(--text-muted);
      margin-top: 0.3rem;
    }

    /* Hero Session Card */
    .hero-session {
      background: linear-gradient(135deg, rgba(15, 25, 35, 0.95) 0%, rgba(9, 28, 48, 0.92) 100%);
      border: 1px solid var(--border-gold);
      border-radius: var(--radius-lg);
      padding: 1.35rem 1.5rem;
      margin-bottom: 1.5rem;
      box-shadow: var(--shadow-card);
      display: grid;
      grid-template-columns: 1.4fr 1fr;
      gap: 1.25rem;
    }

    @media (max-width: 900px) {
      .hero-session {
        grid-template-columns: 1fr;
      }
    }

    /* Section Headers */
    .section-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      flex-wrap: wrap;
      gap: 0.75rem;
      margin: 1.5rem 0 0.95rem 0;
    }

    .section-title {
      font-size: 1.12rem;
      font-weight: 700;
      color: var(--gold-bright);
      letter-spacing: 0.03em;
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }

    /* Cards & Grids */
    .grid-2 {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(420px, 1fr));
      gap: 1.25rem;
    }

    .grid-3 {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(310px, 1fr));
      gap: 1.15rem;
    }

    @media (max-width: 600px) {
      .grid-2, .grid-3 {
        grid-template-columns: 1fr;
      }
    }

    .hex-card {
      background: var(--bg-card);
      border: 1px solid var(--border-subtle);
      border-radius: var(--radius-lg);
      padding: 1.2rem;
      box-shadow: var(--shadow-card);
      transition: transform 0.16s ease, border-color 0.16s ease;
    }

    .hex-card.interactive:hover {
      transform: translateY(-2px);
      border-color: var(--gold-primary);
      cursor: pointer;
    }

    /* Badges */
    .badge {
      display: inline-flex;
      align-items: center;
      gap: 0.28rem;
      padding: 0.18rem 0.58rem;
      border-radius: 999px;
      font-size: 0.72rem;
      font-weight: 700;
      letter-spacing: 0.03em;
      text-transform: uppercase;
    }

    .badge-win, .badge-ready {
      background: rgba(46, 204, 113, 0.16);
      color: #4ade80;
      border: 1px solid rgba(46, 204, 113, 0.4);
    }

    .badge-loss, .badge-cancelled {
      background: rgba(231, 76, 60, 0.16);
      color: #f87171;
      border: 1px solid rgba(231, 76, 60, 0.4);
    }

    .badge-polling {
      background: rgba(200, 170, 110, 0.18);
      color: var(--gold-bright);
      border: 1px solid var(--gold-primary);
    }

    .badge-progress {
      background: rgba(10, 200, 185, 0.18);
      color: var(--cyan-bright);
      border: 1px solid var(--cyan-bright);
    }

    .badge-completed {
      background: rgba(148, 163, 184, 0.16);
      color: var(--text-muted);
      border: 1px solid rgba(148, 163, 184, 0.3);
    }

    .grade-badge {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 32px;
      height: 24px;
      padding: 0 6px;
      border-radius: 6px;
      font-weight: 800;
      font-size: 0.76rem;
    }

    .grade-Splus, .grade-S {
      background: linear-gradient(135deg, #c8aa6e, #f0e6d2);
      color: #091428;
      box-shadow: 0 0 8px rgba(200, 170, 110, 0.4);
    }

    .grade-Aplus, .grade-A {
      background: rgba(10, 200, 185, 0.22);
      color: var(--cyan-bright);
      border: 1px solid rgba(10, 200, 185, 0.5);
    }

    .grade-B {
      background: rgba(59, 130, 246, 0.2);
      color: #60a5fa;
      border: 1px solid rgba(59, 130, 246, 0.4);
    }

    .grade-C, .grade-F, .grade-NA {
      background: rgba(148, 163, 184, 0.14);
      color: var(--text-muted);
      border: 1px solid rgba(148, 163, 184, 0.25);
    }

    .archetype-tag {
      display: inline-block;
      padding: 0.14rem 0.5rem;
      border-radius: 5px;
      font-size: 0.7rem;
      font-weight: 600;
      text-transform: capitalize;
      background: rgba(200, 170, 110, 0.12);
      color: var(--gold-primary);
      border: 1px solid rgba(200, 170, 110, 0.25);
    }

    .highlight-chip {
      display: inline-block;
      padding: 0.14rem 0.5rem;
      border-radius: 5px;
      font-size: 0.7rem;
      font-weight: 600;
      background: rgba(10, 200, 185, 0.11);
      color: var(--cyan-bright);
      border: 1px solid rgba(10, 200, 185, 0.28);
    }

    /* Tables */
    .table-wrap {
      width: 100%;
      overflow-x: auto;
      background: var(--bg-card);
      border: 1px solid var(--border-subtle);
      border-radius: var(--radius-lg);
      box-shadow: var(--shadow-card);
    }

    table.hex-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 0.85rem;
      text-align: left;
    }

    .hex-table th {
      background: rgba(6, 13, 24, 0.85);
      color: var(--gold-primary);
      font-size: 0.74rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      padding: 0.8rem 0.95rem;
      border-bottom: 1px solid var(--border-gold);
      cursor: pointer;
      user-select: none;
      white-space: nowrap;
    }

    .hex-table th:hover {
      color: var(--gold-bright);
      background: rgba(200, 170, 110, 0.1);
    }

    .hex-table td {
      padding: 0.75rem 0.95rem;
      border-bottom: 1px solid var(--border-subtle);
      vertical-align: middle;
    }

    .hex-table tbody tr:hover {
      background: rgba(200, 170, 110, 0.06);
    }

    /* Progress Bars */
    .progress-bar {
      width: 100%;
      height: 7px;
      background: rgba(255, 255, 255, 0.08);
      border-radius: 999px;
      overflow: hidden;
    }

    .progress-fill {
      height: 100%;
      border-radius: 999px;
      background: linear-gradient(90deg, var(--cyan-bright), var(--gold-primary));
    }

    /* Match Accordion Card */
    .match-card {
      background: var(--bg-card);
      border: 1px solid var(--border-subtle);
      border-left: 4px solid var(--win-green);
      border-radius: var(--radius-md);
      margin-bottom: 0.85rem;
      overflow: hidden;
      transition: border-color 0.15s;
    }

    .match-card.loss {
      border-left-color: var(--loss-red);
    }

    .match-header {
      padding: 0.9rem 1.15rem;
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 0.8rem;
      cursor: pointer;
    }

    .match-header:hover {
      background: rgba(255, 255, 255, 0.03);
    }

    .match-body {
      display: none;
      padding: 0 1.15rem 1.1rem 1.15rem;
      border-top: 1px solid var(--border-subtle);
    }

    .match-card.expanded .match-body {
      display: block;
    }

    /* Roster chips */
    .player-chip {
      display: inline-flex;
      align-items: center;
      gap: 0.35rem;
      padding: 0.25rem 0.65rem;
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid var(--border-subtle);
      border-radius: 7px;
      font-size: 0.79rem;
    }

    .role-badge {
      font-size: 0.68rem;
      font-weight: 700;
      padding: 0.1rem 0.38rem;
      border-radius: 4px;
      background: rgba(10, 200, 185, 0.15);
      color: var(--cyan-bright);
      text-transform: uppercase;
    }

    /* Chart containers */
    .chart-box {
      position: relative;
      height: 300px;
      width: 100%;
    }

    /* Modal */
    .modal-backdrop {
      position: fixed;
      inset: 0;
      background: rgba(3, 8, 16, 0.82);
      backdrop-filter: blur(6px);
      z-index: 250;
      display: none;
      align-items: center;
      justify-content: center;
      padding: 1.25rem;
    }

    .modal-backdrop.open {
      display: flex;
    }

    .modal-content {
      background: #0b1626;
      border: 1px solid var(--gold-primary);
      border-radius: var(--radius-lg);
      max-width: 920px;
      width: 100%;
      max-height: 90vh;
      overflow-y: auto;
      padding: 1.5rem;
      box-shadow: 0 20px 60px rgba(0, 0, 0, 0.85);
      position: relative;
    }

    .modal-close {
      position: absolute;
      top: 1rem;
      right: 1rem;
      background: rgba(255, 255, 255, 0.08);
      border: 1px solid var(--border-subtle);
      color: var(--text-main);
      width: 34px;
      height: 34px;
      border-radius: 8px;
      font-size: 1.1rem;
      cursor: pointer;
    }

    /* Pillar Bar list */
    .pillar-row {
      display: grid;
      grid-template-columns: 145px 1fr 48px;
      align-items: center;
      gap: 0.65rem;
      margin-bottom: 0.5rem;
      font-size: 0.8rem;
    }

    /* FAQ & Math Layout */
    .faq-section {
      background: var(--bg-card);
      border: 1px solid var(--border-subtle);
      border-radius: var(--radius-lg);
      padding: 1.4rem;
      margin-bottom: 1.35rem;
      box-shadow: var(--shadow-card);
    }

    .faq-section h3 {
      color: var(--gold-bright);
      font-size: 1.08rem;
      margin-bottom: 0.65rem;
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }

    .formula-box {
      background: rgba(6, 13, 24, 0.9);
      border: 1px solid var(--border-gold);
      border-radius: 8px;
      padding: 0.85rem 1.1rem;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-size: 0.83rem;
      color: var(--gold-bright);
      margin: 0.75rem 0;
      overflow-x: auto;
    }

    .feedback-form-grid {
      display: grid;
      grid-template-columns: 1.15fr 0.85fr;
      gap: 1.25rem;
    }

    @media (max-width: 850px) {
      .feedback-form-grid {
        grid-template-columns: 1fr;
      }
    }

    .form-field {
      margin-bottom: 0.9rem;
    }

    .form-field label {
      display: block;
      font-size: 0.78rem;
      font-weight: 700;
      color: var(--gold-primary);
      text-transform: uppercase;
      margin-bottom: 0.35rem;
    }

    .form-field input, .form-field select, .form-field textarea {
      width: 100%;
      background: rgba(6, 13, 24, 0.9);
      border: 1px solid var(--border-subtle);
      color: var(--text-main);
      padding: 0.58rem 0.8rem;
      border-radius: 8px;
      font-size: 0.86rem;
      font-family: inherit;
    }

    .form-field textarea {
      min-height: 110px;
      resize: vertical;
    }

    .btn-gold {
      background: linear-gradient(135deg, #c8aa6e 0%, #9b7838 100%);
      color: #091428;
      border: 1px solid var(--gold-bright);
      padding: 0.65rem 1.25rem;
      border-radius: 8px;
      font-weight: 800;
      font-size: 0.88rem;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 0.5rem;
      transition: all 0.18s;
    }

    .btn-gold:hover {
      filter: brightness(1.1);
      box-shadow: 0 0 16px var(--gold-glow);
      text-decoration: none;
    }

    .empty-state {
      text-align: center;
      padding: 2.5rem 1rem;
      color: var(--text-muted);
      font-size: 0.92rem;
    }

    footer {
      text-align: center;
      padding: 2rem 1rem;
      color: var(--text-dim);
      font-size: 0.78rem;
      border-top: 1px solid var(--border-subtle);
      margin-top: 2.5rem;
    }
  </style>
</head>
<body>

  <!-- Top Navigation Header -->
  <header class="top-header">
    <div class="header-inner">
      <div class="brand">
        <div class="brand-crest">5S</div>
        <div>
          <div class="brand-title" id="header-group-name">The Summoner's Ten</div>
          <div class="brand-subtitle">
            <span>5-Stack Coordinator Command Center</span>
            <span>•</span>
            <span id="header-updated-at">Updated</span>
          </div>
        </div>
      </div>

      <nav class="nav-tabs" role="tablist">
        <button class="nav-tab active" data-tab="overview">⚡ Overview</button>
        <button class="nav-tab" data-tab="sessions">📅 Sessions</button>
        <button class="nav-tab" data-tab="players">🛡️ Players</button>
        <button class="nav-tab" data-tab="synergies">🤝 Synergies</button>
        <button class="nav-tab" data-tab="trends">📈 Meta &amp; Trends</button>
        <button class="nav-tab" data-tab="faq">📖 FAQ &amp; Feedback</button>
      </nav>

      <div class="header-controls">
        <div class="data-mode-switch" title="Switch between live bot data and rich demonstration data">
          <button class="mode-btn" id="btn-mode-live" onclick="setDatasetMode('live')">Live Data</button>
          <button class="mode-btn" id="btn-mode-demo" onclick="setDatasetMode('demo')">Demo Preview</button>
        </div>
        <button class="gh-feedback-top-btn" onclick="switchTab('faq', 'feedback-anchor')">
          💡 Submit Feedback
        </button>
      </div>
    </div>
  </header>

  <main class="main-container">
    <!-- Notice banner when viewing Demo Preview -->
    <div id="demo-notice-banner" class="demo-banner" style="display: none;">
      <div>
        <strong style="color: var(--gold-bright);">✨ Interactive Demo Preview Active:</strong>
        <span id="demo-banner-text" style="color: var(--text-main);">
          Exploring sample 5-stack sessions, Riot Match-v5 telemetry, duo synergies, and champion trends.
        </span>
      </div>
      <button class="mode-btn active" onclick="setDatasetMode('live')" id="banner-switch-live-btn">
        Switch to Live Data
      </button>
    </div>

    <!-- Global Interactive Filter Bar (shown on data tabs) -->
    <section class="filter-bar" id="global-filter-bar">
      <div class="filter-group">
        <span class="filter-label">Role</span>
        <div class="role-pills" id="role-filter-pills">
          <button class="role-pill active" data-role="ALL">All</button>
          <button class="role-pill" data-role="Top">Top</button>
          <button class="role-pill" data-role="Jungle">Jungle</button>
          <button class="role-pill" data-role="Mid">Mid</button>
          <button class="role-pill" data-role="Bot">Bot</button>
          <button class="role-pill" data-role="Support">Support</button>
        </div>
      </div>

      <div class="filter-group">
        <span class="filter-label">Player</span>
        <select id="filter-player" class="hex-select">
          <option value="ALL">All Squad Members</option>
        </select>

        <span class="filter-label">Queue</span>
        <select id="filter-mode" class="hex-select">
          <option value="ALL">All Queues</option>
          <option value="Ranked 5s">Ranked 5s</option>
          <option value="Ranked Flex">Ranked Flex</option>
          <option value="Normal">Normal / Other</option>
        </select>

        <div class="range-wrap">
          <span class="filter-label">Min Games: <strong id="min-games-val" style="color: var(--cyan-bright);">1</strong></span>
          <input type="range" id="filter-min-games" min="1" max="5" value="1" />
        </div>
      </div>

      <div class="filter-group">
        <input type="text" id="filter-search" class="hex-input" placeholder="Search player, champ, session..." />
        <button class="reset-btn" onclick="resetFilters()">Reset</button>
      </div>
    </section>

    <!-- TAB 1: OVERVIEW -->
    <section id="tab-overview" class="tab-panel active">
      <div id="overview-hero-session"></div>
      <div class="kpi-grid" id="overview-kpi-grid"></div>

      <div class="grid-2" style="margin-bottom: 1.5rem;">
        <div class="hex-card">
          <div class="section-title" style="margin-bottom: 0.85rem;">🏆 Top Squad Performers</div>
          <div id="overview-top-players"></div>
        </div>
        <div class="hex-card">
          <div class="section-title" style="margin-bottom: 0.85rem;">🤝 Highest Synergy Duos</div>
          <div id="overview-top-synergies"></div>
        </div>
      </div>

      <div class="section-header">
        <div class="section-title">⚔️ Recent Match History (Click any match to inspect full 5-role telemetry)</div>
      </div>
      <div id="overview-matches-list"></div>
    </section>

    <!-- TAB 2: SESSIONS -->
    <section id="tab-sessions" class="tab-panel">
      <div class="section-header" style="margin-top: 0;">
        <div class="section-title">📅 Active &amp; Historical Sessions</div>
        <div class="filter-group">
          <span class="filter-label">Status</span>
          <select id="session-status-filter" class="hex-select" onchange="renderSessionsTab()">
            <option value="ALL">All Statuses</option>
            <option value="ACTIVE">Active (Polling / Ready / In Progress)</option>
            <option value="COMPLETED">Completed</option>
            <option value="CANCELLED">Cancelled</option>
          </select>
        </div>
      </div>
      <div id="sessions-grid" class="grid-2"></div>
    </section>

    <!-- TAB 3: PLAYERS -->
    <section id="tab-players" class="tab-panel">
      <div class="section-header" style="margin-top: 0;">
        <div class="section-title">🛡️ @LOLers Roster Cards (Click a player for 6-Pillar &amp; Champion Pool Breakdown)</div>
      </div>
      <div id="players-cards-grid" class="grid-3" style="margin-bottom: 1.75rem;"></div>

      <div class="section-header">
        <div class="section-title">📊 Squad Leaderboard Table (Click headers to sort)</div>
      </div>
      <div class="table-wrap">
        <table class="hex-table" id="players-leaderboard-table">
          <thead>
            <tr>
              <th onclick="sortPlayersBy('rank')">#</th>
              <th onclick="sortPlayersBy('name')">Player</th>
              <th onclick="sortPlayersBy('main_role')">Primary / Main Role</th>
              <th onclick="sortPlayersBy('games')">Games</th>
              <th onclick="sortPlayersBy('win_rate')">Win Rate</th>
              <th onclick="sortPlayersBy('kda')">KDA</th>
              <th onclick="sortPlayersBy('avg_rating')">Holistic Rating</th>
              <th onclick="sortPlayersBy('mvps')">MVPs</th>
              <th>Favorite Champions</th>
            </tr>
          </thead>
          <tbody id="players-table-body"></tbody>
        </table>
      </div>
    </section>

    <!-- TAB 4: SYNERGIES -->
    <section id="tab-synergies" class="tab-panel">
      <div class="section-header" style="margin-top: 0;">
        <div class="section-title">🤝 Living Duo Synergy Leaderboards</div>
        <div class="role-pills" id="synergy-pair-pills">
          <button class="role-pill active" data-pair="ALL" onclick="setSynergyCategory('ALL')">All Pairs</button>
          <button class="role-pill" data-pair="botlane" onclick="setSynergyCategory('botlane')">🏹🛡️ Bot + Support</button>
          <button class="role-pill" data-pair="mid_jungle" onclick="setSynergyCategory('mid_jungle')">🔮🌲 Mid + Jungle</button>
          <button class="role-pill" data-pair="top_jungle" onclick="setSynergyCategory('top_jungle')">⚔️🌲 Top + Jungle</button>
          <button class="role-pill" data-pair="support_jungle" onclick="setSynergyCategory('support_jungle')">🛡️🌲 Support + Jungle</button>
        </div>
      </div>

      <div id="synergies-cards-grid" class="grid-3" style="margin-bottom: 1.6rem;"></div>

      <div class="table-wrap">
        <table class="hex-table">
          <thead>
            <tr>
              <th>Category</th>
              <th>Duo Partners</th>
              <th>Tier &amp; Tag</th>
              <th onclick="sortSynergiesBy('synergy_score')">Synergy Score ▾</th>
              <th onclick="sortSynergiesBy('win_rate')">Win Rate</th>
              <th onclick="sortSynergiesBy('combined_kda')">Duo KDA</th>
              <th onclick="sortSynergiesBy('avg_duo_rating')">Avg Duo Rating</th>
              <th onclick="sortSynergiesBy('coordination_score')">Coordination</th>
              <th onclick="sortSynergiesBy('games')">Games</th>
              <th>Signature Combo</th>
            </tr>
          </thead>
          <tbody id="synergies-table-body"></tbody>
        </table>
      </div>
    </section>

    <!-- TAB 5: META & GAMEPLAY TRENDS -->
    <section id="tab-trends" class="tab-panel">
      <div class="grid-2" style="margin-bottom: 1.4rem;">
        <div class="hex-card">
          <div class="section-title" style="margin-bottom: 0.75rem;">🔥 Most Picked Champions (Wins vs Losses)</div>
          <div class="chart-box">
            <canvas id="chart-most-picked"></canvas>
          </div>
        </div>
        <div class="hex-card">
          <div class="section-title" style="margin-bottom: 0.75rem;">🏆 Highest Holistic Rating by Champion</div>
          <div class="chart-box">
            <canvas id="chart-champ-ratings"></canvas>
          </div>
        </div>
      </div>

      <div class="grid-2" style="margin-bottom: 1.5rem;">
        <div class="hex-card">
          <div class="section-title" style="margin-bottom: 0.75rem;">🧬 Champion Kit Archetype Meta Share</div>
          <div class="chart-box">
            <canvas id="chart-archetypes"></canvas>
          </div>
        </div>
        <div class="hex-card">
          <div class="section-title" style="margin-bottom: 0.75rem;">📈 Cumulative Win Rate &amp; Match Tempo Trend</div>
          <div class="chart-box">
            <canvas id="chart-tempo-trend"></canvas>
          </div>
        </div>
      </div>

      <div class="section-header">
        <div class="section-title">🐉 Champion Pool &amp; Meta Analytics Table (Click headers to sort)</div>
      </div>
      <div class="table-wrap">
        <table class="hex-table">
          <thead>
            <tr>
              <th onclick="sortChampsBy('champion')">Champion</th>
              <th onclick="sortChampsBy('archetype')">Kit Archetype</th>
              <th onclick="sortChampsBy('primary_role')">Primary Role</th>
              <th onclick="sortChampsBy('picks')">Picks ▾</th>
              <th onclick="sortChampsBy('win_rate')">Win Rate</th>
              <th onclick="sortChampsBy('kda')">KDA</th>
              <th onclick="sortChampsBy('dpm')">Avg DPM</th>
              <th onclick="sortChampsBy('cspm')">Avg CS/m</th>
              <th onclick="sortChampsBy('avg_rating')">Holistic Rating</th>
              <th>Top Squad Pilot</th>
            </tr>
          </thead>
          <tbody id="champions-table-body"></tbody>
        </table>
      </div>
    </section>

    <!-- TAB 6: FAQ, RATING MATH & GITHUB FEEDBACK -->
    <section id="tab-faq" class="tab-panel">
      <!-- 1. How the Bot Gets Its Data -->
      <div class="faq-section">
        <h3>📡 1. How the Bot Gets Its Data &amp; Syncs Matches</h3>
        <p style="color: var(--text-muted); font-size: 0.9rem; margin-bottom: 0.9rem;">
          The 5-Stack Coordinator combines real-time Discord session state with official <strong>Riot Games Developer API</strong> telemetry stored in <code>data/league_stats.json</code>:
        </p>
        <div class="grid-3">
          <div class="hex-card" style="background: rgba(6, 13, 24, 0.65);">
            <div style="color: var(--gold-bright); font-weight: 700; margin-bottom: 0.35rem;">🔗 1. Riot Account Linking</div>
            <p style="font-size: 0.82rem; color: var(--text-muted);">
              Players link one or more Riot IDs (<code>GameName#TAG</code>) via <code>/link-riot</code>. The bot queries Riot's <strong>Account-v1 API</strong> (<code>/riot/account/v1/accounts/by-riot-id/</code>) to resolve immutable <code>PUUID</code> identifiers and reconciles past match history automatically.
            </p>
          </div>
          <div class="hex-card" style="background: rgba(6, 13, 24, 0.65);">
            <div style="color: var(--gold-bright); font-weight: 700; margin-bottom: 0.35rem;">🔄 2. Automated &amp; Manual Match Sync</div>
            <p style="font-size: 0.82rem; color: var(--text-muted);">
              Every <strong>10 minutes</strong> (`auto_match_sync_loop`) or when <code>/sync-matches</code> is triggered, the bot fetches recent match IDs via <strong>Match-v5</strong> (<code>/lol/match/v5/matches/by-puuid/</code>) and inspects full post-game telemetry and Riot Challenges data.
            </p>
          </div>
          <div class="hex-card" style="background: rgba(6, 13, 24, 0.65);">
            <div style="color: var(--gold-bright); font-weight: 700; margin-bottom: 0.35rem;">🛡️ 3. Squad Verification &amp; Living Threads</div>
            <p style="font-size: 0.82rem; color: var(--text-muted);">
              Whenever <strong>2 or more linked @LOLers members</strong> play on the same team (Blue <code>100</code> or Red <code>200</code>), the match is de-duplicated by <code>match_id</code>, scored by the Holistic Rating Engine, attached to the active session's W-L tally, and synced to the 4 Living Synergy Threads and this dashboard.
            </p>
          </div>
        </div>
      </div>

      <!-- 2. Performance Rating Calculations -->
      <div class="faq-section">
        <h3>🧮 2. Holistic Individual Performance Rating Engine (0–100 Scale)</h3>
        <p style="color: var(--text-muted); font-size: 0.9rem;">
          Unlike raw KDA formulas that unfairly penalize frontline tanks or sacrificial engage supports, <code>rating_engine.py</code> evaluates every player on a <strong>0–100 scale</strong> by blending <strong>55% Role Responsibility Weights</strong> with <strong>45% Champion Kit Archetype Weights</strong> across <strong>6 Performance Pillars</strong>:
        </p>

        <div class="formula-box">
          Blended Pillar Weight = (0.55 × Role_Weight[pillar]) + (0.45 × Archetype_Weight[pillar])<br/>
          Base Score = Σ (Pillar_Score × Blended_Weight) / Σ (Active_Blended_Weights)<br/>
          Final Rating = clamp(Base_Score − Excess_Death_Penalty + Outcome_Adjustment, 15.0, 99.5)
        </div>

        <div class="grid-3" style="margin-top: 1rem; margin-bottom: 1.2rem;">
          <div class="hex-card" style="background: rgba(6, 13, 24, 0.65);">
            <div style="color: var(--cyan-bright); font-weight: 700; font-size: 0.88rem;">⚔️ Pillar 1: Combat &amp; KDA Efficiency</div>
            <p style="font-size: 0.8rem; color: var(--text-muted); margin-top: 0.3rem;">
              44% KDA ratio (target <code>3.2</code>) + 34% Kill Participation (target <code>58%</code> Jng/Sup/Mid, <code>48%</code> Top/Bot) + 22% Death-rate survival + up to <code>+14</code> playmaking bonus (Solo Kills &amp; Outnumbered Kills) + <code>+8</code> carry kill-conversion bonus.
            </p>
          </div>
          <div class="hex-card" style="background: rgba(6, 13, 24, 0.65);">
            <div style="color: var(--cyan-bright); font-weight: 700; font-size: 0.88rem;">🔥 Pillar 2: Damage &amp; Carry Output</div>
            <p style="font-size: 0.8rem; color: var(--text-muted); margin-top: 0.3rem;">
              60% Damage Per Minute (benchmarked against kit archetype: <code>780</code> Marksman, <code>760</code> Mage, <code>680</code> Assassin, <code>650</code> Splitpusher, <code>620</code> Bruiser, <code>440</code> Tank, <code>300</code> Catcher, <code>240</code> Enchanter) + 40% Team Damage Share (target <code>24%</code> carries).
            </p>
          </div>
          <div class="hex-card" style="background: rgba(6, 13, 24, 0.65);">
            <div style="color: var(--cyan-bright); font-weight: 700; font-size: 0.88rem;">🐉 Pillar 3: Objective &amp; Structural Pressure</div>
            <p style="font-size: 0.8rem; color: var(--text-muted); margin-top: 0.3rem;">
              Combines Structural Pressure (Turret Damage + Takedowns <code>×1500</code> + Plates <code>×600</code>) and Monster Control (Objective Dmg + Dragons <code>×3500</code> + Barons <code>×5000</code> + Heralds <code>×3000</code> + Void Grubs <code>×1200</code> + Steals <code>×6000</code>). Weighted 72/28 monster-heavy for Jungle and 72/28 structure-heavy for Top/Splitpushers.
            </p>
          </div>
          <div class="hex-card" style="background: rgba(6, 13, 24, 0.65);">
            <div style="color: var(--cyan-bright); font-weight: 700; font-size: 0.88rem;">🛡️ Pillar 4: Frontline &amp; Durability</div>
            <p style="font-size: 0.8rem; color: var(--text-muted); margin-top: 0.3rem;">
              45% Self-Mitigated Damage/min (target <code>900/m</code> for Tanks/Bruisers/Catchers) + 25% Team Damage Taken Share (target <code>24%</code> Top/Jng) + 30% Tank Survival Efficiency (<code>(Damage Taken + Mitigated) / Deaths</code>, target <code>9,500</code>).
            </p>
          </div>
          <div class="hex-card" style="background: rgba(6, 13, 24, 0.65);">
            <div style="color: var(--cyan-bright); font-weight: 700; font-size: 0.88rem;">✨ Pillar 5: Utility, CC &amp; Enablement</div>
            <p style="font-size: 0.8rem; color: var(--text-muted); margin-top: 0.3rem;">
              Evaluates CC Score/min (target <code>1.1/m</code> Catchers/Tanks), Effective Healing &amp; Shielding/min (target <code>320/m</code> Enchanters), Immobilize &amp; Pick Kills with Allies, and clutch <code>saveAllyFromDeath</code> rescues.
            </p>
          </div>
          <div class="hex-card" style="background: rgba(6, 13, 24, 0.65);">
            <div style="color: var(--cyan-bright); font-weight: 700; font-size: 0.88rem;">👁️ Pillar 6: Vision, Economy &amp; Lane Lead</div>
            <p style="font-size: 0.8rem; color: var(--text-muted); margin-top: 0.3rem;">
              Role-benchmarked CS/min (<code>7.2</code> Bot, <code>7.0</code> Mid, <code>6.8</code> Top, <code>5.8</code> Jng, <code>1.2</code> Sup) and Vision Score/min (<code>2.10</code> Sup, <code>1.05</code> Jng), plus bonuses for Laning Gold/XP advantage, <code>+25</code> CS leads, and Control Wards.
            </p>
          </div>
        </div>

        <!-- Interactive Role + Archetype Weight Calculator -->
        <div class="hex-card" style="background: rgba(6, 13, 24, 0.78); border-color: var(--border-gold);">
          <div style="display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 1rem; margin-bottom: 0.9rem;">
            <div style="font-weight: 700; color: var(--gold-bright);">
              🔬 Interactive Blended Weight Simulator (55% Role + 45% Archetype)
            </div>
            <div class="filter-group">
              <span class="filter-label">Select Role:</span>
              <select id="sim-role" class="hex-select" onchange="updateWeightSimulator()">
                <option value="Top">Top</option>
                <option value="Jungle">Jungle</option>
                <option value="Mid">Mid</option>
                <option value="Bot" selected>Bot (ADC)</option>
                <option value="Support">Support</option>
              </select>
              <span class="filter-label">Select Kit Archetype:</span>
              <select id="sim-arch" class="hex-select" onchange="updateWeightSimulator()">
                <option value="marksman" selected>Marksman</option>
                <option value="mage">Mage</option>
                <option value="assassin">Assassin</option>
                <option value="splitpusher">Splitpusher</option>
                <option value="bruiser">Bruiser</option>
                <option value="tank">Tank</option>
                <option value="enchanter">Enchanter</option>
                <option value="catcher">Catcher / Engage</option>
              </select>
            </div>
          </div>
          <div id="sim-weights-output"></div>
          <div style="font-size: 0.78rem; color: var(--text-muted); margin-top: 0.7rem;">
            <strong>Adjustments &amp; Grades:</strong> Excess deaths above <code>2.0 deaths / 10 min</code> incur up to a <code>-14.0</code> penalty (<code>6.5×</code> rate for carries, <code>4.5×</code> for frontline/utility). Match outcome adds <code>+2.5</code> for a WIN or <code>-1.5</code> for a LOSS.
            Letter Grades: <span class="grade-badge grade-Splus">S+ ≥ 88</span> <span class="grade-badge grade-S">S ≥ 80</span> <span class="grade-badge grade-Aplus">A+ ≥ 73</span> <span class="grade-badge grade-A">A ≥ 65</span> <span class="grade-badge grade-B">B ≥ 55</span> <span class="grade-badge grade-C">C ≥ 45</span> <span class="grade-badge grade-F">F &lt; 45</span>
          </div>
        </div>
      </div>

      <!-- 3. Pairwise Synergy Formula -->
      <div class="faq-section">
        <h3>🤝 3. Holistic Pairwise Duo Synergy Formula</h3>
        <p style="color: var(--text-muted); font-size: 0.9rem;">
          The 4 Living Synergy Leaderboards (<strong>Bot + Support</strong>, <strong>Mid + Jungle</strong>, <strong>Top + Jungle</strong>, and <strong>Support + Jungle</strong>) evaluate duo chemistry on a 0–100 scale with Bayesian sample-size dampening so 1-game flukes don't outrank proven partnerships:
        </p>
        <div class="formula-box">
          Synergy Score = (0.42 × Bayesian_Win_Rate) + (0.24 × Dampened_Duo_Rating) + (0.14 × Pair_Coordination) + (0.20 × Duo_KDA_Norm)<br/>
          • Bayesian_Win_Rate = (Raw_WR × min(1.0, Games / 5)) + (50.0 × (1 − min(1.0, Games / 5)))<br/>
          • Tiers: S Tier (≥ 80.0) | A Tier (≥ 65.0) | B Tier (&lt; 65.0)
        </div>
      </div>

      <!-- 4. Feedback -> GitHub Issue Creator -->
      <div class="faq-section" id="feedback-anchor" style="border-color: var(--cyan-bright);">
        <h3>💡 4. Submit Feedback &amp; Automatically Open a GitHub Issue</h3>
        <p style="color: var(--text-muted); font-size: 0.9rem; margin-bottom: 1.1rem;">
          Have a feature request, bug report, or UX suggestion for the Discord bot or this web dashboard? Fill out the form below to open a pre-formatted GitHub Issue directly on <a id="faq-repo-link" href="https://github.com/jgdclima/5-stacker-lol/issues" target="_blank" rel="noopener"><code>jgdclima/5-stacker-lol</code></a>, or use the <code>/feedback</code> slash command / <strong>💡 Feedback</strong> button on any session card in Discord (which creates the GitHub Issue automatically via <code>github_tickets.py</code>!).
        </p>

        <div class="feedback-form-grid">
          <div>
            <div class="form-field">
              <label for="fb-category">Feedback Category</label>
              <select id="fb-category" onchange="updateFeedbackPreview()">
                <option value="feature">✨ Feature Request (label: enhancement)</option>
                <option value="bug">🐛 Bug Report (label: bug)</option>
                <option value="ux">🎨 UX / Channel / Dashboard Feedback (label: enhancement)</option>
              </select>
            </div>
            <div class="form-field">
              <label for="fb-title">Issue Title</label>
              <input type="text" id="fb-title" placeholder="e.g., Add champion matchup winrate matrix to Trends tab" oninput="updateFeedbackPreview()" />
            </div>
            <div class="form-field">
              <label for="fb-reporter">Your Name / Discord Tag (Optional)</label>
              <input type="text" id="fb-reporter" placeholder="e.g., Joao#1234" oninput="updateFeedbackPreview()" />
            </div>
            <div class="form-field">
              <label for="fb-desc">Detailed Description</label>
              <textarea id="fb-desc" placeholder="Describe what you'd like to see, steps to reproduce a bug, or how the dashboard/bot can be improved..." oninput="updateFeedbackPreview()"></textarea>
            </div>
            <div style="display: flex; flex-wrap: wrap; gap: 0.75rem; align-items: center;">
              <a id="fb-submit-link" class="btn-gold" href="https://github.com/jgdclima/5-stacker-lol/issues/new" target="_blank" rel="noopener">
                🚀 Create GitHub Issue
              </a>
              <a id="fb-view-issues-link" class="gh-feedback-top-btn" href="https://github.com/jgdclima/5-stacker-lol/issues" target="_blank" rel="noopener">
                📋 View Existing Issues
              </a>
            </div>
          </div>

          <div>
            <div style="font-size: 0.78rem; font-weight: 700; color: var(--gold-primary); text-transform: uppercase; margin-bottom: 0.35rem;">
              Live GitHub Issue Payload Preview
            </div>
            <div class="formula-box" id="fb-markdown-preview" style="margin-top: 0; min-height: 255px; white-space: pre-wrap; color: var(--text-main);"></div>
          </div>
        </div>
      </div>
    </section>
  </main>

  <!-- Player Detail Modal -->
  <div class="modal-backdrop" id="player-modal" onclick="if(event.target === this) closePlayerModal()">
    <div class="modal-content">
      <button class="modal-close" onclick="closePlayerModal()" title="Close">✕</button>
      <div id="player-modal-body"></div>
    </div>
  </div>

  <footer>
    5-Stack Coordinator • Hextech Static Analytics Dashboard • Self-Contained Zero-CORS Bundle
  </footer>

  <!-- Embedded Dashboard Data Payload -->
  <script id="dashboard-data" type="application/json">__DASHBOARD_JSON_PAYLOAD__</script>

  <script>
    // Parse Embedded Payload
    const RAW_BUNDLE = JSON.parse(document.getElementById('dashboard-data').textContent);

    // State
    let datasetMode = RAW_BUNDLE.has_live_matches ? 'live' : 'demo';
    let currentTab = 'overview';
    let filters = {
      role: 'ALL',
      player: 'ALL',
      mode: 'ALL',
      minGames: 1,
      search: ''
    };
    let playerSort = { key: 'avg_rating', asc: false };
    let synergyCategory = 'ALL';
    let synergySort = { key: 'synergy_score', asc: false };
    let champSort = { key: 'picks', asc: false };
    let chartInstances = {};

    function getActiveData() {
      return datasetMode === 'live' ? RAW_BUNDLE.live : RAW_BUNDLE.demo;
    }

    function gradeClass(grade) {
      if (!grade || grade === 'N/A') return 'grade-NA';
      return 'grade-' + grade.replace('+', 'plus');
    }

    function statusBadgeClass(status) {
      const s = (status || '').toUpperCase();
      if (s === 'READY') return 'badge-ready';
      if (s === 'IN_PROGRESS') return 'badge-progress';
      if (s === 'POLLING') return 'badge-polling';
      if (s === 'CANCELLED') return 'badge-cancelled';
      return 'badge-completed';
    }

    function escapeHtml(str) {
      return String(str ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
    }

    // Initialize Dashboard
    function initDashboard() {
      document.getElementById('header-updated-at').textContent = 'Synced ' + RAW_BUNDLE.generated_at;

      // Setup Tab Switching
      document.querySelectorAll('.nav-tab').forEach(btn => {
        btn.addEventListener('click', () => switchTab(btn.dataset.tab));
      });

      // Setup Role Filter Pills
      document.querySelectorAll('#role-filter-pills .role-pill').forEach(pill => {
        pill.addEventListener('click', () => {
          document.querySelectorAll('#role-filter-pills .role-pill').forEach(p => p.classList.remove('active'));
          pill.classList.add('active');
          filters.role = pill.dataset.role;
          renderAll();
        });
      });

      // Setup Dropdown & Search Listeners
      document.getElementById('filter-player').addEventListener('change', e => {
        filters.player = e.target.value;
        renderAll();
      });
      document.getElementById('filter-mode').addEventListener('change', e => {
        filters.mode = e.target.value;
        renderAll();
      });
      document.getElementById('filter-min-games').addEventListener('input', e => {
        filters.minGames = parseInt(e.target.value, 10) || 1;
        document.getElementById('min-games-val').textContent = filters.minGames;
        renderAll();
      });
      document.getElementById('filter-search').addEventListener('input', e => {
        filters.search = e.target.value.trim().toLowerCase();
        renderAll();
      });

      setDatasetMode(datasetMode);
      updateWeightSimulator();
      updateFeedbackPreview();
    }

    function setDatasetMode(mode) {
      datasetMode = mode;
      document.getElementById('btn-mode-live').classList.toggle('active', mode === 'live');
      document.getElementById('btn-mode-demo').classList.toggle('active', mode === 'demo');

      const banner = document.getElementById('demo-notice-banner');
      const bannerBtn = document.getElementById('banner-switch-live-btn');
      const bannerText = document.getElementById('demo-banner-text');

      if (mode === 'demo') {
        banner.style.display = 'flex';
        bannerText.textContent = RAW_BUNDLE.has_live_matches
          ? 'Viewing sample demonstration data. Click "Switch to Live Data" to view your actual server records.'
          : 'No live matches have been logged in data/league_stats.json yet — showing interactive Demo Preview so you can explore all charts and leaderboards.';
        bannerBtn.textContent = 'View Live Server Data';
        bannerBtn.onclick = () => setDatasetMode('live');
      } else if (!RAW_BUNDLE.has_live_matches) {
        banner.style.display = 'flex';
        bannerText.textContent = 'Live data currently has 0 logged matches. Log a match via /sync-matches or /log-match, or switch to Demo Preview to test the charts.';
        bannerBtn.textContent = 'Enable Demo Preview';
        bannerBtn.onclick = () => setDatasetMode('demo');
      } else {
        banner.style.display = 'none';
      }

      const data = getActiveData();
      document.getElementById('header-group-name').textContent = data.group_name || "The Summoner's Ten";

      // Populate Player Filter Dropdown
      const playerSelect = document.getElementById('filter-player');
      const prevVal = playerSelect.value;
      playerSelect.innerHTML = '<option value="ALL">All Squad Members</option>';
      (data.players || []).forEach(p => {
        const opt = document.createElement('option');
        opt.value = p.name;
        opt.textContent = `${p.name} (${p.primary_role})`;
        playerSelect.appendChild(opt);
      });
      if ([...playerSelect.options].some(o => o.value === prevVal)) {
        playerSelect.value = prevVal;
      } else {
        playerSelect.value = 'ALL';
        filters.player = 'ALL';
      }

      renderAll();
    }

    function switchTab(tabId, scrollAnchor) {
      currentTab = tabId;
      document.querySelectorAll('.nav-tab').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.tab === tabId);
      });
      document.querySelectorAll('.tab-panel').forEach(panel => {
        panel.classList.toggle('active', panel.id === 'tab-' + tabId);
      });

      // Hide global filter bar on FAQ tab
      document.getElementById('global-filter-bar').style.display = (tabId === 'faq') ? 'none' : 'flex';

      if (tabId === 'trends') {
        setTimeout(() => renderTrendsCharts(), 30);
      }
      if (scrollAnchor) {
        const el = document.getElementById(scrollAnchor);
        if (el) el.scrollIntoView({ behavior: 'smooth' });
      }
    }

    function resetFilters() {
      filters = { role: 'ALL', player: 'ALL', mode: 'ALL', minGames: 1, search: '' };
      document.querySelectorAll('#role-filter-pills .role-pill').forEach(p => {
        p.classList.toggle('active', p.dataset.role === 'ALL');
      });
      document.getElementById('filter-player').value = 'ALL';
      document.getElementById('filter-mode').value = 'ALL';
      document.getElementById('filter-min-games').value = '1';
      document.getElementById('min-games-val').textContent = '1';
      document.getElementById('filter-search').value = '';
      renderAll();
    }

    function matchPassesFilters(match) {
      if (filters.mode !== 'ALL') {
        const mMode = (match.mode || '').toLowerCase();
        if (filters.mode === 'Ranked 5s' && !mMode.includes('5s')) return false;
        if (filters.mode === 'Ranked Flex' && !mMode.includes('flex')) return false;
        if (filters.mode === 'Normal' && (mMode.includes('5s') || mMode.includes('flex'))) return false;
      }
      const lineup = match.lineup || {};
      const entries = Object.entries(lineup);

      if (filters.player !== 'ALL') {
        const hasPlayer = entries.some(([r, p]) => p && p.player === filters.player && (filters.role === 'ALL' || r === filters.role));
        if (!hasPlayer) return false;
      } else if (filters.role !== 'ALL') {
        if (!lineup[filters.role]) return false;
      }

      if (filters.search) {
        const q = filters.search;
        const inMeta = (match.match_id || '').toLowerCase().includes(q) ||
                       (match.mode || '').toLowerCase().includes(q) ||
                       (match.mvp || '').toLowerCase().includes(q);
        const inLineup = entries.some(([r, p]) =>
          (p.player || '').toLowerCase().includes(q) ||
          (p.champion || '').toLowerCase().includes(q) ||
          (p.highlight || '').toLowerCase().includes(q)
        );
        if (!inMeta && !inLineup) return false;
      }
      return true;
    }

    function renderAll() {
      renderOverviewTab();
      renderSessionsTab();
      renderPlayersTab();
      renderSynergiesTab();
      renderTrendsTab();
    }

    // --- TAB 1: OVERVIEW ---
    function renderOverviewTab() {
      const data = getActiveData();
      const filteredMatches = (data.matches || []).filter(matchPassesFilters);

      // 1. Hero Active Session
      const activeSessions = (data.sessions || []).filter(s => ['IN_PROGRESS', 'READY', 'POLLING'].includes(s.status));
      const heroContainer = document.getElementById('overview-hero-session');

      if (activeSessions.length > 0) {
        const s = activeSessions[0];
        const starters = s.confirmed_players || [];
        const bench = s.bench_substitutes || [];
        const sMatches = s.session_matches || [];
        const sWins = sMatches.filter(m => m.result === 'WIN').length;
        const sLosses = sMatches.length - sWins;
        const pct = Math.min(100, Math.round((starters.length / 5) * 100));

        heroContainer.innerHTML = `
          <div class="hero-session">
            <div>
              <div style="display: flex; align-items: center; gap: 0.65rem; flex-wrap: wrap; margin-bottom: 0.5rem;">
                <span class="badge ${statusBadgeClass(s.status)}">● ${escapeHtml(s.status)}</span>
                <span class="badge badge-polling">${escapeHtml(s.mode)}</span>
                <span style="font-size: 0.8rem; color: var(--text-muted);">ID: <code>${escapeHtml(s.session_id)}</code></span>
              </div>
              <h2 style="font-size: 1.35rem; color: var(--gold-bright); margin-bottom: 0.3rem;">
                📅 Next Squad Session: ${escapeHtml(s.scheduled_time)}
              </h2>
              <p style="font-size: 0.84rem; color: var(--text-muted); margin-bottom: 0.85rem;">
                Organized by <strong style="color: var(--text-main);">${escapeHtml(s.creator)}</strong> •
                ${starters.length}/5 Confirmed Starters ${starters.length >= 2 && starters.length < 5 ? '(Viable Duo/Trio/Flex Stack Ready!)' : ''}
              </p>
              <div class="progress-bar" style="margin-bottom: 0.85rem;">
                <div class="progress-fill" style="width: ${pct}%;"></div>
              </div>
              <div style="display: flex; flex-wrap: wrap; gap: 0.45rem;">
                ${starters.map(p => `
                  <span class="player-chip">
                    <span class="role-badge">${escapeHtml(p.role_pref)}</span>
                    <strong>${escapeHtml(p.name)}</strong>
                  </span>
                `).join('')}
                ${bench.map(p => `
                  <span class="player-chip" style="opacity: 0.75; border-style: dashed;">
                    <span class="role-badge" style="background: rgba(200,170,110,0.2); color: var(--gold-primary);">BENCH</span>
                    <span>${escapeHtml(p.name)} (${escapeHtml(p.role_pref)})</span>
                  </span>
                `).join('')}
              </div>
            </div>
            <div style="display: flex; flex-direction: column; justify-content: space-between; background: rgba(6, 13, 24, 0.65); padding: 1rem; border-radius: 10px; border: 1px solid var(--border-subtle);">
              <div>
                <div class="filter-label" style="margin-bottom: 0.4rem;">Live Session Activity &amp; W-L Tally</div>
                <div style="font-size: 1.1rem; font-weight: 800; color: var(--cyan-bright); margin-bottom: 0.5rem;">
                  Session Record: ${sWins}W - ${sLosses}L (${sMatches.length} games)
                </div>
                <div style="font-size: 0.78rem; color: var(--text-muted); max-height: 95px; overflow-y: auto;">
                  ${(s.activity_log || []).slice(-4).map(line => `<div style="margin-bottom: 0.2rem;">${escapeHtml(line)}</div>`).join('') || '<div>Waiting for lobby updates...</div>'}
                </div>
              </div>
              <div style="margin-top: 0.75rem; text-align: right;">
                <button class="mode-btn active" onclick="switchTab('sessions')">View All ${data.sessions.length} Sessions →</button>
              </div>
            </div>
          </div>
        `;
      } else {
        heroContainer.innerHTML = '';
      }

      // 2. KPI Cards
      const total = filteredMatches.length;
      const wins = filteredMatches.filter(m => m.result === 'WIN').length;
      const losses = total - wins;
      const wr = total > 0 ? ((wins / total) * 100).toFixed(1) : '0.0';

      // MVP Leader
      const sortedPlayers = [...(data.players || [])].sort((a, b) => (b.mvps - a.mvps) || (b.avg_rating - a.avg_rating));
      const topMvp = sortedPlayers[0] || { name: 'N/A', mvps: 0, avg_rating: 0 };

      // Top Duo
      const allSynergies = [
        ...(data.synergies?.botlane || []),
        ...(data.synergies?.mid_jungle || []),
        ...(data.synergies?.top_jungle || []),
        ...(data.synergies?.support_jungle || [])
      ].sort((a, b) => b.synergy_score - a.synergy_score);
      const bestDuo = allSynergies[0];

      // Most Picked Champ
      const topChamp = (data.champions || [])[0];

      const streakLabel = data.kpis.streak_count > 0
        ? `${data.kpis.streak_count}${data.kpis.streak_type === 'WIN' ? 'W' : 'L'} Streak`
        : 'No Streak';

      document.getElementById('overview-kpi-grid').innerHTML = `
        <div class="kpi-card">
          <div class="kpi-label">Filtered Matches</div>
          <div class="kpi-value">${total}</div>
          <div class="kpi-sub">${wins}W - ${losses}L Record</div>
        </div>
        <div class="kpi-card cyan-top">
          <div class="kpi-label">Squad Win Rate</div>
          <div class="kpi-value" style="color: ${parseFloat(wr) >= 50 ? 'var(--win-green)' : 'var(--loss-red)'};">${wr}%</div>
          <div class="kpi-sub">Current Form: <strong>${streakLabel}</strong></div>
        </div>
        <div class="kpi-card">
          <div class="kpi-label">Squad MVP Leader</div>
          <div class="kpi-value">${escapeHtml(topMvp.name)}</div>
          <div class="kpi-sub">👑 ${topMvp.mvps} MVPs • ${topMvp.avg_rating} Avg Rating</div>
        </div>
        <div class="kpi-card cyan-top">
          <div class="kpi-label">Top Duo Synergy</div>
          <div class="kpi-value" style="font-size: 1.25rem;">${bestDuo ? escapeHtml(bestDuo.player_a + ' & ' + bestDuo.player_b) : 'N/A'}</div>
          <div class="kpi-sub">${bestDuo ? `${bestDuo.synergy_score} Score (${bestDuo.tier}) • ${bestDuo.win_rate}% WR` : 'Play 2+ squad games'}</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-label">Signature Comfort Pick</div>
          <div class="kpi-value">${topChamp ? escapeHtml(topChamp.champion) : 'N/A'}</div>
          <div class="kpi-sub">${topChamp ? `${topChamp.picks} Picks • ${topChamp.win_rate}% WR • ${topChamp.kda} KDA` : 'No picks logged yet'}</div>
        </div>
      `;

      // 3. Top Players & Top Synergies Mini Lists
      const topPlayersHtml = (data.players || []).filter(p => p.games > 0).slice(0, 5).map((p, idx) => `
        <div onclick="openPlayerModal('${escapeHtml(p.name)}')" style="display: flex; align-items: center; justify-content: space-between; padding: 0.55rem 0.65rem; border-bottom: 1px solid var(--border-subtle); cursor: pointer;">
          <div style="display: flex; align-items: center; gap: 0.65rem;">
            <span style="font-weight: 800; color: var(--gold-primary); width: 20px;">#${idx + 1}</span>
            <div>
              <div style="font-weight: 700; color: var(--text-main);">${escapeHtml(p.name)} <span class="role-badge">${escapeHtml(p.main_role)}</span></div>
              <div style="font-size: 0.75rem; color: var(--text-muted);">${p.games}G (${p.win_rate}% WR) • ${p.kda} KDA • 👑 ${p.mvps} MVP</div>
            </div>
          </div>
          <div style="display: flex; align-items: center; gap: 0.5rem;">
            <span style="font-weight: 800; color: var(--gold-bright);">${p.avg_rating}</span>
            <span class="grade-badge ${gradeClass(p.grade)}">${escapeHtml(p.grade)}</span>
          </div>
        </div>
      `).join('');
      document.getElementById('overview-top-players').innerHTML = topPlayersHtml || '<div class="empty-state">No player stats recorded yet.</div>';

      const topSynergiesHtml = allSynergies.slice(0, 5).map((s, idx) => `
        <div style="display: flex; align-items: center; justify-content: space-between; padding: 0.55rem 0.65rem; border-bottom: 1px solid var(--border-subtle);">
          <div>
            <div style="font-weight: 700; color: var(--text-main);">#${idx + 1} ${escapeHtml(s.pair)}</div>
            <div style="font-size: 0.75rem; color: var(--text-muted);">
              <span class="highlight-chip">${escapeHtml(s.tag)}</span> • ${s.games}G (${s.win_rate}% WR) • ${s.combined_kda} KDA
            </div>
          </div>
          <div style="text-align: right;">
            <div style="font-weight: 800; color: var(--cyan-bright);">${s.synergy_score}</div>
            <div style="font-size: 0.7rem; color: var(--gold-primary); font-weight: 700;">${escapeHtml(s.tier)}</div>
          </div>
        </div>
      `).join('');
      document.getElementById('overview-top-synergies').innerHTML = topSynergiesHtml || '<div class="empty-state">No duo synergies calculated yet.</div>';

      // 4. Recent Matches Accordion List
      const matchesContainer = document.getElementById('overview-matches-list');
      if (filteredMatches.length === 0) {
        matchesContainer.innerHTML = '<div class="hex-card empty-state">No matches match your current filter selection.</div>';
        return;
      }

      matchesContainer.innerHTML = filteredMatches.map((m, idx) => {
        const isWin = m.result === 'WIN';
        const lineup = m.lineup || {};
        const roleOrder = ['Top', 'Jungle', 'Mid', 'Bot', 'Support'];
        const rolesPresent = roleOrder.filter(r => lineup[r]).concat(Object.keys(lineup).filter(r => !roleOrder.includes(r)));

        const summaryPills = rolesPresent.map(r => {
          const p = lineup[r];
          const isMvp = p.player === m.mvp;
          return `
            <span class="player-chip" style="${isMvp ? 'border-color: var(--gold-primary); background: rgba(200,170,110,0.12);' : ''}">
              <span class="role-badge">${escapeHtml(r)}</span>
              <strong>${escapeHtml(p.player)}</strong>
              <span style="color: var(--gold-primary);">${escapeHtml(p.champion)}</span>
              <span style="font-size: 0.73rem; color: var(--text-muted);">${p.kills}/${p.deaths}/${p.assists}</span>
              <span class="grade-badge ${gradeClass(p.grade)}" style="transform: scale(0.88);">${escapeHtml(p.grade || 'A')}</span>
            </span>
          `;
        }).join('');

        const detailRows = rolesPresent.map(r => {
          const p = lineup[r];
          const kda = ((p.kills + p.assists) / Math.max(1, p.deaths)).toFixed(2);
          const isMvp = p.player === m.mvp;
          return `
            <tr>
              <td><span class="role-badge">${escapeHtml(r)}</span></td>
              <td>
                <strong style="cursor: pointer; color: var(--gold-bright);" onclick="openPlayerModal('${escapeHtml(p.player)}')">
                  ${escapeHtml(p.player)}
                </strong>
                ${isMvp ? ' <span class="badge badge-polling">👑 MVP</span>' : ''}
              </td>
              <td>
                <strong>${escapeHtml(p.champion)}</strong>
                <span class="archetype-tag">${escapeHtml(p.archetype || '')}</span>
              </td>
              <td>${p.kills} / <span style="color: var(--loss-red);">${p.deaths}</span> / ${p.assists} <span style="color: var(--text-muted);">(${kda})</span></td>
              <td>${(p.damage || 0).toLocaleString()}</td>
              <td>${p.cs || 0}</td>
              <td>${p.vision || 0}</td>
              <td><span class="highlight-chip">${escapeHtml(p.highlight || 'Squad Contributor')}</span></td>
              <td>
                <strong style="color: var(--gold-bright); margin-right: 0.35rem;">${p.rating ?? '-'}</strong>
                <span class="grade-badge ${gradeClass(p.grade)}">${escapeHtml(p.grade || '-')}</span>
              </td>
            </tr>
          `;
        }).join('');

        return `
          <div class="match-card ${isWin ? 'win' : 'loss'} ${idx === 0 ? 'expanded' : ''}" id="match-card-${idx}">
            <div class="match-header" onclick="document.getElementById('match-card-${idx}').classList.toggle('expanded')">
              <div style="display: flex; align-items: center; gap: 0.75rem; flex-wrap: wrap;">
                <span class="badge ${isWin ? 'badge-win' : 'badge-loss'}">${isWin ? 'VICTORY' : 'DEFEAT'}</span>
                <strong style="color: var(--gold-bright);">${escapeHtml(m.mode || 'Match')}</strong>
                <span style="font-size: 0.8rem; color: var(--text-muted);">⏱️ ${m.duration_min || 30}m • 📅 ${escapeHtml(m.date || '')}</span>
                <span style="font-size: 0.8rem; color: var(--gold-primary);">👑 MVP: <strong>${escapeHtml(m.mvp || 'N/A')}</strong></span>
              </div>
              <div style="display: flex; flex-wrap: wrap; gap: 0.4rem;">
                ${summaryPills}
              </div>
            </div>
            <div class="match-body">
              <div class="table-wrap" style="margin-top: 0.75rem;">
                <table class="hex-table">
                  <thead>
                    <tr>
                      <th>Role</th>
                      <th>Player</th>
                      <th>Champion &amp; Archetype</th>
                      <th>K / D / A (Ratio)</th>
                      <th>Damage</th>
                      <th>CS</th>
                      <th>Vision</th>
                      <th>Standout Highlight</th>
                      <th>Holistic Rating</th>
                    </tr>
                  </thead>
                  <tbody>${detailRows}</tbody>
                </table>
              </div>
            </div>
          </div>
        `;
      }).join('');
    }

    // --- TAB 2: SESSIONS ---
    function renderSessionsTab() {
      const data = getActiveData();
      const statusFilter = document.getElementById('session-status-filter').value;
      const sessions = (data.sessions || []).filter(s => {
        if (statusFilter === 'ACTIVE' && !['POLLING', 'READY', 'IN_PROGRESS'].includes(s.status)) return false;
        if (statusFilter !== 'ALL' && statusFilter !== 'ACTIVE' && s.status !== statusFilter) return false;
        if (filters.mode !== 'ALL') {
          const m = (s.mode || '').toLowerCase();
          if (filters.mode === 'Ranked 5s' && !m.includes('5s')) return false;
          if (filters.mode === 'Ranked Flex' && !m.includes('flex')) return false;
        }
        if (filters.player !== 'ALL') {
          const inStarters = (s.confirmed_players || []).some(p => p.name === filters.player);
          const inBench = (s.bench_substitutes || []).some(p => p.name === filters.player);
          if (!inStarters && !inBench && s.creator !== filters.player) return false;
        }
        if (filters.search) {
          const q = filters.search;
          const hay = `${s.session_id} ${s.scheduled_time} ${s.mode} ${s.creator} ${(s.confirmed_players || []).map(p => p.name).join(' ')}`.toLowerCase();
          if (!hay.includes(q)) return false;
        }
        return true;
      });

      const container = document.getElementById('sessions-grid');
      if (sessions.length === 0) {
        container.innerHTML = '<div class="hex-card empty-state">No sessions match the selected filters.</div>';
        return;
      }

      container.innerHTML = sessions.map(s => {
        const starters = s.confirmed_players || [];
        const bench = s.bench_substitutes || [];
        const declined = s.declined || [];
        const sMatches = s.session_matches || [];
        const wins = sMatches.filter(m => m.result === 'WIN').length;
        const losses = sMatches.length - wins;
        const pct = Math.min(100, Math.round((starters.length / 5) * 100));

        return `
          <div class="hex-card">
            <div style="display: flex; align-items: center; justify-content: space-between; gap: 0.5rem; margin-bottom: 0.6rem;">
              <div style="display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap;">
                <span class="badge ${statusBadgeClass(s.status)}">${escapeHtml(s.status)}</span>
                <span class="badge badge-polling">${escapeHtml(s.mode)}</span>
              </div>
              <code style="font-size: 0.76rem; color: var(--text-muted);">${escapeHtml(s.session_id)}</code>
            </div>

            <h3 style="color: var(--gold-bright); font-size: 1.1rem; margin-bottom: 0.25rem;">
              🕒 ${escapeHtml(s.scheduled_time)}
            </h3>
            <div style="font-size: 0.8rem; color: var(--text-muted); margin-bottom: 0.75rem;">
              Created by <strong style="color: var(--text-main);">${escapeHtml(s.creator)}</strong> •
              Starters: <strong>${starters.length}/5</strong>
              ${starters.length >= 2 && starters.length < 5 ? '<span style="color: var(--cyan-bright);"> (Viable Flex/Duo/Trio)</span>' : ''}
            </div>

            <div class="progress-bar" style="margin-bottom: 0.85rem;">
              <div class="progress-fill" style="width: ${pct}%;"></div>
            </div>

            <div style="margin-bottom: 0.75rem;">
              <div class="filter-label" style="margin-bottom: 0.35rem;">Confirmed Starters (${starters.length}/5)</div>
              <div style="display: flex; flex-wrap: wrap; gap: 0.4rem;">
                ${starters.length > 0 ? starters.map(p => `
                  <span class="player-chip" onclick="openPlayerModal('${escapeHtml(p.name)}')" style="cursor: pointer;">
                    <span class="role-badge">${escapeHtml(p.role_pref)}</span>
                    <strong>${escapeHtml(p.name)}</strong>
                  </span>
                `).join('') : '<span style="font-size: 0.8rem; color: var(--text-dim);">No starters confirmed yet</span>'}
              </div>
            </div>

            ${bench.length > 0 ? `
              <div style="margin-bottom: 0.75rem;">
                <div class="filter-label" style="margin-bottom: 0.35rem;">🛡️ Bench Substitutes (Auto-Promote Queue)</div>
                <div style="display: flex; flex-wrap: wrap; gap: 0.4rem;">
                  ${bench.map((p, idx) => `
                    <span class="player-chip">
                      <span class="role-badge" style="background: rgba(200,170,110,0.2); color: var(--gold-primary);">#${idx + 1} ${escapeHtml(p.role_pref)}</span>
                      <span>${escapeHtml(p.name)}</span>
                    </span>
                  `).join('')}
                </div>
              </div>
            ` : ''}

            ${declined.length > 0 ? `
              <div style="font-size: 0.76rem; color: var(--text-dim); margin-bottom: 0.75rem;">
                ❌ Declined: ${declined.map(escapeHtml).join(', ')}
              </div>
            ` : ''}

            <div style="background: rgba(6, 13, 24, 0.65); border: 1px solid var(--border-subtle); border-radius: 8px; padding: 0.7rem; font-size: 0.78rem;">
              <div style="display: flex; justify-content: space-between; margin-bottom: 0.35rem;">
                <span class="filter-label">Session Match Tally</span>
                <strong style="color: var(--cyan-bright);">${wins}W - ${losses}L (${sMatches.length} matches)</strong>
              </div>
              <div style="color: var(--text-muted); max-height: 85px; overflow-y: auto;">
                ${(s.activity_log || []).map(l => `<div style="margin-bottom: 0.15rem;">${escapeHtml(l)}</div>`).join('') || '<div>No activity logged.</div>'}
              </div>
            </div>
          </div>
        `;
      }).join('');
    }

    // --- TAB 3: PLAYERS ---
    function sortPlayersBy(key) {
      if (playerSort.key === key) {
        playerSort.asc = !playerSort.asc;
      } else {
        playerSort.key = key;
        playerSort.asc = (key === 'name' || key === 'main_role');
      }
      renderPlayersTab();
    }

    function renderPlayersTab() {
      const data = getActiveData();
      let players = (data.players || []).filter(p => {
        if (filters.player !== 'ALL' && p.name !== filters.player) return false;
        if (filters.role !== 'ALL' && p.primary_role !== filters.role && p.secondary_role !== filters.role && p.main_role !== filters.role) return false;
        if (p.games > 0 && p.games < filters.minGames && filters.minGames > 1) return false;
        if (filters.search) {
          const q = filters.search;
          const hay = `${p.name} ${p.discord_tag} ${p.primary_role} ${p.secondary_role} ${(p.fav_champs || []).join(' ')}`.toLowerCase();
          if (!hay.includes(q)) return false;
        }
        return true;
      });

      players.sort((a, b) => {
        const k = playerSort.key;
        const va = a[k] ?? 0;
        const vb = b[k] ?? 0;
        if (typeof va === 'string') {
          return playerSort.asc ? va.localeCompare(vb) : vb.localeCompare(va);
        }
        return playerSort.asc ? (va - vb) : (vb - va);
      });

      // Render Roster Cards
      const cardsGrid = document.getElementById('players-cards-grid');
      cardsGrid.innerHTML = players.map(p => {
        const riotIds = (p.accounts || []).map(a => a.riot_id).filter(Boolean);
        return `
          <div class="hex-card interactive" onclick="openPlayerModal('${escapeHtml(p.name)}')">
            <div style="display: flex; align-items: flex-start; justify-content: space-between; gap: 0.75rem; margin-bottom: 0.75rem;">
              <div style="display: flex; align-items: center; gap: 0.75rem;">
                <div class="brand-crest" style="width: 40px; height: 40px; font-size: 1rem;">
                  ${escapeHtml(p.name.slice(0, 2).toUpperCase())}
                </div>
                <div>
                  <div style="font-size: 1.05rem; font-weight: 800; color: var(--gold-bright);">${escapeHtml(p.name)}</div>
                  <div style="font-size: 0.75rem; color: var(--text-muted);">
                    ${escapeHtml(p.discord_tag)}
                    ${riotIds.length > 0 ? ` • <span style="color: var(--cyan-bright);">🎮 ${escapeHtml(riotIds[0])}</span>` : ''}
                  </div>
                </div>
              </div>
              <span class="grade-badge ${gradeClass(p.grade)}">${escapeHtml(p.grade)}</span>
            </div>

            <div style="display: flex; gap: 0.45rem; flex-wrap: wrap; margin-bottom: 0.85rem;">
              <span class="role-badge">Main: ${escapeHtml(p.primary_role)}</span>
              <span class="role-badge" style="background: rgba(200,170,110,0.15); color: var(--gold-primary);">2nd: ${escapeHtml(p.secondary_role)}</span>
              ${p.mvps > 0 ? `<span class="badge badge-polling">👑 ${p.mvps} MVP${p.mvps > 1 ? 's' : ''}</span>` : ''}
            </div>

            <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.5rem; background: rgba(6, 13, 24, 0.65); padding: 0.65rem; border-radius: 8px; text-align: center; margin-bottom: 0.8rem;">
              <div>
                <div style="font-size: 0.68rem; color: var(--text-muted); text-transform: uppercase;">Win Rate</div>
                <div style="font-weight: 800; color: ${p.win_rate >= 50 ? 'var(--win-green)' : 'var(--text-main)'};">${p.win_rate}%</div>
                <div style="font-size: 0.68rem; color: var(--text-dim);">${p.wins}W-${p.losses}L</div>
              </div>
              <div>
                <div style="font-size: 0.68rem; color: var(--text-muted); text-transform: uppercase;">KDA Ratio</div>
                <div style="font-weight: 800; color: var(--cyan-bright);">${p.kda}</div>
                <div style="font-size: 0.68rem; color: var(--text-dim);">${p.kills}/${p.deaths}/${p.assists}</div>
              </div>
              <div>
                <div style="font-size: 0.68rem; color: var(--text-muted); text-transform: uppercase;">Avg Rating</div>
                <div style="font-weight: 800; color: var(--gold-bright);">${p.avg_rating}</div>
                <div style="font-size: 0.68rem; color: var(--text-dim);">/ 100</div>
              </div>
            </div>

            <div style="font-size: 0.76rem; color: var(--text-muted);">
              <strong style="color: var(--gold-primary);">Fav Champs:</strong>
              ${(p.fav_champs || []).map(c => `<span class="archetype-tag" style="margin-left: 0.25rem;">${escapeHtml(c)}</span>`).join('')}
            </div>
          </div>
        `;
      }).join('');

      // Render Table
      const tbody = document.getElementById('players-table-body');
      tbody.innerHTML = players.map((p, idx) => `
        <tr onclick="openPlayerModal('${escapeHtml(p.name)}')" style="cursor: pointer;">
          <td><strong>#${idx + 1}</strong></td>
          <td>
            <strong style="color: var(--gold-bright);">${escapeHtml(p.name)}</strong>
            <div style="font-size: 0.72rem; color: var(--text-muted);">${escapeHtml(p.discord_tag)}</div>
          </td>
          <td><span class="role-badge">${escapeHtml(p.primary_role)}</span> <span style="font-size: 0.75rem; color: var(--text-muted);">/ ${escapeHtml(p.secondary_role)}</span></td>
          <td>${p.games} <span style="color: var(--text-muted);">(${p.wins}W-${p.losses}L)</span></td>
          <td><strong style="color: ${p.win_rate >= 50 ? 'var(--win-green)' : 'var(--loss-red)'};">${p.win_rate}%</strong></td>
          <td><strong style="color: var(--cyan-bright);">${p.kda}</strong></td>
          <td>
            <strong style="color: var(--gold-bright); margin-right: 0.35rem;">${p.avg_rating}</strong>
            <span class="grade-badge ${gradeClass(p.grade)}">${escapeHtml(p.grade)}</span>
          </td>
          <td>👑 ${p.mvps}</td>
          <td>${(p.fav_champs || []).map(c => `<span class="archetype-tag" style="margin-right: 0.25rem;">${escapeHtml(c)}</span>`).join('')}</td>
        </tr>
      `).join('');
    }

    function openPlayerModal(playerName) {
      const data = getActiveData();
      const p = (data.players || []).find(x => x.name === playerName);
      if (!p) return;

      const pillars = p.pillars_avg || {};
      const pillarLabels = [
        ['combat', '⚔️ Combat & KDA'],
        ['damage', '🔥 Damage Output'],
        ['objective', '🐉 Objective Pressure'],
        ['frontline', '🛡️ Frontline & Tank'],
        ['utility', '✨ Utility & Peel'],
        ['macro_vision', '👁️ Vision & Economy']
      ];

      const pillarBarsHtml = pillarLabels.map(([k, label]) => {
        const val = pillars[k] || 0;
        return `
          <div class="pillar-row">
            <span style="color: var(--text-muted); font-weight: 600;">${label}</span>
            <div class="progress-bar">
              <div class="progress-fill" style="width: ${Math.min(100, val)}%;"></div>
            </div>
            <strong style="text-align: right; color: var(--gold-bright);">${val}</strong>
          </div>
        `;
      }).join('');

      const champRows = (p.champion_pool || []).map(c => `
        <tr>
          <td><strong>${escapeHtml(c.champion)}</strong> <span class="archetype-tag">${escapeHtml(c.archetype)}</span></td>
          <td><span class="role-badge">${escapeHtml(c.primary_role)}</span></td>
          <td>${c.games} (${c.wins}W-${c.losses}L)</td>
          <td style="color: ${c.win_rate >= 50 ? 'var(--win-green)' : 'var(--loss-red)'}; font-weight: 700;">${c.win_rate}%</td>
          <td>${c.avg_kills}/${c.avg_deaths}/${c.avg_assists} (<strong style="color: var(--cyan-bright);">${c.kda}</strong>)</td>
          <td><strong style="color: var(--gold-bright);">${c.avg_rating}</strong></td>
        </tr>
      `).join('');

      const recentRows = (p.recent_matches || []).slice(0, 8).map(m => `
        <tr>
          <td><span class="badge ${m.result === 'WIN' ? 'badge-win' : 'badge-loss'}">${m.result}</span></td>
          <td>${escapeHtml(m.date || '')}</td>
          <td><span class="role-badge">${escapeHtml(m.role)}</span> <strong>${escapeHtml(m.champion)}</strong></td>
          <td>${m.kills}/${m.deaths}/${m.assists}</td>
          <td><span class="highlight-chip">${escapeHtml(m.highlight || '')}</span> ${m.is_mvp ? '👑' : ''}</td>
          <td><strong>${m.rating}</strong> <span class="grade-badge ${gradeClass(m.grade)}">${escapeHtml(m.grade)}</span></td>
        </tr>
      `).join('');

      const riotAccounts = (p.accounts || []).map(a => `<code style="margin-right: 0.5rem; color: var(--cyan-bright);">${escapeHtml(a.riot_id)}</code>`).join('') || '<span style="color: var(--text-dim);">Not linked yet (/link-riot)</span>';

      document.getElementById('player-modal-body').innerHTML = `
        <div style="display: flex; align-items: center; gap: 1rem; flex-wrap: wrap; margin-bottom: 1.2rem;">
          <div class="brand-crest" style="width: 54px; height: 54px; font-size: 1.35rem;">
            ${escapeHtml(p.name.slice(0, 2).toUpperCase())}
          </div>
          <div>
            <h2 style="color: var(--gold-bright); font-size: 1.45rem;">
              ${escapeHtml(p.name)}
              <span class="grade-badge ${gradeClass(p.grade)}" style="vertical-align: middle; margin-left: 0.4rem;">${escapeHtml(p.grade)}</span>
            </h2>
            <div style="font-size: 0.82rem; color: var(--text-muted);">
              Discord: <strong>${escapeHtml(p.discord_tag)}</strong> •
              Roles: <span class="role-badge">${escapeHtml(p.primary_role)}</span> / <span class="role-badge">${escapeHtml(p.secondary_role)}</span> •
              Linked Riot IDs: ${riotAccounts}
            </div>
          </div>
        </div>

        <div class="grid-2" style="margin-bottom: 1.25rem;">
          <div class="hex-card" style="background: rgba(6, 13, 24, 0.7);">
            <div style="font-weight: 700; color: var(--gold-primary); margin-bottom: 0.65rem; font-size: 0.86rem; text-transform: uppercase;">
              📊 6-Pillar Holistic Performance Profile
            </div>
            ${pillarBarsHtml}
          </div>
          <div class="hex-card" style="background: rgba(6, 13, 24, 0.7); display: flex; flex-direction: column; justify-content: center;">
            <div class="kpi-grid" style="grid-template-columns: repeat(2, 1fr); margin-bottom: 0;">
              <div>
                <div class="kpi-label">Career Win Rate</div>
                <div class="kpi-value" style="font-size: 1.4rem;">${p.win_rate}% (${p.wins}W-${p.losses}L)</div>
              </div>
              <div>
                <div class="kpi-label">Holistic Rating</div>
                <div class="kpi-value" style="font-size: 1.4rem; color: var(--cyan-bright);">${p.avg_rating} / 100</div>
              </div>
              <div>
                <div class="kpi-label">Overall KDA</div>
                <div class="kpi-value" style="font-size: 1.4rem;">${p.kda}</div>
              </div>
              <div>
                <div class="kpi-label">Match MVPs</div>
                <div class="kpi-value" style="font-size: 1.4rem;">👑 ${p.mvps}</div>
              </div>
            </div>
          </div>
        </div>

        <h3 style="color: var(--gold-bright); font-size: 1rem; margin-bottom: 0.55rem;">🐉 Personal Champion Pool</h3>
        <div class="table-wrap" style="margin-bottom: 1.25rem;">
          <table class="hex-table">
            <thead>
              <tr>
                <th>Champion</th>
                <th>Role</th>
                <th>Games</th>
                <th>Win Rate</th>
                <th>Avg K/D/A (Ratio)</th>
                <th>Avg Rating</th>
              </tr>
            </thead>
            <tbody>${champRows || '<tr><td colspan="6" class="empty-state">No champion games logged yet.</td></tr>'}</tbody>
          </table>
        </div>

        <h3 style="color: var(--gold-bright); font-size: 1rem; margin-bottom: 0.55rem;">⚔️ Recent Match Performances</h3>
        <div class="table-wrap">
          <table class="hex-table">
            <thead>
              <tr>
                <th>Outcome</th>
                <th>Date</th>
                <th>Role &amp; Champion</th>
                <th>K/D/A</th>
                <th>Highlight</th>
                <th>Rating</th>
              </tr>
            </thead>
            <tbody>${recentRows || '<tr><td colspan="6" class="empty-state">No recent matches logged yet.</td></tr>'}</tbody>
          </table>
        </div>
      `;

      document.getElementById('player-modal').classList.add('open');
    }

    function closePlayerModal() {
      document.getElementById('player-modal').classList.remove('open');
    }

    // --- TAB 4: SYNERGIES ---
    function setSynergyCategory(cat) {
      synergyCategory = cat;
      document.querySelectorAll('#synergy-pair-pills .role-pill').forEach(p => {
        p.classList.toggle('active', p.dataset.pair === cat);
      });
      renderSynergiesTab();
    }

    function sortSynergiesBy(key) {
      if (synergySort.key === key) {
        synergySort.asc = !synergySort.asc;
      } else {
        synergySort.key = key;
        synergySort.asc = false;
      }
      renderSynergiesTab();
    }

    function renderSynergiesTab() {
      const data = getActiveData();
      const synMap = data.synergies || {};
      const catLabels = {
        botlane: '🏹🛡️ Bot + Support',
        mid_jungle: '🔮🌲 Mid + Jungle',
        top_jungle: '⚔️🌲 Top + Jungle',
        support_jungle: '🛡️🌲 Support + Jungle'
      };

      let rows = [];
      Object.entries(catLabels).forEach(([key, label]) => {
        if (synergyCategory !== 'ALL' && synergyCategory !== key) return;
        (synMap[key] || []).forEach(item => {
          rows.push({ ...item, categoryKey: key, categoryLabel: label });
        });
      });

      rows = rows.filter(r => {
        if (r.games < filters.minGames) return false;
        if (filters.player !== 'ALL' && r.player_a !== filters.player && r.player_b !== filters.player) return false;
        if (filters.search) {
          const q = filters.search;
          const hay = `${r.pair} ${r.tag} ${r.tier} ${r.favorite_combo}`.toLowerCase();
          if (!hay.includes(q)) return false;
        }
        return true;
      });

      rows.sort((a, b) => {
        const k = synergySort.key;
        return synergySort.asc ? (a[k] - b[k]) : (b[k] - a[k]);
      });

      // Top 3 Cards
      const cardsGrid = document.getElementById('synergies-cards-grid');
      cardsGrid.innerHTML = rows.slice(0, 6).map((s, idx) => `
        <div class="hex-card">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
            <span style="font-size: 0.75rem; color: var(--gold-primary); font-weight: 700;">${escapeHtml(s.categoryLabel)}</span>
            <span class="badge ${s.tier === 'S Tier' ? 'badge-ready' : 'badge-polling'}">${escapeHtml(s.tier)}</span>
          </div>
          <h3 style="color: var(--gold-bright); font-size: 1.05rem; margin-bottom: 0.3rem;">
            #${idx + 1} ${escapeHtml(s.player_a)} &amp; ${escapeHtml(s.player_b)}
          </h3>
          <div style="margin-bottom: 0.75rem;">
            <span class="highlight-chip">${escapeHtml(s.tag)}</span>
            <span class="archetype-tag" style="margin-left: 0.3rem;">Combo: ${escapeHtml(s.favorite_combo)}</span>
          </div>
          <div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 0.4rem; background: rgba(6, 13, 24, 0.65); padding: 0.6rem; border-radius: 8px; text-align: center; font-size: 0.8rem;">
            <div>
              <div style="font-size: 0.66rem; color: var(--text-muted);">SYNERGY</div>
              <strong style="color: var(--cyan-bright); font-size: 1rem;">${s.synergy_score}</strong>
            </div>
            <div>
              <div style="font-size: 0.66rem; color: var(--text-muted);">WIN RATE</div>
              <strong style="color: var(--win-green);">${s.win_rate}%</strong>
            </div>
            <div>
              <div style="font-size: 0.66rem; color: var(--text-muted);">DUO KDA</div>
              <strong style="color: var(--gold-bright);">${s.combined_kda}</strong>
            </div>
            <div>
              <div style="font-size: 0.66rem; color: var(--text-muted);">RECORD</div>
              <strong>${s.wins}W-${s.losses}L</strong>
            </div>
          </div>
        </div>
      `).join('');

      const tbody = document.getElementById('synergies-table-body');
      tbody.innerHTML = rows.map(s => `
        <tr>
          <td><span style="font-size: 0.78rem; color: var(--gold-primary); font-weight: 600;">${escapeHtml(s.categoryLabel)}</span></td>
          <td><strong>${escapeHtml(s.pair)}</strong></td>
          <td>
            <span class="badge ${s.tier === 'S Tier' ? 'badge-ready' : 'badge-polling'}">${escapeHtml(s.tier)}</span>
            <span class="highlight-chip" style="margin-left: 0.3rem;">${escapeHtml(s.tag)}</span>
          </td>
          <td><strong style="color: var(--cyan-bright); font-size: 0.98rem;">${s.synergy_score}</strong></td>
          <td><strong style="color: ${s.win_rate >= 50 ? 'var(--win-green)' : 'var(--loss-red)'};">${s.win_rate}%</strong> (${s.wins}W-${s.losses}L)</td>
          <td><strong>${s.combined_kda}</strong></td>
          <td>${s.avg_duo_rating}</td>
          <td>${s.coordination_score}</td>
          <td>${s.games}</td>
          <td><span class="archetype-tag">${escapeHtml(s.favorite_combo)}</span></td>
        </tr>
      `).join('') || '<tr><td colspan="10" class="empty-state">No duo pairs match the current filter criteria.</td></tr>';
    }

    // --- TAB 5: META & GAMEPLAY TRENDS ---
    function sortChampsBy(key) {
      if (champSort.key === key) {
        champSort.asc = !champSort.asc;
      } else {
        champSort.key = key;
        champSort.asc = (key === 'champion' || key === 'archetype' || key === 'primary_role');
      }
      renderTrendsTab();
    }

    function getFilteredChampionStats() {
      const data = getActiveData();
      const filteredMatches = (data.matches || []).filter(matchPassesFilters);
      const map = {};

      filteredMatches.forEach(m => {
        const isWin = m.result === 'WIN';
        const dur = parseFloat(m.duration_min || 30);
        const lineup = m.lineup || {};
        Object.entries(lineup).forEach(([role, p]) => {
          if (!p) return;
          if (filters.role !== 'ALL' && role !== filters.role) return;
          if (filters.player !== 'ALL' && p.player !== filters.player) return;
          if (filters.search) {
            const q = filters.search;
            const hay = `${p.champion} ${p.player} ${p.archetype} ${role}`.toLowerCase();
            if (!hay.includes(q)) return;
          }
          const c = p.champion || 'Unknown';
          if (!map[c]) {
            map[c] = {
              champion: c,
              archetype: p.archetype || 'bruiser',
              picks: 0, wins: 0, losses: 0,
              kills: 0, deaths: 0, assists: 0,
              damage: 0, cs: 0, dur: 0, ratingSum: 0,
              roles: {}, pilots: {}
            };
          }
          const entry = map[c];
          entry.picks += 1;
          if (isWin) entry.wins += 1; else entry.losses += 1;
          entry.kills += (p.kills || 0);
          entry.deaths += (p.deaths || 0);
          entry.assists += (p.assists || 0);
          entry.damage += (p.damage || 0);
          entry.cs += (p.cs || 0);
          entry.dur += dur;
          entry.ratingSum += parseFloat(p.rating || 65);
          entry.roles[role] = (entry.roles[role] || 0) + 1;
          entry.pilots[p.player] = (entry.pilots[p.player] || 0) + 1;
        });
      });

      let list = Object.values(map).map(e => {
        const g = e.picks;
        const avgR = +(e.ratingSum / g).toFixed(1);
        const topRole = Object.keys(e.roles).sort((a, b) => e.roles[b] - e.roles[a])[0] || 'Flex';
        const topPilot = Object.keys(e.pilots).sort((a, b) => e.pilots[b] - e.pilots[a])[0] || 'N/A';
        return {
          champion: e.champion,
          archetype: e.archetype,
          primary_role: topRole,
          picks: g,
          wins: e.wins,
          losses: e.losses,
          win_rate: +((e.wins / g) * 100).toFixed(1),
          kda: +((e.kills + e.assists) / Math.max(1, e.deaths)).toFixed(2),
          dpm: Math.round(e.damage / Math.max(1, e.dur)),
          cspm: +(e.cs / Math.max(1, e.dur)).toFixed(1),
          avg_rating: avgR,
          top_pilot: topPilot
        };
      }).filter(c => c.picks >= filters.minGames);

      list.sort((a, b) => {
        const k = champSort.key;
        const va = a[k];
        const vb = b[k];
        if (typeof va === 'string') return champSort.asc ? va.localeCompare(vb) : vb.localeCompare(va);
        return champSort.asc ? (va - vb) : (vb - va);
      });

      return list;
    }

    function renderTrendsTab() {
      const list = getFilteredChampionStats();
      const tbody = document.getElementById('champions-table-body');

      tbody.innerHTML = list.map(c => `
        <tr>
          <td><strong style="color: var(--gold-bright);">${escapeHtml(c.champion)}</strong></td>
          <td><span class="archetype-tag">${escapeHtml(c.archetype)}</span></td>
          <td><span class="role-badge">${escapeHtml(c.primary_role)}</span></td>
          <td><strong>${c.picks}</strong> (${c.wins}W-${c.losses}L)</td>
          <td><strong style="color: ${c.win_rate >= 50 ? 'var(--win-green)' : 'var(--loss-red)'};">${c.win_rate}%</strong></td>
          <td><strong style="color: var(--cyan-bright);">${c.kda}</strong></td>
          <td>${c.dpm.toLocaleString()}</td>
          <td>${c.cspm}</td>
          <td><strong style="color: var(--gold-bright);">${c.avg_rating}</strong></td>
          <td>${escapeHtml(c.top_pilot)}</td>
        </tr>
      `).join('') || '<tr><td colspan="10" class="empty-state">No champion data matches the current filters.</td></tr>';

      if (currentTab === 'trends') {
        renderTrendsCharts(list);
      }
    }

    function renderTrendsCharts(champListOpt) {
      if (typeof Chart === 'undefined') return;
      const list = champListOpt || getFilteredChampionStats();
      const data = getActiveData();
      const filteredMatches = [...(data.matches || [])].filter(matchPassesFilters).reverse();

      Object.values(chartInstances).forEach(ch => ch && ch.destroy());
      chartInstances = {};

      const topPicked = [...list].sort((a, b) => b.picks - a.picks || b.win_rate - a.win_rate).slice(0, 8);
      const topRated = [...list].sort((a, b) => b.avg_rating - a.avg_rating).slice(0, 8);

      // Chart 1: Most Picked Champions (Wins vs Losses stacked bar)
      const ctx1 = document.getElementById('chart-most-picked');
      if (ctx1) {
        chartInstances.c1 = new Chart(ctx1, {
          type: 'bar',
          data: {
            labels: topPicked.map(c => c.champion),
            datasets: [
              { label: 'Wins', data: topPicked.map(c => c.wins), backgroundColor: 'rgba(46, 204, 113, 0.8)' },
              { label: 'Losses', data: topPicked.map(c => c.losses), backgroundColor: 'rgba(231, 76, 60, 0.8)' }
            ]
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
              x: { stacked: true, ticks: { color: '#e8e4dc' }, grid: { color: 'rgba(255,255,255,0.05)' } },
              y: { stacked: true, ticks: { color: '#94a3b8', stepSize: 1 }, grid: { color: 'rgba(255,255,255,0.06)' } }
            },
            plugins: { legend: { labels: { color: '#e8e4dc' } } }
          }
        });
      }

      // Chart 2: Highest Holistic Rating by Champion
      const ctx2 = document.getElementById('chart-champ-ratings');
      if (ctx2) {
        chartInstances.c2 = new Chart(ctx2, {
          type: 'bar',
          data: {
            labels: topRated.map(c => c.champion),
            datasets: [{
              label: 'Avg Holistic Rating (0-100)',
              data: topRated.map(c => c.avg_rating),
              backgroundColor: 'rgba(10, 200, 185, 0.75)',
              borderColor: '#0ac8b9',
              borderWidth: 1
            }]
          },
          options: {
            indexAxis: 'y',
            responsive: true,
            maintainAspectRatio: false,
            scales: {
              x: { min: 0, max: 100, ticks: { color: '#94a3b8' }, grid: { color: 'rgba(255,255,255,0.06)' } },
              y: { ticks: { color: '#e8e4dc' }, grid: { display: false } }
            },
            plugins: { legend: { labels: { color: '#e8e4dc' } } }
          }
        });
      }

      // Chart 3: Kit Archetype Breakdown
      const archCounts = {};
      list.forEach(c => {
        archCounts[c.archetype] = (archCounts[c.archetype] || 0) + c.picks;
      });
      const archKeys = Object.keys(archCounts);
      const ctx3 = document.getElementById('chart-archetypes');
      if (ctx3) {
        chartInstances.c3 = new Chart(ctx3, {
          type: 'doughnut',
          data: {
            labels: archKeys.map(k => k.toUpperCase()),
            datasets: [{
              data: archKeys.map(k => archCounts[k]),
              backgroundColor: ['#c8aa6e', '#0ac8b9', '#3b82f6', '#2ecc71', '#9b59b6', '#f59e0b', '#ec4899', '#64748b'],
              borderColor: '#091428',
              borderWidth: 2
            }]
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              legend: { position: 'right', labels: { color: '#e8e4dc', font: { size: 11 } } }
            }
          }
        });
      }

      // Chart 4: Cumulative Win Rate & Game Duration Trend
      let cumWins = 0;
      const cumWrData = [];
      const durData = [];
      const labels4 = [];
      filteredMatches.forEach((m, i) => {
        if (m.result === 'WIN') cumWins += 1;
        cumWrData.push(+((cumWins / (i + 1)) * 100).toFixed(1));
        durData.push(parseFloat(m.duration_min || 30));
        labels4.push(`G${i + 1}`);
      });

      const ctx4 = document.getElementById('chart-tempo-trend');
      if (ctx4) {
        chartInstances.c4 = new Chart(ctx4, {
          type: 'line',
          data: {
            labels: labels4,
            datasets: [
              {
                label: 'Cumulative Win Rate (%)',
                data: cumWrData,
                borderColor: '#c8aa6e',
                backgroundColor: 'rgba(200, 170, 110, 0.15)',
                fill: true,
                tension: 0.3
              },
              {
                label: 'Match Duration (min)',
                data: durData,
                borderColor: '#0ac8b9',
                borderDash: [5, 5],
                tension: 0.3
              }
            ]
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
              x: { ticks: { color: '#94a3b8' }, grid: { color: 'rgba(255,255,255,0.05)' } },
              y: { min: 0, max: 100, ticks: { color: '#94a3b8' }, grid: { color: 'rgba(255,255,255,0.06)' } }
            },
            plugins: { legend: { labels: { color: '#e8e4dc' } } }
          }
        });
      }
    }

    // --- TAB 6: FAQ SIMULATOR & GITHUB FEEDBACK BUILDER ---
    function updateWeightSimulator() {
      const role = document.getElementById('sim-role').value;
      const arch = document.getElementById('sim-arch').value;
      const formulas = RAW_BUNDLE.rating_formulas || {};
      const rw = (formulas.role_weights || {})[role] || {};
      const aw = (formulas.archetype_weights || {})[arch] || {};
      const dpm = (formulas.dpm_benchmarks || {})[arch] || 600;
      const cspm = (formulas.cspm_benchmarks || {})[role] || 6.5;
      const vspm = (formulas.vspm_benchmarks || {})[role] || 0.85;

      const pillars = [
        ['combat', '⚔️ Combat & KDA'],
        ['damage', '🔥 Damage Output'],
        ['objective', '🐉 Objective Pressure'],
        ['frontline', '🛡️ Frontline & Durability'],
        ['utility', '✨ Utility & Enablement'],
        ['macro_vision', '👁️ Vision & Economy']
      ];

      const bars = pillars.map(([k, label]) => {
        const rVal = rw[k] || 0;
        const aVal = aw[k] || 0;
        const blended = ((rVal * 0.55 + aVal * 0.45) * 100).toFixed(1);
        return `
          <div class="pillar-row">
            <span style="color: var(--gold-bright); font-weight: 600;">${label}</span>
            <div class="progress-bar" style="height: 10px;">
              <div class="progress-fill" style="width: ${Math.min(100, parseFloat(blended) * 2.2)}%;"></div>
            </div>
            <strong style="text-align: right; color: var(--cyan-bright);">${blended}%</strong>
          </div>
        `;
      }).join('');

      document.getElementById('sim-weights-output').innerHTML = `
        <div style="margin-bottom: 0.65rem; font-size: 0.82rem; color: var(--text-muted);">
          Target Benchmarks for <strong style="color: var(--gold-bright);">${escapeHtml(role)} + ${escapeHtml(arch.toUpperCase())}</strong>:
          DPM Target: <code>${dpm}/min</code> • CS Target: <code>${cspm}/min</code> • Vision Target: <code>${vspm}/min</code>
        </div>
        ${bars}
      `;
    }

    function updateFeedbackPreview() {
      const repo = RAW_BUNDLE.github_repo || 'jgdclima/5-stacker-lol';
      const cat = document.getElementById('fb-category').value;
      const rawTitle = document.getElementById('fb-title').value.trim() || 'Dashboard / Bot Suggestion';
      const reporter = document.getElementById('fb-reporter').value.trim() || 'Web Dashboard User';
      const desc = document.getElementById('fb-desc').value.trim() || 'Describe your feedback or issue here...';

      const catMeta = {
        bug: { prefix: '[Bug]', display: 'Bug Report', label: 'bug' },
        feature: { prefix: '[Feature]', display: 'Feature Request', label: 'enhancement' },
        ux: { prefix: '[UX]', display: 'UX / Channel Feedback', label: 'enhancement' }
      }[cat] || { prefix: '[Feature]', display: 'Feature Request', label: 'enhancement' };

      const fullTitle = rawTitle.toLowerCase().startsWith(catMeta.prefix.toLowerCase())
        ? rawTitle
        : `${catMeta.prefix} ${rawTitle}`;

      const body = [
        `### ${catMeta.display}`,
        ``,
        desc,
        ``,
        `---`,
        `#### Metadata`,
        `- **Submitted by**: \`${reporter}\``,
        `- **Category**: ${catMeta.display}`,
        `- **Source**: 5-Stack Coordinator Interactive Web Dashboard`
      ].join('\n');

      document.getElementById('fb-markdown-preview').textContent = `Title: ${fullTitle}\nLabel: ${catMeta.label}\n\n${body}`;

      const issueUrl = `https://github.com/${repo}/issues/new?title=${encodeURIComponent(fullTitle)}&body=${encodeURIComponent(body)}&labels=${encodeURIComponent(catMeta.label)}`;
      document.getElementById('fb-submit-link').href = issueUrl;
      document.getElementById('fb-view-issues-link').href = `https://github.com/${repo}/issues`;
      document.getElementById('faq-repo-link').href = `https://github.com/${repo}/issues`;
    }

    window.addEventListener('DOMContentLoaded', initDashboard);
  </script>
</body>
</html>
"""


def generate_dashboard(
    stats_mgr: Optional[StatsManager] = None,
    output_path: str = DEFAULT_OUTPUT_PATH,
    data_path: str = DEFAULT_DATA_PATH,
) -> str:
    """
    Generates the self-contained `web/index.html` dashboard with embedded JSON data.
    Returns the absolute path of the generated HTML file.
    """
    payload = build_dashboard_payload(stats_mgr=stats_mgr, filepath=data_path)
    # Escape `</script>` inside JSON to prevent premature script tag termination
    json_str = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    html_content = DASHBOARD_HTML_TEMPLATE.replace("__DASHBOARD_JSON_PAYLOAD__", json_str)

    out_dir = os.path.dirname(output_path)
    if out_dir and not os.path.exists(out_dir):
        os.makedirs(out_dir, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    return os.path.abspath(output_path)


def serve_dashboard(output_path: str = DEFAULT_OUTPUT_PATH, port: int = 8080):
    """Starts a lightweight HTTP server serving the generated directory."""
    abs_path = os.path.abspath(output_path)
    serve_dir = os.path.dirname(abs_path) or "."
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=serve_dir)

    class ReusableTCPServer(socketserver.TCPServer):
        allow_reuse_address = True

    with ReusableTCPServer(("0.0.0.0", port), handler) as httpd:
        print(f"[Dashboard] Serving {abs_path} at http://localhost:{port}")
        httpd.serve_forever()


def main():
    parser = argparse.ArgumentParser(description="Generate static Hextech dashboard for 5-Stack Coordinator.")
    parser.add_argument("--data", default=DEFAULT_DATA_PATH, help="Path to league_stats.json")
    parser.add_argument("--output", default=DEFAULT_OUTPUT_PATH, help="Output HTML file path (default: web/index.html)")
    parser.add_argument("--serve", nargs="?", const=8080, type=int, help="Optionally serve the dashboard on the given port (default: 8080)")
    args = parser.parse_args()

    out_file = generate_dashboard(output_path=args.output, data_path=args.data)
    print(f"[Dashboard] Generated static dashboard -> {out_file}")

    if args.serve:
        serve_dashboard(output_path=args.output, port=args.serve)


if __name__ == "__main__":
    main()
