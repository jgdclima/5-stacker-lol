"""
Holistic, Role- and Champion-Focused Performance & Synergy Rating Engine.

Replaces raw KDA/KP heuristics with a multi-pillar evaluation model tailored to:
1. Role Responsibilities (Top, Jungle, Mid, Bot/ADC, Support)
2. Champion Kit Archetypes (Marksman, Control/Artillery Mage, Assassin/Diver,
   Splitpusher/Skirmisher, Bruiser/Juggernaut, Vanguard/Warden Tank, Enchanter,
   Engage/Catcher) + dynamic stat-signature adaptation for flex/new champions.
3. Position-Specific Pairwise Synergy (Botlane, Mid+Jungle, Top+Jungle, Support+Jungle).
"""

import re
from typing import Dict, Any, List, Optional, Tuple


# --- 1. Champion Archetype Taxonomy ---
# Normalized lowercase alphanumeric champion names mapped to primary kit archetype.
CHAMPION_ARCHETYPE_MAP: Dict[str, str] = {
    # Marksmen / Hypercarries
    "aphelios": "marksman",
    "ashe": "marksman",
    "caitlyn": "marksman",
    "Corki": "marksman",
    "corki": "marksman",
    "draven": "marksman",
    "ezreal": "marksman",
    "jhin": "marksman",
    "jinx": "marksman",
    "kaisa": "marksman",
    "kalista": "marksman",
    "kindred": "marksman",
    "kogmaw": "marksman",
    "lucian": "marksman",
    "missfortune": "marksman",
    "nilah": "marksman",
    "samira": "marksman",
    "senna": "marksman",
    "sivir": "marksman",
    "smolder": "marksman",
    "tristana": "marksman",
    "twitch": "marksman",
    "varus": "marksman",
    "vayne": "marksman",
    "xayah": "marksman",
    "yunara": "marksman",
    "zeri": "marksman",

    # Control / Artillery / Burst Mages
    "anivia": "mage",
    "annie": "mage",
    "aurelionsol": "mage",
    "azir": "mage",
    "brand": "mage",
    "cassiopeia": "mage",
    "fiddlesticks": "mage",
    "heimerdinger": "mage",
    "hwei": "mage",
    "karthus": "mage",
    "lissandra": "mage",
    "lux": "mage",
    "malzahar": "mage",
    "mel": "mage",
    "morgana": "mage",
    "neeko": "mage",
    "orianna": "mage",
    "ryze": "mage",
    "swain": "mage",
    "syndra": "mage",
    "taliyah": "mage",
    "twistedfate": "mage",
    "veigar": "mage",
    "velkoz": "mage",
    "vex": "mage",
    "viktor": "mage",
    "vladimir": "mage",
    "xerath": "mage",
    "ziggs": "mage",
    "zoe": "mage",
    "zyra": "mage",

    # Assassins / Burst Divers / Skirmish Divers
    "ahri": "assassin",
    "akali": "assassin",
    "akshan": "assassin",
    "aurora": "assassin",
    "diana": "assassin",
    "ekko": "assassin",
    "elise": "assassin",
    "evelynn": "assassin",
    "fizz": "assassin",
    "kassadin": "assassin",
    "katarina": "assassin",
    "KAYN": "assassin",
    "kayn": "assassin",
    "khazix": "assassin",
    "leblanc": "assassin",
    "locke": "assassin",
    "masteryi": "assassin",
    "naafiri": "assassin",
    "nidalee": "assassin",
    "nocturne": "assassin",
    "pantheon": "assassin",
    "pyke": "assassin",
    "qiyana": "assassin",
    "rengar": "assassin",
    "shaco": "assassin",
    "sylas": "assassin",
    "talon": "assassin",
    "viego": "assassin",
    "yasuo": "assassin",
    "yone": "assassin",
    "zed": "assassin",

    # Splitpushers / Duelists
    "camille": "splitpusher",
    "fiora": "splitpusher",
    "gangplank": "splitpusher",
    "gwen": "splitpusher",
    "illaoi": "splitpusher",
    "irelia": "splitpusher",
    "jax": "splitpusher",
    "kayle": "splitpusher",
    "nasus": "splitpusher",
    "quinn": "splitpusher",
    "riven": "splitpusher",
    "teemo": "splitpusher",
    "trundle": "splitpusher",
    "tryndamere": "splitpusher",
    "yorick": "splitpusher",

    # Bruisers / Juggernauts / Divers
    "aatrox": "bruiser",
    "ambessa": "bruiser",
    "belveth": "bruiser",
    "briar": "bruiser",
    "darius": "bruiser",
    "drmundo": "bruiser",
    "garen": "bruiser",
    "gnar": "bruiser",
    "gragas": "bruiser",
    "hecarim": "bruiser",
    "jarvaniv": "bruiser",
    "jayce": "bruiser",
    "kled": "bruiser",
    "leesin": "bruiser",
    "lillia": "bruiser",
    "monkeyking": "bruiser",
    "wukong": "bruiser",
    "mordekaiser": "bruiser",
    "olaf": "bruiser",
    "reksai": "bruiser",
    "renekton": "bruiser",
    "rumble": "bruiser",
    "sett": "bruiser",
    "shyvana": "bruiser",
    "singed": "bruiser",
    "udyr": "bruiser",
    "urgot": "bruiser",
    "vi": "bruiser",
    "volibear": "bruiser",
    "warwick": "bruiser",
    "xinzhao": "bruiser",

    # Vanguards / Warden Tanks
    "amumu": "tank",
    "chogath": "tank",
    "galio": "tank",
    "ksante": "tank",
    "malphite": "tank",
    "maokai": "tank",
    "nunu": "tank",
    "ornn": "tank",
    "poppy": "tank",
    "rammus": "tank",
    "sejuani": "tank",
    "shen": "tank",
    "sion": "tank",
    "skarner": "tank",
    "tahmkench": "tank",
    "zac": "tank",

    # Enchanters
    "ivern": "enchanter",
    "janna": "enchanter",
    "karma": "enchanter",
    "lulu": "enchanter",
    "milio": "enchanter",
    "nami": "enchanter",
    "renata": "enchanter",
    "seraphine": "enchanter",
    "sona": "enchanter",
    "soraka": "enchanter",
    "taric": "enchanter",
    "yuumi": "enchanter",
    "zilean": "enchanter",

    # Engage / Catchers
    "alistar": "catcher",
    "bard": "catcher",
    "blitzcrank": "catcher",
    "braum": "catcher",
    "leona": "catcher",
    "nautilus": "catcher",
    "rakan": "catcher",
    "rell": "catcher",
    "thresh": "catcher",
}

