from __future__ import annotations

from typing import TYPE_CHECKING

import discord

from source.enums import PatreonRole

if TYPE_CHECKING:
    from bot import Context as Context


FANCARDS_GUILD_ID = 1064532756413042778
RARE_FINDS_CHANNEL_ID = 1066027597059854346

DISCORD_SERVER_URL = "https://discord.gg/9KqjurZRjv"
PATREON_PAGE_URL = "https://www.patreon.com/Fancards"


def is_patreon(member: discord.Member) -> bool:
    """Returns True if member has any Patreon roles regardless of the tier."""
    member_role_ids = [role.id for role in member.roles]
    return any([patreon_role_id in member_role_ids for patreon_role_id in PatreonRole.get_role_ids()])


def has_minimum_patreon_role(member: discord.Member, minimum_patreon_role: PatreonRole) -> bool:
    """Returns True if member has ``minimum_patreon_role`` or higher tier."""
    patreon_role_map = {role.role_id: role for role in PatreonRole}
    patreon_roles: list[PatreonRole] = []

    for role in member.roles:
        if role.id not in PatreonRole.get_role_ids():
            continue

        patreon_role = patreon_role_map[role.id]
        patreon_roles.append(patreon_role)
    
    return any([patreon_role.tier >= minimum_patreon_role.tier for patreon_role in patreon_roles])
