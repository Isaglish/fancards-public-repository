from __future__ import annotations

import re
from typing import TYPE_CHECKING

import discord
from discord import app_commands

from source.utils import psql
from source.enums import Rarity, Character, Condition

if TYPE_CHECKING:
    from bot import Fancards


def regex_autocomplete(prefix: str, words: list[str]) -> list[str]:
    """Returns the list of ``words`` that begins with ``prefix`` or more."""
    pattern = re.compile(f'^{prefix}.*', flags=re.IGNORECASE)
    return [word for word in words if pattern.match(word)]


async def autocomplete_close_matches(interaction: discord.Interaction, current: str, words: list[str]) -> list[app_commands.Choice[str]]:
    close_matches = regex_autocomplete(current, words)

    if close_matches:
        return [
            app_commands.Choice(name=close_match, value=close_match) for close_match in close_matches[:25]
        ]
        
    return [
        app_commands.Choice(name=word, value=word) for word in words[:25]
    ]


async def rarity_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    rarities = [str(rarity) for rarity in Rarity if rarity not in Rarity.get_exclusive_rarities()]
    return await autocomplete_close_matches(interaction, current, rarities)


async def condition_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    conditions = [str(condition) for condition in Condition]
    return await autocomplete_close_matches(interaction, current, conditions)


async def card_id_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    bot: Fancards = interaction.client  # type: ignore
    
    psql_user = psql.User(bot.pool, interaction.user.id)
    close_matches = await psql_user.cards.get_close_matches_by_card_id(current)

    if close_matches is not None:
        return [
            app_commands.Choice(name=f"{card_table.card_id} ({card_table.character_name})", value=card_table.card_id) for card_table in close_matches[:25]
        ]

    return []


async def character_name_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    character_names = [character_name for (character_name, _) in Character.get_characters()]
    return await autocomplete_close_matches(interaction, current, character_names)
