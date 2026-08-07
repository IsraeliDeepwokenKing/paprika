import discord

from managers.carry_manager import carry_manager


class StageManager:

    async def create(
        self,
        guild: discord.Guild,
        carry_id,
        boss,
        host,
        carry_role,
        max_players
    ):

        category = discord.utils.get(
            guild.categories,
            name="Carry Stages"
        )

        if category is None:
            category = await guild.create_category(
                "Carry Stages"
            )

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(
                view_channel=False,
                connect=False
            ),
            carry_role: discord.PermissionOverwrite(
                view_channel=True,
                connect=True,
                speak=False,
                request_to_speak=False
            ),
            host: discord.PermissionOverwrite(
                view_channel=True,
                connect=True,
                speak=True,
                mute_members=True,
                move_members=True
            )
        }

        stage = await guild.create_stage_channel(
            name=f"{boss}-{carry_id}",
            category=category,
            overwrites=overwrites,
            user_limit=max_players,
            reason="CarryBot"
        )

        try:
            await stage.create_instance(
                topic=f"{boss} Carry"
            )
        except Exception:
            pass

        try:
            await host.move_to(stage)
        except Exception:
            pass

        try:
            await host.edit(
                suppress=False
            )
        except Exception:
            pass

        return stage

    async def delete(
        self,
        guild: discord.Guild,
        stage_id: int
    ):

        channel = guild.get_channel(stage_id)

        if channel is None:

            try:
                channel = await guild.fetch_channel(stage_id)
            except Exception:
                return

        try:
            await channel.delete(
                reason="Carry Ended"
            )
        except Exception:
            pass

    async def sync_permissions(
        self,
        guild: discord.Guild,
        carry_id: str
    ):

        carry = carry_manager.get(carry_id)

        if carry is None:
            return

        stage = guild.get_channel(
            carry["stage_id"]
        )

        if stage is None:

            try:
                stage = await guild.fetch_channel(
                    carry["stage_id"]
                )
            except Exception:
                return

        role = guild.get_role(
            carry["role_id"]
        )

        host = guild.get_member(
            carry["host_id"]
        )

        if role is None:
            return

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(
                view_channel=False,
                connect=False
            ),
            role: discord.PermissionOverwrite(
                view_channel=True,
                connect=True,
                speak=False,
                request_to_speak=False
            )
        }

        if host:
            overwrites[host] = discord.PermissionOverwrite(
                view_channel=True,
                connect=True,
                speak=True,
                mute_members=True,
                move_members=True
            )

        try:
            await stage.edit(
                overwrites=overwrites
            )
        except Exception:
            pass

        try:
            for member in stage.members:

                if host and member.id == host.id:

                    try:
                        await member.edit(
                            suppress=False
                        )
                    except Exception:
                        pass

                else:

                    try:
                        await member.edit(
                            suppress=True
                        )
                    except Exception:
                        pass

        except Exception:
            pass


stage_manager = StageManager()
