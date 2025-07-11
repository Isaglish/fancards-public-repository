from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

import discord

from source.utils import psql
from source.enums import Item, Rarity, SpecialRarity, Condition
from source.utils.embed import create_info_embed

if TYPE_CHECKING:
    from bot import Fancards


# public bot
DROP_LOGS_CHANNEL_ID = 1071860175226548314
GRAB_LOGS_CHANNEL_ID = 1071860357771038810
TRADE_LOGS_CHANNEL_ID = 1071860445939519698

# test bot
# DROP_LOGS_CHANNEL_ID = 1071884852313460756
# GRAB_LOGS_CHANNEL_ID = 1071884932848304219
# TRADE_LOGS_CHANNEL_ID = 1071885064058716221


async def _handle_logger(interaction: discord.Interaction, description: str, channel_id: int) -> tuple[discord.TextChannel, discord.Embed]:
    bot: Fancards = interaction.client # type: ignore

    user = interaction.user
    guild = interaction.guild

    assert guild
    assert guild.icon

    psql_user = psql.User(bot.pool, user.id)

    psql_user_table = await psql_user.get_table()
    if psql_user_table is None:
        registered_at = "Unknown"
    else:
        registered_at = psql_user_table.registered_at

    log_channel = bot.get_channel(channel_id)
    assert isinstance(log_channel, discord.TextChannel)

    if isinstance(registered_at, datetime.datetime):
        registered_at = registered_at.strftime("%m/%d/%Y %H:%M %p")
    
    timestamp = discord.utils.utcnow().strftime("%m/%d/%Y %H:%M:%S %p")
    embed = create_info_embed(interaction, description)
    embed.title = guild.name
    embed.set_thumbnail(url=guild.icon.url)
    embed.set_footer(text=f"User ID • {user.id}\nGuild ID • {guild.id}\nRegistered Since • {registered_at}\nAt • {timestamp}")

    return (log_channel, embed)


class ActionLogger:
    @classmethod
    async def card_drop(cls, interaction: discord.Interaction, drop_count: int, premium: bool = False) -> None:
        premium_text = f" used a {Item.premium_drop.display()} item and" if premium else ""

        log_channel, embed = await _handle_logger(
            interaction,
            f"**{interaction.user}**{premium_text} dropped {drop_count} cards.",
            DROP_LOGS_CHANNEL_ID
        )
        await log_channel.send(embed=embed)

    @classmethod
    async def card_grab(
        cls,
        interaction: discord.Interaction,
        rarity: Rarity,
        special_rarity: SpecialRarity,
        condition: Condition,
        character_name: str,
        card_id: str
    ) -> None:
        log_channel, embed = await _handle_logger(
            interaction,
            f"**{interaction.user}** grabbed a {f'{special_rarity} ' if special_rarity is SpecialRarity.shiny else ''}**{character_name}** card **`{card_id}`**.",
            GRAB_LOGS_CHANNEL_ID
        )

        embed.add_field(name="Rarity", value=f"{rarity.to_emoji(True)} **{rarity.title()}**")
        embed.add_field(name="Condition", value=f"`{condition.title()} {condition.to_unicode()}`")

        await log_channel.send(embed=embed)

    @classmethod
    async def card_trade(
        cls,
        interaction: discord.Interaction,
        user: discord.Member,
        first_card_id: str,
        second_card_id: str
    ) -> None:
        log_channel, embed = await _handle_logger(
            interaction,
            f"**{interaction.user}** traded **`{first_card_id}`** for **`{second_card_id}`** with **{user}**",
            TRADE_LOGS_CHANNEL_ID
        )

        bot: Fancards = interaction.client # type: ignore

        psql_user = psql.User(bot.pool, user.id)

        psql_user_table = await psql_user.get_table()

        if psql_user_table is None:
            registered_at = "Unknown"
        else:
            registered_at = psql_user_table.registered_at

        if isinstance(registered_at, datetime.datetime):
            registered_at = registered_at.strftime("%m/%d/%Y %H:%M %p")

        assert embed.footer.text
        embed.footer.text += f"Second User Registered Since: {registered_at}"
        await log_channel.send(embed=embed)
