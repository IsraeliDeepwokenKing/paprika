import traceback

import discord
from discord.ext import commands
from discord import app_commands

from managers.carry_manager import carry_manager
from managers.embed_manager import embed_manager
from managers.stage_manager import stage_manager

from utils.permissions import permission_manager

from views.carry_buttons import CarryButtons


BOSS_LIMITS = {

    "Titus": {
        "min": 1,
        "max": 6,
        "ping": "Titus Ping"
    },

    "Elder": {
        "min": 1,
        "max": 16,
        "ping": "Elder Ping"
    },

    "Enmity": {
        "min": 5,
        "max": 12,
        "ping": "Enmity Ping"
    }

}


class Host(commands.Cog):

    def __init__(self, bot):

        self.bot = bot


    @app_commands.command(
        name="host",
        description="Start a carry."
    )

    @app_commands.describe(
        boss="Boss",
        players="Maximum players"
    )

    @app_commands.choices(

        boss=[

            app_commands.Choice(
                name="Titus",
                value="Titus"
            ),

            app_commands.Choice(
                name="Elder",
                value="Elder"
            ),

            app_commands.Choice(
                name="Enmity",
                value="Enmity"
            )

        ]

    )

    async def host(

        self,

        interaction: discord.Interaction,

        boss: app_commands.Choice[str],

        players: app_commands.Range[int, 1, 16]

    ):

        try:

            await interaction.response.defer(
                ephemeral=True
            )

            guild = interaction.guild
            host = interaction.user

            boss_name = boss.value

            limits = BOSS_LIMITS[boss_name]

            # -------------------------
            # PLAYER LIMITS
            # -------------------------

            if players < limits["min"]:

                await interaction.followup.send(

                    f"Minimum players for **{boss_name}** is **{limits['min']}**.",

                    ephemeral=True

                )

                return


            if players > limits["max"]:

                await interaction.followup.send(

                    f"Maximum players for **{boss_name}** is **{limits['max']}**.",

                    ephemeral=True

                )

                return


            # -------------------------
            # HOST ROLE
            # -------------------------

            if not permission_manager.has_host_role(

                host,
                boss_name

            ):

                await interaction.followup.send(

                    "You don't have permission to host this boss.",

                    ephemeral=True

                )

                return


            # -------------------------
            # ALREADY HOSTING
            # -------------------------

            if carry_manager.host_has_carry(
                host.id
            ):

                await interaction.followup.send(

                    "You already have an active carry.",

                    ephemeral=True

                )

                return


            carry_id = carry_manager.generate_id()
                        # -------------------------
            # CREATE CARRY ROLE
            # -------------------------

            carry_role = await permission_manager.create_carry_role(

                guild,
                carry_id

            )

            # -------------------------
            # CREATE STAGE
            # -------------------------

            stage = await stage_manager.create(

                guild,
                carry_id,
                boss_name,
                host,
                carry_role,
                players

            )

            # -------------------------
            # FIND CARRY CHANNEL
            # -------------------------

            ping_channel = discord.utils.get(

                guild.text_channels,
                name="carry-pings"

            )

            if ping_channel is None:

                await carry_role.delete()

                await stage.delete()

                await interaction.followup.send(

                    "Couldn't find **#carry-pings**.",

                    ephemeral=True

                )

                return

            # -------------------------
            # SAVE CARRY
            # -------------------------

            carry_manager.create(

                carry_id=carry_id,

                guild_id=guild.id,

                host_id=host.id,

                boss=boss_name,

                max_players=players,

                role_id=carry_role.id,

                stage_id=stage.id,

                channel_id=ping_channel.id,

                message_id=0

            )

            # -------------------------
            # GET PING ROLE
            # -------------------------

            ping_role = permission_manager.get_ping_role(

                guild,
                boss_name

            )

            ping_text = ""

            if ping_role:

                ping_text = ping_role.mention

            # -------------------------
            # BUILD EMBED
            # -------------------------

            embed = await embed_manager.build(

                guild,
                carry_id

            )

            # -------------------------
            # BUTTONS
            # -------------------------

            view = CarryButtons(

                self.bot,
                carry_id

            )

            # -------------------------
            # SEND MESSAGE
            # -------------------------

            message = await ping_channel.send(

                content=ping_text,

                embed=embed,

                view=view,

                allowed_mentions=discord.AllowedMentions(
                    roles=True
                )

            )

            carry_manager.set_message(

                carry_id,
                message.id

            )
                        # -------------------------
            # UPDATE EMBED
            # -------------------------

            await embed_manager.update_message(

                guild,
                carry_id

            )

            # -------------------------
            # UPDATE STAGE PERMISSIONS
            # -------------------------

            await stage_manager.sync_permissions(

                guild,
                carry_id

            )

            # -------------------------
            # DONE
            # -------------------------

            await interaction.followup.send(

                "✅ Carry created successfully.",

                ephemeral=True

            )

        except Exception as e:

            traceback.print_exc()

            if interaction.response.is_done():

                try:

                    await interaction.followup.send(

                        f"❌ {type(e).__name__}: {e}",

                        ephemeral=True

                    )

                except Exception:
                    pass

            else:

                await interaction.response.send_message(

                    f"❌ {type(e).__name__}: {e}",

                    ephemeral=True

                )


async def setup(bot):

    await bot.add_cog(

        Host(bot)

    )
            
