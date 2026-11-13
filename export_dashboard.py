"""
Interactive Web Dashboard Data Exporter & GitHub Pages Sync for 5-Stack Coordinator.

Exports decoupled, privacy-sanitized JSON payloads (`web/data/live_payload.json` and
`web/data/demo_payload.json`) plus a zero-CORS fallback bundle (`web/data/dashboard_bundle.js`)
consumed by the modular ES frontend in `web/`. Also supports pushing sanitized live match
telemetry directly to the `gh-pages` branch via the GitHub Contents API.
"""

import argparse
import asyncio
import base64
import copy
import functools
import http.server
import json
import os
import socketserver
from datetime import datetime
from typing import Any, Dict, List, Optional

import aiohttp

from data_manager import (
    DEFAULT_DATA_PATH,
    DEFAULT_GROUP_NAME,
    LEGACY_DEMO_GROUP_NAME,
    StatsManager,
)
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

DEFAULT_WEB_DIR = "web"
DEFAULT_DATA_DIR = os.path.join(DEFAULT_WEB_DIR, "data")
DEFAULT_OUTPUT_PATH = os.path.join(DEFAULT_WEB_DIR, "index.html")
DEFAULT_GITHUB_REPO = "jgdclima/5-stacker-lol"
DEFAULT_GH_PAGES_BRANCH = "gh-pages"
DEFAULT_GH_PAGES_LIVE_PATH = "data/live_payload.json"
STANDARD_ROLES = ("Top", "Jungle", "Mid", "Bot", "Support")


def _infer_ranked_roles(
    roles_played: Dict[str, int],
    role_perf: Optional[Dict[str, Dict[str, float]]] = None,
) -> List[str]:
    """Ranks standard Summoner's Rift roles played by volume, then win rate and rating."""
    perf = role_perf or {}
    candidates = [r for r in STANDARD_ROLES if (roles_played.get(r) or 0) > 0]
    candidates.sort(
        key=lambda r: (
            -(roles_played.get(r) or 0),
            -((perf.get(r, {}).get("wins", 0)) / max(1, perf.get(r, {}).get("games", roles_played.get(r, 1)))),
            -((perf.get(r, {}).get("rating_sum", 0.0)) / max(1, perf.get(r, {}).get("games", roles_played.get(r, 1)))),
            STANDARD_ROLES.index(r),
        )
    )
    return candidates


