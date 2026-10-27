"""
Data Manager for League of Legends 5-Stack Discord Bot.
Stores player profiles, active sessions, and match records.
Calculates duo synergy stats (specifically Bot + Support synergy), team chemistry, and player win rates.
"""

import json
import os
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime

DEFAULT_DATA_PATH = "data/league_stats.json"

class StatsManager:
    def __init__(self, filepath: str = DEFAULT_DATA_PATH):
        self.filepath = filepath
        self._ensure_dir()
        self.data = self._load()
        if self.reconcile_linked_players_in_history():
            self.save()

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
            "match_history": [],
            "synergy_threads": {},
            "feedback_history": []
        }

    def save(self):
        with open(self.filepath, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2)

    # Session Management
    def create_session(
        self,
        session_id: str,
        scheduled_time: str,
        mode: str,
        is_ranked_5s: bool,
        creator: str,
        scheduled_iso: Optional[str] = None,
        creator_id: Optional[str] = None
    ) -> dict:
        session = {
            "session_id": session_id,
            "created_at": datetime.now().isoformat(),
            "scheduled_time": scheduled_time,
            "scheduled_iso": scheduled_iso,
            "mode": mode,
            "is_ranked_5s": is_ranked_5s,
            "creator": creator,
            "creator_id": str(creator_id) if creator_id else None,
            "status": "POLLING",  # POLLING, READY, IN_PROGRESS, COMPLETED, CANCELLED
            "confirmed_players": [],  # list of {name, role_pref}
            "bench_substitutes": [],
            "declined": [],
            "reminder_sent": False,
            "channel_id": None,
            "message_id": None,
            "thread_id": None,
            "activity_log": [],
            "session_matches": []
        }
        self.data["active_sessions"][session_id] = session
        self.save()
        return session

    def set_session_message(self, session_id: str, channel_id: int, message_id: int):
        """Stores the channel ID and message ID of the session's announcement."""
        session = self.data["active_sessions"].get(session_id)
        if session:
            session["channel_id"] = channel_id
            session["message_id"] = message_id
            self.save()

    def set_session_thread(self, session_id: str, thread_id: int):
        """Stores the attached Discord thread ID for a session."""
        session = self.data["active_sessions"].get(session_id)
        if session:
            session["thread_id"] = thread_id
            self.save()

    def append_session_activity(self, session_id: str, entry: str, max_entries: int = 5) -> Optional[dict]:
        """Appends a timestamped update to the session's in-place activity log."""
        session = self.data["active_sessions"].get(session_id)
        if not session:
            return None
        timestamp = datetime.now().strftime("%I:%M %p").lstrip("0")
        log = session.setdefault("activity_log", [])
        log.append(f"`{timestamp}` {entry}")
        if len(log) > max_entries:
            session["activity_log"] = log[-max_entries:]
        self.save()
        return session

    def attach_match_to_active_session(self, match_record: dict) -> Optional[dict]:
        """
        Associates a newly logged match with the most relevant active session (preferring IN_PROGRESS,
        then READY, then POLLING) so the session card can display a live W-L tally and route the
        detailed match recap into the session's thread.
        """
        active = self.get_active_sessions()
        if not active:
            return None

        priority = {"IN_PROGRESS": 0, "READY": 1, "POLLING": 2}
        active_sorted = sorted(active, key=lambda s: priority.get(s.get("status", "POLLING"), 3))
        target = active_sorted[0]

        matches = target.setdefault("session_matches", [])
        match_id = match_record.get("match_id")
        if not any(m.get("match_id") == match_id for m in matches):
            matches.append({
                "match_id": match_id,
                "result": match_record.get("result", "WIN"),
                "mode": match_record.get("mode", "Match"),
                "mvp": match_record.get("mvp", "N/A")
            })
            self.save()
        return target

    def get_session(self, session_id: str) -> Optional[dict]:
        """Fetches a session by ID."""
        return self.data.get("active_sessions", {}).get(session_id)

    def edit_session_time(
        self,
        session_id: str,
        new_scheduled_time: str,
        new_scheduled_iso: Optional[str],
        new_mode: str,
        is_ranked_5s: bool
    ) -> Tuple[bool, Optional[dict], List[str]]:
        """
        Edits the scheduled time of a session and resets the reminder.
        Returns: (success, session_dict, list_of_signed_up_players_to_alert)
        """
        session = self.data["active_sessions"].get(session_id)
        if not session or session.get("status") in ["CANCELLED", "COMPLETED"]:
            return False, None, []

        session["scheduled_time"] = new_scheduled_time
        session["scheduled_iso"] = new_scheduled_iso
        session["mode"] = new_mode
        session["is_ranked_5s"] = is_ranked_5s
        session["reminder_sent"] = False

        # Gather all currently signed-up participants
        affected = [p["name"] for p in session.get("confirmed_players", [])] + \
                   [p["name"] for p in session.get("bench_substitutes", [])]

        self.save()
        return True, session, affected

    def cancel_session(self, session_id: str) -> Tuple[bool, Optional[dict], List[str]]:
        """
        Cancels an active session and returns affected players.
        Returns: (success, session_dict, list_of_signed_up_players_to_alert)
        """
        session = self.data["active_sessions"].get(session_id)
        if not session or session.get("status") == "CANCELLED":
            return False, None, []

        affected = [p["name"] for p in session.get("confirmed_players", [])] + \
                   [p["name"] for p in session.get("bench_substitutes", [])]

        session["status"] = "CANCELLED"
        self.save()
        return True, session, affected

    def complete_session(self, session_id: str) -> Tuple[bool, Optional[dict]]:
        """Marks an active session as completed."""
        session = self.data["active_sessions"].get(session_id)
        if not session or session.get("status") in ["CANCELLED", "COMPLETED"]:
            return False, None

        session["status"] = "COMPLETED"
        self.save()
        return True, session

    def get_active_sessions(self) -> List[dict]:
        """Returns all non-cancelled, non-completed sessions."""
        return [
            s for s in self.data.get("active_sessions", {}).values()
            if s.get("status") in ["POLLING", "READY", "IN_PROGRESS"]
        ]

    def check_session_lifecycle(self, now_dt: datetime) -> List[dict]:
        """
        Inspects active sessions and transitions their statuses:
        - If now >= scheduled_time and status is 'READY' or 'POLLING': transitions to 'IN_PROGRESS'
        - If now >= scheduled_time + 4 hours: transitions to 'COMPLETED'
        - If scheduled_iso is missing and now >= created_at + 8 hours: transitions to 'COMPLETED'
        Returns list of sessions whose status changed.
        """
        changed = []
        for s_id, s in self.data.get("active_sessions", {}).items():
            current_status = s.get("status")
            if current_status not in ["POLLING", "READY", "IN_PROGRESS"]:
                continue

            iso_str = s.get("scheduled_iso")
            new_status = None

            if iso_str:
                try:
                    target_dt = datetime.fromisoformat(iso_str)
                    if target_dt.tzinfo is None and now_dt.tzinfo is not None:
                        target_dt = now_dt.tzinfo.localize(target_dt)
                    elif target_dt.tzinfo is not None and now_dt.tzinfo is None:
                        target_dt = target_dt.replace(tzinfo=None)

                    diff_sec = (now_dt - target_dt).total_seconds()
                    # 4 hours after scheduled time -> COMPLETED
                    if diff_sec >= 4 * 3600:
                        new_status = "COMPLETED"
                    # At scheduled time (up to 4 hours after) -> IN_PROGRESS
                    elif diff_sec >= 0 and current_status in ["POLLING", "READY"]:
                        new_status = "IN_PROGRESS"
                except Exception:
                    pass

            if not new_status and s.get("created_at"):
                try:
                    created_dt = datetime.fromisoformat(s["created_at"])
                    if created_dt.tzinfo is None and now_dt.tzinfo is not None:
                        created_dt = now_dt.tzinfo.localize(created_dt)
                    elif created_dt.tzinfo is not None and now_dt.tzinfo is None:
                        created_dt = created_dt.replace(tzinfo=None)

                    if (now_dt - created_dt).total_seconds() >= 8 * 3600:
                        new_status = "COMPLETED"
                except Exception:
                    pass

            if new_status and new_status != current_status:
                s["status"] = new_status
                changed.append(s)

        if changed:
            self.save()
        return changed

    def get_pending_reminders(self, now_dt: datetime) -> List[dict]:
        """
        Returns active sessions starting within the next 15 minutes that haven't sent a reminder yet.
        """
        pending = []
        for s_id, s in self.data.get("active_sessions", {}).items():
            if s.get("status") in ["POLLING", "READY"] and not s.get("reminder_sent", False):
                iso_str = s.get("scheduled_iso")
                if not iso_str:
                    continue
                try:
                    target_dt = datetime.fromisoformat(iso_str)
                    diff_sec = (target_dt - now_dt).total_seconds()
                    # Trigger if within 15 minutes (900s) and not passed more than 5 minutes ago (-300s)
                    if -300 <= diff_sec <= 900:
                        pending.append(s)
                except Exception:
                    continue
        return pending

    def mark_reminder_sent(self, session_id: str):
        """Marks that the 15-minute reminder has been delivered."""
        session = self.data["active_sessions"].get(session_id)
        if session:
            session["reminder_sent"] = True
            self.save()

    def register_player(self, session_id: str, player_name: str, status: str = "CONFIRMED", role_pref: str = "Fill") -> tuple:
        """
        Adds player to session with automatic bench promotion.
        - First 5 players are confirmed starters
        - 6th and onward go to bench_substitutes
        - If a starter declines or leaves, the first bench substitute is auto-promoted!
        Returns (is_ready, session, promoted_player_or_None)
        """
        session = self.data["active_sessions"].get(session_id)
        if not session:
            return False, None, None

        was_confirmed = any(p["name"] == player_name for p in session.get("confirmed_players", []))

        # Clean existing entries for this player
        session["confirmed_players"] = [p for p in session["confirmed_players"] if p["name"] != player_name]
        session["bench_substitutes"] = [p for p in session["bench_substitutes"] if p["name"] != player_name]
        session["declined"] = [p for p in session["declined"] if p != player_name]

        promoted_player = None

        if status == "CONFIRMED":
            if len(session["confirmed_players"]) < 5:
                session["confirmed_players"].append({"name": player_name, "role_pref": role_pref})
            else:
                session["bench_substitutes"].append({"name": player_name, "role_pref": role_pref})
        elif status == "BENCH":
            session["bench_substitutes"].append({"name": player_name, "role_pref": role_pref})
            # If they were a starter and moved to bench, promote the next bench player
            if was_confirmed and session["bench_substitutes"]:
                # The next player on bench (excluding the one who just joined bench)
                candidates = [p for p in session["bench_substitutes"] if p["name"] != player_name]
                if candidates:
                    promoted = candidates[0]
                    session["bench_substitutes"].remove(promoted)
                    session["confirmed_players"].append(promoted)
                    promoted_player = promoted
        elif status == "DECLINED":
            session["declined"].append(player_name)
            # Auto-promote from bench if a starter declined
            if was_confirmed and session["bench_substitutes"]:
                promoted = session["bench_substitutes"].pop(0)
                session["confirmed_players"].append(promoted)
                promoted_player = promoted

        # Quorum threshold check (minimum 5 players)
        quorum_met = len(session["confirmed_players"]) >= 5
        if quorum_met:
            session["status"] = "READY"
        elif session["status"] == "READY":
            session["status"] = "POLLING"

        self.save()
        return quorum_met, session, promoted_player


    def link_riot_account(self, discord_id: str, display_name: str, puuid: str, riot_id: str) -> dict:
        """
        Links a Discord user to a Riot PUUID and Riot ID (GameName#TagLine).
        """
        if "linked_players" not in self.data:
            self.data["linked_players"] = {}

        info = {
            "discord_id": str(discord_id),
            "discord_name": display_name,
            "name": display_name,
            "puuid": puuid,
            "riot_id": riot_id,
            "linked_at": datetime.now().isoformat()
        }
        self.data["linked_players"][str(discord_id)] = info

        # Sync to members list if existing, or create new member entry
        found = False
        for m in self.data.get("members", []):
            if m.get("discord_id") == str(discord_id) or m.get("name", "").lower() == display_name.lower():
                m["discord_id"] = str(discord_id)
                m["puuid"] = puuid
                m["riot_id"] = riot_id
                found = True
                break
        if not found:
            self.data.setdefault("members", []).append({
                "id": str(len(self.data.get("members", [])) + 1),
                "name": display_name,
                "discord_id": str(discord_id),
                "discord_tag": display_name,
                "puuid": puuid,
                "riot_id": riot_id,
                "primary_role": "Flex",
                "secondary_role": "Flex",
                "fav_champs": []
            })

        self.reconcile_linked_players_in_history()
        self.save()
        return info

    def set_lolers_roster(self, member_names: List[str]) -> None:
        """
        Records the live Discord server's @LOLers role member display names/usernames
        so synergy and leaderboard calculations strictly filter to @LOLers members.
        """
        cleaned = sorted({n.strip() for n in member_names if n and n.strip()})
        self.data["lolers_roster"] = cleaned
        self.save()

    def get_valid_lolers_names(self) -> set:
        """
        Returns the lowercase set of known @LOLers member names:
        - Live @LOLers role members synced from Discord (`lolers_roster`)
        - Verified @LOLers members who linked Riot accounts (`linked_players`)
        - Configured group members (`members`)
        """
        names = set()
        for n in self.data.get("lolers_roster", []):
            if n:
                names.add(n.lower())
        for info in self.data.get("linked_players", {}).values():
            if info.get("name"):
                names.add(info["name"].lower())
            if info.get("discord_name"):
                names.add(info["discord_name"].lower())
        for m in self.data.get("members", []):
            if m.get("name"):
                names.add(m["name"].lower())
        return names

    def reconcile_linked_players_in_history(self) -> bool:
        """
        Retroactively updates any match_history lineup entries where a linked @LOLers
        member was previously recorded by their raw Riot ID with `is_squad=False`
        before they ran `/link-riot`.
        """
        riot_id_map: Dict[str, str] = {}
        linked_names: set = set()

        for info in self.data.get("linked_players", {}).values():
            rid = (info.get("riot_id") or "").strip().lower()
            name = (info.get("name") or info.get("discord_name") or "").strip()
            if rid and name:
                riot_id_map[rid] = name
                linked_names.add(name.lower())

        for m in self.data.get("members", []):
            rid = (m.get("riot_id") or "").strip().lower()
            name = (m.get("name") or "").strip()
            if rid and name and rid not in riot_id_map:
                riot_id_map[rid] = name
                linked_names.add(name.lower())

        if not riot_id_map and not linked_names:
            return False

        updated = False
        for match in self.data.get("match_history", []):
            squad_list = match.setdefault("squad_players", [])
            lineup = match.get("lineup", {})
            for role, pdata in lineup.items():
                if not isinstance(pdata, dict):
                    continue
                raw_player = (pdata.get("player") or "").strip()
                raw_lower = raw_player.lower()

                if raw_lower in riot_id_map:
                    canonical_name = riot_id_map[raw_lower]
                    if pdata.get("player") != canonical_name or not pdata.get("is_squad"):
                        pdata["player"] = canonical_name
                        pdata["is_squad"] = True
                        updated = True
                    if canonical_name not in squad_list:
                        squad_list.append(canonical_name)
                        updated = True
                elif raw_lower in linked_names and pdata.get("is_squad") is False:
                    pdata["is_squad"] = True
                    if raw_player not in squad_list:
                        squad_list.append(raw_player)
                    updated = True

        return updated

    def is_lolers_member_entry(
        self,
        pdata: dict,
        match: Optional[dict] = None,
        allowed_names: Optional[set] = None,
    ) -> bool:
        """
        Returns True only if a match lineup participant is a verified @LOLers member.
        Excludes random matchmade players (`is_squad == False`).
        """
        if not isinstance(pdata, dict):
            return False
        name = (pdata.get("player") or "").strip()
        if not name:
            return False

        # Auto-tracked Riot matches explicitly mark non-LOLers randoms with is_squad=False
        if "is_squad" in pdata and not pdata.get("is_squad"):
            return False

        if match and "squad_players" in match and isinstance(match["squad_players"], list):
            squad_lower = {p.lower() for p in match["squad_players"] if isinstance(p, str)}
            if squad_lower and name.lower() not in squad_lower and not pdata.get("is_squad"):
                return False

        if allowed_names is not None:
            return name.lower() in allowed_names

        valid_names = self.get_valid_lolers_names()
        if valid_names and "is_squad" not in pdata:
            # For manually logged matches, allow if in valid_names or if not a raw RiotID stranger
            return True

        return True if pdata.get("is_squad", True) else False

    def get_linked_puuids(self) -> Dict[str, dict]:
        """
        Returns a dictionary mapping PUUID -> player info dict.
        """
        result = {}
        for uid, p in self.data.get("linked_players", {}).items():
            if p.get("puuid"):
                result[p["puuid"]] = p
        for m in self.data.get("members", []):
            if m.get("puuid") and m["puuid"] not in result:
                result[m["puuid"]] = m
        return result

    def is_match_logged(self, match_id: str) -> bool:
        """Checks if a match ID has already been recorded."""
        if not match_id:
            return False
        return any(m.get("match_id") == match_id for m in self.data.get("match_history", []))

    def log_match(self, match_record: dict) -> Tuple[bool, dict]:
        """
        Log a finished match record with de-duplication by match_id.
        Returns: (is_new, match_record)
        """
        match_id = match_record.get("match_id")
        if match_id and self.is_match_logged(match_id):
            for existing in self.data.get("match_history", []):
                if existing.get("match_id") == match_id:
                    return False, existing

        self.data.setdefault("match_history", []).insert(0, match_record)
        self.save()
        return True, match_record

    # Synergy Analytics Engine
    def get_pair_synergies(
        self,
        role_a: str,
        role_b: str,
        label_a: str,
        label_b: str,
        allowed_names: Optional[set] = None,
    ) -> List[dict]:
        """
        Generic pair synergy calculator with Bayesian confidence dampening for small sample sizes.
        Strictly considers pairs where BOTH players are @LOLers squad members.
        """
        pair_stats = {}

        for match in self.data.get("match_history", []):
            lineup = match.get("lineup", {})
            pa = lineup.get(role_a)
            pb = lineup.get(role_b)
            if not pa or not pb:
                continue

            # Strictly require both roles to be played by @LOLers members
            if not self.is_lolers_member_entry(pa, match, allowed_names):
                continue
            if not self.is_lolers_member_entry(pb, match, allowed_names):
                continue

            name_a = pa.get("player")
            name_b = pb.get("player")
            if not name_a or not name_b:
                continue

            pair_key = f"{name_a} ({label_a}) & {name_b} ({label_b})"
            if pair_key not in pair_stats:
                pair_stats[pair_key] = {
                    "pair": pair_key,
                    "player_a": name_a,
                    "player_b": name_b,
                    "label_a": label_a,
                    "label_b": label_b,
                    "games": 0,
                    "wins": 0,
                    "losses": 0,
                    "total_kills": 0,
                    "total_deaths": 0,
                    "total_assists": 0,
                    "champions_played": []
                }

            entry = pair_stats[pair_key]
            entry["games"] += 1
            if match.get("result") == "WIN":
                entry["wins"] += 1
            else:
                entry["losses"] += 1

            k = pa.get("kills", 0) + pb.get("kills", 0)
            d = pa.get("deaths", 0) + pb.get("deaths", 0)
            a = pa.get("assists", 0) + pb.get("assists", 0)
            entry["total_kills"] += k
            entry["total_deaths"] += d
            entry["total_assists"] += a
            entry["champions_played"].append(f"{pa.get('champion')} + {pb.get('champion')}")

        result = []
        for key, s in pair_stats.items():
            raw_win_rate = (s["wins"] / s["games"]) * 100 if s["games"] > 0 else 0
            kda = (s["total_kills"] + s["total_assists"]) / max(1, s["total_deaths"])

            # Confidence weighting: dampens 1-game wonders so duos with higher game volume rank appropriately
            confidence = min(1.0, s["games"] / 5.0)
            weighted_wr = (raw_win_rate * confidence) + (50.0 * (1.0 - confidence))

            score = round(min(100.0, (weighted_wr * 0.6) + (min(kda, 6.0) / 6.0 * 40.0)), 1)
            tier = "S Tier" if score >= 80 else ("A Tier" if score >= 65 else "B Tier")
            tag = "Lethal Core" if kda >= 4.0 else ("Objective Anchors" if raw_win_rate >= 60 else "Developing Chemistry")

            result.append({
                "pair": key,
                "player_a": s["player_a"],
                "player_b": s["player_b"],
                "games": s["games"],
                "wins": s["wins"],
                "losses": s["losses"],
                "win_rate": round(raw_win_rate, 1),
                "combined_kda": round(kda, 2),
                "synergy_score": score,
                "tier": tier,
                "tag": tag,
                "favorite_combo": max(set(s["champions_played"]), key=s["champions_played"].count) if s["champions_played"] else "N/A"
            })

        return sorted(result, key=lambda x: (x["games"] >= 3, x["synergy_score"], x["games"]), reverse=True)

    def get_botlane_synergies(self) -> List[dict]:
        res = self.get_pair_synergies("Bot", "Support", "ADC", "SUP")
        for item in res:
            item["adc"] = item.get("player_a")
            item["support"] = item.get("player_b")
        return res

    def get_mid_jungle_synergies(self) -> List[dict]:
        return self.get_pair_synergies("Mid", "Jungle", "MID", "JNG")

    def get_top_jungle_synergies(self) -> List[dict]:
        return self.get_pair_synergies("Top", "Jungle", "TOP", "JNG")

    def get_support_jungle_synergies(self) -> List[dict]:
        return self.get_pair_synergies("Support", "Jungle", "SUP", "JNG")

    def get_player_leaderboard(self, allowed_names: Optional[set] = None) -> List[dict]:
        """Calculates win rate and performance stats strictly for @LOLers members."""
        stats = {m["name"]: {"name": m["name"], "games": 0, "wins": 0, "kills": 0, "deaths": 0, "assists": 0, "mvps": 0, "roles": {}} for m in self.data.get("members", [])}

        for match in self.data.get("match_history", []):
            is_win = match.get("result") == "WIN"
            mvp = match.get("mvp")
            if mvp:
                # Only credit MVP if the player is a @LOLers squad member
                lineup_values = list(match.get("lineup", {}).values())
                mvp_entry = next((p for p in lineup_values if p.get("player") == mvp), {"player": mvp, "is_squad": True})
                if self.is_lolers_member_entry(mvp_entry, match, allowed_names):
                    if mvp not in stats:
                        stats[mvp] = {"name": mvp, "games": 0, "wins": 0, "kills": 0, "deaths": 0, "assists": 0, "mvps": 0, "roles": {}}
                    stats[mvp]["mvps"] += 1

            for role, pdata in match.get("lineup", {}).items():
                if not self.is_lolers_member_entry(pdata, match, allowed_names):
                    continue
                pname = pdata.get("player")
                if pname:
                    if pname not in stats:
                        stats[pname] = {"name": pname, "games": 0, "wins": 0, "kills": 0, "deaths": 0, "assists": 0, "mvps": 0, "roles": {}}
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

    # Living Synergy Thread State Management
    def get_synergy_thread_state(self, pair_key: str) -> Optional[dict]:
        """Returns stored {thread_id, message_id, updated_at} for a living synergy thread."""
        return self.data.get("synergy_threads", {}).get(pair_key)

    def set_synergy_thread_state(self, pair_key: str, thread_id: int, message_id: int) -> dict:
        """Saves the thread_id and living leaderboard message_id for a synergy option."""
        threads = self.data.setdefault("synergy_threads", {})
        state = {
            "pair_key": pair_key,
            "thread_id": thread_id,
            "message_id": message_id,
            "updated_at": datetime.now().isoformat(),
        }
        threads[pair_key] = state
        self.save()
        return state

    # User Feedback & GitHub Ticket History / Rate Limiting
    def can_submit_feedback(self, user_id: str, max_per_hour: int = 5) -> Tuple[bool, int]:
        """
        Checks whether a Discord user is within the hourly feedback ticket submission limit.
        Returns (allowed, remaining_quota).
        """
        now = datetime.now()
        history = self.data.get("feedback_history", [])
        recent_count = 0
        for item in history:
            if str(item.get("user_id")) != str(user_id):
                continue
            try:
                submitted_dt = datetime.fromisoformat(item["created_at"])
                if (now - submitted_dt).total_seconds() < 3600:
                    recent_count += 1
            except Exception:
                continue
        remaining = max(0, max_per_hour - recent_count)
        return recent_count < max_per_hour, remaining

    def record_feedback(
        self,
        user_id: str,
        user_name: str,
        category: str,
        title: str,
        description: str,
        issue_url: Optional[str],
        issue_number: Optional[int] = None,
        session_id: Optional[str] = None,
    ) -> dict:
        """Persists a submitted user feedback entry and its created GitHub issue metadata."""
        entry = {
            "user_id": str(user_id),
            "user_name": user_name,
            "category": category,
            "title": title,
            "description": description,
            "issue_url": issue_url,
            "issue_number": issue_number,
            "session_id": session_id,
            "created_at": datetime.now().isoformat(),
        }
        self.data.setdefault("feedback_history", []).insert(0, entry)
        self.save()
        return entry


