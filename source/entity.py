from __future__ import annotations

import json
import random
from typing import Optional, Any
from io import BytesIO
from typing import TYPE_CHECKING, Optional

import discord

from source.cogs.card import CardImage, CardFactory
from source.enums import Fanmoji, Currency, Rarity, Condition, SpecialRarity, Item, Character
from source.utils import psql, RARE_FINDS_CHANNEL_ID
from source.utils.embed import create_error_embed, create_custom_embed, get_card_property_text

if TYPE_CHECKING:
    from PIL import Image
    from bot import Fancards


CHARACTER_PATH = "./source/assets/characters"


class _CardPackView(discord.ui.View):
    def __init__(self, author: discord.User | discord.Member):
        super().__init__()
        self.author = author
        self.claimed = None

    @discord.ui.button(label="Claim All", emoji=str(Fanmoji.basket), style=discord.ButtonStyle.green)
    async def claim_all(self, interaction: discord.Interaction, button: discord.ui.Button[_CardPackView]) -> None:
        self.claimed = True
        self.stop()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.author != interaction.user:
            await interaction.response.send_message("You don't have the permission to do that.", ephemeral=True)
            return False
           
        return True
    

async def _handle_card_pack(
    cards: list[CardImage],
    interaction: discord.Interaction,
    item: Item,
    message: discord.WebhookMessage
) -> None:
    """Handler of all card packs."""
    bot: Fancards = interaction.client # type: ignore
    view = _CardPackView(interaction.user)

    card_images: list[Image.Image] = [card.image for card in cards]
    aligned_card_images = CardFactory.align_cards(card_images)

    buffer = BytesIO()
    aligned_card_images.save(buffer, format="PNG")
    buffer.seek(0)

    rarest_card = max(cards, key=lambda c: c.rarity.level)
    
    file = discord.File(buffer, filename="pack.png")
    embed = create_custom_embed(
        interaction,
        f"{interaction.user.mention} has opened a {item.display()} and it came with {len(cards)} cards!",
        rarest_card.rarity.to_embed_color()
    )
    embed.set_image(url="attachment://pack.png")

    await message.delete()
    message = await interaction.followup.send(embed=embed, file=file, view=view, wait=True)

    await view.wait()
    if view.claimed is None:
        embed = create_error_embed(interaction, f"{interaction.user.mention} you took too long to claim your pack!")
        await message.edit(embed=embed, view=None)
        return None

    elif view.claimed:
        psql_user = psql.User(bot.pool, interaction.user.id)
        await psql_user.register()

        psql_user_table = await psql_user.get_table()
        assert psql_user_table

        for card in cards:
            if card.character_name == "Troll":
                continue

            await psql_user.cards.add_card(
                psql.CardTable(
                    card_id=card.card_id,
                    owner_id=psql_user_table.id,
                    rarity=card.rarity,
                    condition=card.condition,
                    special_rarity=card.special_rarity,
                    character_name=card.character_name,
                    created_at=discord.utils.utcnow()
                )
            )

        card_property_texts: list[str] = []
        card_images: list[Image.Image] = []
        for card in cards:
            if card.character_name == "Troll":
                card_image = CardFactory.add_condition(card.image, Condition.pristine, SpecialRarity.unknown)
                card_images.append(card_image)
                card_property_text = get_card_property_text(card.card_id, card.rarity, Condition.pristine, card.special_rarity, f"{card.character_name} :D")
                card_property_texts.append(card_property_text)
                continue

            card_image = CardFactory.add_condition(card.image, card.condition, card.special_rarity)
            card_images.append(card_image)
            card_property_text = get_card_property_text(card.card_id, card.rarity, card.condition, card.special_rarity, card.character_name)
            card_property_texts.append(card_property_text)

        card_property_text = "\n".join(card_property_texts)
        aligned_card_images = CardFactory.align_cards(card_images)

        buffer = BytesIO()
        aligned_card_images.save(buffer, format="PNG")
        buffer.seek(0)
        
        file = discord.File(buffer, filename="pack.png")

        embed = create_custom_embed(
            interaction,
            f"{interaction.user.mention} you opened a {item.display()} and claimed these cards:\n\n{card_property_text}",
            rarest_card.rarity.to_embed_color()
        )
        embed.set_image(url="attachment://pack.png")

        await message.delete()
        await interaction.followup.send(embed=embed, file=file, wait=True)

        rarities = [Rarity.mythic, Rarity.legendary] + Rarity.get_valuable_rarities()
        has_any_valuable_cards = any([card.rarity in rarities for card in cards]) or any([card.special_rarity is SpecialRarity.shiny for card in cards])
        if has_any_valuable_cards:
            rare_finds_channel = bot.get_channel(RARE_FINDS_CHANNEL_ID)
            assert isinstance(rare_finds_channel, discord.TextChannel)
            rare_card_images: list[Image.Image] = []

            for card in cards:
                if card.rarity in rarities or card.special_rarity is SpecialRarity.shiny:
                    card_image = CardFactory.add_condition(card.image, card.condition, card.special_rarity)
                    rare_card_images.append(card_image)

            aligned_card_images = CardFactory.align_cards(rare_card_images)

            buffer = BytesIO()
            aligned_card_images.save(buffer, format="PNG")
            buffer.seek(0)

            embed = create_custom_embed(
                interaction,
                f"A {item.display()} was opened by **{interaction.user.display_name}**.",
                rarest_card.rarity.to_embed_color()
            )

            file = discord.File(buffer, filename="pack.png")
            embed.set_image(url="attachment://pack.png")

            await rare_finds_channel.send(embed=embed, file=file)


