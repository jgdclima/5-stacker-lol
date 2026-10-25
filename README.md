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

* **Flexible 5-Player Quorum Coordination**:
  - Any 5 players out of your group can form a squad.
  - When the 5th player RSVPs with **✅ Join 5-Stack**, the bot instantly fires a **Lobby Ready** alert notifying the starting five.
  - Subsequent signups (6th to 10th) are automatically placed onto the **Substitutes / Bench** roster in case someone needs to step out.

* **Ranked 5s Window Detection & Ranked Flex Fallback**:
  - Automatically checks if your session falls within Riot's weekend **Ranked 5s** tournament draft queue windows (Friday, Saturday, Sunday 8:00 PM – 1:00 AM local time).
  - If outside the window or during weekdays, the bot automatically configures the session for **Ranked Flex (5-stack)** so your group never misses a game night.

* **Botlane Synergy & Chemistry Tracking**:
  - Calculates pairwise chemistry when two friends play **Bot (ADC)** and **Support** together.
  - Tracks 2v2 Duo Win Rate, Combined KDA, Kill Participation, Synergy Tier (S+/S/A/B), and signature champion combos.

* **Interactive Discord UI**:
  - One-click buttons for RSVP: **Join 5-Stack**, **Sub / Bench**, **Can't Make It**.
  - Role preference modal to declare Top, Jungle, Mid, Bot, Support, or Fill.

---

## 🚀 Quick Setup & Installation

### Step 1: Create a Discord Application
1. Go to the [Discord Developer Portal](https://discord.com/developers/applications).
2. Click **New Application**, name it `League 5-Stack Coordinator`.
3. In the left sidebar, click **Bot**:
   - Click **Reset Token** and copy your bot token.
   - Under **Privileged Gateway Intents**, enable **Server Members Intent** and **Message Content Intent**.
4. In the left sidebar, click **OAuth2 > URL Generator**:
   - Under **Scopes**, check `bot` and `applications.commands`.
   - Under **Bot Permissions**, check:
     - `Send Messages`
     - `Embed Links`
     - `Read Message History`
     - `Use Slash Commands`
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
```

### Step 4: Install Dependencies & Run
```bash
pip install -r requirements.txt
python bot.py
```
When started, the bot will log in and register all application slash commands with Discord!

---

## 🕹️ Command Reference (Restricted to `#5-stackers`)

| Command | Description |
| :--- | :--- |
| `/session [time_window]` | Propose a new session in `#5-stackers`. Evaluates queue mode (Ranked 5s vs Flex fallback) and opens RSVP buttons. |
| `/queue-check` | Check current Ranked 5s window status, whether it's open, and when the next window unlocks. |
| `/botlane` | Display the top Bot + Support duo chemistry leaderboard and synergy ratings. |
| `/roster` | View all server members who have the `@LOLers` role and their match stats. |
| `/log-match` | Record a finished 5-stack match outcome, botlane combo, KDA, and MVP. |
