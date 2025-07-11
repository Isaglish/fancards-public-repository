from __future__ import annotations

import random
import datetime
import calendar
from typing import TYPE_CHECKING

import discord
from discord.ext import commands, tasks
from discord import app_commands

from source.enums import PatreonRole, Item, Fanmoji, Character, Rarity
from source.cogs.card import CardFactory
from source.utils import psql, FANCARDS_GUILD_ID, PATREON_PAGE_URL, is_patreon, has_minimum_patreon_role
from source.utils.embed import create_custom_embed
from source.utils.view import Promotion

if TYPE_CHECKING:
    import asyncpg
    from bot import Fancards


async def _give_common_tier_rewards(pool: asyncpg.Pool[asyncpg.Record], member: discord.Member) -> None:
    if not has_minimum_patreon_role(member, PatreonRole.common):
        return None
    
    vouchers = 6
    silver = 170_000
    gems = 40
    legendary_card_packs = 2
    
    psql_user = psql.User(pool, member.id)
    psql_user_table = await psql_user.get_table()

    if psql_user_table is None:
        return None
    
    await psql_user.set_voucher(vouchers)
    await psql_user.set_silver(silver)
    await psql_user.set_gem(gems)

    await psql_user.inventory.add_item(Item.legendary_card_pack, legendary_card_packs)

    card_id = CardFactory.generate_card_id()
    owner_id = psql_user_table.id
    character_name = Character.get_random_character()
    rarity = random.choice(Rarity.get_exclusive_rarities())
    condition = CardFactory.generate_condition()
    special_rarity = CardFactory.generate_special_rarity()

    await psql_user.cards.add_card(
        psql.CardTable(
            card_id=card_id,
            owner_id=owner_id,
            rarity=rarity,
            condition=condition,
            special_rarity=special_rarity,
            character_name=character_name,
            created_at=discord.utils.utcnow()
        )
    )


async def _give_uncommon_tier_rewards(pool: asyncpg.Pool[asyncpg.Record], member: discord.Member) -> None:
    if not has_minimum_patreon_role(member, PatreonRole.uncommon):
        return None
    
    vouchers = 12
    gems = 40
    
    psql_user = psql.User(pool, member.id)
    psql_user_table = await psql_user.get_table()

    if psql_user_table is None:
        return None
    
    await psql_user.set_voucher(vouchers)
    await psql_user.set_gem(gems)


async def _give_rare_tier_rewards(pool: asyncpg.Pool[asyncpg.Record], member: discord.Member) -> None:
    if not has_minimum_patreon_role(member, PatreonRole.rare):
        return None
    
    vouchers = 18
    silver = 2_500_000
    gems = 120
    legendary_card_packs = 3
    exotic_card_packs = 3

    psql_user = psql.User(pool, member.id)
    psql_user_table = await psql_user.get_table()

    if psql_user_table is None:
        return None
    
    await psql_user.set_voucher(vouchers)
    await psql_user.set_silver(silver)
    await psql_user.set_gem(gems)

    await psql_user.inventory.add_item(Item.legendary_card_pack, legendary_card_packs)
    await psql_user.inventory.add_item(Item.exotic_card_pack, exotic_card_packs)


class Patreon(commands.Cog):
    def __init__(self, bot: Fancards):
        self.bot = bot
        self.log = bot.log

    async def cog_load(self) -> None:
        self.patreon_reward.start()

    async def cog_unload(self) -> None:
        self.patreon_reward.cancel()

    @app_commands.command(name="patreon", description="Get a link directed to our Patreon page")
    async def patreon(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)

        assert isinstance(interaction.user, discord.Member)
        is_patreon_text = f"{Fanmoji.check_pixel_icon} Thank you! You are a patron and is eligible for benefits! Click the link below to see your benefits!\n{PATREON_PAGE_URL}" if is_patreon(interaction.user) else f"{Fanmoji.cross_pixel_icon} You are currently not a patron! Click the link below to support!\n{PATREON_PAGE_URL}"

        embed = create_custom_embed(
            interaction,
            description=f"{Fanmoji.patreon_badge} Support us on Patreon to receive several perks and benefits!\n{is_patreon_text}",
            color=discord.Color.from_str("#F96854")
        )
        assert self.bot.user
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        embed.set_image(url="https://c10.patreonusercontent.com/4/patreon-media/p/campaign/10405294/1a9ace05d6c84cf8b9e86ec1c2065b18/eyJ3IjoxNjAwLCJ3ZSI6MX0%3D/3.png?token-time=1683158400&token-hash=H-DbCbeDXnTE63GcfTWPR80bRKAoD3IGyeV5Ktvajfk%3D")
        await interaction.followup.send(embed=embed, view=Promotion())

    @tasks.loop(time=datetime.time(hour=0, minute=0, tzinfo=datetime.timezone.utc))
    async def patreon_reward(self) -> None:
        guild = self.bot.get_guild(FANCARDS_GUILD_ID)
        assert guild

        today = datetime.date.today()
        is_last_day_of_month = today.day == calendar.monthrange(today.year, today.month)[1]

        if not is_last_day_of_month:
            return None
        
        for member in guild.members:
            if not is_patreon(member):
                continue
            
            await _give_common_tier_rewards(self.bot.pool, member)
            await _give_uncommon_tier_rewards(self.bot.pool, member)
            await _give_rare_tier_rewards(self.bot.pool, member)

    @patreon_reward.before_loop
    async def before_patreon_reward(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: Fancards) -> None:
    await bot.add_cog(Patreon(bot))
