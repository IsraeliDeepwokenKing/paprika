import discord


class TakeButton(discord.ui.Button):

    def __init__(self):
        super().__init__(
            label="Take",
            style=discord.ButtonStyle.success,
            custom_id="incident_take"
        )

    async def callback(self, interaction: discord.Interaction):

        embed = interaction.message.embeds[0]

        guild = interaction.guild

        category = discord.utils.get(
            guild.categories,
            name="Incident Tickets"
        )

        if category is None:
            category = await guild.create_category(
                "Incident Tickets"
            )

        overwrites = {

            guild.default_role: discord.PermissionOverwrite(
                view_channel=False
            ),

            interaction.user: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True
            )

        }

        ticket = await guild.create_text_channel(

            name=f"incident-{interaction.message.id}",

            category=category,

            overwrites=overwrites

        )

        await ticket.send(

            f"Ticket claimed by {interaction.user.mention}",

            embed=embed

        )

        for item in self.view.children:
            item.disabled = True

        await interaction.response.edit_message(
            view=self.view
        )


class CloseButton(discord.ui.Button):

    def __init__(self):
        super().__init__(
            label="Close",
            style=discord.ButtonStyle.danger,
            custom_id="incident_close"
        )

    async def callback(
        self,
        interaction: discord.Interaction
    ):

        await interaction.response.send_message(

            "Use **/closeincident** inside the ticket.",

            ephemeral=True

        )


class IncidentView(discord.ui.View):

    def __init__(self):

        super().__init__(
            timeout=None
        )

        self.add_item(
            TakeButton()
        )

        self.add_item(
            CloseButton()
        )
