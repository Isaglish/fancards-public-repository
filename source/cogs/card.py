from __future__ import annotations

import random
import string
from math import ceil
from io import BytesIO
from collections import Counter
from typing import TYPE_CHECKING, Optional, Literal, Union
from dataclasses import dataclass

import discord
from discord import app_commands
from discord.ext import commands
from PIL import Image, ImageDraw, ImageChops, ImageFont

from source.app_commands import Group
from source.enums import (
    Item,
    SpecialRarity,
    Rarity,
    Condition,
    Fanmoji,
    BasicWeight,
    PremiumWeight,
    NewUserWeight,
    Character
)
from source.utils import psql, is_patreon, RARE_FINDS_CHANNEL_ID
from source.utils.cooldown import ButtonOnCooldown, resettable_cooldown, reset_command_cooldown, reset_cooldown
from source.utils.view import EmbedPaginator, EmbedPaginatorWithConfirm, Confirm, wait_for_confirmation
from source.utils.embed import (
    create_error_embed,
    create_warning_embed,
    create_info_embed,
    create_success_embed,
    create_custom_embed,
    get_card_property_text
)
from source.utils.time import seconds_to_human, str_to_timedelta
from source.utils.action_logger import ActionLogger
from source.utils.autocomplete import (
    card_id_autocomplete,
    rarity_autocomplete,
    condition_autocomplete,
    character_name_autocomplete,
    regex_autocomplete
)

if TYPE_CHECKING:
    from bot import Fancards

    
WeightT = Union[NewUserWeight, BasicWeight, PremiumWeight]
BALOO_FONT_PATH = "source/assets/Baloo.ttf"


@dataclass
class CardImage:
    image: Image.Image
    rarity: Rarity
    condition: Condition
    special_rarity: SpecialRarity
    character_name: str
    card_id: str
    has_sleeve: bool


