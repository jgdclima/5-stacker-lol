# 🎮 League of Legends 5-Stack Coordinator Discord Bot

A dedicated Discord bot designed to organize League of Legends 5-man premade sessions for your friend group, automatically manage 5-player quorums, detect Riot's official Ranked 5s weekend windows with seamless Ranked Flex fallback, and track in-depth chemistry stats like Botlane Synergy.

---

## 🔒 Server Configuration & Strict Channel Lock

1. **Text Channel Lockdown (`#5-stackers`)**:
   - All session coordination, polls, alerts, and commands are strictly locked to the **`#5-stackers`** text channel.
   - The bot **will not interact with, reply to, or message any other text channel** in your Discord server.
   - Any commands attempted outside `#5-stackers` are silently rejected with an ephemeral notice.

2. **Roster Definition by Role (`@LOLers`)**:
   - The squad roster is defined by the **`@LOLers`** role in your server.
   - Only members with the **`@LOLers`** role can propose sessions, RSVP to the starting 5 or substitute bench, and appear on the official `/roster`.
   - When a 5-player quorum is reached, the bot alerts the starting 5 and mentions `@LOLers` inside `#5-stackers`.

---

## 🌟 Key Features

* **Flexible 5-Player Quorum & Automatic Bench Promotion**:
  - Any 5 players out of your group can form a starting squad.
  - When the 5th player RSVPs with **✅ Join 5-Stack**, the bot instantly fires a **Lobby Ready** alert notifying the starting five.
  - Subsequent signups (6th to 10th) are placed onto the **Substitutes / Bench**.
  - **Auto-Promotion**: If a starting 5 player clicks **❌ Can't Make It**, the first bench substitute is automatically promoted to the starting roster without manual re-coordination.

* **Natural Language Scheduling & Weekend Ranked 5s Detection**:
  - Schedule sessions naturally using phrases like `"Tonight 8:30pm"`, `"Friday 9pm"`, or `"Tomorrow 7pm"`.
  - Automatically evaluates whether the *intended session time* falls inside Riot's weekend **Ranked 5s** tournament draft queue windows (Friday, Saturday, Sunday 8:00 PM – 1:00 AM local time).
  - Automatically falls back to **Ranked Flex (5-stack)** for weekday sessions.

* **15-Minute Countdown Reminders**:
  - Automatically alerts the 5 confirmed starters in `#5-stackers` exactly 15 minutes before game time so the squad can queue up on time.

* **Session Rescheduling & Participant Alerts (`/edit-session`)**:
  - Session creators or admins can reschedule any planned session. The bot re-evaluates queue modes, updates the session card, and pings everyone currently signed up with an availability alert.

* **Multi-Pair Chemistry & Synergy Engine (`/synergy`)**:
  - Tracks pairwise chemistry across key map partnerships in 4 auto-updating Living Threads:
    - **Botlane** (Bot + Support)
    - **Mid + Jungle** (2v2 Core Playmakers)
    - **Top + Jungle** (Topside Gank / Dive Synergy)
    - **Support + Jungle** (Roam & Vision / Objective Control)
  - Powered by a holistic role- and champion-aware rating engine with Bayesian confidence dampening and a 3-game minimum leaderboard threshold.

* **Interactive Multi-Select Discord UI**:
  - Persistent buttons that survive bot reboots without failing.
  - Native **Multi-Select Role Dropdown**: Players can select 1 to 5 role preferences (e.g. `Mid` + `Bot`).

---

## 📊 Holistic Rating & Synergy System Overview

All post-game player ratings, Match MVP selections, and pairwise synergy scores are computed by [`rating_engine.py`](rating_engine.py) using rich telemetry from Riot's **Match-v5 API** (including participant stats and `challenges` sub-metrics).

### 1. Individual Player Rating (`0–100`) & Match MVP Selection

Instead of judging every player strictly by KDA or raw damage, each participant is evaluated across **6 Performance Pillars**:

