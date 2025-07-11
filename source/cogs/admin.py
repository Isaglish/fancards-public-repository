from __future__ import annotations

import json
from typing import TYPE_CHECKING, Optional, Literal, Any
from io import BytesIO

import discord
from discord.ext import commands

from .card import CardFactory
from source.utils import psql
from source.utils.embed import create_error_embed, create_success_embed, create_info_embed
from source.entity import ItemEntity
from source.enums import Currency, Rarity, Condition, SpecialRarity, Item, Character

if TYPE_CHECKING:
    from bot import Fancards
    from source.utils import Context

User = discord.User | discord.Member

FLAGS_PREFIX = "--"
FLAGS_DELIMITER = " "
BLACKLIST_CHANNEL_ID = 1100719915553538078


async def _handle_blacklist(ctx: Context, flags: BlacklistFlags, option: Literal["add", "remove"]) -> None:
    is_option_add = option == "add"

    if isinstance(flags.user, User):
        user_id = flags.user.id
        success_text = f"{flags.user.mention} has been blacklisted.\n**Reason:** {flags.reason}" if is_option_add else f"{flags.user.mention} has been removed from the blacklist."
    else:
        user_id = flags.user
        user = await ctx.bot.fetch_user(user_id)
        success_text = f"{user.mention} has been blacklisted.\n**Reason:** {flags.reason}" if is_option_add else f"{user.mention} has been removed from the blacklist."
        
    psql_blacklist = psql.Blacklist(ctx.bot.pool, user_id)
    psql_blacklist_table = await psql_blacklist.get_table()

    if psql_blacklist_table is not None and is_option_add:
        embed = create_error_embed(ctx, "This user is already in the blacklist.")
        await ctx.reply(embed=embed)
        return None
    
    elif psql_blacklist_table is None and not is_option_add:
        embed = create_error_embed(ctx, "This user not in the blacklist.")
        await ctx.reply(embed=embed)
        return None

    if is_option_add:
        await psql_blacklist.add_user(user_id, flags.reason)
    else:
        await psql_blacklist.remove_user(user_id)

    embed = create_info_embed(ctx, success_text)
    await ctx.reply(embed=embed)

    embed = create_info_embed(ctx, success_text)
    embed.title = "Blacklist Addition." if is_option_add else "Blacklist Removal."
    
    channel = ctx.bot.get_channel(BLACKLIST_CHANNEL_ID)
    assert channel
    assert isinstance(channel, discord.TextChannel)
    await channel.send(embed=embed)


class CommandFlags(commands.FlagConverter, prefix=FLAGS_PREFIX, delimiter=FLAGS_DELIMITER):
    pass


class CardFlags(CommandFlags):
    user: Optional[User] = None
    card_id: Optional[str] = commands.flag(name="cardid", aliases=["id"], default=None)
    rarity: Rarity = commands.flag(name="rarity", aliases=["r"], default=None)
    condition: Condition = commands.flag(name="condition", aliases=["c"], default=None)
    special_rarity: SpecialRarity = commands.flag(name="specialrarity", aliases=["sr"], default=SpecialRarity.unknown)
    character_name: Optional[str] = commands.flag(name="charactername", aliases=["name"], default=None)


class ItemFlags(CommandFlags):
    user: Optional[User] = None
    item: Optional[Item] = None
    amount: int = 1


class CurrencyFlags(CommandFlags):
    user: Optional[User] = None
    currency: Currency = Currency.silver
    amount: int = 1


class BlacklistFlags(CommandFlags):
    user: User | int
    reason: Optional[str] = None


