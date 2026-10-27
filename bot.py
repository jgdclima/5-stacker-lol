"""
League of Legends 5-Stack Coordinator Discord Bot.
Enforces:
1. All session coordination strictly locked to text channel: #5-stackers.
   The bot ignores and does not interact with or post to any other channel.
2. The active roster is strictly defined by the "LOLers" role.
   Only members with the @LOLers role can organize, RSVP, or be listed on the roster.
"""

import os
import sys
import json
import hashlib
from typing import Optional, List, Dict, Any
import discord
from discord import app_commands
from discord.ext import commands, tasks
from datetime import datetime
import uuid
from dotenv import load_dotenv

from schedule_checker import RankedSchedule
from data_manager import StatsManager
from riot_api import RiotAPIClient
from github_tickets import GitHubTicketClient

load_dotenv()

# --- Configuration & Channel/Role Locking ---
COORDINATION_CHANNEL = os.getenv("COORDINATION_CHANNEL", "5-stackers")
ROSTER_ROLE_NAME = os.getenv("ROSTER_ROLE", "LOLers")
SERVER_TIMEZONE = os.getenv("SERVER_TIMEZONE", "America/Vancouver")
RANKED_5S_START_HOUR = int(os.getenv("RANKED_5S_START_HOUR", "20"))
RANKED_5S_END_HOUR = int(os.getenv("RANKED_5S_END_HOUR", "1"))

# Riot Games Developer API Setup
RIOT_API_KEY = os.getenv("RIOT_API_KEY", "")
RIOT_REGION = os.getenv("RIOT_REGION", "americas")
AUTO_TRACKING_INTERVAL = int(os.getenv("AUTO_TRACKING_INTERVAL_MINUTES", "2"))
riot_client = RiotAPIClient(api_key=RIOT_API_KEY, region=RIOT_REGION)

# Bot Setup
intents = discord.Intents.default()
if os.getenv("ENABLE_PRIVILEGED_INTENTS", "false").lower() == "true":
    intents.message_content = True
    intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

scheduler = RankedSchedule(
    timezone_str=SERVER_TIMEZONE,
    start_hour=RANKED_5S_START_HOUR,
    end_hour=RANKED_5S_END_HOUR,
)
stats_mgr = StatsManager()
github_client = GitHubTicketClient()


def has_lolers_role(user: discord.User | discord.Member) -> bool:
    """Check if a Discord user possesses the required @LOLers role."""
    if not isinstance(user, discord.Member):
        return False
    return any(r.name.lower() == ROSTER_ROLE_NAME.lower() for r in user.roles)


def is_allowed_coordination_channel(channel: Any) -> bool:
    """Check if a channel is #5-stackers or a thread inside #5-stackers."""
    if not channel:
        return False
    if getattr(channel, "name", None) == COORDINATION_CHANNEL:
        return True
    parent = getattr(channel, "parent", None)
    if parent and getattr(parent, "name", None) == COORDINATION_CHANNEL:
        return True
    return False


async def check_channel_restriction(interaction: discord.Interaction) -> bool:
    """
    Enforces that all slash commands, button clicks, and modal submissions
    occur strictly within the #5-stackers text channel (or its threads).
    The bot will not interact with or message any other channel.
    """
    if not is_allowed_coordination_channel(interaction.channel):
        await interaction.response.send_message(
            f"🔒 **Channel Restricted**: All 5-stack session coordination is locked to **#{COORDINATION_CHANNEL}**.\n"
            f"This bot does not interact with or message other channels.",
            ephemeral=True
        )
        return False
    return True


# --- Global Interaction Check: Lock to #5-stackers only ---
bot.tree.interaction_check = check_channel_restriction


@bot.event
async def on_message(message: discord.Message):
    """
    Ensure the bot completely ignores any messages or prefix commands
    outside of the #5-stackers text channel (or its threads).
    """
    if message.author.bot:
        return
    if not is_allowed_coordination_channel(message.channel):
        return
    await bot.process_commands(message)


# --- Interactive Discord UI: Feedback Modal, Multi-Select Role Dropdown & Persistent RSVP View ---

def is_session_organizer_or_admin(user: discord.User | discord.Member, session: dict) -> bool:
    """Check if the user is the creator of the session or has guild admin permissions."""
    if not isinstance(user, discord.Member):
        return False
    if user.guild_permissions.administrator or user.guild_permissions.manage_guild or user.guild_permissions.manage_channels:
        return True
    if session.get("creator_id") and str(user.id) == str(session["creator_id"]):
        return True
    creator_name = session.get("creator", "").lower()
    if user.display_name.lower() == creator_name or user.name.lower() == creator_name:
        return True
    return False


class FeedbackModal(discord.ui.Modal, title="💡 Bot Feedback & GitHub Ticket"):
    """Modal allowing users to submit bugs, feature ideas, or UX feedback directly as GitHub Issues."""

    def __init__(self, default_category: str = "Feature Request", session_id: Optional[str] = None):
        super().__init__(timeout=300)
        self.session_id = session_id

        self.category_input = discord.ui.TextInput(
            label="Category (Bug / Feature / UX)",
            placeholder="e.g. Bug, Feature Request, or UX",
            default=default_category,
            max_length=40,
            required=True,
        )
        self.title_input = discord.ui.TextInput(
            label="Short Summary / Ticket Title",
            placeholder="Concise summary of the issue or idea",
            max_length=120,
            required=True,
        )
        self.description_input = discord.ui.TextInput(
            label="Details / Steps to Reproduce",
            style=discord.TextStyle.paragraph,
            placeholder="Describe what happened, what you expected, or how this feature should work...",
            max_length=1500,
            required=True,
        )
        self.add_item(self.category_input)
        self.add_item(self.title_input)
        self.add_item(self.description_input)

    async def on_submit(self, interaction: discord.Interaction):
        if not has_lolers_role(interaction.user):
            await interaction.response.send_message(
                f"⛔ Only members with the **@{ROSTER_ROLE_NAME}** role can submit bot feedback tickets.",
                ephemeral=True,
            )
            return

        allowed, remaining = stats_mgr.can_submit_feedback(str(interaction.user.id))
        if not allowed:
            await interaction.response.send_message(
                "⏳ You have reached the hourly feedback submission limit (5 tickets/hour). Please try again shortly!",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)
        res = await github_client.create_issue(
            category=self.category_input.value,
            title=self.title_input.value,
            description=self.description_input.value,
            reporter_name=interaction.user.display_name,
            reporter_id=str(interaction.user.id),
            session_id=self.session_id,
        )

        stats_mgr.record_feedback(
            user_id=str(interaction.user.id),
            user_name=interaction.user.display_name,
            category=self.category_input.value,
            title=self.title_input.value,
            description=self.description_input.value,
            issue_url=res.get("url"),
            issue_number=res.get("number"),
            session_id=self.session_id,
        )

        if res.get("success") and res.get("url"):
            issue_num_str = f"#{res['number']}" if res.get("number") else "Issue"
            await interaction.followup.send(
                f"✅ **GitHub Ticket Created!**\n"
                f"• **Ticket**: [{issue_num_str} — {res['title']}]({res['url']})\n"
                f"Thanks for helping improve the 5-Stack Coordinator!",
                ephemeral=True,
            )
        else:
            err = res.get("error") or "Unknown error"
            await interaction.followup.send(
                f"⚠️ **Feedback recorded locally**, but automatic GitHub ticket creation encountered an error:\n"
                f"`{err}`",
                ephemeral=True,
            )


async def fetch_session_message(
    session: dict,
    guild: Optional[discord.Guild] = None,
    fallback_msg: Optional[discord.Message] = None,
) -> Optional[discord.Message]:
    """Fetch the canonical Session RSVP message in #5-stackers."""
    if fallback_msg:
        return fallback_msg
    if not session or not session.get("channel_id") or not session.get("message_id"):
        return None
    try:
        ch = guild.get_channel(session["channel_id"]) if guild else None
        if not ch:
            ch = bot.get_channel(session["channel_id"]) or await bot.fetch_channel(session["channel_id"])
        if ch:
            return await ch.fetch_message(session["message_id"])
    except Exception as e:
        print(f"[SessionMessage] Could not fetch session message: {e}")
    return None