| Pillar | Key Riot Match-v5 & `challenges` Metrics |
| :--- | :--- |
| **1. Combat & KDA Efficiency** | KDA ratio, Kill Participation (`killParticipation`) benchmarked by role, deaths per 5 min survival rate, `soloKills`, `outnumberedKills`, and carry kill-share conversion. |
| **2. Damage & Carry Output** | Damage to champions per minute (DPM) benchmarked against champion kit archetype, plus team damage share (`teamDamagePercentage`). |
| **3. Objective & Structural Pressure** | Turret damage, `turretTakedowns`, `turretPlatesTaken`, objective damage, `dragonTakedowns`, `baronTakedowns`, `riftHeraldTakedowns`, `voidMonsterKill` (Void Grubs), and `epicMonsterSteals`. |
| **4. Frontline & Durability** | Self-mitigated damage per minute (`damageSelfMitigated`), team damage taken share (`damageTakenOnTeamPercentage`), and tanking efficiency `(damage_taken + mitigated) / deaths`. |
| **5. Utility, CC & Team Enablement** | Crowd control score per minute (`timeCCingOthers`), effective ally healing & shielding (`effectiveHealAndShielding`), `saveAllyFromDeath`, `immobilizeAndKillWithAlly`, and `pickKillWithAlly`. |
| **6. Vision, Economy & Lane Dominance** | Role-normalized CS/min and Vision Score/min (`visionScore`), plus laning leads (`laningPhaseGoldExpAdvantage`, `maxCsAdvantageOnLaneOpponent`, `controlWardsPlaced`, `wardTakedowns`). |

#### Blended Role (55%) + Champion Kit Archetype (45%) Weighting
A player's pillar weights are dynamically blended from **55% Assigned Role** (`Top`, `Jungle`, `Mid`, `Bot`, `Support`) and **45% Champion Kit Archetype** (`marksman`, `mage`, `assassin`, `splitpusher`, `bruiser`, `tank`, `enchanter`, `catcher`):

| Role / Archetype | Combat | Damage | Objective | Frontline | Utility | Macro / Vision |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Role: Top** | 22% | 20% | 20% | 20% | 6% | 12% |
| **Role: Jungle** | 24% | 14% | 28% | 12% | 10% | 12% |
| **Role: Mid** | 28% | 30% | 12% | 5% | 10% | 15% |
| **Role: Bot (ADC)** | 26% | 36% | 14% | 4% | 4% | 16% |
| **Role: Support** | 20% | 6% | 8% | 10% | 32% | 24% |
| *Archetype: Marksman* | 30% | 38% | 12% | 0% | 0% | 20% |
| *Archetype: Mage* | 28% | 36% | 8% | 0% | 14% | 14% |
| *Archetype: Assassin* | 40% | 34% | 8% | 0% | 6% | 12% |
| *Archetype: Splitpusher* | 22% | 20% | 34% | 8% | 0% | 16% |
| *Archetype: Bruiser* | 28% | 22% | 16% | 20% | 4% | 10% |
| *Archetype: Tank* | 18% | 6% | 12% | 34% | 22% | 8% |
| *Archetype: Enchanter* | 18% | 4% | 6% | 4% | 46% | 22% |
| *Archetype: Catcher* | 22% | 6% | 8% | 16% | 30% | 18% |

* **Why Blending Matters**: An Enchanter Support (`Soraka`/`Lulu`) who goes `1/1/24` with 14k healing and 2.5 vision/min, or a Splitpusher Top (`Yorick`/`Tryndamere`) who takes 5 turrets and 14k structural damage, can earn an `S`/`S+` rating and **Match MVP** on equal footing with a high-kill Marksman or Assassin—while off-meta flex picks (e.g., `Taliyah` Jungle or `Thresh` Top) are automatically evaluated on both their map position and their champion's kit.
* **Excess-Death Liability & Outcome Adjustment**: Exceeding `2.0` deaths per 10 minutes applies a scaling liability penalty (stricter for fragile carry archetypes), and match outcome adds `+2.5` for a Win or `-1.5` for a Loss.
* **Letter Grades & Standout Badges**:
  - **Grades**: `S+` ($\ge 88$), `S` ($\ge 80$), `A+` ($\ge 73$), `A` ($\ge 65$), `B` ($\ge 55$), `C` ($< 55$).
  - **Standout Badges**: Automatically awarded on match recaps (`Splitpush Titan`, `Objective Commander`, `Peel & Enchanter Carry`, `Unkillable Frontline`, `Vision Oracle`, `Hypercarry DPS`, `Map Omnipresence`, `Deathless Precision`).