ROLE_DEFAULT_ARCHETYPE: Dict[str, str] = {
    "Top": "bruiser",
    "Jungle": "bruiser",
    "Mid": "mage",
    "Bot": "marksman",
    "Support": "catcher",
}

# 6 Core Pillars: combat, damage, objective, frontline, utility, macro_vision
ROLE_PILLAR_WEIGHTS: Dict[str, Dict[str, float]] = {
    "Top": {
        "combat": 0.22,
        "damage": 0.20,
        "objective": 0.20,
        "frontline": 0.22,
        "utility": 0.08,
        "macro_vision": 0.08,
    },
    "Jungle": {
        "combat": 0.22,
        "damage": 0.14,
        "objective": 0.30,
        "frontline": 0.12,
        "utility": 0.12,
        "macro_vision": 0.10,
    },
    "Mid": {
        "combat": 0.26,
        "damage": 0.32,
        "objective": 0.12,
        "frontline": 0.06,
        "utility": 0.12,
        "macro_vision": 0.12,
    },
    "Bot": {
        "combat": 0.26,
        "damage": 0.36,
        "objective": 0.14,
        "frontline": 0.04,
        "utility": 0.06,
        "macro_vision": 0.14,
    },
    "Support": {
        "combat": 0.20,
        "damage": 0.08,
        "objective": 0.08,
        "frontline": 0.12,
        "utility": 0.28,
        "macro_vision": 0.24,
    },
}