async def ensure_session_thread(
    session: dict,
    guild: Optional[discord.Guild] = None,
    session_message: Optional[discord.Message] = None,
) -> Optional[discord.Thread]:
    """
    Ensures the session has an attached Discord Thread in #5-stackers.
    Returns the Thread object (unarchiving it if needed).
    """
    if not session:
        return None

    thread_id = session.get("thread_id")
    if thread_id:
        try:
            thread = guild.get_thread(thread_id) if guild else None
            if not thread:
                thread = bot.get_channel(thread_id) or await bot.fetch_channel(thread_id)
            if isinstance(thread, discord.Thread):
                if thread.archived:
                    await thread.edit(archived=False)
                return thread
        except Exception as e:
            print(f"[SessionThread] Could not fetch existing thread {thread_id}: {e}")

    msg = await fetch_session_message(session, guild, session_message)
    if not msg:
        return None

    thread_name = f"🎮 Session {session.get('session_id')} — {session.get('scheduled_time', 'Lobby')}"[:95]
    try:
        thread = await msg.create_thread(name=thread_name, auto_archive_duration=1440)
        stats_mgr.set_session_thread(session["session_id"], thread.id)
        return thread
    except discord.errors.HTTPException as e:
        # If a thread already exists on this message (e.g. error 160004), try guild threads
        if guild:
            found = discord.utils.get(guild.threads, id=msg.id)
            if found:
                stats_mgr.set_session_thread(session["session_id"], found.id)
                return found
        print(f"[SessionThread] Could not create thread for session {session.get('session_id')}: {e}")
        return None
    except Exception as e:
        print(f"[SessionThread] Error creating session thread: {e}")
        return None


async def notify_session(
    session: dict,
    activity_entry: Optional[str] = None,
    thread_content: Optional[str] = None,
    thread_embed: Optional[discord.Embed] = None,
    guild: Optional[discord.Guild] = None,
    session_message: Optional[discord.Message] = None,
    remove_view: bool = False,
    archive_thread: bool = False,
) -> None:
    """
    Hybrid Session Update:
    1. Records an entry in the session's in-place Activity Log.
    2. Ensures the session's attached thread exists (when sending a thread alert/recap).
    3. Edits the single canonical Session Card in #5-stackers in-place.
    4. Posts any ping or detailed Match Recap embed inside the session's thread.
    """
    if not session:
        return

    s_id = session.get("session_id")
    if activity_entry and s_id:
        updated = stats_mgr.append_session_activity(s_id, activity_entry)
        if updated:
            session = updated

    msg = await fetch_session_message(session, guild, session_message)
    thread = None
    if thread_content or thread_embed or not archive_thread:
        thread = await ensure_session_thread(session, guild, msg)

    if msg:
        try:
            embed = build_session_embed(session, guild)
            new_view = None if remove_view else SessionRSVPView(s_id)
            await msg.edit(embed=embed, view=new_view)
        except Exception as e:
            print(f"[SessionUpdate] Error editing session card {s_id}: {e}")

    if (thread_content or thread_embed) and thread:
        try:
            await thread.send(content=thread_content, embed=thread_embed)
        except Exception as e:
            print(f"[SessionThread] Error sending notification to thread {thread.id}: {e}")

    if archive_thread and thread:
        try:
            await thread.edit(archived=True)
        except Exception as e:
            print(f"[SessionThread] Error archiving thread {thread.id}: {e}")


class RoleSelectView(discord.ui.View):
    """Ephemeral view allowing players to multi-select up to 5 role preferences."""
    def __init__(self, session_id: str, action_type: str, session_message: Optional[discord.Message] = None):
        super().__init__(timeout=120)
        self.session_id = session_id
        self.action_type = action_type
        self.session_message = session_message

        options = [
            discord.SelectOption(label="Top", emoji="🛡️", value="Top", description="Solo top lane bruiser / tank"),
            discord.SelectOption(label="Jungle", emoji="🌲", value="Jungle", description="Map objective control & ganks"),
            discord.SelectOption(label="Mid", emoji="⚡", value="Mid", description="Solo mid lane mage / assassin"),
            discord.SelectOption(label="Bot (ADC)", emoji="🏹", value="Bot", description="Attack damage carry"),
            discord.SelectOption(label="Support", emoji="✨", value="Support", description="Vision control & bot utility"),
            discord.SelectOption(label="Fill", emoji="🎲", value="Fill", description="Any available position"),
        ]
        self.select = discord.ui.Select(
            placeholder="Select 1 or more preferred roles...",
            min_values=1,
            max_values=5,
            options=options
        )
        self.select.callback = self.select_callback
        self.add_item(self.select)

    async def select_callback(self, interaction: discord.Interaction):
        if not has_lolers_role(interaction.user):
            await interaction.response.send_message(
                f"⛔ Only members with the **@{ROSTER_ROLE_NAME}** role can join the 5-stack roster.",
                ephemeral=True
            )
            return

        selected_roles = ", ".join(self.select.values)
        quorum_met, session, promoted = stats_mgr.register_player(
            session_id=self.session_id,
            player_name=interaction.user.display_name,
            status=self.action_type,
            role_pref=selected_roles
        )

        if not session:
            await interaction.response.send_message("❌ Session not found or is no longer active.", ephemeral=True)
            return

        # Dismiss the dropdown in-place on the ephemeral message and confirm
        await interaction.response.edit_message(
            content=f"✅ Registered as **{self.action_type}** with role preference(s): **{selected_roles}**!",
            view=None
        )

        thread_alert = None
        activity_line = None

        if promoted:
            activity_line = f"📢 **{promoted['name']}** auto-promoted to Starting 5"
            thread_alert = (
                f"📢 **Roster Auto-Promotion**: **{promoted['name']}** has been promoted from the bench into the Starting 5!"
            )

        if quorum_met and len(session["confirmed_players"]) == 5 and self.action_type == "CONFIRMED":
            role = discord.utils.find(lambda r: r.name.lower() == ROSTER_ROLE_NAME.lower(), interaction.guild.roles) if interaction.guild else None
            role_mention = role.mention if role else f"@{ROSTER_ROLE_NAME}"
            players_ping = ", ".join([f"**{p['name']}**" for p in session["confirmed_players"]])
            mode_announcement = (
                "🛡️ **Ranked 5s Mode Window is OPEN!** Time to queue tournament draft!"
                if session["is_ranked_5s"]
                else "⚡ **Ranked Flex Fallback**: Ranked 5s window closed, but 5-stack Ranked Flex is ready to launch!"
            )
            activity_line = "🚨 **5/5 Quorum Reached — Lobby Ready!**"
            thread_alert = (
                f"🚨 **LOBBY READY! 5-PLAYER QUORUM REACHED!** ({role_mention})\n"
                f"Starting 5: {players_ping}\n"
                f"Target Queue: **{session['mode']}**\n{mode_announcement}"
            )

        await notify_session(
            session=session,
            activity_entry=activity_line,
            thread_content=thread_alert,
            guild=interaction.guild,
            session_message=self.session_message,
        )


class ConfirmActionView(discord.ui.View):
    """Ephemeral confirmation view for destructive/lifecycle session actions."""
    def __init__(self, session_id: str, action_type: str, session_message: Optional[discord.Message] = None):
        super().__init__(timeout=60)
        self.session_id = session_id
        self.action_type = action_type  # "CANCEL" or "END"
        self.session_message = session_message

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger, emoji="⚠️")
    async def confirm_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        session = stats_mgr.get_session(self.session_id)
        if not session:
            await interaction.response.edit_message(content="❌ Session no longer exists.", view=None)
            return

        if self.action_type == "CANCEL":
            success, session, affected = stats_mgr.cancel_session(self.session_id)
            if not success:
                await interaction.response.edit_message(content="❌ Could not cancel session.", view=None)
                return

            affected_pings = []
            if interaction.guild:
                for name in affected:
                    m = discord.utils.find(lambda x: x.display_name.lower() == name.lower() or x.name.lower() == name.lower(), interaction.guild.members)
                    affected_pings.append(m.mention if m else f"**{name}**")
            pings_str = ", ".join(affected_pings)

            cancel_msg = (
                f"🛑 **SESSION CANCELLED**\n"
                f"The 5-stack session for **{session.get('scheduled_time')}** was cancelled by **{interaction.user.display_name}**."
            )
            if pings_str:
                cancel_msg += f"\n📢 Attention {pings_str}: This session will no longer take place."

            await notify_session(
                session=session,
                activity_entry=f"🛑 Cancelled by **{interaction.user.display_name}**",
                thread_content=cancel_msg,
                guild=interaction.guild,
                session_message=self.session_message,
                remove_view=True,
                archive_thread=True,
            )

            await interaction.response.edit_message(
                content=f"✅ Session `{self.session_id}` was cancelled and its card updated in-place.",
                view=None
            )

        elif self.action_type == "END":
            success, session = stats_mgr.complete_session(self.session_id)
            if not success:
                await interaction.response.edit_message(content="❌ Could not end session.", view=None)
                return

            await notify_session(
                session=session,
                activity_entry=f"🏁 Concluded by **{interaction.user.display_name}**",
                thread_content=(
                    f"🏁 **Session Concluded**: The 5-stack session for **{session.get('scheduled_time')}** "
                    f"has officially concluded! Thanks for playing, squad!"
                ),
                guild=interaction.guild,
                session_message=self.session_message,
                remove_view=True,
                archive_thread=True,
            )

            await interaction.response.edit_message(
                content=f"✅ Session `{self.session_id}` has been ended.",
                view=None
            )

    @discord.ui.button(label="Nevermind", style=discord.ButtonStyle.secondary)
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="Operation cancelled.", view=None)