* **Strict `@LOLers` MVP Selection**: Only verified `@LOLers` squad members (`is_squad=True`) are eligible to be named Match MVP.

---

### 2. Pairwise Chemistry & Synergy Rating (`0–100`)

The 4 synergy leaderboards (`Bot + Support`, `Mid + Jungle`, `Top + Jungle`, `Support + Jungle`) evaluate each `@LOLers` duo across 4 dimensions:

$$\text{Synergy Score} = 0.42 \times \text{Bayesian WR} + 0.24 \times \text{Dampened Duo Rating} + 0.14 \times \text{Pair Coordination} + 0.20 \times \text{Duo KDA}$$

1. **Bayesian-Dampened Win Rate (42%)**: Blends the duo's raw win rate toward a `50%` prior over a 5-game confidence ramp ($\text{confidence} = \min(1.0, \text{games}/5)$) so 1- or 2-game samples cannot artificially outrank established partnerships.
2. **Role & Champion-Adjusted Duo Rating (24%)**: The mean of both partners' holistic `0–100` individual match ratings across all games played together in those two roles (dampened toward a `62.0` baseline for $< 3$ games).
3. **Position-Pair Coordination Score (14%)**: Measures how effectively the two specific positions executed their partnership responsibilities together:
   - **Bot + Support**: Combined kill participation, ADC damage/min conversion, Support vision/min, and Support peel (`effective_heal_shield` + CC score).
   - **Mid + Jungle**: 2v2 skirmish participation, joint CC/pick kills (`immobilizeAndKillWithAlly` + `pickKillWithAlly`), and neutral objective control (Dragons, Void Grubs, Heralds, Barons).
   - **Top + Jungle**: Topside pressure (`turretTakedowns`, Rift Heralds, Void Grubs), joint CC/pick kills, and kill participation.
   - **Support + Jungle**: Combined vision control per minute (`visionScore / min`), roam pick kills, and kill participation.
4. **Combined Duo KDA Efficiency (20%)**: Normalized combined $(K + A) / \max(1, D)$ capped at `6.0` KDA $= 100$.

#### Synergy Tiers & Leaderboard Eligibility
* **Tiers**: `S Tier` ($\ge 80.0$), `A Tier` ($65.0\text{–}79.9$), `B Tier` ($< 65.0$).
* **Dynamic Chemistry Tags**: Duos earn contextual tags based on their strengths (`2v8 Bot Kingdom`, `Map Terror 2v2`, `Topside Raidbosses`, `Vision & Roam Lords`, `Lethal Core`, `Objective Anchors`, `High-Impact Duo`, or `Developing Chemistry`).
* **Strict Eligibility Rules**:
  - **Both** players in the pair must be `@LOLers` members (`is_squad=True`).
  - A pair must have played **at least 3 games together** (`MIN_SYNERGY_GAMES = 3`) in that specific role combination to appear on the chemistry leaderboards.

---

## 🚀 Quick Setup & Installation

