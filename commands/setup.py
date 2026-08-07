import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import View, Button

PING_ROLES = [
    "Enmity Ping",
    "Elder Ping",
    "Titus Ping"
]

HOSTER_ROLES = [
    "Enmity Hoster",
    "Elder Hoster",
    "Titus Hoster"
]


class PingRoleButton(Button):

    def __init__(self, role_name: str):
        super().__init__(
            label=role_name.replace(" Ping", ""),
            style=discord.ButtonStyle.secondary,
            custom_id=f"pingrole:{role_name}"
        )
        self.role_name = role_name

    async def callback(self, interaction: discord.Interaction):

        role = discord.utils.get(
            interaction.guild.roles,
            name=self.role_name
        )

        if role is None:
            await interaction.response.send_message(
                "Role not found.",
                ephemeral=True
            )
            return

        if role in interaction.user.roles:

            await interaction.user.remove_roles(role)

            await interaction.response.send_message(
                f"Removed **{role.name}**.",
                ephemeral=True
            )

        else:

            await interaction.user.add_roles(role)

            await interaction.response.send_message(
                f"Added **{role.name}**.",
                ephemeral=True
            )


class PingRoleView(View):

    def __init__(self):
        super().__init__(timeout=None)

        for role in PING_ROLES:
            self.add_item(PingRoleButton(role))


class Setup(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="setup",
        description="Setup Carry Bot"
    )
    async def setup_command(
        self,
        interaction: discord.Interaction
    ):

        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild

        carry_system = discord.utils.get(
            guild.categories,
            name="Carry System"
        )

        if carry_system is None:
            carry_system = await guild.create_category(
                "Carry System"
            )

        carry_stages = discord.utils.get(
            guild.categories,
            name="Carry Stages"
        )

        if carry_stages is None:
            await guild.create_category(
                "Carry Stages"
            )

        for role in HOSTER_ROLES:

            if discord.utils.get(
                guild.roles,
                name=role
            ) is None:

                await guild.create_role(
                    name=role
                )

        for role in PING_ROLES:

            if discord.utils.get(
                guild.roles,
                name=role
            ) is None:

                await guild.create_role(
                    name=role,
                    mentionable=True
                )

        for name in [
            "host-commands",
            "carry-pings",
            "carry-logs",
            "reactions",
            "incident-reports"
        ]:

            if discord.utils.get(
                guild.text_channels,
                name=name
            ) is None:

                await guild.create_text_channel(
                    name=name,
                    category=carry_system
                )

        reaction_channel = discord.utils.get(
            guild.text_channels,
            name="reactions"
        )

        if reaction_channel:

            has_messages = False

            async for _ in reaction_channel.history(limit=1):
                has_messages = True
                break

            if not has_messages:

                embed = discord.Embed(
                    title="Carry Ping Roles",
                    description="Press a button to toggle ping roles.",
                    colour=discord.Colour.blurple()
                )

                await reaction_channel.send(
                    embed=embed,
                    view=PingRoleView()
                )

        await interaction.followup.send(
            "✅ Setup completed.",
            ephemeral=True
        )


async def setup(bot):

    bot.add_view(PingRoleView())

    await bot.add_cog(
        Setup(bot)
    )