class SessionRSVPView(discord.ui.View):
    """Persistent RSVP View with unique custom IDs per session."""
    def __init__(self, session_id: str):
        super().__init__(timeout=None)
        self.session_id = session_id

        self.join_btn = discord.ui.Button(
            label="✅ Join 5-Stack",
            style=discord.ButtonStyle.green,
            custom_id=f"session:join:{session_id}",
            row=0
        )
        self.join_btn.callback = self.join_callback
        self.add_item(self.join_btn)

        self.bench_btn = discord.ui.Button(
            label="⏳ Sub / Bench",
            style=discord.ButtonStyle.secondary,
            custom_id=f"session:bench:{session_id}",
            row=0
        )
        self.bench_btn.callback = self.bench_callback
        self.add_item(self.bench_btn)

        self.decline_btn = discord.ui.Button(
            label="❌ Can't Make It",
            style=discord.ButtonStyle.secondary,
            custom_id=f"session:decline:{session_id}",
            row=0
        )
        self.decline_btn.callback = self.decline_callback
        self.add_item(self.decline_btn)

        self.end_btn = discord.ui.Button(
            label="🏁 End Session",
            style=discord.ButtonStyle.secondary,
            custom_id=f"session:end:{session_id}",
            row=1
        )
        self.end_btn.callback = self.end_callback
        self.add_item(self.end_btn)

        self.cancel_btn = discord.ui.Button(
            label="🛑 Cancel Session",
            style=discord.ButtonStyle.danger,
            custom_id=f"session:cancel:{session_id}",
            row=1
        )
        self.cancel_btn.callback = self.cancel_callback
        self.add_item(self.cancel_btn)

        self.feedback_btn = discord.ui.Button(
            label="💡 Feedback",
            style=discord.ButtonStyle.secondary,
            custom_id=f"session:feedback:{session_id}",
            row=1
        )
        self.feedback_btn.callback = self.feedback_callback
        self.add_item(self.feedback_btn)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await check_channel_restriction(interaction)

    async def join_callback(self, interaction: discord.Interaction):
        if not has_lolers_role(interaction.user):
            await interaction.response.send_message(
                f"⛔ Access Denied: You must have the **@{ROSTER_ROLE_NAME}** role to join 5-stack sessions.",
                ephemeral=True
            )
            return
        view = RoleSelectView(self.session_id, "CONFIRMED", interaction.message)
        await interaction.response.send_message("Select your preferred role(s) from the dropdown below:", view=view, ephemeral=True)

    async def bench_callback(self, interaction: discord.Interaction):
        if not has_lolers_role(interaction.user):
            await interaction.response.send_message(
                f"⛔ Access Denied: You must have the **@{ROSTER_ROLE_NAME}** role to join as a substitute.",
                ephemeral=True
            )
            return
        view = RoleSelectView(self.session_id, "BENCH", interaction.message)
        await interaction.response.send_message("Select your preferred substitute role(s) from the dropdown below:", view=view, ephemeral=True)

    async def decline_callback(self, interaction: discord.Interaction):
        if not has_lolers_role(interaction.user):
            await interaction.response.send_message(
                f"⛔ Access Denied: Only **@{ROSTER_ROLE_NAME}** members are tracked on the roster.",
                ephemeral=True
            )
            return
        _, session, promoted = stats_mgr.register_player(
            session_id=self.session_id,
            player_name=interaction.user.display_name,
            status="DECLINED"
        )
        if promoted:
            stats_mgr.append_session_activity(
                self.session_id,
                f"📢 **{promoted['name']}** auto-promoted to Starting 5"
            )
        embed = build_session_embed(session, interaction.guild)
        await interaction.response.edit_message(embed=embed)

        if promoted:
            thread = await ensure_session_thread(session, interaction.guild, interaction.message)
            if thread:
                try:
                    await thread.send(
                        f"📢 **Roster Auto-Promotion**: {interaction.user.display_name} stepped down. "
                        f"**{promoted['name']}** has been promoted from the bench into the Starting 5!"
                    )
                except Exception as e:
                    print(f"[AutoPromote] Error posting to session thread: {e}")

    async def cancel_callback(self, interaction: discord.Interaction):
        session = stats_mgr.get_session(self.session_id)
        if not session or session.get("status") == "CANCELLED":
            await interaction.response.send_message("❌ Session not found or already cancelled.", ephemeral=True)
            return

        if not is_session_organizer_or_admin(interaction.user, session):
            await interaction.response.send_message(
                f"⛔ Only the session organizer (**{session.get('creator')}**) or an administrator can cancel this session.",
                ephemeral=True
            )
            return

        view = ConfirmActionView(self.session_id, "CANCEL", interaction.message)
        await interaction.response.send_message(
            f"⚠️ **Are you sure you want to cancel the session for {session.get('scheduled_time')}?**\n"
            f"This will mark the session card as cancelled and notify signed-up players in the session thread.",
            view=view,
            ephemeral=True
        )

    async def end_callback(self, interaction: discord.Interaction):
        session = stats_mgr.get_session(self.session_id)
        if not session or session.get("status") in ["CANCELLED", "COMPLETED"]:
            await interaction.response.send_message("❌ Session not found or already concluded.", ephemeral=True)
            return

        if not is_session_organizer_or_admin(interaction.user, session):
            await interaction.response.send_message(
                f"⛔ Only the session organizer (**{session.get('creator')}**) or an administrator can end this session.",
                ephemeral=True
            )
            return

        view = ConfirmActionView(self.session_id, "END", interaction.message)
        await interaction.response.send_message(
            f"⚠️ **Are you sure you want to end the session for {session.get('scheduled_time')}?**\n"
            f"This will mark the session as completed and close the RSVP view.",
            view=view,
            ephemeral=True
        )

    async def feedback_callback(self, interaction: discord.Interaction):
        if not has_lolers_role(interaction.user):
            await interaction.response.send_message(
                f"⛔ Access Denied: Only **@{ROSTER_ROLE_NAME}** members can submit feedback tickets.",
                ephemeral=True
            )
            return
        await interaction.response.send_modal(FeedbackModal(session_id=self.session_id))


def build_session_embed(session: dict, guild: discord.Guild = None) -> discord.Embed:
    confirmed = session.get("confirmed_players", [])
    bench = session.get("bench_substitutes", [])
    declined = session.get("declined", [])
    count = len(confirmed)
    status = session.get("status", "POLLING")

    if status == "CANCELLED":
        status_color = 0xEF4444
        status_badge = "🛑 **STATUS: CANCELLED**"
    elif status == "COMPLETED":
        status_color = 0x6B7280
        status_badge = "🏁 **STATUS: COMPLETED**"
    elif status == "IN_PROGRESS":
        status_color = 0xF59E0B
        status_badge = "⚔️ **STATUS: IN PROGRESS / GAME TIME**"
    elif status == "READY" or count >= 5:
        status_color = 0x22C55E
        status_badge = "✅ **STATUS: LOBBY READY (5/5)**"
    else:
        status_color = 0x3B82F6
        status_badge = f"⏳ **STATUS: RECRUITING ({count}/5 Players)** (Needs {5-count} more from @{ROSTER_ROLE_NAME})"

    creator_name = session.get("creator", "Unknown")
    thread_line = f"**Session Thread**: <#{session['thread_id']}>\n" if session.get("thread_id") else ""

    embed = discord.Embed(
        title="🎮 League of Legends 5-Stack Coordinator",
        description=f"{status_badge}\n\n"
                    f"**Session ID**: `{session.get('session_id')}`\n"
                    f"**Organizer**: **{creator_name}**\n"
                    f"**Target Window**: `{session.get('scheduled_time')}`\n"
                    f"**Detected Mode**: **{session.get('mode')}**\n"
                    f"{thread_line}"
                    f"{'🏆 *Ranked 5s Tournament Draft Active*' if session.get('is_ranked_5s') else '🔄 *Ranked Flex 24/7 Fallback Active*'}",
        color=status_color
    )

    # Starters (Minimum 5 required)
    starters_text = "\n".join([f"{i+1}. **{p['name']}** — *{p['role_pref']}*" for i, p in enumerate(confirmed)]) or "*No players registered yet.*"
    embed.add_field(name=f"Starting Roster ({count}/5)", value=starters_text, inline=False)

    # Bench / Overflow
    bench_text = "\n".join([f"• **{p['name']}** ({p['role_pref']})" for p in bench]) or "*Empty*"
    embed.add_field(name=f"Sitting in the cuck chair 🪑 ({len(bench)})", value=bench_text, inline=True)

    # Unavailable
    declined_text = ", ".join(declined) or "*None*"
    embed.add_field(name="Unavailable", value=declined_text, inline=True)

    # Compact Session Match Log (if games were played during this session)
    session_matches = session.get("session_matches", [])
    if session_matches:
        wins = sum(1 for m in session_matches if m.get("result") == "WIN")
        losses = len(session_matches) - wins
        match_lines = [
            f"• Game {i+1}: {'🏆 WIN' if m.get('result') == 'WIN' else '💀 LOSS'} (MVP: **{m.get('mvp', 'N/A')}**)"
            for i, m in enumerate(session_matches[-5:])
        ]
        embed.add_field(
            name=f"🎮 Session Match Log ({wins}W - {losses}L)",
            value="\n".join(match_lines),
            inline=False
        )

    # In-Place Activity Log (reschedules, promotions, reminders, status changes)
    activity_log = session.get("activity_log", [])
    if activity_log:
        embed.add_field(
            name="📌 Recent Session Updates",
            value="\n".join(activity_log[-5:]),
            inline=False
        )

    return embed


