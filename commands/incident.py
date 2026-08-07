import discord

from discord.ext import commands
from discord import app_commands

from views.incident_view import IncidentView


class IncidentModal(discord.ui.Modal, title="Incident Report"):

    reason = discord.ui.TextInput(
        label="Reason",
        required=True,
        max_length=200
    )

    clip = discord.ui.TextInput(
        label="Clip Link",
        required=True,
        placeholder="https://..."
    )

    context = discord.ui.TextInput(
        label="Context (Optional)",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=1000
    )

    async def on_submit(
        self,
        interaction: discord.Interaction
    ):

        reports = discord.utils.get(
            interaction.guild.text_channels,
            name="incident-reports"
        )

        if reports is None:

            return await interaction.response.send_message(
                "incident-reports channel not found.",
                ephemeral=True
            )

        embed = discord.Embed(
            title="🚨 Incident Report",
            colour=discord.Colour.red()
        )

        embed.add_field(
            name="Reporter",
            value=interaction.user.mention,
            inline=False
        )

        embed.add_field(
            name="Reason",
            value=self.reason.value,
            inline=False
        )

        embed.add_field(
            name="Clip",
            value=self.clip.value,
            inline=False
        )

        embed.add_field(
            name="Context",
            value=self.context.value or "None",
            inline=False
        )

        embed.set_footer(
            text=f"Reporter ID: {interaction.user.id}"
        )

        await reports.send(
            embed=embed,
            view=IncidentView()
        )

        await interaction.response.send_message(
            "✅ Incident submitted.",
            ephemeral=True
        )


class Incident(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="incident",
        description="Create an incident report."
    )
    async def incident(
        self,
        interaction: discord.Interaction
    ):

        await interaction.response.send_modal(
            IncidentModal()
        )


async def setup(bot):

    bot.add_view(
        IncidentView()
    )

    await bot.add_cog(
        Incident(bot)
    )