ARCHETYPE_PILLAR_WEIGHTS: Dict[str, Dict[str, float]] = {
    "marksman": {
        "combat": 0.26,
        "damage": 0.38,
        "objective": 0.14,
        "frontline": 0.02,
        "utility": 0.04,
        "macro_vision": 0.16,
    },
    "mage": {
        "combat": 0.24,
        "damage": 0.36,
        "objective": 0.10,
        "frontline": 0.04,
        "utility": 0.14,
        "macro_vision": 0.12,
    },
    "assassin": {
        "combat": 0.35,
        "damage": 0.32,
        "objective": 0.11,
        "frontline": 0.05,
        "utility": 0.07,
        "macro_vision": 0.10,
    },
    "splitpusher": {
        "combat": 0.20,
        "damage": 0.20,
        "objective": 0.30,
        "frontline": 0.12,
        "utility": 0.04,
        "macro_vision": 0.14,
    },
    "bruiser": {
        "combat": 0.25,
        "damage": 0.23,
        "objective": 0.18,
        "frontline": 0.20,
        "utility": 0.07,
        "macro_vision": 0.07,
    },
    "tank": {
        "combat": 0.18,
        "damage": 0.10,
        "objective": 0.14,
        "frontline": 0.32,
        "utility": 0.18,
        "macro_vision": 0.08,
    },
    "enchanter": {
        "combat": 0.20,
        "damage": 0.04,
        "objective": 0.06,
        "frontline": 0.06,
        "utility": 0.38,
        "macro_vision": 0.26,
    },
    "catcher": {
        "combat": 0.20,
        "damage": 0.06,
        "objective": 0.08,
        "frontline": 0.16,
        "utility": 0.28,
        "macro_vision": 0.22,
    },
}

# Expected Damage Per Minute (DPM) benchmark by archetype
ARCHETYPE_DPM_BENCHMARK: Dict[str, float] = {
    "marksman": 780.0,
    "mage": 760.0,
    "assassin": 680.0,
    "splitpusher": 650.0,
    "bruiser": 620.0,
    "tank": 440.0,
    "catcher": 300.0,
    "enchanter": 240.0,
}

# Expected CS Per Minute benchmark by role
ROLE_CSPM_BENCHMARK: Dict[str, float] = {
    "Top": 6.8,
    "Jungle": 5.8,
    "Mid": 7.0,
    "Bot": 7.2,
    "Support": 1.2,
}

# Expected Vision Score Per Minute benchmark by role
ROLE_VSPM_BENCHMARK: Dict[str, float] = {
    "Top": 0.75,
    "Jungle": 1.05,
    "Mid": 0.80,
    "Bot": 0.75,
    "Support": 2.10,
}


def normalize_champion_key(champion_name: str) -> str:
    """Normalizes a champion name (e.g. 'Kai\\'Sa' -> 'kaisa', 'Jarvan IV' -> 'jarvaniv')."""
    if not champion_name:
        return ""
    return re.sub(r"[^a-z0-9]", "", champion_name.lower())


def get_champion_archetype(champion_name: str, role: str = "Flex", pdata: Optional[dict] = None) -> str:
    """
    Resolves a champion's kit archetype, with dynamic stat-signature fallback
    for unknown/future champions or off-meta builds.
    """
    norm = normalize_champion_key(champion_name)
    archetype = CHAMPION_ARCHETYPE_MAP.get(norm)
    if archetype:
        return archetype

    # Dynamic inference from match stats if champion isn't in static registry
    if pdata:
        heal_shield = pdata.get("heal_shield", 0) or pdata.get("effective_heal_shield", 0)
        mitigated = pdata.get("damage_mitigated", 0)
        turret_dmg = pdata.get("turret_damage", 0)
        cc_score = pdata.get("cc_score", 0)
        if role == "Support" and heal_shield >= 4000:
            return "enchanter"
        if role == "Support" and cc_score >= 25:
            return "catcher"
        if turret_dmg >= 8000:
            return "splitpusher"
        if mitigated >= 25000 and pdata.get("damage", 0) < 20000:
            return "tank"

    return ROLE_DEFAULT_ARCHETYPE.get(role, "bruiser")


def _clamp(val: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, val))


def _ratio_score(val: float, target: float, max_mult: float = 1.6) -> float:
    """Maps a metric against its role/archetype benchmark onto a 0-100 scale."""
    if target <= 0:
        return 50.0
    ratio = val / target
    if ratio <= 1.0:
        return _clamp(ratio * 78.0)
    extra = (ratio - 1.0) / max(0.1, (max_mult - 1.0))
    return _clamp(78.0 + extra * 22.0)


def rating_to_grade(score: float) -> str:
    """Converts a 0-100 holistic rating into a readable letter tier."""
    if score >= 88.0:
        return "S+"
    if score >= 80.0:
        return "S"
    if score >= 73.0:
        return "A+"
    if score >= 65.0:
        return "A"
    if score >= 55.0:
        return "B"
    return "C"