def _generate_leaked_card(leak_rarity: Rarity, leak_chance: float, deduct_from: int) -> tuple[list[CardImage], int]:
    """A random chance to get a card that has a rarity much higher than the pack's.
    
    Returns the list of generated cards or an empty list and the variable to deduct from.
    """
    if random.random()*100 < leak_chance:
        generated_cards = CardFactory.generate_card(rarity=leak_rarity, amount=1, pack=True)
        return (generated_cards, deduct_from-1)

    return ([], deduct_from)


def _generate_card_pack_contents(member: discord.Member, rarities_and_amounts: list[tuple[Rarity, int]], cards_list: list[CardImage]) -> list[CardImage]:
    for rarity, amount in rarities_and_amounts:
        generated_cards = CardFactory.generate_card(member=member, rarity=rarity, amount=amount, pack=True)
        cards_list.extend(generated_cards)

    return cards_list


async def _use_rare_card_pack(
    interaction: discord.Interaction,
    item: Item,
    message: discord.WebhookMessage
) -> None:
    max_cards = 7
    cards: list[CardImage] = []
    rare_cards = random.randint(2, 4)
    uncommon_cards = max_cards - rare_cards

    generated_cards, rare_cards = _generate_leaked_card(Rarity.epic, 20, rare_cards)
    cards.extend(generated_cards)

    rarities_and_amounts = [
        (Rarity.rare, rare_cards),
        (Rarity.uncommon, uncommon_cards)
    ]
    assert isinstance(interaction.user, discord.Member)
    cards = _generate_card_pack_contents(interaction.user, rarities_and_amounts, cards)

    await _handle_card_pack(cards, interaction, item, message)


async def _use_epic_card_pack(
    interaction: discord.Interaction,
    item: Item,
    message: discord.WebhookMessage
) -> None:
    max_cards = 7
    cards: list[CardImage] = []
    epic_cards = random.randint(1, 2)
    rare_cards = random.randint(0, max_cards - epic_cards)
    uncommon_cards = max_cards - (epic_cards + rare_cards)

    generated_cards, epic_cards = _generate_leaked_card(Rarity.mythic, 10, epic_cards)
    cards.extend(generated_cards)

    rarities_and_amounts = [
        (Rarity.epic, epic_cards),
        (Rarity.rare, rare_cards),
        (Rarity.uncommon, uncommon_cards)
    ]
    assert isinstance(interaction.user, discord.Member)
    cards = _generate_card_pack_contents(interaction.user, rarities_and_amounts, cards)


    await _handle_card_pack(cards, interaction, item, message)


async def _use_mythic_card_pack(
    interaction: discord.Interaction,
    item: Item,
    message: discord.WebhookMessage
) -> None:
    max_cards = 5
    cards: list[CardImage] = []
    mythic_cards = 1
    epic_cards = random.randint(1, 2)
    rare_cards = max_cards - (mythic_cards + epic_cards)

    generated_cards, mythic_cards = _generate_leaked_card(Rarity.legendary, 1, mythic_cards)
    cards.extend(generated_cards)

    rarities_and_amounts = [
        (Rarity.mythic, mythic_cards),
        (Rarity.epic, epic_cards),
        (Rarity.rare, rare_cards)
    ]
    assert isinstance(interaction.user, discord.Member)
    cards = _generate_card_pack_contents(interaction.user, rarities_and_amounts, cards)

    await _handle_card_pack(cards, interaction, item, message)


