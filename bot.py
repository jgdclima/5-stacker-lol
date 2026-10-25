"""
League of Legends 5-Stack Coordinator Discord Bot.
Enforces:
1. All session coordination strictly locked to text channel: #5-stackers.
   The bot ignores and does not interact with or post to any other channel.
2. The active roster is strictly defined by the "LOLers" role.
   Only members with the @LOLers role can organize, RSVP, or be listed on the roster.
"""

import os
import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime
import uuid
from dotenv import load_dotenv

from schedule_checker import RankedSchedule
from data_manager import StatsManager

load_dotenv()

# --- Configuration & Channel/Role Locking ---
COORDINATION_CHANNEL = os.getenv("COORDINATION_CHANNEL", "5-stackers")
ROSTER_ROLE_NAME = os.getenv("ROSTER_ROLE", "LOLers")
SERVER_TIMEZONE = os.getenv("SERVER_TIMEZONE", "America/Vancouver")
RANKED_5S_START_HOUR = int(os.getenv("RANKED_5S_START_HOUR", "20"))
RANKED_5S_END_HOUR = int(os.getenv("RANKED_5S_END_HOUR", "1"))

# Bot Setup
intents = discord.Intents.default()
intents.message_content = True
intents.members = True  # Required to query members holding the @LOLers role
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


# --- Interactive Discord UI: Session RSVP View ---

class RoleSelectModal(discord.ui.Modal, title="Select Role Preference"):
    def __init__(self, session_id: str, action_type: str):
        super().__init__()
        self.session_id = session_id
        self.action_type = action_type
        self.role_input = discord.ui.TextInput(
            label="Preferred Role(s)",
            placeholder="e.g. Bot, Support, Mid, Jungle, Top, Fill",
            default="Fill",
            max_length=20
        )
        self.add_item(self.role_input)

    async def on_submit(self, interaction: discord.Interaction):
        # Double check @LOLers role
        if not has_lolers_role(interaction.user):
            await interaction.response.send_message(
                f"⛔ Only members with the **@{ROSTER_ROLE_NAME}** role can join the 5-stack roster.",
                ephemeral=True
            )
            return

        role_pref = self.role_input.value.strip() or "Fill"
        quorum_met, session = stats_mgr.register_player(
            session_id=self.session_id,
            player_name=interaction.user.display_name,
            status=self.action_type,
            role_pref=role_pref
        )
        embed = build_session_embed(session, interaction.guild)
        await interaction.response.edit_message(embed=embed)

        if quorum_met and len(session["confirmed_players"]) == 5:
            # Announce quorum ping in #5-stackers mentioning the @LOLers role
            role = discord.utils.find(lambda r: r.name.lower() == ROSTER_ROLE_NAME.lower(), interaction.guild.roles) if interaction.guild else None
            role_mention = role.mention if role else f"@{ROSTER_ROLE_NAME}"
            
            players_ping = ", ".join([f"**{p['name']}**" for p in session['confirmed_players']])
            mode_announcement = (
                f"🛡️ **Ranked 5s Mode Window is OPEN!** Time to queue tournament draft!"
                if session['is_ranked_5s']
                else f"⚡ **Ranked Flex Fallback**: Ranked 5s window closed, but 5-stack Ranked Flex is ready to launch!"
            )
            await interaction.followup.send(
                f"🚨 **LOBBY READY! 5-PLAYER QUORUM REACHED!** ({role_mention})\n"
                f"Starting 5: {players_ping}\n"
                f"Target Queue: **{session['mode']}**\n{mode_announcement}",
                ephemeral=False
            )


class SessionRSVPView(discord.ui.View):
    def __init__(self, session_id: str):
        super().__init__(timeout=None)
        self.session_id = session_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return await check_channel_restriction(interaction)

    @discord.ui.button(label="✅ Join 5-Stack", style=discord.ButtonStyle.green, custom_id="join_session")
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not has_lolers_role(interaction.user):
            await interaction.response.send_message(
                f"⛔ Access Denied: You must have the **@{ROSTER_ROLE_NAME}** role to join 5-stack sessions.",
                ephemeral=True
            )
            return
        await interaction.response.send_modal(RoleSelectModal(self.session_id, "CONFIRMED"))

    @discord.ui.button(label="⏳ Sub / Bench", style=discord.ButtonStyle.secondary, custom_id="bench_session")
    async def bench_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not has_lolers_role(interaction.user):
            await interaction.response.send_message(
                f"⛔ Access Denied: You must have the **@{ROSTER_ROLE_NAME}** role to join as a substitute.",
                ephemeral=True
            )
            return
        await interaction.response.send_modal(RoleSelectModal(self.session_id, "BENCH"))

    @discord.ui.button(label="❌ Can't Make It", style=discord.ButtonStyle.danger, custom_id="decline_session")
    async def decline_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not has_lolers_role(interaction.user):
            await interaction.response.send_message(
                f"⛔ Access Denied: Only **@{ROSTER_ROLE_NAME}** members are tracked on the roster.",
                ephemeral=True
            )
            return
        _, session = stats_mgr.register_player(
            session_id=self.session_id,
            player_name=interaction.user.display_name,
            status="DECLINED"
        )
        embed = build_session_embed(session, interaction.guild)
        await interaction.response.edit_message(embed=embed)


