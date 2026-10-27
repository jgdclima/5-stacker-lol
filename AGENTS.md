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
