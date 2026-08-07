import discord
from discord.ui import Button, View

from managers.carry_manager import carry_manager
from managers.queue_manager import queue_manager
from managers.embed_manager import embed_manager
from managers.stage_manager import stage_manager
from utils.permissions import permission_manager


class JoinButton(Button):

    def __init__(self, carry_id: str):

        super().__init__(
            label="Join",
            style=discord.ButtonStyle.success,
            custom_id=f"join:{carry_id}"
        )

        self.carry_id = carry_id

    async def callback(
        self,
        interaction: discord.Interaction
    ):

        carry = carry_manager.get(self.carry_id)

        if carry is None:

            await interaction.response.send_message(
                "This carry no longer exists.",
                ephemeral=True
            )

            return

        if interaction.user.id == carry["host_id"]:

            await interaction.response.send_message(
                "You cannot join your own carry.",
                ephemeral=True
            )

            return

        guild = interaction.guild
        member = interaction.user

        success, result = queue_manager.join(
            self.carry_id,
            member.id
        )

        if not success:

            await interaction.response.send_message(
                result,
                ephemeral=True
            )

            return

        role = guild.get_role(
            carry["role_id"]
        )

        if role:

            await permission_manager.give_carry_role(
                member,
                role
            )

        await stage_manager.sync_permissions(
            guild,
            self.carry_id
        )

        await embed_manager.update_message(
            guild,
            self.carry_id
        )

        if result == "active":

            carry = carry_manager.get(self.carry_id)

            position = carry["active"].index(member.id)

            await interaction.response.send_message(
                f"You joined the carry.\nPosition: **{position + 1}**",
                ephemeral=True
            )

        else:

            carry = carry_manager.get(self.carry_id)

            position = carry["waiting"].index(member.id)

            await interaction.response.send_message(
                f"The carry is full.\nYou have been added to the waiting queue (**{position + 1}**).",
                ephemeral=True
            )
class LeaveButton(Button):

    def __init__(self, carry_id: str):

        super().__init__(
            label="Leave",
            style=discord.ButtonStyle.danger,
            custom_id=f"leave:{carry_id}"
        )

        self.carry_id = carry_id

    async def callback(
        self,
        interaction: discord.Interaction
    ):

        carry = carry_manager.get(self.carry_id)

        if carry is None:

            await interaction.response.send_message(
                "This carry no longer exists.",
                ephemeral=True
            )

            return

        guild = interaction.guild
        member = interaction.user

        success, promoted = queue_manager.leave(
            self.carry_id,
            member.id
        )

        if not success:

            await interaction.response.send_message(
                promoted,
                ephemeral=True
            )

            return

        role = guild.get_role(
            carry["role_id"]
        )

        if role:

            await permission_manager.remove_carry_role(
                member,
                role
            )

        if promoted is not None:

            promoted_member = guild.get_member(promoted)

            if promoted_member and role:

                await permission_manager.give_carry_role(
                    promoted_member,
                    role
                )

        await stage_manager.sync_permissions(
            guild,
            self.carry_id
        )

        await embed_manager.update_message(
            guild,
            self.carry_id
        )

        await interaction.response.send_message(
            "You left the carry.",
            ephemeral=True
        )


class CarryButtons(View):

    def __init__(
        self,
        bot,
        carry_id: str
    ):

        super().__init__(timeout=None)

        self.bot = bot
        self.carry_id = carry_id

        self.add_item(
            JoinButton(carry_id)
        )

        self.add_item(
            LeaveButton(carry_id)
        )