def _build_demo_dataset() -> Dict[str, Any]:
    """
    Constructs a rich, realistic demonstration dataset for 'The Summoner's Ten'
    so the dashboard can be explored interactively even before live matches are logged
    or whenever the user toggles 'Demo Data Mode' in the UI.
    """
    temp_mgr = StatsManager(filepath=":memory_demo:")
    # Prevent writing to disk for demo state
    temp_mgr.save = lambda: None  # type: ignore

    temp_mgr.data["group_name"] = LEGACY_DEMO_GROUP_NAME
    temp_mgr.data["members"] = [
        {"id": "1", "name": "João", "discord_tag": "Joao#1234", "primary_role": "Bot", "secondary_role": "Mid", "fav_champs": ["Jinx", "Kai'Sa", "Jhin"]},
        {"id": "2", "name": "Melanie", "discord_tag": "Melanie#5678", "primary_role": "Support", "secondary_role": "Top", "fav_champs": ["Nami", "Leona", "Lulu"]},
        {"id": "3", "name": "Marcus", "discord_tag": "Marcus#9012", "primary_role": "Jungle", "secondary_role": "Top", "fav_champs": ["Vi", "Jarvan IV", "Sejuani"]},
        {"id": "4", "name": "Elena", "discord_tag": "Elena#3456", "primary_role": "Mid", "secondary_role": "Support", "fav_champs": ["Ahri", "Orianna", "Syndra"]},
        {"id": "5", "name": "David", "discord_tag": "David#7890", "primary_role": "Top", "secondary_role": "Jungle", "fav_champs": ["Ornn", "Aatrox", "Shen"]},
        {"id": "6", "name": "Sarah", "discord_tag": "Sarah#2345", "primary_role": "Support", "secondary_role": "Mid", "fav_champs": ["Thresh", "Nautilus", "Rakan"]},
        {"id": "7", "name": "Leo", "discord_tag": "Leo#6789", "primary_role": "Bot", "secondary_role": "Top", "fav_champs": ["Ezreal", "Ashe", "Varus"]},
        {"id": "8", "name": "Chloe", "discord_tag": "Chloe#0123", "primary_role": "Mid", "secondary_role": "Bot", "fav_champs": ["Viktor", "Sylas", "Hwei"]},
        {"id": "9", "name": "Alex", "discord_tag": "Alex#4567", "primary_role": "Jungle", "secondary_role": "Support", "fav_champs": ["Xin Zhao", "Amumu", "Zac"]},
        {"id": "10", "name": "Sam", "discord_tag": "Sam#8901", "primary_role": "Top", "secondary_role": "Mid", "fav_champs": ["Gnar", "Jax", "Malphite"]},
    ]

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
    ref_names = None if is_demo else stats_mgr.get_referenced_player_names()

    def _make_player_profile(name: str, source: Optional[dict] = None) -> Dict[str, Any]:
        src = source or {}
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
            "main_role": src.get("primary_role", "Flex"),
        })
        return {
            "id": src.get("id", src.get("discord_id", "")),
            "name": name,
            "discord_tag": src.get("discord_tag", src.get("discord_name", "")),
            "primary_role": src.get("primary_role", lb.get("main_role", "Flex")),
            "secondary_role": src.get("secondary_role", "Fill"),
            "fav_champs": src.get("fav_champs", []),
            "accounts": StatsManager._extract_accounts(src),
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

    has_linked_roster = bool(raw_data.get("linked_players"))
    player_profiles: Dict[str, Dict[str, Any]] = {}
    for member in members:
        if not is_demo and stats_mgr.is_unlinked_legacy_demo_member(member, ref_names):
            continue
        if not is_demo and has_linked_roster and not member.get("discord_id") and not StatsManager._extract_accounts(member):
            continue
        name = member["name"]
        player_profiles[name] = _make_player_profile(name, member)

    for linked in raw_data.get("linked_players", {}).values():
        if not isinstance(linked, dict):
            continue
        name = (linked.get("name") or linked.get("discord_name") or "").strip()
        if name and name not in player_profiles:
            player_profiles[name] = _make_player_profile(name, linked)

    for lb_entry in leaderboard:
        name = lb_entry["name"]
        if lb_entry.get("games", 0) > 0 and name not in player_profiles:
            player_profiles[name] = _make_player_profile(name)

    # Aggregate champion trends, role stats, archetype stats, and per-player details
    champ_stats: Dict[str, Dict[str, Any]] = {}
    role_distribution: Dict[str, Dict[str, int]] = {
        r: {"games": 0, "wins": 0} for r in STANDARD_ROLES
    }
    archetype_stats: Dict[str, Dict[str, Any]] = {}
    player_role_perf: Dict[str, Dict[str, Dict[str, float]]] = {}

    for match in enriched_matches:
        is_win = match.get("result") == "WIN"
        dur = float(match.get("duration_min") or 30.0)
        mode = match.get("mode", "Match")
        lineup = match.get("lineup", {})

        for role, pdata in lineup.items():
            if not isinstance(pdata, dict):
                continue
            if not stats_mgr.is_lolers_member_entry(pdata, m_copy):
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

            # Champion aggregation (split by champion + role played)
            champ_role_key = (champ, role)
            if champ_role_key not in champ_stats:
                champ_stats[champ_role_key] = {
                    "champion": champ,
                    "role": role,
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
            cs_entry = champ_stats[champ_role_key]
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
                rp = player_role_perf.setdefault(pname, {}).setdefault(
                    role, {"games": 0, "wins": 0, "rating_sum": 0.0}
                )
                rp["games"] += 1
                if is_win:
                    rp["wins"] += 1
                rp["rating_sum"] += rating
                for pil_k, pil_v in pillars.items():
                    prof["pillar_totals"][pil_k] = prof["pillar_totals"].get(pil_k, 0.0) + float(pil_v)
                    prof["pillar_counts"][pil_k] = prof["pillar_counts"].get(pil_k, 0) + 1

                if champ_role_key not in prof["champions"]:
                    prof["champions"][champ_role_key] = {
                        "champion": champ,
                        "role": role,
                        "archetype": arch,
                        "games": 0,
                        "wins": 0,
                        "kills": 0,
                        "deaths": 0,
                        "assists": 0,
                        "total_rating": 0.0,
                    }
                pc = prof["champions"][champ_role_key]
                pc["games"] += 1
                if is_win:
                    pc["wins"] += 1
                pc["kills"] += kills
                pc["deaths"] += deaths
                pc["assists"] += assists
                pc["total_rating"] += rating

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
        for (_cname, _crole), cdata in prof["champions"].items():
            g = cdata["games"]
            champ_list.append({
                "champion": cdata["champion"],
                "role": cdata["role"],
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
                "primary_role": cdata["role"],
            })
        prof["champion_pool"] = sorted(champ_list, key=lambda x: (x["games"], x["avg_rating"]), reverse=True)
        prof.pop("champions", None)

        ranked_roles = _infer_ranked_roles(prof["roles_played"], player_role_perf.get(name))
        if prof.get("primary_role") not in STANDARD_ROLES:
            if ranked_roles:
                prof["primary_role"] = ranked_roles[0]
            elif prof.get("main_role") in STANDARD_ROLES:
                prof["primary_role"] = prof["main_role"]
            else:
                prof["primary_role"] = "Flex"
        if prof.get("main_role") not in STANDARD_ROLES and prof["primary_role"] in STANDARD_ROLES:
            prof["main_role"] = prof["primary_role"]
        if prof.get("secondary_role") not in STANDARD_ROLES or prof.get("secondary_role") == prof["primary_role"]:
            alt_role = next((r for r in ranked_roles if r != prof["primary_role"]), None)
            if alt_role:
                prof["secondary_role"] = alt_role
            elif prof["primary_role"] in STANDARD_ROLES:
                prof["secondary_role"] = "Fill"

        final_players.append(prof)

    final_players.sort(key=lambda x: (x["avg_rating"], x["win_rate"], x["games"]), reverse=True)

    # Finalize champion summary list
    champions_list: List[Dict[str, Any]] = []
    for (_cname, _crole), c in champ_stats.items():
        g = c["picks"]
        dur_total = max(1.0, c["duration_min"])
        avg_r = round(c["total_rating"] / g, 1) if g > 0 else 0.0
        champions_list.append({
            "champion": c["champion"],
            "role": c["role"],
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
            "primary_role": c["role"],
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

    group_name = raw_data.get("group_name") or DEFAULT_GROUP_NAME
    if not is_demo and group_name == LEGACY_DEMO_GROUP_NAME:
        group_name = DEFAULT_GROUP_NAME

    return {
        "is_demo": is_demo,
        "group_name": group_name,
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


def sanitize_live_payload(live_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Strips sensitive Discord snowflake IDs and Riot PUUIDs from `live` dashboard data
    while preserving player display names, Riot GameNames, match stats, and session history.
    """
    sanitized = copy.deepcopy(live_data)

    for player in sanitized.get("players", []):
        if not isinstance(player, dict):
            continue
        player["id"] = ""
        player.pop("discord_id", None)
        cleaned_accounts = []
        for acct in player.get("accounts", []):
            if not isinstance(acct, dict):
                continue
            acct_copy = dict(acct)
            acct_copy.pop("puuid", None)
            cleaned_accounts.append(acct_copy)
        player["accounts"] = cleaned_accounts

    for session in sanitized.get("sessions", []):
        if not isinstance(session, dict):
            continue
        for sensitive_key in ("creator_id", "channel_id", "message_id", "thread_id"):
            session.pop(sensitive_key, None)

    for match in sanitized.get("matches", []):
        if not isinstance(match, dict):
            continue
        match.pop("puuid", None)
        for pdata in match.get("lineup", {}).values():
            if isinstance(pdata, dict):
                pdata.pop("puuid", None)

    return sanitized


def build_dashboard_payload(stats_mgr: Optional[StatsManager] = None, filepath: str = DEFAULT_DATA_PATH) -> Dict[str, Any]:
    """
    Builds the complete JSON payload containing both:
    - `live`: Privacy-sanitized live data from `data/league_stats.json`
    - `demo`: Rich demonstration data for interactive previewing
    - `rating_formulas`: Rating engine benchmarks, weights, and GitHub feedback configuration
    """
    mgr = stats_mgr or StatsManager(filepath=filepath)
    raw_live = _compile_payload_from_manager(mgr, is_demo=False)
    live_payload = sanitize_live_payload(raw_live)
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


def build_live_payload_document(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Extracts the standalone `live_payload.json` document from a full dashboard payload."""
    return {
        "generated_at": payload["generated_at"],
        "github_repo": payload["github_repo"],
        "has_live_matches": payload["has_live_matches"],
        "rating_formulas": payload["rating_formulas"],
        "dataset": payload["live"],
    }


def build_demo_payload_document(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Extracts the standalone `demo_payload.json` document from a full dashboard payload."""
    return {
        "generated_at": payload["generated_at"],
        "github_repo": payload["github_repo"],
        "rating_formulas": payload["rating_formulas"],
        "dataset": payload["demo"],
    }


def export_dashboard_data(
    stats_mgr: Optional[StatsManager] = None,
    data_dir: str = DEFAULT_DATA_DIR,
    data_path: str = DEFAULT_DATA_PATH,
) -> Dict[str, Any]:
    """
    Writes decoupled JSON payloads (`live_payload.json`, `demo_payload.json`) and
    zero-CORS fallback JS bundle (`dashboard_bundle.js`) into `data_dir`.
    """
    payload = build_dashboard_payload(stats_mgr=stats_mgr, filepath=data_path)
    os.makedirs(data_dir, exist_ok=True)

    live_path = os.path.join(data_dir, "live_payload.json")
    demo_path = os.path.join(data_dir, "demo_payload.json")
    bundle_path = os.path.join(data_dir, "dashboard_bundle.js")

    live_doc = build_live_payload_document(payload)
    demo_doc = build_demo_payload_document(payload)

    with open(live_path, "w", encoding="utf-8") as f:
        json.dump(live_doc, f, indent=2, ensure_ascii=False)
        f.write("\n")

    with open(demo_path, "w", encoding="utf-8") as f:
        json.dump(demo_doc, f, indent=2, ensure_ascii=False)
        f.write("\n")

    bundle_json = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    with open(bundle_path, "w", encoding="utf-8") as f:
        f.write(f"window.__DASHBOARD_BUNDLE__ = {bundle_json};\n")

    return {
        "payload": payload,
        "live_path": os.path.abspath(live_path),
        "demo_path": os.path.abspath(demo_path),
        "bundle_path": os.path.abspath(bundle_path),
    }


def generate_dashboard(
    stats_mgr: Optional[StatsManager] = None,
    output_path: str = DEFAULT_OUTPUT_PATH,
    data_path: str = DEFAULT_DATA_PATH,
    data_dir: Optional[str] = None,
) -> str:
    """
    Synchronizes dashboard JSON/JS payloads without overwriting the authored modular
    frontend (`web/index.html`). When called with a custom non-default `output_path`
    (e.g., standalone test artifact), writes a self-contained HTML copy with embedded JSON.
    """
    is_default_output = os.path.normpath(output_path) == os.path.normpath(DEFAULT_OUTPUT_PATH)

    if is_default_output:
        target_data_dir = data_dir or DEFAULT_DATA_DIR
        export_dashboard_data(stats_mgr=stats_mgr, data_dir=target_data_dir, data_path=data_path)
        return os.path.abspath(output_path)

    payload = build_dashboard_payload(stats_mgr=stats_mgr, filepath=data_path)
    if data_dir:
        export_dashboard_data(stats_mgr=stats_mgr, data_dir=data_dir, data_path=data_path)

    template_path = DEFAULT_OUTPUT_PATH
    if os.path.exists(template_path):
        with open(template_path, "r", encoding="utf-8") as f:
            html_template = f.read()
    else:
        html_template = "<!DOCTYPE html><html><body></body></html>"

    json_str = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    payload_tag = f'  <script id="dashboard-data" type="application/json">{json_str}</script>\n</body>'
    if "</body>" in html_template:
        html_content = html_template.replace("</body>", payload_tag, 1)
    else:
        html_content = html_template + payload_tag

    out_dir = os.path.dirname(output_path)
    if out_dir and not os.path.exists(out_dir):
        os.makedirs(out_dir, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    return os.path.abspath(output_path)


async def sync_live_payload_to_github_pages(
    stats_mgr: Optional[StatsManager] = None,
    repo: Optional[str] = None,
    token: Optional[str] = None,
    branch: str = DEFAULT_GH_PAGES_BRANCH,
    target_path: str = DEFAULT_GH_PAGES_LIVE_PATH,
    data_path: str = DEFAULT_DATA_PATH,
) -> Dict[str, Any]:
    """
    Pushes the privacy-sanitized `live_payload.json` directly to the `gh-pages` branch
    via the GitHub Contents API so GitHub Pages stays synced with NAS match records.
    """
    target_repo = (repo or os.getenv("GITHUB_REPO") or DEFAULT_GITHUB_REPO).strip()
    auth_token = (token if token is not None else os.getenv("GITHUB_TOKEN", "")).strip()

    if not auth_token:
        return {
            "success": False,
            "skipped": True,
            "reason": "GITHUB_TOKEN not configured",
            "url": None,
        }

    payload = build_dashboard_payload(stats_mgr=stats_mgr, filepath=data_path)
    live_doc = build_live_payload_document(payload)
    total_matches = live_doc["dataset"]["kpis"]["total_matches"]
    live_json_str = json.dumps(live_doc, indent=2, ensure_ascii=False) + "\n"
    b64_content = base64.b64encode(live_json_str.encode("utf-8")).decode("ascii")

    api_url = f"https://api.github.com/repos/{target_repo}/contents/{target_path}"
    headers = {
        "Authorization": f"Bearer {auth_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "5-Stack-Coordinator-Dashboard-Sync",
    }

    try:
        async with aiohttp.ClientSession() as session:
            existing_sha = None
            async with session.get(api_url, headers=headers, params={"ref": branch}, timeout=15) as get_resp:
                if get_resp.status == 200:
                    existing_json = await get_resp.json()
                    existing_sha = existing_json.get("sha")
                    raw_b64 = existing_json.get("content", "")
                    if raw_b64:
                        try:
                            decoded = base64.b64decode(raw_b64).decode("utf-8")
                            existing_doc = json.loads(decoded)
                            if existing_doc.get("dataset") == live_doc["dataset"]:
                                return {
                                    "success": True,
                                    "skipped": False,
                                    "unchanged": True,
                                    "url": existing_json.get("html_url"),
                                    "matches": total_matches,
                                }
                        except Exception:
                            pass
                elif get_resp.status not in (404,):
                    err_txt = await get_resp.text()
                    return {
                        "success": False,
                        "skipped": False,
                        "error": f"GitHub GET HTTP {get_resp.status}: {err_txt[:200]}",
                    }

            put_body: Dict[str, Any] = {
                "message": f"chore(data): sync sanitized live match stats ({total_matches} matches)",
                "content": b64_content,
                "branch": branch,
            }
            if existing_sha:
                put_body["sha"] = existing_sha

            async with session.put(api_url, headers=headers, json=put_body, timeout=20) as put_resp:
                if put_resp.status in (200, 201):
                    resp_data = await put_resp.json()
                    return {
                        "success": True,
                        "skipped": False,
                        "unchanged": False,
                        "url": resp_data.get("content", {}).get("html_url"),
                        "matches": total_matches,
                    }
                err_txt = await put_resp.text()
                return {
                    "success": False,
                    "skipped": False,
                    "error": f"GitHub PUT HTTP {put_resp.status}: {err_txt[:200]}",
                }
    except Exception as exc:
        return {
            "success": False,
            "skipped": False,
            "error": str(exc),
        }


def serve_dashboard(output_path: str = DEFAULT_OUTPUT_PATH, port: int = 8080):
    """Starts a lightweight HTTP server serving the `web/` directory."""
    abs_path = os.path.abspath(output_path)
    serve_dir = os.path.dirname(abs_path) or "."
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=serve_dir)

    class ReusableTCPServer(socketserver.TCPServer):
        allow_reuse_address = True

    with ReusableTCPServer(("0.0.0.0", port), handler) as httpd:
        print(f"[Dashboard] Serving {serve_dir} at http://localhost:{port}")
        httpd.serve_forever()


def main():
    parser = argparse.ArgumentParser(description="Export modular dashboard data for 5-Stack Coordinator.")
    parser.add_argument("--data", default=DEFAULT_DATA_PATH, help="Path to league_stats.json")
    parser.add_argument("--output", default=DEFAULT_OUTPUT_PATH, help="Dashboard entry path (default: web/index.html)")
    parser.add_argument("--serve", nargs="?", const=8080, type=int, help="Optionally serve web/ on the given port (default: 8080)")
    parser.add_argument("--push-gh-pages", action="store_true", help="Push sanitized live_payload.json to gh-pages branch")
    args = parser.parse_args()

    out_file = generate_dashboard(output_path=args.output, data_path=args.data)
    print(f"[Dashboard] Exported dashboard data payloads -> {out_file}")

    if args.push_gh_pages:
        res = asyncio.run(sync_live_payload_to_github_pages(data_path=args.data))
        if res.get("success"):
            status = "unchanged (skipped commit)" if res.get("unchanged") else f"pushed ({res.get('matches')} matches)"
            print(f"[Dashboard] GitHub Pages sync {status}: {res.get('url')}")
        elif res.get("skipped"):
            print(f"[Dashboard] GitHub Pages sync skipped: {res.get('reason')}")
        else:
            print(f"[Dashboard] GitHub Pages sync failed: {res.get('error')}")

    if args.serve:
        serve_dashboard(output_path=args.output, port=args.serve)


if __name__ == "__main__":
    main()