def score_player_in_match(
    role: str,
    pdata: dict,
    match_context: Optional[dict] = None,
) -> Dict[str, Any]:
    """
    Computes a holistic 0-100 performance score for a single participant in a match,
    blending Role weights (55%) and Champion Archetype weights (45%).
    Gracefully adapts when historical or manual matches have only a subset of fields.
    """
    ctx = match_context or {}
    lineup = ctx.get("lineup", {})
    duration_min = float(ctx.get("duration_min") or pdata.get("duration_min") or 30.0)
    duration_min = max(10.0, duration_min)
    is_win = (ctx.get("result") == "WIN")

    champion = pdata.get("champion", "Unknown")
    archetype = get_champion_archetype(champion, role, pdata)

    kills = int(pdata.get("kills", 0))
    deaths = int(pdata.get("deaths", 0))
    assists = int(pdata.get("assists", 0))
    damage = int(pdata.get("damage", 0))
    cs = int(pdata.get("cs", 0))
    vision = int(pdata.get("vision", 0))

    # Team totals for relative share computation
    if lineup:
        team_kills = sum(int(p.get("kills", 0)) for p in lineup.values() if isinstance(p, dict))
        team_damage = sum(int(p.get("damage", 0)) for p in lineup.values() if isinstance(p, dict))
        team_taken = sum(int(p.get("damage_taken", 0)) for p in lineup.values() if isinstance(p, dict))
    else:
        team_kills = max(1, kills + assists)
        team_damage = max(1, damage * 4)
        team_taken = 0

    # --- Pillar 1: Combat & KDA Efficiency ---
    kda = (kills + assists) / max(1, deaths)
    kp = float(pdata.get("kill_participation") or ((kills + assists) / max(1, team_kills)))
    kp = min(1.0, kp)
    solo_kills = int(pdata.get("solo_kills", 0))
    outnumbered_kills = int(pdata.get("outnumbered_kills", 0))

    kda_sub = _ratio_score(kda, target=3.2, max_mult=2.5)
    kp_target = 0.58 if role in ("Jungle", "Support", "Mid") else 0.48
    kp_sub = _ratio_score(kp, target=kp_target, max_mult=1.45)
    survival_sub = _clamp(100.0 - (deaths / (duration_min / 5.0)) * 28.0, 20.0, 100.0)
    playmaking_bonus = min(14.0, solo_kills * 3.5 + outnumbered_kills * 4.5)

    # Carry kill-conversion bonus (carries getting high kill share)
    kill_share = kills / max(1, team_kills)
    carry_kill_bonus = min(8.0, kill_share * 20.0) if archetype in ("marksman", "assassin", "mage", "splitpusher", "bruiser") else 0.0

    combat_score = _clamp(
        (kda_sub * 0.44) + (kp_sub * 0.34) + (survival_sub * 0.22) + playmaking_bonus + carry_kill_bonus
    )

    # --- Pillar 2: Damage & Carry Output ---
    has_damage = damage > 0 or team_damage > 0
    if has_damage:
        dpm = damage / duration_min
        dpm_target = ARCHETYPE_DPM_BENCHMARK.get(archetype, 600.0)
        dpm_sub = _ratio_score(dpm, target=dpm_target, max_mult=1.7)

        dmg_share = float(pdata.get("team_damage_pct") or (damage / max(1, team_damage)))
        share_target = 0.24 if archetype in ("marksman", "mage", "assassin") else (0.18 if archetype in ("bruiser", "splitpusher") else 0.10)
        share_sub = _ratio_score(dmg_share, target=share_target, max_mult=1.6)
        damage_score = _clamp(dpm_sub * 0.60 + share_sub * 0.40)
    else:
        damage_score = -1.0  # Indicates pillar data not present in minimal record

    # --- Pillar 3: Objective & Structural Pressure ---
    turret_dmg = int(pdata.get("turret_damage", 0))
    obj_dmg = int(pdata.get("objective_damage", 0))
    turret_takedowns = int(pdata.get("turret_takedowns", 0))
    turret_plates = int(pdata.get("turret_plates", 0))
    dragons = int(pdata.get("dragon_takedowns", 0))
    barons = int(pdata.get("baron_takedowns", 0))
    heralds = int(pdata.get("rift_herald_takedowns", 0))
    grubs = int(pdata.get("void_monster_kills", 0))
    steals = int(pdata.get("objectives_stolen", 0))

    has_objectives = any(x > 0 for x in (turret_dmg, obj_dmg, turret_takedowns, dragons, barons, heralds, grubs, steals))
    if has_objectives:
        struct_pts = _ratio_score(
            turret_dmg + (turret_takedowns * 1500) + (turret_plates * 600),
            target=6500.0 if archetype == "splitpusher" else 3800.0,
            max_mult=2.0,
        )
        monster_pts = _ratio_score(
            obj_dmg + (dragons * 3500) + (barons * 5000) + (heralds * 3000) + (grubs * 1200) + (steals * 6000),
            target=18000.0 if role == "Jungle" else 6500.0,
            max_mult=1.9,
        )
        if role == "Jungle":
            objective_score = _clamp(monster_pts * 0.72 + struct_pts * 0.28)
        elif archetype == "splitpusher" or role == "Top":
            objective_score = _clamp(struct_pts * 0.72 + monster_pts * 0.28)
        else:
            objective_score = _clamp(struct_pts * 0.55 + monster_pts * 0.45)
    else:
        objective_score = -1.0

    # --- Pillar 4: Frontline & Durability ---
    dmg_taken = int(pdata.get("damage_taken", 0))
    dmg_mitigated = int(pdata.get("damage_mitigated", 0))
    taken_pct = float(pdata.get("damage_taken_pct") or (dmg_taken / max(1, team_taken) if team_taken > 0 else 0.0))

    has_frontline = (dmg_taken > 0 or dmg_mitigated > 0)
    if has_frontline:
        mit_per_min = dmg_mitigated / duration_min
        mit_target = 900.0 if archetype in ("tank", "bruiser", "catcher") else 450.0
        mit_sub = _ratio_score(mit_per_min, target=mit_target, max_mult=2.0)
        taken_sub = _ratio_score(taken_pct, target=0.24 if role in ("Top", "Jungle") else 0.16, max_mult=1.6)
        tank_efficiency = _ratio_score((dmg_taken + dmg_mitigated) / max(1, deaths), target=9500.0, max_mult=2.0)
        frontline_score = _clamp(mit_sub * 0.45 + taken_sub * 0.25 + tank_efficiency * 0.30)
    else:
        frontline_score = -1.0

    # --- Pillar 5: Utility, Crowd Control & Team Enablement ---
    cc_score = float(pdata.get("cc_score", 0))
    heal_shield = float(pdata.get("effective_heal_shield", 0) or pdata.get("heal_shield", 0))
    ally_saves = int(pdata.get("save_ally_from_death", 0))
    immob_kills = int(pdata.get("immobilize_and_kill_with_ally", 0))
    pick_kills = int(pdata.get("pick_kill_with_ally", 0))

    has_utility = any(x > 0 for x in (cc_score, heal_shield, ally_saves, immob_kills, pick_kills))
    if has_utility:
        cc_sub = _ratio_score(cc_score / duration_min, target=1.1 if archetype in ("catcher", "tank") else 0.65, max_mult=2.0)
        hs_sub = _ratio_score(heal_shield / duration_min, target=320.0 if archetype == "enchanter" else 90.0, max_mult=2.0)
        setup_sub = _ratio_score(immob_kills * 1.5 + pick_kills * 1.5 + ally_saves * 3.0 + assists * 0.5, target=14.0, max_mult=1.8)
        if archetype == "enchanter":
            utility_score = _clamp(hs_sub * 0.50 + setup_sub * 0.35 + cc_sub * 0.15)
        elif archetype in ("catcher", "tank"):
            utility_score = _clamp(cc_sub * 0.45 + setup_sub * 0.40 + hs_sub * 0.15)
        else:
            utility_score = _clamp(setup_sub * 0.50 + cc_sub * 0.35 + hs_sub * 0.15)
    elif role == "Support" or assists > 0:
        # Fallback utility estimation from assists & KP when detailed Riot fields are absent
        utility_score = _clamp(_ratio_score(assists / (duration_min / 10.0), target=4.5, max_mult=1.8) * 0.65 + kp_sub * 0.35)
    else:
        utility_score = -1.0

    # --- Pillar 6: Vision, Economy & Lane Dominance ---
    has_macro = (cs > 0 or vision > 0 or pdata.get("gold_earned", 0) > 0)
    if has_macro:
        cspm = cs / duration_min
        vspm = vision / duration_min
        cspm_sub = _ratio_score(cspm, target=ROLE_CSPM_BENCHMARK.get(role, 6.0), max_mult=1.45)
        vspm_sub = _ratio_score(vspm, target=ROLE_VSPM_BENCHMARK.get(role, 0.85), max_mult=1.65)

        lane_adv_bonus = 0.0
        if pdata.get("laning_gold_xp_advantage"):
            lane_adv_bonus += 6.0
        if float(pdata.get("max_cs_advantage", 0)) >= 25.0:
            lane_adv_bonus += 4.0
        if int(pdata.get("wards_killed", 0)) >= 5 or int(pdata.get("control_wards_placed", 0)) >= 3:
            lane_adv_bonus += 4.0

        if role == "Support":
            macro_vision_score = _clamp(vspm_sub * 0.85 + cspm_sub * 0.15 + lane_adv_bonus)
        else:
            macro_vision_score = _clamp(cspm_sub * 0.62 + vspm_sub * 0.38 + lane_adv_bonus)
    else:
        macro_vision_score = -1.0

    # --- Combine Pillars via 55% Role + 45% Champion Archetype Weights ---
    role_w = ROLE_PILLAR_WEIGHTS.get(role, ROLE_PILLAR_WEIGHTS["Mid"])
    arch_w = ARCHETYPE_PILLAR_WEIGHTS.get(archetype, ARCHETYPE_PILLAR_WEIGHTS["bruiser"])

    raw_pillars = {
        "combat": combat_score,
        "damage": damage_score,
        "objective": objective_score,
        "frontline": frontline_score,
        "utility": utility_score,
        "macro_vision": macro_vision_score,
    }

    weighted_sum = 0.0
    active_weight_total = 0.0
    active_pillars = {}

    for p_name, p_val in raw_pillars.items():
        if p_val < 0:
            continue
        blended_w = (role_w.get(p_name, 0.15) * 0.55) + (arch_w.get(p_name, 0.15) * 0.45)
        weighted_sum += p_val * blended_w
        active_weight_total += blended_w
        active_pillars[p_name] = round(p_val, 1)

    base_score = (weighted_sum / active_weight_total) if active_weight_total > 0 else combat_score

    # Excess-death liability penalty (especially punishing for carries & high death frequency)
    deaths_per_10m = deaths / (duration_min / 10.0)
    death_penalty = 0.0
    if deaths_per_10m > 2.0:
        excess_rate = deaths_per_10m - 2.0
        mult = 6.5 if archetype in ("marksman", "mage", "assassin") else 4.5
        death_penalty = min(14.0, excess_rate * mult)

    outcome_adj = 2.5 if is_win else -1.5
    final_score = round(_clamp(base_score - death_penalty + outcome_adj, 15.0, 99.5), 1)

    # Determine standout badge
    highlight = _determine_player_highlight(role, archetype, pdata, active_pillars, kda, kp)

    return {
        "rating": final_score,
        "grade": rating_to_grade(final_score),
        "archetype": archetype,
        "highlight": highlight,
        "pillars": active_pillars,
    }