# --- Living Synergy Threads Engine ---

SYNERGY_OPTIONS: Dict[str, Dict[str, str]] = {
    "botlane": {
        "title": "🏹 Botlane (ADC + Support)",
        "thread_name": "🏹 Synergy — Botlane (ADC + Support)",
        "method": "get_botlane_synergies",
    },
    "mid_jungle": {
        "title": "⚡ Mid + Jungle (2v2 Core)",
        "thread_name": "⚡ Synergy — Mid + Jungle (2v2 Core)",
        "method": "get_mid_jungle_synergies",
    },
    "top_jungle": {
        "title": "🛡️ Top + Jungle (Topside Synergy)",
        "thread_name": "🛡️ Synergy — Top + Jungle (Topside)",
        "method": "get_top_jungle_synergies",
    },
    "support_jungle": {
        "title": "✨ Support + Jungle (Roam & Objectives)",
        "thread_name": "✨ Synergy — Support + Jungle (Roam)",
        "method": "get_support_jungle_synergies",
    },
}


MIN_SYNERGY_GAMES = 3


def build_synergy_embed(pair_key: str, is_living_thread: bool = False) -> discord.Embed:
    """Builds the chemistry leaderboard embed for any of the 4 synergy options (requires >= 3 games together)."""
    cfg = SYNERGY_OPTIONS.get(pair_key, SYNERGY_OPTIONS["botlane"])
    title = cfg["title"]
    getter = getattr(stats_mgr, cfg["method"])
    duos = [d for d in getter(min_games=MIN_SYNERGY_GAMES) if d.get("games", 0) >= MIN_SYNERGY_GAMES]

    state = stats_mgr.get_synergy_thread_state(pair_key)
    thread_link = ""
    if not is_living_thread and state and state.get("thread_id"):
        thread_link = f"\n📌 **Living Thread**: <#{state['thread_id']}>"

    desc = (
        f"Live auto-updating leaderboard across 5-stack & squad games in **#{COORDINATION_CHANNEL}** "
        f"*(min. {MIN_SYNERGY_GAMES} games together)*."
        if is_living_thread
        else f"Pairwise performance across 5-stack & squad games in **#{COORDINATION_CHANNEL}** "
             f"*(min. {MIN_SYNERGY_GAMES} games together)*.{thread_link}"
    )

    embed = discord.Embed(
        title=f"Chemistry Leaderboard — {title}",
        description=desc,
        color=0xEC4899,
    )

    limit = 10 if is_living_thread else 5
    if not duos:
        embed.add_field(
            name=f"No Qualifying Duos Yet (Min. {MIN_SYNERGY_GAMES} Games)",
            value=f"*Play at least {MIN_SYNERGY_GAMES} squad matches together as @{ROSTER_ROLE_NAME} members to appear on this leaderboard!*",
            inline=False,
        )
    else:
        for i, duo in enumerate(duos[:limit], start=1):
            duo_rating_str = f" | **Avg Duo Rating**: `{duo['avg_duo_rating']}/100`" if duo.get("avg_duo_rating") else ""
            embed.add_field(
                name=f"#{i} {duo['pair']} — {duo['tier']} ({duo['synergy_score']}/100)",
                value=(
                    f"**Record**: {duo['wins']}W - {duo['losses']}L ({duo['win_rate']}% WR in {duo['games']} games)\n"
                    f"**Duo KDA**: {duo['combined_kda']}{duo_rating_str} | **Tag**: `{duo['tag']}`\n"
                    f"**Signature Combo**: `{duo['favorite_combo']}`"
                ),
                inline=False,
            )

    updated_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    embed.set_footer(text=f"Last updated: {updated_str} • Min. {MIN_SYNERGY_GAMES} games required • Auto-updates")
    return embed


async def sync_living_synergy_threads(
    guild: Optional[discord.Guild] = None,
    pair_keys: Optional[List[str]] = None,
) -> None:
    """
    Ensures a living thread exists for each synergy option in #5-stackers and edits its
    leaderboard embed message in-place whenever new match data is processed.
    """
    target_guilds = [guild] if guild else list(bot.guilds)
    keys_to_sync = pair_keys or list(SYNERGY_OPTIONS.keys())

    for g in target_guilds:
        if not g:
            continue
        role = discord.utils.find(lambda r: r.name.lower() == ROSTER_ROLE_NAME.lower(), g.roles)
        if role and role.members:
            roster_names = []
            for m in role.members:
                roster_names.append(m.display_name)
                roster_names.append(m.name)
            stats_mgr.set_lolers_roster(roster_names)

        channel = discord.utils.get(g.text_channels, name=COORDINATION_CHANNEL)
        if not channel:
            continue

        for pair_key in keys_to_sync:
            cfg = SYNERGY_OPTIONS.get(pair_key)
            if not cfg:
                continue

            embed = build_synergy_embed(pair_key, is_living_thread=True)
            state = stats_mgr.get_synergy_thread_state(pair_key)
            thread: Optional[discord.Thread] = None
            msg: Optional[discord.Message] = None

            if state and state.get("thread_id"):
                tid = state["thread_id"]
                try:
                    thread = g.get_thread(tid) or bot.get_channel(tid) or await bot.fetch_channel(tid)
                    if isinstance(thread, discord.Thread) and thread.archived:
                        await thread.edit(archived=False)
                except Exception:
                    thread = None

            if thread and state and state.get("message_id"):
                try:
                    msg = await thread.fetch_message(state["message_id"])
                    await msg.edit(embed=embed)
                    stats_mgr.set_synergy_thread_state(pair_key, thread.id, msg.id)
                    continue
                except Exception:
                    msg = None

            if not thread:
                # Check if an existing active thread in the channel already has this name
                existing_thread = discord.utils.get(channel.threads, name=cfg["thread_name"])
                if existing_thread:
                    thread = existing_thread
                else:
                    try:
                        thread = await channel.create_thread(
                            name=cfg["thread_name"],
                            type=discord.ChannelType.public_thread,
                            auto_archive_duration=1440,
                        )
                    except Exception as e:
                        print(f"[SynergyThread] Could not create living thread for {pair_key}: {e}")
                        continue

            if thread:
                try:
                    if thread.archived:
                        await thread.edit(archived=False)
                    msg = await thread.send(embed=embed)
                    stats_mgr.set_synergy_thread_state(pair_key, thread.id, msg.id)
                except Exception as e:
                    print(f"[SynergyThread] Could not post leaderboard in thread for {pair_key}: {e}")


# --- Slash Commands ---

@bot.tree.command(name="session", description=f"Propose a new 5-stack session in #{COORDINATION_CHANNEL}.")
@app_commands.describe(time_window="Proposed date and time (e.g. 'Tonight 8:30 PM', 'Friday 9:00 PM', 'Tomorrow 7pm')")
async def session_cmd(interaction: discord.Interaction, time_window: str):
    if not has_lolers_role(interaction.user):
        await interaction.response.send_message(
            f"⛔ Only members with the **@{ROSTER_ROLE_NAME}** role can organize 5-stack sessions.",
            ephemeral=True
        )
        return

    target_dt, display_time, parsed_ok = scheduler.parse_target_time(time_window)
    eval_res = scheduler.evaluate_time(target_dt)
    session_id = str(uuid.uuid4())[:8]

    session = stats_mgr.create_session(
        session_id=session_id,
        scheduled_time=display_time,
        mode=eval_res["mode"],
        is_ranked_5s=eval_res["is_ranked_5s"],
        creator=interaction.user.display_name,
        scheduled_iso=eval_res.get("target_iso"),
        creator_id=str(interaction.user.id)
    )

    view = SessionRSVPView(session_id)
    embed = build_session_embed(session, interaction.guild)
    
    role = discord.utils.find(lambda r: r.name.lower() == ROSTER_ROLE_NAME.lower(), interaction.guild.roles) if interaction.guild else None
    role_mention = role.mention if role else f"@{ROSTER_ROLE_NAME}"

    await interaction.response.defer(ephemeral=True)

    target_channel = interaction.channel
    if isinstance(target_channel, discord.Thread) and target_channel.parent:
        target_channel = target_channel.parent

    try:
        session_msg = await target_channel.send(
            content=f"📢 {role_mention}: **{interaction.user.display_name}** proposed a 5-stack session for **{display_time}** in **#{COORDINATION_CHANNEL}**! Who's in?",
            embed=embed,
            view=view
        )
    except discord.errors.Forbidden as e:
        if e.code in [50001, 50013]:
            await interaction.followup.send(
                f"❌ **Missing Channel Access in #{COORDINATION_CHANNEL}** (Discord error {e.code}):\n"
                f"The bot does not have permission to view or post in **#{COORDINATION_CHANNEL}**.\n\n"
                f"**How to fix** (Discord Server Settings):\n"
                f"1. In Discord, assign the **`@{ROSTER_ROLE_NAME}`** role to **`5 Stacker LoL`** (or go to **#{COORDINATION_CHANNEL}** ⚙️ ➔ **Permissions** and add **`5 Stacker LoL`**).\n"
                f"2. Ensure **View Channel**, **Send Messages**, **Embed Links**, and **Manage Messages** are enabled.",
                ephemeral=True
            )
            return
        raise

    stats_mgr.set_session_message(session_id, session_msg.channel.id, session_msg.id)

    # Create attached session thread immediately so all pings & match recaps stay organized
    thread = await ensure_session_thread(session, interaction.guild, session_msg)
    if thread:
        updated_embed = build_session_embed(stats_mgr.get_session(session_id) or session, interaction.guild)
        try:
            await session_msg.edit(embed=updated_embed, view=view)
        except Exception as e:
            print(f"[Session] Could not update card with thread link: {e}")

    await interaction.followup.send(
        f"✅ 5-stack session `{session_id}` announced in {target_channel.mention}!",
        ephemeral=True
    )


