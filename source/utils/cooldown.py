from __future__ import annotations

from typing import Callable, Union, TypeVar, Any

import discord
from discord import app_commands
from discord.ext import commands

GroupT = TypeVar("GroupT", bound=Union["app_commands.Group", "commands.Cog"])
CommandT = TypeVar("CommandT", bound=app_commands.Command[Any, ..., Any])


class ButtonOnCooldown(commands.CommandError):
    """An exception that is raised when a button view being interacted with is on cooldown"""
    def __init__(self, retry_after: float):
        self.retry_after = retry_after


def resettable_cooldown(rate: float, per: float) -> Callable[[CommandT], CommandT]:
    """Add a resettable cooldown to an :class:`app_commands.Command`."""
    def predicate(interaction: discord.Interaction) -> discord.User | discord.Member:
        return interaction.user

    def decorator(command: CommandT) -> CommandT:
        command.extras["cooldown"] = commands.CooldownMapping.from_cooldown(rate, per, predicate)
        cooldown: commands.CooldownMapping[discord.Interaction] = command.extras["cooldown"]
        
        def wrapper(interaction: discord.Interaction) -> bool:
            bucket = cooldown.get_bucket(interaction)
            assert bucket
            retry_after = cooldown.update_rate_limit(interaction)
            if retry_after and retry_after > 1:
                raise app_commands.CommandOnCooldown(bucket, retry_after)

            return True

        cmd = app_commands.check(wrapper)
        return cmd(command)

    return decorator


def reset_command_cooldown(interaction: discord.Interaction) -> None:
    """Reset a command cooldown. Requires the `@resettable_cooldown` decorator to work."""
    assert interaction.command
    cooldown = interaction.command.extras["cooldown"]
    bucket = cooldown.get_bucket(interaction)
    assert bucket
    bucket.reset()


def reset_cooldown(interaction: discord.Interaction, cooldown: commands.CooldownMapping[discord.Interaction]) -> None:
    """Reset a custom cooldown."""
    bucket = cooldown.get_bucket(interaction)
    assert bucket
    bucket.reset()
