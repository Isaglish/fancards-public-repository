from __future__ import annotations

import random
from typing import Optional
from typing import TYPE_CHECKING, Optional

import discord
from discord import app_commands
from discord.ext import commands

from source.entity import ItemEntity
from source.app_commands import Group
from source.enums import Fanmoji, Currency, Item, PatreonRole
from source.utils import psql, is_patreon, has_minimum_patreon_role
from source.utils.embed import (
    create_error_embed,
    create_success_embed,
    create_warning_embed,
    create_info_embed
)
from source.utils.view import Confirm, EmbedPaginator, wait_for_confirmation
from source.utils.autocomplete import autocomplete_close_matches, regex_autocomplete

if TYPE_CHECKING:
    from bot import Fancards


ITEMS = [item for item in Item]
ITEM_ENTITIES = [ItemEntity.to_entity(item) for item in Item]


async def _confirm_item_buy(
    interaction: discord.Interaction,
    psql_user: psql.User,
    psql_user_table: Optional[psql.UserTable],
    message: discord.WebhookMessage,
    item: Item,
    item_entity: ItemEntity,
    currency: Currency,
    total_price: int,
    amount_to_buy: int,
    backpack_level: int
) -> None:
    if psql_user_table is None:
        embed = create_error_embed(interaction, "You are currently not registered.")
        await message.edit(embed=embed, view=None)
        return None
    
    if (psql_user_table.star < total_price and currency is Currency.star
        or psql_user_table.silver < total_price and currency is Currency.silver
        or psql_user_table.gem < total_price and currency is Currency.gem
        or psql_user_table.voucher < total_price and currency is Currency.voucher
    ):
        embed = create_error_embed(interaction, f"You currently don't have enough {currency.display()}.")
        await message.edit(embed=embed, view=None)
        return None

    if item is Item.backpack_upgrade and backpack_level == 5:
        embed = create_error_embed(interaction, "Your backpack is already at maximum level.")
        await interaction.followup.send(embed=embed)
        return None

    if currency is Currency.silver:
        await psql_user.set_silver(total_price, subtract=True)

    elif currency is Currency.gem:
        await psql_user.set_gem(total_price, subtract=True)

    elif currency is Currency.voucher:
        await psql_user.set_voucher(total_price, subtract=True)
        
    else:
        raise ValueError("Currency is not defined.")

    if item is Item.backpack_upgrade:
        await psql_user.increase_backpack_level()
    else:
        await psql_user.inventory.add_item(item, amount_to_buy)

    usable_item_text = "\n\nUse command </item use:1071353123051941898> to use this item." if item_entity.usable else ""
    embed = create_success_embed(interaction, f"Purchase successful!\n\n**You received:**\n• {item.display()} `x{amount_to_buy}`{usable_item_text}")
    await message.edit(embed=embed, view=None)


async def _confirm_item_use(
    interaction: discord.Interaction,
    psql_user: psql.User,
    message: discord.WebhookMessage,
    item: Item,
    amount_to_use: int
) -> None:
    item_result = await psql_user.inventory.get_item(item)
    if item_result is None:
        embed = create_error_embed(interaction, f"I couldn't find any {item.display()} in your inventory.")
        await message.edit(embed=embed, view=None)
        return None

    if item_result.amount < amount_to_use:
        embed = create_error_embed(interaction, f"You currently don't have enough {item.display()} in your inventory.")
        await message.edit(embed=embed, view=None)
        return None

    psql_user_table = await psql_user.get_table()

    if psql_user_table is None:
        embed = create_error_embed(interaction, "You are currently not registered.")
        await message.edit(embed=embed, view=None)
        return None
    
    cards = await psql_user.cards.get_cards()
    assert cards

    if item in [Item.rare_card_pack, Item.epic_card_pack, Item.mythic_card_pack, Item.legendary_card_pack, Item.exotic_card_pack]:
        backpack_level = psql_user_table.backpack_level

        if (backpack_level < 5) and (len(cards) > backpack_level*500):
            embed = create_error_embed(interaction, "Your backpack is full! Consider burning cards or upgrading your backpack.")
            await message.edit(embed=embed, view=None)
            return None
    
    assert isinstance(interaction.user, discord.Member)
    if has_minimum_patreon_role(interaction.user, PatreonRole.uncommon):
        if random.random() < 0.9:  # 10% chance of not removing
            await psql_user.inventory.remove_item(item, amount_to_use)
    else:
        await psql_user.inventory.remove_item(item, amount_to_use)

    item_entity = ItemEntity.to_entity(item)
    if item_entity.usable:
        await item_entity.use(interaction, item, message)