@bot.tree.command(name="edit-session", description="Reschedule a planned 5-stack session and notify signed-up players.")
@app_commands.describe(
    session_id="The ID of the session to edit",
    new_time="New proposed date/time (e.g. 'Tonight 9:30 PM', 'Friday 9:00 PM', 'Tomorrow 8pm')"
)
async def edit_session_cmd(interaction: discord.Interaction, session_id: str, new_time: str):
    if not has_lolers_role(interaction.user):
        await interaction.response.send_message(
            f"⛔ Only members with the **@{ROSTER_ROLE_NAME}** role can edit sessions.",
            ephemeral=True
        )
        return

    target_dt, display_time, parsed_ok = scheduler.parse_target_time(new_time)
    eval_res = scheduler.evaluate_time(target_dt)

    success, session, affected = stats_mgr.edit_session_time(
        session_id=session_id,
        new_scheduled_time=display_time,
        new_scheduled_iso=eval_res.get("target_iso"),
        new_mode=eval_res["mode"],
        is_ranked_5s=eval_res["is_ranked_5s"]
    )

    if not success:
        await interaction.response.send_message(
            f"❌ Session `{session_id}` not found or is already cancelled.",
            ephemeral=True
        )
        return

    affected_pings = []
    if interaction.guild:
        for name in affected:
            m = discord.utils.find(lambda x: x.display_name.lower() == name.lower() or x.name.lower() == name.lower(), interaction.guild.members)
            affected_pings.append(m.mention if m else f"**{name}**")
    pings_str = ", ".join(affected_pings) or "Signed-up players"

    await notify_session(
        session=session,
        activity_entry=f"🔄 Rescheduled to **{display_time}** ({eval_res['mode']}) by **{interaction.user.display_name}**",
        thread_content=(
            f"⚠️ **SESSION RESCHEDULED!**\n"
            f"Attention {pings_str}: **{interaction.user.display_name}** changed the session time to **{display_time}** ({eval_res['mode']}).\n"
            f"Please check your availability and update your RSVP on the session card if needed!"
        ),
        guild=interaction.guild,
    )

    await interaction.response.send_message(
        f"✅ Session `{session_id}` updated in-place to **{display_time}** ({eval_res['mode']})!",
        ephemeral=True
    )


@bot.tree.command(name="cancel-session", description="Cancel an active 5-stack session.")
@app_commands.describe(session_id="The ID of the session to cancel")
async def cancel_session_cmd(interaction: discord.Interaction, session_id: str):
    if not has_lolers_role(interaction.user):
        await interaction.response.send_message(
            f"⛔ Only members with the **@{ROSTER_ROLE_NAME}** role can cancel sessions.",
            ephemeral=True
        )
        return

    session = stats_mgr.get_session(session_id)
    if not session or session.get("status") == "CANCELLED":
        await interaction.response.send_message(f"❌ Session `{session_id}` not found or already cancelled.", ephemeral=True)
        return

    if not is_session_organizer_or_admin(interaction.user, session):
        await interaction.response.send_message(
            f"⛔ Only the session organizer (**{session.get('creator')}**) or an administrator can cancel this session.",
            ephemeral=True
        )
        return

    success, session, affected = stats_mgr.cancel_session(session_id)
    if not success:
        await interaction.response.send_message(f"❌ Session `{session_id}` not found.", ephemeral=True)
        return

    affected_pings = []
    if interaction.guild:
        for name in affected:
            m = discord.utils.find(lambda x: x.display_name.lower() == name.lower() or x.name.lower() == name.lower(), interaction.guild.members)
            affected_pings.append(m.mention if m else f"**{name}**")
    pings_str = ", ".join(affected_pings)

    cancel_msg = f"🛑 **Session Cancelled**: The session `{session_id}` ({session.get('scheduled_time')}) was cancelled by **{interaction.user.display_name}**."
    if pings_str:
        cancel_msg += f"\n📢 Attention {pings_str}: This session will no longer take place."

    await notify_session(
        session=session,
        activity_entry=f"🛑 Cancelled by **{interaction.user.display_name}**",
        thread_content=cancel_msg,
        guild=interaction.guild,
        remove_view=True,
        archive_thread=True,
    )

    await interaction.response.send_message(
        f"✅ Session `{session_id}` has been cancelled and updated in-place.",
        ephemeral=True
    )


@bot.tree.command(name="end-session", description="End an active 5-stack session.")
@app_commands.describe(session_id="The ID of the session to end")
async def end_session_cmd(interaction: discord.Interaction, session_id: str):
    if not has_lolers_role(interaction.user):
        await interaction.response.send_message(
            f"⛔ Only members with the **@{ROSTER_ROLE_NAME}** role can end sessions.",
            ephemeral=True
        )
        return

    session = stats_mgr.get_session(session_id)
    if not session or session.get("status") in ["CANCELLED", "COMPLETED"]:
        await interaction.response.send_message(f"❌ Session `{session_id}` not found or already concluded.", ephemeral=True)
        return

    if not is_session_organizer_or_admin(interaction.user, session):
        await interaction.response.send_message(
            f"⛔ Only the session organizer (**{session.get('creator')}**) or an administrator can end this session.",
            ephemeral=True
        )
        return

    success, session = stats_mgr.complete_session(session_id)
    if not success:
        await interaction.response.send_message(f"❌ Session `{session_id}` not found.", ephemeral=True)
        return

    await notify_session(
        session=session,
        activity_entry=f"🏁 Concluded by **{interaction.user.display_name}**",
        thread_content=(
            f"🏁 **Session Concluded**: The session `{session_id}` ({session.get('scheduled_time')}) "
            f"was ended by **{interaction.user.display_name}**. Thanks for playing!"
        ),
        guild=interaction.guild,
        remove_view=True,
        archive_thread=True,
    )

    await interaction.response.send_message(
        f"✅ Session `{session_id}` has been marked as completed.",
        ephemeral=True
    )


@bot.tree.command(name="sessions", description="List all active and recent 5-stack sessions.")
@app_commands.describe(public="Share publicly in the channel instead of a private response (default: False)")
async def sessions_cmd(interaction: discord.Interaction, public: bool = False):
    active = stats_mgr.get_active_sessions()
    all_sessions = stats_mgr.data.get("active_sessions", {})

    if not all_sessions:
        await interaction.response.send_message("No sessions found. Create one with `/session`!", ephemeral=True)
        return

    embed = discord.Embed(
        title="📋 5-Stack Sessions Overview",
        description=f"Showing all active and recent sessions in **#{COORDINATION_CHANNEL}**.",
        color=0x3B82F6
    )

    if active:
        active_lines = []
        for s in active:
            st = s.get("status")
            badge = "⏳ Recruiting" if st == "POLLING" else ("✅ Lobby Ready" if st == "READY" else "⚔️ In Progress")
            count = len(s.get("confirmed_players", []))
            thread_ref = f" • <#{s['thread_id']}>" if s.get("thread_id") else ""
            active_lines.append(
                f"• `{s.get('session_id')}`: **{s.get('scheduled_time')}** ({s.get('mode')}) — {badge} ({count}/5){thread_ref}\n"
                f"  *Organizer*: **{s.get('creator')}**"
            )
        embed.add_field(name=f"Active Sessions ({len(active)})", value="\n".join(active_lines), inline=False)
    else:
        embed.add_field(name="Active Sessions (0)", value="*No active sessions right now. Use `/session` to organize one!*", inline=False)

    recent_closed = [
        s for s in all_sessions.values()
        if s.get("status") in ["COMPLETED", "CANCELLED"]
    ][-3:]
    if recent_closed:
        closed_lines = []
        for s in reversed(recent_closed):
            badge = "🏁 Completed" if s.get("status") == "COMPLETED" else "🛑 Cancelled"
            closed_lines.append(
                f"• `{s.get('session_id')}`: {s.get('scheduled_time')} — {badge} (by {s.get('creator')})"
            )
        embed.add_field(name="Recent Past Sessions", value="\n".join(closed_lines), inline=False)

    await interaction.response.send_message(embed=embed, ephemeral=not public)