def build_session_embed(session: dict, guild: discord.Guild = None) -> discord.Embed:
    confirmed = session["confirmed_players"]
    bench = session["bench_substitutes"]
    declined = session["declined"]
    count = len(confirmed)

    status_color = 0x22C55E if count >= 5 else 0x3B82F6  # Green if ready, blue if polling
    embed = discord.Embed(
        title="🎮 League of Legends 5-Stack Coordinator",
        description=f"**Channel**: `#{COORDINATION_CHANNEL}` &bull; **Roster Role**: `@{ROSTER_ROLE_NAME}`\n"
                    f"**Target Window**: `{session['scheduled_time']}`\n"
                    f"**Detected Mode**: **{session['mode']}**\n"
                    f"{'🏆 *Ranked 5s Tournament Draft Active*' if session['is_ranked_5s'] else '🔄 *Ranked Flex 24/7 Fallback Active*'}",
        color=status_color
    )

    # Starters (Minimum 5 required)
    starters_text = "\n".join([f"{i+1}. **{p['name']}** — *{p['role_pref']}*" for i, p in enumerate(confirmed)]) or "*No players registered yet.*"
    status_indicator = "✅ **LOBBY READY (5/5)**" if count >= 5 else f"⏳ **Recruiting: {count}/5 Players** (Needs {5-count} more from @{ROSTER_ROLE_NAME})"
    embed.add_field(name=f"Starting Roster ({count}/5)", value=f"{status_indicator}\n{starters_text}", inline=False)

    # Bench / Overflow
    bench_text = "\n".join([f"• **{p['name']}** ({p['role_pref']})" for p in bench]) or "*Empty*"
    embed.add_field(name=f"Substitutes / Bench ({len(bench)})", value=bench_text, inline=True)

    # Unavailable
    declined_text = ", ".join(declined) or "*None*"
    embed.add_field(name="Unavailable", value=declined_text, inline=True)

    embed.set_footer(text=f"Coordination restricted to #{COORDINATION_CHANNEL} • Roster restricted to @{ROSTER_ROLE_NAME}")
    return embed


# --- Slash Commands ---

@bot.tree.command(name="session", description=f"Propose a new 5-stack session in #{COORDINATION_CHANNEL}.")
@app_commands.describe(time_window="Proposed date and time (e.g. 'Tonight 8:30 PM', 'Saturday 9:00 PM')")
async def session_cmd(interaction: discord.Interaction, time_window: str):
    if not has_lolers_role(interaction.user):
        await interaction.response.send_message(
            f"⛔ Only members with the **@{ROSTER_ROLE_NAME}** role can organize 5-stack sessions.",
            ephemeral=True
        )
        return

    eval_res = scheduler.evaluate_time()
    session_id = str(uuid.uuid4())[:8]

    session = stats_mgr.create_session(
        session_id=session_id,
        scheduled_time=time_window,
        mode=eval_res["mode"],
        is_ranked_5s=eval_res["is_ranked_5s"],
        creator=interaction.user.display_name
    )

    view = SessionRSVPView(session_id)
    embed = build_session_embed(session, interaction.guild)
    
    # Mention the @LOLers role so the squad gets alerted in #5-stackers
    role = discord.utils.find(lambda r: r.name.lower() == ROSTER_ROLE_NAME.lower(), interaction.guild.roles) if interaction.guild else None
    role_mention = role.mention if role else f"@{ROSTER_ROLE_NAME}"

    await interaction.response.send_message(
        f"📢 {role_mention}: **{interaction.user.display_name}** proposed a 5-stack session in **#{COORDINATION_CHANNEL}**! Who's in?",
        embed=embed,
        view=view
    )


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
                f"**Record**: {duo['wins']}W - {duo['losses']}L ({duo['win_rate']}% WR)\n"
                f"**Duo KDA**: {duo['combined_kda']} | **Tag**: {duo['tag']}\n"
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
    stats_mgr.log_match(record)

    embed = discord.Embed(
        title=f"📝 Match Logged — {result.value}",
        description=f"**Mode**: {record['mode']}\n**Botlane**: **{adc_player}** ({adc_champion} `{ak}/{ad}/{aa}`) + **{sup_player}** ({sup_champion} `{sk}/{sd}/{sa}`)",
        color=0x22C55E if result.value == "WIN" else 0xEF4444
    )
    if mvp:
        embed.add_field(name="🏆 Match MVP", value=mvp, inline=True)
    embed.set_footer(text=f"Match ID: {record['match_id']} • Use /botlane to view updated synergy!")
    await interaction.response.send_message(embed=embed)


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print(f"Channel Lock Active: #{COORDINATION_CHANNEL}")
    print(f"Roster Role Active: @{ROSTER_ROLE_NAME}")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} application commands.")
    except Exception as e:
        print(f"Failed to sync commands: {e}")


if __name__ == "__main__":
    TOKEN = os.getenv("DISCORD_BOT_TOKEN")
    if not TOKEN:
        print("Please set DISCORD_BOT_TOKEN environment variable in .env file.")
    else:
        bot.run(TOKEN)
