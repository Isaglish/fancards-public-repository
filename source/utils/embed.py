from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from source.enums import FancadeColor, Fanmoji, Rarity, Condition, SpecialRarity

if TYPE_CHECKING:
    from . import Context


def get_card_property_text(
    card_id: str,
    rarity: Rarity,
    condition: Condition,
    special_rarity: SpecialRarity,
    character_name: str,
    has_sleeve: bool = False,
    locked: bool = False
) -> str:
    lock_icon = Fanmoji.locked if locked else Fanmoji.unlocked
    sleeve = f" | {Fanmoji.card_sleeve}" if has_sleeve else ""
    rarity_str = f"{rarity.to_emoji(False)} | {Fanmoji.shiny}" if special_rarity is SpecialRarity.shiny else f"{rarity.to_emoji(False)} |"

    return f"{lock_icon}** | `{card_id}`** | `{condition.to_unicode()}` | {rarity_str} **{character_name}**{sleeve}"


def create_error_embed(interaction: discord.Interaction | Context, description: str) -> discord.Embed:
    """Returns a red embed."""
    if isinstance(interaction, commands.Context):
        user = interaction.author
    else:
        user = interaction.user
    
    embed = discord.Embed(
        color=FancadeColor.red(),
        description=description
    )
    embed.set_author(name=user, icon_url=user.display_avatar.url)
    return embed


def create_warning_embed(interaction: discord.Interaction | Context, description: str) -> discord.Embed:
    """Returns a yellow embed."""
    if isinstance(interaction, commands.Context):
        user = interaction.author
    else:
        user = interaction.user

    embed = discord.Embed(
        color=FancadeColor.yellow(),
        description=description
    )
    embed.set_author(name=user, icon_url=user.display_avatar.url)
    return embed


def create_success_embed(interaction: discord.Interaction | Context, description: str) -> discord.Embed:
    """Returns a green embed."""
    if isinstance(interaction, commands.Context):
        user = interaction.author
    else:
        user = interaction.user
    
    embed = discord.Embed(
        color=FancadeColor.light_green(),
        description=description
    )
    embed.set_author(name=user, icon_url=user.display_avatar.url)
    return embed


def create_info_embed(interaction: discord.Interaction | Context, description: str) -> discord.Embed:
    """Returns a blue embed."""
    if isinstance(interaction, commands.Context):
        user = interaction.author
    else:
        user = interaction.user

    embed = discord.Embed(
        color=FancadeColor.light_blue(),
        description=description
    )
    embed.set_author(name=user, icon_url=user.display_avatar.url)
    return embed


def create_custom_embed(interaction: discord.Interaction | Context, description: str, color: discord.Color) -> discord.Embed:
    """Returns a custom colored embed."""
    if isinstance(interaction, commands.Context):
        user = interaction.author
    else:
        user = interaction.user
    
    embed = discord.Embed(
        color=color,
        description=description
    )
    embed.set_author(name=user, icon_url=user.display_avatar.url)
    return embed
