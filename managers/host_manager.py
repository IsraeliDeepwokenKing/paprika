import discord

from managers.carry_manager import carry_manager
from managers.stage_manager import stage_manager
from managers.log_manager import log_manager
from utils.permissions import permission_manager


class HostManager:

    async def create_host(
        self,
        guild: discord.Guild,
        host: discord.Member,
        boss: str,
        max_players: int,
        ping_channel: discord.TextChannel
    ):

        if carry_manager.host_has_carry(host.id):
            raise Exception("Već imaš aktivan carry.")

        if not permission_manager.has_host_role(
            host,
            boss
        ):
            raise Exception("Nemaš host rolu za ovog bossa.")

        role = await permission_manager.create_carry_role(
    guild,
    carry_id
)

        carry_id = carry_manager.generate_id()
        stage = await stage_manager.create(
            guild,
            "TEMP",
            boss,
            host
        )

        carry_id = carry_manager.create(
            guild.id,
            host.id,
            boss,
            max_players,
            stage.id,
            0,
            ping_channel.id
        )

        await role.edit(
            name=f"carry-{carry_id}"
        )

        await stage.edit(
            name=f"{boss.lower()}-{carry_id}"
        )

        carry_manager.set_role(
            carry_id,
            role.id
        )

        carry_manager.set_stage(
            carry_id,
            stage.id
        )

        log_manager.add(
            carry_id,
            host.id,
            "host_created"
        )

        return carry_id, role, stage


host_manager = HostManager()