def _determine_player_highlight(
    role: str,
    archetype: str,
    pdata: dict,
    pillars: Dict[str, float],
    kda: float,
    kp: float,
) -> str:
    if int(pdata.get("turret_takedowns", 0)) >= 4 or int(pdata.get("turret_damage", 0)) >= 10000:
        return "Splitpush Titan"
    if int(pdata.get("dragon_takedowns", 0)) + int(pdata.get("baron_takedowns", 0)) >= 3:
        return "Objective Commander"
    if float(pdata.get("effective_heal_shield", 0) or pdata.get("heal_shield", 0)) >= 6000:
        return "Peel & Enchanter Carry"
    if pillars.get("frontline", 0) >= 82.0:
        return "Unkillable Frontline"
    if role == "Support" and pillars.get("macro_vision", 0) >= 82.0:
        return "Vision Oracle"
    if (
        pillars.get("damage", 0) >= 82.0
        and kda >= 3.5
        and archetype in ("marksman", "mage", "assassin", "bruiser", "splitpusher")
    ):
        return "Hypercarry DPS"
    if kp >= 0.68:
        return "Map Omnipresence"
    if kda >= 5.0:
        return "Deathless Precision"
    return f"{archetype.capitalize()} Specialist"


def evaluate_match_lineup_and_mvp(record: dict) -> Tuple[str, float, Dict[str, Any]]:
    """
    Scores every participant in `record['lineup']`, attaches `rating`, `grade`,
    `archetype`, and `highlight` to each lineup entry, and selects the `@LOLers`
    squad member with the highest holistic rating as Match MVP.
    """
    lineup = record.get("lineup", {})
    best_mvp = record.get("mvp") or "Squad"
    best_score = -1.0

    for role, pdata in lineup.items():
        if not isinstance(pdata, dict):
            continue
        eval_res = score_player_in_match(role, pdata, record)
        pdata["rating"] = eval_res["rating"]
        pdata["grade"] = eval_res["grade"]
        pdata["archetype"] = eval_res["archetype"]
        pdata["highlight"] = eval_res["highlight"]

        if pdata.get("is_squad", True) and eval_res["rating"] > best_score:
            best_score = eval_res["rating"]
            best_mvp = pdata.get("player", best_mvp)

    record["mvp"] = best_mvp
    if best_score > 0:
        record["mvp_rating"] = round(best_score, 1)
    return best_mvp, best_score, lineup