async def _use_legendary_card_pack(
    interaction: discord.Interaction,
    item: Item,
    message: discord.WebhookMessage
) -> None:
    max_cards = 5
    cards: list[CardImage] = []
    legendary_cards = 1
    mythic_cards = random.randint(0, 1)
    epic_cards = abs(mythic_cards - 1)
    rare_cards = max_cards - (legendary_cards + mythic_cards + epic_cards)

    generated_cards, legendary_cards = _generate_leaked_card(Rarity.exotic, 0.1, legendary_cards)
    cards.extend(generated_cards)

    rarities_and_amounts = [
        (Rarity.legendary, legendary_cards),
        (Rarity.mythic, mythic_cards),
        (Rarity.epic, epic_cards),
        (Rarity.rare, rare_cards)
    ]
    assert isinstance(interaction.user, discord.Member)
    cards = _generate_card_pack_contents(interaction.user, rarities_and_amounts, cards)

    await _handle_card_pack(cards, interaction, item, message)


async def _use_exotic_card_pack(
    interaction: discord.Interaction,
    item: Item,
    message: discord.WebhookMessage
) -> None:
    max_cards = 5
    cards: list[CardImage] = []
    exotic_cards = random.randint(0, 1)
    legendary_cards = random.randint(0, 2)
    mythic_cards = random.randint(0, 1)
    epic_cards = max_cards - (exotic_cards + legendary_cards + mythic_cards)

    rarities_and_amounts = [
        (Rarity.exotic, exotic_cards),
        (Rarity.legendary, legendary_cards),
        (Rarity.mythic, mythic_cards),
        (Rarity.epic, epic_cards)
    ]
    assert isinstance(interaction.user, discord.Member)
    cards = _generate_card_pack_contents(interaction.user, rarities_and_amounts, cards)
    
    await _handle_card_pack(cards, interaction, item, message)


class ItemEntity:
    def __init__(
        self,
        name: str,
        description: str,
        price: Optional[int] = None,
        currency: Optional[str] = None,
        visible: bool = True,
        usable: bool = False
    ) -> None:
        self.name = name
        self.description = description
        self.price = price
        self.currency = Currency(currency) if currency is not None else None
        self.visible = visible
        self.usable = usable
    
    @classmethod
    def to_entity(cls, item: Item) -> ItemEntity:
        with open("source/json/items.json", "r") as file:
            data: dict[str, list[dict[str, Any]]] = json.load(file)

        item_entities: dict[str, ItemEntity] = {}
        for _item in data["items"]:
            item_entities[_item["name"]] = ItemEntity(**_item)

        return item_entities[str(item)]

    @property
    def purchasable(self) -> bool:
        return self.price is not None
    
    async def use(self, interaction: discord.Interaction, item: Item, message: discord.WebhookMessage) -> None:
        handler_map = {
            Item.rare_card_pack: _use_rare_card_pack,
            Item.epic_card_pack: _use_epic_card_pack,
            Item.mythic_card_pack: _use_mythic_card_pack,
            Item.legendary_card_pack: _use_legendary_card_pack,
            Item.exotic_card_pack: _use_exotic_card_pack
        }
        handler = handler_map[item]
        await handler(interaction, item, message)


class CraftableCharacterEntity:
    def __init__(
        self,
        name: str,
        required_characters: dict[str, int],
        required_items: dict[str, int]
    ) -> None:
        self.name = name
        self.rarity = Rarity(Character.get_character_rarity(name))
        self.required_characters = required_characters
        self.required_items = {Item(item): amount for (item, amount) in required_items.items()}

    @staticmethod
    def to_entity(character_name: str) -> CraftableCharacterEntity:
        with open("source/json/craftable_characters.json", "r") as file:
            data: dict[str, list[dict[str, Any]]] = json.load(file)

        mapping = {character["name"]: CraftableCharacterEntity(**character) for character in data["characters"]}
        return mapping[character_name]
    
    @staticmethod
    def get_character_names() -> list[str]:
        with open("source/json/craftable_characters.json", "r") as file:
            data: dict[str, list[dict[str, Any]]] = json.load(file)

        return [character["name"] for character in data["characters"]]
