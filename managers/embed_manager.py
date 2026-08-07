import discord

from managers.carry_manager import carry_manager


class EmbedManager:

    async def build(
        self,
        guild: discord.Guild,
        carry_id: str
    ):

        carry = carry_manager.get(carry_id)

        if carry is None:
            return None


        # ------------------------
        # HOST
        # ------------------------

        host = guild.get_member(
            int(carry["host_id"])
        )


        # ------------------------
        # ACTIVE
        # ------------------------

        active_lines = []

        active = carry.get("active", [])

        for slot in range(carry["max_players"]):

            if slot < len(active):

                member = guild.get_member(
                    int(active[slot])
                )

                if member:

                    active_lines.append(
                        f"{slot + 1}. {member.mention}"
                    )

                else:

                    active_lines.append(
                        f"{slot + 1}. Unknown User"
                    )

            else:

                active_lines.append(
                    f"{slot + 1}. —"
                )


        # ------------------------
        # WAITING
        # ------------------------

        waiting_lines = []

        waiting = carry.get("waiting", [])


        if waiting:

            for i, uid in enumerate(waiting):

                member = guild.get_member(
                    int(uid)
                )

                if member:

                    waiting_lines.append(
                        f"{i + 1}. {member.mention}"
                    )

                else:

                    waiting_lines.append(
                        f"{i + 1}. Unknown User"
                    )

        else:

            waiting_lines.append(
                "None"
            )


        # ------------------------
        # EMBED
        # ------------------------

        embed = discord.Embed(

            title=f"{carry['boss']} Carry",

            colour=discord.Colour.blurple()

        )


        embed.add_field(

            name="Carry ID",

            value=f"`{carry_id}`",

            inline=False

        )


        embed.add_field(

            name="Host",

            value=host.mention if host else "Unknown",

            inline=False

        )


        embed.add_field(

            name=f"Active ({len(active)}/{carry['max_players']})",

            value="\n".join(active_lines),

            inline=False

        )


        embed.add_field(

            name=f"Waiting ({len(waiting)})",

            value="\n".join(waiting_lines),

            inline=False

        )


        embed.set_footer(

            text="Deepwoken Carry"

        )


        return embed



    async def update_message(
        self,
        guild: discord.Guild,
        carry_id: str
    ):

        carry = carry_manager.get(carry_id)


        if carry is None:
            return


        channel = guild.get_channel(
            int(carry["channel_id"])
        )


        if channel is None:
            return


        try:

            message = await channel.fetch_message(
                int(carry["message_id"])
            )


        except Exception:

            return



        embed = await self.build(
            guild,
            carry_id
        )


        if embed:

            await message.edit(
                embed=embed
            )



embed_manager = EmbedManager()