# --- 2. Holistic Pair Synergy Rating Model ---

def compute_holistic_pair_synergy(
    role_a: str,
    role_b: str,
    pair_entry: dict,
    match_instances: List[Tuple[dict, dict, dict]],
) -> Dict[str, Any]:
    """
    Computes a holistic 0-100 pairwise synergy score, tier, and descriptive tag
    for `(role_a, role_b)` using:
      1. Bayesian-dampened Win Rate (35%)
      2. Role & Champion-Adjusted Individual Performance Ratings of both partners (30%)
      3. Position-Pair Specific Coordination & Map Impact (20%)
      4. Combined Duo KDA & Survival Efficiency (15%)
    """
    games = pair_entry["games"]
    wins = pair_entry["wins"]
    raw_win_rate = (wins / games) * 100.0 if games > 0 else 0.0
    combined_kda = (pair_entry["total_kills"] + pair_entry["total_assists"]) / max(1, pair_entry["total_deaths"])

    # 1. Bayesian Win Rate Component (0-100), dampened for small sample sizes (< 5 games)
    confidence = min(1.0, games / 5.0)
    weighted_wr = (raw_win_rate * confidence) + (50.0 * (1.0 - confidence))

    # 2. Individual Holistic Ratings + Pair-Specific Coordination across games played together
    ratings_a = []
    ratings_b = []
    coord_scores = []

    for match, pa, pb in match_instances:
        ra = pa.get("rating")
        if ra is None:
            ra = score_player_in_match(role_a, pa, match)["rating"]
        rb = pb.get("rating")
        if rb is None:
            rb = score_player_in_match(role_b, pb, match)["rating"]
        ratings_a.append(float(ra))
        ratings_b.append(float(rb))

        coord_scores.append(_score_pair_coordination_in_match(role_a, role_b, pa, pb, match))

    avg_rating_a = sum(ratings_a) / len(ratings_a) if ratings_a else 65.0
    avg_rating_b = sum(ratings_b) / len(ratings_b) if ratings_b else 65.0
    raw_duo_rating = (avg_rating_a + avg_rating_b) / 2.0

    # Dampen performance & coordination toward a 62.0 baseline for < 3 games so 1-game samples stay in A Tier
    perf_conf = min(1.0, games / 3.0)
    dampened_duo_rating = (raw_duo_rating * perf_conf) + (62.0 * (1.0 - perf_conf))

    raw_coord = sum(coord_scores) / len(coord_scores) if coord_scores else 65.0
    dampened_coord = (raw_coord * perf_conf) + (62.0 * (1.0 - perf_conf))

    # 4. KDA efficiency component (0-100)
    kda_norm = (min(combined_kda, 6.0) / 6.0) * 100.0

    # Combine all 4 dimensions
    synergy_score = round(
        _clamp(
            (weighted_wr * 0.42)
            + (dampened_duo_rating * 0.24)
            + (dampened_coord * 0.14)
            + (kda_norm * 0.20),
            0.0,
            100.0,
        ),
        1,
    )

    tier = "S Tier" if synergy_score >= 80.0 else ("A Tier" if synergy_score >= 65.0 else "B Tier")
    tag = _determine_pair_synergy_tag(role_a, role_b, raw_win_rate, combined_kda, raw_duo_rating, raw_coord)

    return {
        "synergy_score": synergy_score,
        "tier": tier,
        "tag": tag,
        "avg_duo_rating": round(raw_duo_rating, 1),
        "coordination_score": round(raw_coord, 1),
    }