async def _confirm_item_recycle(
    interaction: discord.Interaction,
    psql_user: psql.User,
    message: discord.WebhookMessage,
    item: Item,
    amount_to_recycle: int,
    currency: Currency,
    total_price: int
) -> None:
    item_result = await psql_user.inventory.get_item(item)
    if item_result is None:
        embed = create_error_embed(interaction, f"I couldn't find any {item.display()} in your inventory.")
        await message.edit(embed=embed, view=None)
        return None

    if item_result.amount < amount_to_recycle:
        embed = create_error_embed(interaction, f"You currently don't have enough {item.display()} in your inventory.")
        await message.edit(embed=embed, view=None)
        return None
    
    if currency is Currency.silver:
        await psql_user.set_silver(total_price)

    elif currency is Currency.gem:
        await psql_user.set_gem(total_price)

    elif currency is Currency.voucher:
        await psql_user.set_voucher(total_price)

    else:
        raise ValueError("Currency is not defined.")
    
    await psql_user.inventory.remove_item(item, amount_to_recycle)

    embed = create_success_embed(interaction, f"Recycling successful! You received:\n{currency.to_emoji()} {total_price:,}")
    await message.edit(embed=embed, view=None)


def _calculate_backpack_upgrade_price(backpack_level: int) -> int:
    base_price = 50 * backpack_level
    price = ((base_price*(backpack_level/2)) + (base_price*2)) - 50
    return round(price)


async def _item_buy_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    bot: Fancards = interaction.client  # type: ignore
    psql_user = psql.User(bot.pool, interaction.user.id)
    psql_user_table = await psql_user.get_table()

    if psql_user_table is None:
        entity_names = [entity.name for entity in ITEM_ENTITIES if entity.purchasable]
        return await autocomplete_close_matches(interaction, current, entity_names)
    
    silver = psql_user_table.silver
    stars = psql_user_table.star
    gems = psql_user_table.gem
    vouchers = psql_user_table.voucher

    currency_map = {
        Currency.silver: silver,
        Currency.star: stars,
        Currency.gem: gems,
        Currency.voucher: vouchers
    }
    
    entity_names: list[str] = []
    for item in ITEMS:
        entity = ItemEntity.to_entity(item)
        price = entity.price
        if not entity.purchasable:
            continue

        if item is Item.backpack_upgrade:
            price = _calculate_backpack_upgrade_price(psql_user_table.backpack_level)

        assert price
        assert entity.currency

        if price <= currency_map[entity.currency]:
            entity_names.append(entity.name)

    return await autocomplete_close_matches(interaction, current, entity_names)


async def _item_use_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    bot: Fancards = interaction.client  # type: ignore
    psql_user = psql.User(bot.pool, interaction.user.id)
    psql_user_table = await psql_user.get_table()

    if psql_user_table is None:
        entity_names = [entity.name for entity in ITEM_ENTITIES if entity.usable]
        return await autocomplete_close_matches(interaction, current, entity_names)
    
    entity_names: list[str] = []
    for item in ITEMS:
        entity = ItemEntity.to_entity(item)
        if not entity.usable:
            continue

        if (await psql_user.inventory.get_item(item)) is not None:
            entity_names.append(entity.name)
    
    return await autocomplete_close_matches(interaction, current, entity_names)


async def _item_info_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    entity_names = [entity.name for entity in ITEM_ENTITIES]
    return await autocomplete_close_matches(interaction, current, entity_names)


