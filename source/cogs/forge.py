from __future__ import annotations

import random
from typing import TYPE_CHECKING, Optional
from io import BytesIO
from math import floor

import discord
from discord import app_commands
from discord.ext import commands
from PIL import Image

from source.app_commands import Group
from source.enums import Condition, SpecialRarity, Item, Fanmoji, Rarity, Currency
from source.entity import CraftableCharacterEntity
from source.cogs.card import CardFactory, CardImage
from source.utils import psql, RARE_FINDS_CHANNEL_ID
from source.utils.psql import CardTable
from source.utils.embed import create_info_embed, create_error_embed, create_success_embed, create_warning_embed, get_card_property_text
from source.utils.view import Confirm, EmbedPaginatorWithConfirm, wait_for_confirmation
from source.utils.autocomplete import card_id_autocomplete, regex_autocomplete, autocomplete_close_matches
from source.utils.cooldown import resettable_cooldown, reset_command_cooldown

if TYPE_CHECKING:
    from bot import Fancards


async def _character_name_autocomplete(interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
    character_names = CraftableCharacterEntity.get_character_names()
    return await autocomplete_close_matches(interaction, current ,character_names)


async def _confirm_forge_upgrade(
    interaction: discord.Interaction,
    psql_user: psql.User,
    message: discord.WebhookMessage,
    upgrade_cost: int,
    card: CardImage,
    new_condition: Condition,
    display_card: Image.Image
):
    item = await psql_user.inventory.get_item(Item.glistening_gem)
    if item is None:
        embed = create_error_embed(interaction, f"You currently don't have any {Item.glistening_gem.display()}")
        await message.edit(embed=embed, view=None, attachments=[])
        return None

    if item.amount < upgrade_cost:
        embed = create_error_embed(interaction, f"You currently don't have enough {Item.glistening_gem.display()}")
        await message.edit(embed=embed, view=None, attachments=[])
        return None
    
    await psql_user.inventory.remove_item(Item.glistening_gem, upgrade_cost)
    await psql_user.cards.change_card_condition(card.card_id, new_condition)

    reward_exp = random.randint(150, 250)
    reward_exp = await psql_user.levels.handle_exp_addition(interaction, reward_exp)

    buffer = BytesIO()
    display_card.save(buffer, format="PNG")
    buffer.seek(0)
    
    embed = create_success_embed(interaction, f"Upgrade successful!\n\nYou gained **{reward_exp}** EXP!")
    embed.set_image(url="attachment://card_upgrade.png")
    await message.edit(embed=embed, view=None)


async def _confirm_forge_fusion(
    interaction: discord.Interaction,
    psql_user: psql.User,
    psql_user_table: psql.UserTable,
    message: discord.WebhookMessage,
    card: CardImage,
    card1: psql.CardTable,
    star_cost: int,
    first_card_id: str,
    second_card_id: str,
) -> None:
    cards_check = await psql_user.cards.get_cards_by_card_id([first_card_id, second_card_id])
    if cards_check is None or len(cards_check) < 2:
        embed = create_error_embed(interaction, "One of the cards you wanted to fuse no longer exists.")
        await message.edit(embed=embed, view=None)
        return None

    if psql_user_table.star < star_cost:
        embed = create_error_embed(interaction, f"You are currently don't have enough {Currency.star.display()}.")
        await message.edit(embed=embed, view=None)
        return None

    await psql_user.set_star(star_cost, subtract=True)
    await psql_user.cards.delete_cards_by_card_id([first_card_id, second_card_id])
    await psql_user.cards.add_card(
        CardTable(
            card.card_id,
            card1.owner_id,
            card.rarity,
            card.condition,
            card.special_rarity,
            card.character_name,
            discord.utils.utcnow()
        )
    )

    reward_exp = random.randint(1, 3) + star_cost / 1.5
    reward_exp = round(reward_exp)
    reward_exp = await psql_user.levels.handle_exp_addition(interaction, reward_exp)

    card_image = CardFactory.add_condition(card.image, card.condition, card.special_rarity)
    buffer = BytesIO()
    card_image.save(buffer, format="PNG")
    buffer.seek(0)

    if card.rarity in [Rarity.common, Rarity.rare, Rarity.legendary, Rarity.mythic]:
        text = f"a _{card.rarity}_ {'_Shiny_ ' if card.special_rarity is SpecialRarity.shiny else ''}**{card.character_name}**"
    else:
        text = f"an _{card.rarity}_ {'_Shiny_ ' if card.special_rarity is SpecialRarity.shiny else ''}**{card.character_name}**"

    embed = create_success_embed(interaction, f"Fusion successful! You received {text} card **`{card.card_id}`** in return.\nIt's in **{card.condition}** condition.\n\nYou gained **{reward_exp}** EXP!")
    file = discord.File(buffer, filename=f"card.png")
    embed.set_image(url="attachment://card.png")
    await message.delete()
    await interaction.followup.send(embed=embed, file=file)


async def _confirm_forge_craft_final(
    interaction: discord.Interaction,
    psql_user: psql.User,
    message: discord.WebhookMessage,
    star_cost: int,
    craftable_character_entity: CraftableCharacterEntity,
    required_cards: list[psql.CardTable],
    character_name: str,
    crafted_card_image: Image.Image,
    crafted_card_table: psql.CardTable
) -> None:
    # check player's inventory to make sure they still have the required resources
    for required_character, required_amount in craftable_character_entity.required_characters.items():
        owned_cards = await psql_user.cards.get_cards_by_character_name(required_character)

        if owned_cards is None:
            reset_command_cooldown(interaction)
            embed = create_error_embed(interaction, f"You are currently missing `x{required_amount}` **{required_character}** cards.")
            await message.edit(embed=embed, view=None, attachments=[])
            return None
        
        owned_cards = [card for card in owned_cards if not card.locked]
        
        if (owned_characters_count := len(owned_cards)) < required_amount:
            reset_command_cooldown(interaction)
            embed = create_error_embed(interaction, f"You are currently missing `x{required_amount - owned_characters_count}` **{required_character}** cards.")
            await message.edit(embed=embed, view=None, attachments=[])
            return None
        
    for required_item, required_amount in craftable_character_entity.required_items.items():
        item = await psql_user.inventory.get_item(required_item)
        if item is None:
            reset_command_cooldown(interaction)
            embed = create_error_embed(interaction, f"You are currently missing {required_item.display()} `x{required_amount}`")
            await message.edit(embed=embed, view=None, attachments=[])
            return None

        if item.amount < required_amount:
            reset_command_cooldown(interaction)
            embed = create_error_embed(interaction, f"You are currently missing {required_item.display()} `x{required_amount - item.amount}`")
            await message.edit(embed=embed, view=None, attachments=[])
            return None
        
    for required_item, required_amount in craftable_character_entity.required_items.items():
        await psql_user.inventory.remove_item(required_item, required_amount)

    await psql_user.set_star(star_cost, subtract=True)
    await psql_user.cards.delete_cards_by_card_id([card.card_id for card in required_cards])

    await psql_user.cards.add_card(crafted_card_table)

    buffer = BytesIO()
    crafted_card_image.save(buffer, format="PNG")
    buffer.seek(0)
    file = discord.File(buffer, filename="crafted_card.png")

    card_properties_text = f"\n{get_card_property_text(crafted_card_table.card_id, crafted_card_table.rarity, crafted_card_table.condition, crafted_card_table.special_rarity, crafted_card_table.character_name)}"
    embed = create_success_embed(interaction, f"You crafted a **{character_name}** card!\n{card_properties_text}")
    embed.set_image(url="attachment://crafted_card.png")

    await message.delete()
    await interaction.followup.send(embed=embed, file=file)

    if crafted_card_table.rarity is Rarity.nightmare or crafted_card_table.special_rarity is SpecialRarity.shiny:
        bot: Fancards = interaction.client  # type: ignore
        rare_finds_channel = bot.get_channel(RARE_FINDS_CHANNEL_ID)
        assert isinstance(rare_finds_channel, discord.TextChannel)

        buffer = BytesIO()
        crafted_card_image.save(buffer, format="PNG")
        buffer.seek(0)

        file = discord.File(buffer, filename="crafted_card.png")
        embed.description = f"**{interaction.user.display_name}** crafted a **{character_name}** card!"
        embed.set_image(url="attachment://crafted_card.png")

        await rare_finds_channel.send(embed=embed, file=file)


async def _confirm_forge_craft(
    interaction: discord.Interaction,
    psql_user: psql.User,
    psql_user_table: psql.UserTable,
    message: discord.WebhookMessage,
    star_cost: int,
    craftable_character_entity: CraftableCharacterEntity,
    required_cards: list[psql.CardTable],
    character_name: str
) -> None:
    if psql_user_table.star < star_cost:
        reset_command_cooldown(interaction)
        embed = create_error_embed(interaction, f"You currently don't have enough {Currency.star.display()}.")
        await message.edit(embed=embed, view=None)
        return None
    
    for required_character, required_amount in craftable_character_entity.required_characters.items():
        owned_cards = await psql_user.cards.get_cards_by_character_name(required_character)

        if owned_cards is None:
            reset_command_cooldown(interaction)
            embed = create_error_embed(interaction, f"You are currently missing `x{required_amount}` **{required_character}** cards.")
            await message.edit(embed=embed, view=None, attachments=[])
            return None
        
        owned_cards = [card for card in owned_cards if not card.locked]
        
        if (owned_characters_count := len(owned_cards)) < required_amount:
            reset_command_cooldown(interaction)
            embed = create_error_embed(interaction, f"You are currently missing `x{required_amount - owned_characters_count}` **{required_character}** cards.")
            await message.edit(embed=embed, view=None, attachments=[])
            return None
        
        for i in range(required_amount):
            required_cards.append(owned_cards[i])
        
    for required_item, required_amount in craftable_character_entity.required_items.items():
        item = await psql_user.inventory.get_item(required_item)

        if item is None:
            reset_command_cooldown(interaction)
            embed = create_error_embed(interaction, f"You are currently missing {required_item.display()} `x{required_amount}`")
            await message.edit(embed=embed, view=None, attachments=[])
            return None

        if item.amount < required_amount:
            reset_command_cooldown(interaction)
            embed = create_error_embed(interaction, f"You are currently missing {required_item.display()} `x{required_amount - item.amount}`")
            await message.edit(embed=embed, view=None, attachments=[])
            return None
        
    average_card_condition_value = sum([card.condition.level for card in required_cards]) / len(required_cards)
    condition_map = {
        Condition.damaged.level: Condition.damaged,
        Condition.poor.level: Condition.poor,
        Condition.good.level: Condition.good,
        Condition.near_mint.level: Condition.near_mint,
        Condition.mint.level: Condition.mint,
        Condition.pristine.level: Condition.pristine
    }
    condition = condition_map[floor(average_card_condition_value)]
    
    # second confirmation prompt
    assert isinstance(interaction.user, discord.Member)
    view = Confirm(interaction.user)

    assert isinstance(interaction.user, discord.Member)
    card_id = CardFactory.generate_card_id()
    rarity = craftable_character_entity.rarity
    name = craftable_character_entity.name
    special_rarity = CardFactory.generate_special_rarity(interaction.user)
    crafted_card_image = CardFactory.build_card(card_id, rarity, condition, special_rarity, name)

    crafted_card_table = CardTable(
        card_id=card_id,
        owner_id=psql_user_table.id,
        rarity=rarity,
        condition=condition,
        special_rarity=special_rarity,
        character_name=name,
        created_at=discord.utils.utcnow()
    )

    embed = create_warning_embed(interaction, f"Are you sure you want to craft this card?\nIts condition will be **{condition}**!")
    await message.delete()
    message = await interaction.followup.send(embed=embed, view=view, wait=True)
    await wait_for_confirmation(
        interaction,
        view,
        message,
        _confirm_forge_craft_final,
        interaction=interaction,
        psql_user=psql_user,
        message=message,
        star_cost=star_cost,
        craftable_character_entity=craftable_character_entity,
        required_cards=required_cards,
        character_name=character_name,
        crafted_card_image=crafted_card_image,
        crafted_card_table=crafted_card_table
    )


class Forge(commands.Cog):
    def __init__(self, bot: Fancards):
        self.bot = bot
        self.log = bot.log

    forge_group = Group(name="forge", description="Forge related commands")

    @forge_group.command(name="upgrade", description="Upgrade the condition of a card")
    @app_commands.rename(card_id="card-id")
    @app_commands.describe(card_id="The ID of the card you wish to upgrade")
    @app_commands.autocomplete(card_id=card_id_autocomplete)
    async def forge_upgrade(self, interaction: discord.Interaction, card_id: Optional[str] = None):
        await interaction.response.defer(thinking=True)

        psql_user = psql.User(self.bot.pool, interaction.user.id)
        psql_user_table = await psql_user.get_table()
        assert psql_user_table
        
        if card_id is None:
            card = await psql_user.cards.get_most_recently_obtained_card()
        else:
            card = await psql_user.cards.get_card(card_id)

        if card is None:
            embed = create_error_embed(interaction, f"I couldn't find any card with the ID **`{card_id}`**.")
            await interaction.followup.send(embed=embed)
            return None

        if card.condition is Condition.pristine:
            embed = create_error_embed(interaction, "Your card is already in **pristine** condition.")
            await interaction.followup.send(embed=embed)
            return None

        if card.owner_id != psql_user_table.id:
            embed = create_error_embed(interaction, "You can only upgrade cards you own.")
            await interaction.followup.send(embed=embed)
            return None

        card = CardImage(
            image=Image.open(f"source/assets/cards/{card.rarity}.png"),
            rarity=card.rarity,
            condition=card.condition,
            special_rarity=card.special_rarity,
            character_name=card.character_name,
            card_id=card.card_id,
            has_sleeve=card.has_sleeve
        )

        new_condition = CardFactory.upgrade(card.condition)
        display_card = CardFactory.display_card_side_by_side_condition(card, card.condition, new_condition)
        assert isinstance(interaction.user, discord.Member)
        view = Confirm(interaction.user)

        buffer = BytesIO()
        display_card.save(buffer, format="PNG")
        buffer.seek(0)

        upgrade_cost = 1
        if card.special_rarity is SpecialRarity.shiny:
            upgrade_cost = 4

        embed = create_warning_embed(interaction, f"Are you sure you want to upgrade this card?\n\n**It will cost:**\n{Fanmoji.glistening_gem} `x{upgrade_cost}`\n\n`{card.condition.title()} {card.condition.to_unicode()}` -> `{new_condition.title()} {new_condition.to_unicode()}`")
        file = discord.File(buffer, filename="card_upgrade.png")
        embed.set_image(url="attachment://card_upgrade.png")

        message = await interaction.followup.send(embed=embed, file=file, view=view, wait=True)
        await wait_for_confirmation(
            interaction,
            view,
            message,
            _confirm_forge_upgrade,
            interaction=interaction,
            psql_user=psql_user,
            message=message,
            upgrade_cost=upgrade_cost,
            card=card,
            new_condition=new_condition,
            display_card=display_card
        )

    @forge_group.command(name="fusion", description="Fuse two cards together to get a random card of the same rarity")
    @app_commands.rename(first_card_id="first-card", second_card_id="second-card")
    @app_commands.describe(first_card_id="The ID of the first card", second_card_id="The ID of the second card")
    async def forge_fusion(self, interaction: discord.Interaction, first_card_id: str, second_card_id: str):
        await interaction.response.defer(thinking=True)

        psql_user = psql.User(self.bot.pool, interaction.user.id)
        psql_user_table = await psql_user.get_table()

        if psql_user_table is None:
            embed = create_error_embed(interaction, "You are currently not registered.")
            await interaction.followup.send(embed=embed)
            return None

        fusion_crystal = await psql_user.inventory.get_item(Item.fusion_crystal)

        if fusion_crystal is None:
            embed = create_error_embed(interaction, f"I couldn't find any {Item.fusion_crystal.display()} in your inventory.")
            await interaction.followup.send(embed=embed)
            return None
        
        cards = await psql_user.cards.get_cards_by_card_id([first_card_id, second_card_id])

        if cards is None:
            embed = create_error_embed(interaction, "I couldn't find any of the cards you provided.")
            await interaction.followup.send(embed=embed)
            return None

        if len(cards) < 2:
            embed = create_error_embed(interaction, "I couldn't find one of the cards you provided.")
            await interaction.followup.send(embed=embed)
            return None

        card1 = list(cards)[0]
        card2 = list(cards)[1]

        if card1.owner_id != psql_user_table.id or card2.owner_id != psql_user_table.id:
            embed = create_error_embed(interaction, "You can only fuse cards you own.")
            await interaction.followup.send(embed=embed)
            return None

        if card1.rarity is not card2.rarity:
            embed = create_error_embed(interaction, "Both cards must have the same rarity in-order to be fused.")
            await interaction.followup.send(embed=embed)
            return None

        if (card1.special_rarity is not card2.special_rarity) and card1.special_rarity is SpecialRarity.shiny:
            embed = create_error_embed(interaction, "Both cards must be shiny in-order to be fused.")
            await interaction.followup.send(embed=embed)
            return None

        if card1.rarity in Rarity.get_valuable_rarities():
            embed = create_error_embed(interaction, "Both of these cards are too valuable to be fused.")
            await interaction.followup.send(embed=embed)
            return None

        star_cost = Rarity.to_star(card1.rarity)

        if card1.condition is card2.condition:
            card = CardFactory.generate_card(
                rarity=card1.rarity,
                condition=card1.condition,
                special_rarity=card1.special_rarity,
                amount=1
            )[0]
        else:
            best_condition = max(cards, key=lambda c: c.condition.level).condition
            new_condition = CardFactory.downgrade(best_condition)
            card = CardFactory.generate_card(
                rarity=card1.rarity,
                condition=new_condition,
                special_rarity=card1.special_rarity,
                amount=1
            )[0]

        assert isinstance(interaction.user, discord.Member)
        view = Confirm(interaction.user)

        star_cost = round(star_cost * 2.5) if card1.special_rarity is not SpecialRarity.shiny else star_cost * 20

        card_return_text = f"You will receive a random card of the same rarity in **{card.condition}** condition."
        card1_property_text = get_card_property_text(card1.card_id, card1.rarity, card1.condition, card1.special_rarity, card1.character_name)
        card2_property_text = get_card_property_text(card2.card_id, card2.rarity, card2.condition, card2.special_rarity, card2.character_name)
        card_properties_text = f"{card1_property_text}\n{card2_property_text}"

        embed = create_warning_embed(interaction, f"Are you sure you want to fuse both of these cards?\n{card_return_text}\n\n**It will cost:**\n{Fanmoji.star} {star_cost:,}\n\n{card_properties_text}")
        message = await interaction.followup.send(embed=embed, view=view, wait=True)
        await wait_for_confirmation(
            interaction,
            view,
            message,
            _confirm_forge_fusion,
            interaction=interaction,
            psql_user=psql_user,
            psql_user_table=psql_user_table,
            message=message,
            card=card,
            card1=card1,
            star_cost=star_cost,
            first_card_id=first_card_id,
            second_card_id=second_card_id
        )

    @resettable_cooldown(1, 60)
    @forge_group.command(name="craft", description="Craft a card")
    @app_commands.describe(character_name="The name of the character to craft")
    @app_commands.rename(character_name="character-name")
    @app_commands.autocomplete(character_name=_character_name_autocomplete)
    async def forge_craft(self, interaction: discord.Interaction, character_name: str):
        await interaction.response.defer(thinking=True)

        psql_user = psql.User(self.bot.pool, interaction.user.id)
        psql_user_table = await psql_user.get_table()

        if psql_user_table is None:
            embed = create_error_embed(interaction, "You are currently not registered.")
            await interaction.followup.send(embed=embed)
            return None
        
        try:
            craftable_character_entity = CraftableCharacterEntity.to_entity(character_name)
        except KeyError:
            craftable_characters = CraftableCharacterEntity.get_character_names()
            close_matches = regex_autocomplete(character_name, craftable_characters)

            if len(close_matches) > 0:
                embed = create_error_embed(interaction, f"This character is not craftable, did you mean `{close_matches[0]}`?")
                await interaction.followup.send(embed=embed)
                return None
            else:
                embed = create_error_embed(interaction, "This character is not craftable.")
                await interaction.followup.send(embed=embed)
                return None
            
        required_cards: list[CardTable] = []
        star_cost = Rarity.to_star(craftable_character_entity.rarity)
        star_cost = round(star_cost * 2.5)
        stars = psql_user_table.star

        required_characters = [(character, amount) for character, amount in craftable_character_entity.required_characters.items()]
        required_items = [(item, amount) for item, amount in craftable_character_entity.required_items.items()]
        required_resources = required_characters + required_items

        embeds: list[discord.Embed] = []
        end = 10
        for start in range(0, len(required_resources), 10):
            current_resources = required_resources[start:end]
            end += 10

            resources: list[str] = []
            for resource, amount in current_resources:
                if isinstance(resource, Item):
                    required_item = resource
                    item_owned = await psql_user.inventory.get_item(required_item)

                    item_amount = 0
                    if item_owned is not None:
                        item_amount = item_owned.amount
                    
                    property_text = f"• {required_item.display()} `x{amount}` (`x{item_amount}`)"
                    resources.append(property_text)
                    continue

                required_character = resource
                cards_owned = await psql_user.cards.get_cards_by_character_name(required_character)

                characters_unlocked = 0
                if cards_owned is not None:
                    characters_unlocked = len([card for card in cards_owned if not card.locked])
                    
                property_text = f"• `x{amount}` **{required_character}** card{'s' if amount > 1 else ''} (`x{characters_unlocked}` {Fanmoji.unlocked})"
                resources.append(property_text)

            joined_resources = "\n".join(resources)
            embed = create_info_embed(interaction, f"Crafting this card requires these resources:\n\n• {Fanmoji.star} {star_cost:,} ({stars:,})\n{joined_resources}")
            embeds.append(embed)

        view = EmbedPaginatorWithConfirm(interaction, embeds)
        embed = view.index_page
        message = await interaction.followup.send(embed=embed, view=view, wait=True)
        await wait_for_confirmation(
            interaction,
            view,
            message,
            _confirm_forge_craft,
            interaction=interaction,
            psql_user=psql_user,
            psql_user_table=psql_user_table,
            message=message,
            star_cost=star_cost,
            craftable_character_entity=craftable_character_entity,
            required_cards=required_cards,
            character_name=character_name
        )
            

async def setup(bot: Fancards) -> None:
    await bot.add_cog(Forge(bot))
    