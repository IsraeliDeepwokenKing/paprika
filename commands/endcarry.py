import discord
from discord.ext import commands
from discord import app_commands

from managers.carry_manager import carry_manager
from managers.log_manager import log_manager
from managers.stage_manager import stage_manager
from utils.permissions import permission_manager


class EndCarry(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="endcarry",
        description="End an active carry"
    )
    @app_commands.describe(
        carry_id="Carry ID"
    )
    async def endcarry(
        self,
        interaction: discord.Interaction,
        carry_id: str
    ):

        await interaction.response.defer(ephemeral=True)

        carry_id = carry_id.upper()

        carry = carry_manager.get(carry_id)

        if carry is None:
            return await interaction.followup.send(
                "Carry not found.",
                ephemeral=True
            )

        if interaction.user.id != carry["host_id"]:
            return await interaction.followup.send(
                "Only the host can end this carry.",
                ephemeral=True
            )

        guild = interaction.guild

        role = guild.get_role(carry["role_id"])
        channel = guild.get_channel(carry["channel_id"])
        logs = discord.utils.get(
            guild.text_channels,
            name="carry-logs"
        )

        # ---------------- LOG ----------------

        try:

            if logs:

                embed = discord.Embed(
                    title="📋 Carry Ended",
                    colour=discord.Colour.red()
                )

                host = guild.get_member(carry["host_id"])

                embed.add_field(
                    name="Carry ID",
                    value=carry["carry_id"],
                    inline=True
                )

                embed.add_field(
                    name="Boss",
                    value=carry["boss"],
                    inline=True
                )

                embed.add_field(
                    name="Host",
                    value=host.mention if host else f"<@{carry['host_id']}>",
                    inline=False
                )

                players = "\n".join(
                    f"<@{uid}>"
                    for uid in carry["active"]
                )

                embed.add_field(
                    name=f"Players ({len(carry['active'])})",
                    value=players or "None",
                    inline=False
                )

                history = log_manager.get(carry_id)

                if history:

                    text = "\n".join(
                        f"<@{uid}> • {action}"
                        for uid, action, ts in history
                    )

                else:
                    text = "No logs."

                embed.add_field(
                    name="Carry History",
                    value=text[:1024],
                    inline=False
                )

                await logs.send(embed=embed)

        except Exception as e:
            print("LOG ERROR:", e)

        # ---------------- REMOVE ROLES ----------------

        if role:

            for uid in carry["active"]:

                member = guild.get_member(uid)

                if member:

                    try:
                        await permission_manager.remove_carry_role(
                            member,
                            role
                        )
                    except:
                        pass

        # ---------------- DELETE MESSAGE ----------------

        if channel:

            try:
                message = await channel.fetch_message(
                    carry["message_id"]
                )
                await message.delete()
            except:
                pass

        # ---------------- DELETE STAGE ----------------

        try:
            await stage_manager.delete(
                guild,
                carry["stage_id"]
            )
        except:
            pass

        # ---------------- DELETE ROLE ----------------

        if role:

            try:
                await role.delete(
                    reason="Carry Ended"
                )
            except:
                pass

        # ---------------- CLEAR DB ----------------

        log_manager.clear(carry_id)
        carry_manager.delete(carry_id)

        # ---------------- DONE ----------------

        await interaction.followup.send(
            f"✅ Carry **{carry_id}** ended.",
            ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(
        EndCarry(bot)
    )