async def _item_recycle_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    bot: Fancards = interaction.client  # type: ignore
    psql_user = psql.User(bot.pool, interaction.user.id)
    psql_user_table = await psql_user.get_table()

    if psql_user_table is None:
        entity_names = [entity.name for entity in ITEM_ENTITIES if entity.visible and entity.purchasable]
        return await autocomplete_close_matches(interaction, current, entity_names)
    
    entity_names: list[str] = []
    for item in ITEMS:
        entity = ItemEntity.to_entity(item)
        if not entity.visible or not entity.purchasable:
            continue

        if (await psql_user.inventory.get_item(item)) is not None:
            entity_names.append(entity.name)

    return await autocomplete_close_matches(interaction, current, entity_names)


class ItemCog(commands.Cog):
    def __init__(self, bot: Fancards):
        self.bot = bot
        self.log = bot.log

    item_group = Group(name="item", description="Item related commands")

    def _display_balance(self, psql_user_table: psql.UserTable) -> str:
        return f"{Fanmoji.silver} {psql_user_table.silver:,}\n{Fanmoji.star} {psql_user_table.star:,}\n{Fanmoji.gem} {psql_user_table.gem:,}\n{Fanmoji.voucher} {psql_user_table.voucher:,}"

    @item_group.command(name="inventory", description="View your inventory or specify a user to view theirs")
    @app_commands.describe(user="Show the inventory of this user")
    async def show_inventory(self, interaction: discord.Interaction, user: Optional[discord.Member | discord.User] = None):
        await interaction.response.defer(thinking=True)
        user = interaction.user if user is None or interaction.user == user else user

        psql_user = psql.User(self.bot.pool, user.id)

        psql_user_table = await psql_user.get_table()

        if psql_user_table is None:
            description = "You are currently not registered." if user == interaction.user else "This user is not registered."
            embed = create_error_embed(interaction, description)
            await interaction.followup.send(embed=embed)
            return None

        inventory = await psql_user.inventory.get_items()

        silver = psql_user_table.silver
        star = psql_user_table.star
        gem = psql_user_table.gem
        voucher = psql_user_table.voucher

        if inventory is None:
            embed = create_info_embed(
                interaction,
                f"Viewing the inventory of {user.mention}.\n{Fanmoji.silver} {silver:,}\n{Fanmoji.star} {star:,}\n{Fanmoji.gem} {gem:,}\n{Fanmoji.voucher} {voucher:,}"
            )
            await interaction.followup.send(embed=embed)
            return None
        
        embeds: list[discord.Embed] = []
        end = 10
        for start in range(0, len(inventory), 10):
            current_page = list(inventory)[start:end]
            end += 10

            items: list[str] = []
            for item_table in current_page:
                item = item_table.item
                item_entity = ItemEntity.to_entity(item)
                if not item_entity.visible:
                    continue
                
                items.append(f"• {item.display()} `x{item_table.amount}`")

            joined_items = "\n".join(items)
            embed = create_info_embed(
                interaction,
                f"Viewing the inventory of {user.mention}.\n{Fanmoji.silver} {silver:,}\n{Fanmoji.star} {star:,}\n{Fanmoji.gem} {gem:,}\n{Fanmoji.voucher} {voucher:,}\n\n{joined_items}"
            )
            embeds.append(embed)

        paginator = EmbedPaginator(interaction, embeds)
        embed = paginator.index_page
        await interaction.followup.send(embed=embed, view=paginator)

    @item_group.command(name="shop", description="View the shop and buy some items")
    async def item_shop(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)

        shop_items = [item for item in Item if ItemEntity.to_entity(item).purchasable]

        psql_user = psql.User(self.bot.pool, interaction.user.id)
        psql_user_table = await psql_user.get_table()

        if psql_user_table is None:
            balance = "`[Not Registered]`"
            backpack_level = 1
        else:
            backpack_level = psql_user_table.backpack_level
            balance = self._display_balance(psql_user_table)

        embeds: list[discord.Embed] = []
        end = 5
        for start in range(0, len(shop_items), 5):
            current_shop_items = shop_items[start:end]
            end += 5

            items: list[str] = []
            for shop_item in current_shop_items:
                shop_item_entity = ItemEntity.to_entity(shop_item)
                assert shop_item_entity.currency

                shop_item_name = shop_item.title()
                price = shop_item_entity.price
                if shop_item is Item.backpack_upgrade:
                    if backpack_level == 5:
                        continue
                
                    shop_item_name = f"{shop_item.title()} (Lvl. {backpack_level+1})"
                    price = _calculate_backpack_upgrade_price(backpack_level)

                assert isinstance(interaction.user, discord.Member)
                if is_patreon(interaction.user) and price is not None:
                    price -= price * 0.2
                    price = round(price)
                
                items.append(f"{shop_item.to_emoji()} **{shop_item_name}**\n_{shop_item_entity.description}_\n- {shop_item_entity.currency.to_emoji()} {price:,}\n")

            joined_items = "\n".join(items)
            embed = create_info_embed(interaction, f"**Your balance:**\n{balance}\n\n{joined_items}\n\n- </item buy:1071353123051941898> to buy an item.\n- </item use:1071353123051941898> to use an item.\n- </item info:1071353123051941898> to view an item.")
            embed.title = "Buy some useful items!"
            embeds.append(embed)

        paginator = EmbedPaginator(interaction, embeds)
        embed = paginator.index_page
        await interaction.followup.send(embed=embed, view=paginator)

    @item_group.command(name="buy", description="Buy an item from the shop")
    @app_commands.rename(item_name="item", amount_to_buy="amount")
    @app_commands.describe(
        item_name="The name of the item you wish to buy; case-insensitive",
        amount_to_buy="The amount of the item you wish to buy"
    )
    @app_commands.autocomplete(item_name=_item_buy_autocomplete)
    async def item_buy(self, interaction: discord.Interaction, item_name: str, amount_to_buy: int = 1):
        await interaction.response.defer(thinking=True)

        if amount_to_buy < 1:
            embed = create_error_embed(interaction, "Please put a positive number as amount.")
            await interaction.followup.send(embed=embed)
            return None

        item_map = {str(item): item for item in Item if ItemEntity.to_entity(item).purchasable}
        try:
            item = item_map[item_name.casefold()]
        except KeyError:
            items = [str(item) for item in Item if ItemEntity.to_entity(item).purchasable]
            close_matches = regex_autocomplete(item_name, items)

            if close_matches:
                embed = create_error_embed(interaction, f"That item is not in the shop, did you mean `{close_matches[0]}`?")
                await interaction.followup.send(embed=embed)
                return None
            else:
                embed = create_error_embed(interaction, "That item is not in the shop, please take a look at </item shop:1071353123051941898> to view all available items.")
                await interaction.followup.send(embed=embed)
                return None

        item_entity = ItemEntity.to_entity(item)
        assert item_entity.price
        base_price = item_entity.price

        assert isinstance(interaction.user, discord.Member)
        if is_patreon(interaction.user):
            base_price -= base_price * 0.2
            base_price = round(base_price)

        total_price = item_entity.price*amount_to_buy

        psql_user = psql.User(self.bot.pool, interaction.user.id)
        psql_user_table = await psql_user.get_table()

        psql_levels_table = await psql_user.levels.get_table()
        assert psql_levels_table

        required_level = 5
        if psql_levels_table.current_level < required_level:
            embed = create_error_embed(interaction, f"You must be at least **level {required_level}** in-order to purchase from the shop.")
            await interaction.followup.send(embed=embed)
            return None

        if psql_user_table is None:
            balance = "`[Not Registered]`"
            backpack_level = 1
        else:
            balance = self._display_balance(psql_user_table)
            backpack_level = psql_user_table.backpack_level

        item_name = item.title()
        if item is Item.backpack_upgrade:
            if backpack_level == 5:
                embed = create_error_embed(interaction, "Your backpack is already at maximum level.")
                await interaction.followup.send(embed=embed)
                return None

            amount_to_buy = 1
            base_price = float("inf")
            total_price = _calculate_backpack_upgrade_price(backpack_level)
            item_name = f"{item.title()} (Lvl. {backpack_level+1})"

        assert item_entity.currency
        currency = item_entity.currency
        
        item_text = f"• {item.display()} `x{amount_to_buy}`\n>> {currency.to_emoji()} {base_price:,}"
        embed = create_warning_embed(interaction, f"**Your balance:**\n{balance}\n\nAre you sure you want to buy this item?\n{item_text}\n\n**It will cost:**\n>> {currency.to_emoji()} {total_price:,}")

        assert isinstance(interaction.user, discord.Member)
        view = Confirm(interaction.user)
        message = await interaction.followup.send(embed=embed, view=view, wait=True)
        await wait_for_confirmation(
            interaction,
            view,
            message,
            _confirm_item_buy,
            interaction=interaction,
            message=message,
            psql_user=psql_user,
            psql_user_table=psql_user_table,
            item=item,
            item_entity=item_entity,
            currency=currency,
            total_price=total_price,
            amount_to_buy=amount_to_buy,
            backpack_level=backpack_level
        )

    @item_group.command(name="use", description="Use an item in your inventory")
    @app_commands.rename(item_name="item")
    @app_commands.describe(item_name="The name of the item you want to use; case-insensitive")
    @app_commands.autocomplete(item_name=_item_use_autocomplete)
    async def item_use(self, interaction: discord.Interaction, item_name: str):
        await interaction.response.defer(thinking=True)

        item_map = {str(item): item for item in Item if ItemEntity.to_entity(item).usable}
        try:
            item = item_map[item_name.casefold()]
        except KeyError:
            items = [str(item) for item in Item if ItemEntity.to_entity(item).usable]
            close_matches = regex_autocomplete(item_name, items)

            if close_matches:
                embed = create_error_embed(interaction, f"That item either doesn't exist or it is unusable, did you mean `{close_matches[0]}`?")
                await interaction.followup.send(embed=embed)
                return None
            else:
                embed = create_error_embed(interaction, "Either that item doesn't exist or it is unusable.")
                await interaction.followup.send(embed=embed)
                return None

        psql_user = psql.User(self.bot.pool, interaction.user.id)

        item_result = await psql_user.inventory.get_item(item)
        if item_result is None:
            embed = create_error_embed(interaction, f"I couldn't find any {item.display()} in your inventory.")
            await interaction.followup.send(embed=embed)
            return None

        amount_to_use = 1
        if item_result.amount < amount_to_use:
            embed = create_error_embed(interaction, f"You currently don't have enough {item.display()} in your inventory.")
            await interaction.followup.send(embed=embed)
            return None

        embed = create_warning_embed(interaction, f"Are you sure you want to use this item?\n• {item.display()} `x{amount_to_use}`")
        assert isinstance(interaction.user, discord.Member)
        view = Confirm(interaction.user)
        
        message = await interaction.followup.send(embed=embed, view=view, wait=True)
        await wait_for_confirmation(
            interaction,
            view,
            message,
            _confirm_item_use,
            interaction=interaction,
            psql_user=psql_user,
            message=message,
            item=item,
            amount_to_use=amount_to_use
        )

    @item_group.command(name="info", description="View information about an item")
    @app_commands.rename(item_name="item")
    @app_commands.describe(item_name="The name of the item you want to view the info of; case-insensitive")
    @app_commands.autocomplete(item_name=_item_info_autocomplete)
    async def item_info(self, interaction: discord.Interaction, item_name: str):
        await interaction.response.defer(thinking=True)

        item_map = {str(item): item for item in Item}
        try:
            item = item_map[item_name.casefold()]
        except KeyError:
            items = [str(item) for item in Item]
            close_matches = regex_autocomplete(item_name, items)

            if close_matches:
                embed = create_error_embed(interaction, f"That item doesn't exist, did you mean `{close_matches[0]}`?")
                await interaction.followup.send(embed=embed)
                return None
            else:
                embed = create_error_embed(interaction, "That item doesn't exist.")
                await interaction.followup.send(embed=embed)
                return None

        item_entity = ItemEntity.to_entity(item)
        embed = create_info_embed(interaction, f"{item.display()}\n_{item_entity.description}_")

        embed.add_field(name="Usable:", value=item_entity.usable, inline=False)
        embed.add_field(name="Purchasable:", value=item_entity.purchasable, inline=False)

        if item_entity.purchasable:
            assert item_entity.currency

            if item_entity.name == str(Item.backpack_upgrade):
                psql_user_table = await psql.User(self.bot.pool, interaction.user.id).get_table()
                backpack_level = psql_user_table.backpack_level if psql_user_table is not None else 1
                price = _calculate_backpack_upgrade_price(backpack_level)
                embed.add_field(name=f"Price (Lvl. {backpack_level+1}):", value=f"{item_entity.currency.to_emoji()} {price:,}")
            else:
                embed.add_field(name="Price:", value=f"{item_entity.currency.to_emoji()} {item_entity.price:,}")
        
        embed.add_field(name="Shown in Inventory:", value=item_entity.visible, inline=False)
        
        await interaction.followup.send(embed=embed)

    @item_group.command(name="recycle", description="Recycle an item for half of its original price")
    @app_commands.rename(item_name="item", amount_to_recycle="amount")
    @app_commands.describe(
        item_name="The name of the item you want to recycle; case-insensitive",
        amount_to_recycle="The amount of the item you want to recycle"
    )
    @app_commands.autocomplete(item_name=_item_recycle_autocomplete)
    async def item_recycle(self, interaction: discord.Interaction, item_name: str, amount_to_recycle: int = 1):
        await interaction.response.defer(thinking=True)

        item_map = {str(item): item for item in Item if ItemEntity.to_entity(item).visible}
        try:
            item = item_map[item_name.casefold()]
        except KeyError:
            items = [str(item) for item in Item if ItemEntity.to_entity(item).visible]
            close_matches = regex_autocomplete(item_name, items)

            if close_matches:
                embed = create_error_embed(interaction, f"That item doesn't exist, did you mean `{close_matches[0]}`?")
                await interaction.followup.send(embed=embed)
                return None
            else:
                embed = create_error_embed(interaction, "That item doesn't exist.")
                await interaction.followup.send(embed=embed)
                return None

        if amount_to_recycle < 1:
            embed = create_error_embed(interaction, "Please put a positive number as amount.")
            await interaction.followup.send(embed=embed)
            return None

        item_entity = ItemEntity.to_entity(item)
        if item_entity.purchasable:
            assert item_entity.price
            total_price = (item_entity.price // 2)*amount_to_recycle if item_entity.price > 1 else amount_to_recycle
            currency = item_entity.currency
            assert currency
        else:
            total_price = 0
            currency = Currency.silver

        psql_user = psql.User(self.bot.pool, interaction.user.id)

        item_result = await psql_user.inventory.get_item(item)
        if item_result is None:
            embed = create_error_embed(interaction, f"I couldn't find any {item.display()} in your inventory.")
            await interaction.followup.send(embed=embed)
            return None

        if item_result.amount < amount_to_recycle:
            embed = create_error_embed(interaction, f"You currently don't have enough {item.display()} in your inventory.")
            await interaction.followup.send(embed=embed)
            return None

        embed = create_warning_embed(interaction, f"Are you sure you want to recycle this item?\n• {item.display()} `x{amount_to_recycle}`\n\n**You will receive:**\n{currency.to_emoji()} {total_price:,}")
        assert isinstance(interaction.user, discord.Member)
        view = Confirm(interaction.user)
        
        message = await interaction.followup.send(embed=embed, view=view, wait=True)
        await wait_for_confirmation(
            interaction,
            view,
            message,
            _confirm_item_recycle,
            interaction=interaction,
            psql_user=psql_user,
            message=message,
            item=item,
            amount_to_recycle=amount_to_recycle,
            currency=currency,
            total_price=total_price
        )
                    

async def setup(bot: Fancards) -> None:
    await bot.add_cog(ItemCog(bot))