@bot.tree.command(name="queue-check", description="Check current Ranked 5s window status and next opening.")
@app_commands.describe(public="Share publicly in the channel instead of a private response (default: False)")
async def queue_check_cmd(interaction: discord.Interaction, public: bool = False):
    info = scheduler.evaluate_time()
    embed = discord.Embed(
        title="⚔️ League of Legends Queue Status",
        color=0x10B981 if info["is_ranked_5s"] else 0xF59E0B
    )
    embed.add_field(name="Current Mode", value=f"**{info['mode']}**", inline=False)
    embed.add_field(name="Status", value=info["description"], inline=False)
    embed.add_field(name="Current Time", value=info["evaluated_time"], inline=True)
    embed.add_field(name="Next Ranked 5s Window", value=info["next_window_start"], inline=True)
    embed.set_footer(text=f"Ranked 5s runs Fri-Sun 8PM-1AM. Ranked Flex is 24/7 • #{COORDINATION_CHANNEL}")
    await interaction.response.send_message(embed=embed, ephemeral=not public)


@bot.tree.command(name="synergy", description="View duo chemistry and win rates across team positions.")
@app_commands.describe(
    pair_type="The duo partnership to inspect",
    public="Share publicly in the channel instead of a private response (default: False)"
)
@app_commands.choices(pair_type=[
    app_commands.Choice(name="Botlane (ADC + Support)", value="botlane"),
    app_commands.Choice(name="Mid + Jungle (2v2 Core)", value="mid_jungle"),
    app_commands.Choice(name="Top + Jungle (Topside Synergy)", value="top_jungle"),
    app_commands.Choice(name="Support + Jungle (Roam & Objectives)", value="support_jungle"),
])
async def synergy_cmd(interaction: discord.Interaction, pair_type: app_commands.Choice[str], public: bool = False):
    embed = build_synergy_embed(pair_type.value, is_living_thread=False)
    await interaction.response.send_message(embed=embed, ephemeral=not public)


@bot.tree.command(name="botlane", description="Check Bot + Support duo chemistry ratings and win rates.")
@app_commands.describe(public="Share publicly in the channel instead of a private response (default: False)")
async def botlane_cmd(interaction: discord.Interaction, public: bool = False):
    embed = build_synergy_embed("botlane", is_living_thread=False)
    await interaction.response.send_message(embed=embed, ephemeral=not public)


@bot.tree.command(name="roster", description=f"View all members holding the @{ROSTER_ROLE_NAME} role and their stats.")
@app_commands.describe(public="Share publicly in the channel instead of a private response (default: False)")
async def roster_cmd(interaction: discord.Interaction, public: bool = False):
    guild = interaction.guild
    role = discord.utils.find(lambda r: r.name.lower() == ROSTER_ROLE_NAME.lower(), guild.roles) if guild else None
    
    leaderboard = stats_mgr.get_player_leaderboard()
    leaderboard_map = {p["name"].lower(): p for p in leaderboard}

    embed = discord.Embed(
        title=f"🛡️ The @{ROSTER_ROLE_NAME} Squad Roster",
        description=f"Official 5-stack pool defined by the **@{ROSTER_ROLE_NAME}** role. Coordinated in **#{COORDINATION_CHANNEL}**.",
        color=0x8B5CF6
    )

    if role and role.members:
        # Display live guild members who hold the role
        for member in role.members:
            p_stat = leaderboard_map.get(member.display_name.lower()) or leaderboard_map.get(member.name.lower())
            if p_stat and p_stat.get("games", 0) > 0:
                rating_part = f" | **Rating**: `{p_stat['avg_rating']}` ({p_stat['grade']})" if p_stat.get("avg_rating") else ""
                stat_str = (
                    f"**WR**: {p_stat['win_rate']}% ({p_stat['wins']}W-{p_stat['losses']}L) | "
                    f"**KDA**: {p_stat['kda']}{rating_part} | 🏆 {p_stat['mvps']} MVPs"
                )
            else:
                stat_str = "*Ready for first 5-stack session*"
            embed.add_field(
                name=f"🎮 {member.display_name}",
                value=stat_str,
                inline=True
            )
        embed.set_footer(text=f"Total Roster: {len(role.members)} members with @{ROSTER_ROLE_NAME} role")
    else:
        # Fallback to configured data manager members if role not found in cache
        for p in leaderboard:
            rating_part = f" | **Rating**: `{p['avg_rating']}` ({p['grade']})" if p.get("avg_rating") else ""
            embed.add_field(
                name=f"{p['name']} ({p['main_role']})",
                value=f"**WR**: {p['win_rate']}% ({p['wins']}W-{p['losses']}L) | **KDA**: {p['kda']}{rating_part} | **MVPs**: 🏆 {p['mvps']}",
                inline=True
            )
        embed.set_footer(text=f"Ensure the @{ROSTER_ROLE_NAME} role exists in your Discord server.")

    await interaction.response.send_message(embed=embed, ephemeral=not public)


@bot.tree.command(name="feedback", description="Submit a bug report, feature request, or UX idea directly to GitHub Issues.")
@app_commands.describe(category="Type of feedback to submit")
@app_commands.choices(category=[
    app_commands.Choice(name="Feature Request", value="Feature Request"),
    app_commands.Choice(name="Bug Report", value="Bug Report"),
    app_commands.Choice(name="UX / Channel Noise", value="UX / Channel Feedback"),
])
async def feedback_cmd(
    interaction: discord.Interaction,
    category: Optional[app_commands.Choice[str]] = None,
):
    if not has_lolers_role(interaction.user):
        await interaction.response.send_message(
            f"⛔ Only members with the **@{ROSTER_ROLE_NAME}** role can submit bot feedback tickets.",
            ephemeral=True
        )
        return

    default_cat = category.value if category else "Feature Request"
    await interaction.response.send_modal(FeedbackModal(default_category=default_cat))


@bot.tree.command(name="log-match", description="Log a completed 5-stack match and update synergy/player stats.")
@app_commands.describe(
    result="Match outcome (WIN or LOSS)",
    adc_player="Player in Bot (ADC) role",
    adc_champion="Champion played by ADC",
    adc_kda="ADC Kills/Deaths/Assists (e.g. 8/2/10)",
    sup_player="Player in Support role",
    sup_champion="Champion played by Support",
    sup_kda="Support Kills/Deaths/Assists (e.g. 1/3/18)",
    mvp="Match MVP player name (optional)",
    public="Share publicly in the channel instead of a private response (default: False)"
)
@app_commands.choices(result=[
    app_commands.Choice(name="WIN", value="WIN"),
    app_commands.Choice(name="LOSS", value="LOSS"),
])
async def log_match_cmd(
    interaction: discord.Interaction,
    result: app_commands.Choice[str],
    adc_player: str,
    adc_champion: str,
    adc_kda: str,
    sup_player: str,
    sup_champion: str,
    sup_kda: str,
    mvp: str = "",
    public: bool = False
):
    if not has_lolers_role(interaction.user):
        await interaction.response.send_message(
            f"⛔ Only members with the **@{ROSTER_ROLE_NAME}** role can log match results.",
            ephemeral=True
        )
        return

    def parse_kda(kda_str: str):
        parts = [p.strip() for p in kda_str.replace("-", "/").split("/")]
        try:
            k, d, a = int(parts[0]), int(parts[1]), int(parts[2])
        except (IndexError, ValueError):
            k, d, a = 0, 0, 0
        return k, d, a

    ak, ad, aa = parse_kda(adc_kda)
    sk, sd, sa = parse_kda(sup_kda)
    eval_res = scheduler.evaluate_time()

    record = {
        "match_id": str(uuid.uuid4())[:8],
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "mode": eval_res["mode"],
        "result": result.value,
        "mvp": mvp or adc_player,
        "squad_players": [adc_player, sup_player],
        "lineup": {
            "Bot": {"player": adc_player, "is_squad": True, "champion": adc_champion, "kills": ak, "deaths": ad, "assists": aa},
            "Support": {"player": sup_player, "is_squad": True, "champion": sup_champion, "kills": sk, "deaths": sd, "assists": sa},
        }
    }
    is_new, saved = stats_mgr.log_match(record)

    embed = discord.Embed(
        title=f"📝 Match Logged — {result.value}",
        description=f"**Mode**: {record['mode']}\n**Botlane**: **{adc_player}** ({adc_champion} `{ak}/{ad}/{aa}`) + **{sup_player}** ({sup_champion} `{sk}/{sd}/{sa}`)",
        color=0x22C55E if result.value == "WIN" else 0xEF4444
    )
    if mvp:
        embed.add_field(name="🏆 Match MVP", value=mvp, inline=True)
    embed.set_footer(text=f"Match ID: {record['match_id']} • Living synergy threads updated!")
    await interaction.response.send_message(embed=embed, ephemeral=not public)

    if is_new:
        matched_session = stats_mgr.attach_match_to_active_session(saved)
        if matched_session:
            await notify_session(
                session=matched_session,
                activity_entry=f"🎮 Match logged: **{result.value}** (MVP: **{record['mvp']}**)",
                thread_embed=embed,
                guild=interaction.guild,
            )
        await sync_living_synergy_threads(interaction.guild)