def _score_pair_coordination_in_match(
    role_a: str,
    role_b: str,
    pa: dict,
    pb: dict,
    match: dict,
) -> float:
    """Evaluates position-pair specific coordination metrics within a single match."""
    lineup = match.get("lineup", {})
    duration_min = max(10.0, float(match.get("duration_min") or 30.0))
    team_kills = sum(int(p.get("kills", 0)) for p in lineup.values() if isinstance(p, dict)) or 1

    ka = int(pa.get("kills", 0)) + int(pa.get("assists", 0))
    kb = int(pb.get("kills", 0)) + int(pb.get("assists", 0))
    avg_kp = min(1.0, ((ka + kb) / 2.0) / team_kills)
    kp_score = _ratio_score(avg_kp, target=0.52, max_mult=1.45)

    picks_and_cc = (
        int(pa.get("immobilize_and_kill_with_ally", 0))
        + int(pb.get("immobilize_and_kill_with_ally", 0))
        + int(pa.get("pick_kill_with_ally", 0))
        + int(pb.get("pick_kill_with_ally", 0))
    )
    setup_score = _ratio_score(picks_and_cc, target=8.0, max_mult=2.0) if picks_and_cc > 0 else kp_score

    roles = {role_a, role_b}
    if roles == {"Bot", "Support"}:
        adc = pa if role_a == "Bot" else pb
        sup = pb if role_a == "Bot" else pa
        adc_dpm = int(adc.get("damage", 0)) / duration_min
        sup_vis = int(sup.get("vision", 0)) / duration_min
        sup_peel = float(sup.get("effective_heal_shield", 0) or sup.get("heal_shield", 0)) + int(sup.get("cc_score", 0)) * 120.0
        bot_carry_sub = _ratio_score(adc_dpm, target=720.0, max_mult=1.6) if adc.get("damage") else kp_score
        sup_vis_sub = _ratio_score(sup_vis, target=1.8, max_mult=1.6) if sup.get("vision") else kp_score
        peel_sub = _ratio_score(sup_peel / duration_min, target=220.0, max_mult=1.8) if sup_peel > 0 else sup_vis_sub
        return _clamp(kp_score * 0.35 + bot_carry_sub * 0.30 + sup_vis_sub * 0.20 + peel_sub * 0.15)

    if roles == {"Mid", "Jungle"}:
        jng = pa if role_a == "Jungle" else pb
        objectives = (
            int(jng.get("dragon_takedowns", 0)) * 2
            + int(jng.get("void_monster_kills", 0))
            + int(jng.get("rift_herald_takedowns", 0)) * 2
            + int(jng.get("baron_takedowns", 0)) * 3
        )
        obj_sub = _ratio_score(objectives, target=5.0, max_mult=1.8) if objectives > 0 else kp_score
        return _clamp(kp_score * 0.45 + setup_score * 0.30 + obj_sub * 0.25)

    if roles == {"Top", "Jungle"}:
        top = pa if role_a == "Top" else pb
        jng = pb if role_a == "Top" else pa
        topside_pressure = (
            int(top.get("turret_takedowns", 0)) * 2
            + int(jng.get("rift_herald_takedowns", 0)) * 2
            + int(jng.get("void_monster_kills", 0))
        )
        pressure_sub = _ratio_score(topside_pressure, target=4.0, max_mult=1.8) if topside_pressure > 0 else kp_score
        return _clamp(kp_score * 0.40 + setup_score * 0.30 + pressure_sub * 0.30)

    if roles == {"Support", "Jungle"}:
        comb_vspm = (int(pa.get("vision", 0)) + int(pb.get("vision", 0))) / duration_min
        vis_sub = _ratio_score(comb_vspm, target=2.8, max_mult=1.6) if (pa.get("vision") or pb.get("vision")) else kp_score
        return _clamp(vis_sub * 0.40 + kp_score * 0.35 + setup_score * 0.25)

    return _clamp(kp_score * 0.60 + setup_score * 0.40)


def _determine_pair_synergy_tag(
    role_a: str,
    role_b: str,
    raw_win_rate: float,
    combined_kda: float,
    avg_duo_rating: float,
    coord_score: float,
) -> str:
    roles = {role_a, role_b}
    if avg_duo_rating >= 76.0 and raw_win_rate >= 60.0:
        if roles == {"Bot", "Support"}:
            return "2v8 Bot Kingdom"
        if roles == {"Mid", "Jungle"}:
            return "Map Terror 2v2"
        if roles == {"Top", "Jungle"}:
            return "Topside Raidbosses"
        if roles == {"Support", "Jungle"}:
            return "Vision & Roam Lords"
    if combined_kda >= 4.0:
        return "Lethal Core"
    if coord_score >= 74.0 or raw_win_rate >= 60.0:
        return "Objective Anchors"
    if avg_duo_rating >= 68.0:
        return "High-Impact Duo"
    return "Developing Chemistry"
