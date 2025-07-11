from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from source.app_commands import Group
from source.utils.embed import create_success_embed, create_error_embed

if TYPE_CHECKING:
    from bot import Fancards


class Config(commands.Cog):
    def __init__(self, bot: Fancards):
        self.bot = bot
        self.log = bot.log

    config_group = Group(name="config", description="Config related commands", default_permissions=discord.Permissions(manage_guild=True))
    config_toggle_group = Group(name="toggle", description="Config Toggle related commands.", parent=config_group)

    @config_toggle_group.command(name="level", description="Toggles level up notification on or off")
    async def config_toggle_level(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)

        if not interaction.permissions.manage_guild:
            await interaction.followup.send("You don't have the permission to do that.", ephemeral=True)
            return None
        
        async with self.bot.pool.acquire() as connection:
            assert interaction.guild
            query = """
            INSERT INTO config (guild_id, level_toggle) VALUES ($1, FALSE)
            ON CONFLICT (guild_id) DO UPDATE SET level_toggle = NOT config.level_toggle
            RETURNING config.level_toggle;
            """
            level_toggle = await connection.fetchval(query, interaction.guild.id)

        if level_toggle:
            embed = create_success_embed(interaction, f"Level up notifications have been `enabled`.")
        else:
            embed = create_error_embed(interaction, f"Level up notifications have been `disabled`.")

        await interaction.followup.send(embed=embed)
    

async def setup(bot: Fancards) -> None:
    await bot.add_cog(Config(bot))
