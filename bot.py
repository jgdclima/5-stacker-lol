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


def has_lolers_role(user: discord.User | discord.Member) -> bool:
    """Check if a Discord user possesses the required @LOLers role."""
    if not isinstance(user, discord.Member):
        return False
    return any(r.name.lower() == ROSTER_ROLE_NAME.lower() for r in user.roles)


async def check_channel_restriction(interaction: discord.Interaction) -> bool:
    """
    Enforces that all slash commands, button clicks, and modal submissions
    occur strictly within the #5-stackers text channel.
    The bot will not interact with or message any other channel.
    """
    channel = interaction.channel
    if not channel or getattr(channel, "name", None) != COORDINATION_CHANNEL:
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
    outside of the #5-stackers text channel.
    """
    if message.author.bot:
        return
    # The bot must not interact with or message any other text channel
    if not message.channel or getattr(message.channel, "name", None) != COORDINATION_CHANNEL:
        return
    await bot.process_commands(message)


# --- Interactive Discord UI: Multi-Select Role Dropdown & Persistent RSVP View ---

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

        # Update the original session embed in the channel
        embed = build_session_embed(session, interaction.guild)
        msg_to_edit = self.session_message
        if not msg_to_edit and session.get("channel_id") and session.get("message_id"):
            try:
                ch = interaction.guild.get_channel(session["channel_id"]) if interaction.guild else None
                if not ch:
                    ch = bot.get_channel(session["channel_id"]) or await bot.fetch_channel(session["channel_id"])
                if ch:
                    msg_to_edit = await ch.fetch_message(session["message_id"])
            except Exception as e:
                print(f"[RSVP] Could not fetch session message: {e}")

        if msg_to_edit:
            try:
                await msg_to_edit.edit(embed=embed)
            except Exception as e:
                print(f"[RSVP] Error updating session message embed: {e}")

        if quorum_met and len(session["confirmed_players"]) == 5:
            role = discord.utils.find(lambda r: r.name.lower() == ROSTER_ROLE_NAME.lower(), interaction.guild.roles) if interaction.guild else None
            role_mention = role.mention if role else f"@{ROSTER_ROLE_NAME}"
            players_ping = ", ".join([f"**{p['name']}**" for p in session['confirmed_players']])
            mode_announcement = (
                f"🛡️ **Ranked 5s Mode Window is OPEN!** Time to queue tournament draft!"
                if session['is_ranked_5s']
                else f"⚡ **Ranked Flex Fallback**: Ranked 5s window closed, but 5-stack Ranked Flex is ready to launch!"
            )
            if interaction.channel:
                await interaction.channel.send(
                    f"🚨 **LOBBY READY! 5-PLAYER QUORUM REACHED!** ({role_mention})\n"
                    f"Starting 5: {players_ping}\n"
                    f"Target Queue: **{session['mode']}**\n{mode_announcement}"
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

            # Delete the channel RSVP message
            msg_to_delete = self.session_message
            if not msg_to_delete and session.get("channel_id") and session.get("message_id"):
                try:
                    ch = interaction.guild.get_channel(session["channel_id"]) if interaction.guild else None
                    if not ch:
                        ch = bot.get_channel(session["channel_id"]) or await bot.fetch_channel(session["channel_id"])
                    if ch:
                        msg_to_delete = await ch.fetch_message(session["message_id"])
                except Exception as e:
                    print(f"[Cancel] Could not fetch message to delete: {e}")

            if msg_to_delete:
                try:
                    await msg_to_delete.delete()
                except Exception as e:
                    print(f"[Cancel] Error deleting session message: {e}")

            # Notify in channel pinging all affected players
            affected_pings = []
            if interaction.guild:
                for name in affected:
                    m = discord.utils.find(lambda x: x.display_name.lower() == name.lower() or x.name.lower() == name.lower(), interaction.guild.members)
                    affected_pings.append(m.mention if m else f"**{name}**")
            pings_str = ", ".join(affected_pings)

            channel = interaction.channel
            if channel:
                cancel_msg = (
                    f"🛑 **SESSION CANCELLED**\n"
                    f"The 5-stack session for **{session.get('scheduled_time')}** was cancelled by **{interaction.user.display_name}**."
                )
                if pings_str:
                    cancel_msg += f"\n📢 Attention {pings_str}: This session will no longer take place."
                await channel.send(cancel_msg)

            await interaction.response.edit_message(
                content=f"✅ Session `{self.session_id}` was cancelled and removed.",
                view=None
            )

        elif self.action_type == "END":
            success, session = stats_mgr.complete_session(self.session_id)
            if not success:
                await interaction.response.edit_message(content="❌ Could not end session.", view=None)
                return

            # Update the channel RSVP message: remove buttons and show COMPLETED embed
            embed = build_session_embed(session, interaction.guild)
            msg_to_edit = self.session_message
            if not msg_to_edit and session.get("channel_id") and session.get("message_id"):
                try:
                    ch = interaction.guild.get_channel(session["channel_id"]) if interaction.guild else None
                    if not ch:
                        ch = bot.get_channel(session["channel_id"]) or await bot.fetch_channel(session["channel_id"])
                    if ch:
                        msg_to_edit = await ch.fetch_message(session["message_id"])
                except Exception as e:
                    print(f"[End] Could not fetch message to update: {e}")

            if msg_to_edit:
                try:
                    await msg_to_edit.edit(embed=embed, view=None)
                except Exception as e:
                    print(f"[End] Error editing message: {e}")

            channel = interaction.channel
            if channel:
                await channel.send(
                    f"🏁 **Session Concluded**: The 5-stack session for **{session.get('scheduled_time')}** has officially concluded! Thanks for playing, squad!"
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
        embed = build_session_embed(session, interaction.guild)
        await interaction.response.edit_message(embed=embed)

        if promoted and interaction.channel:
            await interaction.channel.send(
                f"📢 **Roster Auto-Promotion**: {interaction.user.display_name} stepped down. **{promoted['name']}** has been promoted from the bench into the Starting 5!"
            )

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
            f"This will delete the RSVP message and notify all signed-up players.",
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

    embed = discord.Embed(
        title="🎮 League of Legends 5-Stack Coordinator",
        description=f"{status_badge}\n\n"
                    f"**Session ID**: `{session.get('session_id')}`\n"
                    f"**Organizer**: **{creator_name}**\n"
                    f"**Target Window**: `{session.get('scheduled_time')}`\n"
                    f"**Detected Mode**: **{session.get('mode')}**\n"
                    f"{'🏆 *Ranked 5s Tournament Draft Active*' if session.get('is_ranked_5s') else '🔄 *Ranked Flex 24/7 Fallback Active*'}",
        color=status_color
    )

    # Starters (Minimum 5 required)
    starters_text = "\n".join([f"{i+1}. **{p['name']}** — *{p['role_pref']}*" for i, p in enumerate(confirmed)]) or "*No players registered yet.*"
    embed.add_field(name=f"Starting Roster ({count}/5)", value=starters_text, inline=False)

    # Bench / Overflow
    bench_text = "\n".join([f"• **{p['name']}** ({p['role_pref']})" for p in bench]) or "*Empty*"
    embed.add_field(name=f"Substitutes / Bench ({len(bench)})", value=bench_text, inline=True)

    # Unavailable
    declined_text = ", ".join(declined) or "*None*"
    embed.add_field(name="Unavailable", value=declined_text, inline=True)
    return embed


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

    try:
        session_msg = await interaction.channel.send(
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

    await interaction.followup.send(
        f"✅ 5-stack session `{session_id}` announced in {interaction.channel.mention}!",
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

    embed = build_session_embed(session, interaction.guild)
    view = SessionRSVPView(session_id)

    affected_pings = []
    if interaction.guild:
        for name in affected:
            m = discord.utils.find(lambda x: x.display_name.lower() == name.lower() or x.name.lower() == name.lower(), interaction.guild.members)
            affected_pings.append(m.mention if m else f"**{name}**")
    pings_str = ", ".join(affected_pings) or "Signed-up players"

    await interaction.response.send_message(
        f"⚠️ **SESSION RESCHEDULED!**\n"
        f"Attention {pings_str}: **{interaction.user.display_name}** changed the session time to **{display_time}** ({eval_res['mode']}).\n"
        f"Please check your availability and update your RSVP if needed!",
        embed=embed,
        view=view
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

    # Delete channel RSVP message if present
    if session.get("channel_id") and session.get("message_id"):
        try:
            ch = interaction.guild.get_channel(session["channel_id"]) if interaction.guild else None
            if not ch:
                ch = bot.get_channel(session["channel_id"]) or await bot.fetch_channel(session["channel_id"])
            if ch:
                msg = await ch.fetch_message(session["message_id"])
                await msg.delete()
        except Exception as e:
            print(f"[Slash Cancel] Error deleting message: {e}")

    affected_pings = []
    if interaction.guild:
        for name in affected:
            m = discord.utils.find(lambda x: x.display_name.lower() == name.lower() or x.name.lower() == name.lower(), interaction.guild.members)
            affected_pings.append(m.mention if m else f"**{name}**")
    pings_str = ", ".join(affected_pings)

    cancel_msg = f"🛑 **Session Cancelled**: The session `{session_id}` ({session.get('scheduled_time')}) was cancelled by **{interaction.user.display_name}**."
    if pings_str:
        cancel_msg += f"\n📢 Attention {pings_str}: This session will no longer take place."

    await interaction.response.send_message(cancel_msg)


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

    # Update original session RSVP message
    if session.get("channel_id") and session.get("message_id"):
        try:
            ch = interaction.guild.get_channel(session["channel_id"]) if interaction.guild else None
            if not ch:
                ch = bot.get_channel(session["channel_id"]) or await bot.fetch_channel(session["channel_id"])
            if ch:
                msg = await ch.fetch_message(session["message_id"])
                embed = build_session_embed(session, interaction.guild)
                await msg.edit(embed=embed, view=None)
        except Exception as e:
            print(f"[Slash End] Error updating message: {e}")

    await interaction.response.send_message(
        f"🏁 **Session Concluded**: The session `{session_id}` ({session.get('scheduled_time')}) was ended by **{interaction.user.display_name}**. Thanks for playing!"
    )


@bot.tree.command(name="sessions", description="List all active and recent 5-stack sessions.")
async def sessions_cmd(interaction: discord.Interaction):
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
            active_lines.append(
                f"• `{s.get('session_id')}`: **{s.get('scheduled_time')}** ({s.get('mode')}) — {badge} ({count}/5)\n"
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

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="queue-check", description="Check current Ranked 5s window status and next opening.")
async def queue_check_cmd(interaction: discord.Interaction):
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
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="synergy", description="View duo chemistry and win rates across team positions.")
@app_commands.describe(pair_type="The duo partnership to inspect")
@app_commands.choices(pair_type=[
    app_commands.Choice(name="Botlane (ADC + Support)", value="botlane"),
    app_commands.Choice(name="Mid + Jungle (2v2 Core)", value="mid_jungle"),
    app_commands.Choice(name="Top + Jungle (Topside Synergy)", value="top_jungle"),
    app_commands.Choice(name="Support + Jungle (Roam & Objectives)", value="support_jungle"),
])
async def synergy_cmd(interaction: discord.Interaction, pair_type: app_commands.Choice[str]):
    mapping = {
        "botlane": ("🏹 Botlane (ADC + Support)", stats_mgr.get_botlane_synergies()),
        "mid_jungle": ("⚡ Mid + Jungle (2v2 Core)", stats_mgr.get_mid_jungle_synergies()),
        "top_jungle": ("🛡️ Top + Jungle (Topside Synergy)", stats_mgr.get_top_jungle_synergies()),
        "support_jungle": ("✨ Support + Jungle (Roam & Objectives)", stats_mgr.get_support_jungle_synergies()),
    }
    title, duos = mapping.get(pair_type.value, mapping["botlane"])

    if not duos:
        await interaction.response.send_message(f"No match history recorded yet for **{title}**.", ephemeral=True)
        return

    embed = discord.Embed(
        title=f"Chemistry Leaderboard — {title}",
        description=f"Pairwise performance across 5-stack & squad games in **#{COORDINATION_CHANNEL}**.",
        color=0xEC4899
    )

    for duo in duos[:5]:
        embed.add_field(
            name=f"{duo['pair']} — {duo['tier']} ({duo['synergy_score']}/100)",
            value=(
                f"**Record**: {duo['wins']}W - {duo['losses']}L ({duo['win_rate']}% WR in {duo['games']} games)\n"
                f"**Duo KDA**: {duo['combined_kda']} | **Tag**: `{duo['tag']}`\n"
                f"**Signature Combo**: `{duo['favorite_combo']}`"
            ),
            inline=False
        )

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="botlane", description="Check Bot + Support duo chemistry ratings and win rates.")
async def botlane_cmd(interaction: discord.Interaction):
    duos = stats_mgr.get_botlane_synergies()
    if not duos:
        await interaction.response.send_message("No botlane duo matches recorded yet. Log a match using `/log-match`!", ephemeral=True)
        return

    embed = discord.Embed(
        title="🏹 Botlane Synergy & Chemistry Ratings",
        description=f"Performance when @{ROSTER_ROLE_NAME} bot & support play together in 5-stack sessions.",
        color=0xEC4899
    )

    for duo in duos[:5]:
        embed.add_field(
            name=f"{duo['pair']} — {duo['tier']} ({duo['synergy_score']}/100)",
            value=(
                f"**Record**: {duo['wins']}W - {duo['losses']}L ({duo['win_rate']}% WR in {duo['games']} games)\n"
                f"**Duo KDA**: {duo['combined_kda']} | **Tag**: `{duo['tag']}`\n"
                f"**Signature Combo**: `{duo['favorite_combo']}`"
            ),
            inline=False
        )

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="roster", description=f"View all members holding the @{ROSTER_ROLE_NAME} role and their stats.")
async def roster_cmd(interaction: discord.Interaction):
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
            p_stat = leaderboard_map.get(member.display_name.lower())
            if p_stat:
                stat_str = f"**WR**: {p_stat['win_rate']}% ({p_stat['wins']}W-{p_stat['losses']}L) | **KDA**: {p_stat['kda']} | 🏆 {p_stat['mvps']} MVPs"
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
            embed.add_field(
                name=f"{p['name']} ({p['main_role']})",
                value=f"**WR**: {p['win_rate']}% ({p['wins']}W-{p['losses']}L) | **KDA**: {p['kda']} | **MVPs**: 🏆 {p['mvps']}",
                inline=True
            )
        embed.set_footer(text=f"Ensure the @{ROSTER_ROLE_NAME} role exists in your Discord server.")

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="log-match", description="Log a completed 5-stack match and update synergy/player stats.")
@app_commands.describe(
    result="Match outcome (WIN or LOSS)",
    adc_player="Player in Bot (ADC) role",
    adc_champion="Champion played by ADC",
    adc_kda="ADC Kills/Deaths/Assists (e.g. 8/2/10)",
    sup_player="Player in Support role",
    sup_champion="Champion played by Support",
    sup_kda="Support Kills/Deaths/Assists (e.g. 1/3/18)",
    mvp="Match MVP player name (optional)"
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
    mvp: str = ""
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
        "lineup": {
            "Bot": {"player": adc_player, "champion": adc_champion, "kills": ak, "deaths": ad, "assists": aa},
            "Support": {"player": sup_player, "champion": sup_champion, "kills": sk, "deaths": sd, "assists": sa},
        }
    }
    is_new, _ = stats_mgr.log_match(record)

    embed = discord.Embed(
        title=f"📝 Match Logged — {result.value}",
        description=f"**Mode**: {record['mode']}\n**Botlane**: **{adc_player}** ({adc_champion} `{ak}/{ad}/{aa}`) + **{sup_player}** ({sup_champion} `{sk}/{sd}/{sa}`)",
        color=0x22C55E if result.value == "WIN" else 0xEF4444
    )
    if mvp:
        embed.add_field(name="🏆 Match MVP", value=mvp, inline=True)
    embed.set_footer(text=f"Match ID: {record['match_id']} • Use /botlane to view updated synergy!")
    await interaction.response.send_message(embed=embed)


def build_match_recap_embed(record: dict) -> discord.Embed:
    """Builds a rich match recap embed for auto-tracked matches."""
    is_win = record.get("result") == "WIN"
    color = 0x22C55E if is_win else 0xEF4444
    duration = record.get("duration_min", 0)

    embed = discord.Embed(
        title=f"{'🏆 Victory' if is_win else '💀 Defeat'} — {record.get('mode', 'Match')} ({duration} min)",
        description=f"**Date**: `{record.get('date')}` &bull; **MVP**: 🌟 **{record.get('mvp', 'N/A')}**",
        color=color
    )

    # Lineup display
    lineup = record.get("lineup", {})
    lineup_rows = []
    for role in ["Top", "Jungle", "Mid", "Bot", "Support"]:
        pinfo = lineup.get(role)
        if pinfo:
            star = "🐒 " if pinfo.get("is_squad") else ""
            lineup_rows.append(
                f"{star}**{role}**: **{pinfo['player']}** ({pinfo['champion']} `{pinfo['kills']}/{pinfo['deaths']}/{pinfo['assists']}`)"
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
                f"Use `/botlane` to view updated chemistry tier!"
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
@app_commands.describe(riot_id="Your Riot ID in the format GameName#TagLine (e.g. Doublelift#NA1)")
async def link_riot_cmd(interaction: discord.Interaction, riot_id: str):
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

    await interaction.response.defer(ephemeral=False)
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
        f"Your squad matches in normal, flex, and tournament queues will now be automatically recorded."
    )


@bot.tree.command(name="sync-matches", description="Force check Riot API for recently completed squad games.")
async def sync_matches_cmd(interaction: discord.Interaction):
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

    await interaction.response.defer(ephemeral=False)
    new_matches = await check_and_sync_recent_matches(interaction.guild)

    if not new_matches:
        await interaction.followup.send("🔍 Match sync complete. No new squad matches found.")
        return

    await interaction.followup.send(f"✅ Found and recorded **{len(new_matches)}** new squad match(es)!")
    for m in new_matches:
        embed = build_match_recap_embed(m)
        await interaction.followup.send(embed=embed)


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
            await channel.send(
                f"⏰ **15-MINUTE COUNTDOWN ALERT!** ({ping_str})\n"
                f"The 5-stack session for **{s.get('scheduled_time')}** starts in 15 minutes! Ready up your League clients!"
            )

    # Check session lifecycle (transitions to IN_PROGRESS or COMPLETED)
    changed = stats_mgr.check_session_lifecycle(now_dt)
    for s in changed:
        if s.get("channel_id") and s.get("message_id"):
            for guild in bot.guilds:
                channel = guild.get_channel(s["channel_id"])
                if channel:
                    try:
                        msg = await channel.fetch_message(s["message_id"])
                        embed = build_session_embed(s, guild)
                        new_view = None if s.get("status") in ["COMPLETED", "CANCELLED"] else SessionRSVPView(s.get("session_id"))
                        await msg.edit(embed=embed, view=new_view)
                    except Exception as e:
                        print(f"[Lifecycle] Error updating session message: {e}")


@tasks.loop(minutes=AUTO_TRACKING_INTERVAL)
async def auto_match_tracker():
    """Polls Riot API and broadcasts squad games, pinging only participants."""
    await bot.wait_until_ready()
    if not riot_client.is_configured():
        return

    for guild in bot.guilds:
        channel = discord.utils.get(guild.text_channels, name=COORDINATION_CHANNEL)
        if not channel:
            continue

        try:
            new_matches = await check_and_sync_recent_matches(guild)
            for m in new_matches:
                embed = build_match_recap_embed(m)
                
                # Only ever ping the specific players who participated in the match
                participant_pings = []
                for p_name in m.get("squad_players", []):
                    found_member = discord.utils.find(lambda x: x.display_name.lower() == p_name.lower() or x.name.lower() == p_name.lower(), guild.members)
                    participant_pings.append(found_member.mention if found_member else f"**{p_name}**")
                pings_str = ", ".join(participant_pings) or "Squad"

                await channel.send(
                    f"🎮 **Match Auto-Recorded!** ({pings_str}) &bull; **{m.get('result')}** ({m.get('mode')})",
                    embed=embed
                )
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
