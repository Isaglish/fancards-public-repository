from typing import Any

import discord
from discord import app_commands

from source.utils.embed import create_error_embed
from source.utils.time import seconds_to_human


class Group(app_commands.Group):
    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)

    async def on_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        if isinstance(error, app_commands.CommandOnCooldown):
            human_time = seconds_to_human(error.retry_after)
            embed = create_error_embed(interaction, f"You are currently on cooldown, please wait for `{human_time}` before using this command again.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            raise error
