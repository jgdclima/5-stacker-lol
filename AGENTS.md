# 5-Stack Coordinator Development Guidelines

## 1. Session Viability & Quorum Invariants
- **Low Player Count Viability**: Sessions can proceed with 2, 3, 4, or 5 players (Duo, Trio, or Flex queues). Never automatically expire, cancel, or reject sessions simply because they did not reach 5 confirmed starters.
- **Session Lifecycle Transitions**:
  - `POLLING`: Recruiting players (< 5 confirmed starters).
  - `READY`: 5/5 players confirmed.
  - `IN_PROGRESS`: Scheduled start time reached (valid for both `POLLING` and `READY`).
  - `COMPLETED`: Session concluded manually (via button or `/end-session`) or automatically 4 hours after scheduled start time.
  - `CANCELLED`: Only explicitly triggered by the session creator or server administrator.

## 2. Discord API & Channel Permissions (Error 50001 / 50013)
- **Private Channel Access**: The `#5-stackers` channel is locked to `@LOLers` with `@everyone: view_channel=False`. The bot requires:
  - The `@LOLers` role (or an explicit overwrite for the bot role) with `View Channel`, `Send Messages`, `Embed Links`, and `Manage Messages`.
  - Slash command interaction responses bypass channel overrides, but standard REST endpoints (`channel.send`, `message.edit`, `message.delete`) fail with `403 Forbidden (50001): Missing Access` if the bot lacks channel view access.
- **No Silent Exception Swallowing**: Never use bare `try: ... except Exception: pass` around `message.edit()`, `message.delete()`, or `channel.send()`. Always log errors or catch `discord.errors.Forbidden` to display helpful setup guidance to the user.

## 3. Discord UI & Component Patterns
- **In-Place Ephemeral Updates**: When a user makes a selection on an ephemeral dropdown or button, always dismiss the component in-place using `await interaction.response.edit_message(content=..., view=None)`. Never send a secondary ephemeral message that leaves the previous dropdown dangling.
- **Creator Authorization Checks**: Destructive or terminating actions (Cancel Session, End Session) must strictly verify that `interaction.user` is either the session organizer (`session['creator_id']` / `session['creator']`) or a server administrator.

## 4. Bot Relaunch & Slash Command Syncing
- **Relaunch Script (`relaunch.py` / `relaunch.bat`)**: After modifying bot code, run `.\relaunch.bat` (or `python relaunch.py`) to cleanly terminate any existing `bot.py` instances, launch the updated bot in the background (`data/bot.log`), and verify startup.
- **Conditional Slash Command Registration**: `bot.py` and `relaunch.py` compute a deterministic SHA-256 hash of all `app_commands` schemas (`data/commands_state.json`) and only call `await bot.tree.sync()` when slash command names, descriptions, options, choices, or permissions change (or when `--sync` / `FORCE_COMMAND_SYNC=1` is passed).

## 5. Channel Noise Reduction & Living Threads Architecture
- **Hybrid Session Card + Per-Session Thread**: Each `/session` posts exactly **1 living Session Card** in `#5-stackers` (edited in-place via `notify_session` for all RSVPs, `/edit-session` reschedules, `/end-session`, `/cancel-session`, `session_matches` W-L tally, and `activity_log`) and creates **1 attached Discord Thread** (`session['thread_id']`) for notifications that require real Discord pings (5/5 Lobby Ready, Bench Auto-Promotion, Reschedule alerts, 15-Minute Countdown) and full Match Recap embeds.
- **Living Synergy Threads**: The bot maintains 4 living threads in `#5-stackers` (`botlane`, `mid_jungle`, `top_jungle`, `support_jungle` tracked in `data['synergy_threads']`) whose leaderboard messages are edited in-place whenever new match data is processed.
- **Ephemeral Info Commands**: All read-only/lookup commands (`/sessions`, `/queue-check`, `/synergy`, `/botlane`, `/roster`, `/link-riot`, `/sync-matches`) default to `ephemeral=True` with an optional `public: bool = False` parameter.
- **Automated GitHub Feedback Tickets**: Users can submit feedback via `/feedback` or the **💡 Feedback** button on session cards (`FeedbackModal`), which automatically opens a GitHub Issue on `jgdclima/5-stacker-lol` via `github_tickets.py`.
