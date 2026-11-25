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
    if score >= 45.0:
        return "C"
    return "F"


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
    raw_active_weights = {}

    for p_name, p_val in raw_pillars.items():
        if p_val < 0:
            continue
        blended_w = (role_w.get(p_name, 0.15) * 0.55) + (arch_w.get(p_name, 0.15) * 0.45)
        weighted_sum += p_val * blended_w
        active_weight_total += blended_w
        active_pillars[p_name] = round(p_val, 1)
        raw_active_weights[p_name] = blended_w

    base_score = (weighted_sum / active_weight_total) if active_weight_total > 0 else combat_score
    norm_weights = {
        k: round((w / active_weight_total), 4) if active_weight_total > 0 else 0.0
        for k, w in raw_active_weights.items()
    }

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

    # Compute deterministic per-match coaching diagnostics
    coaching = _build_match_coaching_diagnostics(
        role=role,
        archetype=archetype,
        pdata=pdata,
        duration_min=duration_min,
        team_kills=team_kills,
        kp=kp,
        kp_target=kp_target,
        deaths_per_10m=deaths_per_10m,
        death_penalty=death_penalty,
        outcome_adj=outcome_adj,
        active_pillars=active_pillars,
        norm_weights=norm_weights,
        final_score=final_score,
        highlight=highlight,
    )

    return {
        "rating": final_score,
        "grade": rating_to_grade(final_score),
        "archetype": archetype,
        "highlight": highlight,
        "pillars": active_pillars,
        "short_tip": coaching["short_tip"],
        "coaching": coaching,
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
    `archetype`, `highlight`, `short_tip`, and `coaching` to each lineup entry,
    and selects the `@LOLers` squad member with the highest holistic rating as Match MVP.
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
        pdata["short_tip"] = eval_res["short_tip"]
        pdata["coaching"] = eval_res["coaching"]

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


# --- 3. Deterministic Performance-Improvement Coaching Engine ---

PILLAR_LABELS: Dict[str, str] = {
    "combat": "Combat & KDA",
    "damage": "Damage Output",
    "objective": "Objectives & Turrets",
    "frontline": "Frontline & Survivability",
    "utility": "Utility & Setup",
    "macro_vision": "CS, Vision & Macro",
}


def _build_match_coaching_diagnostics(
    role: str,
    archetype: str,
    pdata: dict,
    duration_min: float,
    team_kills: int,
    kp: float,
    kp_target: float,
    deaths_per_10m: float,
    death_penalty: float,
    outcome_adj: float,
    active_pillars: Dict[str, float],
    norm_weights: Dict[str, float],
    final_score: float,
    highlight: str,
) -> Dict[str, Any]:
    """
    Produces a deterministic, transparent per-match coaching breakdown showing:
    - Exact pillar contributions vs. 65.0 baseline
    - Exact death liability penalty & outcome adjustment
    - Ranked improvement levers (summary + optional Match-v5 timeline signals)
    - Compact 1-line Discord cue (`short_tip`)
    """
    pillar_impacts = []
    for pk, pscore in active_pillars.items():
        w = norm_weights.get(pk, 0.0)
        pillar_impacts.append({
            "pillar": pk,
            "label": PILLAR_LABELS.get(pk, pk),
            "score": round(pscore, 1),
            "weight_pct": round(w * 100.0, 1),
            "impact_vs_avg": round((pscore - 65.0) * w, 1),
        })
    pillar_impacts.sort(key=lambda x: x["impact_vs_avg"])

    levers: List[Dict[str, Any]] = []

    # 1. Excess deaths penalty (exact rating drain)
    if death_penalty >= 1.5:
        pen_r = round(death_penalty, 1)
        levers.append({
            "key": "excess_deaths",
            "category": "Survivability",
            "title": "Cut Excess Deaths",
            "observed": f"{deaths_per_10m:.1f} deaths / 10m",
            "target": "<= 2.0 deaths / 10m",
            "est_rating_gain": pen_r,
            "severity": "high" if pen_r >= 5.0 else "medium",
            "detail": f"Died {deaths_per_10m:.1f}/10m (threshold 2.0/10m), directly costing -{pen_r} rating pts.",
            "short_cue": f"↑ Cut deaths ({deaths_per_10m:.1f}/10m, -{pen_r} pts)",
        })

    # 2. CS/min gap (non-Support when CS data is present)
    cs = int(pdata.get("cs", 0))
    if role != "Support" and cs > 0:
        cspm = cs / duration_min
        cs_target = ROLE_CSPM_BENCHMARK.get(role, 6.0)
        if cspm < cs_target * 0.85:
            gap_ratio = (cs_target - cspm) / max(1.0, cs_target)
            est_gain = round(min(9.0, max(1.5, gap_ratio * 24.0 * max(0.12, norm_weights.get("macro_vision", 0.16)))), 1)
            levers.append({
                "key": "low_cspm",
                "category": "Economy & Farming",
                "title": "Raise CS/min",
                "observed": f"{cspm:.1f} CS/m",
                "target": f"{cs_target:.1f} CS/m ({role})",
                "est_rating_gain": est_gain,
                "severity": "high" if cspm < cs_target * 0.72 else "medium",
                "detail": f"Farmed {cspm:.1f} CS/min vs. {cs_target:.1f} {role} benchmark — catch side waves between fights.",
                "short_cue": f"↑ CS/m ({cspm:.1f} vs {cs_target:.1f})",
            })

    # 3. Vision/min & Control Wards
    vision = int(pdata.get("vision", 0))
    v_target = ROLE_VSPM_BENCHMARK.get(role, 0.85)
    if vision > 0 or pdata.get("wards_placed", 0) > 0:
        vspm = vision / duration_min
        if vspm < v_target * 0.78:
            gap_ratio = (v_target - vspm) / max(0.5, v_target)
            est_gain = round(min(8.5, max(1.5, gap_ratio * 22.0 * max(0.14, norm_weights.get("macro_vision", 0.16)))), 1)
            levers.append({
                "key": "low_vision",
                "category": "Vision Control",
                "title": "Boost Vision Score",
                "observed": f"{vspm:.2f} vis/m",
                "target": f"{v_target:.2f} vis/m ({role})",
                "est_rating_gain": est_gain,
                "severity": "high" if (role == "Support" or vspm < v_target * 0.6) else "medium",
                "detail": f"Vision score {vspm:.2f}/min vs. {v_target:.2f}/min {role} target — drop wards before objective setups.",
                "short_cue": f"↑ Vision ({vspm:.2f} vs {v_target:.2f}/m)",
            })
        elif duration_min >= 20.0 and int(pdata.get("control_wards_placed", 0)) == 0 and int(pdata.get("wards_placed", 0)) > 0:
            levers.append({
                "key": "no_control_wards",
                "category": "Vision Control",
                "title": "Buy Control Wards",
                "observed": "0 control wards",
                "target": ">= 2 control wards",
                "est_rating_gain": 2.0,
                "severity": "low",
                "detail": f"Placed 0 control wards in a {duration_min:.0f}-minute game; denying river vision unlocks objective setups.",
                "short_cue": "↑ Buy control wards (0 placed)",
            })

    # 4. Damage Output (for damage-dealing archetypes)
    damage = int(pdata.get("damage", 0))
    if damage > 0 and archetype in ("marksman", "mage", "assassin", "bruiser", "splitpusher"):
        dpm = damage / duration_min
        dpm_target = ARCHETYPE_DPM_BENCHMARK.get(archetype, 600.0)
        if dpm < dpm_target * 0.78:
            gap_ratio = (dpm_target - dpm) / max(100.0, dpm_target)
            est_gain = round(min(9.5, max(1.8, gap_ratio * 26.0 * max(0.15, norm_weights.get("damage", 0.22)))), 1)
            levers.append({
                "key": "low_dpm",
                "category": "Damage Output",
                "title": "Increase Damage Share",
                "observed": f"{dpm:.0f} DPM",
                "target": f"{dpm_target:.0f} DPM ({archetype})",
                "est_rating_gain": est_gain,
                "severity": "high" if dpm < dpm_target * 0.62 else "medium",
                "detail": f"Dealt {dpm:.0f} DPM vs. {dpm_target:.0f} {archetype} target — look for safer poke/uptime in skirmishes.",
                "short_cue": f"↑ DPM ({dpm:.0f} vs {dpm_target:.0f})",
            })

    # 5. Kill Participation / Fight Presence
    if team_kills >= 8 and kp < kp_target * 0.75:
        kp_pct = round(kp * 100)
        kp_t_pct = round(kp_target * 100)
        est_gain = round(min(7.0, max(1.5, (kp_target - kp) * 20.0 * max(0.15, norm_weights.get("combat", 0.20)))), 1)
        levers.append({
            "key": "low_kp",
            "category": "Map Presence",
            "title": "Join More Teamfights",
            "observed": f"{kp_pct}% KP",
            "target": f"{kp_t_pct}% KP ({role})",
            "est_rating_gain": est_gain,
            "severity": "medium",
            "detail": f"Kill participation was {kp_pct}% vs. {kp_t_pct}% {role} target — sync rotations with squad skirmishes.",
            "short_cue": f"↑ Fight presence ({kp_pct}% vs {kp_t_pct}% KP)",
        })

    # 6. Objective / Structural Pressure
    obj_score = active_pillars.get("objective", -1.0)
    if obj_score >= 0 and obj_score < 52.0 and (role in ("Jungle", "Top") or archetype == "splitpusher"):
        est_gain = round(min(7.5, max(1.5, (65.0 - obj_score) * max(0.14, norm_weights.get("objective", 0.18)))), 1)
        levers.append({
            "key": "low_objectives",
            "category": "Objectives & Turrets",
            "title": "Convert Objective Pressure",
            "observed": f"{obj_score:.0f}/100 pillar",
            "target": ">= 65/100 pillar",
            "est_rating_gain": est_gain,
            "severity": "medium",
            "detail": f"Objective/turret pressure scored {obj_score:.0f}/100 — prioritize dragon/herald setups or side-lane plates.",
            "short_cue": f"↑ Objective pressure ({obj_score:.0f}/100)",
        })

    # 7. Timeline-powered diagnostics (when Match-v5 Timeline data is present)
    tl = pdata.get("timeline") if isinstance(pdata.get("timeline"), dict) else None
    if tl:
        gd15 = tl.get("gold_diff_15")
        csd15 = tl.get("cs_diff_15")
        if (isinstance(gd15, (int, float)) and gd15 <= -800) or (
            role != "Support" and isinstance(csd15, (int, float)) and csd15 <= -15
        ):
            if isinstance(gd15, (int, float)) and gd15 <= -800:
                obs_str = f"{int(gd15):+d}g @15m"
                cue_str = f"↑ Early lane ({int(gd15):+d}g @15m)"
                sev = "high" if gd15 <= -1500 else "medium"
                gain = round(min(6.5, max(2.0, abs(gd15) / 350.0)), 1)
            else:
                obs_str = f"{int(csd15):+d} CS @15m"
                cue_str = f"↑ Early lane ({int(csd15):+d} CS @15m)"
                sev = "high" if csd15 <= -25 else "medium"
                gain = round(min(5.5, max(1.8, abs(csd15) / 6.0)), 1)
            levers.append({
                "key": "lane_deficit_15",
                "category": "Laning Phase (0–15m)",
                "title": "Tighten Early Laning",
                "observed": obs_str,
                "target": "Even or ahead @15m",
                "est_rating_gain": gain,
                "severity": sev,
                "detail": f"Fell behind lane opponent by {obs_str}; focus on wave control and early recall timings.",
                "short_cue": cue_str,
            })

        pre_obj = int(tl.get("pre_objective_deaths", 0))
        if pre_obj >= 2:
            levers.append({
                "key": "pre_obj_deaths",
                "category": "Objective Timing",
                "title": "Avoid Pre-Objective Deaths",
                "observed": f"{pre_obj} deaths <60s pre-obj",
                "target": "0 pre-objective deaths",
                "est_rating_gain": round(min(6.0, pre_obj * 2.2), 1),
                "severity": "high" if pre_obj >= 3 else "medium",
                "detail": f"Died {pre_obj} times within 60s before an epic monster — avoid face-checking or overextending on spawn timers.",
                "short_cue": f"↑ Pre-obj discipline ({pre_obj} deaths)",
            })

        late_d = int(tl.get("late_deaths", 0))
        if late_d >= 2:
            levers.append({
                "key": "late_deaths",
                "category": "Late-Game Positioning",
                "title": "Protect Late-Game Life",
                "observed": f"{late_d} deaths after 25m",
                "target": "<= 1 late death",
                "est_rating_gain": round(min(6.0, late_d * 2.0), 1),
                "severity": "high" if late_d >= 3 else "medium",
                "detail": f"Recorded {late_d} deaths past 25 minutes — late picks swing Baron/Soul fights.",
                "short_cue": f"↑ Late positioning ({late_d} deaths 25m+)",
            })

    # Rank levers by estimated rating impact descending and keep top 3
    levers.sort(key=lambda x: x["est_rating_gain"], reverse=True)
    top_levers = levers[:3]

    if top_levers and (final_score < 84.0 or top_levers[0]["severity"] == "high"):
        short_tip = top_levers[0]["short_cue"]
    else:
        short_tip = f"✓ Clean game — {highlight}"

    return {
        "death_penalty": round(death_penalty, 1),
        "deaths_per_10m": round(deaths_per_10m, 2),
        "outcome_adj": outcome_adj,
        "pillar_impacts": pillar_impacts,
        "levers": top_levers,
        "short_tip": short_tip,
        "has_timeline": bool(tl),
    }


def build_player_coaching_report(
    player_name: str,
    matches: List[dict],
    primary_role: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Builds a multi-game deterministic coaching report for a specific squad player:
    - Top 3 recurring focus areas (frequency & average rating gain)
    - Win vs. Loss metric splits (what drops most in losses)
    - Timeline laning & death-timing profile (when available)
    - Role fit (on-role vs off-role) & Champion fit (best vs weakest pick)
    """
    target_lower = (player_name or "").strip().lower()
    appearances: List[Tuple[dict, str, dict, dict]] = []

    for match in matches:
        if not isinstance(match, dict):
            continue
        if match.get("is_remake") or str(match.get("result", "")).upper() == "REMAKE":
            continue
        dur = match.get("duration_min")
        if isinstance(dur, (int, float)) and 0 < dur < 5.0:
            continue

        for role, pdata in (match.get("lineup") or {}).items():
            if not isinstance(pdata, dict):
                continue
            if "is_squad" in pdata and not pdata.get("is_squad"):
                continue
            if (pdata.get("player") or "").strip().lower() != target_lower:
                continue
            eval_res = score_player_in_match(role, pdata, match)
            appearances.append((match, role, pdata, eval_res))
            break

    total_games = len(appearances)
    if total_games == 0:
        return {
            "player": player_name,
            "games_analyzed": 0,
            "wins": 0,
            "losses": 0,
            "top_focus_areas": [],
            "win_vs_loss": None,
            "death_profile": None,
            "role_fit": None,
            "champion_fit": None,
        }

    wins_list = [a for a in appearances if a[0].get("result") == "WIN"]
    losses_list = [a for a in appearances if a[0].get("result") != "WIN"]

    # 1. Aggregate recurring coaching levers
    lever_agg: Dict[str, Dict[str, Any]] = {}
    for _m, _role, _pdata, ev in appearances:
        for lv in ev["coaching"]["levers"]:
            k = lv["key"]
            if k not in lever_agg:
                lever_agg[k] = {
                    "key": k,
                    "category": lv["category"],
                    "title": lv["title"],
                    "occurrences": 0,
                    "gain_sum": 0.0,
                    "latest_detail": lv["detail"],
                    "short_cue": lv["short_cue"],
                }
            lever_agg[k]["occurrences"] += 1
            lever_agg[k]["gain_sum"] += float(lv["est_rating_gain"])

    focus_areas = []
    for item in lever_agg.values():
        occ = item["occurrences"]
        avg_gain = round(item["gain_sum"] / occ, 1)
        freq_pct = round((occ / total_games) * 100.0, 1)
        priority_score = round(occ * avg_gain, 2)
        focus_areas.append({
            "key": item["key"],
            "category": item["category"],
            "title": item["title"],
            "occurrences": occ,
            "games_analyzed": total_games,
            "frequency_pct": freq_pct,
            "avg_est_gain": avg_gain,
            "priority_score": priority_score,
            "summary": f"Flagged in {occ}/{total_games} games ({freq_pct:.0f}%), avg +{avg_gain} rating upside. {item['latest_detail']}",
        })
    focus_areas.sort(key=lambda x: (x["priority_score"], x["occurrences"]), reverse=True)

    # 2. Win vs. Loss metric splits
    def _avg_metrics(subset: List[Tuple[dict, str, dict, dict]]) -> Optional[Dict[str, Any]]:
        if not subset:
            return None
        ratings, d10_list, cspm_list, vspm_list, kp_list, dpm_list, gd15_list, csd15_list = [], [], [], [], [], [], [], []
        for m, r, p, ev in subset:
            dur = max(10.0, float(m.get("duration_min") or 30.0))
            ratings.append(float(ev["rating"]))
            d10_list.append(float(ev["coaching"]["deaths_per_10m"]))
            if r != "Support" and int(p.get("cs", 0)) > 0:
                cspm_list.append(int(p.get("cs", 0)) / dur)
            if int(p.get("vision", 0)) > 0:
                vspm_list.append(int(p.get("vision", 0)) / dur)
            if p.get("kill_participation") is not None:
                kp_list.append(float(p["kill_participation"]) * 100.0)
            if int(p.get("damage", 0)) > 0:
                dpm_list.append(int(p.get("damage", 0)) / dur)
            tl = p.get("timeline") if isinstance(p.get("timeline"), dict) else None
            if tl:
                if isinstance(tl.get("gold_diff_15"), (int, float)):
                    gd15_list.append(float(tl["gold_diff_15"]))
                if isinstance(tl.get("cs_diff_15"), (int, float)):
                    csd15_list.append(float(tl["cs_diff_15"]))
        return {
            "games": len(subset),
            "avg_rating": round(sum(ratings) / len(ratings), 1),
            "deaths_per_10m": round(sum(d10_list) / len(d10_list), 2),
            "cspm": round(sum(cspm_list) / len(cspm_list), 1) if cspm_list else None,
            "vspm": round(sum(vspm_list) / len(vspm_list), 2) if vspm_list else None,
            "kp_pct": round(sum(kp_list) / len(kp_list), 1) if kp_list else None,
            "dpm": round(sum(dpm_list) / len(dpm_list), 0) if dpm_list else None,
            "gold_diff_15": round(sum(gd15_list) / len(gd15_list), 0) if gd15_list else None,
            "cs_diff_15": round(sum(csd15_list) / len(csd15_list), 1) if csd15_list else None,
        }

    win_stats = _avg_metrics(wins_list)
    loss_stats = _avg_metrics(losses_list)
    biggest_loss_drop = None
    if win_stats and loss_stats:
        drops = []
        d_diff = loss_stats["deaths_per_10m"] - win_stats["deaths_per_10m"]
        if d_diff >= 0.4:
            drops.append((d_diff * 12.0, f"Deaths jump from {win_stats['deaths_per_10m']:.1f} to {loss_stats['deaths_per_10m']:.1f}/10m in losses"))
        if win_stats["cspm"] is not None and loss_stats["cspm"] is not None:
            cs_drop = win_stats["cspm"] - loss_stats["cspm"]
            if cs_drop >= 0.6:
                drops.append((cs_drop * 8.0, f"CS/m drops from {win_stats['cspm']:.1f} (W) to {loss_stats['cspm']:.1f} (L)"))
        if win_stats["vspm"] is not None and loss_stats["vspm"] is not None:
            vis_drop = win_stats["vspm"] - loss_stats["vspm"]
            if vis_drop >= 0.15:
                drops.append((vis_drop * 25.0, f"Vision/m falls from {win_stats['vspm']:.2f} (W) to {loss_stats['vspm']:.2f} (L)"))
        if win_stats["kp_pct"] is not None and loss_stats["kp_pct"] is not None:
            kp_drop = win_stats["kp_pct"] - loss_stats["kp_pct"]
            if kp_drop >= 8.0:
                drops.append((kp_drop * 0.5, f"KP drops from {win_stats['kp_pct']:.0f}% (W) to {loss_stats['kp_pct']:.0f}% (L)"))
        if drops:
            drops.sort(key=lambda x: x[0], reverse=True)
            biggest_loss_drop = drops[0][1]

    win_vs_loss = {
        "wins": win_stats,
        "losses": loss_stats,
        "biggest_loss_drop": biggest_loss_drop,
    }

    # 3. Timeline laning & death-timing profile
    tl_games = 0
    early_d, mid_d, late_d, pre_obj_d = 0, 0, 0, 0
    gd10_vals, csd10_vals, gd15_vals, csd15_vals = [], [], [], []
    for _m, _r, p, _ev in appearances:
        tl = p.get("timeline") if isinstance(p.get("timeline"), dict) else None
        if not tl:
            continue
        tl_games += 1
        early_d += int(tl.get("early_deaths", 0))
        mid_d += int(tl.get("mid_deaths", 0))
        late_d += int(tl.get("late_deaths", 0))
        pre_obj_d += int(tl.get("pre_objective_deaths", 0))
        if isinstance(tl.get("gold_diff_10"), (int, float)):
            gd10_vals.append(float(tl["gold_diff_10"]))
        if isinstance(tl.get("cs_diff_10"), (int, float)):
            csd10_vals.append(float(tl["cs_diff_10"]))
        if isinstance(tl.get("gold_diff_15"), (int, float)):
            gd15_vals.append(float(tl["gold_diff_15"]))
        if isinstance(tl.get("cs_diff_15"), (int, float)):
            csd15_vals.append(float(tl["cs_diff_15"]))

    death_profile = None
    if tl_games > 0:
        death_profile = {
            "games_with_timeline": tl_games,
            "early_deaths_avg": round(early_d / tl_games, 2),
            "mid_deaths_avg": round(mid_d / tl_games, 2),
            "late_deaths_avg": round(late_d / tl_games, 2),
            "pre_objective_deaths_avg": round(pre_obj_d / tl_games, 2),
            "avg_gold_diff_10": round(sum(gd10_vals) / len(gd10_vals), 0) if gd10_vals else None,
            "avg_cs_diff_10": round(sum(csd10_vals) / len(csd10_vals), 1) if csd10_vals else None,
            "avg_gold_diff_15": round(sum(gd15_vals) / len(gd15_vals), 0) if gd15_vals else None,
            "avg_cs_diff_15": round(sum(csd15_vals) / len(csd15_vals), 1) if csd15_vals else None,
        }

    # 4. Role Fit (on-role vs off-role)
    role_counts: Dict[str, int] = {}
    for _m, r, _p, _ev in appearances:
        role_counts[r] = role_counts.get(r, 0) + 1
    inferred_primary = primary_role if primary_role in ("Top", "Jungle", "Mid", "Bot", "Support") else max(role_counts, key=role_counts.get)
    on_role_ratings = [ev["rating"] for _m, r, _p, ev in appearances if r == inferred_primary]
    off_role_ratings = [ev["rating"] for _m, r, _p, ev in appearances if r != inferred_primary]
    role_fit = {
        "primary_role": inferred_primary,
        "on_role_games": len(on_role_ratings),
        "off_role_games": len(off_role_ratings),
        "on_role_avg": round(sum(on_role_ratings) / len(on_role_ratings), 1) if on_role_ratings else None,
        "off_role_avg": round(sum(off_role_ratings) / len(off_role_ratings), 1) if off_role_ratings else None,
        "delta": (
            round((sum(on_role_ratings) / len(on_role_ratings)) - (sum(off_role_ratings) / len(off_role_ratings)), 1)
            if on_role_ratings and off_role_ratings
            else None
        ),
    }

    # 5. Champion Fit
    champ_agg: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for m, r, p, ev in appearances:
        ck = (p.get("champion", "Unknown"), r)
        if ck not in champ_agg:
            champ_agg[ck] = {"champion": ck[0], "role": r, "games": 0, "wins": 0, "rating_sum": 0.0}
        champ_agg[ck]["games"] += 1
        if m.get("result") == "WIN":
            champ_agg[ck]["wins"] += 1
        champ_agg[ck]["rating_sum"] += float(ev["rating"])

    champ_entries = [
        {
            "champion": c["champion"],
            "role": c["role"],
            "games": c["games"],
            "win_rate": round((c["wins"] / c["games"]) * 100.0, 1),
            "avg_rating": round(c["rating_sum"] / c["games"], 1),
        }
        for c in champ_agg.values()
    ]
    qualified = [c for c in champ_entries if c["games"] >= 2] or champ_entries
    qualified.sort(key=lambda x: (x["avg_rating"], x["win_rate"], x["games"]), reverse=True)
    champion_fit = {
        "best_pick": qualified[0] if qualified else None,
        "weakest_pick": qualified[-1] if len(qualified) > 1 else None,
    }

    return {
        "player": player_name,
        "games_analyzed": total_games,
        "wins": len(wins_list),
        "losses": len(losses_list),
        "top_focus_areas": focus_areas[:3],
        "win_vs_loss": win_vs_loss,
        "death_profile": death_profile,
        "role_fit": role_fit,
        "champion_fit": champion_fit,
    }


def build_squad_coaching_summary(matches: List[dict]) -> Dict[str, Any]:
    """
    Aggregates squad-wide recurring rating drains across all proper matches for the
    Overview tab's 'Coaching & Leaks' summary section.
    """
    proper_matches = [
        m for m in matches
        if isinstance(m, dict)
        and not m.get("is_remake")
        and str(m.get("result", "")).upper() != "REMAKE"
        and not (isinstance(m.get("duration_min"), (int, float)) and 0 < m.get("duration_min") < 5.0)
    ]
    if not proper_matches:
        return {
            "games_analyzed": 0,
            "squad_appearances": 0,
            "avg_death_penalty": 0.0,
            "top_leaks": [],
        }

    lever_agg: Dict[str, Dict[str, Any]] = {}
    total_appearances = 0
    total_death_penalty = 0.0

    for match in proper_matches:
        for role, pdata in (match.get("lineup") or {}).items():
            if not isinstance(pdata, dict):
                continue
            if "is_squad" in pdata and not pdata.get("is_squad"):
                continue
            ev = score_player_in_match(role, pdata, match)
            total_appearances += 1
            total_death_penalty += float(ev["coaching"]["death_penalty"])
            pname = pdata.get("player", "Unknown")

            for lv in ev["coaching"]["levers"]:
                k = lv["key"]
                if k not in lever_agg:
                    lever_agg[k] = {
                        "key": k,
                        "category": lv["category"],
                        "title": lv["title"],
                        "occurrences": 0,
                        "gain_sum": 0.0,
                        "players": {},
                    }
                lever_agg[k]["occurrences"] += 1
                lever_agg[k]["gain_sum"] += float(lv["est_rating_gain"])
                lever_agg[k]["players"][pname] = lever_agg[k]["players"].get(pname, 0) + 1

    leaks = []
    for item in lever_agg.values():
        occ = item["occurrences"]
        avg_gain = round(item["gain_sum"] / occ, 1)
        rate_pct = round((occ / max(1, total_appearances)) * 100.0, 1)
        top_players = sorted(item["players"].items(), key=lambda x: x[1], reverse=True)[:3]
        leaks.append({
            "key": item["key"],
            "category": item["category"],
            "title": item["title"],
            "occurrences": occ,
            "rate_pct": rate_pct,
            "avg_est_gain": avg_gain,
            "total_points_impact": round(item["gain_sum"], 1),
            "top_affected_players": [p for p, _cnt in top_players],
            "summary": f"Appears in {occ} squad game-slots ({rate_pct:.0f}%), costing ~{avg_gain} rating pts when triggered.",
        })
    leaks.sort(key=lambda x: (x["total_points_impact"], x["occurrences"]), reverse=True)

    return {
        "games_analyzed": len(proper_matches),
        "squad_appearances": total_appearances,
        "avg_death_penalty": round(total_death_penalty / max(1, total_appearances), 2),
        "top_leaks": leaks[:4],
    }

