"""Deepwoken Carry Bot rewrite (discord.py 2.5+)."""
import asyncio
import os
import random
import sqlite3
import string
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands, tasks
from dotenv import load_dotenv

load_dotenv()
# New database name avoids colliding with the old bot's incompatible schema.
DB_PATH = Path("data/deepwoken_bot.db")
REGIONS = ["NA", "EU", "SA", "Asia", "Oceania"]
TICKET_TYPES = {"pve": "PvE Application", "tryout": "Tryout Application", "help": "General Help"}
BOT_CHANNELS = ["carry-pings", "gank-pings", "application-reviews", "tickets", "reactions", "giveaways", "bot-logs", "version", "update-log"]
OLD_BOSS_PINGS = ["Enmity Ping", "Elder Ping", "Titus Ping"]
CARRY_BOSSES = {"Enmity": 16, "Elder": 16, "Titus": 6}
BOT_VERSION = "v2.0.0 — ENMITY"
SPAM_MESSAGE_LIMIT = 6
SPAM_MESSAGE_WINDOW = 10
PRIMARY_GUILD_ID = int(os.getenv("GUILD_ID", "0"))
REGENT_VERSION = "v2.1.0 — REGENT"


class Store:
    def __init__(self):
        DB_PATH.parent.mkdir(exist_ok=True)
        self.db = sqlite3.connect(DB_PATH, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS blacklist (guild_id INTEGER, user_id INTEGER, reason TEXT, added_by INTEGER, PRIMARY KEY(guild_id,user_id));
        CREATE TABLE IF NOT EXISTS carries (message_id INTEGER PRIMARY KEY, guild_id INTEGER, host_id INTEGER, boss TEXT, region TEXT, max_players INTEGER, joined TEXT DEFAULT '', created_at INTEGER);
        CREATE TABLE IF NOT EXISTS giveaways (message_id INTEGER PRIMARY KEY, guild_id INTEGER, channel_id INTEGER, prize TEXT, ends_at INTEGER, winners INTEGER, entrants TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS tickets (ticket_id TEXT PRIMARY KEY, guild_id INTEGER, channel_id INTEGER, opener_id INTEGER, kind TEXT, created_at INTEGER);
        CREATE TABLE IF NOT EXISTS configured_guilds (guild_id INTEGER PRIMARY KEY, configured_at INTEGER);
        CREATE TABLE IF NOT EXISTS raid_lockdowns (guild_id INTEGER, channel_id INTEGER, prior_send_messages INTEGER, PRIMARY KEY(guild_id, channel_id));
        CREATE TABLE IF NOT EXISTS ganks (gank_id TEXT PRIMARY KEY, message_id INTEGER, guild_id INTEGER, host_id INTEGER, region TEXT, target TEXT, joined TEXT DEFAULT '', stage_id INTEGER, role_id INTEGER, created_at INTEGER);
        CREATE TABLE IF NOT EXISTS pvp_points (guild_id INTEGER, user_id INTEGER, month TEXT, points INTEGER DEFAULT 0, PRIMARY KEY(guild_id, user_id, month));
        CREATE TABLE IF NOT EXISTS host_vouches (guild_id INTEGER, host_id INTEGER, voucher_id INTEGER, month TEXT, PRIMARY KEY(guild_id, host_id, voucher_id, month));
        CREATE TABLE IF NOT EXISTS monthly_awards (guild_id INTEGER, month TEXT, pvp_winner_id INTEGER, host_winner_id INTEGER, PRIMARY KEY(guild_id, month));
        CREATE TABLE IF NOT EXISTS release_announcements (guild_id INTEGER, version TEXT, PRIMARY KEY(guild_id, version));
        """)
        self._add_column("carries", "carry_id", "TEXT")
        self._add_column("carries", "waiting", "TEXT DEFAULT ''")
        self._add_column("carries", "stage_id", "INTEGER")
        self._add_column("carries", "role_id", "INTEGER")
        self._add_column("giveaways", "creator_id", "INTEGER")
        self._add_column("giveaways", "giveaway_id", "TEXT")
        self._add_column("giveaways", "winner_ids", "TEXT DEFAULT ''")
        self._add_column("giveaways", "ended", "INTEGER DEFAULT 0")
        self.db.commit()
    def _add_column(self, table, name, definition):
        columns = {row[1] for row in self.db.execute(f"PRAGMA table_info({table})")}
        if name not in columns: self.db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")
    def blacklisted(self, guild_id, user_id):
        return self.db.execute("SELECT 1 FROM blacklist WHERE guild_id=? AND user_id=?", (guild_id,user_id)).fetchone() is not None
    def ticket_id(self):
        while True:
            value = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
            if not self.db.execute("SELECT 1 FROM tickets WHERE ticket_id=?", (value,)).fetchone():
                return value
    def carry_id(self):
        while True:
            value = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
            if not self.db.execute("SELECT 1 FROM carries WHERE carry_id=?", (value,)).fetchone(): return value
    def giveaway_id(self):
        while True:
            value = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
            if not self.db.execute("SELECT 1 FROM giveaways WHERE giveaway_id=?", (value,)).fetchone(): return value
    def gank_id(self):
        while True:
            value = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
            if not self.db.execute("SELECT 1 FROM ganks WHERE gank_id=?", (value,)).fetchone():
                return value

store = Store()
# Avoid the member cache and other high-volume gateway data. Message content
# is required only for the anti-spam event below.
intents = discord.Intents.default(); intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents, max_messages=500)
# Message timestamps stay in memory and are discarded after ten seconds.
recent_messages: dict[tuple[int, int, int], deque[float]] = defaultdict(deque)


def role(guild, name): return discord.utils.get(guild.roles, name=name)
def channel(guild, name): return discord.utils.get(guild.text_channels, name=name)
async def ensure_role(guild, name, mentionable=False):
    return role(guild, name) or await guild.create_role(name=name, mentionable=mentionable)


def is_primary_guild(guild: discord.Guild | None) -> bool:
    return guild is not None and (PRIMARY_GUILD_ID == 0 or guild.id == PRIMARY_GUILD_ID)


async def activate_raid_lockdown(guild: discord.Guild, detection: str):
    """Temporarily stop @everyone from sending messages, preserving prior settings."""
    if store.db.execute("SELECT 1 FROM raid_lockdowns WHERE guild_id=? LIMIT 1", (guild.id,)).fetchone():
        return False
    changed = 0
    for text_channel in guild.text_channels:
        # Keep a staff-only audit channel available for the alert and response.
        if text_channel.name == "bot-logs":
            continue
        overwrite = text_channel.overwrites_for(guild.default_role)
        previous = overwrite.send_messages
        try:
            overwrite.send_messages = False
            await text_channel.set_permissions(guild.default_role, overwrite=overwrite, reason="Anti-raid lockdown")
            store.db.execute(
                "INSERT OR REPLACE INTO raid_lockdowns(guild_id,channel_id,prior_send_messages) VALUES(?,?,?)",
                (guild.id, text_channel.id, None if previous is None else int(previous)),
            )
            changed += 1
        except discord.Forbidden:
            continue
    store.db.commit()
    logs = channel(guild, "bot-logs")
    if logs:
        embed = discord.Embed(
            title="Anti-raid lockdown activated",
            description=(f"Detected {detection}. "
                         f"Messaging was locked in {changed} channel(s). Use `/unlockdown` after checking the server."),
            colour=discord.Colour.red(),
        )
        try:
            await logs.send(embed=embed)
        except discord.HTTPException:
            pass
    return changed > 0

def parse_duration(value: str) -> int | None:
    """Convert 30s, 30m, 12h, 3d, or 1w into seconds."""
    value = value.strip().lower()
    if len(value) < 2 or not value[:-1].isdigit(): return None
    multiplier = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}.get(value[-1])
    return int(value[:-1]) * multiplier if multiplier else None

async def auto_setup(guild: discord.Guild, reset_channels: bool = False):
    """Make resources. A first setup removes only exact bot-channel names."""
    if reset_channels:
        for existing in list(guild.text_channels):
            if existing.name in BOT_CHANNELS:
                await existing.delete(reason="Deepwoken Bot initial channel rebuild")
    category = discord.utils.get(guild.categories, name="Deepwoken Bot") or await guild.create_category("Deepwoken Bot")
    if not discord.utils.get(guild.categories, name="Carry Stages"):
        await guild.create_category("Carry Stages")
    if not discord.utils.get(guild.categories, name="Gank Stages"):
        await guild.create_category("Gank Stages")
    for name in ["Gank Ping Certified", "Lieutenant", "Review Certified", "Carry Staff", "Giveaway Manager", "Gank Ping", "Giveaway Ping", "Update Ping", "Enmity Hoster", "Elder Hoster", "Titus Hoster", *OLD_BOSS_PINGS]:
        await ensure_role(guild, name, mentionable=name in {"Gank Ping", "Giveaway Ping", "Update Ping", *OLD_BOSS_PINGS})
    for name, colour in [("PvPer of the Month", discord.Colour.dark_red()), ("Hoster of the Month", discord.Colour.gold())]:
        award_role = await ensure_role(guild, name)
        if award_role.colour != colour:
            await award_role.edit(colour=colour, reason="Monthly award role colour")
    for region in REGIONS: await ensure_role(guild, f"Gank Ping • {region}", mentionable=True)
    for name in BOT_CHANNELS:
        if not channel(guild, name): await guild.create_text_channel(name, category=category)
    version = channel(guild, "version")
    if version:
        await version.edit(topic=f"Current bot release: {REGENT_VERSION}")
        has_version_post = False
        async for message in version.history(limit=20):
            if message.author == bot.user and message.embeds and message.embeds[0].title == "Deepwoken Carry Bot" and REGENT_VERSION in (message.embeds[0].description or ""):
                has_version_post = True
                break
        if not has_version_post:
            await version.send(embed=discord.Embed(
                title="Deepwoken Carry Bot",
                description=f"Current version: **{REGENT_VERSION}**",
                colour=discord.Colour.blurple(),
            ))
    if not store.db.execute("SELECT 1 FROM release_announcements WHERE guild_id=? AND version=?", (guild.id, REGENT_VERSION)).fetchone():
        update_log = channel(guild, "update-log")
        update_ping = role(guild, "Update Ping")
        if update_log:
            await update_log.send(
                content=update_ping.mention if update_ping else None,
                embed=discord.Embed(title=f"{REGENT_VERSION} update", description="Gank IDs and stages, Lieutenant-only `/endgank`, PvP points, monthly awards, hoster vouches, and anti-spam protection are live.", colour=discord.Colour.gold()),
                allowed_mentions=discord.AllowedMentions(roles=True),
            )
        store.db.execute("INSERT INTO release_announcements VALUES(?,?)", (guild.id, REGENT_VERSION))
        store.db.commit()
    tickets = channel(guild, "tickets")
    if tickets and not [m async for m in tickets.history(limit=1)]:
        await tickets.send(embed=discord.Embed(title="Support & Applications", description="Choose what you need below.", colour=discord.Colour.blurple()), view=TicketMenu())
    reactions = channel(guild, "reactions")
    if reactions and not [m async for m in reactions.history(limit=1)]:
        await reactions.send(embed=discord.Embed(title="Notification Roles", description="Choose the alerts you want to receive.\n\n**Gank Ping** — all gank alerts\n**Giveaway Ping** — new giveaways\n**Update Ping** — bot/server updates\n**Boss pings** — Elder, Titus, or Enmity carries\n\nUse the region selector to receive gank alerts for specific regions.", colour=discord.Colour.blurple()), view=PingRoleView())

class NotificationRoleButton(discord.ui.Button):
    def __init__(self, role_name):
        super().__init__(label=role_name, style=discord.ButtonStyle.secondary, custom_id=f"notification_role:{role_name.lower().replace(' ', '_')}")
        self.role_name = role_name
    async def callback(self, interaction):
        await interaction.response.defer(ephemeral=True)
        ping_role = role(interaction.guild, self.role_name)
        if not ping_role: return await interaction.followup.send("That role has not been created yet.", ephemeral=True)
        if ping_role in interaction.user.roles:
            await interaction.user.remove_roles(ping_role); message = f"Removed **{self.role_name}**."
        else:
            await interaction.user.add_roles(ping_role); message = f"Added **{self.role_name}**."
        await interaction.followup.send(message, ephemeral=True)

class RegionRoleSelect(discord.ui.Select):
    def __init__(self): super().__init__(placeholder="Toggle your gank-ping regions", custom_id="notification_regions", min_values=1, max_values=len(REGIONS), options=[discord.SelectOption(label=x, value=x) for x in REGIONS])
    async def callback(self, interaction):
        await interaction.response.defer(ephemeral=True)
        changed = []
        for region_name in self.values:
            ping_role = role(interaction.guild, f"Gank Ping • {region_name}")
            if ping_role in interaction.user.roles:
                await interaction.user.remove_roles(ping_role); changed.append(f"removed {region_name}")
            else:
                await interaction.user.add_roles(ping_role); changed.append(f"added {region_name}")
        await interaction.followup.send(", ".join(changed).capitalize() + ".", ephemeral=True)

class PingRoleView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        for name in ["Gank Ping", "Giveaway Ping", "Update Ping", *OLD_BOSS_PINGS]: self.add_item(NotificationRoleButton(name))
        self.add_item(RegionRoleSelect())


def gank_members(value):
    return [int(user_id) for user_id in (value or "").split(",") if user_id]


def gank_embed(row):
    members = gank_members(row["joined"])
    embed = discord.Embed(title=f"{row['region']} Gank • {row['gank_id']}", description=row["target"], colour=discord.Colour.red())
    embed.add_field(name="Host", value=f"<@{row['host_id']}>", inline=True)
    embed.add_field(name="Gank ID", value=f"`{row['gank_id']}`", inline=True)
    embed.add_field(name="Gank Stage", value=f"<#{row['stage_id']}>" if row["stage_id"] else "Unavailable", inline=True)
    embed.add_field(name=f"Participants ({len(members)})", value=" ".join(f"<@{user_id}>" for user_id in members) or "No one has joined yet.", inline=False)
    embed.set_footer(text="Join the gank with the button. Lieutenant can end it with /endgank.")
    return embed


class GankParticipationView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Join Gank", style=discord.ButtonStyle.danger, custom_id="gank_join")
    async def join(self, interaction, button):
        row = store.db.execute("SELECT * FROM ganks WHERE message_id=?", (interaction.message.id,)).fetchone()
        if not row:
            return await interaction.response.send_message("This gank has already ended.", ephemeral=True)
        members = gank_members(row["joined"])
        if interaction.user.id in members:
            return await interaction.response.send_message("You are already in this gank.", ephemeral=True)
        members.append(interaction.user.id)
        store.db.execute("UPDATE ganks SET joined=? WHERE gank_id=?", (",".join(map(str, members)), row["gank_id"]))
        store.db.commit()
        gank_role = interaction.guild.get_role(row["role_id"]) if row["role_id"] else None
        if gank_role:
            await interaction.user.add_roles(gank_role, reason=f"Joined gank {row['gank_id']}")
        row = store.db.execute("SELECT * FROM ganks WHERE gank_id=?", (row["gank_id"],)).fetchone()
        await interaction.response.edit_message(embed=gank_embed(row), view=self)

    @discord.ui.button(label="Leave Gank", style=discord.ButtonStyle.secondary, custom_id="gank_leave")
    async def leave(self, interaction, button):
        row = store.db.execute("SELECT * FROM ganks WHERE message_id=?", (interaction.message.id,)).fetchone()
        if not row:
            return await interaction.response.send_message("This gank has already ended.", ephemeral=True)
        if interaction.user.id == row["host_id"]:
            return await interaction.response.send_message("The host cannot leave; a Lieutenant must end the gank.", ephemeral=True)
        members = gank_members(row["joined"])
        if interaction.user.id not in members:
            return await interaction.response.send_message("You are not in this gank.", ephemeral=True)
        members.remove(interaction.user.id)
        store.db.execute("UPDATE ganks SET joined=? WHERE gank_id=?", (",".join(map(str, members)), row["gank_id"]))
        store.db.commit()
        gank_role = interaction.guild.get_role(row["role_id"]) if row["role_id"] else None
        if gank_role:
            await interaction.user.remove_roles(gank_role, reason=f"Left gank {row['gank_id']}")
        row = store.db.execute("SELECT * FROM ganks WHERE gank_id=?", (row["gank_id"],)).fetchone()
        await interaction.response.edit_message(embed=gank_embed(row), view=self)


class GankModal(discord.ui.Modal, title="Gank alert"):
    target = discord.ui.TextInput(label="Target / server details", style=discord.TextStyle.paragraph, max_length=1000)
    def __init__(self, region): super().__init__(); self.region = region
    async def on_submit(self, interaction):
        if store.blacklisted(interaction.guild.id, interaction.user.id):
            return await interaction.response.send_message("You are blacklisted from this bot.", ephemeral=True)
        if not role(interaction.guild, "Gank Ping Certified") in interaction.user.roles:
            return await interaction.response.send_message("You need the Gank Ping Certified role.", ephemeral=True)
        gank_id = store.gank_id()
        gank_role = await interaction.guild.create_role(name=f"Gank {gank_id}", reason="Gank stage access")
        overwrites = {interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False, connect=False), gank_role: discord.PermissionOverwrite(view_channel=True, connect=True, speak=True)}
        stage_category = discord.utils.get(interaction.guild.categories, name="Gank Stages")
        gank_stage = await interaction.guild.create_voice_channel(f"gank-{gank_id.lower()}", category=stage_category, overwrites=overwrites, reason="Gank stage")
        await interaction.user.add_roles(gank_role, reason=f"Gank host {gank_id}")
        store.db.execute("INSERT INTO ganks(gank_id,message_id,guild_id,host_id,region,target,joined,stage_id,role_id,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)", (gank_id, 0, interaction.guild.id, interaction.user.id, self.region, self.target.value, str(interaction.user.id), gank_stage.id, gank_role.id, int(time.time())))
        store.db.commit()
        row = store.db.execute("SELECT * FROM ganks WHERE gank_id=?", (gank_id,)).fetchone()
        gank_ping = role(interaction.guild, "Gank Ping")
        post = await channel(interaction.guild, "gank-pings").send(content=gank_ping.mention if gank_ping else None, embed=gank_embed(row), view=GankParticipationView(), allowed_mentions=discord.AllowedMentions(roles=True))
        store.db.execute("UPDATE ganks SET message_id=? WHERE gank_id=?", (post.id, gank_id))
        store.db.commit()
        return await interaction.response.send_message(f"Gank `{gank_id}` started.", ephemeral=True)
        region_ping = role(interaction.guild, f"Gank Ping • {self.region}")
        gank_ping = role(interaction.guild, "Gank Ping")
        mentions = " ".join(ping.mention for ping in [gank_ping, region_ping] if ping)
        await channel(interaction.guild, "gank-pings").send(f"{mentions}\n**{self.region} Gank Alert** — {interaction.user.mention}\n{self.target.value}", allowed_mentions=discord.AllowedMentions(roles=True))
        await interaction.response.send_message("Gank ping sent.", ephemeral=True)

class GankRegion(discord.ui.Select):
    def __init__(self): super().__init__(placeholder="Select gank region", custom_id="gank_region", options=[discord.SelectOption(label=x) for x in REGIONS])
    async def callback(self, interaction): await interaction.response.send_modal(GankModal(self.values[0]))
class GankView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None); self.add_item(GankRegion())

class PvEModal(discord.ui.Modal, title="PvE Application"):
    bosses = discord.ui.TextInput(label="Bosses you can do", style=discord.TextStyle.paragraph)
    clips = discord.ui.TextInput(label="Clips (links)", style=discord.TextStyle.paragraph)
    region = discord.ui.TextInput(label="Region", placeholder="NA / EU / SA / Asia / Oceania")
    async def on_submit(self, interaction): await create_ticket(interaction, "pve", {"Bosses":self.bosses.value,"Clips":self.clips.value,"Region":self.region.value})
class TryoutModal(discord.ui.Modal, title="Tryout Application"):
    region = discord.ui.TextInput(label="Region")
    peak = discord.ui.TextInput(label="Peak ELO")
    reset = discord.ui.TextInput(label="Last Chime reset ELO")
    activity = discord.ui.TextInput(label="Activity (/5)")
    playstyle = discord.ui.TextInput(label="Playstyle", placeholder="e.g. support or depths ganker")
    async def on_submit(self, interaction): await create_ticket(interaction, "tryout", {"Region":self.region.value,"Peak ELO":self.peak.value,"Reset ELO":self.reset.value,"Activity":self.activity.value,"Playstyle":self.playstyle.value})
class HelpModal(discord.ui.Modal, title="General Help"):
    question = discord.ui.TextInput(label="Your question", style=discord.TextStyle.paragraph)
    async def on_submit(self, interaction): await create_ticket(interaction, "help", {"Question":self.question.value})

class TicketSelect(discord.ui.Select):
    def __init__(self): super().__init__(placeholder="Open a ticket", custom_id="ticket_select", options=[discord.SelectOption(label=v, value=k) for k,v in TICKET_TYPES.items()])
    async def callback(self, interaction):
        if store.blacklisted(interaction.guild.id, interaction.user.id): return await interaction.response.send_message("You are blacklisted from this bot.", ephemeral=True)
        await interaction.response.send_modal({"pve":PvEModal(), "tryout":TryoutModal(), "help":HelpModal()}[self.values[0]])
class TicketMenu(discord.ui.View):
    def __init__(self): super().__init__(timeout=None); self.add_item(TicketSelect())

class ReviewView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    async def decide(self, interaction, approved):
        if role(interaction.guild, "Review Certified") not in interaction.user.roles: return await interaction.response.send_message("Review Certified is required.", ephemeral=True)
        status = "PASSED" if approved else "DENIED"; embed = interaction.message.embeds[0]; embed.colour = discord.Colour.green() if approved else discord.Colour.red(); embed.set_footer(text=f"{status} by {interaction.user}")
        await interaction.message.edit(embed=embed, view=None); await interaction.response.send_message(f"Application {status.lower()}.", ephemeral=True)
    @discord.ui.button(label="Pass", style=discord.ButtonStyle.success, custom_id="review_pass")
    async def passed(self, interaction, button): await self.decide(interaction, True)
    @discord.ui.button(label="Deny", style=discord.ButtonStyle.danger, custom_id="review_deny")
    async def denied(self, interaction, button): await self.decide(interaction, False)

async def create_ticket(interaction, kind, fields):
    guild = interaction.guild; overwrites = {guild.default_role: discord.PermissionOverwrite(view_channel=False), interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True)}
    for n in ["Carry Staff", "Review Certified"]:
        if r := role(guild,n): overwrites[r] = discord.PermissionOverwrite(view_channel=True, send_messages=True)
    ticket_id = store.ticket_id()
    ticket = await guild.create_text_channel(f"{kind}-{ticket_id}".lower(), category=discord.utils.get(guild.categories,name="Deepwoken Bot"), overwrites=overwrites)
    store.db.execute("INSERT INTO tickets VALUES(?,?,?,?,?,?)", (ticket_id, guild.id, ticket.id, interaction.user.id, kind, int(time.time())))
    store.db.commit()
    embed = discord.Embed(title=f"{TICKET_TYPES[kind]} • {ticket_id}", description=f"Opened by {interaction.user.mention}\nTicket ID: `{ticket_id}`", colour=discord.Colour.blurple())
    for key, value in fields.items(): embed.add_field(name=key, value=value, inline=False)
    await ticket.send(embed=embed)
    if kind == "pve": await channel(guild,"application-reviews").send(embed=embed, view=ReviewView())
    await interaction.response.send_message(f"Ticket created: {ticket.mention}", ephemeral=True)

@bot.tree.command(description="Post a region-targeted gank alert.")
async def gank(interaction: discord.Interaction): await interaction.response.send_message("Choose a region.", view=GankView(), ephemeral=True)


def month_key(moment: datetime | None = None) -> str:
    moment = moment or datetime.now(timezone.utc)
    return f"{moment.year:04d}-{moment.month:02d}"


@bot.tree.command(description="End a gank by its six-character gank ID and award its participants one PvP point.")
@app_commands.describe(gank_id="Six-character gank ID, for example A7K2QP")
async def endgank(interaction: discord.Interaction, gank_id: str):
    lieutenant = role(interaction.guild, "Lieutenant")
    if not lieutenant or lieutenant not in interaction.user.roles:
        return await interaction.response.send_message("Only members with the Lieutenant role can end a gank.", ephemeral=True)
    row = store.db.execute("SELECT * FROM ganks WHERE gank_id=? AND guild_id=?", (gank_id.upper(), interaction.guild.id)).fetchone()
    if not row:
        return await interaction.response.send_message("Gank not found. Check the six-character gank ID.", ephemeral=True)
    participants = gank_members(row["joined"])
    period = month_key()
    for user_id in participants:
        store.db.execute("INSERT INTO pvp_points(guild_id,user_id,month,points) VALUES(?,?,?,1) ON CONFLICT(guild_id,user_id,month) DO UPDATE SET points=points+1", (interaction.guild.id, user_id, period))
    store.db.execute("DELETE FROM ganks WHERE gank_id=?", (row["gank_id"],))
    store.db.commit()
    gank_role = interaction.guild.get_role(row["role_id"]) if row["role_id"] else None
    for user_id in participants:
        member = interaction.guild.get_member(user_id)
        if member and gank_role:
            try: await member.remove_roles(gank_role, reason=f"Gank {row['gank_id']} ended")
            except discord.HTTPException: pass
    stage = interaction.guild.get_channel(row["stage_id"]) if row["stage_id"] else None
    if stage:
        try: await stage.delete(reason=f"Gank {row['gank_id']} ended")
        except discord.HTTPException: pass
    if gank_role:
        try: await gank_role.delete(reason=f"Gank {row['gank_id']} ended")
        except discord.HTTPException: pass
    post = channel(interaction.guild, "gank-pings")
    if post and row["message_id"]:
        try: await post.get_partial_message(row["message_id"]).delete()
        except discord.HTTPException: pass
    await interaction.response.send_message(f"Gank `{row['gank_id']}` ended. {len(participants)} participant(s) received 1 PvP point.", ephemeral=True)


@bot.tree.command(description="Vouch for a hoster once per month.")
@app_commands.describe(hoster="The hoster you want to vouch for")
async def vouch(interaction: discord.Interaction, hoster: discord.Member):
    if hoster.bot or hoster.id == interaction.user.id:
        return await interaction.response.send_message("You cannot vouch for that member.", ephemeral=True)
    if not any(role(interaction.guild, name) in hoster.roles for name in ["Enmity Hoster", "Elder Hoster", "Titus Hoster"]):
        return await interaction.response.send_message("That member is not a configured hoster.", ephemeral=True)
    try:
        store.db.execute("INSERT INTO host_vouches VALUES(?,?,?,?)", (interaction.guild.id, hoster.id, interaction.user.id, month_key()))
        store.db.commit()
    except sqlite3.IntegrityError:
        return await interaction.response.send_message("You have already vouched for that hoster this month.", ephemeral=True)
    total = store.db.execute("SELECT COUNT(*) FROM host_vouches WHERE guild_id=? AND host_id=? AND month=?", (interaction.guild.id, hoster.id, month_key())).fetchone()[0]
    await interaction.response.send_message(f"Vouch recorded for {hoster.mention}. They now have {total} vouch(es) this month.", ephemeral=True)

def ids(value): return [int(item) for item in value.split(",") if item]
def carry_embed(row):
    players = ids(row["joined"]); waiting = ids(row["waiting"] or "")
    player_text = "\n".join(f"{i + 1}. <@{user_id}>" for i, user_id in enumerate(players)) or "None"
    wait_text = "\n".join(f"{i + 1}. <@{user_id}>" for i, user_id in enumerate(waiting)) or "Empty"
    embed = discord.Embed(title=f"{row['boss']} Carry • {row['carry_id']}", description="Press **Join** to enter. If all slots are full, you are added to the waiting list and receive a DM.", colour=discord.Colour.gold())
    embed.add_field(name="Host", value=f"<@{row['host_id']}>", inline=True)
    embed.add_field(name="Region", value=row["region"], inline=True)
    embed.add_field(name="Slots", value=f"{len(players)}/{row['max_players']} (host included)", inline=True)
    embed.add_field(name="Carry ID", value=f"`{row['carry_id']}`", inline=True)
    embed.add_field(name="Private Stage", value=f"<#{row['stage_id']}>" if row["stage_id"] else "Creating…", inline=True)
    embed.add_field(name="Stage Access", value="Only carry members can see/join. Only the host can speak.", inline=True)
    embed.add_field(name=f"Players ({len(players)}/{row['max_players']})", value=player_text, inline=False)
    embed.add_field(name=f"Waiting List ({len(waiting)})", value=wait_text, inline=False)
    embed.set_footer(text=f"Carry ID: {row['carry_id']} • Join puts you in the waiting list if full")
    return embed

async def create_stage(guild, row, host):
    category = discord.utils.get(guild.categories, name="Carry Stages") or await guild.create_category("Carry Stages")
    carry_role = await guild.create_role(name=f"Carry {row['carry_id']}", reason="Carry access role")
    overwrites = {guild.default_role: discord.PermissionOverwrite(view_channel=False, connect=False), carry_role: discord.PermissionOverwrite(view_channel=True, connect=True, speak=False, request_to_speak=False), host: discord.PermissionOverwrite(view_channel=True, connect=True, speak=True, mute_members=True, move_members=True)}
    stage = await guild.create_stage_channel(name=f"{row['boss']}-{row['carry_id']}", category=category, overwrites=overwrites, user_limit=row["max_players"], reason="CarryBot carry stage")
    try: await stage.create_instance(topic=f"{row['boss']} Carry • {row['carry_id']}")
    except discord.HTTPException: pass
    await host.add_roles(carry_role, reason="Carry host")
    store.db.execute("UPDATE carries SET stage_id=?, role_id=? WHERE message_id=?", (stage.id, carry_role.id, row["message_id"])); store.db.commit()
    return stage, carry_role

async def update_carry_message(guild, row):
    post = channel(guild, "carry-pings")
    if not post: return
    try: await post.get_partial_message(row["message_id"]).edit(embed=carry_embed(row), view=CarryView())
    except discord.HTTPException: pass

async def create_carry(interaction: discord.Interaction, boss: app_commands.Choice[str], region: app_commands.Choice[str], players: int):
    await interaction.response.defer(ephemeral=True)
    boss_name = boss.value
    if store.blacklisted(interaction.guild.id, interaction.user.id): return await interaction.followup.send("You are blacklisted.", ephemeral=True)
    if players > CARRY_BOSSES[boss_name]: return await interaction.followup.send(f"{boss_name} allows at most {CARRY_BOSSES[boss_name]} players, including you.", ephemeral=True)
    if store.db.execute("SELECT 1 FROM carries WHERE guild_id=? AND host_id=?", (interaction.guild.id, interaction.user.id)).fetchone(): return await interaction.followup.send("You already have an active carry. Use /endcarry first.", ephemeral=True)
    host_role = role(interaction.guild, f"{boss_name} Hoster")
    if host_role not in interaction.user.roles: return await interaction.followup.send(f"You need the **{boss_name} Hoster** role.", ephemeral=True)
    carry_id = store.carry_id()
    cursor = store.db.execute("INSERT INTO carries (guild_id,host_id,boss,region,max_players,joined,waiting,created_at,carry_id) VALUES(?,?,?,?,?,?,?,?,?)", (interaction.guild.id, interaction.user.id, boss_name, region.value, players, str(interaction.user.id), "", int(time.time()), carry_id)); store.db.commit()
    temp = store.db.execute("SELECT * FROM carries WHERE rowid=?", (cursor.lastrowid,)).fetchone()
    stage, _ = await create_stage(interaction.guild, temp, interaction.user)
    row = store.db.execute("SELECT * FROM carries WHERE carry_id=?", (carry_id,)).fetchone()
    boss_ping = role(interaction.guild, f"{boss_name} Ping")
    msg = await channel(interaction.guild,"carry-pings").send(content=boss_ping.mention if boss_ping else None, embed=carry_embed(row), view=CarryView(), allowed_mentions=discord.AllowedMentions(roles=True))
    store.db.execute("UPDATE carries SET message_id=? WHERE carry_id=?", (msg.id, carry_id)); store.db.commit()
    await interaction.followup.send(f"Carry `{carry_id}` created. Your private stage is {stage.mention}.", ephemeral=True)

@bot.tree.command(name="startcarry", description="Start a carry.")
@app_commands.describe(boss="Boss", region="Carry region", players="Total player limit, including host")
@app_commands.choices(boss=[app_commands.Choice(name=x, value=x) for x in CARRY_BOSSES], region=[app_commands.Choice(name=x, value=x) for x in REGIONS])
async def startcarry(interaction: discord.Interaction, boss: app_commands.Choice[str], region: app_commands.Choice[str], players: app_commands.Range[int,2,16]):
    await create_carry(interaction, boss, region, players)

class CarryView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Join", style=discord.ButtonStyle.primary, custom_id="carry_join")
    async def join(self, interaction, button):
        if store.blacklisted(interaction.guild.id, interaction.user.id):
            return await interaction.response.send_message("You are blacklisted from this bot.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        row=store.db.execute("SELECT * FROM carries WHERE message_id=?",(interaction.message.id,)).fetchone()
        if not row: return await interaction.followup.send("This carry has ended.", ephemeral=True)
        joined=ids(row["joined"]); waiting=ids(row["waiting"] or "")
        if interaction.user.id in joined or interaction.user.id in waiting: return await interaction.followup.send("You are already in this carry or its waiting list.", ephemeral=True)
        if len(joined) >= row["max_players"]:
            waiting.append(interaction.user.id); store.db.execute("UPDATE carries SET waiting=? WHERE message_id=?",(",".join(map(str,waiting)),row["message_id"])); store.db.commit()
            try: await interaction.user.send(f"You are now #{len(waiting)} in the waiting list for **{row['boss']}** carry `{row['carry_id']}`.")
            except discord.HTTPException: pass
            updated=store.db.execute("SELECT * FROM carries WHERE message_id=?",(row["message_id"],)).fetchone(); await update_carry_message(interaction.guild,updated)
            return await interaction.followup.send("Carry is full; you were added to the waiting list and sent a DM.",ephemeral=True)
        joined.append(interaction.user.id); store.db.execute("UPDATE carries SET joined=? WHERE message_id=?",(",".join(map(str,joined)),row["message_id"])); store.db.commit()
        carry_role=interaction.guild.get_role(row["role_id"])
        if carry_role: await interaction.user.add_roles(carry_role, reason="Joined carry")
        updated=store.db.execute("SELECT * FROM carries WHERE message_id=?",(row["message_id"],)).fetchone(); await update_carry_message(interaction.guild,updated)
        await interaction.followup.send("You joined the carry. You can now see and join its private stage.",ephemeral=True)
    @discord.ui.button(label="Leave", style=discord.ButtonStyle.danger, custom_id="carry_leave")
    async def leave(self, interaction, button):
        await interaction.response.defer(ephemeral=True)
        row=store.db.execute("SELECT * FROM carries WHERE message_id=?",(interaction.message.id,)).fetchone()
        if not row: return await interaction.followup.send("This carry has ended.", ephemeral=True)
        if interaction.user.id == row["host_id"]: return await interaction.followup.send("Hosts must use /endcarry.", ephemeral=True)
        joined=ids(row["joined"]); waiting=ids(row["waiting"] or "")
        if interaction.user.id in waiting:
            waiting.remove(interaction.user.id)
        elif interaction.user.id in joined:
            joined.remove(interaction.user.id)
            carry_role=interaction.guild.get_role(row["role_id"])
            if carry_role: await interaction.user.remove_roles(carry_role, reason="Left carry")
            if waiting:
                promoted=waiting.pop(0); joined.append(promoted)
                member=interaction.guild.get_member(promoted); carry_role=interaction.guild.get_role(row["role_id"])
                if member and carry_role:
                    await member.add_roles(carry_role, reason="Promoted from carry waiting list")
                    try: await member.send(f"A space opened: you are now in **{row['boss']}** carry `{row['carry_id']}`.")
                    except discord.HTTPException: pass
        else: return await interaction.followup.send("You are not in this carry.", ephemeral=True)
        store.db.execute("UPDATE carries SET joined=?, waiting=? WHERE message_id=?",(",".join(map(str,joined)),",".join(map(str,waiting)),row["message_id"])); store.db.commit()
        updated=store.db.execute("SELECT * FROM carries WHERE message_id=?",(row["message_id"],)).fetchone(); await update_carry_message(interaction.guild,updated)
        await interaction.followup.send("You left the carry.", ephemeral=True)

@bot.tree.command(description="Blacklist a user from bot systems.")
@app_commands.checks.has_permissions(manage_guild=True)
async def blacklist(interaction: discord.Interaction, member: discord.Member, reason: str):
    store.db.execute("INSERT OR REPLACE INTO blacklist VALUES(?,?,?,?)",(interaction.guild.id,member.id,reason,interaction.user.id)); store.db.commit(); await interaction.response.send_message(f"Blacklisted {member.mention}.", ephemeral=True)
@bot.tree.command(description="Remove a user from the bot blacklist.")
@app_commands.checks.has_permissions(manage_guild=True)
async def unblacklist(interaction: discord.Interaction, member: discord.Member):
    store.db.execute("DELETE FROM blacklist WHERE guild_id=? AND user_id=?",(interaction.guild.id,member.id)); store.db.commit(); await interaction.response.send_message("Blacklist entry removed.",ephemeral=True)


@bot.tree.command(description="Restore channels locked by the anti-raid system.")
@app_commands.checks.has_permissions(manage_guild=True)
async def unlockdown(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    rows = store.db.execute("SELECT * FROM raid_lockdowns WHERE guild_id=?", (interaction.guild.id,)).fetchall()
    if not rows:
        return await interaction.followup.send("There is no anti-raid lockdown to remove.", ephemeral=True)
    restored = 0
    for row in rows:
        text_channel = interaction.guild.get_channel(row["channel_id"])
        if not isinstance(text_channel, discord.TextChannel):
            store.db.execute("DELETE FROM raid_lockdowns WHERE guild_id=? AND channel_id=?", (interaction.guild.id, row["channel_id"]))
            continue
        overwrite = text_channel.overwrites_for(interaction.guild.default_role)
        overwrite.send_messages = None if row["prior_send_messages"] is None else bool(row["prior_send_messages"])
        try:
            await text_channel.set_permissions(interaction.guild.default_role, overwrite=overwrite, reason=f"Anti-raid lockdown removed by {interaction.user}")
        except discord.Forbidden:
            continue
        store.db.execute("DELETE FROM raid_lockdowns WHERE guild_id=? AND channel_id=?", (interaction.guild.id, text_channel.id))
        restored += 1
    store.db.commit()
    logs = channel(interaction.guild, "bot-logs")
    if logs:
        await logs.send(embed=discord.Embed(title="Anti-raid lockdown removed", description=f"Removed by {interaction.user.mention}; restored {restored} channel(s).", colour=discord.Colour.green()))
    await interaction.followup.send(f"Anti-raid lockdown removed from {restored} channel(s).", ephemeral=True)

@bot.tree.command(description="Start a giveaway (duration: 30s, 30m, 12h, 3d, or 1w).")
@app_commands.checks.has_permissions(manage_guild=True)
async def giveaway(interaction: discord.Interaction, prize: str, duration: str, winners: app_commands.Range[int,1,20]=1):
    await interaction.response.defer(ephemeral=True)
    seconds = parse_duration(duration)
    if not seconds or seconds > 31536000:
        return await interaction.followup.send("Use a duration such as `30s`, `30m`, `12h`, `3d`, or `1w` (up to one year).", ephemeral=True)
    ends=int(time.time())+seconds
    giveaway_id = store.giveaway_id()
    e=discord.Embed(title=f"🎉 GIVEAWAY • {giveaway_id}",description=f"Prize: **{prize}**\nGiveaway ID: `{giveaway_id}`\nEnds: <t:{ends}:F> (**<t:{ends}:R>**)\nWinners: {winners}",colour=discord.Colour.magenta())
    giveaway_ping = role(interaction.guild, "Giveaway Ping")
    msg=await channel(interaction.guild,"giveaways").send(content=giveaway_ping.mention if giveaway_ping else None, embed=e,view=GiveawayView(), allowed_mentions=discord.AllowedMentions(roles=True))
    store.db.execute("INSERT INTO giveaways (message_id,guild_id,channel_id,prize,ends_at,winners,entrants,creator_id,giveaway_id,winner_ids,ended) VALUES(?,?,?,?,?,?,?,?,?,?,0)",(msg.id,interaction.guild.id,msg.channel.id,prize,ends,winners,"",interaction.user.id,giveaway_id,""));store.db.commit();await interaction.followup.send(f"Giveaway `{giveaway_id}` started.",ephemeral=True)
class GiveawayView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Enter",emoji="🎉",style=discord.ButtonStyle.success,custom_id="giveaway_enter")
    async def enter(self,interaction,button):
        if store.blacklisted(interaction.guild.id, interaction.user.id):
            return await interaction.response.send_message("You are blacklisted from this bot.", ephemeral=True)
        r=store.db.execute("SELECT entrants FROM giveaways WHERE message_id=?",(interaction.message.id,)).fetchone(); users=set(filter(None,r[0].split(","))); users.add(str(interaction.user.id));store.db.execute("UPDATE giveaways SET entrants=? WHERE message_id=?",(",".join(users),interaction.message.id));store.db.commit();await interaction.response.send_message("You entered!",ephemeral=True)

class GiveawayClaimView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Claim Prize", style=discord.ButtonStyle.success, custom_id="giveaway_claim")
    async def claim(self, interaction, button):
        row = store.db.execute("SELECT * FROM giveaways WHERE message_id=?", (interaction.message.id,)).fetchone()
        if not row or interaction.user.id not in ids(row["winner_ids"] or ""):
            return await interaction.response.send_message("Only a selected winner can claim this giveaway.", ephemeral=True)
        if row["ended"] == 2: return await interaction.response.send_message("This giveaway has already been claimed.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        ticket_id = store.ticket_id(); guild = interaction.guild; creator = guild.get_member(row["creator_id"])
        overwrites = {guild.default_role: discord.PermissionOverwrite(view_channel=False), interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True)}
        if creator: overwrites[creator] = discord.PermissionOverwrite(view_channel=True, send_messages=True)
        ticket = await guild.create_text_channel(f"giveaway-{ticket_id}".lower(), category=discord.utils.get(guild.categories,name="Deepwoken Bot"), overwrites=overwrites)
        store.db.execute("INSERT INTO tickets VALUES(?,?,?,?,?,?)", (ticket_id,guild.id,ticket.id,interaction.user.id,"giveaway",int(time.time())))
        store.db.execute("UPDATE giveaways SET ended=2 WHERE message_id=?", (row["message_id"],)); store.db.commit()
        await ticket.send(f"{interaction.user.mention} {creator.mention if creator else ''}", embed=discord.Embed(title=f"Giveaway Claim • {ticket_id}", description=f"Prize: **{row['prize']}**\nWinner: {interaction.user.mention}\nCreator: {creator.mention if creator else 'Unavailable'}", colour=discord.Colour.green()))
        await interaction.followup.send(f"Claim ticket created: {ticket.mention}", ephemeral=True)

async def announce_winners(guild, row, winner_ids):
    giveaway_channel = guild.get_channel(row["channel_id"])
    if not giveaway_channel: return
    mentions = ", ".join(f"<@{winner}>" for winner in winner_ids) if winner_ids else "no valid entries"
    await giveaway_channel.send(f"Giveaway ended: **{row['prize']}** — {mentions}")
    try:
        original = await giveaway_channel.fetch_message(row["message_id"])
        embed = original.embeds[0]; embed.colour = discord.Colour.green() if winner_ids else discord.Colour.red(); embed.add_field(name="Winners", value=mentions, inline=False)
        await original.edit(embed=embed, view=GiveawayClaimView() if winner_ids else None)
    except discord.HTTPException: pass
    for winner in winner_ids:
        member = guild.get_member(winner)
        if member:
            try: await member.send(f"You won **{row['prize']}** in **{guild.name}**! Go to the giveaway post and press **Claim Prize**.")
            except discord.HTTPException: pass

@bot.tree.command(description="Reroll an ended giveaway using its six-character giveaway ID.")
@app_commands.checks.has_permissions(manage_guild=True)
async def reroll(interaction: discord.Interaction, giveaway_id: str):
    await interaction.response.defer(ephemeral=True)
    row = store.db.execute("SELECT * FROM giveaways WHERE giveaway_id=? AND guild_id=? AND ended>=1", (giveaway_id.upper(),interaction.guild.id)).fetchone()
    if not row: return await interaction.followup.send("No ended giveaway with that ID was found.", ephemeral=True)
    entrants = ids(row["entrants"]); prior = set(ids(row["winner_ids"] or "")); candidates = [entry for entry in entrants if entry not in prior] or entrants
    picks = select_giveaway_winners(interaction.guild, candidates, row["winners"]) if candidates else []
    store.db.execute("UPDATE giveaways SET winner_ids=?, ended=1 WHERE message_id=?",(",".join(map(str,picks)),row["message_id"])); store.db.commit()
    await announce_winners(interaction.guild, row, picks)
    await interaction.followup.send("Giveaway rerolled.", ephemeral=True)


@bot.tree.command(description="End your current carry and remove its post.")
async def endcarry(interaction: discord.Interaction):
    row = store.db.execute("SELECT * FROM carries WHERE guild_id=? AND host_id=?", (interaction.guild.id, interaction.user.id)).fetchone()
    if not row:
        return await interaction.response.send_message("You do not have an active carry.", ephemeral=True)
    post_channel = channel(interaction.guild, "carry-pings")
    if post_channel:
        try:
            await post_channel.get_partial_message(row["message_id"]).delete()
        except discord.HTTPException:
            pass
    if row["stage_id"]:
        stage = interaction.guild.get_channel(row["stage_id"])
        if stage:
            try: await stage.delete(reason="Carry ended")
            except discord.HTTPException: pass
    if row["role_id"]:
        carry_role = interaction.guild.get_role(row["role_id"])
        if carry_role:
            try: await carry_role.delete(reason="Carry ended")
            except discord.HTTPException: pass
    store.db.execute("DELETE FROM carries WHERE message_id=?", (row["message_id"],)); store.db.commit()
    logs = channel(interaction.guild, "bot-logs")
    if logs:
        await logs.send(embed=discord.Embed(title="Carry ended", description=f"**{row['boss']}** ({row['region']}) ended by {interaction.user.mention}.", colour=discord.Colour.red()))
    await interaction.response.send_message("Your carry has been ended.", ephemeral=True)


class IncidentModal(discord.ui.Modal, title="Incident Report"):
    reason = discord.ui.TextInput(label="Reason", max_length=200)
    clip = discord.ui.TextInput(label="Clip link", placeholder="https://...", required=True)
    context = discord.ui.TextInput(label="Context (optional)", style=discord.TextStyle.paragraph, required=False, max_length=1000)
    async def on_submit(self, interaction):
        ticket_id = store.ticket_id()
        staff = role(interaction.guild, "Carry Staff")
        category = discord.utils.get(interaction.guild.categories, name="Incident Tickets") or await interaction.guild.create_category("Incident Tickets")
        overwrites = {interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False), interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)}
        if staff: overwrites[staff] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
        ticket = await interaction.guild.create_text_channel(f"incident-{ticket_id}".lower(), category=category, overwrites=overwrites)
        store.db.execute("INSERT INTO tickets VALUES(?,?,?,?,?,?)", (ticket_id, interaction.guild.id, ticket.id, interaction.user.id, "incident", int(time.time())))
        store.db.commit()
        report = discord.Embed(title="🚨 Incident Report", colour=discord.Colour.red())
        report.add_field(name="Reporter", value=interaction.user.mention, inline=False)
        report.add_field(name="Reason", value=self.reason.value, inline=False)
        report.add_field(name="Clip", value=self.clip.value, inline=False)
        report.add_field(name="Context", value=self.context.value or "None", inline=False)
        report.set_footer(text=f"Incident ID: {ticket_id} • Reporter ID: {interaction.user.id}")
        await ticket.send(embed=report)
        await interaction.response.send_message(f"Incident ticket created: {ticket.mention}", ephemeral=True)


class IncidentReviewView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Take", style=discord.ButtonStyle.success, custom_id="incident_take")
    async def take(self, interaction, button):
        staff = role(interaction.guild, "Carry Staff")
        if staff not in interaction.user.roles and not interaction.user.guild_permissions.manage_guild:
            return await interaction.response.send_message("Carry Staff is required.", ephemeral=True)
        category = discord.utils.get(interaction.guild.categories, name="Incident Tickets") or await interaction.guild.create_category("Incident Tickets")
        overwrites = {interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False), interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)}
        ticket = await interaction.guild.create_text_channel(f"incident-{interaction.message.id}", category=category, overwrites=overwrites)
        await ticket.send(f"Taken by {interaction.user.mention}", embed=interaction.message.embeds[0])
        for child in self.children: child.disabled = True
        await interaction.response.edit_message(view=self)


class CloseIncidentModal(discord.ui.Modal, title="Close Incident"):
    punishment = discord.ui.TextInput(label="Punishment", placeholder="Warn / Kick / Ban / Blacklist / None")
    notes = discord.ui.TextInput(label="Notes (optional)", style=discord.TextStyle.paragraph, required=False, max_length=1000)
    async def on_submit(self, interaction):
        log = discord.Embed(title="Incident Closed", colour=discord.Colour.green(), description=f"Closed by {interaction.user.mention}")
        log.add_field(name="Ticket", value=interaction.channel.name, inline=False)
        log.add_field(name="Punishment", value=self.punishment.value, inline=False)
        log.add_field(name="Notes", value=self.notes.value or "None", inline=False)
        await channel(interaction.guild, "bot-logs").send(embed=log)
        await interaction.response.send_message("Closing incident ticket…", ephemeral=True)
        await interaction.channel.delete(reason=f"Incident closed by {interaction.user}")


@bot.tree.command(description="Submit an incident report.")
async def incident(interaction: discord.Interaction):
    await interaction.response.send_modal(IncidentModal())


@bot.tree.command(description="Close the current incident ticket.")
async def closeincident(interaction: discord.Interaction):
    staff = role(interaction.guild, "Carry Staff")
    if not interaction.channel.name.startswith("incident-"):
        return await interaction.response.send_message("Use this in an incident ticket.", ephemeral=True)
    if staff not in interaction.user.roles and not interaction.user.guild_permissions.manage_guild:
        return await interaction.response.send_message("Carry Staff is required.", ephemeral=True)
    await interaction.response.send_modal(CloseIncidentModal())


@bot.tree.command(name="close", description="Close a ticket by its six-character ID, or use inside the ticket.")
@app_commands.describe(ticket_id="Optional ticket ID, for example A7K2QP")
async def close(interaction: discord.Interaction, ticket_id: str | None = None):
    await interaction.response.defer(ephemeral=True)
    if ticket_id:
        ticket = store.db.execute("SELECT * FROM tickets WHERE ticket_id=? AND guild_id=?", (ticket_id.upper(), interaction.guild.id)).fetchone()
    else:
        ticket = store.db.execute("SELECT * FROM tickets WHERE channel_id=? AND guild_id=?", (interaction.channel_id, interaction.guild.id)).fetchone()
    if not ticket:
        return await interaction.followup.send("Ticket not found. Use its six-character ID, or run `/close` inside the ticket.", ephemeral=True)
    staff = role(interaction.guild, "Carry Staff")
    is_staff = interaction.user.guild_permissions.manage_guild or (staff and staff in interaction.user.roles)
    if interaction.user.id != ticket["opener_id"] and not is_staff:
        return await interaction.followup.send("Only the ticket opener or Carry Staff can close this ticket.", ephemeral=True)
    ticket_channel = interaction.guild.get_channel(ticket["channel_id"])
    store.db.execute("DELETE FROM tickets WHERE ticket_id=?", (ticket["ticket_id"],)); store.db.commit()
    logs = channel(interaction.guild, "bot-logs")
    if logs:
        await logs.send(embed=discord.Embed(title="Ticket Closed", description=f"Ticket `{ticket['ticket_id']}` ({ticket['kind']}) closed by {interaction.user.mention}.", colour=discord.Colour.red()))
    await interaction.followup.send(f"Closing ticket `{ticket['ticket_id']}`…", ephemeral=True)
    if ticket_channel:
        await ticket_channel.delete(reason=f"Ticket {ticket['ticket_id']} closed by {interaction.user}")

def select_giveaway_winners(guild: discord.Guild, entrants: list[int], count: int) -> list[int]:
    """PvPer of the Month has three chances in every drawing, but can win only once."""
    pvp_role = role(guild, "PvPer of the Month")
    pool, winners = list(dict.fromkeys(entrants)), []
    while pool and len(winners) < count:
        weights = [3 if pvp_role and (member := guild.get_member(user_id)) and pvp_role in member.roles else 1 for user_id in pool]
        winner = random.choices(pool, weights=weights, k=1)[0]
        pool.remove(winner)
        winners.append(winner)
    return winners


async def award_previous_month(guild: discord.Guild):
    now = datetime.now(timezone.utc)
    previous = now.month - 1 or 12
    year = now.year if now.month > 1 else now.year - 1
    period = f"{year:04d}-{previous:02d}"
    if store.db.execute("SELECT 1 FROM monthly_awards WHERE guild_id=? AND month=?", (guild.id, period)).fetchone():
        return
    pvp = store.db.execute("SELECT user_id FROM pvp_points WHERE guild_id=? AND month=? ORDER BY points DESC, user_id ASC LIMIT 1", (guild.id, period)).fetchone()
    host = store.db.execute("SELECT host_id, COUNT(*) AS total FROM host_vouches WHERE guild_id=? AND month=? GROUP BY host_id ORDER BY total DESC, host_id ASC LIMIT 1", (guild.id, period)).fetchone()
    pvp_role, host_role = role(guild, "PvPer of the Month"), role(guild, "Hoster of the Month")
    for award_role, winner_id in [(pvp_role, pvp["user_id"] if pvp else None), (host_role, host["host_id"] if host else None)]:
        if award_role:
            for member in award_role.members:
                await member.remove_roles(award_role, reason="Monthly award rotation")
            winner = None
            if winner_id:
                try:
                    winner = await guild.fetch_member(winner_id)
                except discord.HTTPException:
                    pass
            if winner:
                await winner.add_roles(award_role, reason=f"{period} monthly award")
    store.db.execute("INSERT INTO monthly_awards VALUES(?,?,?,?)", (guild.id, period, pvp["user_id"] if pvp else None, host["host_id"] if host else None))
    store.db.commit()
    updates = channel(guild, "update-log")
    if updates and (pvp or host):
        pvp_text = f"<@{pvp['user_id']}>" if pvp else "No winner"
        host_text = f"<@{host['host_id']}>" if host else "No winner"
        await updates.send(embed=discord.Embed(title=f"{period} monthly awards", description=f"PvPer of the Month: {pvp_text}\nHoster of the Month: {host_text}", colour=discord.Colour.gold()))


@tasks.loop(seconds=10)
async def cleanup():
    now=int(time.time())
    for row in store.db.execute("SELECT * FROM carries WHERE created_at<?",(now-1800,)).fetchall():
        if len(ids(row["joined"])) > 1: continue
        guild=bot.get_guild(row["guild_id"]); ch=guild and channel(guild,"carry-pings")
        try: await (ch.get_partial_message(row["message_id"])).delete()
        except discord.HTTPException: pass
        store.db.execute("DELETE FROM carries WHERE message_id=?",(row["message_id"],))
    for row in store.db.execute("SELECT * FROM giveaways WHERE ends_at<=? AND ended=0",(now,)).fetchall():
        entrants = ids(row["entrants"])
        guild = bot.get_guild(row["guild_id"])
        winner_ids = select_giveaway_winners(guild, entrants, row["winners"]) if entrants and guild else []
        store.db.execute("UPDATE giveaways SET winner_ids=?, ended=1 WHERE message_id=?", (",".join(map(str,winner_ids)), row["message_id"]))
        store.db.commit()
        if guild: await announce_winners(guild, row, winner_ids)
    store.db.commit()
    for guild in filter(is_primary_guild, bot.guilds):
        await award_previous_month(guild)

@bot.event
async def on_guild_join(guild):
    if not is_primary_guild(guild):
        return
    await auto_setup(guild, reset_channels=True)
    store.db.execute("INSERT OR REPLACE INTO configured_guilds VALUES(?,?)", (guild.id, int(time.time())))
    store.db.commit()


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot or not is_primary_guild(message.guild):
        return
    if isinstance(message.author, discord.Member) and message.author.guild_permissions.manage_messages:
        return
    key = (message.guild.id, message.channel.id, message.author.id)
    messages = recent_messages[key]
    now = time.monotonic()
    messages.append(now)
    while messages and now - messages[0] > SPAM_MESSAGE_WINDOW:
        messages.popleft()
    if len(messages) >= SPAM_MESSAGE_LIMIT:
        await activate_raid_lockdown(
            message.guild,
            f"**{len(messages)} messages from {message.author.mention} in #{message.channel.name} within {SPAM_MESSAGE_WINDOW} seconds**",
        )

@bot.event
async def on_ready():
    bot.add_view(TicketMenu()); bot.add_view(ReviewView()); bot.add_view(CarryView()); bot.add_view(GiveawayView()); bot.add_view(GiveawayClaimView()); bot.add_view(GankView()); bot.add_view(GankParticipationView()); bot.add_view(PingRoleView())
    for guild in filter(is_primary_guild, bot.guilds):
        configured = store.db.execute("SELECT 1 FROM configured_guilds WHERE guild_id=?", (guild.id,)).fetchone()
        await auto_setup(guild, reset_channels=configured is None)
        if configured is None:
            store.db.execute("INSERT INTO configured_guilds VALUES(?,?)", (guild.id, int(time.time())))
    store.db.commit()
    if not cleanup.is_running(): cleanup.start()
    # This bot uses global application commands.  Earlier versions copied the
    # same commands into every guild as well, so Discord displayed each command
    # twice (once globally and once as a guild command).  Clear those legacy
    # guild registrations, then sync the single global command set.
    for guild in filter(is_primary_guild, bot.guilds):
        bot.tree.clear_commands(guild=guild)
        await bot.tree.sync(guild=guild)
    synced = await bot.tree.sync()
    print(f"Ready as {bot.user}")
    print(f"Successfully synced {len(synced)} global slash command(s):")
    for command in synced:
        print(f"  /{command.name}")

if __name__ == "__main__": bot.run(os.environ["DISCORD_TOKEN"])
