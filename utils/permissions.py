import discord


HOST_ROLES = {
    "Titus": "Titus Hoster",
    "Elder": "Elder Hoster",
    "Enmity": "Enmity Hoster"
}

PING_ROLES = {
    "Titus": "Titus Ping",
    "Elder": "Elder Ping",
    "Enmity": "Enmity Ping"
}


class PermissionManager:

    # ----------------------------
    # HOST ROLE
    # ----------------------------

    def has_host_role(
        self,
        member: discord.Member,
        boss: str
    ) -> bool:

        role_name = HOST_ROLES.get(boss)

        if role_name is None:
            return False

        return discord.utils.get(
            member.roles,
            name=role_name
        ) is not None

    # ----------------------------
    # PING ROLE
    # ----------------------------

    def get_ping_role(
        self,
        guild: discord.Guild,
        boss: str
    ):

        role_name = PING_ROLES.get(boss)

        if role_name is None:
            return None

        return discord.utils.get(
            guild.roles,
            name=role_name
        )

    # ----------------------------
    # CREATE CARRY ROLE
    # ----------------------------

    async def create_carry_role(
        self,
        guild: discord.Guild,
        carry_id: str
    ):

        role = await guild.create_role(

            name=f"carry-{carry_id}",

            mentionable=False,

            reason="CarryBot"

        )

        return role

    # ----------------------------
    # GIVE ROLE
    # ----------------------------

    async def give_carry_role(
        self,
        member: discord.Member,
        role: discord.Role
    ):

        if role not in member.roles:

            await member.add_roles(
                role,
                reason="Joined carry"
            )

    # ----------------------------
    # REMOVE ROLE
    # ----------------------------

    async def remove_carry_role(
        self,
        member: discord.Member,
        role: discord.Role
    ):

        if role in member.roles:

            await member.remove_roles(
                role,
                reason="Left carry"
            )

    # ----------------------------
    # DELETE ROLE
    # ----------------------------

    async def delete_carry_role(
        self,
        guild: discord.Guild,
        role_id: int
    ):

        role = guild.get_role(role_id)

        if role:

            await role.delete(
                reason="Carry ended"
            )


permission_manager = PermissionManager()