### Step 1: Create a Discord Application
1. Go to the [Discord Developer Portal](https://discord.com/developers/applications).
2. Click **New Application**, name it `League 5-Stack Coordinator`.
3. In the left sidebar, click **Bot**:
   - Click **Reset Token** and copy your bot token into `.env`.
   - Under **Privileged Gateway Intents**, enable **Server Members Intent** (and optionally **Message Content Intent**).
4. In the left sidebar, click **Installation**:
   - Under **Installation Contexts**, ensure **Guild Install** is checked (required to add the bot to servers).
   - Click **Save Changes**.
5. In the left sidebar, click **OAuth2 > URL Generator**:
   - Under **Scopes**, check `bot`.
   - Under **Bot Permissions**, check:
     - `View Channels`
     - `Send Messages`
     - `Embed Links`
     - `Read Message History`
     - `Use External Emojis`
     - `Add Reactions`
   - Copy the generated URL and open it in your browser to invite the bot to your Discord server.

### Step 2: Set Up Server Channel & Role
1. In your Discord server, create a text channel named **`#5-stackers`**.
2. Create a server role named **`LOLers`** and assign it to the group of friends who play League.

### Step 3: Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Edit `.env`:
```env
DISCORD_BOT_TOKEN=your_actual_bot_token_here
COORDINATION_CHANNEL=5-stackers
ROSTER_ROLE=LOLers
SERVER_TIMEZONE=America/Vancouver

# Riot Games Developer API (https://developer.riotgames.com/)
RIOT_API_KEY=RGAPI-your-riot-api-key-here
RIOT_REGION=americas
AUTO_TRACKING_INTERVAL_MINUTES=2
```

### Step 4: Install Dependencies & Run
```bash
pip install -r requirements.txt
python bot.py
```
When started, the bot will log in, register slash commands, start the 15-minute reminder poller, and begin auto-tracking squad matches!

To restart the bot after making code changes (and automatically re-register slash commands with Discord only if command definitions changed):
```bash
# Windows (CMD / PowerShell)
.\relaunch.bat

# Cross-platform Python
python relaunch.py

# Optional flags:
#   --sync / --force-sync : Force Discord slash command re-registration even if unchanged
#   --check-only          : Inspect pending slash command changes without restarting
#   --stop-only           : Stop running bot.py instance(s) and exit
#   --foreground (-f)     : Keep bot running attached in the foreground terminal
```

---

## 🕹️ Command Reference (Restricted to `#5-stackers`)

| Command | Description |
| :--- | :--- |
| `/session [time_window]` | Propose a new session in `#5-stackers` using natural language (e.g. `'Tonight 8:30pm'`, `'Friday 9pm'`). Creates 1 living Session Card + 1 attached Session Thread. |
| `/edit-session <id> <new_time>` | Reschedule a planned session in-place on the Session Card and alert signed-up players in the Session Thread. |
| `/cancel-session <id>` | Cancel an active session in-place and archive its thread. |
| `/end-session <id>` | Conclude an active session in-place and archive its thread. |
| `/sessions [public]` | View active and recent sessions (ephemeral by default; set `public: True` to share). |
| `/queue-check [public]` | Check current Ranked 5s window status and next opening (ephemeral by default). |
| `/synergy <pair_type> [public]` | View duo chemistry across Botlane, Mid + Jungle, Top + Jungle, or Support + Jungle (ephemeral by default, links to the living Synergy Thread). |
| `/botlane [public]` | Quick shortcut to display Bot + Support duo chemistry ratings and win rates (ephemeral by default). |
| `/roster [public]` | View all server members who have the `@LOLers` role and their match stats (ephemeral by default). |
| `/link-riot <riot_id> [public]` | Link your Riot ID (`GameName#TagLine`) to your Discord account for automatic match tracking. |
| `/sync-matches [public]` | Manually trigger an immediate Riot API check for recent squad matches and update living synergy threads. |
| `/log-match ... [public]` | Manually record a finished match outcome, botlane combo, KDA, and MVP, updating living synergy threads. |
| `/feedback [category]` | Open a modal form to submit a Bug Report, Feature Request, or UX idea that automatically creates a GitHub Issue on `jgdclima/5-stacker-lol` (also accessible via the **💡 Feedback** button on session cards). |

---

## 📜 Riot Developer Portal Application Description

When submitting an application for a **Personal API Key** / **Personal Project** on the [Riot Developer Portal](https://developer.riotgames.com/), you can use or adapt the template below for your product description fields:

```markdown
### Product Name
League 5-Stack Coordinator

### Product Type
Discord Bot / Community Gaming Tool (Personal / Non-Commercial)

### Product Summary
League 5-Stack Coordinator is a non-commercial Discord bot built for a private community of League of Legends players. It organizes 5-player game nights, manages starting and substitute rosters, evaluates game windows (such as Ranked 5s / Ranked Flex), and provides post-game team chemistry metrics (such as ADC & Support duo synergy ratings) without requiring manual statistical entry.

### Detailed Product Description & User Workflow
1. User Opt-In & Account Linking:
   - Players in our Discord server explicitly opt in by issuing `/link-riot riot_id:GameName#TagLine`.
   - The bot calls the `ACCOUNT-V1` endpoint to resolve the provided Riot ID to a permanent PUUID and stores this mapping in a local data store. No passwords, session tokens, or sensitive account credentials are ever requested or stored.

2. Match Detection & Post-Game Analytics:
   - When our Discord group organizes a 5-stack session, the bot monitors for newly concluded games involving the linked squad members.
   - Using the `MATCH-V5` endpoints, the bot fetches the most recent match IDs for linked players and retrieves match details.
   - If two or more linked squad members played on the same team (in Normals, Ranked Flex, Ranked 5s, or Clash), the bot extracts end-game metrics: team outcome (Win/Loss), champions played, role positions, K/D/A, and team kill participation.
   - Matches are indexed and de-duplicated by Riot's unique match ID to prevent duplicate requests and eliminate redundant processing.

3. Community Metrics & Synergy Tracking:
   - The bot calculates pairwise botlane chemistry (ADC + Support combined win rates, average KDA, and champion combinations) and updates an internal community leaderboard accessible via `/roster` and `/botlane`.
   - Match results are broadcast exclusively to a designated channel (`#5-stackers`) in our server as a summary embed.

### API Endpoints Used & Justification
- `ACCOUNT-V1` (`/riot/account/v1/accounts/by-riot-id/{gameName}/{tagLine}`):
  - Justification: Required to convert user-provided Riot IDs into immutable PUUIDs during the `/link-riot` command, ensuring tracking persists across summoner name changes.
- `MATCH-V5` (`/lol/match/v5/matches/by-puuid/{puuid}/ids`):
  - Justification: Used to poll recent match history (count: 5) for registered squad players to identify newly completed group matches.
- `MATCH-V5` (`/lol/match/v5/matches/{matchId}`):
  - Justification: Fetches the match statistics (participants, queueId, teamId, win/loss, role, kills, deaths, assists, championName) necessary to generate the post-match summary and compute duo synergy stats.

### Rate Limiting & Architecture
- Polling is throttled via an asynchronous task loop running once every 2 minutes.
- Only accounts that have explicitly linked their Riot ID are queried.
- All match IDs are locally cached, ensuring each match detail payload is requested only once.
- Total request volume averages under 10–15 calls per polling cycle, remaining well below Riot's personal development limit of 20 requests/second and 100 requests per 2 minutes.

### Riot Developer Policy & Terms of Service Compliance
- Non-Commercial: Free of charge, with no paywalls, subscriptions, donations, or advertisements.
- Competitive Integrity: Does not provide in-game overlays, live scouting, opponent MMR tracking, or real-time advantages during an active match.
- Privacy & Consent: Only collects data for users who voluntarily initiate the `/link-riot` command.
- Legal Disclaimer: Includes the mandatory Riot Games legal disclaimer on all documentation and Discord embeds.
```

---

## ⚖️ Legal Disclaimer
League 5-Stack Coordinator isn't endorsed by Riot Games and doesn't reflect the views or opinions of Riot Games or anyone officially involved in producing or managing Riot Games properties. Riot Games, and all associated properties are trademarks or registered trademarks of Riot Games, Inc.