class Admin(commands.Cog):
    def __init__(self, bot: Fancards):
        self.bot = bot
        self.log = bot.log

    @commands.is_owner()
    @commands.command("toggle-maintenance-mode")
    async def toggle_maintenance(self, ctx: Context) -> None:
        with open("source/json/config.json", "r") as file:
            data: dict[str, Any] = json.load(file)

        with open("source/json/config.json", "w") as file:
            maintenance_mode = data.get("maintenance_mode", False)
            data["maintenance_mode"] = not maintenance_mode
            json.dump(data, file, indent=4)

        embed = create_success_embed(ctx, f"Maintenance Mode has been set to `{maintenance_mode}`")
        await ctx.send(embed=embed)

    @commands.is_owner()
    @commands.group(name="give", invoke_without_command=True)
    async def give_group(self, ctx: Context):
        pass

    @commands.is_owner()
    @give_group.command(
        name="currency",
        description="Gives a currency out of thin air."
    )
    async def give_currency(self, ctx: Context, *, flags: CurrencyFlags) -> None:
        user = ctx.author if flags.user is None or flags.user == ctx.author else flags.user
        amount = flags.amount
        currency = flags.currency
        
        psql_user = psql.User(self.bot.pool, user.id)
        psql_user_table = await psql_user.get_table()
        if psql_user_table is None:
            embed = create_error_embed(ctx, "This user is not registered.")
            await ctx.send(embed=embed)
            return None
        
        if amount == 0:
            embed = create_error_embed(ctx, "Please provide a proper amount.")
            await ctx.send(embed=embed)
            return None
        
        if amount < 1:
            embed = create_error_embed(ctx, f"{currency.to_emoji()} {abs(amount):,} was deducted from {user.mention}.")
        else:
            embed = create_success_embed(ctx, f"{user.mention} was given {currency.to_emoji()} {amount:,}.")
        
        if currency is Currency.silver:
            await psql_user.set_silver(amount)

        elif currency is Currency.star:
            await psql_user.set_star(amount)

        elif currency is Currency.gem:
            await psql_user.set_gem(amount)

        elif currency is Currency.voucher:
            await psql_user.set_voucher(amount)

        await ctx.send(embed=embed)

    @commands.is_owner()
    @give_group.command(
        name="card",
        description="Gives a card out of thin air."
    )
    async def give_card(self, ctx: Context, *, flags: CardFlags) -> None:
        user = ctx.author if flags.user is None or flags.user == ctx.author else flags.user
        
        psql_user = psql.User(self.bot.pool, user.id)
        psql_user_table = await psql_user.get_table()
        if psql_user_table is None:
            embed = create_error_embed(ctx, "This user is not registered.")
            await ctx.send(embed=embed)
            return None
        
        card_id = flags.card_id or CardFactory.generate_card_id()
        owner_id = psql_user_table.id
        character_name = flags.character_name or Character.get_random_character(flags.rarity)
        rarity = flags.rarity or Character.get_character_rarity(character_name)
        condition = flags.condition or CardFactory.generate_condition()
        special_rarity = flags.special_rarity or CardFactory.generate_special_rarity()

        character_names = (character_name for (character_name, _) in Character.get_characters())
        if character_name not in list(character_names):
            embed = create_error_embed(ctx, "This character doesn't exist, remember, character names are case-sensitive.")
            await ctx.send(embed=embed)
            return None

        base_card = CardFactory.build_card(
            card_id=card_id,
            rarity=rarity,
            condition=condition,
            special_rarity=special_rarity,
            character_name=character_name
        )
        buffer = BytesIO()
        base_card.save(buffer, format="PNG")
        buffer.seek(0)

        file = discord.File(buffer, filename="card.png")
        
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
        embed = create_info_embed(ctx, f"{user.mention} was given the card **`{card_id}`**.")
        embed.set_image(url="attachment://card.png")
        await ctx.send(embed=embed, file=file)

    @commands.is_owner()
    @give_group.command(
        name="item",
        description="Gives an item out of thin air."
    )
    async def give_item(self, ctx: Context, *, flags: ItemFlags):
        user = ctx.author if flags.user is None or flags.user == ctx.author else flags.user

        psql_user = psql.User(self.bot.pool, user.id)
        psql_user_table = await psql_user.get_table()
        if psql_user_table is None:
            embed = create_error_embed(ctx, "This user is not registered.")
            await ctx.send(embed=embed)
            return None
        
        item = flags.item
        amount = flags.amount

        if item is None:
            embed = create_error_embed(ctx, "Please provide an item to give.")
            await ctx.send(embed=embed)
            return None
        
        if amount == 0:
            embed = create_error_embed(ctx, "Please provide a proper amount.")
            await ctx.send(embed=embed)
            return None
        
        if not ItemEntity.to_entity(item).visible:
            embed = create_error_embed(ctx, "This item cannot be stored in the inventory.")
            await ctx.send(embed=embed)
            return None
        
        if amount < 1:
            await psql_user.inventory.remove_item(item, abs(amount))
            description = f"{item.display()} `x{abs(amount):,}` was removed from the inventory of {user.mention}."
            embed = create_error_embed(ctx, description)
        else:
            await psql_user.inventory.add_item(item, amount)
            description = f"{item.display()} `x{amount:,}` was added to the inventory of {user.mention}."
            embed = create_success_embed(ctx, description)

        await ctx.send(embed=embed)

    @commands.is_owner()
    @commands.command(
        name="delete-card",
        aliases=["dcard"],
        description="Deletes a card."
    )
    async def delete_card(self, ctx: Context, card_id: str):
        psql_card = psql.Card(self.bot.pool, ctx.author.id)

        card = await psql_card.get_card(card_id)
        if card is None:
            embed = create_error_embed(ctx, f"I couldn't find any card with the ID **`{card_id}`**")
            await ctx.send(embed=embed)
            return None

        await psql_card.delete_card(card_id)
        embed = create_info_embed(ctx, f"Card **`{card_id}`** has been deleted.")
        await ctx.send(embed=embed)

    @commands.is_owner()
    @commands.group(name="blacklist", invoke_without_command=True)
    async def blacklist_group(self, ctx: Context):
        pass
    
    @blacklist_group.command(
        name="add",
        description="Add a user to the blacklist."
    )
    async def blacklist_add(self, ctx: Context, *, flags: BlacklistFlags):
        await _handle_blacklist(ctx, flags, "add")

    @blacklist_group.command(
        name="remove",
        description="Remove a user from the blacklist."
    )
    async def blacklist_remove(self, ctx: Context, *, flags: BlacklistFlags):
        await _handle_blacklist(ctx, flags, "remove")


async def setup(bot: Fancards) -> None:
    await bot.add_cog(Admin(bot))