class CardFactory:
    @staticmethod
    def generate_rarity(weight: Optional[WeightT] = None) -> Rarity:
        weight_class = weight or BasicWeight
        return random.choices(
            list(weight_class.rarity.keys()),
            list(weight_class.rarity.values())
        )[0]  # type: ignore

    @staticmethod
    def generate_condition(weight: Optional[WeightT] = None) -> Condition:
        weight_class = weight or BasicWeight
        return random.choices(
            list(weight_class.condition.keys()),
            list(weight_class.condition.values())
        )[0]  # type: ignore

    @staticmethod
    def generate_special_rarity(member: Optional[discord.Member] = None, weight: Optional[WeightT] = None) -> SpecialRarity:
        """Generates a `:class:SpecialRarity` depending on the ``weight``,
        provide ``member`` to have it check if it should increase the chances.

        Returns the `:class:SpecialRarity` generated.
        """
        weight_class = weight or BasicWeight

        special_rarity = weight_class.special_rarity
        if member is not None and is_patreon(member):
            special_rarity = {sr: w for (sr, w) in weight_class.special_rarity.value.items()}
            shiny_weight = special_rarity.get(SpecialRarity.shiny, 0.01) * 2
            special_rarity[SpecialRarity.unknown] -= shiny_weight
        
        return random.choices(
            list(special_rarity.keys()),
            list(special_rarity.values())
        )[0]  # type: ignore

    @staticmethod
    def generate_card_id() -> str:
        card_id = string.digits + string.ascii_lowercase + string.digits
        return "".join(random.choices(card_id, k=6))

    @classmethod
    def generate_card(
        cls,
        member: Optional[discord.Member] = None,
        rarity: Optional[Rarity] = None,
        condition: Optional[Condition] = None,
        special_rarity: Optional[SpecialRarity] = None,
        amount: int = 3,
        weight: Optional[WeightT] = None,
        pack: bool = False
    ) -> list[CardImage]:
        """Generates either a random or guaranteed amount of cards by defining rarity, condition, and special_rarity"""
        cards: list[CardImage] = []
        for _ in range(amount):
            card_rarity = rarity or cls.generate_rarity(weight)
            card_condition = condition or cls.generate_condition(weight)
            card_special_rarity = special_rarity or cls.generate_special_rarity(member, weight)

            base_card = Image.open(f"source/assets/cards/{card_rarity}.png")
            base_card, character_name = cls.add_character(base_card, card_rarity)

            card_id = cls.generate_card_id()
            if character_name == "Troll":
                card_id = "7R0115"
            
            base_card = cls.add_id_text(base_card, card_id)

            if pack:
                condition_weight = {
                    Condition.pristine: 10,
                    Condition.mint: 80,
                    Condition.near_mint: 10
                }
                card_condition = random.choices(
                    list(condition_weight.keys()),
                    list(condition_weight.values())
                )[0]

            card = CardImage(
                image=base_card,
                rarity=card_rarity,
                condition=card_condition,
                special_rarity=card_special_rarity,
                character_name=character_name,
                card_id=card_id,
                has_sleeve=False
            )
            cards.append(card)

        return cards

    @staticmethod
    def add_condition(base_card: Image.Image, condition: Condition, special_rarity: SpecialRarity) -> Image.Image:
        """Add condition texture to the ``base_card``"""
        if special_rarity is SpecialRarity.shiny:
            texture = Image.open("source/assets/conditions/shiny.png")

            texture = texture.convert("RGBA").resize(base_card.size)
            transparent_image = Image.new("RGBA", texture.size, (0, 0, 0, 0))
            texture = Image.blend(transparent_image, texture, alpha=0.7)

            base_card = base_card.convert("RGBA")
            base_card = ImageChops.screen(base_card, texture)

        if condition is Condition.mint:
            return base_card  # mint has no texture

        texture = Image.open(f"source/assets/conditions/{condition}.png")

        if condition is Condition.pristine:
            texture = texture.resize(base_card.size)
            return Image.alpha_composite(base_card.convert("RGBA"), texture.convert("RGBA"))

        elif condition is Condition.near_mint:
            base_card = base_card.convert("RGBA")
            texture = texture.resize(base_card.size).convert("RGBA")

            transparent_image = Image.new("RGBA", texture.size, (0, 0, 0, 0))
            texture = Image.blend(transparent_image, texture, alpha=0.5)
            base_card = ImageChops.screen(base_card, texture)
            return base_card

        else:
            texture = texture.resize(base_card.size)
            return ImageChops.screen(base_card.convert("RGBA"), texture.convert("RGBA"))

    @staticmethod
    def add_id_text(base_card: Image.Image, card_id: str) -> Image.Image:
        font = ImageFont.truetype(BALOO_FONT_PATH, 17)
        draw = ImageDraw.Draw(base_card)
        draw.text((37, 510), f"#{card_id}", font=font)  # type: ignore
        return base_card

    @staticmethod
    def add_character_name(base_card: Image.Image, character_name: str) -> Image.Image:
        bound_width = 285
        bound_height = 50
        font_size = 49

        draw = ImageDraw.Draw(base_card)
        font = ImageFont.truetype(BALOO_FONT_PATH, font_size)
        width, height = draw.multiline_textsize(character_name, font=font)

        while width > bound_width:
            font_size -= 1
            font = ImageFont.truetype(BALOO_FONT_PATH, font_size)
            width, height = draw.textbbox((0, 0), character_name, font=font)[2:]

        x = (base_card.width - width) / 2
        y = (900 - height) / 2 + 5

        if height > bound_height:
            y -= 5

        draw.multiline_text((x, y), character_name, font=font)
        return base_card
    
    @classmethod
    def build_card(
        cls,
        card_id: str,
        rarity: Rarity,
        condition: Condition,
        special_rarity: SpecialRarity,
        character_name: str
    ) -> Image.Image:
        """Completely builds a card.

        Returns the image of the card that was built.
        """
        base_card = Image.open(f"source/assets/cards/{rarity}.png")
        base_card, _ = cls.add_character(base_card, rarity, character_name)
        base_card = cls.add_id_text(base_card, card_id)
        base_card = cls.add_character_name(base_card, character_name)
        base_card = cls.add_condition(base_card, condition, special_rarity)
        
        return base_card

    @classmethod
    def add_character(cls, base_card: Image.Image, rarity: Rarity, character_name: Optional[str] = None) -> tuple[Image.Image, str]:
        if character_name is None:
            character_rarity = rarity
            character_name = Character.get_random_character(rarity)
        else:
            character_rarity = Character.get_character_rarity(character_name)

        character_image = Image.open(f"source/assets/characters/{character_rarity}/{character_name}.png")
        base_card = cls.add_character_name(base_card, character_name)
        base_card.paste(character_image, (0, 0), mask=character_image)
        return (base_card, character_name)

    @staticmethod
    def align_cards(
        card_images: list[Image.Image],
        cards_per_row: int = 3,
        album: bool = False,
        pixel_offset: int = 30
    ) -> Image.Image:
        width = max([card_image.width for card_image in card_images]) + pixel_offset
        height = max([card_image.height for card_image in card_images]) + pixel_offset

        if album:
            page_width = width * cards_per_row
            page_height = height * cards_per_row
        else:
            page_width = width * len(card_images)
            page_width = width * cards_per_row if page_width > width * cards_per_row else page_width
            page_height = height * ceil((1*len(card_images)) / cards_per_row)

        page = Image.new("RGBA", (page_width, page_height), (0, 0, 0, 0))

        row = 0
        column = 0
        for card_image in card_images:
            if column != 0 and column % cards_per_row == 0:
                column = 0
                row += 1

            page.paste(card_image, (width*column, height*row))
            column += 1

        return page

    @staticmethod
    def downgrade(current_condition: Condition) -> Condition:
        """Downgrades a card's condition (e.g. Turn pristine into mint, mint into near mint, and near mint into good.)
        
        Returns the downgraded ``Condition``.
        """
        condition_map = {
            Condition.pristine: Condition.mint,
            Condition.mint: Condition.near_mint,
            Condition.near_mint: Condition.good,
            Condition.good: Condition.poor,
            Condition.poor: Condition.damaged,
            Condition.damaged: Condition.damaged
        }
        return condition_map[current_condition]

    @staticmethod
    def upgrade(current_condition: Condition) -> Condition:
        """Upgrades a card's condition (e.g. Turn damaged into poor, poor into good and good into near mint.)
        
        Returns the upgraded ``Condition``.
        """
        condition_map = {
            Condition.damaged: Condition.poor,
            Condition.poor: Condition.good,
            Condition.good: Condition.near_mint,
            Condition.near_mint: Condition.mint,
            Condition.mint: Condition.pristine,
            Condition.pristine: Condition.pristine
        }
        return condition_map[current_condition]

    @classmethod
    def display_card_side_by_side_condition(cls, card: CardImage, old_condition: Condition, new_condition: Condition) -> Image.Image:
        base_card = card.image
        base_card, _ = cls.add_character(base_card, card.rarity, card.character_name)
        base_card = cls.add_id_text(base_card, card.card_id)
        base_card = cls.add_character_name(base_card, card.character_name)

        original_card = cls.add_condition(base_card, old_condition, card.special_rarity)
        upgraded_card = cls.add_condition(base_card, new_condition, card.special_rarity)
        arrow = Image.open("source/assets/arrow_right.png")

        px_offset = 120
        width = original_card.width + upgraded_card.width + px_offset
        height = max(original_card.height, upgraded_card.height)
        combined_image = Image.new('RGBA', (width, height), (0, 0, 0, 0))

        combined_image.paste(original_card, (0,0))
        combined_image.paste(arrow, ((combined_image.width // 2) - 50, (combined_image.height // 2) - 50))
        combined_image.paste(upgraded_card, (original_card.width + px_offset, 0))
        
        return combined_image
    

async def _confirm_single_card_burn(
    interaction: discord.Interaction,
    message: discord.WebhookMessage,
    total_silver: int,
    total_star: int,
    glistening_gem: int,
    success_text: str,
    card: psql.CardTable
) -> None:
    bot: Fancards = interaction.client  # type: ignore
    psql_user = psql.User(bot.pool, interaction.user.id)

    check_card = await psql_user.cards.get_card(card.card_id)
    if check_card is None:
        embed = create_error_embed(interaction, "The card you wanted to burn doesn't exist anymore.")
        await message.edit(embed=embed, view=None, attachments=[])
        return None
    
    await psql_user.set_silver(total_silver)
    await psql_user.set_star(total_star)

    if card.special_rarity is SpecialRarity.shiny:
        await psql_user.inventory.add_item(Item.glistening_gem, glistening_gem)

    await psql_user.cards.delete_card(card.card_id)

    embed = create_success_embed(
        interaction,
        success_text
    )
    embed.set_thumbnail(url="attachment://card.png")
    await message.edit(embed=embed, view=None)


async def _confirm_multiple_card_burn(
    interaction: discord.Interaction,
    psql_user: psql.User,
    message: discord.WebhookMessage,
    valid_card_ids: list[str],
    total_silver: int,
    total_star: int,
    total_glistening_gem: int,
    success_text: str,
    has_shiny: bool
) -> None:
    check_card = await psql_user.cards.get_cards_by_card_id(valid_card_ids)
    if check_card is None:
        embed = create_error_embed(interaction, "The cards you wanted to burn do not exist anymore.")
        await message.edit(embed=embed, view=None)
        return None
        
    await psql_user.set_silver(total_silver)
    await psql_user.set_star(total_star)

    if has_shiny:
        await psql_user.inventory.add_item(Item.glistening_gem, total_glistening_gem)

    await psql_user.cards.delete_cards_by_card_id(valid_card_ids)

    embed = create_success_embed(interaction, success_text)
    await message.edit(embed=embed, view=None)


async def _confirm_all_card_burn(
    interaction: discord.Interaction,
    psql_user: psql.User,
    message: discord.WebhookMessage,
    valid_card_ids: list[str],
    total_silver: int,
    total_star: int,
    total_glistening_gem: int,
    success_text: str,
    has_shiny: bool
) -> None:
    check_card = await psql_user.cards.get_cards_by_card_id(valid_card_ids)
    if check_card is None or len(check_card) != len(valid_card_ids):
        reset_command_cooldown(interaction)
        embed = create_error_embed(interaction, "Some of the cards you wanted to burn do not exist anymore.")
        await message.edit(embed=embed, view=None)
        return None

    await psql_user.set_silver(total_silver)
    await psql_user.set_star(total_star)

    if has_shiny:
        await psql_user.inventory.add_item(Item.glistening_gem, total_glistening_gem)

    await psql_user.cards.delete_cards_by_card_id(valid_card_ids)

    embed = create_success_embed(interaction, success_text)
    await message.edit(embed=embed, view=None)
    

async def _confirm_card_sleeve(
    interaction: discord.Interaction,
    is_option_add: bool,
    psql_user: psql.User,
    message: discord.WebhookMessage,
    card_id: str
) -> None:
    if is_option_add:
        success_text = f"You've successfully added a {Item.card_sleeve.display()} to your card **`{card_id}`**."
        card_sleeve = await psql_user.inventory.get_item(Item.card_sleeve)
        if card_sleeve is None:
            embed = create_error_embed(interaction, f"I couldn't find any {Item.card_sleeve.display()} in your inventory.")
            await message.edit(embed=embed, view=None, attachments=[])
            return None

        await psql_user.inventory.remove_item(Item.card_sleeve)
    else:
        success_text = f"You've successfully removed a {Item.card_sleeve.display()} from your card **`{card_id}`**.\n\n**You received:**\n• {Item.card_sleeve.display()} `x1`"
        await psql_user.inventory.add_item(Item.card_sleeve)

    await psql_user.cards.invert_has_sleeve(card_id)

    embed = create_success_embed(interaction, success_text)
    embed.set_image(url="attachment://card.png")
    await message.edit(embed=embed, view=None)


def _calculate_card_value(card: psql.CardTable) -> int:
    base_rarity_value = 10000
    multiplier_rarity_value = 5000

    base_condition_value = 500

    if card.rarity is Rarity.exclusive_icicle:
        rarity_level = 9
    else:
        rarity_level = card.rarity.level

    rarity_weight = base_rarity_value + (multiplier_rarity_value*(rarity_level-1))
    condition_weight = base_condition_value*card.condition.level
    special_rarity_weight = 26000 if card.special_rarity is SpecialRarity.shiny else 0

    return rarity_weight + condition_weight + special_rarity_weight


def _filter_card_collection(
    cards: list[psql.CardTable],
    rarity: Optional[str] = None,
    condition: Optional[str] = None,
    character_name: Optional[str] = None,
    card_age: Optional[str] = None,
    locked: Optional[bool] = None,
    card_sleeve: Optional[bool] = None,
    by_card_id: bool = False,
    descending: bool = False
) -> list[psql.CardTable]:
    filtered_cards = cards
    if rarity is not None:
        try:
            rarity_map = {str(r): r for r in Rarity if r not in Rarity.get_exclusive_rarities()}
            _rarity = rarity_map[rarity.casefold()]
            filtered_cards = [card for card in filtered_cards if card.rarity is _rarity]
        except ValueError:
            filtered_cards = cards

    if condition is not None:
        try:
            _condition = Condition(condition)
            filtered_cards = [card for card in filtered_cards if card.condition is _condition]
        except ValueError:
            filtered_cards = cards

    if character_name is not None:
        character_names = [character_name for (character_name, _) in Character.get_characters()]
        character_name = regex_autocomplete(character_name, character_names)[0]
        filtered_cards = [card for card in filtered_cards if card.character_name == character_name and card.character_name in character_names]

    if card_age is not None:
        card_age_delta = str_to_timedelta(card_age)
        if card_age_delta is not None:
            filtered_cards = [card for card in filtered_cards if (discord.utils.utcnow() - card.created_at) < card_age_delta]

    if locked is not None:
        if locked:
            filtered_cards = [card for card in filtered_cards if card.locked]
        else:
            filtered_cards = [card for card in filtered_cards if not card.locked]

    if card_sleeve is not None:
        if card_sleeve:
            filtered_cards = [card for card in filtered_cards if card.has_sleeve]
        else:
            filtered_cards = [card for card in filtered_cards if not card.has_sleeve]

    if by_card_id:
        filtered_cards = sorted(filtered_cards, key=lambda card: card.card_id)
    else:
        filtered_cards = sorted(filtered_cards, key=_calculate_card_value)

    if descending:
        filtered_cards.reverse()

    return filtered_cards


async def _handle_single_card_lock(interaction: discord.Interaction, card: psql.CardTable, lock_option: Literal["lock", "unlock"]):
    bot: Fancards = interaction.client  # type: ignore
    
    if lock_option == "lock" and card.locked:
        embed = create_error_embed(interaction, f"This card **`{card.card_id}`** has already been `locked`.")
        await interaction.followup.send(embed=embed)
        return None

    if lock_option == "unlock" and not card.locked:
        embed = create_error_embed(interaction, f"This card **`{card.card_id}`** has already been `unlocked`.")
        await interaction.followup.send(embed=embed)
        return None

    await psql.Card(bot.pool, interaction.user.id).invert_locked(card.card_id)

    embed = create_success_embed(interaction, f"Your card **`{card.card_id}`** has been `{lock_option}ed`.")
    await interaction.followup.send(embed=embed)


async def _handle_multiple_card_lock(interaction: discord.Interaction, cards: list[psql.CardTable], lock_option: Literal["lock", "unlock"]):
    bot: Fancards = interaction.client  # type: ignore
    
    psql_user_table = await psql.User(bot.pool, interaction.user.id).get_table()
    assert psql_user_table
    
    for card in cards:
        if (lock_option == "lock" and card.locked) or (lock_option == "unlock" and not card.locked):
            continue

        if card.owner_id != psql_user_table.id:
            continue

        await psql.Card(bot.pool, interaction.user.id).invert_locked(card.card_id)

    embed = create_success_embed(interaction, f"The cards you provided has been `{lock_option}ed`.")
    await interaction.followup.send(embed=embed)


async def _handle_card_lock(interaction: discord.Interaction, lock_option: Literal["lock", "unlock"], card_ids: Optional[str] = None):
    bot: Fancards = interaction.client  # type: ignore
    psql_user = psql.User(bot.pool, interaction.user.id)

    psql_user_table = await psql_user.get_table()
    assert psql_user_table

    if card_ids is None:
        recent_card = await psql_user.cards.get_most_recently_obtained_card()

        if recent_card is None:
            embed = create_error_embed(interaction, "You currently don't own any cards.")
            await interaction.followup.send(embed=embed)
            return None

        await _handle_single_card_lock(interaction, recent_card, lock_option)
        return None

    filtered_card_ids = list(filter(lambda x: x, [card_id.strip() for card_id in card_ids.split(" ")]))
    if len(filtered_card_ids) == 1:
        card = await psql_user.cards.get_card(filtered_card_ids[0])

        if card is None:
            embed = create_error_embed(interaction, f"I couldn't find any card with the ID `{filtered_card_ids[0]}`.")
            await interaction.followup.send(embed=embed)
            return None

        if card.owner_id != psql_user_table.id:
            embed = create_error_embed(interaction, f"You can only lock cards you own.")
            await interaction.followup.send(embed=embed)
            return None

        await _handle_single_card_lock(interaction, card, lock_option)

    if len(filtered_card_ids) > 1:
        card_id_count = Counter(filtered_card_ids)
        if [item for item, count in card_id_count.items() if count > 1]:
            embed = create_error_embed(interaction, "Please don't duplicate your card IDs.")
            await interaction.followup.send(embed=embed)
            return None

        cards = await psql_user.cards.get_cards_by_card_id(filtered_card_ids)

        if not cards:
            embed = create_error_embed(interaction, f"I couldn't find any cards with the IDs you provided.")
            await interaction.followup.send(embed=embed)
            return None

        await _handle_multiple_card_lock(interaction, list(cards), lock_option)


async def _handle_card_sleeve(interaction: discord.Interaction, option: Literal["add", "remove"], card_id: Optional[str] = None) -> None:
    bot: Fancards = interaction.client  # type: ignore
    
    psql_user = psql.User(bot.pool, interaction.user.id)
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
    
    is_option_add = option == "add"
    if is_option_add:
        unowned_error_text = "You can only add sleeves to cards you own."
        confirmation_text = f"Are you sure you want to add a sleeve to this card?\n\n**It will require:**\n• {Item.card_sleeve.display()} `x1`"

        if card.has_sleeve:
            embed = create_error_embed(interaction, "This card already has a sleeve.")
            await interaction.followup.send(embed=embed)
            return None
        
    else:
        unowned_error_text = "You can only remove sleeves from cards you own."
        confirmation_text = f"Are you sure you want to remove this card's sleeve?\n\n**You will receive:**\n• {Item.card_sleeve.display()} `x1`"

        if not card.has_sleeve:
            embed = create_error_embed(interaction, "This card does not have a sleeve.")
            await interaction.followup.send(embed=embed)
            return None

    card_id = card_id or card.card_id

    if card.owner_id != psql_user_table.id:
        embed = create_error_embed(interaction, unowned_error_text)
        await interaction.followup.send(embed=embed)
        return None

    base_card = CardFactory.build_card(
        card_id=card.card_id,
        rarity=card.rarity,
        condition=card.condition,
        special_rarity=card.special_rarity,
        character_name=card.character_name
    )
    buffer = BytesIO()
    base_card.save(buffer, format="PNG")
    buffer.seek(0)

    assert isinstance(interaction.user, discord.Member)
    view = Confirm(interaction.user)

    embed = create_warning_embed(interaction, confirmation_text)

    file = discord.File(buffer, filename="card.png")
    embed.set_image(url="attachment://card.png")

    message = await interaction.followup.send(embed=embed, view=view, file=file, wait=True)
    await wait_for_confirmation(
        interaction,
        view,
        message,
        _confirm_card_sleeve,
        interaction=interaction,
        is_option_add=is_option_add,
        psql_user=psql_user,
        message=message,
        card_id=card_id
    )


async def _handle_single_card_burn(interaction: discord.Interaction, card: psql.CardTable):
    base_card = CardFactory.build_card(
        card_id=card.card_id,
        rarity=card.rarity,
        condition=card.condition,
        special_rarity=card.special_rarity,
        character_name=card.character_name
    )
    buffer = BytesIO()
    base_card.save(buffer, format="PNG")
    buffer.seek(0)

    file = discord.File(buffer, filename="card.png")
    card_properties_text = f"\n{get_card_property_text(card.card_id, card.rarity, card.condition, card.special_rarity, card.character_name, has_sleeve=card.has_sleeve)}"

    if card.rarity in Rarity.get_valuable_rarities():
        reset_command_cooldown(interaction)
        embed = create_error_embed(interaction, f"This is an unburnable card since it is too valuable.{card_properties_text}")
        embed.set_thumbnail(url="attachment://card.png")
        await interaction.followup.send(embed=embed, file=file)
        return None

    if card.locked:
        reset_command_cooldown(interaction)
        embed = create_error_embed(interaction, "You can't burn this card since it is `locked`.")
        embed.set_thumbnail(url="attachment://card.png")
        await interaction.followup.send(embed=embed, file=file)
        return None

    rarity_to_silver = random.randint(*card.rarity.to_silver())

    days = (discord.utils.utcnow() - card.created_at).days
    days = min(days, 60)

    additional_silver_per_day = sum([rarity_to_silver // 4 for _ in range(days)])
    additional_star_per_day = sum([card.condition.to_star() // 4 for _ in range(days)])
    total_silver = rarity_to_silver + additional_silver_per_day
    total_star = card.condition.to_star() + additional_star_per_day
    glistening_gem = 1

    assert isinstance(interaction.user, discord.Member)
    view = Confirm(author=interaction.user)

    if card.special_rarity is SpecialRarity.shiny:
        embed = create_warning_embed(interaction, f"Are you sure you wanna burn this card?\n\n**You will receive:**\n{Fanmoji.silver} {total_silver:,}\n{Fanmoji.star} {total_star:,}\n{Fanmoji.glistening_gem} `x{glistening_gem}`\n{card_properties_text}")
        success_text = f"Burning successful! You received:\n{Fanmoji.silver} {total_silver:,}\n{Fanmoji.star} {total_star:,}\n{Fanmoji.glistening_gem} `x{glistening_gem}`"
    else:
        embed = create_warning_embed(interaction, f"Are you sure you wanna burn this card?\n\n**You will receive:**\n{Fanmoji.silver} {total_silver:,}\n{Fanmoji.star} {total_star:,}\n{card_properties_text}")
        success_text = f"Burning successful! You received:\n{Fanmoji.silver} {total_silver:,}\n{Fanmoji.star} {total_star:,}"

    embed.set_thumbnail(url="attachment://card.png")
    
    message = await interaction.followup.send(embed=embed, file=file, view=view, wait=True)
    await wait_for_confirmation(
        interaction,
        view,
        message,
        _confirm_single_card_burn,
        interaction=interaction,
        message=message,
        total_silver=total_silver,
        total_star=total_star,
        glistening_gem=glistening_gem,
        success_text=success_text,
        card=card
    )


async def _handle_multiple_card_burn(interaction: discord.Interaction, cards: list[psql.CardTable]):
    bot: Fancards = interaction.client  # type: ignore
    
    total_items: list[list[str]] = []
    valid_card_ids: list[str] = []
    invalid_card_count = 0

    psql_user = psql.User(bot.pool, interaction.user.id)

    psql_user_table = await psql_user.get_table()
    assert psql_user_table

    end = 10
    for start in range(0, len(cards), 10):
        current_cards = cards[start:end]
        end += 10

        items: list[str] = []
        for card in current_cards:
            card_properties_text = f"\n{get_card_property_text(card.card_id, card.rarity, card.condition, card.special_rarity, card.character_name, has_sleeve=card.has_sleeve)}"

            if card.rarity in Rarity.get_valuable_rarities():
                card_properties_text += " `[Too Valuable]`"
                invalid_card_count += 1
                items.append(card_properties_text)
                continue

            if card.owner_id != psql_user_table.id:
                card_properties_text += " `[Not Owned]`"
                items.append(card_properties_text)
                invalid_card_count += 1
                continue

            if card.locked:
                card_properties_text += " `[Locked]`"
                items.append(card_properties_text)
                invalid_card_count += 1
                continue

            valid_card_ids.append(card.card_id)
            items.append(card_properties_text)

        total_items.append(items)

    total_silver = 0
    total_star = 0
    total_glistening_gem = 0
    has_shiny = False
    for card in cards:
        if card.card_id not in valid_card_ids:
            continue

        rarity_to_silver = random.randint(*card.rarity.to_silver())

        days = (discord.utils.utcnow() - card.created_at).days
        days = min(days, 60)

        additional_silver_per_day = sum([rarity_to_silver // 4 for _ in range(days)])
        additional_star_per_day = sum([card.condition.to_star() // 4 for _ in range(days)])
        total_silver += rarity_to_silver + additional_silver_per_day
        total_star += card.condition.to_star() + additional_star_per_day

        if card.special_rarity is SpecialRarity.shiny:
            total_glistening_gem += 1
            has_shiny = True

    embeds: list[discord.Embed] = []
    for item in total_items:
        item = "".join(item)
        if has_shiny:
            embed = create_warning_embed(
                interaction,
                f"Are you sure you wanna burn these cards?\nBurnable cards: `x{len(cards) - invalid_card_count}`\n\n**You will receive:**\n{Fanmoji.silver} {total_silver:,}\n{Fanmoji.star} {total_star:,}\n{Fanmoji.glistening_gem} `x{total_glistening_gem}`\n{item}"
            )
        else:
            embed = create_warning_embed(
                interaction,
                f"Are you sure you wanna burn these cards?\nBurnable cards: `x{len(cards) - invalid_card_count}`\n\n**You will receive:**\n{Fanmoji.silver} {total_silver:,}\n{Fanmoji.star} {total_star:,}\n{item}"
            )
        embeds.append(embed)

    assert isinstance(interaction.user, discord.Member)

    if invalid_card_count == len(cards):
        reset_command_cooldown(interaction)
        embed = create_error_embed(interaction, "The cards you provided cannot be burned.")
        await interaction.followup.send(embed=embed)
        return None

    view = EmbedPaginatorWithConfirm(interaction=interaction, embeds=embeds)

    if has_shiny:
        success_text = f"Burning successful! You received:\n{Fanmoji.silver} {total_silver:,}\n{Fanmoji.star} {total_star:,}\n{Fanmoji.glistening_gem} `x{total_glistening_gem}`"
    else:
        success_text = f"Burning successful! You received:\n{Fanmoji.silver} {total_silver:,}\n{Fanmoji.star} {total_star:,}"

    embed = view.index_page
    message = await interaction.followup.send(embed=embed, view=view, wait=True)
    await wait_for_confirmation(
        interaction,
        view,
        message,
        _confirm_multiple_card_burn,
        interaction=interaction,
        psql_user=psql_user,
        message=message,
        valid_card_ids=valid_card_ids,
        total_silver=total_silver,
        total_star=total_star,
        total_glistening_gem=total_glistening_gem,
        success_text=success_text,
        has_shiny=has_shiny
    )


async def _handle_all_card_burn(interaction: discord.Interaction) -> None:
    bot: Fancards = interaction.client  # type: ignore
    
    psql_user = psql.User(bot.pool, interaction.user.id)

    cards = await psql_user.cards.get_cards()
    if cards is None:
        embed = create_error_embed(interaction, "You currently don't own any cards.")
        await interaction.followup.send(embed=embed)
        return None

    total_silver = 0
    total_star = 0
    total_glistening_gem = 0
    has_shiny = False
    invalid_card_count = 0
    valid_card_ids: list[str] = []
    for card in cards:
        if card.locked:
            continue

        if card.rarity in Rarity.get_valuable_rarities():
            invalid_card_count += 1
            continue

        rarity_to_silver = random.randint(*card.rarity.to_silver())

        days = (discord.utils.utcnow() - card.created_at).days
        days = min(days, 60)

        additional_silver_per_day = sum([rarity_to_silver // 4 for _ in range(days)])
        additional_star_per_day = sum([card.condition.to_star() // 4 for _ in range(days)])
        total_silver += rarity_to_silver + additional_silver_per_day
        total_star += card.condition.to_star() + additional_star_per_day

        if card.special_rarity is SpecialRarity.shiny:
            total_glistening_gem += 1
            has_shiny = True

        valid_card_ids.append(card.card_id)

    if has_shiny:
        embed = create_warning_embed(
            interaction,
            f"Are you sure you wanna burn all your cards except the locked ones?\nBurnable cards: `x{len(valid_card_ids)}`\n\n**You will receive:**\n{Fanmoji.silver} {total_silver:,}\n{Fanmoji.star} {total_star:,}\n{Fanmoji.glistening_gem} `x{total_glistening_gem}`"
        )
    else:
        embed = create_warning_embed(
            interaction,
            f"Are you sure you wanna burn all your cards except the locked ones??\nBurnable cards: `x{len(valid_card_ids)}`\n\n**You will receive:**\n{Fanmoji.silver} {total_silver:,}\n{Fanmoji.star} {total_star:,}"
        )

    assert isinstance(interaction.user, discord.Member)

    if invalid_card_count == len(cards):
        reset_command_cooldown(interaction)
        embed = create_error_embed(interaction, "The cards you provided cannot be burned.")
        await interaction.followup.send(embed=embed)
        return None

    view = Confirm(author=interaction.user)

    if has_shiny:
        success_text = f"Burning successful! You received:\n{Fanmoji.silver} {total_silver:,}\n{Fanmoji.star} {total_star:,}\n{Fanmoji.glistening_gem} `x{total_glistening_gem}`"
    else:
        success_text = f"Burning successful! You received:\n{Fanmoji.silver} {total_silver:,}\n{Fanmoji.star} {total_star:,}"

    message = await interaction.followup.send(embed=embed, view=view, wait=True)
    await wait_for_confirmation(
        interaction,
        view,
        message,
        _confirm_all_card_burn,
        interaction=interaction,
        psql_user=psql_user,
        message=message,
        valid_card_ids=valid_card_ids,
        total_silver=total_silver,
        total_star=total_star,
        total_glistening_gem=total_glistening_gem,
        success_text=success_text,
        has_shiny=has_shiny
    )


async def _paginate_card_collection(
    interaction: discord.Interaction,
    cards: list[psql.CardTable],
    card_count: int,
    user: discord.Member | discord.User,
    card_limit: Optional[int] = None
) -> None:
    
    filtered_cards_count = len(cards)
    embeds: list[discord.Embed] = []
    end = 10
    for start in range(0, filtered_cards_count, 10):
        current_cards = cards[start:end]
        end += 10

        items: list[str] = []
        for card in current_cards:
            card_property_text = get_card_property_text(
                card.card_id,
                card.rarity,
                card.condition,
                card.special_rarity,
                card.character_name,
                card.has_sleeve,
                card.locked
            )
            items.append(card_property_text)

        joined_items = "\n".join(items)
        card_count_text = f"Total cards: `x{card_count:,}`/`{card_limit:,}`" if card_limit is not None else f"Total cards: `x{card_count:,}`"

        if filtered_cards_count != card_count:
            card_count_text += f"\nFiltered cards: `x{filtered_cards_count:,}`"
        
        embed = create_info_embed(
            interaction,
            f"Viewing the card collection of {user.mention}.\n{card_count_text}\n\n{joined_items}"
        )
        embeds.append(embed)

    paginator = EmbedPaginator(interaction, embeds)
    embed = paginator.index_page
    await interaction.followup.send(embed=embed, view=paginator)


async def _paginate_character_count(
    interaction: discord.Interaction,
    cards: list[psql.CardTable],
    user: discord.Member | discord.User,
    card_limit: Optional[int] = None,
    descending: bool = False
) -> None:
    embeds: list[discord.Embed] = []
    end = 10

    character_map = Counter([(card.rarity, card.character_name) for card in cards])
    for start in range(0, len(character_map), 10):
        characters: list[tuple[Rarity, str, int]] = [(rarity, character_name, count) for ((rarity, character_name), count) in character_map.items() if rarity not in Rarity.get_exclusive_rarities()]
        current_properties = sorted(characters, key=lambda c: c[0].level, reverse=descending)[start:end]
        end += 10

        items: list[str] = []
        for rarity, name, count in current_properties:
            items.append(f"{rarity.to_emoji(True)} **{name}** `x{count}`")

        joined_items = "\n".join(items)
        total_cards_text = f"Total cards: `x{len(cards)}`/`{card_limit:,}`" if card_limit is not None else f"Total cards: `x{len(cards)}`"
        embed = create_info_embed(
            interaction,
            f"Viewing the card collection of {user.mention}.\n{total_cards_text}\n\n{joined_items}"
        )
        embeds.append(embed)

    paginator = EmbedPaginator(interaction, embeds)
    embed = paginator.index_page
    await interaction.followup.send(embed=embed, view=paginator)


def _predicate(interaction: discord.Interaction) -> discord.User | discord.Member:
    return interaction.user


BUTTON_COOLDOWN_CACHE = commands.CooldownMapping.from_cooldown(1, 6, type=_predicate)


class _CardDropButton(discord.ui.Button[discord.ui.View]):
    def __init__( self, emoji: str, custom_id: str):
        super().__init__(emoji=emoji, custom_id=custom_id, style=discord.ButtonStyle.gray)
        self.grabbed_cards: list[int] = []

    async def callback(self, interaction: discord.Interaction) -> None:
        if not isinstance(self.view, _CardDropView):
            return None

        bot: Fancards = interaction.client  # type: ignore
        assert self.custom_id

        psql_user = psql.User(bot.pool, interaction.user.id)
        await psql_user.register()

        psql_user_table = await psql_user.get_table()
        assert psql_user_table

        cards = await psql_user.cards.get_cards()
        
        card_count = len(cards) if cards is not None else 0
        backpack_level = psql_user_table.backpack_level

        if card_count >= backpack_level*500:
            embed = create_error_embed(interaction, "Your backpack is full! Consider burning cards or upgrading your backpack.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return None

        selected = int(self.custom_id.partition(".")[-1])
        if selected in self.grabbed_cards:
            reset_cooldown(interaction, BUTTON_COOLDOWN_CACHE)
            embed = create_error_embed(interaction, "That card has already been grabbed.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return None

        self.grabbed_cards.append(selected)
        self.disabled = True
        await interaction.response.edit_message(view=self.view)

        rarity = self.view.cards[selected].rarity
        condition = self.view.cards[selected].condition
        special_rarity = self.view.cards[selected].special_rarity

        card_image = self.view.cards[selected].image
        character_name = self.view.cards[selected].character_name
        card_id = self.view.cards[selected].card_id

        if character_name == "Troll":
            card_image = CardFactory.add_condition(card_image, Condition.pristine, SpecialRarity.unknown)
            buffer = BytesIO()
            card_image.save(buffer, format="PNG")
            buffer.seek(0)

            troll_text = [
                "Did you really just grab me?",
                "LOL you just got trolled!",
                "You must be trolling, you got a **Troll** card!",
                "Looks like fate dealt you a **Troll** card, better luck next time.",
                "Looks like the **Troll** is laughing at your success, congrats on the card!",
                "You got a wild card in the form of a **Troll**, better use it wisely.",
                "Looks like the **Troll** just played his hand, and you were the lucky one to grab it.",
                "Looks like the **Troll** is on your side today, congrats on the card!"
            ]

            embed = create_error_embed(interaction, random.choice(troll_text))
            file = discord.File(buffer, filename=f"card.png")
            embed.set_image(url="attachment://card.png")
            await interaction.followup.send(embed=embed, file=file)
            return None

        user_id = await psql_user.register()

        await psql_user.cards.add_card(
            psql.CardTable(
                card_id=card_id,
                owner_id=user_id,
                rarity=rarity,
                condition=condition,
                special_rarity=special_rarity,
                character_name=character_name,
                created_at=discord.utils.utcnow()
            )
        )
        silver1, silver2 = rarity.to_silver()
        reward_silver = random.randint(silver1//3, silver2//3)

        await psql_user.set_silver(reward_silver)
        
        reward_exp = random.randint(1, 3)
        assert isinstance(interaction.user, discord.Member)
        
        reward_exp = await psql_user.levels.handle_exp_addition(interaction, reward_exp)
        rewards_text = f"You gained **{reward_exp}** EXP and earned {Fanmoji.silver} {reward_silver:,}!"

        card_image = CardFactory.add_condition(card_image, condition, special_rarity)
        buffer = BytesIO()
        card_image.save(buffer, format="PNG")
        buffer.seek(0)

        rarity_text = f"a {rarity.to_emoji(True)} {f'{Fanmoji.shiny} ' if special_rarity is SpecialRarity.shiny else ''}**{character_name}**"

        condition_text_map = {
            Condition.damaged: "Oh.. This card is badly **damaged**.",
            Condition.poor: "It's condition is quite **poor**.",
            Condition.good: "It's in **good** condition.",
            Condition.near_mint: "Cool! It's in **near mint** condition!",
            Condition.mint: "Awesome! It's in **mint** condition!",
            Condition.pristine: "Woah! This card is in **pristine** condition!"
        }

        if self.view.author != interaction.user:
            verb = "stole"
            description = f"{interaction.user.mention} {verb} {rarity_text} card **`{card_id}`** from {self.view.author.mention}!\n{condition_text_map[condition]}\n\n{rewards_text}"
        else:
            verb = "took"
            description = f"{interaction.user.mention} {verb} {rarity_text} card **`{card_id}`**!\n{condition_text_map[condition]}\n\n{rewards_text}"

        rarity_weight = self.view.weight.rarity.value[rarity]
        condition_weight = self.view.weight.condition.value[condition]

        if special_rarity is SpecialRarity.shiny:
            special_rarity_weight = self.view.weight.special_rarity.value[special_rarity]
            special_rarity_text = f"\nSpecial Rarity: {special_rarity.title()} ({special_rarity_weight}%)"
        else:
            special_rarity_text = ""

        embed = create_custom_embed(interaction, description, rarity.to_embed_color())
        embed.set_footer(text=f"Rarity: {rarity.title()} ({rarity_weight}%)\nCondition: {condition.title()} ({condition_weight}%){special_rarity_text}")

        file = discord.File(buffer, filename=f"card.png")
        embed.set_image(url="attachment://card.png")
        await interaction.followup.send(embed=embed, file=file)

        await ActionLogger.card_grab(interaction, rarity, special_rarity, condition, character_name, card_id)

        if rarity in [Rarity.mythic, Rarity.legendary] or special_rarity is SpecialRarity.shiny:
            rare_finds_channel = bot.get_channel(RARE_FINDS_CHANNEL_ID)
            assert isinstance(rare_finds_channel, discord.TextChannel)

            embed.description = f"**{interaction.user.display_name}** {verb} {rarity_text} card **`{card_id}`** from a drop!\n{condition_text_map[condition]}"
            if self.view.weight is PremiumWeight:
                embed.description = f"**{interaction.user.display_name}** {verb} {rarity_text} card **`{card_id}`** from a {Item.premium_drop.display()}!\n{condition_text_map[condition]}"

            buffer = BytesIO()
            card_image.save(buffer, format="PNG")
            buffer.seek(0)

            file = discord.File(buffer, filename=f"card.png")
            embed.set_image(url="attachment://card.png")

            await rare_finds_channel.send(embed=embed, file=file)


class _CardDropView(discord.ui.View):
    def __init__(self, author: discord.User | discord.Member, weight: WeightT):
        super().__init__(timeout=10)
        self.author = author
        self.weight = weight
        self.cards: list[CardImage] = []

    def add_buttons(self) -> None:
        for i, card in enumerate(self.cards):
            button = _CardDropButton(
                emoji=str(card.rarity.to_emoji(True)),
                custom_id=f"drop_button.{i}"
            )
            self.add_item(button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        retry_after = BUTTON_COOLDOWN_CACHE.update_rate_limit(interaction)
        if retry_after and retry_after > 1:
            raise ButtonOnCooldown(retry_after)

        return True

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item[discord.ui.View]) -> None:
        if isinstance(error, ButtonOnCooldown):
            human_time = seconds_to_human(error.retry_after)
            embed = create_error_embed(interaction, f"You are currently on cooldown, please wait for `{human_time}` before grabbing more cards.")
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await super().on_error(interaction, error, item)


class CardCog(commands.Cog):
    def __init__(self, bot: Fancards):
        self.bot = bot
        self.log = bot.log

    card_group = Group(name="card", description="Card related commands")
    card_sleeve_group = Group(name="sleeve", description="Card sleeve related commands", parent=card_group)

    @resettable_cooldown(1, 15)
    @card_group.command(name="drop", description="Drops a set of random cards for everyone to grab")
    async def card_drop(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)

        psql_user = psql.User(self.bot.pool, interaction.user.id)
        await psql_user.register()

        psql_levels_table = await psql_user.levels.get_table()
        assert psql_levels_table

        current_level = psql_levels_table.current_level

        item = await psql_user.inventory.get_item(Item.premium_drop)

        if item is None:
            premium_drop_text = ""
            weight = NewUserWeight if current_level < 5 else BasicWeight

        else:
            reset_command_cooldown(interaction)
            await psql_user.inventory.remove_item(Item.premium_drop)
            item = await psql_user.inventory.get_item(Item.premium_drop)

            amount = item.amount if item is not None else 0

            premium_drop_text = f"Used {Item.premium_drop.display()} `x1`, you now have `x{amount}` remaining.\n\n"
            weight = PremiumWeight

        assert isinstance(interaction.user, discord.Member)
        assert isinstance(weight, WeightT)
        view = _CardDropView(interaction.user, weight=weight)
        cards = CardFactory.generate_card(interaction.user, weight=weight)
        view.cards.extend(cards)
        view.add_buttons()
        
        card_images = [card.image for card in view.cards]
        dropped_cards = CardFactory.align_cards(card_images)

        buffer = BytesIO()
        dropped_cards.save(buffer, format="PNG")
        buffer.seek(0)

        rarest_card = max(cards, key=lambda c: c.rarity.level)
        drop_count = len(view.cards)

        embed = create_custom_embed(
            interaction,
            f"{premium_drop_text}{interaction.user.mention} has dropped {drop_count} cards!",
            rarest_card.rarity.to_embed_color()
        )

        file = discord.File(buffer, filename="dropped_cards.png")
        embed.set_image(url="attachment://dropped_cards.png")

        message = await interaction.followup.send(embed=embed, file=file, view=view, wait=True)
        await ActionLogger.card_drop(interaction, drop_count, weight is PremiumWeight)

        timeout = await view.wait()
        if timeout:
            embed = create_error_embed(interaction, f"{interaction.user.mention} This drop has expired. All remaining cards can no longer be grabbed.")
            embed.set_image(url="attachment://dropped_cards.png")

            for button in view.children:
                if isinstance(button, _CardDropButton):
                    button.disabled = True
                    button.style = discord.ButtonStyle.gray

        await message.edit(embed=embed, view=view)

    @card_group.command(name="collection", description="View your card collection or specify a user to view their collection")
    @app_commands.describe(
        user="View this user's card collection",
        rarity="The rarity of the cards",
        condition="The condition of the cards",
        character_name="The name of the characters on the cards",
        card_age="The age of the cards e.g. 1h 30m",
        locked="Whether the cards are locked",
        card_sleeve="Whether the cards have a sleeve",
        by_card_id="Whether to sort the cards by card-id, cards are sorted by value as default",
        by_character_count="Whether to change to a character count page",
        descending="Whether to sort the cards by descending"
    )
    @app_commands.rename(
        character_name="character",
        card_age="card-age",
        card_sleeve="card-sleeve",
        by_card_id="by-card-id",
        by_character_count="by-character-count"
    )
    @app_commands.autocomplete(
        rarity=rarity_autocomplete,
        condition=condition_autocomplete,
        character_name=character_name_autocomplete
    )
    async def card_collection(
        self,
        interaction: discord.Interaction,
        user: Optional[discord.Member | discord.User] = None,
        rarity: Optional[str] = None,
        condition: Optional[str] = None,
        character_name: Optional[str] = None,
        card_age: Optional[str] = None,
        locked: Optional[bool] = None,
        card_sleeve: Optional[bool] = None,
        by_card_id: bool = False,
        by_character_count: bool = False,
        descending: bool = False
    ):
        await interaction.response.defer(thinking=True)
        user =  interaction.user if user is None or interaction.user == user else user

        psql_user = psql.User(self.bot.pool, user.id)
        psql_user_table = await psql_user.get_table()
        assert psql_user_table

        cards = await psql_user.cards.get_cards()
        if cards is None:
            embed = create_error_embed(interaction, "You currently don't own any cards.")
            if user != interaction.user:
                embed = create_error_embed(interaction, "This user currently doesn't own any card.")

            await interaction.followup.send(embed=embed)
            return None
        
        filtered_cards = _filter_card_collection(
            cards=cards,
            rarity=rarity,
            condition=condition,
            character_name=character_name,
            card_age=card_age,
            locked=locked,
            card_sleeve=card_sleeve,
            by_card_id=by_card_id,
            descending=descending
        )

        if not filtered_cards:
            embed = create_error_embed(interaction, "No cards match the provided filters.")
            await interaction.followup.send(embed=embed)
            return None
        
        backpack_level = psql_user_table.backpack_level
        card_limit = backpack_level*500 if backpack_level < 5 else None
        if not by_character_count:
            await _paginate_card_collection(
                interaction,
                cards=filtered_cards,
                card_count=len(cards),
                user=user,
                card_limit=card_limit,
            )
            return None
        
        await _paginate_character_count(interaction, cards, user, card_limit, descending)


    @card_group.command(name="view", description="View a card to reveal more information about said card")
    @app_commands.describe(card_id="The ID of the card you want to view")
    @app_commands.rename(card_id="card-id")
    @app_commands.autocomplete(card_id=card_id_autocomplete)
    async def card_view(self, interaction: discord.Interaction, card_id: Optional[str] = None):
        await interaction.response.defer(thinking=True)

        psql_user = psql.User(self.bot.pool, interaction.user.id)

        if card_id is None:
            card = await psql_user.cards.get_most_recently_obtained_card()
        else:
            card = await psql_user.cards.get_card(card_id)

        if card is None and card_id is None:
            embed = create_error_embed(interaction, f"You are currently not registered.")
            await interaction.followup.send(embed=embed)
            return None
            
        if card is None:
            embed = create_error_embed(interaction, f"I couldn't find any card with the ID **`{card_id}`**.")
            await interaction.followup.send(embed=embed)
            return None

        card_id = card_id or card.card_id
        owner_id = await psql_user.cards.get_card_owner_id(card_id)
        assert owner_id
        owner = await self.bot.fetch_user(owner_id)

        card_age = (discord.utils.utcnow() - card.created_at).total_seconds()

        base_card = CardFactory.build_card(
            card_id=card.card_id,
            rarity=card.rarity,
            condition=card.condition,
            special_rarity=card.special_rarity,
            character_name=card.character_name
        )
        buffer = BytesIO()
        base_card.save(buffer, format="PNG")
        buffer.seek(0)

        embed = create_custom_embed(interaction, "", color=card.rarity.to_embed_color())
        embed.title = "Viewing card information."

        embed.add_field(name="Owner:", value=owner.mention)
        embed.add_field(name="Card ID:", value=f"**`{card_id}`**")
        embed.add_field(name="Condition:", value=f"`{card.condition.title()} {card.condition.to_unicode()}`")
        embed.add_field(name="Rarity:", value=f"{f'{Fanmoji.shiny}{card.rarity.to_emoji(True)} ' if card.special_rarity is SpecialRarity.shiny else f'{card.rarity.to_emoji(True)} '}**{card.rarity.title()}**")
        embed.add_field(name="Character Name:", value=f"**{card.character_name}**")
        embed.add_field(name="Age:", value=f"`{seconds_to_human(card_age)}`")
        embed.add_field(name="Locked:", value=str(card.locked).title())
        embed.add_field(name="Has Card Sleeve:", value=str(card.has_sleeve).title())
        embed.add_field(name="", value="")

        file = discord.File(buffer, filename="card.png")
        embed.set_image(url="attachment://card.png")

        await interaction.followup.send(embed=embed, file=file)

    @resettable_cooldown(1, 60)
    @card_group.command(
        name="burn", 
        description="Burn a single or multiple cards in exchange for silver, star, and other items",
    )
    @app_commands.describe(card_ids="The ID of the cards you want to burn, separate by space, or all")
    @app_commands.rename(card_ids="card-ids")
    async def card_burn(self, interaction: discord.Interaction, card_ids: Optional[str] = None):
        await interaction.response.defer(thinking=True)
        assert interaction.command
        
        psql_user = psql.User(self.bot.pool, interaction.user.id)
        
        psql_user_table = await psql_user.get_table()
        assert psql_user_table
        if card_ids is None:
            recent_card = await psql_user.cards.get_most_recently_obtained_card()

            if recent_card is None:
                embed = create_error_embed(interaction, "You currently don't own any cards.")
                await interaction.followup.send(embed=embed)
                return None

            await _handle_single_card_burn(interaction, recent_card)
            return None

        if card_ids.casefold() == "all":
            await _handle_all_card_burn(interaction)
            return None

        filtered_card_ids = list(filter(lambda x: x, [card_id.strip() for card_id in card_ids.split(" ")]))
        if len(filtered_card_ids) == 1:
            card = await psql_user.cards.get_card(filtered_card_ids[0])

            if card is None:
                reset_command_cooldown(interaction)
                embed = create_error_embed(interaction, f"I couldn't find any card with the ID `{card_ids}`.")
                await interaction.followup.send(embed=embed)
                return None

            if card.owner_id != psql_user_table.id:
                reset_command_cooldown(interaction)
                embed = create_error_embed(interaction, f"You can only burn cards you own.")
                await interaction.followup.send(embed=embed)
                return None

            await _handle_single_card_burn(interaction, card)

        if len(filtered_card_ids) > 1:
            card_id_count = Counter(filtered_card_ids)
            if [item for item, count in card_id_count.items() if count > 1]:
                reset_command_cooldown(interaction)
                embed = create_error_embed(interaction, "Please don't duplicate your card IDs.")
                await interaction.followup.send(embed=embed)
                return None

            cards = await psql_user.cards.get_cards_by_card_id(filtered_card_ids)

            if cards is None:
                reset_command_cooldown(interaction)
                embed = create_error_embed(interaction, f"I couldn't find any cards with the IDs you provided.")
                await interaction.followup.send(embed=embed)
                return None

            await _handle_multiple_card_burn(interaction, list(cards))

    @card_sleeve_group.command(name="add", description="Add a card sleeve that protects your card from degrading once")
    @app_commands.rename(card_id="card-id")
    @app_commands.describe(card_id="The ID of the card you wanna put in a card sleeve")
    @app_commands.autocomplete(card_id=card_id_autocomplete)
    async def card_sleeve_add(self, interaction: discord.Interaction, card_id: Optional[str] = None):
        await interaction.response.defer(thinking=True)
        await _handle_card_sleeve(interaction, "add", card_id)

    @card_sleeve_group.command(name="remove", description="Remove a card sleeve from the specified card")
    @app_commands.rename(card_id="card-id")
    @app_commands.describe(card_id="The ID of the card you wanna remove the card sleeve from")
    @app_commands.autocomplete(card_id=card_id_autocomplete)
    async def card_sleeve_remove(self, interaction: discord.Interaction, card_id: Optional[str] = None):
        await interaction.response.defer(thinking=True)
        await _handle_card_sleeve(interaction, "remove", card_id)

    @card_group.command(name="lock", description="Locks a card from being burned or used for crafting")
    @app_commands.rename(card_ids="card-ids")
    @app_commands.describe(card_ids="The ID of the cards you wanna lock")
    async def card_lock(self, interaction: discord.Interaction, card_ids: Optional[str] = None):
        await interaction.response.defer(thinking=True)
        await _handle_card_lock(interaction, "lock", card_ids)

    @card_group.command(name="unlock", description="Unlocks a card allowing it to be burned and used for crafting")
    @app_commands.rename(card_ids="card-ids")
    @app_commands.describe(card_ids="The ID of the cards you wanna unlock")
    async def card_unlock(self, interaction: discord.Interaction, card_ids: Optional[str] = None):
        await interaction.response.defer(thinking=True)
        await _handle_card_lock(interaction, "unlock", card_ids)
        

async def setup(bot: Fancards) -> None:
    await bot.add_cog(CardCog(bot))
    