def build_match_recap_embed(record: dict) -> discord.Embed:
    """Builds a rich match recap embed for auto-tracked matches."""
    is_win = record.get("result") == "WIN"
    color = 0x22C55E if is_win else 0xEF4444
    duration = record.get("duration_min", 0)
    mvp_name = record.get("mvp", "N/A")
    mvp_rating = record.get("mvp_rating")
    mvp_suffix = f" (`{mvp_rating}/100`)" if mvp_rating else ""

    embed = discord.Embed(
        title=f"{'🏆 Victory' if is_win else '💀 Defeat'} — {record.get('mode', 'Match')} ({duration} min)",
        description=f"**Date**: `{record.get('date')}` &bull; **MVP**: 🌟 **{mvp_name}**{mvp_suffix}",
        color=color
    )

    # Lineup display
    lineup = record.get("lineup", {})
    lineup_rows = []
    for role in ["Top", "Jungle", "Mid", "Bot", "Support"]:
        pinfo = lineup.get(role)
        if pinfo:
            star = "🐒 " if pinfo.get("is_squad") else ""
            rating_badge = (
                f" • `{pinfo['grade']} ({pinfo['rating']})`"
                if pinfo.get("rating") is not None and pinfo.get("grade")
                else ""
            )
            highlight_badge = f" *[{pinfo['highlight']}]*" if pinfo.get("highlight") and pinfo.get("is_squad") else ""
            lineup_rows.append(
                f"{star}**{role}**: **{pinfo['player']}** ({pinfo['champion']} `{pinfo['kills']}/{pinfo['deaths']}/{pinfo['assists']}`){rating_badge}{highlight_badge}"
            )
    if lineup_rows:
        embed.add_field(name="Squad Lineup", value="\n".join(lineup_rows), inline=False)

    # Botlane synergy highlight
    bot_p = lineup.get("Bot")
    sup_p = lineup.get("Support")
    if bot_p and sup_p and bot_p.get("is_squad") and sup_p.get("is_squad"):
        comb_k = bot_p["kills"] + sup_p["kills"]
        comb_d = max(1, bot_p["deaths"] + sup_p["deaths"])
        comb_a = bot_p["assists"] + sup_p["assists"]
        comb_kda = round((comb_k + comb_a) / comb_d, 2)
        embed.add_field(
            name="🏹 Botlane Synergy Updated",
            value=(
                f"**{bot_p['player']}** & **{sup_p['player']}** ({bot_p['champion']} + {sup_p['champion']})\n"
                f"Combined 2v2 KDA: `{comb_kda}`\n"
                f"Living synergy threads updated!"
            ),
            inline=False
        )

    embed.set_footer(text=f"Match ID: {record.get('match_id')} • Auto-tracked via Riot Games API")
    return embed


async def check_and_sync_recent_matches(guild: discord.Guild = None) -> list:
    """
    Queries Riot API for recently completed matches of linked squad members.
    Logs any unrecorded squad matches and returns list of newly logged matches.
    """
    if not riot_client.is_configured():
        return []

    linked = stats_mgr.get_linked_puuids()
    if not linked:
        return []

    new_logged = []
    seen_match_ids = set()

    for puuid in linked.keys():
        match_ids = await riot_client.get_recent_match_ids(puuid, count=5)
        for mid in match_ids:
            if mid in seen_match_ids or stats_mgr.is_match_logged(mid):
                continue
            seen_match_ids.add(mid)

            match_data = await riot_client.get_match_details(mid)
            if not match_data:
                continue

            # Parse squad match (minimum 2 squad members together, up to full 5-stack)
            record = riot_client.parse_squad_match(match_data, linked, min_squad_size=2)
            if record:
                is_new, saved = stats_mgr.log_match(record)
                if is_new:
                    new_logged.append(saved)

    return new_logged


@bot.tree.command(name="link-riot", description="Link your Riot ID to automatically track your match stats.")
@app_commands.describe(
    riot_id="Your Riot ID in the format GameName#TagLine (e.g. Doublelift#NA1)",
    public="Share publicly in the channel instead of a private response (default: False)"
)
async def link_riot_cmd(interaction: discord.Interaction, riot_id: str, public: bool = False):
    if not has_lolers_role(interaction.user):
        await interaction.response.send_message(
            f"⛔ Only members with the **@{ROSTER_ROLE_NAME}** role can link Riot accounts.",
            ephemeral=True
        )
        return

    if "#" not in riot_id:
        await interaction.response.send_message(
            "❌ Invalid Riot ID format. Please use `GameName#TagLine` (e.g. `Faker#KR1` or `Doublelift#NA1`).",
            ephemeral=True
        )
        return

    parts = riot_id.split("#", 1)
    game_name = parts[0].strip()
    tag_line = parts[1].strip()

    if not riot_client.is_configured():
        await interaction.response.send_message(
            "⚠️ Riot API key is not configured in `.env`. Please add your `RIOT_API_KEY` to enable Riot verification.",
            ephemeral=True
        )
        return

    await interaction.response.defer(ephemeral=not public)
    account = await riot_client.get_account_by_riot_id(game_name, tag_line)
    if not account or "puuid" not in account:
        await interaction.followup.send(
            f"❌ Could not find Riot account for **{game_name}#{tag_line}** in region `{RIOT_REGION}`. Please verify spelling and region.",
            ephemeral=True
        )
        return

    puuid = account["puuid"]
    actual_riot_id = f"{account.get('gameName', game_name)}#{account.get('tagLine', tag_line)}"
    stats_mgr.link_riot_account(
        discord_id=str(interaction.user.id),
        display_name=interaction.user.display_name,
        puuid=puuid,
        riot_id=actual_riot_id
    )

    await interaction.followup.send(
        f"✅ Successfully linked **{interaction.user.display_name}** to Riot ID **{actual_riot_id}**!\n"
        f"Your squad matches in normal, flex, and tournament queues will now be automatically recorded.",
        ephemeral=not public
    )


@bot.tree.command(name="sync-matches", description="Force check Riot API for recently completed squad games.")
@app_commands.describe(public="Share publicly in the channel instead of a private response (default: False)")
async def sync_matches_cmd(interaction: discord.Interaction, public: bool = False):
    if not has_lolers_role(interaction.user):
        await interaction.response.send_message(
            f"⛔ Only members with the **@{ROSTER_ROLE_NAME}** role can trigger a match sync.",
            ephemeral=True
        )
        return

    if not riot_client.is_configured():
        await interaction.response.send_message(
            "⚠️ Riot API key is not configured in `.env`. Please set `RIOT_API_KEY`.",
            ephemeral=True
        )
        return

    await interaction.response.defer(ephemeral=not public)
    new_matches = await check_and_sync_recent_matches(interaction.guild)

    if not new_matches:
        await interaction.followup.send("🔍 Match sync complete. No new squad matches found.", ephemeral=not public)
        return

    for m in new_matches:
        matched_session = stats_mgr.attach_match_to_active_session(m)
        if matched_session:
            await notify_session(
                session=matched_session,
                activity_entry=f"🎮 Match recorded: **{m.get('result')}** ({m.get('mode')})",
                thread_embed=build_match_recap_embed(m),
                guild=interaction.guild,
            )
    await sync_living_synergy_threads(interaction.guild)

    await interaction.followup.send(
        f"✅ Found and recorded **{len(new_matches)}** new squad match(es)! Living synergy threads updated.",
        ephemeral=not public
    )
    for m in new_matches:
        embed = build_match_recap_embed(m)
        await interaction.followup.send(embed=embed, ephemeral=not public)


# --- Automated Background Tasks: Poller & 15-Minute Countdown ---

