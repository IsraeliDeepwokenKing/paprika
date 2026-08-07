import discord

from discord.ext import commands
from discord import app_commands


class CloseModal(discord.ui.Modal, title="Close Incident"):

    punishment = discord.ui.TextInput(
        label="Punishment",
        placeholder="Warn / Kick / Ban / Blacklist / None",
        required=True,
        max_length=100
    )

    notes = discord.ui.TextInput(
        label="Notes",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=1000
    )

    async def on_submit(
        self,
        interaction: discord.Interaction
    ):

        logs = discord.utils.get(
            interaction.guild.text_channels,
            name="incident-logs"
        )

        if logs:

            embed = discord.Embed(
                title="✅ Incident Closed",
                colour=discord.Colour.green()
            )

            embed.add_field(
                name="Ticket",
                value=interaction.channel.name,
                inline=False
            )

            embed.add_field(
                name="Closed By",
                value=interaction.user.mention,
                inline=False
            )

            embed.add_field(
                name="Punishment",
                value=self.punishment.value,
                inline=False
            )

            embed.add_field(
                name="Notes",
                value=self.notes.value or "None",
                inline=False
            )

            messages = []

            async for message in interaction.channel.history(
                oldest_first=True,
                limit=20
            ):

                if message.author.bot:

                    if message.embeds:

                        e = message.embeds[0]

                        for field in e.fields:

                            messages.append(
                                f"**{field.name}**\n{field.value}"
                            )

            if messages:

                embed.add_field(
                    name="Incident",
                    value="\n\n".join(messages)[:1024],
                    inline=False
                )

            await logs.send(
                embed=embed
            )

        await interaction.response.send_message(
            "Closing ticket...",
            ephemeral=True
        )

        await interaction.channel.delete(
            reason=f"Closed by {interaction.user}"
        )


class CloseIncident(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="closeincident",
        description="Close an incident ticket."
    )
    async def closeincident(
        self,
        interaction: discord.Interaction
    ):

        if not interaction.channel.name.startswith(
            "incident-"
        ):

            return await interaction.response.send_message(
                "Use this inside an incident ticket.",
                ephemeral=True
            )

        await interaction.response.send_modal(
            CloseModal()
        )


async def setup(bot):

    await bot.add_cog(
        CloseIncident(bot)
    )