@tasks.loop(minutes=1)
async def session_reminder_task():
    """Checks for active sessions starting within 15 minutes and transitions session lifecycle."""
    await bot.wait_until_ready()
    now_dt = datetime.now(scheduler.tz)
    pending = stats_mgr.get_pending_reminders(now_dt)

    for s in pending:
        s_id = s.get("session_id")
        stats_mgr.mark_reminder_sent(s_id)

        for guild in bot.guilds:
            channel = discord.utils.get(guild.text_channels, name=COORDINATION_CHANNEL)
            if not channel:
                continue

            starters = s.get("confirmed_players", [])
            starter_pings = []
            for p in starters:
                m = discord.utils.find(lambda x: x.display_name.lower() == p["name"].lower() or x.name.lower() == p["name"].lower(), guild.members)
                starter_pings.append(m.mention if m else f"**{p['name']}**")

            ping_str = ", ".join(starter_pings) or f"@{ROSTER_ROLE_NAME}"
            await notify_session(
                session=s,
                activity_entry="⏰ **15-minute countdown reminder sent**",
                thread_content=(
                    f"⏰ **15-MINUTE COUNTDOWN ALERT!** ({ping_str})\n"
                    f"The 5-stack session for **{s.get('scheduled_time')}** starts in 15 minutes! Ready up your League clients!"
                ),
                guild=guild,
            )

    # Check session lifecycle (transitions to IN_PROGRESS or COMPLETED)
    changed = stats_mgr.check_session_lifecycle(now_dt)
    for s in changed:
        is_done = s.get("status") in ["COMPLETED", "CANCELLED"]
        status_note = (
            "⚔️ **Session is now IN PROGRESS!**"
            if s.get("status") == "IN_PROGRESS"
            else "🏁 **Session auto-concluded**"
        )
        for guild in bot.guilds:
            if s.get("channel_id") and guild.get_channel(s["channel_id"]):
                await notify_session(
                    session=s,
                    activity_entry=status_note,
                    guild=guild,
                    remove_view=is_done,
                    archive_thread=is_done,
                )


@tasks.loop(minutes=AUTO_TRACKING_INTERVAL)
async def auto_match_tracker():
    """Polls Riot API, updates active session cards/threads, and updates living synergy threads."""
    await bot.wait_until_ready()
    if not riot_client.is_configured():
        return

    for guild in bot.guilds:
        channel = discord.utils.get(guild.text_channels, name=COORDINATION_CHANNEL)
        if not channel:
            continue

        try:
            new_matches = await check_and_sync_recent_matches(guild)
            if not new_matches:
                continue

            for m in new_matches:
                embed = build_match_recap_embed(m)

                # Only ever ping the specific players who participated in the match
                participant_pings = []
                for p_name in m.get("squad_players", []):
                    found_member = discord.utils.find(lambda x: x.display_name.lower() == p_name.lower() or x.name.lower() == p_name.lower(), guild.members)
                    participant_pings.append(found_member.mention if found_member else f"**{p_name}**")
                pings_str = ", ".join(participant_pings) or "Squad"
                recap_header = f"🎮 **Match Auto-Recorded!** ({pings_str}) &bull; **{m.get('result')}** ({m.get('mode')})"

                matched_session = stats_mgr.attach_match_to_active_session(m)
                if matched_session:
                    await notify_session(
                        session=matched_session,
                        activity_entry=f"🎮 Match recorded: **{m.get('result')}** (MVP: **{m.get('mvp', 'N/A')}**)",
                        thread_content=recap_header,
                        thread_embed=embed,
                        guild=guild,
                    )
                else:
                    await channel.send(recap_header, embed=embed)

            await sync_living_synergy_threads(guild)
        except Exception as e:
            print(f"[Tracker] Error in auto match poller: {e}")


COMMANDS_STATE_FILE = os.path.join("data", "commands_state.json")


def get_slash_commands_payload(tree: Optional[app_commands.CommandTree] = None) -> List[Dict[str, Any]]:
    """Serialize all registered slash commands in deterministic order for change detection."""
    target_tree = tree or bot.tree
    payloads = [cmd.to_dict(target_tree) for cmd in target_tree.get_commands()]
    return sorted(payloads, key=lambda c: c.get("name", ""))


def compute_commands_hash(payloads: List[Dict[str, Any]]) -> str:
    """Compute a deterministic SHA-256 hash of the slash command registration payloads."""
    canonical = json.dumps(payloads, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def detect_slash_command_changes(
    tree: Optional[app_commands.CommandTree] = None,
    state_file: str = COMMANDS_STATE_FILE,
) -> Dict[str, Any]:
    """
    Compare current slash command definitions against the last registered state on disk.
    Returns a dictionary detailing whether re-registration with Discord is needed and which
    commands were added, removed, or modified.
    """
    payloads = get_slash_commands_payload(tree)
    current_hash = compute_commands_hash(payloads)
    current_map = {c["name"]: c for c in payloads}

    if not os.path.exists(state_file):
        return {
            "changed": True,
            "first_run": True,
            "current_hash": current_hash,
            "previous_hash": None,
            "added": sorted(current_map.keys()),
            "removed": [],
            "modified": [],
            "payloads": payloads,
        }

    try:
        with open(state_file, "r", encoding="utf-8") as f:
            saved = json.load(f)
        previous_hash = saved.get("hash")
        saved_commands = saved.get("commands", {})
    except Exception:
        return {
            "changed": True,
            "first_run": True,
            "current_hash": current_hash,
            "previous_hash": None,
            "added": sorted(current_map.keys()),
            "removed": [],
            "modified": [],
            "payloads": payloads,
        }

    added = sorted(name for name in current_map if name not in saved_commands)
    removed = sorted(name for name in saved_commands if name not in current_map)
    modified = sorted(
        name
        for name in current_map
        if name in saved_commands
        and json.dumps(current_map[name], sort_keys=True) != json.dumps(saved_commands[name], sort_keys=True)
    )
    changed = (previous_hash != current_hash) or bool(added or removed or modified)

    return {
        "changed": changed,
        "first_run": False,
        "current_hash": current_hash,
        "previous_hash": previous_hash,
        "added": added,
        "removed": removed,
        "modified": modified,
        "payloads": payloads,
    }


def save_slash_command_state(
    payloads: List[Dict[str, Any]],
    current_hash: str,
    state_file: str = COMMANDS_STATE_FILE,
) -> None:
    """Persist the currently registered slash command schema and hash to disk."""
    os.makedirs(os.path.dirname(state_file) or ".", exist_ok=True)
    state_data = {
        "hash": current_hash,
        "synced_at": datetime.now().isoformat(),
        "commands": {c["name"]: c for c in payloads},
    }
    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(state_data, f, indent=2, sort_keys=True)


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print(f"Channel Lock Active: #{COORDINATION_CHANNEL}")
    print(f"Roster Role Active: @{ROSTER_ROLE_NAME}")

    # Register persistent RSVP views for all active sessions
    active_sessions = stats_mgr.get_active_sessions()
    registered_views = 0
    for s in active_sessions:
        s_id = s.get("session_id")
        bot.add_view(SessionRSVPView(s_id))
        registered_views += 1
    if registered_views > 0:
        print(f"Re-registered {registered_views} persistent session RSVP view(s).")

    # Start 15-minute countdown reminder loop
    if not session_reminder_task.is_running():
        session_reminder_task.start()
        print("15-minute session countdown reminder task started.")

    if riot_client.is_configured():
        print(f"Riot API Active (Region: {RIOT_REGION}, Poll Interval: {AUTO_TRACKING_INTERVAL}m)")
        if not auto_match_tracker.is_running():
            auto_match_tracker.start()
    else:
        print("Riot API not configured: Add RIOT_API_KEY to .env to enable auto-tracking.")

    try:
        await sync_living_synergy_threads()
        print("Living synergy threads synchronized.")
    except Exception as e:
        print(f"Warning: Could not synchronize living synergy threads: {e}")

    force_sync = (
        os.getenv("FORCE_COMMAND_SYNC", "false").lower() in ("1", "true", "yes")
        or "--sync" in sys.argv
        or "--force-sync" in sys.argv
    )
    cmd_diff = detect_slash_command_changes(bot.tree)

    if force_sync or cmd_diff["changed"]:
        try:
            if force_sync and not cmd_diff["changed"]:
                print("Force command sync requested — re-registering slash commands with Discord...")
            elif cmd_diff["first_run"]:
                print(f"No cached command state found — registering {len(cmd_diff['payloads'])} slash commands with Discord...")
            else:
                changes = []
                if cmd_diff["added"]:
                    changes.append(f"added: {', '.join('/' + c for c in cmd_diff['added'])}")
                if cmd_diff["modified"]:
                    changes.append(f"modified: {', '.join('/' + c for c in cmd_diff['modified'])}")
                if cmd_diff["removed"]:
                    changes.append(f"removed: {', '.join('/' + c for c in cmd_diff['removed'])}")
                print(f"Slash command changes detected ({'; '.join(changes)}) — re-registering with Discord...")

            synced = await bot.tree.sync()
            save_slash_command_state(cmd_diff["payloads"], cmd_diff["current_hash"])
            os.environ.pop("FORCE_COMMAND_SYNC", None)
            print(f"Synced {len(synced)} application commands (schema hash: {cmd_diff['current_hash'][:8]}).")
        except Exception as e:
            print(f"Failed to sync commands: {e}")
    else:
        print(
            f"Slash commands unchanged ({len(cmd_diff['payloads'])} commands, "
            f"schema hash: {cmd_diff['current_hash'][:8]}) — skipping Discord re-registration."
        )


if __name__ == "__main__":
    TOKEN = os.getenv("DISCORD_BOT_TOKEN")
    if not TOKEN:
        print("Please set DISCORD_BOT_TOKEN environment variable in .env file.")
    else:
        try:
            bot.run(TOKEN)
        finally:
            if riot_client:
                import asyncio
                asyncio.run(riot_client.close())
